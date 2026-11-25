"""Identify an ordered grocery SKU in camera images and physically deliver the selected parcel."""
from dataclasses import asdict
import argparse
import hashlib
import json
import re
from decimal import Decimal
import time
from pathlib import Path
import subprocess

import cv2
import numpy as np
from PIL import Image

from .bin_perception import detect_bin
from .catalogue_features import CatalogueEncoder, WEIGHTS_SHA
from .catalogue_model import CatalogueHead
from .geometry import backproject
from .grocery_catalogue import DEFAULT_HEAD, resolve_decision
from .juice_gate import TARGETS, apply_juice_gate, confirmed_flavour, ocr
from .perception import Perception
from .simulation import BinFixture, Cell, ROOT
from .types import OperationError


ORANGE = 'God-Morgon-Orange-Juice'
MIX = 'God-Morgon-Orange-Red-Grapefruit-Juice'
MINT = 'Unregistered-Mint-Tea'
ART = ROOT / 'assets/order-pick'
CASES = {'standard': ('orange', 'mixed', 'mint'), 'swapped': ('mixed', 'orange', 'mint'),
         'duplicate': ('orange-1000ml', 'orange-1000ml', 'mint'),
         'different-sizes': ('orange-1000ml', 'orange-500ml', 'mint'),
         'ambiguous': ('orange', 'orange', 'mint'), 'unreadable': ('orange-obscured', 'mixed', 'mint'),
         'absent': ('mixed', 'mint', 'mint'), 'unknown-only': ('mint', 'mint', 'mint')}
BIN = BinFixture((.34, .185), (.204, .145), .20, .056)


def write_json(path, record):
    path.write_text(json.dumps(record, indent=2, allow_nan=False, ensure_ascii=False) + '\n')


def save_depth(path, depth):
    # Float-bit row differences compress slanted planar depths without changing
    # any sensor values. Recover with uint32 cumsum along x, then view float32.
    bits = np.ascontiguousarray(depth, dtype='<f4').view('<u4')
    delta = np.empty_like(bits)
    delta[:, 0] = bits[:, 0]
    delta[:, 1:] = bits[:, 1:] - bits[:, :-1]
    np.savez_compressed(path, depth_f32_u32_dx=delta)


def camera_metadata(obs):
    return dict(observation_id=obs.observation_id, sim_time_s=round(obs.sim_time, 6),
                received_monotonic_ns=obs.received_ns, resolution_px=list(obs.depth.shape[::-1]),
                calibration_id=obs.calibration_id, K=obs.K.tolist(), T_base_camera=obs.T_base_camera.tolist())


def inspect_face(obs, wide_point):
    """Rectify the measured top face; camera pixels, depth and intrinsics are the only inputs."""
    obs.validate(obs.sim_time)
    valid = np.isfinite(obs.depth) & (obs.depth > .05) & (obs.depth < 3.)
    v, u = np.nonzero(valid)
    xyz = backproject(np.column_stack((u, v)), obs.depth[v, u], obs.K, obs.T_base_camera)
    mask = np.zeros(obs.depth.shape, np.uint8)
    mask[v, u] = (np.abs(xyz[:, 2] - wide_point[2]) < .003)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    center = (obs.depth.shape[1] / 2, obs.depth.shape[0] / 2)
    center_faces = [c for c in contours if cv2.pointPolygonTest(c, center, False) >= 0 and cv2.contourArea(c) > 2000]
    if len(center_faces) != 1:
        raise OperationError('ZOOM_FACE_UNRESOLVED')
    contour = center_faces[0]
    corners = cv2.approxPolyDP(contour, .018 * cv2.arcLength(contour, True), True)[:, 0]
    if len(corners) != 4:
        raise OperationError('ZOOM_FACE_UNRESOLVED')
    # All demonstration parcels are loaded face-up, with their lettering within
    # 15 degrees of upright. Derive the small yaw and actual corners from depth.
    upper, lower = np.split(corners[np.argsort(corners[:, 1])], 2)
    tl, tr = upper[np.argsort(upper[:, 0])]
    bl, br = lower[np.argsort(lower[:, 0])]
    ordered = np.float32([tl, tr, br, bl])
    width = int(round((np.linalg.norm(tr-tl) + np.linalg.norm(br-bl)) / 2))
    height = int(round((np.linalg.norm(bl-tl) + np.linalg.norm(br-tr)) / 2))
    target = np.float32([(0, 0), (width-1, 0), (width-1, height-1), (0, height-1)])
    face = cv2.warpPerspective(obs.rgb, cv2.getPerspectiveTransform(ordered, target), (width, height))

    # Intersect the commanded camera rays with the measured horizontal top plane.
    rays = np.column_stack((ordered, np.ones(4))) @ np.linalg.inv(obs.K).T @ obs.T_base_camera[:3, :3].T
    base = obs.T_base_camera[:3, 3]
    corners_m = base + rays * ((wide_point[2] - base[2]) / rays[:, 2])[:, None]
    edge = corners_m[1] - corners_m[0]
    return face, dict(corners_px=ordered.tolist(), corners_base_m=corners_m.tolist(),
                      top_yaw_rad=float(np.arctan2(edge[1], edge[0])))


