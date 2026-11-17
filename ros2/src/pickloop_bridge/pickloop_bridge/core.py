"""HTTP and observable-data helpers; no simulator or robot-truth access."""
import json
import math
import re
from pathlib import PurePosixPath
from urllib.parse import quote
from urllib.request import Request, urlopen

TERMINAL={'COMPLETED','HELD','CANCELLED','HOLD_RECOVERY_REQUIRED','FAILED'}


def progress(snapshot):
    samples=snapshot.get('frames') or snapshot.get('events') or [{}]
    latest=samples[-1]
    sim_time=float(latest.get('sim_time',snapshot.get('sim_time',0.)))
    if not math.isfinite(sim_time):raise ValueError('nonfinite sim_time')
    return (str(snapshot.get('state',snapshot.get('status','QUEUED'))),
            str(snapshot.get('run_id') or ''),sim_time,int(latest.get('attempt',1)))


def camera_path(run_id, relative):
    path=PurePosixPath(relative)
    if (not re.fullmatch(r'[A-Za-z0-9_.-]+',run_id) or path.is_absolute()
            or '..' in path.parts or ':' in relative or not path.parts or path.parts[0]!='frames'):
        raise ValueError('camera must be a relative frame inside this run')
    return '/runs/'+quote(run_id,safe='')+'/'+str(path)


class HttpCore:
    def __init__(self,base_url,timeout=1.):
        self.base_url=base_url.rstrip('/');self.timeout=timeout
    def request(self,path,body=None):
        payload=None if body is None else json.dumps(body).encode()
        request=Request(self.base_url+path,data=payload,headers={'Content-Type':'application/json'},
                        method='GET' if body is None else 'POST')
        with urlopen(request,timeout=self.timeout) as response:
            return json.load(response)
    def submit(self,goal):
        return self.request('/api/jobs',{key:getattr(goal,key) for key in ('job_id','seed','fault','policy','sku')})
    def status(self,job_id):return self.request('/api/jobs/'+quote(job_id,safe=''))
    def cancel(self,job_id):return self.request('/api/jobs/'+quote(job_id,safe='')+'/cancel',{})
    def image(self,path):
        with urlopen(self.base_url+path,timeout=self.timeout) as response:
            data=response.read(10_000_001)
            if len(data)>10_000_000:raise ValueError('frame exceeds 10 MB')
            return data
