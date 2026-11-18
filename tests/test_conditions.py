"""Conditions cannot clear disturbances through retries or extra camera captures."""
import copy
import json
import numpy as np
import pytest


def test_condition_generation_is_deterministic_json_and_split_separated():
    from pickloop.conditions import make_condition
    for split, seeds in [('development', range(200, 210)), ('heldout', range(3000, 3012))]:
        for seed in seeds:
            value = make_condition(seed, 'normal', split)
            assert value == make_condition(seed, 'normal', split)
            assert json.loads(json.dumps(value, allow_nan=False)) == value
            assert np.all(np.array(value['suction']['seal_halfwidth_m']) + .012 <= np.array([.032, .026]) + 1e-12)
            positions = np.array([obj['xy_m'] for obj in value['objects']])
            for i in range(3):
                for j in range(i):
                    assert np.linalg.norm(positions[i] - positions[j]) > .086
    dev = make_condition(200, 'normal', 'development')
    held = make_condition(3000, 'normal', 'heldout')
    assert dev['objects'][0]['xy_m'][0] < held['objects'][0]['xy_m'][0]
    assert dev['sensor']['depth_noise_std_m'] < held['sensor']['depth_noise_std_m']
    assert abs(dev['objects'][0]['yaw_rad']) < abs(held['objects'][0]['yaw_rad'])
    with pytest.raises(ValueError, match='split'):
        make_condition(200, 'normal', 'test')


def test_scene_uses_condition_layout_and_rejects_mismatched_identity():
    from pickloop.conditions import make_condition
    from pickloop.simulation import Cell, scene_xml
    import mujoco
    condition = make_condition(201, 'normal')
    model = mujoco.MjModel.from_xml_string(scene_xml(201, condition))
    for name, obj in zip(('a', 'b', 'u'), condition['objects']):
        body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'parcel_' + name)
        np.testing.assert_allclose(model.body_pos[body, :2], obj['xy_m'])
    with pytest.raises(ValueError, match='seed'):
        Cell(seed=202, condition=condition)


def test_attempt_and_capture_counts_cannot_clear_absolute_sensor_outage():
    from pickloop.conditions import make_condition
    from pickloop.simulation import Cell
    condition = make_condition(202, 'depth_missing')
    condition['sensor']['release_s'] = .8
    from pickloop.conditions import condition_id
    condition['condition_id'] = condition_id(condition)
    original = copy.deepcopy(condition)
    with Cell(seed=202, fault='depth_missing', condition=condition) as cell:
        first = cell.observe()
        assert np.isnan(first.depth).any()
        cell.attempt = 9
        condition['sensor']['release_s'] = 0  # caller mutation cannot alter a running case
        for _ in range(3):
            repeated = cell.observe()
            np.testing.assert_array_equal(repeated.rgb, first.rgb)
            np.testing.assert_array_equal(repeated.depth, first.depth)
            np.testing.assert_array_equal(repeated.T_base_camera, first.T_base_camera)
        assert cell.condition == original
        cell.step_for(.4)
        assert np.isfinite(cell.observe().depth).all()


def test_condition_pressure_and_supply_outage_ignore_attempt_counter():
    from pickloop.conditions import make_condition
    from pickloop.simulation import Cell
    condition = make_condition(203, 'suction_once')
    condition['suction']['outage_windows_s'] = [[0., 5.]]
    from pickloop.conditions import condition_id
    condition['condition_id'] = condition_id(condition)
    with Cell(seed=203, fault='suction_once', condition=condition) as cell:
        p = cell.truth_summary()['objects'][0]['position']
        cell.move_to([p[0], p[1], p[2] + .025])
        cell.command_suction(True)
        for attempt in (1, 8):
            cell.attempt = attempt
            cell.step_for(.05)
            assert cell.attached is None and cell.pressure_kpa == -6.
        cell.step_for(max(0., 5.05-cell.sim_time))
        assert cell.attached is not None
        assert cell.pressure_kpa == pytest.approx(condition['suction']['sealed_pressure_kpa'])


def test_extra_observations_do_not_advance_noise_or_physics():
    from pickloop.conditions import make_condition
    from pickloop.simulation import Cell
    condition = make_condition(204, 'normal')
    with Cell(seed=204, condition=condition) as cell:
        before = cell.data.qpos.copy()
        a, b = cell.observe(), cell.observe()
        np.testing.assert_array_equal(a.depth, b.depth)
        np.testing.assert_array_equal(cell.data.qpos, before)
        cell.step_for(.02)
        assert not np.array_equal(cell.observe().depth, a.depth)


def test_condition_identity_covers_params_and_is_order_independent():
    from pickloop.conditions import make_condition, condition_id, in_window
    value = make_condition(205, 'drop')
    assert value['condition_id'].startswith('development-205-drop-')
    assert condition_id(dict(reversed(list(value.items())))) == value['condition_id']
    value['sensor']['release_s'] += .1
    assert condition_id(value) != value['condition_id']
    assert in_window(1., [1., 2.])
    assert not in_window(2., [1., 2.])


def test_scene_blocker_height_and_stale_condition_id_validation():
    from pickloop.conditions import make_condition
    from pickloop.simulation import scene_xml
    import mujoco
    condition = make_condition(206, 'path_blocked')
    model = mujoco.MjModel.from_xml_string(scene_xml(206, condition))
    geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'blocker')
    assert model.geom_pos[geom, 2] + model.geom_size[geom, 2] == pytest.approx(condition['blocker_top_m'])
    condition['blocker_top_m'] += .01
    with pytest.raises(ValueError, match='condition_id'):
        scene_xml(206, condition)