def confirmed_volume(reads):
    """Agree on one volume in both camera reads of the fixture's shipping label."""
    volumes = []
    for line in reads:
        values = set()
        for number, unit in re.findall(r'(?<![\w.,-])(\d+(?:[.,]\d+)?)\s*(ml|cl|l)\b', line.lower()):
            ml = Decimal(number.replace(',', '.')) * {'ml': 1, 'cl': 10, 'l': 1000}[unit]
            if ml > 0 and ml == int(ml):
                values.add(int(ml))
        volumes.append(values)
    if len(set().union(*volumes)) > 1:
        return None, 'conflict'
    if len(volumes) == 2 and all(len(values) == 1 for values in volumes):
        return next(iter(volumes[0])), 'confirmed'
    return None, 'unreadable'


def shipping_label_decision(generic, carton, first_face, second_face):
    """Require agreement between accepted catalogue identity and the human-readable label."""
    if generic['prediction'] not in TARGETS:
        return dict(prediction='UNKNOWN', reason='catalogue_hold_or_unstocked', reads=[])
    # Identical lower strip for every parcel. The two readings use distinct
    # optical sampling (4.2 and 4.6 degree FOV) of the same physical label.
    reads = []
    try:
        for index, face in enumerate((first_face, second_face)):
            band = face[int(len(face) * .795):]
            gray = cv2.cvtColor(cv2.resize(band, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC), cv2.COLOR_RGB2GRAY)
            if index == 1:
                _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            reads.append(ocr(255-gray, 6))
    except (OSError, subprocess.SubprocessError) as exc:
        return dict(prediction='UNKNOWN', reason=f'ocr_unavailable:{type(exc).__name__}', reads=[])
    named, reason = confirmed_flavour(reads, located_panel=False)
    if named is None:
        return dict(prediction='UNKNOWN', reason=reason, reads=reads)
    if carton['prediction'] == 'UNKNOWN' and any(carton.get('juice_gate_text', [])):
        return dict(prediction='UNKNOWN', reason='carton_text_unconfirmed', label_prediction=named, reads=reads)
    if named != generic['prediction'] or carton['prediction'] not in ('UNKNOWN', named):
        return dict(prediction='UNKNOWN', reason='flavour_disagrees_with_classifier', label_prediction=named, reads=reads)
    volume_ml, volume_status = confirmed_volume(reads)
    return dict(prediction=named, reason='catalogue_and_shipping_label_agree', reads=reads,
                volume_ml=volume_ml, volume_status=volume_status)


