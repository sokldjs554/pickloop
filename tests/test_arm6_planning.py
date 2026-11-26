import mujoco
import numpy as np
import pytest

from pickloop import arm6_planning as arm6


@pytest.mark.parametrize('seed', [3, 17, 41])
def test_rrt_connect_detours_around_a_fixture(seed):
    scene = arm6.Arm6Scene()
    start, goal = arm6.DEMO_START, arm6.DEMO_GOAL
    assert scene.configuration(start).valid
    assert scene.configuration(goal).valid
    assert scene.edge(start, goal, max_step_rad=0.01).blocking_pair is not None

    plan = arm6.plan_path(scene, start, goal, seed=seed)
    assert plan.status == 'path_found'
    assert plan.iterations > 0
    assert len(plan.waypoints_rad) > 2
    assert np.array_equal(plan.waypoints_rad[0], start)
    assert np.array_equal(plan.waypoints_rad[-1], goal)
    assert np.all(plan.waypoints_rad >= scene.lower)
    assert np.all(plan.waypoints_rad <= scene.upper)
    assert np.all(np.ptp(plan.waypoints_rad, axis=0) > 0)
    # Check independent interpolation points between every pair of waypoints.
    for left, right in zip(plan.waypoints_rad, plan.waypoints_rad[1:]):
        subdivisions = int(np.ceil(np.max(np.abs(right - left)) / 0.006))
        for q in np.linspace(left, right, subdivisions + 1):
            assert scene.configuration(q).valid


def test_invalid_endpoints_and_exhausted_budget_do_not_return_paths():
    scene = arm6.Arm6Scene()
    start, goal = arm6.DEMO_START, arm6.DEMO_GOAL
    mid = (start + goal) / 2
    assert 'fixture' in scene.configuration(mid).blocking_pair
    invalid_goal = arm6.plan_path(scene, start, mid, seed=3)
    assert invalid_goal.status == 'invalid_goal'
    assert invalid_goal.detail == 'collision'
    assert invalid_goal.waypoints_rad.size == 0

    outside = start.copy()
    outside[4] = scene.upper[4] + 0.1
    invalid_start = arm6.plan_path(scene, outside, goal, seed=3)
    assert invalid_start.status == 'invalid_start'
    assert invalid_start.detail == 'joint_limit'
    assert invalid_start.waypoints_rad.size == 0

    exhausted = arm6.plan_path(scene, start, goal, seed=3, max_iterations=0)
    assert exhausted.status == 'search_budget_exhausted'
    assert exhausted.waypoints_rad.size == 0


def test_clear_workspace_uses_the_direct_segment():
    scene = arm6.Arm6Scene(with_fixture=False)
    plan = arm6.plan_path(scene, arm6.DEMO_START, arm6.DEMO_GOAL, seed=3)
    assert plan.status == 'direct_path'
    assert plan.iterations == 0
    assert len(plan.waypoints_rad) == 2
    assert scene.model.nq == scene.model.nv == scene.model.nu == 6
    assert np.all(scene.model.jnt_type == mujoco.mjtJoint.mjJNT_HINGE)
    assert np.unique(scene.model.actuator_trnid[:, 0]).size == 6


def test_measured_actuator_torque_reports_motor_saturation():
    probe = arm6.simulated_torque_probe(arm6.Arm6Scene())
    command = np.array(probe['requested_motor_torque_nm'])
    measured = np.array(probe['joint_actuator_sensor_nm'])
    assert command.shape == measured.shape == (6,)
    assert 0 < measured[-1] < command[-1]
    assert measured[-1] == pytest.approx(8.0)
    assert np.allclose(measured, probe['simulator_qfrc_actuator_nm'])
