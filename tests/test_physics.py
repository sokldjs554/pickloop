import numpy as np
from pickloop.simulation import Cell


def test_dynamic_lift_and_release():
    # Explicit oracle component test: no perception claim for these known coordinates.
    with Cell(seed=2, fault='normal') as cell:
        assert cell.calibration_rms_px < 1.5
        p=cell.truth_summary()['objects'][0]['position']
        cell.move_to([p[0],p[1],.25])
        cell.move_to([p[0],p[1],p[2]+.025])
        cell.command_suction(True)
        cell.step_for(.25)
        assert cell.attached is not None
        cell.move_to([p[0],p[1],.30])
        assert cell.truth_summary()['objects'][0]['position'][2] > .23
        assert cell.pressure_kpa < -35
        cell.command_suction(False)
        cell.step_for(.8)
        assert cell.attached is None
        assert cell.truth_summary()['objects'][0]['position'][2] < .12
        assert cell.drop_count==1  # unsupported release, distinct from near-support placement


def test_seal_failure_does_not_attach():
    with Cell(seed=2, fault='suction_permanent') as cell:
        p=cell.truth_summary()['objects'][0]['position']
        cell.move_to([p[0],p[1],p[2]+.025])
        cell.command_suction(True); cell.step_for(.3)
        assert cell.attached is None and cell.pressure_kpa > -35


def test_observation_exposes_pixels_not_truth():
    with Cell(seed=1) as cell:
        obs=cell.observe()
        assert obs.rgb.shape == (480,480,3)
        assert obs.depth.shape == (480,480)
        assert not hasattr(obs,'object_ids')
        assert not hasattr(obs,'object_positions')


def test_vertical_stages_stay_engaged_across_the_full_stroke():
    import mujoco
    from pickloop.geometry import JOINT_LOWER, JOINT_UPPER

    with Cell(seed=2) as cell:
        def extent(name):
            geom = cell.model.geom(name)
            center = cell.data.geom_xpos[geom.id]
            return center[:2], center[2] - geom.size[1], center[2] + geom.size[1]

        for q in np.linspace(JOINT_LOWER[2], JOINT_UPPER[2], 39):
            cell.data.qpos[2] = q
            cell.data.joint('stage_travel').qpos[0] = q / 2
            mujoco.mj_forward(cell.model, cell.data)
            guide, sleeve, rod = (extent(name) for name in ('lift_guide', 'lift_sleeve', 'shaft'))
            for outer, inner in ((guide, sleeve), (sleeve, rod)):
                np.testing.assert_allclose(outer[0], inner[0], atol=1e-10)
                assert min(outer[2], inner[2]) - max(outer[1], inner[1]) >= .009
            assert max(sleeve[2], rod[2]) < guide[2]
            assert extent('cup')[2] < guide[1]


def test_passive_sleeve_follows_during_descent_and_retraction():
    with Cell(seed=2) as cell:
        samples = []
        def sample(c):
            z = c.joints[2]
            mid = c.data.qpos[c.stage_qpos]
            samples.append((z, mid))
        cell.on_step = sample
        cell.move_to([.38, -.16, .11])
        cell.move_to([.38, -.16, .34])
        q, sleeve = np.asarray(samples).T
        assert q.max() - q.min() > .20
        np.testing.assert_allclose(sleeve, q / 2, atol=5e-4)
