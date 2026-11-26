import json
import subprocess
import sys

import numpy as np
import pytest

from pickloop.mobile import MobileMap, ROOT
from pickloop.slam_drive import KinematicPlant, RouteFollower, drive_route
from pickloop.slam_navigation import SlamNavigationMap


def _open_navigation(unknown=False):
    grid = np.zeros((45, 55), dtype=np.int8)
    if unknown:
        grid[:, 29] = -1  # World-frame x in [1.9, 2.0).
    return SlamNavigationMap(grid, [-1., -2.], .10, radius=.24, margin=.13)


def _plant(*, obstruction=False):
    return KinematicPlant(MobileMap({
        'bounds_m': [-1., -2., 4.5, 2.5],
        'obstacles_m': [[2.3, -.3, 2.5, .3]] if obstruction else [],
        'grid_resolution_m': .10,
        'robot_radius_m': .24,
        'planning_margin_m': .13,
        'landmarks_m': [],
    }), [0., 0., 0.], seed=13)


def test_reconstructed_route_is_executed_and_scored_against_plant_truth(tmp_path):
    subprocess.run([sys.executable, 'scripts/run_slam_drive.py', '--out-dir', str(tmp_path)], cwd=ROOT, check=True)
    report = json.loads((tmp_path / 'summary.json').read_text())
    assert report['route_length_m'] == pytest.approx(6.3730868)
    route = report['trials']['clear_route']
    assert route['status'] == 'GOAL_REACHED'
    assert route['truth_goal_error_m'] < .08
    assert route['truth_max_path_deviation_m'] < .10
    assert 6.2 < route['truth_travel_m'] < 6.6
    assert route['truth_min_body_clearance_m'] > .13
    assert route['map_min_body_clearance_lower_bound_m'] > .06
    assert route['accepted_scan_updates'] >= 8
    assert route['stopped']


def test_crossing_unobserved_strip_rejects_route_before_motion():
    result = drive_route(RouteFollower(_open_navigation(unknown=True), [[0., 0.], [3., 0.]]), _plant())
    assert result.status == 'NO_PATH'
    assert not result.samples


def test_live_lidar_brakes_for_obstruction_absent_from_map():
    result = drive_route(RouteFollower(_open_navigation(), [[0., 0.], [3., 0.]]), _plant(obstruction=True))
    assert result.status == 'LIDAR_STOP'
    assert result.samples[-1].wheels_m_s == pytest.approx([0., 0.])
    assert 1.4 < result.samples[-1].truth_pose[0] < 2.02
    assert all(np.all(sample.requested_m_s == 0.) for sample in result.samples if sample.status == 'LIDAR_STOP')


def test_malformed_lidar_feedback_yields_zero_command():
    follower = RouteFollower(_open_navigation(), [[0., 0.], [3., 0.]])
    request = follower.command(np.full(35, 8.), np.zeros(2))
    assert follower.status == 'SENSOR_INVALID'
    assert request == pytest.approx([0., 0.])
