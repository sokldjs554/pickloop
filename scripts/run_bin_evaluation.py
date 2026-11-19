"""Evaluate an RGB-D opening estimate, and its use by the real pick/place loop."""
import argparse
from dataclasses import asdict, replace
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import tempfile

import cv2
import numpy as np
from PIL import Image

from pickloop.bin_perception import detect_bin
from pickloop.engine import run_job
from pickloop.geometry import project
from pickloop.simulation import BinFixture, Cell, ROOT
from pickloop.types import OperationError


SEED_START = 74100
NUM_SCENES = 32
JOB_INDICES = (0, 1, 2, 3, 4, 5, 6, 7)


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def scene_fixture(seed):
    # Independent draws for each cell parameter; the bin detector has no seed input.
    rng = np.random.default_rng(seed)
    return BinFixture((rng.uniform(.215, .445), rng.uniform(.135, .180)),
                      (rng.uniform(.170, .220), rng.uniform(.100, .145)),
                      rng.uniform(-np.pi / 3, np.pi / 3), rng.uniform(.043, .081))


def perturb_depth(obs, seed):
    rng = np.random.default_rng(np.random.SeedSequence([seed, 573]))
    depth = obs.depth + rng.normal(0, .00065, obs.depth.shape).astype(obs.depth.dtype)
    depth[rng.random(depth.shape) < .025] = np.nan
    return replace(obs, depth=depth)


def save_example(out, obs, fixture, estimate):
    folder = out / 'example'
    folder.mkdir()
    Image.fromarray(obs.rgb).save(folder / 'rgb.png')
    np.savez_compressed(folder / 'depth-calibration.npz', depth_m=obs.depth, K=obs.K,
                        T_base_camera=obs.T_base_camera)
    write_json(folder / 'observation.json', dict(run_id=obs.run_id, observation_id=obs.observation_id,
               sim_time=obs.sim_time, calibration_id=obs.calibration_id, truth=asdict(fixture),
               estimate=asdict(estimate)))
    c, s = np.cos(estimate.yaw_rad), np.sin(estimate.yaw_rad)
    xy = np.array([[-1, -1], [-1, 1], [1, 1], [1, -1]]) * np.array(estimate.inner_size_m) / 2
    xy = xy @ np.array([[c, s], [-s, c]]) + estimate.center_xy_m
    uv, _ = project(np.column_stack((xy, np.full(4, estimate.rim_z_m))), obs.K, obs.T_base_camera)
    canvas = obs.rgb.copy()
    cv2.polylines(canvas, [np.round(uv).astype(np.int32)], True, (255, 205, 70), 2, cv2.LINE_AA)
    Image.fromarray(canvas).save(folder / 'fitted-opening.png')


def measure_scene(out, index):
    seed = SEED_START + index
    fixture = scene_fixture(seed)
    row = dict(seed=seed, fixture=asdict(fixture), estimate=None, errors=None, failure=None)
    with Cell(seed=seed, run_id=f'bin-sweep-{seed}', bin_layout=[fixture]) as cell:
        obs = perturb_depth(cell.observe(), seed)
        try:
            estimate = detect_bin(obs, cell.sim_time)
        except OperationError as exc:
            row['failure'] = exc.code
            return row
        if index == 0:
            save_example(out, obs, fixture, estimate)
    angular_error = abs((estimate.yaw_rad - fixture.yaw_rad + np.pi / 2) % np.pi - np.pi / 2)
    size_error = np.abs(np.array(estimate.inner_size_m) - fixture.inner_size_m) * 1000
    row['estimate'] = asdict(estimate)
    row['errors'] = dict(center_xy_mm=float(np.linalg.norm(np.array(estimate.center_xy_m) - fixture.center_xy_m) * 1000),
                         long_mm=float(size_error[0]), short_mm=float(size_error[1]),
                         yaw_deg=float(np.rad2deg(angular_error)),
                         floor_z_mm=abs(estimate.floor_z_m - .072) * 1000,
                         cavity_depth_mm=abs(estimate.rim_z_m - estimate.floor_z_m - fixture.depth_m) * 1000)
    return row


