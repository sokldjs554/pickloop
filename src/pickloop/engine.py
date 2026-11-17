"""Actual Behaviour Tree coordinator; bounded recovery and independently evaluated completion."""
import fcntl
import json
import threading
import time
import uuid
from pathlib import Path
import numpy as np
import py_trees as bt
from PIL import Image
from .device import DeviceClient, DeviceEmulator, DeviceError
from .journal import JobStore, EventLog, source_provenance
from .perception import Perception
from .simulation import Cell, ROOT, BIN_CENTER, BIN_HALF
from .types import OperationError

FAULTS=('normal','occlusion','depth_missing','calibration_error','suction_once','communication_delay','drop','path_blocked','suction_permanent','unknown','stale_observation','connection_loss')
PHASES=('OBSERVE','PLAN','APPROACH','SEAL','LIFT','TRANSPORT','PLACE','RELEASE','VERIFY')

class Action(bt.behaviour.Behaviour):
    def __init__(self,name,controller):super().__init__(name);self.controller=controller
    def update(self):
        c=self.controller
        try:
            c.guard();c.state=self.name;c.store.transition(c.job_id,self.name);c.emit('STATE_ENTER')
            getattr(c,self.name.lower())();c.emit('STATE_OK')
            return bt.common.Status.SUCCESS
        except OperationError as e:
            c.last_error=e;c.emit('STATE_FAILED',reason=e.code,detail=e.detail)
            return bt.common.Status.FAILURE
        except (DeviceError,TimeoutError,ConnectionError,OSError) as e:
            c.last_error=OperationError('DEVICE_UNCERTAIN',{'type':type(e).__name__,'message':str(e)})
            c.emit('STATE_FAILED',reason=c.last_error.code,detail=c.last_error.detail)
            return bt.common.Status.FAILURE

class Recovery(bt.decorators.Decorator):
    def __init__(self,child,c):super().__init__('BoundedRecovery',child);self.c=c
    def update(self):
        c=self.c
        if self.decorated.status!=bt.common.Status.FAILURE:return self.decorated.status
        if c.last_error.code in ('CANCELLED','WALL_TIMEOUT','SIM_TIMEOUT','DEVICE_UNCERTAIN','COLLISION') or c.attempt>=c.max_attempts:
            return bt.common.Status.FAILURE
        try:c.recover()
        except (OperationError,DeviceError,TimeoutError) as e:
            c.last_error=e if isinstance(e,OperationError) else OperationError('DEVICE_UNCERTAIN');return bt.common.Status.FAILURE
        self.decorated.stop(bt.common.Status.INVALID)
        return bt.common.Status.RUNNING

