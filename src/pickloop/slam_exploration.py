"""Bounded stop-and-scan exploration of a previously unseen occupancy grid."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import binary_dilation
from scipy.spatial import cKDTree

from .lidar_slam import compose, integrate_encoders, occupancy_grid, relative
from .mobile import DT, MAX_WHEEL_ACCEL_M_S2, MAX_WHEEL_M_S, TRACK_M
from .slam_drive import (TRACKING_MARGIN_M, DriveResult, DriveSample, RouteFollower, ScanReference,
                         drive_route, lidar_clear, stopping_distance, valid_scan)
from .slam_navigation import SlamNavigationMap


RESOLUTION_M = .07
RADIUS_M, MARGIN_M = .24, .13
_SWEEP_YAW_RATE_RAD_S = .73
_BRAKE_TICKS = math.ceil(MAX_WHEEL_M_S / (MAX_WHEEL_ACCEL_M_S2 * DT))


def sweep(plant, initial_pose, radius=RADIUS_M):
    """Turn through one full circle; anchor new scans to the first scan of this sweep."""
    pose = initial_pose.copy()
    wheel_pose = initial_pose.copy()
    encoders = np.zeros(2)
    first_scan = plant.scan()
    if not valid_scan(first_scan):
        return pose, [], [], DriveResult('SENSOR_INVALID', [])
    reference = ScanReference([pose], [first_scan])
    poses, scans, samples = [], [], []
    turn = _SWEEP_YAW_RATE_RAD_S * TRACK_M / 2
    turned = 0.
    last_fix = 0
    status = 'RUNNING'
    for tick in range(280):
        scan = first_scan if tick == 0 else plant.scan()
        if not valid_scan(scan):
            status = 'SENSOR_INVALID'
            break
        if not lidar_clear(scan, radius + TRACKING_MARGIN_M + stopping_distance(encoders)):
            status = 'LIDAR_STOP'
            break
        if turned >= 2 * math.pi:
            status = 'SWEEP_COMPLETE'
            break
        matched = None
        if tick % 4 == 0:
            fixed, matched = reference.locate(pose, scan)
            if fixed is not None:
                pose = compose(pose, .55 * relative(pose, fixed))
                last_fix = tick
        if tick - last_fix >= 100:
            status = 'LOCALIZATION_LOST'
            break
        poses.append(pose.copy())
        scans.append(scan)
        command = np.array([-turn, turn])
        encoders = plant.advance(command)
        turned += (encoders[1] - encoders[0]) * DT / TRACK_M
        pose = integrate_encoders(pose, encoders, DT)
        wheel_pose = integrate_encoders(wheel_pose, encoders, DT)
        samples.append(DriveSample((len(samples) + 1) * DT, status, command, encoders, float(np.min(scan)),
                                   matched, pose.copy(), wheel_pose.copy(), plant.truth_pose.copy(),
                                   plant.wheels_m_s.copy()))
    if status == 'RUNNING':
        status = 'SWEEP_TIMEOUT'
    for _ in range(_BRAKE_TICKS):
        scan = plant.scan()
        command = np.zeros(2)
        encoders = plant.advance(command)
        pose = integrate_encoders(pose, encoders, DT)
        wheel_pose = integrate_encoders(wheel_pose, encoders, DT)
        samples.append(DriveSample((len(samples) + 1) * DT, status, command, encoders, float(np.min(scan)),
                                   None, pose.copy(), wheel_pose.copy(), plant.truth_pose.copy(),
                                   plant.wheels_m_s.copy()))
    return pose, poses, scans, DriveResult(status, samples)


def _frontier_goal(navigation, grid, pose, visited):
    unknown = grid == -1
    free = grid == 0
    frontier_cells = free & binary_dilation(unknown)

    def centers(mask):
        rows, cols = np.nonzero(mask)
        return navigation.origin + RESOLUTION_M * (np.column_stack((cols, rows)) + .5)

    points = centers(free)
    distance = np.linalg.norm(points - pose[:2], axis=1)
    away_from_visited = cKDTree(visited).query(points)[0] >= .50
    candidates = points[(.65 <= distance) & (distance <= 1.40) & away_from_visited]
    if not len(candidates) or not frontier_cells.any():
        return None
    information = cKDTree(centers(frontier_cells)).query_ball_point(candidates, 1.60, return_length=True)
    travel = np.linalg.norm(candidates - pose[:2], axis=1)
    for index in np.lexsort((-travel, -information)):
        if information[index] == 0:
            break
        goal = candidates[index]
        # Drive only a direct, inflated-footprint segment of observed free cells.
        # The goal approaches a frontier; the robot never drives onto the unknown edge.
        if navigation.segment_clear(pose[:2], goal):
            return goal
    return None


@dataclass
class ExplorationResult:
    status: str
    motions: dict[str, DriveResult]
    legs: list[dict]
    maps: list[tuple[np.ndarray, np.ndarray]]
    keyframes: int


def explore(plant, *, max_legs=2):
    """Create a grid from live data, choose frontiers, drive, and rescan at each stop."""
    poses, scans, maps, legs = [], [], [], []
    motions = {}
    point = np.zeros(3)  # Define the frame from the first simulated observation.
    visited = [point[:2].copy()]
    for index in range(max_legs + 1):
        point, new_poses, new_scans, result = sweep(plant, point)
        motions[f'sweep_{index}'] = result
        if result.status != 'SWEEP_COMPLETE':
            return ExplorationResult(result.status, motions, legs, maps, len(scans))
        poses.extend(new_poses)
        scans.extend(new_scans)
        grid, origin = occupancy_grid(poses, scans, RESOLUTION_M)
        maps.append((grid, origin))
        if index == max_legs:
            break
        navigation = SlamNavigationMap(grid, origin, RESOLUTION_M, radius=RADIUS_M, margin=MARGIN_M)
        goal = _frontier_goal(navigation, grid, point, visited)
        if goal is None:
            return ExplorationResult('NO_REACHABLE_FRONTIER', motions, legs, maps, len(scans))
        reference = ScanReference(poses[::12], scans[::12])
        path = [point[:2], goal]
        follower = RouteFollower(navigation, path, reference, initial_pose=point)
        drive = drive_route(follower, plant, max_steps=625)
        motions[f'leg_{index + 1}'] = drive
        legs.append(dict(status=drive.status, route_xy_m=np.asarray(path).tolist(),
                         observed_free_cells=int((grid == 0).sum()),
                         map_centerline_clearance_lower_bound_m=navigation.segment_clearance(*path),
                         scan_update_attempts=follower.fix_attempts, accepted_scan_updates=follower.accepted_fixes))
        if drive.status != 'GOAL_REACHED':
            return ExplorationResult(drive.status, motions, legs, maps, len(scans))
        point = follower.pose.copy()
        visited.append(point[:2].copy())
    return ExplorationResult('FRONTIER_BUDGET_REACHED', motions, legs, maps, len(scans))
