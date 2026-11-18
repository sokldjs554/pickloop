"""Export all raw evaluation evidence and separately identified representative replays."""
import argparse,json,shutil,hashlib
from pathlib import Path
from datetime import datetime,timezone

def export(evaluation,replays,dest):
    evaluation,replays,dest=map(Path,(evaluation,replays,dest));dest.mkdir(exist_ok=True,parents=True)
    rows={}
    raw=[]
    for path in sorted(evaluation.glob('*/run.json')):
        run=json.loads(path.read_text());rows[run['seed'],run['fault'],run['policy']]=run
        target=dest/'evaluation'/run['run_id'];target.mkdir(parents=True,exist_ok=True)
        for name in ['run.json','result.json','events.jsonl','calibration.json']:shutil.copy2(path.parent/name,target/name)
        raw.append({k:run.get(k) for k in ['run_id','seed','fault','policy','condition_id','status','success','reason']}|{'run_url':f"data/evaluation/{run['run_id']}/run.json"})
    (dest/'evaluation'/'index.json').write_text(json.dumps({'runs':raw},ensure_ascii=False,indent=2))
    for name in ['manifest.json','metrics.json','summary.md','trials.csv']:shutil.copy2(evaluation/name,dest/name)
    entries=[]
    for path in sorted(replays.glob('*/run.json')):
        run=json.loads(path.read_text());original=rows[run['seed'],run['fault'],run['policy']]
        equal={k:run[k]==original[k] for k in ['condition','initial_truth','success','reason','retries']}
        equal['sim_delta_s']=run['sim_duration_s']-original['sim_duration_s']
        # Source hash and exact physical steps must agree; only render wall overhead may differ.
        equal['source']=run['provenance']['source_sha256']==original['provenance']['source_sha256']
        equal['model']=run['provenance']['model_sha256']==original['provenance']['model_sha256']
        if not all(v for k,v in equal.items() if k!='sim_delta_s') or abs(equal['sim_delta_s'])>1e-7:
            raise ValueError(f"Replay differs from frozen evaluation: {run['run_id']} {equal}")
        target=dest/'runs'/run['run_id'];shutil.copytree(path.parent,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('*.sqlite','*.sqlite-wal','*.sqlite-shm'))
        entry={k:run.get(k) for k in ['run_id','job_id','seed','fault','policy','status','success','sku','sim_duration_s','wall_duration_s','retries','reason','condition_id']}
        entry.update(run_url=f"data/runs/{run['run_id']}/run.json",evaluation_run_id=original['run_id'],evaluation_url=f"data/evaluation/{original['run_id']}/run.json",equivalence=equal)
        entries.append(entry)
    catalog=dict(schema_version=2,generated_at=datetime.now(timezone.utc).isoformat(),source_version=next(iter(rows.values()))['provenance']['git_commit'],runs=entries,metrics_url='data/metrics.json',all_evaluation_url='data/evaluation/index.json',replay_note='Same frozen condition and source; physical outcomes/timing verified equal. Rendering wall time is separate from evaluation.')
    (dest/'index.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
    print(json.dumps({'raw_evaluation_runs':len(raw),'recorded_replays':len(entries),'frames':sum(len(json.loads(p.read_text())['frames']) for p in (dest/'runs').glob('*/run.json'))}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('evaluation');p.add_argument('replays');p.add_argument('--dest',default='web/data');a=p.parse_args();export(a.evaluation,a.replays,a.dest)
