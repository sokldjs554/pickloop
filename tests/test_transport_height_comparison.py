"""Evidence integrity tests; no physics jobs or network calls are started here."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'compare_transport_height.py'


@pytest.fixture
def comparison():
    spec = importlib.util.spec_from_file_location('height_comparison', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_height_override_changes_only_before_and_restores_even_on_error(comparison):
    class Controller:
        @property
        def transport_height(self):
            return .4 if self.attempt > 1 and self.last_error.code == 'PATH_BLOCKED' else .3
    original = Controller.transport_height
    controller = Controller()
    controller.policy = 'recovery'
    controller.attempt = 2
    controller.last_error = SimpleNamespace(code='SEAL_NOT_CONFIRMED')
    controller.state = 'TRANSPORT'
    controller.cell = SimpleNamespace(sim_time=8.)
    trace = []
    with pytest.raises(RuntimeError):
        with comparison.height_override(Controller, 'before', trace):
            assert controller.transport_height == .4
            raise RuntimeError('interrupted trial')
    assert Controller.transport_height is original
    with comparison.height_override(Controller, 'after', trace):
        assert controller.transport_height == .3
        controller.last_error.code = 'PATH_BLOCKED'
        assert controller.transport_height == .4
    assert [x['height_m'] for x in trace] == [.4, .3, .4]
    assert Controller.transport_height is original


def records():
    metrics = dict(sim_duration_s=10., wall_duration_s=2., retries=1,
                   drops=0, collisions=0, wrong_placements=0, timeout=False,
                   verified_by_vision=True, verified_by_truth=True)
    native = dict(condition={'condition_id': 'condition-1'}, initial_truth={'objects': [1]},
                  provenance={'source_sha256': 'source', 'model_sha256': 'model'},
                  success=True, status='COMPLETED', reason=None, policy='recovery',
                  seed=64000, fault='normal', run_id='run', job_id='job', metrics=metrics)
    return [{'case_id': 'normal-64000', 'scenario': 'normal', 'variant': v,
             'result_path': f'raw/normal-64000/{v}/result.json', 'result': copy.deepcopy(native)}
            for v in ('before', 'after')]


@pytest.mark.parametrize('field,value', [
    ('condition', {'condition_id': 'other'}),
    ('initial_truth', {'objects': [2]}),
    ('provenance', {'source_sha256': 'changed', 'model_sha256': 'model'}),
    ('provenance', {'source_sha256': 'source', 'model_sha256': 'changed'}),
])
def test_summary_rejects_hidden_pair_confounds(comparison, field, value):
    rows = records()
    rows[1]['result'][field] = value
    with pytest.raises(ValueError, match='MISMATCH'):
        comparison.summarize_records(rows)


def test_summary_rejects_partial_and_duplicate_pairs(comparison):
    rows = records()
    with pytest.raises(ValueError, match='INCOMPLETE'):
        comparison.summarize_records(rows[:1])
    with pytest.raises(ValueError, match='DUPLICATE'):
        comparison.summarize_records(rows + [rows[0]])


def test_failed_runs_remain_in_time_and_safety_totals(comparison):
    rows = records()
    failed = rows[1]['result']
    failed.update(success=False, status='HELD', reason='SEAL_NOT_CONFIRMED')
    failed['metrics'].update(sim_duration_s=25., wall_duration_s=4., drops=1)
    result = comparison.summarize_records(rows)
    assert result['aggregate']['after']['completed'] == 0
    assert result['aggregate']['after']['total_sim_s'] == 25.
    assert result['aggregate']['after']['drops'] == 1
    assert result['pairs'][0]['delta_sim_s'] == 15.
    assert result['paired_outcomes'] == {'both_completed': 0, 'before_only': 1,
                                        'after_only': 0, 'neither_completed': 0}


def test_mixed_condition_has_same_frozen_suction_outage_and_distinct_identity(comparison):
    from pickloop.conditions import make_condition, condition_id
    cases = comparison.make_cases([64000], make_condition, condition_id)
    by_name = {case['scenario']: case for case in cases}
    mixed = by_name['mixed']['condition']
    assert mixed['fault'] == 'path_blocked'
    assert mixed['suction']['outage_windows_s'] == by_name['suction_once']['condition']['suction']['outage_windows_s']
    assert mixed['objects'] == by_name['path_blocked']['condition']['objects']
    assert mixed['condition_id'] == condition_id(mixed)
    assert mixed['condition_id'] != by_name['path_blocked']['condition']['condition_id']


def test_refuses_existing_output_and_duplicate_seeds(comparison, tmp_path):
    path = tmp_path / 'run'
    path.mkdir()
    with pytest.raises(FileExistsError):
        comparison.new_output(path)
    with pytest.raises(ValueError):
        comparison.validate_seeds([64000, 64000])