class Reader:
    def __init__(self, weights):
        self.encoder = CatalogueEncoder(weights)
        self.head = CatalogueHead.load(DEFAULT_HEAD)

    def read(self, faces, second_faces):
        generic = self.head.predict(self.encoder.encode(faces))
        decisions = []
        for row, face, second in zip(generic, faces, second_faces, strict=True):
            resolved = resolve_decision(row, lambda: face)
            final = apply_juice_gate(resolved, lambda: face)
            shipping = shipping_label_decision(row, final, face, second)
            decisions.append(dict(generic=row, carton_gate=final, shipping_label=shipping, prediction=shipping['prediction'],
                                  decision_source='catalogue_and_shipping_label_ocr' if shipping['prediction'] != 'UNKNOWN' else 'hold'))
        return decisions


def read_candidates(cell, obs, proposals, reader, directory, name):
    rows, faces, second_faces = [], [], []
    for index, proposal in enumerate(sorted(proposals, key=lambda p: p['bbox'][0]), 1):
        if proposal['depth_valid_ratio'] < .8 or proposal['uncertainty_m'] > .006:
            raise OperationError('DEPTH_UNCERTAIN')
        detail = cell.inspect_point(proposal['position'])
        face, geometry = inspect_face(detail, proposal['position'])
        prefix = f'{name}-{index}'
        Image.fromarray(detail.rgb).save(directory / f'{prefix}-camera.png')
        Image.fromarray(face).save(directory / f'{prefix}-face.png')
        save_depth(directory / f'{prefix}-depth.npz', detail.depth)
        confirm = cell.inspect_point(proposal['position'], fovy=4.6)
        second, second_geometry = inspect_face(confirm, proposal['position'])
        Image.fromarray(confirm.rgb).save(directory / f'{prefix}-second-camera.png')
        Image.fromarray(second).save(directory / f'{prefix}-second-face.png')
        save_depth(directory / f'{prefix}-second-depth.npz', confirm.depth)
        rows.append(dict(candidate_id=prefix, bbox_xywh_px=list(proposal['bbox']),
                         position_m=proposal['position'].tolist(), uncertainty_m=proposal['uncertainty_m'],
                         depth_valid_ratio=proposal['depth_valid_ratio'], source_observation_id=obs.observation_id,
                         zoom=camera_metadata(detail), zoom_camera=f'{prefix}-camera.png',
                         zoom_depth=f'{prefix}-depth.npz', crop=f'{prefix}-face.png', **geometry,
                         confirmation=dict(camera=camera_metadata(confirm), image=f'{prefix}-second-camera.png',
                                           crop=f'{prefix}-second-face.png', depth=f'{prefix}-second-depth.npz',
                                           **second_geometry)))
        faces.append(face)
        second_faces.append(second)
    if faces:
        for candidate, decision in zip(rows, reader.read(faces, second_faces), strict=True):
            candidate.update(decision)
    return rows


def pick_plan(cell, candidate):
    """Check room for the cup on the measured face and the unloaded approach."""
    p = np.asarray(candidate['position_m'])
    face_xy = np.array(candidate['corners_base_m'], np.float32)[:, :2].copy()
    margin = cv2.pointPolygonTest(face_xy, tuple(p[:2]), True)
    approach = [*p[:2], .28]
    result = dict(eligible=False, face_edge_distance_m=margin,
                  required_edge_distance_m=.012 + candidate['uncertainty_m'],
                  approach_distance_m=float(np.linalg.norm(np.asarray(cell.tcp) - approach)))
    if margin < result['required_edge_distance_m']:
        return {**result, 'reason': 'INSUFFICIENT_CUP_CLEARANCE'}
    try:
        hover, _, _ = cell.plan_move(approach, allow_contact=False)
        cell.plan_move(p, allow_contact=True, start=hover)
    except OperationError as exc:
        return {**result, 'reason': exc.code}
    return {**result, 'eligible': True, 'reason': 'CLEAR_APPROACH'}


