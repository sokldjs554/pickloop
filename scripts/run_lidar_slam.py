#!/usr/bin/env python3
"""Collect a mobile simulator loop, run offline SLAM and score against held-out truth."""
import argparse
import hashlib
import json
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

from pickloop.lidar_slam import (estimate, integrate_encoders, match_scans,
                                 occupancy_grid, relative, rotation)
from pickloop.mobile import DT, FleetScheduler, MobileMap, MobileSimulation, ROOT, wrap


def collect(seed):
    """Generate scans with the existing simulator. The known-map EKF drives the vehicle."""
    world = MobileMap.load()
    robot = 'amr-1'
    fleet = FleetScheduler(world.config['robot_starts_m_rad'])
    fleet.acquire(robot, 0.)
    start = np.array(world.config['robot_starts_m_rad'][robot], dtype=float)
    truth = start.copy()
    odometry = np.zeros(3)
    frames, sample_count, last_frame = [], 0, None

    def capture(event, sim_time, name, state, data):
        nonlocal truth, odometry, sample_count, last_frame
        if event != 'SAMPLE':
            return
        # MobileSimulation.tick raycasts before motion; the encoder and reported
        # truth describe the subsequent interval. Pair this scan with its start.
        last_frame = (sim_time - DT, odometry.copy(), np.asarray(data['lidar_ranges_m']), truth.copy())
        if not frames:
            frames.append(last_frame)
        else:
            change = relative(frames[-1][1], odometry)
            if np.linalg.norm(change[:2]) >= .30 or abs(change[2]) >= .34:
                frames.append(last_frame)
        odometry = integrate_encoders(odometry, data['encoder_m_s'], DT)
        truth = np.asarray(data['truth_pose_m_rad'])
        sample_count += 1

    sim = MobileSimulation(world, seed, capture, fleet, threading.Event(), 240., time.monotonic() + 120.)
    waypoints = [[6.35, 1., np.pi / 2], [6.35, 4.05, np.pi],
                 [1.05, 4.05, -np.pi / 2], [*start[:2], start[2]]]
    for i, target in enumerate(waypoints):
        sim.drive(robot, target, 'MAPPING')
        if i == 1:
            open_count = len(frames)
    if frames[-1][0] != last_frame[0]:
        frames.append(last_frame)
    timestamps, wheels, ranges, truth = map(np.asarray, zip(*frames))
    return world, timestamps, wheels, ranges, truth, open_count, sample_count


def metrics(poses, truth):
    distance = np.linalg.norm(poses[:, :2] - truth[:, :2], axis=1)
    angle = wrap(poses[:, 2] - truth[:, 2])
    return dict(xy_rmse_m=float(np.sqrt(np.mean(distance**2))), final_xy_error_m=float(distance[-1]),
                yaw_rmse_deg=float(np.rad2deg(np.sqrt(np.mean(angle**2)))))


def map_metrics(grid, origin, res, start, world):
    """Reference surfaces are used only after reconstruction, in the evaluator."""
    dense = []
    for left, bottom, right, top in [world.bounds, *world.obstacles]:
        corners = np.array([[left, bottom], [left, top], [right, top], [right, bottom]])
        for a, b in zip(corners, np.roll(corners, -1, axis=0)):
            dense.extend(np.linspace(a, b, max(2, int(np.ceil(np.linalg.norm(b - a) / .02))), endpoint=False))
    surface = (np.asarray(dense) - start[:2]) @ rotation(start[2])
    rows, cols = np.nonzero(grid == 100)
    occupied = origin + res * (np.column_stack((cols, rows)) + .5)
    distance, _ = cKDTree(surface).query(occupied)
    coverage, _ = cKDTree(occupied).query(surface)
    return dict(grid_resolution_m=res, occupied_cells=len(rows), free_cells=int((grid == 0).sum()),
                unknown_cells=int((grid == -1).sum()), wall_tolerance_m=.14,
                occupied_near_wall_fraction=float(np.mean(distance <= .14)),
                wall_covered_fraction=float(np.mean(coverage <= .14)))


