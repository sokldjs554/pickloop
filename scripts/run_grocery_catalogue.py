"""Fit without official validation/test data, or score those photos with a saved catalogue."""
import argparse
from contextlib import ExitStack
import csv
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from catalogue_outside_source import MANIFEST_SHA256
from pickloop.catalogue_features import FEATURE_VERSION, REVISION, WEIGHTS_SHA
from pickloop.catalogue_model import CatalogueHead, calibrate
from pickloop.grocery_catalogue import BRAVO_GALLERY_SHA256, resolve_decision
from pickloop.grocery_evaluation import PREFIX
from pickloop.photo_evaluation import crop_pixels, write_csv, write_json


def cached(directory, split):
    with (directory / f'{split}.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    hashes = [r['sha256'] for r in rows]
    with np.load(directory / f'{split}.npz', allow_pickle=False) as data:
        if (hashes != data['hashes'].tolist() or len(set(hashes)) != len(hashes)
                or data['feature_version'].item() != FEATURE_VERSION or len(rows) != len(data['vectors'])):
            raise ValueError(f'inconsistent cached features: {split}')
        return rows, data['vectors']


def development_mask(rows, class_count):
    ids = np.array([int(r['class_id']) for r in rows])
    mask = np.zeros(len(rows), dtype=bool)
    for n in range(class_count):
        order = sorted(np.flatnonzero(ids == n), key=lambda i: rows[i]['path'])
        count = max(2, round(.2 * len(order)))
        if len(order) <= count:
            raise ValueError(f'insufficient training views for class {n}')
        seed = int.from_bytes(sha256(f'pickloop-full-catalogue-{n}'.encode()).digest()[:4], 'big')
        start = seed % (len(order) - count + 1)
        mask[order[start:start + count]] = True
    return mask


def fit(cache, out, head_path):
    registry = json.loads((cache / 'registry.json').read_text())
    names = [r['name'] for r in registry]
    train, x = cached(cache, 'train')
    external, outside = cached(cache, 'outside_calibration')
    if {r['sha256'] for r in train} & {r['sha256'] for r in external}:
        raise ValueError('overlap with calibration photos')
    mask = development_mask(train, len(names))
    ids = np.array([int(r['class_id']) for r in train])
    truth = [r['truth'] for r, hold in zip(train, mask) if hold]
    if any(r['truth'] != names[int(r['class_id'])] for r in train):
        raise ValueError('registry mismatch in fit data')
    options = []
    best, selected = None, None
    for ridge in (.1, 1., 4.):
        head = CatalogueHead.fit(names, x[~mask], ids[~mask], ridge)
        linear, supports = head.evidence(x[mask])
        for weight in (0., .35, .8):
            head.neighbour_weight = weight
            decisions = head.decisions(linear, supports)
            good = np.array([r['top1'] == t for r, t in zip(decisions, truth, strict=True)])
            accuracy = float(np.mean([good[ids[mask] == n].mean() for n in range(len(names))]))
            options.append(dict(ridge=ridge, neighbour_weight=weight, macro_accuracy=accuracy, correct=int(good.sum())))
            key = (accuracy, int(good.sum()), -weight)
            if best is None or key > best:
                best, selected = key, (ridge, weight)
    ridge, weight = selected
    head = CatalogueHead.fit(names, x[~mask], ids[~mask], ridge)
    head.neighbour_weight = weight
    known_scores = head.predict(x[mask])
    outside_scores = head.predict(outside)
    gate = calibrate(known_scores, truth, outside_scores)
    head.min_support, head.min_score, head.min_margin = (gate[k] for k in ('support', 'score', 'margin'))
    head_path.parent.mkdir(parents=True, exist_ok=True)
    head.save(head_path)
    head = CatalogueHead.load(head_path)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / 'registry.json', registry)
    write_csv(out / 'training.csv', [{**r, 'role':'development' if hold else 'fit'} for r, hold in zip(train, mask)])
    development = [dict(row, **d) for row, d in zip([r for r, hold in zip(train, mask) if hold], head.predict(x[mask]), strict=True)]
    development += [dict(row, **d) for row, d in zip(external, head.predict(outside), strict=True)]
    write_csv(out / 'development.csv', development)
    protocol = dict(feature_version=FEATURE_VERSION, checkpoint_revision=REVISION, checkpoint_sha256=WEIGHTS_SHA,
                    catalogue_head_sha256=sha256(head_path.read_bytes()).hexdigest(),
                    fitting=int((~mask).sum()), known_development=int(mask.sum()), outside_calibration=len(external),
                    ridge=ridge, neighbour_weight=weight, candidates=options, gate=gate)
    write_json(out / 'fit.json', protocol)
    return protocol


