"""Check published evidence links, frozen experiment integrity, and local archive contents."""
import argparse,csv,hashlib,json,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--web',default='web');p.add_argument('--archive');a=p.parse_args()
web=Path(a.web);data=web/'data'
metrics=json.loads((data/'metrics.json').read_text());catalog=json.loads((data/'index.json').read_text());raw=json.loads((data/'evaluation/index.json').read_text())['runs']
assert len(raw)==sum(x['n'] for x in metrics['aggregate'].values())
manifest=metrics['protocol'];assert len(raw)==len(manifest['cases'])*len(manifest['policies'])
source=manifest['provenance'];index={r['run_id']:r for r in raw}
for pair in metrics['pairs']:
    for policy in manifest['policies']:assert pair[policy+'_run'] in index
for item in raw:
    path=web/item['run_url'];r=json.loads(path.read_text())
    assert r['policy'] in manifest['policies'] and r['metrics']['attempts']<=manifest['policies'][r['policy']]['max_attempts']
    assert r['provenance']['source_sha256']==source['source_sha256']
    assert r['provenance']['model_sha256']==source['model_sha256']
for record in metrics['raw_files']:
    path=data/'evaluation'/record['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
frames=0;divergent=[]
for item in catalog['runs']:
    p=web/item['run_url'];r=json.loads(p.read_text());assert item['evaluation_run_id'] in index
    assert r['frames']
    if item['recording_equivalent'] is False:divergent.append(r['run_id'])
    for frame in r['frames']:
        for media in ['scene','camera']:assert (p.parent/frame[media]).is_file()
        assert any(e['event_id']==frame['log_event_id'] for e in r['events'])
        frames+=1
for card in json.loads((data/'evidence.json').read_text()):
    for link in card['links']:assert (web/link['url']).is_file(),link['url']
if a.archive:
    with zipfile.ZipFile(a.archive) as z:
        assert z.testzip() is None
        names=set(z.namelist())
        for rel in ['README.md','REPLAY_MEDIA.md','src/pickloop/engine.py','src/pickloop/experiment.py','models/appearance.pt','runs/ablation-heldout/manifest.json','runs/ablation-heldout/metrics.json']:
            assert 'pickloop/'+rel in names
        for rel,sha in source['source_files'].items():assert hashlib.sha256(z.read('pickloop/'+rel)).hexdigest()==sha
        assert hashlib.sha256(z.read('pickloop/models/appearance.pt')).hexdigest()==source['model_sha256']
print(json.dumps(dict(raw_runs=len(raw),recorded_runs=len(catalog['runs']),recorded_frames=frames,divergent_first_recordings=divergent,source_sha256=source['source_sha256'],model_sha256=source['model_sha256']),indent=2))
