#!/usr/bin/env python3
"""Replay the LiDAR sensor log and verify an A* route on its reconstructed map."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from pickloop.lidar_slam import estimate, occupancy_grid, rotation
from pickloop.mobile import MobileHold, MobileMap, ROOT
from pickloop.slam_navigation import SlamNavigationMap


RESOLUTION_M = .07
RADIUS_M, MARGIN_M = .24, .13
START, GOAL = [0., 0.], [5.2, 2.8]
DEFAULT_LOG = ROOT / 'runs/lidar-slam/keyframes.json'


def _rectangle_clearance(start, end, rectangle):
    """Exact segment-to-rectangle distance, including intersections."""
    lower, upper = np.split(np.asarray(rectangle), 2)
    vector = end - start
    enter, leave = 0., 1.
    for position, delta, lo, hi in zip(start, vector, lower, upper):
        if delta:
            a, b = sorted(((lo - position) / delta, (hi - position) / delta))
            enter, leave = max(enter, a), min(leave, b)
        elif not lo <= position <= hi:
            enter = math.inf
    if enter <= leave:
        return 0.

    endpoints = np.vstack((start, end))
    offsets = endpoints - np.clip(endpoints, lower, upper)
    endpoint_distance = np.min(np.linalg.norm(offsets, axis=1))
    corners = np.array([[x, y] for x in (lower[0], upper[0]) for y in (lower[1], upper[1])])
    # Apart from intersections, a closest pair includes an endpoint or a corner.
    if not np.any(vector):
        return float(endpoint_distance)
    projection = np.clip((corners - start) @ vector / (vector @ vector), 0., 1.)
    corner_distance = np.min(np.linalg.norm(corners - (start + projection[:, None] * vector), axis=1))
    return float(min(endpoint_distance, corner_distance))


def _score_route(route, world):
    """Reference geometry is loaded solely for this post-hoc collision check."""
    initial = np.asarray(world.config['robot_starts_m_rad']['amr-1'])
    points = np.asarray(route) @ rotation(initial[2]).T + initial[:2]
    lo, hi = np.split(np.asarray(world.bounds), 2)
    boundary_clearance = np.min(np.minimum(points - lo, hi - points))
    obstacle_clearance = min((_rectangle_clearance(a, b, rectangle)
                              for a, b in zip(points, points[1:]) for rectangle in world.obstacles),
                             default=math.inf)
    clearance = float(min(boundary_clearance, obstacle_clearance))
    return dict(min_centerline_clearance_m=clearance,
                min_body_clearance_m=clearance - RADIUS_M,
                clears_footprint_and_margin=clearance > RADIUS_M + MARGIN_M)


def _control(navigation, grid, goal):
    col, row = np.floor((np.asarray(goal) - navigation.origin) / RESOLUTION_M).astype(int)
    occupancy = int(grid[row, col]) if 0 <= row < grid.shape[0] and 0 <= col < grid.shape[1] else None
    try:
        navigation.plan(START, goal)
    except MobileHold as error:
        return dict(goal_xy_m=goal, goal_cell=occupancy, status=str(error))
    return dict(goal_xy_m=goal, goal_cell=occupancy, status='PATH_FOUND')


def _plot(path, grid, origin, route):
    scale, padding = 5, 14
    pixels = np.flipud(np.where(grid == -1, 180, np.where(grid == 100, 32, 250))).astype('uint8')
    tile = Image.fromarray(pixels).convert('RGB').resize((grid.shape[1] * scale, grid.shape[0] * scale),
                                                         Image.Resampling.NEAREST)
    width, height = tile.size
    image = Image.new('RGB', (width + 2 * padding, height + 70), 'white')
    image.paste(tile, (padding, 36))
    draw = ImageDraw.Draw(image)
    draw.text((padding, 11), 'A* on reconstructed lidar occupancy | first-scan frame', fill='#202020')
    route_px = (np.asarray(route) - origin) * scale / RESOLUTION_M
    points = [(x + padding, 36 + height - y) for x, y in route_px]
    draw.line([points[0], points[-1]], fill='#a6332e', width=3)
    draw.line(points, fill='#1463a4', width=4)
    for x, y in points:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill='#1463a4', outline='white')
    draw.text((points[0][0] - 8, points[0][1] + 8), 'Start', fill='#1463a4')
    draw.text((points[-1][0] + 7, points[-1][1] - 15), 'Goal', fill='#1463a4')
    for offset, label, color in [(0, 'A* route', '#1463a4'), (102, 'Rejected direct line', '#a6332e'),
                                 (246, 'Occupied', '#202020'), (345, 'Unknown', '#b4b4b4'),
                                 (444, 'Free', '#fafafa')]:
        x, y = padding + offset, height + 48
        draw.rectangle((x, y, x + 16, y + 10), fill=color, outline='#828282')
        draw.text((x + 22, y - 1), label, fill='#202020')
    image.save(path)


def run(log, output):
    log_data = log.read_bytes()
    record = json.loads(log_data)
    frames = record['keyframes']
    odometry = [frame['odometry'] for frame in frames]
    scans = [frame['ranges_m'] for frame in frames]
    slam = estimate(odometry, scans)
    grid, origin = occupancy_grid(slam.poses, scans, RESOLUTION_M)
    navigation = SlamNavigationMap(grid, origin, RESOLUTION_M, radius=RADIUS_M, margin=MARGIN_M)

    route = navigation.plan(START, GOAL)
    direct_clear = navigation.segment_clear(START, GOAL)
    clearance = min(navigation.segment_clearance(a, b) for a, b in zip(route, route[1:]))
    controls = dict(occupied_goal=_control(navigation, grid, [2.3, .72]),
                    unknown_goal=_control(navigation, grid, [2.3, 1.4]))
    world = MobileMap.load()
    held_out = _score_route(route, world)
    held_out_direct = _score_route([START, GOAL], world)
    files = ('configs/mobile-map.json', 'scripts/run_slam_navigation.py', 'src/pickloop/lidar_slam.py',
             'src/pickloop/mobile.py', 'src/pickloop/slam_navigation.py')
    source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}
    report = dict(schema=1, domain='offline planning on simulated 2D LiDAR data', seed=record['seed'],
                  log_sha256=hashlib.sha256(log_data).hexdigest(), source_sha256=source_hashes,
                  sensor_keyframes=len(frames),
                  frame='first_scan_xy_m', grid_resolution_m=RESOLUTION_M, grid_origin_xy_m=origin.tolist(),
                  grid_shape_rows_cols=list(grid.shape), radius_m=RADIUS_M, margin_m=MARGIN_M,
                  route_xy_m=route, route_length_m=sum(math.dist(a, b) for a, b in zip(route, route[1:])),
                  grid_centerline_clearance_lower_bound_m=clearance, direct_line_grid_clear=direct_clear,
                  controls=controls, held_out_route=held_out, held_out_direct_line=held_out_direct)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    _plot(output / 'route.png', grid, origin, route)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keyframes', type=Path, default=DEFAULT_LOG)
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'runs/slam-navigation')
    args = parser.parse_args()
    report = run(args.keyframes, args.out_dir)
    print(f"seed {report['seed']}: route {report['route_length_m']:.3f} m, minimum grid centreline "
          f"clearance >= {report['grid_centerline_clearance_lower_bound_m']:.3f} m, held-out body "
          f"clearance {report['held_out_route']['min_body_clearance_m']:.3f} m")
    controls = report['controls']
    print('direct line grid clear:', report['direct_line_grid_clear'])
    print('goal controls:', {name: result['status'] for name, result in controls.items()})
    if (report['direct_line_grid_clear'] or not report['held_out_route']['clears_footprint_and_margin']
            or report['held_out_direct_line']['clears_footprint_and_margin']
            or controls['occupied_goal']['goal_cell'] != 100 or controls['unknown_goal']['goal_cell'] != -1
            or any(result['status'] != 'NO_PATH' for result in controls.values())):
        raise SystemExit('SLAM navigation verification failed')


if __name__ == '__main__':
    main()
