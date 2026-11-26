#!/usr/bin/env python3
"""Execute the recorded SLAM route in a separate LiDAR and wheel kinematics run."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from pickloop.lidar_slam import estimate, occupancy_grid, relative
from pickloop.mobile import DT, ROOT, MobileMap
from pickloop.slam_drive import KinematicPlant, RouteFollower, ScanReference, drive_route
from pickloop.slam_navigation import SlamNavigationMap

if __package__:
    from .run_slam_navigation import _rectangle_clearance
else:
    from run_slam_navigation import _rectangle_clearance


DEFAULT_KEYFRAMES = ROOT / 'runs/lidar-slam/keyframes.json'
DEFAULT_ROUTE = ROOT / 'runs/slam-navigation/summary.json'
EXECUTION_SEED = 23


def _trajectory_clearance(points, world):
    """Evaluate every midpoint-integrator motion segment against hidden geometry."""
    lower, upper = np.split(np.asarray(world.bounds), 2)
    boundary = np.minimum(points - lower, upper - points).min()
    segments = zip(points, points[1:]) if len(points) > 1 else [(points[0], points[0])]
    obstacle = min((_rectangle_clearance(start, end, box)
                    for start, end in segments for box in world.obstacles), default=math.inf)
    return float(min(boundary, obstacle) - world.radius)


def _path_deviation(points, route):
    distance = np.full(len(points), np.inf)
    for start, end in zip(route, route[1:]):
        vector = end - start
        offset = points - start
        if np.any(vector):
            offset = offset - np.clip(offset @ vector / (vector @ vector), 0., 1.)[:, None] * vector
        distance = np.minimum(distance, np.linalg.norm(offset, axis=1))
    return float(distance.max())


def _score(result, follower, world, initial, route):
    samples = result.samples
    raw_truth = np.array([initial, *(sample.truth_pose for sample in samples)])
    truth = np.array([relative(initial, pose) for pose in raw_truth])
    estimates = np.array([np.zeros(3), *(sample.estimate_pose for sample in samples)])
    body_clearance = _trajectory_clearance(raw_truth[:, :2], world)
    requested = np.array([[0., 0.], *(sample.requested_m_s for sample in samples)])
    wheels = np.array([[0., 0.], *(sample.wheels_m_s for sample in samples)])
    encoder_only = np.array([np.zeros(3), *(sample.wheel_pose for sample in samples)])
    stop = next((sample for sample in samples if sample.status != 'RUNNING'), None)
    map_clearance = min((follower.navigation.segment_clearance(a, b) for a, b in
                         zip(estimates[:, :2], estimates[1:, :2])), default=None)
    rmse = lambda pose: float(np.sqrt(np.mean(np.sum((pose[:, :2] - truth[:, :2]) ** 2, axis=1))))
    return dict(status=result.status, samples=len(samples), duration_s=len(samples) * DT,
                stopped=bool((wheels[-1] == 0.).all()),
                commanded_motion_ticks=int(np.count_nonzero(np.any(requested != 0., axis=1))),
                peak_wheel_speed_m_s=float(np.max(np.abs(wheels))),
                peak_wheel_acceleration_m_s2=float(np.max(np.abs(np.diff(wheels, axis=0)), initial=0.) / DT),
                truth_goal_error_m=math.dist(truth[-1, :2], route[-1]),
                estimated_goal_error_m=math.dist(estimates[-1, :2], route[-1]),
                truth_max_path_deviation_m=_path_deviation(truth[:, :2], route),
                truth_travel_m=float(np.linalg.norm(np.diff(truth[:, :2], axis=0), axis=1).sum()),
                truth_min_body_clearance_m=body_clearance, truth_collision=body_clearance <= 0.,
                map_min_body_clearance_lower_bound_m=None if map_clearance is None else map_clearance - world.radius,
                estimated_xy_rmse_m=rmse(estimates), concurrent_encoder_only_xy_rmse_m=rmse(encoder_only),
                scan_update_attempts=follower.fix_attempts, accepted_scan_updates=follower.accepted_fixes,
                matched_reference_keyframes=sorted({s.matched_keyframe for s in samples if s.matched_keyframe is not None}),
                first_zero_on_terminal_s=None if stop is None else stop.time_s - DT,
                terminal_min_lidar_range_m=None if stop is None else stop.minimum_lidar_range_m,
                truth_final_pose_m_rad=truth[-1].tolist(), estimated_final_pose_m_rad=estimates[-1].tolist())


def _write_trace(path, results, initial):
    def row(name, sample):
        rounded = lambda values: np.round(values, 7).tolist()
        return [name, round(sample.time_s, 4), sample.status, rounded(sample.requested_m_s),
                rounded(sample.encoder_m_s), round(sample.minimum_lidar_range_m, 6), sample.matched_keyframe,
                rounded(sample.estimate_pose), rounded(sample.wheel_pose), rounded(relative(initial, sample.truth_pose)),
                rounded(sample.wheels_m_s)]

    columns = ['trial', 'time_s', 'status', 'command_m_s', 'encoder_m_s', 'min_lidar_m', 'matched_keyframe',
               'estimate_m_rad', 'encoder_only_m_rad', 'truth_m_rad', 'wheels_m_s']
    lines = (json.dumps(row(name, sample), separators=(',', ':'))
             for name, result in results.items() for sample in result.samples)
    content = '\n'.join([json.dumps(columns, separators=(',', ':')), *lines]) + '\n'
    path.write_bytes(gzip.compress(content.encode(), mtime=0))


def run(output, keyframes=DEFAULT_KEYFRAMES, route_report=DEFAULT_ROUTE):
    keyframe_bytes, route_bytes = keyframes.read_bytes(), route_report.read_bytes()
    recording, planned = json.loads(keyframe_bytes), json.loads(route_bytes)
    hash_bytes = lambda data: hashlib.sha256(data).hexdigest()
    if planned['log_sha256'] != hash_bytes(keyframe_bytes) or planned['seed'] != recording['seed']:
        raise ValueError('route and keyframes must come from the same SLAM replay')
    frames = recording['keyframes']
    odometry, scans = [f['odometry'] for f in frames], [f['ranges_m'] for f in frames]
    poses = estimate(odometry, scans).poses
    grid, origin = occupancy_grid(poses, scans, planned['grid_resolution_m'])
    navigation = SlamNavigationMap(grid, origin, planned['grid_resolution_m'],
                                   radius=planned['radius_m'], margin=planned['margin_m'])
    reference = ScanReference(poses, scans)
    route = np.array(planned['route_xy_m'])
    world = MobileMap.load()
    initial = np.asarray(world.config['robot_starts_m_rad']['amr-1'])
    # The injected obstacle is present in the live plant's raycaster only.
    obstruction = [2.4, .80, 2.55, 1.4]
    obstructed = MobileMap({**world.config, 'obstacles_m': [*world.obstacles, obstruction]})
    trials = {'clear_route': (route, world), 'live_obstruction': (route, obstructed)}
    for name, control in planned['controls'].items():
        trials[name] = (np.array([route[0], control['goal_xy_m']]), world)
    results, scores = {}, {}
    for name, (path, plant_world) in trials.items():
        follower = RouteFollower(navigation, path, reference)
        plant = KinematicPlant(plant_world, initial, EXECUTION_SEED)
        result = drive_route(follower, plant)
        results[name] = result
        scores[name] = _score(result, follower, plant_world, initial, path)
    output.mkdir(exist_ok=True, parents=True)
    trace = output / 'samples.jsonl.gz'
    _write_trace(trace, results, initial)
    files = ('configs/mobile-map.json', 'scripts/run_slam_navigation.py', 'scripts/run_slam_drive.py',
             'src/pickloop/lidar_slam.py', 'src/pickloop/mobile.py', 'src/pickloop/slam_navigation.py',
             'src/pickloop/slam_drive.py')
    report = dict(schema=1, domain='closed-loop simulated differential drive on a fixed reconstructed 2D map',
                  frame='first_scan_xy_m_yaw_rad', mapping_seed=recording['seed'], execution_seed=EXECUTION_SEED,
                  keyframes=len(frames), keyframes_sha256=hash_bytes(keyframe_bytes), route_sha256=hash_bytes(route_bytes),
                  source_sha256={name: hash_bytes((ROOT / name).read_bytes()) for name in files},
                  tick_s=DT, route_xy_m=route.tolist(),
                  route_length_m=sum(math.dist(a, b) for a, b in zip(route, route[1:])),
                  obstruction_plant_world_rectangle_m=obstruction, trace_sha256=hash_bytes(trace.read_bytes()), trials=scores)
    (output / 'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keyframes', type=Path, default=DEFAULT_KEYFRAMES)
    parser.add_argument('--route', type=Path, default=DEFAULT_ROUTE)
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'runs/slam-drive')
    args = parser.parse_args()
    report = run(args.out_dir, args.keyframes, args.route)
    for name, row in report['trials'].items():
        print(f"{name} {row['status']}, travel {row['truth_travel_m']:.3f} m, "
              f"goal error {row['truth_goal_error_m']:.3f} m, body clearance {row['truth_min_body_clearance_m']:.3f} m")
    trials = report['trials']
    clear = trials['clear_route']
    blocked = trials['live_obstruction']
    controls = [trials['occupied_goal'], trials['unknown_goal']]
    if (clear['status'] != 'GOAL_REACHED' or clear['truth_goal_error_m'] > .08
            or clear['truth_max_path_deviation_m'] > .10 or clear['accepted_scan_updates'] == 0
            or blocked['status'] != 'LIDAR_STOP' or blocked['commanded_motion_ticks'] == 0
            or any(row['truth_collision'] or not row['stopped'] for row in trials.values())
            or any(row['status'] != 'NO_PATH' or row['commanded_motion_ticks'] for row in controls)):
        raise SystemExit('closed-loop SLAM drive verification failed')


if __name__ == '__main__':
    main()
