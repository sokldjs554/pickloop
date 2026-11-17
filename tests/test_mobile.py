"""Behavioral safety tests for the bounded known-map mobile simulator."""
import json
import threading

import numpy as np
import pytest

from pickloop import mobile


def test_footprint_astar_rejects_blocked_corridor():
    world = mobile.MobileMap.load()
    route = world.plan([1., 1.], [6.6, 3.])
    assert len(route) > 2
    assert all(world.clear(point, world.radius + world.margin) for point in route)
    world.obstacles.append([3.2, 0., 3.7, 6.])
    with pytest.raises(mobile.MobileHold, match='NO_PATH'):
        world.plan([1., 1.], [6.6, 3.])


def test_ekf_corrects_encoder_drift_using_landmark_measurements():
    estimator = mobile.PoseEKF([1.2, .9, .12])
    truth = np.array([1., 1., 0.])
    before = np.linalg.norm(estimator.pose - truth)
    landmarks = np.array([[.5, .5], [7.5, .5], [7.5, 5.5], [.5, 5.5]])
    for _ in range(6):
        for landmark in landmarks:
            delta = landmark - truth[:2]
            estimator.observe(landmark, [np.linalg.norm(delta), np.arctan2(delta[1], delta[0])])
    assert np.linalg.norm(estimator.pose - truth) < before / 10
    assert np.linalg.eigvalsh(estimator.cov).min() > 0


def test_zone_lease_expiry_fences_owner_and_cannot_reassign_occupied_zone():
    fleet = mobile.FleetScheduler(['amr-1', 'amr-2'], lease_s=1.)
    assert fleet.acquire('amr-1', 0.)
    fleet.enter('amr-1', .1)
    assert not fleet.acquire('amr-2', .2)
    assert not fleet.valid('amr-1', 1.1)
    assert not fleet.acquire('amr-2', 1.2)
    with pytest.raises(mobile.MobileHold, match='ZONE_NOT_CLEAR'):
        fleet.release('amr-1', estimated_clear=False)
    fleet.release('amr-1', estimated_clear=True)
    assert fleet.acquire('amr-2', 1.3)


def test_fleet_allocator_never_double_assigns_robot_or_task():
    fleet = mobile.FleetScheduler(['amr-1', 'amr-2'])
    poses = {'amr-1': [1., 1.], 'amr-2': [1., 4.8]}
    assert fleet.allocate('pick-1', [6., 1.], poses) == 'amr-1'
    assert fleet.allocate('pick-2', [6., 4.8], poses) == 'amr-2'
    assert fleet.allocate('pick-1', [6., 1.], poses) == 'amr-1'
    assert fleet.allocate('pick-3', [6., 3.], poses) is None


@pytest.mark.parametrize('seed', [0, 1, 7])
def test_mission_drives_docks_picks_and_leaves_with_bounded_wheels(tmp_path, seed):
    # A small explicit test double isolates orchestration; real physics evidence is CLI output.
    calls = []
    def picker(**kwargs):
        calls.append(kwargs)
        return {'job_id': kwargs['job_id'], 'run_id': 'test-picker', 'success': True,
                'status': 'COMPLETED', 'sim_duration_s': 10., 'metrics': {}}
    result = mobile.run_mission(seed=seed, out_dir=tmp_path, pick_runner=picker)
    assert result['status'] == 'COMPLETED', result
    assert len(calls) == 1 and calls[0]['job_id'] == result['job_id']
    rows = [json.loads(line) for line in (tmp_path / result['mission_id'] / 'trajectory.jsonl').read_text().splitlines()]
    assert rows and result['metrics']['collision_count'] == 0
    assert result['metrics']['max_wheel_speed_m_s'] <= .550001
    assert result['metrics']['max_wheel_acceleration_m_s2'] <= .800001
    dock = next(row for row in rows if row['event'] == 'DOCK_ACCEPTED')
    assert dock['data']['estimate_error_m'] <= .06
    assert dock['data']['truth_error_m'] <= .06
    assert result['metrics']['distance_m'] > 6
    assert result['next_task']['status'] == 'COMPLETED'
    assert result['metrics']['localization_rmse_m'] < .08
    assert result['metrics'] == mobile.metrics_from_rows(rows)
    svg = (tmp_path / result['mission_id'] / 'trajectory.svg').read_text()
    assert 'Computed trajectory' in svg and 'polyline' in svg


@pytest.mark.parametrize('scenario,reason', [('blocked', 'NO_PATH'), ('zone_contention', 'ZONE_WAIT_TIMEOUT')])
def test_unsafe_navigation_never_invokes_picker(tmp_path, scenario, reason):
    def forbidden(**kwargs):
        pytest.fail('picker called before accepted dock')
    result = mobile.run_mission(seed=2, scenario=scenario, out_dir=tmp_path, pick_runner=forbidden)
    assert result['status'] == 'HELD' and result['reason'] == reason
    assert result['pick_result'] is None
    assert not result['physics_picker']
    assert result['metrics']['collision_count'] == 0


def test_cancel_and_deadline_prevent_picker(tmp_path):
    event = threading.Event(); event.set()
    cancelled = mobile.run_mission(out_dir=tmp_path, cancel=event)
    expired = mobile.run_mission(out_dir=tmp_path, sim_deadline_s=.1)
    assert cancelled['status'] == 'CANCELLED'
    assert expired['status'] == 'HELD' and expired['reason'] == 'SIM_DEADLINE'


def test_default_backend_is_not_reported_as_executed_when_route_blocks(tmp_path):
    result = mobile.run_mission(out_dir=tmp_path, scenario='blocked')
    assert result['pick_result'] is None
    assert result['physics_picker'] is False


def test_docking_requires_both_estimator_and_independent_evaluator():
    assert mobile.dock_check([1., 1., 0.], [1., 1., 0.], [1., 1., 0.], [0., 0.])['accepted']
    assert not mobile.dock_check([1., 1., 0.], [1.2, 1., 0.], [1., 1., 0.], [0., 0.])['accepted']
    assert not mobile.dock_check([1.2, 1., 0.], [1., 1., 0.], [1., 1., 0.], [0., 0.])['accepted']
    assert not mobile.dock_check([1., 1., 0.], [1., 1., 0.], [1., 1., 0.], [.2, .2])['accepted']


def test_cancellation_during_motion_logs_bounded_braking_to_rest(tmp_path):
    class CancelAfterMotion:
        def __init__(self):
            self.checks = 0
        def is_set(self):
            self.checks += 1
            return self.checks > 100
    result = mobile.run_mission(out_dir=tmp_path, cancel=CancelAfterMotion())
    assert result['status'] == 'CANCELLED'
    samples = [json.loads(line) for line in (tmp_path / result['mission_id'] / 'trajectory.jsonl').read_text().splitlines()
               if json.loads(line)['event'] == 'SAMPLE']
    assert np.max(np.abs(samples[-1]['data']['wheel_m_s'])) == 0.
    assert any(row['state'] == 'BRAKING' for row in samples)
    assert result['metrics']['max_wheel_acceleration_m_s2'] <= .800001
    assert result['pick_result'] is None
