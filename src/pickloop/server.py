"""Local simulation service. Serves recorded evidence and computes new CPU runs."""
import json
import fcntl
import sqlite3
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .engine import run_job,FAULTS
from .simulation import ROOT
from .journal import JobStore

class JobRequest(BaseModel):
    seed:int=Field(default=7,ge=0,le=2**31-1,strict=True)
    fault:Literal['normal','occlusion','depth_missing','calibration_error','suction_once','communication_delay','drop','path_blocked','suction_permanent','unknown','stale_observation','connection_loss']='normal'
    policy:Literal['baseline','recovery']='recovery'
    sku:Literal['SKU-RED-A','SKU-RED-B','UNREGISTERED']='SKU-RED-A'
    job_id:str|None=Field(default=None,pattern=r'^[A-Za-z0-9_-]{1,100}$')


def create_app(run_dir=None):
    directory=Path(run_dir or ROOT/'runs'/'live');directory.mkdir(parents=True,exist_ok=True)
    jobs={};configs={};cancels={};lock=threading.RLock();pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='pickloop')
    @asynccontextmanager
    async def lifespan(app):
        # Only the owner of the simulator lease may fence interrupted jobs.
        with (directory/'.runner.lock').open('a') as lease:
            try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:pass  # another active process owns the physical cell
            else:
                recovery_store=JobStore(directory/'jobs.sqlite');recovery_store.close()
        yield
        for event in cancels.values():event.set()
        pool.shutdown(wait=True,cancel_futures=True)
    app=FastAPI(title='PickLoop local simulation',lifespan=lifespan)
    @app.middleware('http')
    async def same_origin(request:Request,call_next):
        origin=request.headers.get('origin')
        if request.method in ('POST','PUT','DELETE') and origin:
            parsed=urlparse(origin)
            if parsed.netloc!=request.headers.get('host'):
                return JSONResponse({'detail':'Cross-origin writes are disabled'},status_code=403)
        return await call_next(request)
    @app.get('/api/health')
    def health():return {'mode':'live','simulation':'MuJoCo CPU','hardware_connected':False,'capacity':1,'faults':FAULTS}
    def progress(job_id,snapshot):
        with lock:jobs[job_id]=json.loads(json.dumps(snapshot))
    def worker(job_id,config):
        try:
            result=run_job(out_dir=directory,job_id=job_id,cancel=cancels[job_id],progress=lambda s:progress(job_id,s),record=True,**config)
            path=directory/result['run_id']/'run.json'
            snapshot=json.loads(path.read_text()) if path.exists() else result
            progress(job_id,snapshot)
        except Exception as e:
            progress(job_id,dict(job_id=job_id,status='HOLD_RECOVERY_REQUIRED',success=False,reason=f'{type(e).__name__}: {e}',frames=[],events=[]))
    @app.post('/api/jobs')
    def submit(body:JobRequest):
        job_id=body.job_id or 'live-'+uuid.uuid4().hex[:10]
        config=body.model_dump(exclude={'job_id'})
        with lock:
            if job_id in jobs:
                if configs[job_id]!=config:raise HTTPException(409,'JOB_ID_CONFLICT')
                return {'job_id':job_id,'run_id':jobs[job_id].get('run_id'),'status':jobs[job_id]['status']}
            if any(j.get('status') in ('QUEUED','RUNNING') for j in jobs.values()):raise HTTPException(409,'RUNNER_BUSY')
            jobs[job_id]=dict(job_id=job_id,run_id=None,status='QUEUED',frames=[],events=[],**config)
            configs[job_id]=config;cancels[job_id]=threading.Event();pool.submit(worker,job_id,config)
        return {'job_id':job_id,'run_id':None,'status':'QUEUED'}
    @app.get('/api/jobs/{job_id}')
    def get(job_id:str):
        with lock:
            if job_id in jobs:return jobs[job_id]
        # Historical status is read without starting a job or rewriting its ledger.
        for path in directory.glob('*/run.json'):
            data=json.loads(path.read_text())
            if data['job_id']==job_id:return data
        ledger=directory/'jobs.sqlite'
        if ledger.exists():
            with sqlite3.connect(ledger) as db:
                row=db.execute('SELECT config,run_id,state,result FROM jobs WHERE id=?',(job_id,)).fetchone()
            if row:
                if row[3]:return json.loads(row[3])
                return dict(job_id=job_id,run_id=row[1],status=row[2],state=row[2],success=False,reason='RESTART_REQUIRES_RECONCILIATION' if row[2]=='HOLD_RECOVERY_REQUIRED' else 'ACTIVE_IN_OTHER_RUNNER',frames=[],events=[],**json.loads(row[0]))
        raise HTTPException(404,'Unknown job ID')
    @app.post('/api/jobs/{job_id}/cancel')
    def cancel(job_id:str):
        with lock:
            if job_id not in cancels:raise HTTPException(404,'Unknown active job ID')
            cancels[job_id].set();return {'job_id':job_id,'cancel_requested':True,'status':jobs[job_id]['status']}
    app.mount('/runs',StaticFiles(directory=directory),name='runs')
    if (ROOT/'web'/'index.html').exists():app.mount('/',StaticFiles(directory=ROOT/'web',html=True),name='ui')
    return app

app=create_app()
