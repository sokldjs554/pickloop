"""Persistent job identity and event evidence. One runner lease owns a database."""
import hashlib
import json
import sqlite3
import subprocess
import time
from pathlib import Path

TERMINAL={'COMPLETED','HELD','CANCELLED','HOLD_RECOVERY_REQUIRED'}

class JobStore:
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=3)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,config TEXT,run_id TEXT,state TEXT,result TEXT)')
        self.db.execute("UPDATE jobs SET state='HOLD_RECOVERY_REQUIRED' WHERE state NOT IN ('COMPLETED','HELD','CANCELLED','HOLD_RECOVERY_REQUIRED')")
        self.db.commit()
    def get(self,job_id):
        row=self.db.execute('SELECT config,run_id,state,result FROM jobs WHERE id=?',(job_id,)).fetchone()
        return None if row is None else dict(config=json.loads(row[0]),run_id=row[1],state=row[2],result=json.loads(row[3]) if row[3] else None)
    def begin(self,job_id,config,run_id):
        old=self.get(job_id)
        if old:
            if old['config']!=config: raise ValueError('JOB_ID_CONFLICT')
            return dict(old,created=False)
        self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,NULL)',(job_id,json.dumps(config,sort_keys=True),run_id,'QUEUED'));self.db.commit()
        return dict(created=True,state='QUEUED',run_id=run_id)
    def transition(self,job_id,state,result=None):
        self.db.execute('UPDATE jobs SET state=?,result=? WHERE id=?',(state,json.dumps(result) if result is not None else None,job_id));self.db.commit()
    def close(self):self.db.close()


def source_provenance(root):
    root=Path(root);digest=hashlib.sha256();files={}
    for prefix in ['src','cpp','assets','configs']:
        for path in sorted((root/prefix).rglob('*')):
            if not path.is_file() or '__pycache__' in str(path) or path.suffix=='.pyc':continue
            rel=str(path.relative_to(root));h=hashlib.sha256(path.read_bytes()).hexdigest();files[rel]=h
            digest.update((rel+'\0'+h+'\n').encode())
    try:commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,stderr=subprocess.DEVNULL,text=True).strip()
    except subprocess.CalledProcessError:commit='uncommitted'
    model=root/'models'/'appearance.pt'
    return {'source_sha256':digest.hexdigest(),'git_commit':commit,'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),'source_files':files}


class EventLog:
    def __init__(self,directory,run_id,job_id):
        self.path=Path(directory)/'events.jsonl';self.handle=self.path.open('w');self.run_id=run_id;self.job_id=job_id
        self.events=[];self.start=time.monotonic()
    def emit(self,sim_time,state,event,attempt,observation_id=None,**data):
        row=dict(schema_version=1,run_id=self.run_id,job_id=self.job_id,event_id=len(self.events),sim_time=round(sim_time,6),wall_elapsed_s=round(time.monotonic()-self.start,6),state=state,event=event,attempt=attempt,observation_id=observation_id,data=data)
        self.events.append(row);self.handle.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');self.handle.flush()
        return row
    def close(self):self.handle.close()