def identity_matches(order, candidates, volume_ml):
    if any(row['prediction'] == 'UNKNOWN' and order in
           (row['generic']['prediction'], row['shipping_label'].get('label_prediction')) for row in candidates):
        raise OperationError('ORDER_LABEL_UNCONFIRMED')
    matches = [row for row in candidates if row['prediction'] == order]
    if not matches:
        raise OperationError('ORDER_NOT_FOUND')
    labels = [row['shipping_label'] for row in matches]
    if any(label.get('volume_status') == 'conflict' for label in labels):
        raise OperationError('ORDER_VOLUME_UNCONFIRMED')
    if volume_ml is None and len(matches) == 1:
        return matches  # A single flavour-only order retains its historical semantics.
    if any(label.get('volume_status') != 'confirmed' for label in labels):
        raise OperationError('ORDER_VOLUME_UNCONFIRMED')
    if volume_ml is None:
        if len({label['volume_ml'] for label in labels}) != 1:
            raise OperationError('ORDER_VOLUME_AMBIGUOUS')
        return matches
    exact = [row for row in matches if row['shipping_label']['volume_ml'] == volume_ml]
    if not exact:
        raise OperationError('ORDER_VOLUME_MISMATCH')
    return exact


def choose(order, candidates, volume_ml=None):
    matches = identity_matches(order, candidates, volume_ml)
    safe = [row for row in matches if row['pick_plan']['eligible']]
    if not safe:
        raise OperationError('ORDER_NO_SAFE_APPROACH')
    return min(safe, key=lambda row: (row['pick_plan']['approach_distance_m'], row['candidate_id']))


class Record:
    def __init__(self, cell, directory):
        self.cell = cell
        self.directory = directory
        self.frames = []
        self.trace = []
        self.movie = None
        self.next_time = 0.
        self.movie_frames = 0
        self.require_seal = False

    def event(self, stage, **details):
        c = self.cell
        row = dict(stage=stage, sim_time_s=round(c.sim_time, 6), tcp_m=c.tcp.tolist(),
                   pressure_kpa=c.pressure_kpa, valve_on=c.valve, **details)
        self.trace.append(row)

    def photo(self, stage, rgb=None, **details):
        self.event(stage, **details)
        filename = f'{len(self.frames):02d}-{stage.lower()}.jpg'
        Image.fromarray(self.cell.render_scene() if rgb is None else rgb).save(self.directory/filename, quality=90)
        self.frames.append(dict(stage=stage, sim_time_s=round(self.cell.sim_time, 6), image=filename))

    def start_movie(self):
        self.movie = subprocess.Popen(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                   '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '640x480', '-framerate', '6',
                   '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-threads', '1', '-preset', 'veryfast',
                   '-crf', '22', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(self.directory/'motion.mp4')],
                   stdin=subprocess.PIPE)
        self.next_time = self.cell.sim_time
        self.sample(self.cell)
        self.cell.on_step = self.sample

    def sample(self, cell):
        if self.require_seal and cell.pressure_kpa > -35 and not cell._stopping:
            raise OperationError('VACUUM_LOSS')
        if cell.sim_time + 1e-8 >= self.next_time:
            self.movie.stdin.write(cell.render_scene().tobytes())
            self.movie_frames += 1
            self.next_time += 1/6

    def close(self):
        self.cell.on_step = None
        if self.movie is not None:
            self.movie.stdin.close()
            if self.movie.wait():
                raise RuntimeError('ffmpeg failed to encode the scene-camera record')


def move_order(cell, rec, selected, destination):
    xy = destination.center_xy_m
    p = selected['position_m']
    rec.start_movie()
    cell.move_to([*p[:2], .28], allow_contact=False)
    cell.move_to(p, allow_contact=True)
    rec.photo('APPROACH', source_candidate=selected['candidate_id'])
    cell.command_suction(True)
    rec.event('VALVE_COMMAND', value=True)
    cell.step_for(.20)
    if cell.pressure_kpa > -35:
        raise OperationError('SEAL_NOT_CONFIRMED')
    rec.require_seal = True
    rec.photo('SEALED')
    cell.move_to([*p[:2], .30])
    rec.photo('LIFTED')
    cell.move_to([*xy, .30], allow_contact=False)
    rec.photo('TRANSPORTED', bin_observation_id=destination.observation_id)
    cell.move_to([*xy, destination.floor_z_m + .063], allow_contact=True)
    rec.photo('PLACED')
    rec.require_seal = False
    cell.command_suction(False)
    rec.event('VALVE_COMMAND', value=False)
    cell.step_for(.40)
    rec.photo('RELEASED')
    cell.move_to([*xy, .30], allow_contact=False)
    cell.move_to([.19, -.32, .30], allow_contact=False)
    cell.move_to([.19, -.32, .34], allow_contact=False)
    cell.step_for(.15)