class Controller:
    def __init__(self,cell,device,client,store,log,directory,job_id,policy,sku,record,cancel,progress):
        self.cell=cell;self.device=device;self.client=client;self.store=store;self.log=log;self.directory=directory
        self.job_id=job_id;self.policy=policy;self.sku=sku;self.record=record;self.cancel_event=cancel;self.progress=progress
        self.state='QUEUED';self.attempt=1;self.max_attempts=1 if policy=='baseline' else 3
        self.perception=Perception();self.last_error=None;self.target_detection=None;self.detections=[];self.last_observation=None
        self.frames=[];self.last_frame=-100.;self.command_id=0;self.carrying=False;self.verified=False;self.first_failure_time=None
        self.start_sim=cell.sim_time;self.start_wall=time.monotonic();self.inference_times=[];self.position_estimates=[]
        self.max_joint_velocity=np.zeros(4);self.max_joint_acceleration=np.zeros(4);self._last_velocity=cell.data.qvel[:4].copy()
        self.device.set_feedback(cell.pressure_kpa,cell.attached is not None)
        self.cell.on_step=self.on_step
        self.cell.output_source=self.device.output_valve
        if record:(directory/'frames').mkdir(exist_ok=True)
    def guard(self):
        if self.cancel_event.is_set():raise OperationError('CANCELLED')
        if self.cell.sim_time-self.start_sim>60:raise OperationError('SIM_TIMEOUT')
        if time.monotonic()-self.start_wall>90:raise OperationError('WALL_TIMEOUT')
    def emit(self,event,**data):
        obs_id=self.last_observation.observation_id if self.last_observation else None
        self.log.emit(self.cell.sim_time,self.state,event,self.attempt,obs_id,**data)
        if event in ('STATE_ENTER','STATE_FAILED','RECOVERY_BEGIN','RECOVERY_END','TERMINAL'):self.capture(force=True)
    def on_step(self,cell):
        if not cell._stopping:self.guard()
        self.device.set_feedback(cell.pressure_kpa,cell.attached is not None)
        velocity=cell.data.qvel[:4].copy()
        self.max_joint_velocity=np.maximum(self.max_joint_velocity,np.abs(velocity))
        self.max_joint_acceleration=np.maximum(self.max_joint_acceleration,np.abs((velocity-self._last_velocity)/cell.model.opt.timestep));self._last_velocity=velocity
        if not cell._stopping and self.carrying and cell.pressure_kpa>-35 and self.state not in ('RELEASE','VERIFY','RECOVERY'):
            self.carrying=False;raise OperationError('VACUUM_LOSS')
        if self.record and cell.sim_time-self.last_frame>=.20:self.capture()
    def capture(self,force=False):
        if not self.record:return
        if not force and self.cell.sim_time-self.last_frame<.20:return
        self.last_frame=self.cell.sim_time;obs=self.cell.observe();i=len(self.frames)
        camera=f'frames/{i:05d}-camera.jpg';scene=f'frames/{i:05d}-scene.jpg'
        Image.fromarray(obs.rgb).save(self.directory/camera,quality=82)
        Image.fromarray(self.cell.render_scene()).save(self.directory/scene,quality=82)
        # These two images and telemetry were sampled without advancing physics.
        frame=dict(frame_id=i,sim_time=round(self.cell.sim_time,6),wall_elapsed_s=time.monotonic()-self.start_wall,state=self.state,attempt=self.attempt,pressure_kpa=self.cell.pressure_kpa,valve=self.cell.valve,attached=self.cell.attached is not None,joints=self.cell.joints.tolist(),tcp=self.cell.tcp.tolist(),scene=scene,camera=camera,observation_id=obs.observation_id,log_event_id=max(0,len(self.log.events)-1),detections=[self.perception.serialize(d) for d in self.detections] if self.last_observation and abs(obs.sim_time-self.last_observation.sim_time)<.01 else [])
        self.frames.append(frame)
        if self.progress:self.progress(self.snapshot())
    def snapshot(self):return dict(run_id=self.cell.run_id,job_id=self.job_id,seed=self.cell.seed,fault=self.cell.fault,policy=self.policy,sku=self.sku,status='RUNNING',state=self.state,frames=self.frames,events=self.log.events,run_url=f'/runs/{self.cell.run_id}/run.json')
    def observe(self):
        if self.carrying:return
        obs=self.cell.observe();self.last_observation=obs
        t=time.perf_counter();self.target_detection,self.detections=self.perception.target(obs,self.cell.sim_time,self.sku);self.inference_times.append(time.perf_counter()-t)
        self.position_estimates.append({'attempt':self.attempt,'position':self.target_detection.position.tolist(),'observation_id':obs.observation_id})
        self.emit('PERCEPTION',detections=[self.perception.serialize(d) for d in self.detections],inference_wall_s=self.inference_times[-1],calibration_id=obs.calibration_id)
    def plan(self):
        if self.carrying:return
        if self.target_detection is None:raise OperationError('NO_TARGET')
        try:self.last_observation.validate(self.cell.sim_time)
        except ValueError as e:raise OperationError(str(e)) from e
        p=self.target_detection.position
        if not (.10<p[0]<.58 and -.30<p[1]<.10):raise OperationError('TARGET_OUTSIDE_SOURCE')
        self.emit('PLAN_READY',target=p.tolist(),lift_height_m=.30 if self.attempt==1 else .40,planner='analytic_SCARA_IK_quintic_dense_collision_check')
    def approach(self):
        if self.carrying:return
        p=self.target_detection.position
        self.cell.move_to([*p[:2],.28],allow_contact=False)
        self.cell.move_to([*p[:2],p[2]],allow_contact=True)
    def set_valve(self,on):
        self.command_id+=1
        if self.cell.fault=='communication_delay' and self.attempt==1 and on:
            # Delay an actual status RPC before actuation: no command was issued, safe to retry.
            self.device.inject_fault('delay_response')
            try:self.client.status()
            except TimeoutError as e:raise OperationError('DEVICE_RESPONSE_DELAY') from e
        if self.cell.fault=='connection_loss' and self.attempt==1 and on:self.device.inject_fault('drop_ack')
        status=self.client.command(self.command_id,bool(on))
        if status['error']!='none':raise OperationError('DEVICE_UNCERTAIN')
        self.emit('DEVICE_ACK',command_id=self.command_id,status=status)
    def seal(self):
        if self.carrying:return
        self.set_valve(True);self.cell.step_for(.20);status=self.client.status()
        self.emit('SEAL_MEASURED',status=status)
        if status['pressure_kpa']>-35 or not status['attached']:raise OperationError('SEAL_NOT_CONFIRMED')
        self.carrying=True
    def lift(self):
        if self.cell.tcp[2]>.29 and self.carrying:return
        p=self.cell.tcp;self.cell.move_to([*p[:2],.30])
        status=self.client.status()
        if status['pressure_kpa']>-35:raise OperationError('VACUUM_LOSS')
        self.emit('LIFT_CONFIRMED',status=status,tcp=self.cell.tcp.tolist())
    def transport(self):
        height=.30 if self.attempt==1 else .40
        self.cell.move_to([*self.cell.tcp[:2],height],allow_contact=False)
        self.cell.move_to([*BIN_CENTER,height],allow_contact=False)
    def place(self):self.cell.move_to([*BIN_CENTER,.135],allow_contact=True)
    def release(self):
        self.carrying=False;self.set_valve(False);self.cell.step_for(.40)
        clearance=.40 if self.attempt>1 else .30
        self.cell.move_to([*BIN_CENTER,clearance],allow_contact=False)
        self.cell.move_to([.19,-.32,clearance],allow_contact=False)
        self.cell.move_to([.19,-.32,.34],allow_contact=False)
    def verify(self):
        observations=[]
        for _ in range(2):
            self.cell.step_for(.15);obs=self.cell.observe();self.last_observation=obs
            target,self.detections=self.perception.target(obs,self.cell.sim_time,self.sku)
            inside=np.all(np.abs(target.position[:2]-BIN_CENTER)<BIN_HALF-np.array([.032,.026]))
            if not inside or not .105<target.position[2]<.15:raise OperationError('PLACEMENT_NOT_CONFIRMED')
            observations.append(target.position)
        if np.linalg.norm(observations[1]-observations[0])>.004:raise OperationError('PLACEMENT_UNSTABLE')
        status=self.client.status()
        if status['valve'] or status['attached'] or status['pressure_kpa'] < -3:raise OperationError('RELEASE_NOT_CONFIRMED')
        self.verified=True;self.emit('PLACEMENT_VERIFIED',positions=[p.tolist() for p in observations],status=status)
    def recover(self):
        self.state='RECOVERY'
        if self.first_failure_time is None:self.first_failure_time=self.cell.sim_time
        self.emit('RECOVERY_BEGIN',reason=self.last_error.code)
        stop_report=self.cell.stop_motion()
        self.emit('STOP_REPORT',**stop_report)
        if self.cell.collision_count:raise OperationError('COLLISION')
        self.attempt+=1;self.cell.attempt=self.attempt
        if not self.carrying:
            self.set_valve(False)
            self.cell.move_to([*self.cell.tcp[:2],.34],allow_contact=True)
            self.cell.move_to([.19,-.32,.34],allow_contact=False)
            self.cell.step_for(.4)
            self.target_detection=None
        else:
            # Pressure-confirmed payload remains supported; retry transport at higher clearance.
            status=self.client.status()
            if status['pressure_kpa']>-35:raise OperationError('VACUUM_LOSS')
        self.emit('RECOVERY_END',next_attempt=self.attempt,holding_payload=self.carrying)


