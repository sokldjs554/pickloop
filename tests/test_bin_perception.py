from dataclasses import replace

import numpy as np
import pytest

from pickloop.bin_perception import detect_bin
from pickloop.engine import run_job
from pickloop.simulation import BinFixture, Cell
from pickloop.types import OperationError


def angle_error(a, b):
    return abs((a - b + np.pi / 2) % np.pi - np.pi / 2)


@pytest.mark.integration
def test_bin_geometry_comes_from_rendered_observation():
    fixture = BinFixture((.27, .18), (.204, .117), -.58, .071)
    with Cell(seed=5, bin_layout=[fixture]) as cell:
        obs = cell.observe()
        fitted = detect_bin(obs, cell.sim_time)
        assert np.linalg.norm(np.array(fitted.center_xy_m) - fixture.center_xy_m) < .004
        assert np.max(np.abs(np.array(fitted.inner_size_m) - fixture.inner_size_m)) < .005
        assert angle_error(fitted.yaw_rad, fixture.yaw_rad) < np.deg2rad(2)
        assert abs(fitted.rim_z_m - fitted.floor_z_m - fixture.depth_m) < .003
        assert fitted.contains_payload(fitted.center_xy_m)
        assert not fitted.contains_payload((.5, .1))
        with pytest.raises(OperationError, match='BIN_NOT_FOUND'):
            detect_bin(replace(obs, depth=np.full_like(obs.depth, np.nan)), cell.sim_time)
        with pytest.raises(OperationError, match='OBSERVATION_STALE'):
            detect_bin(obs, cell.sim_time + .5)


@pytest.mark.integration
@pytest.mark.parametrize(('layout', 'outcome'), [
    ([], 'BIN_NOT_FOUND'),
    ([BinFixture((.19, .17), (.175, .108), .22, .052),
      BinFixture((.45, .18), (.202, .125), -.31, .063)], 'BIN_AMBIGUOUS'),
    ([BinFixture((.238, .16), (.16, .13), 0., .055),
      BinFixture((.414, .16), (.16, .13), 0., .055)], 'BIN_OPENING_OBSTRUCTED'),
    ([BinFixture((.35, .16), (.16, .079), .20, .055)], 'BIN_TOO_SMALL'),
])
def test_unusable_destination_holds_before_motion(layout, outcome, tmp_path):
    result = run_job(seed=5, policy='recovery', out_dir=tmp_path, record=False, bin_layout=layout)
    assert result['status'] == 'HELD' and result['reason'] == outcome
    assert result['metrics']['attempts'] == 1
    assert not result['metrics']['selection_attempted']
    assert result['final_truth']['attached'] is None
    assert result['metrics']['drops'] == 0


@pytest.mark.integration
def test_integrated_destination_is_observed_and_truth_verified(tmp_path):
    # A hard-coded nominal x of .38 falls outside this bin.
    fixture = BinFixture((.235, .167), (.181, .112), .56, .058)
    options = dict(seed=12, policy='baseline', out_dir=tmp_path, job_id='observed-goal', record=False)
    result = run_job(**options, bin_layout=[fixture])
    assert result['success'], result['reason']
    assert result['metrics']['verified_by_vision'] and result['metrics']['verified_by_truth']
    assert result['metrics']['collisions'] == result['metrics']['drops'] == 0
    assert len(result['bin_estimates']) == 3
    target = next(obj for obj in result['final_truth']['objects'] if obj['sku'] == result['sku'])
    assert np.linalg.norm(np.array(target['position'][:2]) - fixture.center_xy_m) < .01
    assert run_job(**options, bin_layout=[fixture])['run_id'] == result['run_id']
    with pytest.raises(ValueError, match='JOB_ID_CONFLICT'):
        run_job(**options, bin_layout=[])
