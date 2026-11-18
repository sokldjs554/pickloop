import copy
from types import SimpleNamespace
import numpy as np
import pytest
from pickloop.engine import Controller, POLICIES
from pickloop.experiment import paired_rows, contrast
from pickloop.types import OperationError


def row(seed, policy, success=False):
    return dict(seed=seed,fault='normal',policy=policy,success=success,initial_truth={'objects':[]},condition={'seed':seed},provenance={'source_sha256':'same','model_sha256':'same-model'})


def test_pairs_require_identical_conditions_and_physics():
    rows=[row(1,p) for p in POLICIES]
    assert len(paired_rows(rows))==1
    for key in ['condition','initial_truth','provenance']:
        altered=copy.deepcopy(rows);altered[2][key]={'source_sha256':'different','model_sha256':'same-model'}
        with pytest.raises(ValueError):paired_rows(altered)
    with pytest.raises(ValueError,match='INCOMPLETE'):paired_rows(rows[:-1])
    with pytest.raises(ValueError,match='DUPLICATE'):paired_rows(rows+[rows[0]])


def test_paired_contrast_counts_both_directions_and_clusters_seeds():
    rows=[]
    for seed in range(4):
        rows.extend(row(seed,p,success=(seed%2==0 if p=='recovery' else seed%2==1)) for p in POLICIES)
    c=contrast(paired_rows(rows),'naive','recovery')
    assert c['after_only']==2 and c['before_only']==2 and c['completion_delta']==0
    assert c['seed_clusters']==4 and c['seed_cluster_bootstrap95'][0]<0<c['seed_cluster_bootstrap95'][1]


def controller(policy):
    c=Controller.__new__(Controller);c.policy=policy;c.attempt=2;c.carrying=False
    c.target_detection=SimpleNamespace(position=np.array([.3,-.2,.11]))
    c.cell=SimpleNamespace(sim_time=5.,observe=lambda:SimpleNamespace(observation_id='fresh',validate=lambda t:None))
    c.emit=lambda *a,**kw:None
    c.sku='SKU-RED-A';c.inference_times=[];c.position_estimates=[]
    c.perception=SimpleNamespace(target=lambda *a:(_ for _ in ()).throw(RuntimeError('fresh inference invoked')))
    return c


def test_naive_reuses_target_but_still_checks_fresh_observation():
    c=controller('naive');original=c.target_detection;c.observe()
    assert c.target_detection is original and c.last_observation.observation_id=='fresh'
    c.cell.observe=lambda:SimpleNamespace(validate=lambda t:(_ for _ in ()).throw(ValueError('OBSERVATION_STALE')))
    with pytest.raises(OperationError,match='OBSERVATION_STALE'):c.observe()


def test_reobservation_and_path_ablation_are_independent():
    for p in ['reobserve','recovery']:
        c=controller(p)
        with pytest.raises(RuntimeError,match='fresh inference'):c.observe()
    assert controller('naive').transport_height==.30
    assert controller('reobserve').transport_height==.30
    assert controller('recovery').transport_height==.40
    c=controller('recovery');c.attempt=1;assert c.transport_height==.30


def test_checkpoint_change_invalidates_pair_even_if_source_is_identical():
    rows=[row(1,p) for p in POLICIES]
    rows[1]['provenance']['model_sha256']='different-model'
    with pytest.raises(ValueError,match='MODEL_MISMATCH'):paired_rows(rows)

@pytest.mark.integration
def test_unconfirmed_seal_with_attachment_never_releases_during_retry(tmp_path,monkeypatch):
    from pickloop.device import DeviceClient
    from pickloop.engine import run_job
    original=DeviceClient.status
    def contradictory_feedback(client):
        status=original(client)
        if status['attached']:status['pressure_kpa']=-6.
        return status
    monkeypatch.setattr(DeviceClient,'status',contradictory_feedback)
    r=run_job(seed=3,policy='recovery',out_dir=tmp_path,record=False)
    assert r['status']=='HELD' and r['reason']=='RECOVERY_LOAD_UNCONFIRMED'
    assert r['final_truth']['attached'] is not None and r['metrics']['drops']==0
    assert r['terminal_policy']['action']=='RETAIN'

@pytest.mark.integration
def test_empty_exhausted_seal_turns_valve_off_with_separate_evidence(tmp_path):
    import json
    from pickloop.engine import run_job
    r=run_job(seed=3,fault='suction_permanent',policy='recovery',out_dir=tmp_path,record=False)
    assert r['terminal_policy']['action']=='OFF_CONFIRMED'
    assert r['terminal_policy']['status']['valve'] is False
    events=json.loads((tmp_path/r['run_id']/'run.json').read_text())['events']
    assert any(e['event']=='RETRY_EXHAUSTED' for e in events)
    assert any(e['event']=='HOLD_POLICY' for e in events)