def run_case(out, work, name, seed, fixtures, sku, policy='baseline'):
    result = run_job(seed=seed, policy=policy, out_dir=work, record=False, sku=sku,
                     job_id=name, bin_layout=fixtures)
    folder = out / 'jobs' / name
    folder.mkdir(parents=True)
    source = Path(work) / result['run_id']
    for filename in ('result.json', 'events.jsonl', 'calibration.json'):
        shutil.copyfile(source / filename, folder / filename)
    return dict(case=name, seed=seed, sku=sku, policy=policy, fixture_count=len(fixtures), status=result['status'],
                reason=result['reason'], success=result['success'], observed_fits=len(result['bin_estimates']),
                vision_verified=result['metrics']['verified_by_vision'], truth_verified=result['metrics']['verified_by_truth'],
                drops=result['metrics']['drops'], collisions=result['metrics']['collisions'],
                wrong_placements=result['metrics']['wrong_placements'], evidence=f'jobs/{name}/result.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='Fresh output directory')
    out = parser.parse_args().out
    if out.exists() and any(out.iterdir()):
        parser.error('--out must be empty to preserve recorded measurements')
    out.mkdir(parents=True, exist_ok=True)
    rows = [measure_scene(out, index) for index in range(NUM_SCENES)]
    write_json(out / 'perception-trials.json', rows)
    errors = [entry['errors'] for entry in rows if entry['errors'] is not None]
    metrics = {}
    for key in (errors[0] if errors else {}):
        values = [row[key] for row in errors]
        metrics[key] = dict(mean=float(np.mean(values)), p95=float(np.percentile(values, 95)), max=max(values))

    with tempfile.TemporaryDirectory(prefix='pickloop-bin-') as work:
        jobs = []
        for index in JOB_INDICES:
            seed = SEED_START + index
            sku = ('SKU-RED-A', 'SKU-RED-B')[index % 2]
            jobs.append(run_case(out, work, f'single-{seed}', seed, [scene_fixture(seed)], sku))
        jobs.append(run_case(out, work, 'missing', SEED_START + NUM_SCENES, [], 'SKU-RED-A', policy='recovery'))
        pair = [BinFixture((.19, .17), (.175, .108), .22, .052),
                BinFixture((.45, .18), (.202, .125), -.31, .063)]
        jobs.append(run_case(out, work, 'ambiguous', SEED_START + NUM_SCENES + 1, pair, 'SKU-RED-A', policy='recovery'))
        touching = [BinFixture((.238, .16), (.16, .13), 0., .055),
                    BinFixture((.414, .16), (.16, .13), 0., .055)]
        jobs.append(run_case(out, work, 'touching', SEED_START + NUM_SCENES + 2, touching, 'SKU-RED-A', policy='recovery'))
        narrow = [BinFixture((.35, .16), (.16, .079), .20, .055)]
        jobs.append(run_case(out, work, 'undersized', SEED_START + NUM_SCENES + 3, narrow, 'SKU-RED-A', policy='recovery'))
    sources = ['src/pickloop/bin_perception.py', 'src/pickloop/simulation.py', 'src/pickloop/engine.py',
               'src/pickloop/geometry.py', 'src/pickloop/perception.py', 'src/pickloop/types.py',
               'scripts/run_bin_evaluation.py', 'models/appearance.pt']
    summary = dict(schema_version=1, protocol='bin-rgbd-v1', seed_start=SEED_START,
                   sweep=dict(fitted=len(errors), total=len(rows), depth_noise_std_m=.00065,
                              depth_dropout=.025, errors=metrics),
                   placement_jobs_completed=sum(j['success'] for j in jobs[:len(JOB_INDICES)]),
                   placement_jobs_total=len(JOB_INDICES),
                   negative_control_holds=sum(j['status'] == 'HELD' for j in jobs[len(JOB_INDICES):]),
                   negative_controls_total=len(jobs) - len(JOB_INDICES), jobs=jobs,
                   source_sha256={rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in sources},
                   versions={name: version(name) for name in ('mujoco', 'numpy', 'opencv-python-headless', 'torch')})
    write_json(out / 'metrics.json', summary)
    print(json.dumps(dict(fitted=len(errors), scenes=len(rows), jobs=[(j['case'], j['status'], j['reason']) for j in jobs])))


if __name__ == '__main__':
    main()
