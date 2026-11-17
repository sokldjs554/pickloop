import json
import threading
import pytest
from pickloop.journal import JobStore
from pickloop.engine import run_job


def test_restart_fences_unfinished_jobs(tmp_path):
    path=tmp_path/'jobs.sqlite'
    s=JobStore(path); assert s.begin('job-1',{'seed':1},'run-1')['state']=='QUEUED'
    s.transition('job-1','APPROACH');s.close()
    s=JobStore(path)
    assert s.get('job-1')['state']=='HOLD_RECOVERY_REQUIRED'
    assert not s.begin('job-1',{'seed':1},'run-2')['created']
    with pytest.raises(ValueError):s.begin('job-1',{'seed':2},'run-3')
    s.close()


@pytest.mark.integration
def test_actual_perception_to_verified_placement(tmp_path):
    result=run_job(seed=3,fault='normal',policy='recovery',out_dir=tmp_path,record=False)
    assert result['status']=='COMPLETED',result
    assert result['success'] and result['metrics']['wrong_placements']==0
    assert result['metrics']['verified_by_vision']
    assert result['metrics']['verified_by_truth']
    assert result['metrics']['first_attempt_success']


@pytest.mark.integration
def test_transient_suction_recovers_but_baseline_holds(tmp_path):
    baseline=run_job(seed=3,fault='suction_once',policy='baseline',out_dir=tmp_path,record=False)
    improved=run_job(seed=3,fault='suction_once',policy='recovery',out_dir=tmp_path,record=False)
    assert baseline['status']=='HELD'
    assert improved['status']=='COMPLETED',improved
    assert improved['metrics']['retries']==1
    assert not improved['metrics']['first_attempt_success']


@pytest.mark.integration
def test_permanent_failure_is_bounded(tmp_path):
    result=run_job(seed=3,fault='suction_permanent',policy='recovery',out_dir=tmp_path,record=False)
    assert result['status']=='HELD'
    assert result['metrics']['attempts']==3
    assert result['reason']=='SEAL_NOT_CONFIRMED'


def test_cancel_before_motion_never_succeeds(tmp_path):
    cancel=threading.Event();cancel.set()
    result=run_job(seed=3,out_dir=tmp_path,cancel=cancel,record=False)
    assert result['status']=='CANCELLED' and not result['success']


def test_duplicate_completed_job_does_not_execute_again(tmp_path):
    first=run_job(seed=3,out_dir=tmp_path,job_id='persistent-1',record=False)
    second=run_job(seed=3,out_dir=tmp_path,job_id='persistent-1',record=False)
    assert first['run_id']==second['run_id']
    assert len(list(tmp_path.glob('*/events.jsonl')))==1

@pytest.mark.integration
def test_measured_free_motion_and_recovery_limits(tmp_path):
    for fault in ('normal','drop'):
        r=run_job(seed=4,fault=fault,out_dir=tmp_path,record=False)
        assert r['success']
        assert max(r['metrics']['max_joint_velocity'][:2]) <= 1.2
        assert max(r['metrics']['max_joint_acceleration'][:2]) <= 3.0
        assert r['metrics']['max_joint_acceleration'][2] <= .8

@pytest.mark.integration
def test_blocked_path_replans_with_payload_clearance(tmp_path):
    r=run_job(seed=4,fault='path_blocked',out_dir=tmp_path,record=False)
    assert r['success'],r['reason']
    assert r['metrics']['retries']==1
    assert r['metrics']['collisions']==0
