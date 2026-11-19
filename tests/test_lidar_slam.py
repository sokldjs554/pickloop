import json
from pathlib import Path

import numpy as np

from pickloop.lidar_slam import compose, estimate, relative, integrate_encoders, match_scans, occupancy_grid
from pickloop.mobile import MobileMap


def test_scan_verification_corrects_a_bad_wheel_prior_and_rejects_an_impostor():
    world = MobileMap.load()
    rng = np.random.default_rng(173)
    reference = np.array([1., 1., .3])
    revisit = np.array([1.16, 1.08, .35])
    prior = relative(reference, revisit) + [.15, -.14, .08]
    ranges = world.lidar(reference, rng)
    result = match_scans(ranges, world.lidar(revisit, rng), prior, loop=True)
    assert result.accepted
    assert np.linalg.norm(result.delta - relative(reference, revisit)) < .035
    # The candidate search has been fooled into proposing exactly the same place.
    impostor = match_scans(ranges, world.lidar([6.3, 3.8, 1.6], rng), np.zeros(3), loop=True)
    assert not impostor.accepted


def test_grid_max_range_is_free_and_unobserved_cells_remain_unknown():
    scan = np.full(36, 8.)
    scan[18] = 2.
    grid, origin = occupancy_grid(np.zeros((1, 3)), [scan], .1)
    def at(x, y):
        col, row = np.floor((np.array([x, y]) - origin) / .1 + 1.e-9).astype(int)
        return grid[row, col]
    assert at(1., 0.) == 0
    assert at(2., 0.) == 100
    assert at(-8., 0.) == 0
    assert at(3., 0.) == -1


def test_pose_and_encoder_transforms_use_the_vehicle_frame():
    pose = np.array([2., 3., np.pi / 2])
    moved = integrate_encoders(pose, [1., 1.], 1.)
    np.testing.assert_allclose(moved, [2., 4., np.pi / 2], atol=1.e-12)
    np.testing.assert_allclose(compose(pose, relative(pose, moved)), moved, atol=1.e-12)


def test_loop_graph_corrects_the_replayed_trajectory_using_sensor_inputs_only():
    path = Path(__file__).resolve().parents[1] / 'runs/lidar-slam/keyframes.json'
    frames = json.loads(path.read_text())['keyframes']
    odometry = np.array([frame['odometry'] for frame in frames])
    scans = [frame['ranges_m'] for frame in frames]
    result = estimate(odometry, scans)
    assert result.loops
    assert not estimate(odometry[:30], scans[:30]).loops
    truth = np.array([frame['evaluation_truth'] for frame in frames])

    def rmse(poses):
        return np.sqrt(np.mean(np.sum((poses[:, :2] - truth[:, :2]) ** 2, axis=1)))

    assert rmse(result.poses) < .06
    assert rmse(result.poses) < rmse(result.frontend) < rmse(odometry)
    for edge in result.loops:
        expected = relative(truth[edge.start], truth[edge.end])
        error = relative(expected, edge.match.delta)
        assert np.linalg.norm(error[:2]) < .10
        assert abs(error[2]) < .06
