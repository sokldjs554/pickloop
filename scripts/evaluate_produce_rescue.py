"""Frozen produce experiment. Infer from anonymous photos, seal outputs, then join truth."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
from shutil import copyfile
from zipfile import ZipFile

for env in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','OMP_THREAD_LIMIT'):
    os.environ[env] = '1'

from evaluate_new_photos import (ROOT, catalogue_semantics, file_hash, fingerprints, official_references,
                                 read_blind, read_csv, rgb_bytes, screen_inputs, write_csv, write_json)
from pickloop.catalogue_features import CatalogueEncoder, verified_weights as dinov2_file
from pickloop.catalogue_model import CatalogueHead
from pickloop.grocery_catalogue import DEFAULT_HEAD, resolve_decision
from pickloop.produce_rescue import TARGETS, apply_produce_rescue, classifier, verified_weights
from pickloop.product_text import recognize_exact

HERE = ROOT/'docs/experiments/produce-rescue'
PRIOR = ROOT/'docs/experiments/new-photos'
PREFIX = 'GroceryStoreDataset-fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/'
FREEZE_SHA = 'bef655e059ead9b6f473d0c4797b5fe01f6dfd509105e4760ad94e2b2d77a434'


def verify():
    path = HERE/'model-freeze.json'
    if file_hash(path) != FREEZE_SHA:
        raise ValueError('Produce model freeze changed')
    frozen = json.loads(path.read_text())
    for name, digest in frozen['source_files'].items():
        if file_hash(ROOT/name) != digest:
            raise ValueError(f'Frozen recognizer changed: {name}')
    if catalogue_semantics() != frozen['resolver_ast_sha256']:
        raise ValueError('Frozen catalogue resolver changed')


def capture(row, prior_cache=None):
    path = Path(row['path'])
    if prior_cache is not None:
        matches = [p for p in prior_cache.rglob(path.name) if p.is_file() and file_hash(p) == row['sha256']]
        if not matches:
            raise ValueError('Prior photo absent from fetched cache: '+row['id'])
        path = matches[0]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != row['sha256']:
        raise ValueError('Image bytes changed: '+row['id'])
    return raw


def experiments(before, rgb, weights, audit=False):
    after = apply_produce_rescue(before, lambda:rgb, weights=weights)
    d = after['produce_rescue']
    result = dict(before=before['prediction'], after=after['prediction'], prior_top1=before['generic_top1'],
                  prior_generic=before['generic_prediction'], prior_support=before.get('support'),
                  prior_reason=before['recognition_reason'], reason=d['reason'], views=d['views'])
    if audit:
        # Extra diagnostic only. The policy never sees these scores on vetoed rows.
        result['ungated_view_predictions'] = d['views'] or classifier(weights).evidence(rgb)
    return result


def metrics(rows):
    stats = {}
    for arm in ('before','after'):
        counts = Counter()
        for r in rows:
            if r[arm]=='UNKNOWN':
                counts['target_held' if r['truth']!='UNKNOWN' else 'outside_held'] += 1
            else:
                counts['correct_named' if r[arm]==r['truth'] else 'wrong_named'] += 1
                if r['truth']=='UNKNOWN':
                    counts['outside_false_named'] += 1
        stats[arm] = {k:counts[k] for k in ('correct_named','wrong_named','target_held','outside_held','outside_false_named')}
    return dict(total=len(rows), known=sum(r['truth']!='UNKNOWN' for r in rows), outside=sum(r['truth']=='UNKNOWN' for r in rows),
                policies=stats, newly_correct=sum(r['before']!=r['truth']==r['after']!='UNKNOWN' for r in rows),
                new_wrong=sum(r['before'] in (r['truth'],'UNKNOWN') and r['after'] not in (r['truth'],'UNKNOWN') for r in rows))


def development(args):
    archive = json.loads((PRIOR/'predictions-seal.json').read_text())
    if file_hash(PRIOR/'predictions-blind.jsonl') != archive['predictions_sha256']:
        raise ValueError('Prior sealed predictions changed')
    preds = {r['id']:r for r in map(json.loads,(PRIOR/'predictions-blind.jsonl').read_text().splitlines())}
    inputs = {r['id']:r for r in read_csv(PRIOR/'inference-inputs.csv')}
    weights = verified_weights(args.resnet)
    rows = []
    for row in read_csv(PRIOR/'rows.csv'):
        i = row['id']
        raw = capture(inputs[i],args.prior_cache)
        if preds[i]['sha256'] != inputs[i]['sha256'] or row['sha256'] != inputs[i]['sha256']:
            raise ValueError('Prior photo differs from cached policy output')
        rgb=rgb_bytes(raw)
        result=experiments(preds[i]['after'],rgb,weights,audit=True)
        if result['before']!=row['after_prediction']:
            raise ValueError('Prior default differs from reported result')
        rows.append(dict(id=i,cohort='prior_produce' if row['role']=='produce_control' else 'prior_juice_stress',
                         truth=row['exact_truth'],sha256=row['sha256'],**result))
    # Independent difficult neighbours in the pre-existing official catalogue.
    # Choose first four unique official test images for each fixed class by path.
    candidates = read_csv(ROOT/'docs/experiments/grocery-catalogue/predictions.csv')
    with ZipFile(args.archive) as archive:
        for sku in ('Zucchini','Avocado','Watermelon','Aubergine','Lemon'):
            neighbours=sorted((r for r in candidates if r['truth']==sku and r['split']=='test'),key=lambda r:r['path'])[:4]
            for row in neighbours:
                raw = archive.read(PREFIX+row['path'])
                if hashlib.sha256(raw).hexdigest()!=row['sha256']:
                    raise ValueError('Official neighbour bytes changed')
                rgb=rgb_bytes(raw)
                base={k:row[k] for k in ('top1','prediction','generic_prediction','generic_top1','decision_source')}
                base.update({k:float(row[k]) for k in ('support','score','margin')})
                begin=recognize_exact(base,lambda:rgb)
                result=experiments(begin,rgb,weights,audit=True)
                rows.append(dict(id=row['path'],cohort='official_neighbour_stress',truth=sku,sha256=row['sha256'],**result))
    write_csv(args.out/'development.csv', rows)
    summaries = {}
    for group in sorted({r['cohort'] for r in rows}):
        group_rows=[r for r in rows if r['cohort']==group]
        summaries[group]=dict(**metrics(group_rows), renamed=sum(r['before']!=r['after'] for r in group_rows),
                              raw_imagenet_single_view_target=sum(r['ungated_view_predictions'][0]['label'] in TARGETS for r in group_rows))
    write_json(args.out/'development.json',dict(scope='Pre-existing development and stress images. No fresh holdout.', groups=summaries))


def infer(args):
    # Truth ledger is intentionally absent from inference arguments. Its digest
    # can be supplied by the separate collector without opening its contents.
    out = args.out
    if any((out/n).exists() for n in ('inference-protocol.json','blind.jsonl','prediction-seal.json')):
        raise ValueError('Use a fresh output directory for a new blind run')
    if len(args.labels_sha)!=64 or any(c not in '0123456789abcdef' for c in args.labels_sha):
        raise ValueError('Expected frozen truth ledger SHA-256')
    blind = read_blind(args.blind, 'fresh')
    refs,archive_hash=official_references(args.archive,args.reference_cache)
    for row in read_csv(PRIOR/'inputs.csv'):
        refs.append(dict(id='prior:'+row['id'],**fingerprints(capture(row,args.prior_cache))))
    for row in blind:
        capture(row)
    eligible,screening=screen_inputs(blind,refs)
    copyfile(args.blind,out/'original-blind.csv')
    write_csv(out/'screening.csv',screening)
    helper=Path(__file__).with_name('evaluate_new_photos.py')
    protocol=dict(frozen_utc=datetime.now(timezone.utc).isoformat(), model_freeze_sha256=FREEZE_SHA,
                  harness_sha256=file_hash(Path(__file__)), helper_sha256=file_hash(helper),
                  blind_sha256=file_hash(args.blind), labels_sha256=args.labels_sha,
                  archive_sha256=archive_hash, prior_reference_and_official_count=len(refs),
                  screening_sha256=file_hash(out/'screening.csv'), eligible_ids=[r['id'] for r in eligible],
                  environment={n:version(n) for n in ('torch','torchvision','numpy','opencv-python-headless','timm','safetensors','Pillow')})
    write_json(out/'inference-protocol.json',protocol)
    weights=verified_weights(args.resnet)
    head=CatalogueHead.load(DEFAULT_HEAD)
    enc=CatalogueEncoder(dinov2_file(args.dinov2))
    with (out/'blind.jsonl').open('x') as stream:
        for row in eligible:
            rgb=rgb_bytes(capture(row))
            generic,=head.predict(enc.encode([rgb]))
            begin=recognize_exact(resolve_decision(generic,lambda:rgb),lambda:rgb)
            record=dict(id=row['id'],sha256=row['sha256'],**experiments(begin,rgb,weights))
            stream.write(json.dumps(record,allow_nan=False)+'\n')
            stream.flush()
    verify()
    write_json(out/'prediction-seal.json', dict(count=len(eligible), completed_utc=datetime.now(timezone.utc).isoformat(),
               protocol_sha256=file_hash(out/'inference-protocol.json'), predictions_sha256=file_hash(out/'blind.jsonl')))


def score(args):
    out=args.out
    seal=json.loads((out/'prediction-seal.json').read_text())
    protocol=json.loads((out/'inference-protocol.json').read_text())
    if (file_hash(out/'blind.jsonl')!=seal['predictions_sha256'] or file_hash(out/'inference-protocol.json')!=seal['protocol_sha256']
            or file_hash(args.labels)!=protocol['labels_sha256'] or file_hash(Path(__file__))!=protocol['harness_sha256']):
        raise ValueError('A frozen input, harness or prediction seal changed')
    inputs={r['id']:r for r in read_csv(out/'original-blind.csv')}
    raw_labels=read_csv(args.labels)
    labels={r['id']:r for r in raw_labels}
    if len(labels)!=len(raw_labels) or set(labels)!=set(inputs):
        raise ValueError('One gold row is required for every candidate')
    predictions=list(map(json.loads,(out/'blind.jsonl').read_text().splitlines()))
    if [r['id'] for r in predictions]!=protocol['eligible_ids'] or len(predictions)!=seal['count']:
        raise ValueError('Sealed population differs from screened cohort')
    rows=[]
    for r in predictions:
        lab=labels[r['id']]
        truth=lab['truth']
        if truth not in {*TARGETS.values(),'UNKNOWN'} or r['sha256']!=inputs[r['id']]['sha256']:
            raise ValueError('Unverified label, target or image')
        rows.append(dict(**r,truth=truth,source_class=lab['source_class'],source_url=lab['source_url'],
                         author=lab['author'],license=lab.get('license',lab.get('licence','')),image_url=lab['image_url']))
    copyfile(args.labels,out/'labels-joined-after.csv')
    write_csv(out/'results.csv',rows)
    write_json(out/'summary.json',dict(scope='Previously unseen source photos after conservative duplicate screening',
              submitted=len(inputs),screened_out=len(inputs)-len(rows),**metrics(rows),
              by_source_class={name:metrics([r for r in rows if r['source_class']==name]) for name in sorted({r['source_class'] for r in rows})},
              seal_sha256=file_hash(out/'prediction-seal.json')))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    dev=sub.add_parser('development')
    inf=sub.add_parser('infer')
    sc=sub.add_parser('score')
    for p in (dev,inf,sc):
        p.add_argument('--out',type=Path,required=True)
    for p in (dev,inf):
        p.add_argument('--resnet',type=Path)
        p.add_argument('--prior-cache',type=Path,help='optional downloaded cache from scripts/fetch_recognition_photos.py')
        p.add_argument('--archive',type=Path,required=True)
    inf.add_argument('--dinov2',type=Path)
    inf.add_argument('--blind',type=Path,required=True)
    inf.add_argument('--labels-sha',required=True)
    inf.add_argument('--reference-cache',type=Path)
    sc.add_argument('--labels',type=Path,required=True)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    verify()
    {'development':development,'infer':infer,'score':score}[args.mode](args)


if __name__=='__main__':
    main()
