#!/usr/bin/env python3
"""Freeze/deduplicate opaque photos, infer from pixels, then join locked labels.

Stages are intentionally separate: prepare -> infer -> score -> audit.
No threshold fitting, source selection by prediction, or image redistribution.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
UNKNOWN = 'UNKNOWN'
OFFICIAL_PREFIX = 'GroceryStoreDataset-fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/'
REGISTERED_GTINS = {
    '7310865074225': 'God-Morgon-Apple-Juice',
    '7310860007372': 'God-Morgon-Orange-Juice',
    '7310860007259': 'God-Morgon-Orange-Red-Grapefruit-Juice',
}
BASELINE_COMMIT = '2ebacf1f83192eb83983cde93256b871e49af764'
BASELINE_FILES = {
    'src/pickloop/catalogue_features.py': 'f32127e6506e86ab4ecab1983bb20f64d01dc02ce6ca9bdc6d421d1ff4be6957',
    'src/pickloop/catalogue_model.py': 'b8750265dd4a43d085dd0e24e5f972780bbf6fb97b2a29adb925bbb0370839df',
    'src/pickloop/carton_matcher.py': '9ae3670c1b1a7e46018a201e443b74d8b0e5427e7623ebe101245e6eeb2c3243',
    'src/pickloop/data/grocery_catalogue.npz': '55b1af5108cb748b05702f14976a9bee471872730ce5221ad2c9be16a906fcd1',
    'src/pickloop/data/bravo_carton_panels.npz': '7537c7c13ee7a44635e2fc49c3a21235be712b6b4bcbd2a4bc558bd44a81312c',
}
BASELINE_SEMANTICS = '49584fe5c5cbaf9b49eacf8c5d117bf4e9cee5abdaeee0c5e855613125143a19'
ROLES = ('new_primary', 'alternate_gtin_challenge', 'prior_development',
         'produce_control', 'identity_unverified')


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields=None):
    if fields is None:
        fields = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})


def rgb_bytes(data):
    with Image.open(io.BytesIO(data)) as image:
        return np.asarray(ImageOps.exif_transpose(image).convert('RGB'))


def hashes(rgb):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    dh = np.packbits(small[:, 1:] > small[:, :-1]).tobytes().hex()
    low = cv2.dct(cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32))[:8, :8].ravel()
    ph = np.packbits(low > np.median(low[1:])).tobytes().hex()
    return ph, dh


def fingerprints(data):
    rgb = rgb_bytes(data)
    ph, dh = hashes(rgb)
    # Additional conservative check for the same studio packshot on a resized
    # white/black canvas. This crop is NEVER supplied to the classifier.
    corners = np.concatenate([rgb[:3, :3].reshape(-1, 3), rgb[-3:, :3].reshape(-1, 3),
                              rgb[:3, -3:].reshape(-1, 3), rgb[-3:, -3:].reshape(-1, 3)])
    background = np.median(corners, axis=0)
    crop = rgb
    if np.max(np.abs(corners.astype(float)-background)) < 25:
        mask = np.max(np.abs(rgb.astype(float)-background), axis=2) > 30
        yy, xx = np.nonzero(mask)
        if len(xx) > rgb.shape[0]*rgb.shape[1]*.02:
            crop = rgb[yy.min():yy.max()+1, xx.min():xx.max()+1]
    cp, cd = hashes(crop)
    return dict(sha256=hashlib.sha256(data).hexdigest(),
                pixel_sha256=hashlib.sha256(f'{rgb.shape}|'.encode()+rgb.tobytes()).hexdigest(),
                phash=ph, dhash=dh, crop_phash=cp, crop_dhash=cd,
                width=rgb.shape[1], height=rgb.shape[0])


def distances(a, b, prefix=''):
    return tuple((int(a[prefix+k], 16)^int(b[prefix+k], 16)).bit_count() for k in ('phash','dhash'))


def duplicate_reason(a, b):
    if a['sha256'] == b['sha256']:
        return 'identical_file_bytes'
    if a['pixel_sha256'] == b['pixel_sha256']:
        return 'identical_decoded_pixels'
    if max(distances(a, b)) <= 8 or max(distances(a, b, 'crop_')) <= 8:
        return 'perceptual_near_duplicate_candidate'
    return None


def read_blind(path, cohort):
    path = Path(path).resolve()
    with path.open(newline='') as handle:
        reader = csv.DictReader(handle)
        if set(reader.fieldnames or ()) not in ({'id','path','sha256'}, {'sample_id','path','sha256'}):
            raise ValueError('Blind manifest must contain ONLY id,path,sha256')
        rows = list(reader)
    result, seen = [], set()
    for row in rows:
        identity = row.get('id', row.get('sample_id'))
        if not identity or identity in seen:
            raise ValueError('Duplicate or empty blind ID')
        seen.add(identity)
        image_path = (path.parent/row['path']).resolve()
        if file_hash(image_path) != row['sha256']:
            raise ValueError(f'Input checksum mismatch: {identity}')
        result.append(dict(id=identity, path=str(image_path), sha256=row['sha256'], cohort=cohort))
    return sorted(result, key=lambda r:r['id'])


def official_references(archive_path, cache=None):
    expected = {}
    for name in ('training.csv','predictions.csv'):
        for r in read_csv(ROOT/'docs/experiments/grocery-catalogue'/name):
            if r.get('split') != 'outside_test':
                expected[r['path']] = r['sha256']
    archive_sha = file_hash(archive_path)
    if cache and Path(cache).exists():
        cached = json.loads(Path(cache).read_text())
        if (cached['archive_sha256'] == archive_sha and cached['harness_sha256'] == file_hash(__file__)
                and cached['expected_sha256'] == digest(expected)):
            return cached['references'], archive_sha
    references = []
    with ZipFile(archive_path) as archive:
        for name in sorted(archive.namelist()):
            if name.startswith(OFFICIAL_PREFIX) and name.lower().endswith('.jpg'):
                relative = name[len(OFFICIAL_PREFIX):]
                fp = fingerprints(archive.read(name))
                if expected.get(relative) != fp['sha256']:
                    raise ValueError(f'Official image checksum mismatch: {relative}')
                references.append(dict(id='official:'+relative, **fp))
    if len(references) != 5502 or len(expected) != 5502:
        raise ValueError('Expected all 5502 official train/test/val/catalogue photos')
    if cache:
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
        write_json(cache, dict(archive_sha256=archive_sha, harness_sha256=file_hash(__file__),
                              expected_sha256=digest(expected), references=references))
    return references, archive_sha


def screen_inputs(inputs, references):
    pool = list(references)
    screened, included = [], []
    # Prior seven are always replayed as development, never promoted to unseen.
    ordered = sorted(inputs, key=lambda r:(r['cohort'] != 'prior', r['cohort'], r['id']))
    for item in ordered:
        fp = fingerprints(Path(item['path']).read_bytes())
        nearest = min(pool, key=lambda ref:(min(max(distances(fp, ref)), max(distances(fp, ref, 'crop_'))), ref['id']))
        matches = [(duplicate_reason(fp, ref), ref) for ref in pool]
        matches = [(reason, ref) for reason, ref in matches if reason]
        rank = {'identical_file_bytes':0, 'identical_decoded_pixels':1, 'perceptual_near_duplicate_candidate':2}
        match = min(matches, key=lambda v:(rank[v[0]],v[1]['id'])) if matches else None
        keep = item['cohort'] == 'prior' or match is None
        screened.append(dict(id=item['id'], cohort=item['cohort'], sha256=item['sha256'],
                             status='development_replay' if item['cohort']=='prior' else 'included' if keep else 'excluded',
                             reason=match[0] if match else '', duplicate_of=match[1]['id'] if match else '',
                             nearest=nearest['id'], phash_distance=distances(fp,nearest)[0],
                             dhash_distance=distances(fp,nearest)[1],
                             crop_phash_distance=distances(fp,nearest,'crop_')[0],
                             crop_dhash_distance=distances(fp,nearest,'crop_')[1]))
        if keep:
            included.append(item)
        # Even excluded prior/candidate pixels remain in the contamination pool.
        pool.append(dict(id=item['cohort']+':'+item['id'], **fp))
    return included, screened


def prepare(args):
    out = args.out.resolve()
    if out.exists():
        raise FileExistsError('Use a new output directory; do not replace a frozen cohort')
    inputs = read_blind(args.blind, 'new') + read_blind(args.prior_blind, 'prior')
    truth_hashes = dict(new=file_hash(args.labels), prior=file_hash(args.prior_labels))
    if args.control_blind or args.control_labels:
        if not (args.control_blind and args.control_labels):
            raise ValueError('Control requires blind and labels manifests')
        inputs += read_blind(args.control_blind, 'produce_control')
        truth_hashes['produce_control'] = file_hash(args.control_labels)
    if len({r['id'] for r in inputs}) != len(inputs):
        raise ValueError('IDs must be unique across cohorts')
    references, archive_sha = official_references(args.archive, args.reference_cache)
    included, screening = screen_inputs(inputs, references)
    out.mkdir(parents=True)
    originals = {'original-blind-new.csv':args.blind, 'original-labels-new.csv':args.labels,
                 'original-blind-prior.csv':args.prior_blind, 'original-labels-prior.csv':args.prior_labels}
    if args.control_blind:
        originals.update({'original-blind-control.csv':args.control_blind,
                          'original-labels-control.csv':args.control_labels})
    for name,path in originals.items():
        shutil.copyfile(path,out/name)  # Preserve original bytes; do not parse truth.
    write_csv(out/'inputs.csv', inputs)
    write_csv(out/'screening.csv', screening)
    write_csv(out/'inference-inputs.csv', included)
    protocol = dict(schema_version=1, frozen_at=datetime.now(timezone.utc).isoformat(),
                    harness_sha256=file_hash(__file__), source_protocol_sha256=file_hash(args.source_protocol) if args.source_protocol else None,
                    inputs_sha256=file_hash(out/'inputs.csv'), inference_inputs_sha256=file_hash(out/'inference-inputs.csv'),
                    screening_sha256=file_hash(out/'screening.csv'), truth_manifest_sha256=truth_hashes,
                    registry_sha256=file_hash(ROOT/'docs/experiments/grocery-catalogue/registry.json'),
                    original_manifests={name:file_hash(out/name) for name in originals},
                    reference_archive_sha256=archive_sha, reference_count=len(references), reference_index_sha256=digest(references),
                    candidates=len(inputs), included=len(included),
                    cohorts=dict(Counter(r['cohort'] for r in inputs)), registered_gtins=REGISTERED_GTINS,
                    duplicate_rule='Exclude new/control if file/pixel identical OR pHash<=8 AND dHash<=8 on whole image OR background-trimmed image. Include earlier candidates in the reference pool. Prior seven remain development even if duplicate.',
                    selection='ID-sorted, prediction-independent; crop used for dedup only, classifier gets original EXIF-oriented RGB.',
                    roles=list(ROLES), baseline='Existing default 81-way catalogue + Bravo panel resolution; old optional juice gate is NOT applied.',
                    after='product_text.recognize_exact(baseline_decision, callable returning original RGB)',
                    blinding='Truth manifests hashed as bytes only at prepare; no truth/GTIN/name/URL is parsed or supplied to classifiers. Labels joined after complete sealed prediction ledger.',
                    analysis='Descriptive micro counts; known exact-name recall denominator=known only; unknown false-accept denominator=unknown only. All paired transitions including correct->bad. Multiple views grouped conservatively; no iid confidence interval.',
                    prior_role='All seven previous external photos are development evidence, not unseen evaluation.',
                    exact_identity='Original registered 1-L GTINs in primary; alternate GTIN same-flavour is a separate challenge with exact UNKNOWN; controls use registered fine-class identity, not a packaged GTIN claim.',
                    tuning='No threshold/data/model edits after first new-image inference; interrupted batches preserved, never selective rerun.')
    write_json(out/'protocol.json', protocol)
    if args.source_protocol:
        shutil.copyfile(args.source_protocol, out/'source-protocol.txt')
    print(json.dumps(dict(frozen=str(out/'protocol.json'), candidates=len(inputs), included=len(included),
                          screening=Counter(r['status'] for r in screening)), indent=2))


def catalogue_semantics():
    tree = ast.parse((ROOT/'src/pickloop/grocery_catalogue.py').read_text())
    names = {'DEFAULT_HEAD','BRAVO_GALLERY','BRAVO_GALLERY_SHA256','BRAVO','bravo_matcher','resolve_decision'}
    nodes = [n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names or
             isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in n.targets)]
    return hashlib.sha256('\n'.join(ast.dump(n,include_attributes=False) for n in nodes).encode()).hexdigest()


def check_inputs(out):
    protocol = json.loads((out/'protocol.json').read_text())
    if file_hash(__file__) != protocol['harness_sha256']:
        raise ValueError('Evaluator changed after cohort freeze')
    if file_hash(ROOT/'docs/experiments/grocery-catalogue/registry.json') != protocol['registry_sha256']:
        raise ValueError('Registered class list changed after cohort freeze')
    for name,sha in protocol['original_manifests'].items():
        if file_hash(out/name) != sha:
            raise ValueError('Original manifest bytes changed after cohort freeze')
    for name, key in [('inputs.csv','inputs_sha256'), ('inference-inputs.csv','inference_inputs_sha256'), ('screening.csv','screening_sha256')]:
        if file_hash(out/name) != protocol[key]:
            raise ValueError('Frozen input/screening ledger changed')
    return protocol


def predict_one(item, classifier):
    data = Path(item['path']).read_bytes()
    if hashlib.sha256(data).hexdigest() != item['sha256']:
        raise ValueError('Photo checksum changed')
    rgb = rgb_bytes(data)
    before, after = classifier(rgb)  # Only pixels cross this boundary.
    return dict(id=item['id'], sha256=item['sha256'], before=before, after=after)


def infer(args):
    out = args.out.resolve()
    protocol = check_inputs(out)
    if file_hash(__file__) != protocol['harness_sha256']:
        raise ValueError('Evaluator changed after cohort freeze')
    for rel, sha in BASELINE_FILES.items():
        if file_hash(ROOT/rel) != sha:
            raise ValueError('Existing baseline code/model changed: '+rel)
    if catalogue_semantics() != BASELINE_SEMANTICS:
        raise ValueError('Existing default baseline resolver changed')
    paths = [p for p in sorted((ROOT/'src/pickloop').rglob('*')) if p.is_file() and
             '__pycache__' not in p.parts and p.suffix != '.pyc']
    files = {str(p.relative_to(ROOT)):file_hash(p) for p in paths}
    if 'src/pickloop/product_text.py' not in files:
        raise ValueError('New recognizer must be completed and frozen before inference')
    external = {str(args.weights.resolve()):file_hash(args.weights)}
    executable = shutil.which('tesseract')
    if not executable:
        raise ValueError('Tesseract executable missing')
    external[executable] = file_hash(executable)
    # Record the actual optical decoder binary, not only its package version.
    barcode_binary = importlib.util.find_spec('zxingcpp').origin
    external[barcode_binary] = file_hash(barcode_binary)
    for p in sorted(args.tessdata.glob('*.traineddata')):
        external[str(p.resolve())] = file_hash(p)
    if not list(args.tessdata.glob('*.traineddata')):
        raise ValueError('No OCR model data found to freeze')
    freeze = dict(schema_version=1, frozen_at=datetime.now(timezone.utc).isoformat(),
                  source_files=files, source_sha256=digest(files), external_files=external,
                  harness_sha256=file_hash(__file__), protocol_sha256=file_hash(out/'protocol.json'),
                  baseline_commit=BASELINE_COMMIT, baseline_files=BASELINE_FILES,
                  baseline_resolver_semantics_sha256=BASELINE_SEMANTICS,
                  environment=dict(python=platform.python_version(), platform=platform.platform(),
                                   packages={p:importlib.metadata.version(p) for p in ('numpy','Pillow','opencv-python-headless','torch','torchvision','timm','safetensors','scipy','zxing-cpp')},
                                   tesseract=subprocess.check_output([executable,'--version'],text=True).splitlines()[0]))
    with (out/'model-freeze.json').open('x') as handle:
        json.dump(freeze, handle, indent=2);handle.write('\n')
    for key in ('OMP_NUM_THREADS','OMP_THREAD_LIMIT','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
        os.environ[key] = '1'
    from pickloop.catalogue_features import CatalogueEncoder
    from pickloop.catalogue_model import CatalogueHead
    from pickloop.grocery_catalogue import DEFAULT_HEAD, resolve_decision
    from pickloop.product_text import recognize_exact
    head, encoder = CatalogueHead.load(DEFAULT_HEAD), CatalogueEncoder(args.weights)
    def classify(rgb):
        generic, = head.predict(encoder.encode([rgb]))
        before = resolve_decision(generic, lambda:rgb)
        after = recognize_exact(dict(before), lambda:rgb)
        return before, after
    inputs = read_csv(out/'inference-inputs.csv')
    started = time.monotonic()
    with (out/'predictions-blind.jsonl').open('x') as handle:
        for item in inputs:
            if any(file_hash(ROOT/p) != sha for p,sha in files.items()):
                raise ValueError('Frozen recognizer source/data changed during inference')
            result = predict_one(item, classify)
            handle.write(json.dumps(result, ensure_ascii=False, allow_nan=False)+'\n');handle.flush()
            print('predicted', item['id'], flush=True)  # No truth is read; predictions stay in the raw ledger.
    if any(file_hash(p) != sha for p,sha in external.items()):
        raise ValueError('External model/OCR files changed during inference')
    if any(file_hash(ROOT/p) != sha for p,sha in files.items()):
        raise ValueError('Frozen source/data changed during final image inference')
    write_json(out/'predictions-seal.json', dict(count=len(inputs), predictions_sha256=file_hash(out/'predictions-blind.jsonl'),
                                               model_freeze_sha256=file_hash(out/'model-freeze.json'),
                                               completed_at=datetime.now(timezone.utc).isoformat(), wall_s=time.monotonic()-started))


def outcome(truth, prediction):
    if truth == UNKNOWN:
        return 'correct_rejection' if prediction == UNKNOWN else 'false_accept'
    return 'correct' if prediction == truth else 'held' if prediction == UNKNOWN else 'wrong'


def exact_role(label, *, prior, control=False):
    truth = label['truth']
    if prior:
        return truth, 'prior_development'
    if control:
        return truth, 'produce_control'
    status = label.get('exact_sku_status', '')
    if status == 'alternate_gtin_family':
        return UNKNOWN, 'alternate_gtin_challenge'
    if status == 'registered':
        if REGISTERED_GTINS.get(label.get('gtin')) != truth:
            raise ValueError('Registered exact truth/GTIN mismatch')
        return truth, 'new_primary'
    if status == 'verified_identical_alias':
        if not label.get('alias_evidence_url') or REGISTERED_GTINS.get(label.get('registered_gtin')) != truth:
            raise ValueError('Alias requires independent identical-package evidence and registered GTIN')
        return truth, 'new_primary'
    if status == 'unknown' and truth == UNKNOWN:
        return UNKNOWN, 'new_primary'
    if status in ('unverified','identity_unverified'):
        return UNKNOWN, 'identity_unverified'
    raise ValueError('Missing/invalid exact-SKU status; do not silently promote family labels')


def paired_metrics(rows):
    known = sum(r['exact_truth'] != UNKNOWN for r in rows)
    unknown = len(rows)-known
    result = dict(n=len(rows), known=known, unknown=unknown,
                  source_groups=len({r['source_group'] for r in rows}))
    for arm in ('before','after'):
        counts = Counter(outcome(r['exact_truth'],r[arm+'_prediction']) for r in rows)
        held = counts['held']+counts['correct_rejection']
        result[arm] = dict(correct_names=counts['correct'], known_exact_recall=counts['correct']/known if known else None,
                           named_wrong=counts['wrong']+counts['false_accept'], known_wrong=counts['wrong'],
                           held=held, known_held=counts['held'], unknown_correct_rejections=counts['correct_rejection'],
                           unknown_false_accepts=counts['false_accept'],
                           unknown_false_accept_rate=counts['false_accept']/unknown if unknown else None,
                           named=len(rows)-held, family_matches=sum(r.get('family_truth') not in ('',None,UNKNOWN) and
                                                                   r[arm+'_prediction']==r['family_truth'] for r in rows))
    transitions = Counter(outcome(r['exact_truth'],r['before_prediction'])+'->'+
                          outcome(r['exact_truth'],r['after_prediction']) for r in rows)
    result['paired_transitions'] = dict(sorted(transitions.items()))
    result['formerly_correct_to_bad'] = transitions['correct->held']+transitions['correct->wrong']
    return result


def summarize(rows):
    strata, groups, routes = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in rows:
        strata[row['role'],row['view_type'],row['capture_type']].append(row)
        groups[row['role'],row['source_group']].append(row)
        routes[row['role'],row.get('recognition_source','unrecorded')].append(row)
    return dict(roles={role:paired_metrics([r for r in rows if r['role']==role]) for role in ROLES},
                by_stratum=[dict(role=k[0],view_type=k[1],capture_type=k[2],**paired_metrics(v)) for k,v in sorted(strata.items())],
                by_route=[dict(role=k[0],recognition_source=k[1],**paired_metrics(v)) for k,v in sorted(routes.items())],
                by_source_group=[dict(role=k[0],source_group=k[1],ids=sorted(r['id'] for r in v),
                                      source_urls=sorted({r.get('source_url','') for r in v}),**paired_metrics(v)) for k,v in sorted(groups.items())])


def score(args):
    out = args.out.resolve()
    protocol = check_inputs(out)
    seal = json.loads((out/'predictions-seal.json').read_text())
    if (file_hash(out/'predictions-blind.jsonl') != seal['predictions_sha256'] or
            file_hash(out/'model-freeze.json') != seal['model_freeze_sha256']):
        raise ValueError('Prediction ledger or model freeze changed')
    freeze = json.loads((out/'model-freeze.json').read_text())
    if freeze['protocol_sha256'] != file_hash(out/'protocol.json') or freeze['harness_sha256'] != protocol['harness_sha256']:
        raise ValueError('Protocol/evaluator changed after model freeze')
    labels, label_rows = {}, []
    for cohort, path in [('new',args.labels),('prior',args.prior_labels),('produce_control',args.control_labels)]:
        if path is None:
            if cohort in protocol['truth_manifest_sha256']:
                raise ValueError('Missing frozen control labels')
            continue
        if file_hash(path) != protocol['truth_manifest_sha256'].get(cohort):
            raise ValueError('Truth manifest changed after input freeze')
        for label in read_csv(path):  # First label parsing/join occurs here, after the sealed predictions.
            identity = label.get('id',label.get('sample_id'))
            if identity in labels:
                raise ValueError('Duplicate truth ID')
            labels[identity] = label
            label_rows.append(dict(id=identity,cohort=cohort,**{k:v for k,v in label.items() if k not in ('id','sample_id')}))
    all_inputs = read_csv(out/'inputs.csv')
    if set(labels) != {r['id'] for r in all_inputs}:
        raise ValueError('Label IDs must match all frozen candidates, including exclusions')
    write_csv(out/'labels-joined-after.csv', label_rows)
    inputs = {r['id']:r for r in read_csv(out/'inference-inputs.csv')}
    predictions = [json.loads(line) for line in (out/'predictions-blind.jsonl').read_text().splitlines()]
    if len(predictions) != len(inputs) or {r['id'] for r in predictions} != set(inputs) or seal['count'] != len(inputs):
        raise ValueError('Incomplete/duplicate prediction population')
    registry = {r['name'] for r in json.loads((ROOT/'docs/experiments/grocery-catalogue/registry.json').read_text())}
    rows = []
    for prediction in predictions:
        identity = prediction['id'];item = inputs[identity];label = labels[identity]
        if prediction['sha256'] != item['sha256']:
            raise ValueError('Prediction/photo identity mismatch')
        truth, role = exact_role(label, prior=item['cohort']=='prior', control=item['cohort']=='produce_control')
        if truth not in registry|{UNKNOWN}:
            raise ValueError('Truth outside fixed catalogue')
        group = label.get('source_group') or 'prior-product:'+label.get('gtin',identity)
        row = dict(id=identity,role=role,source_group=group,view_type=label.get('view_type') or 'unclassified',
                   capture_type=label.get('capture_type',''),gtin=label.get('gtin',''),exact_truth=truth,
                   family_truth=label.get('family_truth') or label['truth'],
                   exact_sku_status=label.get('exact_sku_status','prior_development'),
                   source_url=label.get('source_url',''),image_url=label.get('image_url',''),
                   sha256=item['sha256'],notes=label.get('notes',''))
        for arm in ('before','after'):
            name = prediction[arm]['prediction']
            if name not in registry|{UNKNOWN}:
                raise ValueError('Classifier emitted a name outside the fixed catalogue')
            row[arm+'_prediction'] = name
            row[arm+'_outcome'] = outcome(truth,name)
        row['transition'] = row['before_outcome']+'->'+row['after_outcome']
        for key in ('recognition_source','recognition_reason','recognition_text','recognition_gtins','baseline_prediction'):
            row[key] = prediction['after'].get(key,'')
        # Preserve source attribution, capture and retrieval provenance for public audit.
        for key,value in label.items():
            if key not in row and key not in ('id','sample_id','truth'):
                row[key] = value
        rows.append(row)
    screening = read_csv(out/'screening.csv')
    summary = dict(schema_version=1, experiment='new-external-pixel-only-before-after',
                   generated_at=datetime.now(timezone.utc).isoformat(), executor='Codex',
                   baseline_commit=BASELINE_COMMIT, **summarize(rows),
                   screening=dict(candidates=len(all_inputs),inferred=len(rows),
                                  status_counts=dict(Counter(r['status'] for r in screening)),
                                  exclusion_reasons=dict(Counter(r['reason'] for r in screening if r['status']=='excluded'))),
                   files={name:file_hash(out/name) for name in ('protocol.json','model-freeze.json','predictions-blind.jsonl','predictions-seal.json','inputs.csv','screening.csv','labels-joined-after.csv')},
                   scope='Small selected external-photo cohort. Prior seven are development only. Alternate GTIN family matches are not exact-SKU hits. Multiple views share source groups; no independent-photo confidence intervals. Produce controls evaluate fine-class identity separately.')
    write_csv(out/'rows.csv', rows)
    write_csv(out/'source-groups.csv', summary['by_source_group'])
    summary['files']['rows.csv'] = file_hash(out/'rows.csv')
    summary['files']['source-groups.csv'] = file_hash(out/'source-groups.csv')
    write_json(out/'summary.json', summary)
    lines = ['# New external-photo before/after evaluation','',summary['scope'],'',
             '| Role | Photos / source groups | Known / unknown | Before correct / named wrong / held | After correct / named wrong / held | Formerly correct → bad |',
             '|---|---:|---:|---:|---:|---:|']
    for role,m in summary['roles'].items():
        b,a = m['before'],m['after']
        lines.append(f"| {role} | {m['n']} / {m['source_groups']} | {m['known']} / {m['unknown']} | {b['correct_names']} / {b['named_wrong']} / {b['held']} | {a['correct_names']} / {a['named_wrong']} / {a['held']} | {m['formerly_correct_to_bad']} |")
    lines += ['', 'Known recall = exact correct names / known photos. Unknown false-accept rate = named predictions / unknown photos. Held known photos remain failures of naming; held unknown photos are correct rejections. See summary.json for both denominators, all transitions, views and source groups.',
              '', 'Dedup is conservative exact/pixel and whole/background-trimmed perceptual screening, not proof that two surviving photos show different physical packages. Exclusions remain in screening.csv; GTIN/source/session grouping is separate from photo counts. No raw external image bytes are redistributed here.']
    (out/'summary.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary['roles'], indent=2))


def audit(out):
    out = out.resolve();check_inputs(out)
    summary = json.loads((out/'summary.json').read_text())
    for name, sha in summary['files'].items():
        if file_hash(out/name) != sha:
            raise ValueError('Published file hash mismatch: '+name)
    rebuilt = summarize(read_csv(out/'rows.csv'))
    for key in rebuilt:
        if rebuilt[key] != summary[key]:
            raise ValueError('Summary does not reduce from published rows: '+key)
    print(json.dumps(dict(audit='passed',photos=sum(r['n'] for r in summary['roles'].values()),
                         roles={k:v['n'] for k,v in summary['roles'].items()}),indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('prepare')
    for name in ('blind','labels','prior-blind','prior-labels','archive','out'):
        p.add_argument('--'+name,type=Path,required=True)
    for name in ('control-blind','control-labels','source-protocol','reference-cache'):
        p.add_argument('--'+name,type=Path)
    p = subs.add_parser('infer');p.add_argument('--out',type=Path,required=True);p.add_argument('--weights',type=Path,required=True)
    p.add_argument('--tessdata',type=Path,default=Path('/usr/share/tesseract-ocr/5/tessdata'))
    p = subs.add_parser('score')
    for name in ('out','labels','prior-labels'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--control-labels',type=Path)
    p = subs.add_parser('audit');p.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    if args.command == 'audit':audit(args.out)
    else:globals()[args.command](args)


if __name__ == '__main__':
    main()