def verified_pixels(row, archive, outside_root, outside_hashes):
    path = row['path']
    if row['split'] == 'outside_test':
        if outside_hashes.get(path) != row['sha256']:
            raise ValueError(f'outside test image differs from the pinned manifest: {path}')
        data = (outside_root / path).read_bytes()
    else:
        data = archive.read(PREFIX + path)
    if sha256(data).hexdigest() != row['sha256']:
        raise ValueError(f'pixel source checksum differs from cached features: {path}')
    rgb, _ = crop_pixels(data, {})
    return rgb


def evaluate(cache, out, head_path, archive_path=None, outside_manifest=None, general_only=False):
    fit_summary = json.loads((out / 'fit.json').read_text())
    if sha256(head_path.read_bytes()).hexdigest() != fit_summary['catalogue_head_sha256']:
        raise ValueError('head differs from frozen fit')
    head = CatalogueHead.load(head_path)
    seen = set()
    for file in ('training.csv', 'development.csv'):
        with (out / file).open(newline='') as stream:
            seen.update(r['sha256'] for r in csv.DictReader(stream))
    predictions = []
    with ExitStack() as sources:
        if not general_only:
            if archive_path is None or outside_manifest is None:
                raise ValueError('Bravo verification requires --archive and --outside-manifest')
            archive = sources.enter_context(ZipFile(archive_path))
            manifest_bytes = outside_manifest.read_bytes()
            if sha256(manifest_bytes).hexdigest() != MANIFEST_SHA256:
                raise ValueError('Freiburg manifest checksum mismatch')
            outside = {r['path']: r['sha256'] for r in csv.DictReader(manifest_bytes.decode().splitlines())
                       if r['split'] == 'test'}
        for split in ('test', 'val', 'catalogue', 'outside_test'):
            rows, x = cached(cache, split)
            row_hashes = {r['sha256'] for r in rows}
            if seen & row_hashes:
                raise ValueError(f'overlap with fitting, calibration or another evaluation split: {split}')
            seen.update(row_hashes)
            for start in range(0, len(rows), 128):
                batch = rows[start:start + 128]
                for row, decision in zip(batch, head.predict(x[start:start+128]), strict=True):
                    if not general_only:
                        decision = resolve_decision(decision, lambda: verified_pixels(row, archive, outside_manifest.parent, outside))
                    predictions.append(dict(row, **decision))
    write_csv(out / 'predictions.csv', predictions)
    return {'evaluated': len(predictions), 'bravo_gallery_sha256': None if general_only else BRAVO_GALLERY_SHA256}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['fit', 'evaluate'])
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--head', type=Path, required=True)
    parser.add_argument('--archive', type=Path, help='original Grocery Store Dataset ZIP for Bravo verification')
    parser.add_argument('--outside-manifest', type=Path, help='Freiburg manifest.csv beside its original images directory')
    parser.add_argument('--general-only', action='store_true', help='reproduce the general-only evaluation format')
    args = parser.parse_args()
    if args.command == 'fit':
        result = fit(args.cache, args.out, args.head)
    else:
        result = evaluate(args.cache, args.out, args.head, args.archive, args.outside_manifest, args.general_only)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
