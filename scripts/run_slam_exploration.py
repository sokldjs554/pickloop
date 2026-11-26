#!/usr/bin/env python3
"""Drive two sensor-selected frontiers in a new, initially empty online map."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from pickloop.lidar_slam import relative
from pickloop.mobile import DT, ROOT, MobileMap
from pickloop.slam_drive import KinematicPlant
from pickloop.slam_exploration import RESOLUTION_M, explore

if __package__:
    from .run_slam_drive import _trajectory_clearance, _write_trace
else:
    from run_slam_drive import _trajectory_clearance, _write_trace


SEED = 31


def _free_cells(grid, origin):
    rows, cols = np.where(grid == 0)
    offset = np.rint(origin / RESOLUTION_M).astype(int)
    return set(map(tuple, np.column_stack((cols, rows)) + offset))


def run(output):
    world = MobileMap.load()
    start = np.array(world.config['robot_starts_m_rad']['amr-1'])
    plant = KinematicPlant(world, start, seed=SEED)
    result = explore(plant)
    samples = [sample for motion in result.motions.values() for sample in motion.samples]
    truth = np.array([start, *(sample.truth_pose for sample in samples)])
    estimated = np.array([np.zeros(3), *(sample.estimate_pose for sample in samples)])
    truth_local = np.array([relative(start, pose) for pose in truth])
    clearance = _trajectory_clearance(truth[:, :2], world)
    baseline = _free_cells(*result.maps[0]) if result.maps else set()
    final = _free_cells(*result.maps[-1]) if result.maps else set()
    output.mkdir(exist_ok=True, parents=True)
    trace = output / 'samples.jsonl.gz'
    _write_trace(trace, result.motions, start)
    maps = output / 'grids.npz'
    np.savez_compressed(maps, **{f'grid_{i}': grid for i, (grid, _) in enumerate(result.maps)},
                        origins_xy_m=np.array([origin for _, origin in result.maps]), resolution_m=RESOLUTION_M)
    files = ('configs/mobile-map.json', 'scripts/run_slam_drive.py', 'scripts/run_slam_exploration.py',
             'scripts/run_slam_navigation.py', 'src/pickloop/lidar_slam.py', 'src/pickloop/mobile.py',
             'src/pickloop/slam_drive.py', 'src/pickloop/slam_exploration.py', 'src/pickloop/slam_navigation.py')
    report = dict(schema=1, seed=SEED, domain='bounded sensor-driven frontier exploration in a 2D kinematic simulator',
                  frame='first_scan_xy_m_yaw_rad', preloaded_map=False, status=result.status,
                  grid_resolution_m=RESOLUTION_M, sensor_keyframes=result.keyframes,
                  initial_free_cells=len(baseline), final_free_cells=len(final),
                  newly_free_cells=len(final - baseline), no_longer_free_cells=len(baseline - final),
                  free_cells_by_sweep=[int((grid == 0).sum()) for grid, _ in result.maps],
                  truth_travel_m=float(np.linalg.norm(np.diff(truth[:, :2], axis=0), axis=1).sum()),
                  truth_min_body_clearance_m=clearance, truth_collision=clearance <= 0.,
                  estimate_xy_rmse_m=float(np.sqrt(np.mean(np.sum((estimated[:, :2] - truth_local[:, :2]) ** 2, axis=1)))),
                  stopped=bool((plant.wheels_m_s == 0.).all()), simulated_duration_s=len(samples) * DT,
                  legs=result.legs, trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest(),
                  grids_sha256=hashlib.sha256(maps.read_bytes()).hexdigest(),
                  source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files})
    (output / 'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'runs/slam-exploration')
    args = parser.parse_args()
    report = run(args.out_dir)
    print(f"{report['status']}, {len(report['legs'])} frontier legs, {report['truth_travel_m']:.3f} m travel, "
          f"{report['initial_free_cells']} -> {report['final_free_cells']} free cells, "
          f"{report['truth_min_body_clearance_m']:.3f} m minimum body clearance")
    if (report['status'] != 'FRONTIER_BUDGET_REACHED' or report['truth_collision'] or not report['stopped']
            or report['initial_free_cells'] >= report['final_free_cells']):
        raise SystemExit('frontier exploration verification failed')


if __name__ == '__main__':
    main()
