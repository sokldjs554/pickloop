"""Record prespecified first-heldout-seed representative cases without altering final results."""
import argparse,json
from pathlib import Path
from pickloop.engine import run_job,POLICIES
p=argparse.ArgumentParser();p.add_argument('evaluation');p.add_argument('--out',required=True);a=p.parse_args()
manifest=json.loads((Path(a.evaluation)/'manifest.json').read_text())
selected=('normal','suction_once','suction_permanent','drop','path_blocked','unknown','calibration_error')
seed=manifest['seeds'][0]
for case in manifest['cases']:
    if case['seed']!=seed or case['fault'] not in selected:continue
    for policy in POLICIES:
        r=run_job(seed=seed,fault=case['fault'],condition=case['condition'],policy=policy,out_dir=a.out,record=True)
        print(seed,case['fault'],policy,r['status'],r['reason'],flush=True)
