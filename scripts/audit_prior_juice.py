"""Replay frozen decisions on all three God Morgon classes in the old official test split."""
import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
from pathlib import Path
import shutil
from zipfile import ZipFile

# Two operating-system workers, each with one OpenCV/BLAS/Tesseract thread.
for key in ('OMP_NUM_THREADS','OMP_THREAD_LIMIT','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
    os.environ[key] = '1'

import cv2
from pickloop.grocery_evaluation import PREFIX
from pickloop.juice_gate import APPLE, ORANGE, MIX, apply_juice_gate
from pickloop.photo_evaluation import crop_pixels, write_csv, write_json
from pickloop.product_text import recognize_exact

ROOT = Path(__file__).resolve().parents[1]
ARCHIVED = ROOT/'docs/experiments/grocery-catalogue/predictions.csv'
PREVIOUS_MIX = ROOT/'docs/experiments/juice-gate/historical-predictions.csv'
ARCHIVED_SHA = '6e7982856b3c907a584d084b60cb684b20609a28a5e803f08ad2083f45a7530f'
PREVIOUS_MIX_SHA = '6dd85e0dc167a4f89207a20dda7257e40e4468e537107746ee7709411d49f1d0'
LABELS = {'30': APPLE, '31': ORANGE, '32': MIX}
POLICIES = ('old_default','former_juice_gate','frozen_default')


def file_sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_freeze(path):
    freeze = json.loads(path.read_text())
    sources = freeze['source_files']
    required = {'src/pickloop/' + name for name in ('product_text.py','pack_barcode.py','juice_gate.py',
                'carton_matcher.py','photo_evaluation.py','grocery_catalogue.py','data/grocery_catalogue.npz',
                'data/juice_gate.npz','data/bravo_carton_panels.npz')}
    serialized = json.dumps(sources, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if not required <= sources.keys() or hashlib.sha256(serialized).hexdigest() != freeze['source_sha256']:
        raise ValueError('Incomplete or changed frozen model manifest')
    for rel, digest in sources.items():
        if file_sha(ROOT/rel) != digest:
            raise ValueError(f'Stale frozen source or model: {rel}')
    # This historical replay reuses the archived 81-way decisions. Only OCR
    # runs again; verify the actual executable and English language data used.
    external = {Path(k).name:h for k,h in freeze['external_files'].items()}
    executable = shutil.which('tesseract')
    eng = Path(os.environ.get('TESSDATA_PREFIX','/usr/share/tesseract-ocr/5/tessdata'))/'eng.traineddata'
    if not executable or file_sha(Path(executable)) != external.get('tesseract') or file_sha(eng) != external.get('eng.traineddata'):
        raise ValueError('OCR executable or English language data differ from freeze')
    if file_sha(ARCHIVED) != ARCHIVED_SHA or file_sha(PREVIOUS_MIX) != PREVIOUS_MIX_SHA:
        raise ValueError('Archived baseline or historical rows changed')
    return freeze


def load_inputs(archive_path):
    with ARCHIVED.open() as stream:
        rows = [r for r in csv.DictReader(stream) if r['split']=='test' and r['truth'] in LABELS.values()]
    by_path = {r['path']:r for r in rows}
    if len(rows) != len(by_path):
        raise ValueError('duplicate test path')
    with ZipFile(archive_path) as archive:
        official = {}
        for row in csv.reader(archive.read(PREFIX+'test.txt').decode().splitlines()):
            path, fine, _ = (s.strip() for s in row)
            if fine in LABELS:
                official[path] = LABELS[fine]
        if official != {p:r['truth'] for p,r in by_path.items()}:
            raise ValueError('archived truth cohort differs from complete official test split')
        if Counter(official.values()) != Counter({APPLE:19, ORANGE:22, MIX:19}):
            raise ValueError('unexpected class counts')
        inputs = []
        for row in rows:
            raw = archive.read(PREFIX+row['path'])
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError(f"Source photo bytes changed: {row['path']}")
            inputs.append((row,raw))
    return inputs


def classify(item):
    cv2.setNumThreads(1)
    row, raw = item
    rgb, _ = crop_pixels(raw, {})
    # All policies begin with the archived 81-way + Bravo decision for these
    # exact photo bytes. No truth, filename or current order reaches a policy.
    baseline = {k:row[k] for k in ('top1','prediction','generic_top1','generic_prediction','decision_source')}
    baseline.update({k:float(row[k]) for k in ('score','support','margin')})
    old_gate = apply_juice_gate(dict(baseline), lambda:rgb)
    current = recognize_exact(dict(baseline), lambda:rgb)
    return dict(path=row['path'], sha256=row['sha256'], rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
                truth=row['truth'], raw_top1=baseline['top1'], old_default=baseline['prediction'],
                former_juice_gate=old_gate['prediction'], frozen_default=current['prediction'],
                former_reason=old_gate.get('juice_gate_reason','outside_route'),
                frozen_source=current['recognition_source'], frozen_reason=current['recognition_reason'])


def state(row, policy):
    return 'held' if row[policy]=='UNKNOWN' else ('correct' if row[policy]==row['truth'] else 'wrong')


def metrics(rows):
    result = dict(photos=len(rows), policies={}, transitions={})
    for policy in POLICIES:
        counts = Counter(state(r,policy) for r in rows)
        result['policies'][policy] = dict(correct_named=counts['correct'], wrong_named=counts['wrong'], held=counts['held'])
    for old, new in [(POLICIES[0],POLICIES[1]),(POLICIES[0],POLICIES[2]),(POLICIES[1],POLICIES[2])]:
        cells = Counter((state(r,old),state(r,new)) for r in rows)
        transitions = {f'{a}_to_{b}':cells[a,b] for a in ('correct','wrong','held') for b in ('correct','wrong','held')}
        transitions['new_wrong'] = cells['correct','wrong'] + cells['held','wrong']
        result['transitions'][f'{old}_vs_{new}'] = transitions
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',required=True,type=Path)
    p.add_argument('--freeze',required=True,type=Path,help='sealed model-freeze.json')
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--workers',type=int,choices=(1,2),default=2)
    args = p.parse_args()
    freeze = verify_freeze(args.freeze)
    freeze_sha = file_sha(args.freeze)
    inputs = load_inputs(args.archive)
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        rows = list(executor.map(classify, inputs, chunksize=1))
    verify_freeze(args.freeze)
    if file_sha(args.freeze) != freeze_sha:
        raise ValueError('Model freeze changed during replay')
    with PREVIOUS_MIX.open() as stream:
        older = {r['id']:r for r in csv.DictReader(stream)}
    mixed = [r for r in rows if r['truth']==MIX]
    if set(older) != {r['path'] for r in mixed}:
        raise ValueError('Published mixed cohort differs from official mixed test rows')
    disagreements = []
    for r in mixed:
        old = older[r['path']]
        if old['sha256'] != r['sha256'] or old['before'] != r['old_default']:
            raise ValueError(f"Prior mixed cohort baseline mismatch: {r['path']}")
        if old['after'] != r['former_juice_gate']:
            disagreements.append(r['path'])
    result = dict(protocol='Historical replay only. All 60 official test photos whose truth is one of three named God Morgon juices.',
                  baseline_method='Reuse archived 81-class + Bravo decision after per-photo SHA-256 and complete official test-list verification.',
                  rgb_method='EXIF transpose, convert to RGB, whole image, identical array for former gate and frozen default.',
                  cohort_overlap='The 19 previously reported mixed-juice images are a subset of these 60.',
                  policies=POLICIES, archived_predictions_sha256=ARCHIVED_SHA,
                  previous_mixed_ledger_sha256=PREVIOUS_MIX_SHA, archive_prefix=PREFIX,
                  sealed_freeze_sha256=freeze_sha, sealed_source_sha256=freeze['source_sha256'],
                  frozen_product_text_sha256=freeze['source_files']['src/pickloop/product_text.py'],
                  frozen_barcode_sha256=freeze['source_files']['src/pickloop/pack_barcode.py'],
                  former_gate_sha256=freeze['source_files']['src/pickloop/juice_gate.py'],
                  barcode_library=dict(name='zxing-cpp',version=version('zxing-cpp')),
                  full=metrics(rows), by_truth={sku:metrics([r for r in rows if r['truth']==sku]) for sku in (APPLE,ORANGE,MIX)},
                  former_gate_disagreements_with_published_mixed=disagreements)
    args.out.mkdir(parents=True,exist_ok=True)
    write_csv(args.out/'predictions.csv',rows)
    write_json(args.out/'summary.json',result)
    print(json.dumps(dict(all=result['full'], previous_mixed=result['by_truth'][MIX]), indent=2))


if __name__ == '__main__':
    main()