def run_job(seed=0,fault='normal',policy='recovery',out_dir='runs',job_id=None,record=True,cancel=None,progress=None,sku='SKU-RED-A'):
    if fault not in FAULTS or policy not in ('baseline','recovery'):raise ValueError('Unsupported scenario/policy')
    if not isinstance(seed,int) or isinstance(seed,bool) or seed<0:raise ValueError('seed must be nonnegative integer')
    if sku not in ('SKU-RED-A','SKU-RED-B','UNREGISTERED'):raise ValueError('Unsupported order SKU')
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    lease=(out/'.runner.lock').open('a')
    try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:lease.close();raise RuntimeError('RUNNER_BUSY')
    store=JobStore(out/'jobs.sqlite');config=dict(seed=seed,fault=fault,policy=policy,sku=sku)
    job_id=job_id or 'job-'+uuid.uuid4().hex[:10];run_id=f'{fault}-{seed}-{policy}-{uuid.uuid4().hex[:6]}'
    begun=store.begin(job_id,config,run_id)
    if not begun['created']:
        store.close();lease.close()
        if begun['result'] is not None:return begun['result']
        return dict(job_id=job_id,run_id=begun['run_id'],status=begun['state'],success=False,reason='RESTART_REQUIRES_RECONCILIATION')
    directory=out/run_id;directory.mkdir();log=EventLog(directory,run_id,job_id)
    cell=None;device=None;c=None;start=time.monotonic()
    try:
        cell=Cell(seed=seed,fault=fault,run_id=run_id)
        device=DeviceEmulator(journal_path=directory/'device.sqlite').start();client=DeviceClient('127.0.0.1',device.port,timeout=.12)
        c=Controller(cell,device,client,store,log,directory,job_id,policy,'UNREGISTERED' if fault=='unknown' else sku,record,cancel or threading.Event(),progress)
        initial_truth=cell.truth_summary()  # evaluation only; never supplied to controller/perception
        sequence=bt.composites.Sequence('PickAndVerify',memory=True,children=[Action(p,c) for p in PHASES])
        tree=bt.trees.BehaviourTree(Recovery(sequence,c))
        c.emit('RUN_START',config=config,calibration=cell.calibration)
        while True:
            tree.tick()
            if tree.root.status!=bt.common.Status.RUNNING:break
        status='COMPLETED' if tree.root.status==bt.common.Status.SUCCESS else ('CANCELLED' if c.last_error.code=='CANCELLED' else 'HELD')
        reason=None if status=='COMPLETED' else c.last_error.code
        if status!='COMPLETED':
            # Hold current command; never release an unconfirmed load on cancellation.
            stop_report=cell.stop_motion()
            c.emit('STOP_REPORT',**stop_report)
            if status=='CANCELLED' and c.command_id:
                try:client.cancel(c.command_id)
                except (DeviceError,TimeoutError):reason='CANCELLED_DEVICE_UNCERTAIN'
        final_truth=cell.truth_summary()
        requested=next((o for o in final_truth['objects'] if o['sku']==c.sku),None)
        truth_ok=bool(requested and requested['in_bin'] and requested['speed_m_s']<.02 and final_truth['attached'] is None)
        wrong=sum(o['in_bin'] for o in final_truth['objects'] if o['sku']!=c.sku)
        success=bool(status=='COMPLETED' and c.verified and truth_ok and not wrong)
        if status=='COMPLETED' and not success:status='HELD';reason='EVALUATOR_DISAGREEMENT'
        errors=[]
        target_initial=next((o for o in initial_truth['objects'] if o['sku']==c.sku),None)
        if target_initial and c.position_estimates:
            gt=np.array(target_initial['position']);gt[2]+=.025
            errors=[float(np.linalg.norm(np.array(c.position_estimates[0]['position'])-gt))]
        selection_correct=bool(errors and errors[0]<.045)
        sim_duration=cell.sim_time-c.start_sim;wall_duration=time.monotonic()-start
        metrics=dict(first_attempt_pick_success=any(e['event']=='LIFT_CONFIRMED' and e['attempt']==1 for e in log.events),first_attempt_success=success and c.attempt==1,attempts=c.attempt,retries=c.attempt-1,wrong_placements=wrong,drops=final_truth['drop_count'],collisions=final_truth['collision_count'],held=status=='HELD',cancelled=status=='CANCELLED',sim_duration_s=sim_duration,wall_duration_s=wall_duration,recovery_sim_s=None if c.first_failure_time is None else cell.sim_time-c.first_failure_time,selection_correct=selection_correct,selection_attempted=bool(c.position_estimates),position_error_m=errors[0] if errors else None,inference_wall_s=c.inference_times,verified_by_vision=c.verified,verified_by_truth=truth_ok,max_joint_velocity=c.max_joint_velocity.tolist(),max_joint_acceleration=c.max_joint_acceleration.tolist(),timeout=reason in ('SIM_TIMEOUT','WALL_TIMEOUT'))
        c.state=status;c.emit('TERMINAL',status=status,success=success,reason=reason,metrics=metrics)
        result=dict(schema_version=1,run_id=run_id,job_id=job_id,seed=seed,fault=fault,policy=policy,sku=c.sku,status=status,success=success,reason=reason,sim_duration_s=sim_duration,wall_duration_s=wall_duration,retries=c.attempt-1,metrics=metrics,initial_truth=initial_truth,final_truth=final_truth,position_estimates=c.position_estimates,provenance=source_provenance(ROOT))
        (directory/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
        replay=dict(result,events=log.events,frames=c.frames,run_url=f'/runs/{run_id}/run.json')
        (directory/'run.json').write_text(json.dumps(replay,ensure_ascii=False,allow_nan=False))
        (directory/'calibration.json').write_text(json.dumps(cell.calibration,indent=2))
        store.transition(job_id,status,result)
        if progress:progress(replay)
        return result
    except Exception as e:
        store.transition(job_id,'HOLD_RECOVERY_REQUIRED')
        log.emit(cell.sim_time if cell else 0,'HOLD_RECOVERY_REQUIRED','UNHANDLED_FAILURE',c.attempt if c else 0,error=type(e).__name__,message=str(e))
        raise
    finally:
        if c:c.cell.on_step=None
        if device:device.stop()
        if cell:cell.close()
        log.close();store.close();lease.close()
