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

@pytest.mark.integration
def test_cancel_during_lift_brakes_and_keeps_vacuum(tmp_path):
    cancelled=threading.Event()
    def monitor(snapshot):
        frame=snapshot['frames'][-1]
        if frame['state']=='LIFT' and frame['attached'] and frame['tcp'][2]>.20:
            cancelled.set()
    r=run_job(seed=5,out_dir=tmp_path,record=True,cancel=cancelled,progress=monitor)
    assert cancelled.is_set() and r['status']=='CANCELLED'
    assert r['final_truth']['attached'] is not None
    assert r['metrics']['drops']==0
    assert r['metrics']['max_joint_acceleration'][2] <= .8

@pytest.mark.integration
def test_executed_but_unconfirmed_valve_still_affects_physics(tmp_path,monkeypatch):
    from pickloop.device import DeviceEmulator
    original=DeviceEmulator._process
    armed=set()
    def lose_ack_and_status(self,pdu,stopping):
        if pdu[0]==16 and int.from_bytes(pdu[-2:],'big')==1 and id(self) not in armed:
            armed.add(id(self));self.inject_fault('drop_ack')
            response=original(self,pdu,stopping);self.inject_fault('delay_response');return response
        return original(self,pdu,stopping)
    monkeypatch.setattr(DeviceEmulator,'_process',lose_ack_and_status)
    r=run_job(seed=4,out_dir=tmp_path,record=False)
    assert r['status']=='HELD' and r['reason']=='DEVICE_UNCERTAIN'
    assert r['final_truth']['attached'] is not None
    import sqlite3
    with sqlite3.connect(tmp_path/r['run_id']/'device.sqlite') as db:
        assert db.execute('SELECT valve,execution_count FROM controller').fetchone()==(1,1)

@pytest.mark.integration
def test_dynamic_collision_has_durable_terminal_evidence(tmp_path,monkeypatch):
    from pickloop.simulation import Cell
    import mujoco,numpy as np
    original=Cell.step
    injected=set()
    def block_during_motion(cell):
        if cell.attached is not None and cell.tcp[2]>.25 and cell.tcp[1]>-.16 and np.linalg.norm(cell.data.qvel[:2])>.15:
            gid=mujoco.mj_name2id(cell.model,mujoco.mjtObj.mjOBJ_GEOM,'blocker')
            cell.model.geom_pos[gid,2]=.20;injected.add(id(cell))
        original(cell)
    monkeypatch.setattr(Cell,'step',block_during_motion)
    r=run_job(seed=4,out_dir=tmp_path,record=False)
    assert injected
    assert r['status']=='HELD' and not r['success']
    assert r['metrics']['collisions']>0
    assert (tmp_path/r['run_id']/'result.json').is_file()
    assert (tmp_path/r['run_id']/'run.json').is_file()

def test_stale_observation_at_planning_becomes_recoverable_error():
    from pickloop.engine import Controller
    from pickloop.simulation import Cell
    from pickloop.perception import Perception
    from pickloop.types import OperationError
    with Cell(seed=1) as cell:
        obs=cell.observe();target,_=Perception().target(obs,cell.sim_time,'SKU-RED-A')
        cell.step_for(.5)
        c=Controller.__new__(Controller);c.carrying=False;c.target_detection=target;c.last_observation=obs;c.cell=cell
        with pytest.raises(OperationError,match='OBSERVATION_STALE'):c.plan()
