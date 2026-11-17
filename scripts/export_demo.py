"""Copy authentic runs into the static operator replay without computing fake states."""
import argparse
import json
import shutil
from datetime import datetime,timezone
from pathlib import Path


def export(source,dest,metrics=None):
    source,dest=Path(source),Path(dest);dest.mkdir(parents=True,exist_ok=True)
    entries=[]
    for path in sorted(source.glob('*/run.json')):
        run=json.loads(path.read_text())
        if not run['frames']:continue
        folder=dest/'runs'/run['run_id'];folder.mkdir(parents=True,exist_ok=True)
        for name in ['run.json','result.json','events.jsonl','calibration.json']:
            shutil.copy2(path.parent/name,folder/name)
        shutil.copytree(path.parent/'frames',folder/'frames',dirs_exist_ok=True)
        entries.append({k:run.get(k) for k in ['run_id','job_id','seed','fault','policy','status','success','sku','sim_duration_s','wall_duration_s','retries','reason']}|{'run_url':f"data/runs/{run['run_id']}/run.json"})
    if not entries:raise ValueError('No recorded runs to export')
    catalog={'schema_version':1,'generated_at':datetime.now(timezone.utc).isoformat(),'source_version':run['provenance']['git_commit'],'runs':entries}
    if metrics:
        shutil.copy2(metrics,dest/'metrics.json');catalog['metrics_url']='data/metrics.json'
    (dest/'index.json').write_text(json.dumps(catalog,indent=2,ensure_ascii=False))
    print(f'Exported {len(entries)} authentic runs to {dest}')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--dest',default='web/data');p.add_argument('--metrics');a=p.parse_args();export(a.source,a.dest,a.metrics)