def verify_camera(cell, reader, directory, order, volume_ml, output):
    obs = cell.observe()
    output['camera'] = camera_metadata(obs)
    Image.fromarray(obs.rgb).save(directory/'placed-overview.png')
    dest = detect_bin(obs, cell.sim_time)
    proposals = [p for p in Perception.proposals(obs, cell.sim_time) if dest.contains_payload(p['position'][:2])]
    candidates = read_candidates(cell, obs, proposals, reader, directory, 'placed')
    output['candidates'] = candidates
    matches = identity_matches(order, candidates, volume_ml)
    if len(candidates) != 1:
        raise OperationError('DESTINATION_COUNT_MISMATCH')
    p = np.asarray(matches[0]['position_m'])
    cell.step_for(.2)
    second = cell.observe()
    dest = detect_bin(second, cell.sim_time)
    locations = [r['position'] for r in Perception.proposals(second, cell.sim_time) if dest.contains_payload(r['position'][:2])]
    if len(locations) != 1 or np.linalg.norm(locations[0] - p) > .004 or abs(p[2] - dest.floor_z_m - .05) > .010:
        raise OperationError('PLACEMENT_UNSTABLE')
    if cell.valve or cell.pressure_kpa < -3:
        raise OperationError('RELEASE_NOT_CONFIRMED')
    output.update(verified=True, second_observation=camera_metadata(second), second_position_m=locations[0].tolist())


def independent_evaluation(cell, fixtures, order, volume_ml):
    # Consult the physical material manifest only after the control loop ends.
    truth = cell.truth_summary()
    objects = [dict(sku=label['sku'], volume_ml=label.get('volume_ml'), fixture_texture=label['texture'],
                    position_m=item['position'], speed_m_s=item['speed_m_s'], in_bin=item['in_bin'])
               for item, label in zip(truth['objects'], fixtures, strict=True)]
    inside = [obj for obj in objects if obj['in_bin']]
    delivered = inside[0] if len(inside) == 1 else {}
    wrong = sum(obj['sku'] != order or (volume_ml is not None and obj['volume_ml'] != volume_ml) for obj in inside)
    correct = bool(delivered and not wrong and delivered['speed_m_s'] < .02 and truth['attached'] is None)
    return dict(verified=correct, delivered_sku=delivered.get('sku'), delivered_volume_ml=delivered.get('volume_ml'),
                count_in_bin=len(inside), objects=objects, attached_at_finish=truth['attached'] is not None,
                drops=truth['drop_count'], collisions=truth['collision_count'], wrong_placements=wrong)


