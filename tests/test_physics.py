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