def map_image(path, grid, origin, res, odometry, frontend, slam, truth):
    """Draw the reconstructed occupancy and the scored trajectories in the same frame."""
    scale = 5
    pixels = np.flipud(np.where(grid == 100, 40, np.where(grid == 0, 251, 179))).astype('uint8')
    tile = Image.fromarray(pixels).convert('RGB').resize((grid.shape[1] * scale, grid.shape[0] * scale),
                                                         Image.Resampling.NEAREST)
    w, h = tile.size
    image = Image.new('RGB', (2 * w + 36, h + 102), 'white')
    image.paste(tile, (12, 36))
    image.paste(tile, (w + 24, 36))
    draw = ImageDraw.Draw(image)
    draw.text((12, 12), 'LiDAR occupancy  |  first scan frame', fill='#181818')
    draw.text((w + 24, 12), 'Trajectories  |  same frame, no fitted alignment', fill='#181818')
    for poses, color, width in [(odometry, '#c84b31', 3), (frontend, '#9a66cf', 3),
                                (truth, '#256da8', 5), (slam, '#208643', 2)]:
        points = (poses[:, :2] - origin) * scale / res
        path_pixels = [(float(w + 24 + x), float(36 + h - y)) for x, y in points]
        draw.line(path_pixels, fill=color, width=width)
    y = h + 47
    for offset, label, color in [(0, 'Occupied', '#282828'), (98, 'Unknown', '#b3b3b3'),
                                 (193, 'Free', '#fbfbfb')]:
        draw.rectangle((12 + offset, y, 24 + offset, y + 12), fill=color, outline='#8a8a8a')
        draw.text((29 + offset, y - 1), label, fill='#222222')
    y += 24
    draw.line((12, y, 12 + scale / res, y), fill='#333333', width=2)
    draw.text((18 + scale / res, y - 6), '1 m', fill='#222222')
    y = h + 47
    for offset, label, color in [(0, 'Wheel', '#c84b31'), (88, 'Local', '#9a66cf'),
                                 (169, 'Truth', '#256da8'), (259, 'SLAM', '#208643')]:
        x = w + 24 + offset
        draw.line((x, y + 5, x + 17, y + 5), fill=color, width=3)
        draw.text((x + 24, y - 1), label, fill='#222222')
    image.save(path)


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def run(seed, output=None):
    world, times, odo, scans, truth_world, open_count, samples = collect(seed)
    solution = estimate(odo, scans)
    truth = np.array([relative(truth_world[0], p) for p in truth_world])
    resolution = .07
    grid, origin = occupancy_grid(solution.poses, scans, resolution)
    edges = []
    for edge in solution.loops:
        expected = relative(truth[edge.start], truth[edge.end])
        diff = relative(expected, edge.match.delta)
        xy_error, yaw_error = float(np.linalg.norm(diff[:2])), float(abs(diff[2]))
        edges.append(dict(start=edge.start, end=edge.end, relative_pose=edge.match.delta.tolist(),
                          overlap=edge.match.overlap, rms_m=edge.match.rms_m, truth_error_m=xy_error,
                          truth_yaw_error_rad=yaw_error, within_evaluator_tolerance=xy_error <= .10 and yaw_error <= .06))
    # Run the same detector on an open prefix, and force an unrelated scan
    # to have a zero odometry displacement to exercise the geometric rejection.
    open_run = estimate(odo[:open_count], scans[:open_count])
    other = open_count - 1
    false_match = match_scans(scans[0], scans[other], np.zeros(3), loop=True)
    report = dict(seed=seed, simulated_samples=samples, keyframes=len(times),
                  duration_s=float(times[-1]), keyframe_path_length_m=float(np.linalg.norm(np.diff(truth[:, :2], axis=0), axis=1).sum()),
                  wheel_only=metrics(odo, truth), local_scan_matching=metrics(solution.frontend, truth),
                  pose_graph=metrics(solution.poses, truth), local_matches=solution.local_matches,
                  loop_candidates_checked=solution.loop_candidates, accepted_loops=edges,
                  map=map_metrics(grid, origin, resolution, truth_world[0], world),
                  open_prefix=dict(keyframes=open_count, accepted_loops=len(open_run.loops), candidates=open_run.loop_candidates),
                  wrong_place_control=dict(keyframes=[0, other], proposed_displacement_m=0.,
                                           true_distance_m=float(np.linalg.norm(truth[0,:2] - truth[other,:2])),
                                           accepted=false_match.accepted, overlap=false_match.overlap, rms_m=false_match.rms_m))
    if output is not None:
        map_image(output / 'map.png', grid, origin, resolution, odo, solution.frontend, solution.poses, truth)
        records = [dict(time_s=round(float(t), 6), odometry=wheel.tolist(), ranges_m=scan.tolist(),
                        local_pose=local.tolist(), slam_pose=post.tolist(), evaluation_truth=gt.tolist())
                   for t, wheel, scan, local, post, gt in zip(times, odo, scans, solution.frontend, solution.poses, truth)]
        write_json(output / 'keyframes.json', dict(schema=1, seed=seed, frame='first_scan_xy_m_yaw_rad', keyframes=records))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', nargs='+', type=int, default=[7, 19, 41])
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'runs/lidar-slam')
    args = parser.parse_args()
    args.out_dir.mkdir(exist_ok=True, parents=True)
    reports = [run(seed, args.out_dir if i == 0 else None) for i, seed in enumerate(args.seeds)]
    files = ('configs/mobile-map.json', 'src/pickloop/mobile.py', 'src/pickloop/lidar_slam.py',
             'scripts/run_lidar_slam.py')
    summary = dict(schema=1, source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
                   domain='offline 2D kinematic simulation', example_seed=args.seeds[0], trials=reports)
    write_json(args.out_dir / 'summary.json', summary)
    for r in reports:
        print(f"seed {r['seed']}: {r['keyframes']} keyframes, {len(r['accepted_loops'])} loop(s), "
              f"wheel/local/graph XY RMSE [m] " + ' / '.join(f"{r[k]['xy_rmse_m']:.4f}" for k in ('wheel_only','local_scan_matching','pose_graph')))


if __name__ == '__main__':
    main()