def run_case(case, order, directory, reader, seed=21, volume_ml=None):
    if volume_ml is not None and (type(volume_ml) is not int or volume_ml <= 0):
        raise ValueError('Order volume must be a positive integer in mL')
    if case not in CASES:
        raise ValueError(f'Unsupported layout {case}')
    if order not in reader.head.names:
        raise ValueError('Order SKU must exist in the loaded catalogue')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError('Use an empty output directory to preserve existing evidence')
    manifest = json.loads((ART/'manifest.json').read_text())
    fixtures = {entry['texture']: entry for entry in manifest['labels']}
    textures = [ART/f'{name}.png' for name in CASES[case]]
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != fixtures[path.name]['texture_sha256'] for path in textures):
        raise ValueError('Parcel texture checksum mismatch')
    start_wall = time.time_ns()
    with Cell(seed=seed, run_id=directory.name, bin_layout=[BIN], parcel_textures=textures) as cell:
        record = Record(cell, directory)
        output = dict(schema_version=2, id=directory.name, case=case, order_sku=order, order_volume_ml=volume_ml, quantity=1, seed=seed,
                      started_unix_ns=start_wall, sensor='MuJoCo rendered RGB-D overview + steerable optical zoom',
                      catalogue_classes=len(reader.head.names), head_sha256=hashlib.sha256(DEFAULT_HEAD.read_bytes()).hexdigest(),
                      encoder_sha256=WEIGHTS_SHA, fixture_manifest_sha256=hashlib.sha256((ART/'manifest.json').read_bytes()).hexdigest(),
                      status='HELD', reason=None, selected=None, candidates=[], placement_camera={'verified':False})
        try:
            obs = cell.observe()
            output['overview'] = camera_metadata(obs)
            Image.fromarray(obs.rgb).save(directory/'overview.png')
            save_depth(directory/'overview-depth.npz', obs.depth)
            record.photo('OBSERVE', obs.rgb, observation_id=obs.observation_id)
            destination = detect_bin(obs, cell.sim_time)
            output['destination'] = asdict(destination)
            proposals = [p for p in Perception.proposals(obs, cell.sim_time) if p['position'][1] < .10]
            output['candidates'] = read_candidates(cell, obs, proposals, reader, directory, 'source')
            selectable = identity_matches(order, output['candidates'], volume_ml)
            for candidate in selectable:
                candidate['pick_plan'] = pick_plan(cell, candidate)
            selected = choose(order, output['candidates'], volume_ml)
            output['selection'] = dict(rule='shortest_clear_approach_then_candidate_id',
                                       start_tcp_m=cell.tcp.tolist(), matching_ids=[r['candidate_id'] for r in selectable],
                                       selected_id=selected['candidate_id'])
            selected_volume = selected['shipping_label']['volume_ml']
            output['selected'] = {key: selected[key] for key in ('candidate_id','position_m','bbox_xywh_px','top_yaw_rad','crop','prediction')}
            output['selected']['volume_ml'] = selected_volume
            record.event('ORDER_MATCHED', candidate=selected['candidate_id'], observation_id=obs.observation_id)
            fresh = cell.observe()
            matches = [p for p in Perception.proposals(fresh, cell.sim_time)
                       if np.linalg.norm(np.asarray(selected['position_m']) - p['position']) < .003]
            if len(matches) != 1:
                raise OperationError('TARGET_MOVED')
            record.event('POSE_RECONFIRMED', observation_id=fresh.observation_id, position_m=matches[0]['position'].tolist())
            move_order(cell, record, selected, destination)
            verify_camera(cell, reader, directory, order, selected_volume, output['placement_camera'])
            output['status'] = 'COMPLETED'
            record.photo('VERIFIED')
        except OperationError as exc:
            output['reason'] = exc.code
            record.require_seal = False
            output['stop'] = cell.stop_motion()
            record.photo('HELD', cell.observe().rgb, reason=exc.code)
        finally:
            record.close()
        expected_volume = output['selected']['volume_ml'] if output['selected'] else volume_ml
        output['evaluation'] = independent_evaluation(cell, [fixtures[p.name] for p in textures], order, expected_volume)
        if output['status'] == 'COMPLETED' and not output['evaluation']['verified']:
            output['status'], output['reason'] = 'HELD', 'EVALUATOR_DISAGREEMENT'
        output.update(frames=record.frames, trace=record.trace, clip='motion.mp4' if record.movie_frames else None,
                      clip_fps=6, clip_frames=record.movie_frames, finished_sim_time_s=round(cell.sim_time, 6),
                      finished_unix_ns=time.time_ns())
    write_json(directory/'result.json', output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, default='standard')
    parser.add_argument('--order', default=ORANGE)
    parser.add_argument('--volume-ml', type=int, help='required label volume in mL')
    parser.add_argument('--weights', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=21)
    args = parser.parse_args()
    result = run_case(args.case, args.order, args.out, Reader(args.weights), args.seed, args.volume_ml)
    print(json.dumps({k: result[k] for k in ('id','case','order_sku','status','reason','selected')}, indent=2))


if __name__ == '__main__':
    main()
