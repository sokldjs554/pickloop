"""Repeat the two fixed protocols on the published Grocery Store Dataset photographs."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

import torch
import torch.nn.functional as F

from .photo_evaluation import (UNKNOWN, checkpoint_details, crop_pixels, metrics, outcome, prediction_row,
                               sha256, write_csv, write_json)
from .vision_model import AppearanceModel

REVISION = 'fc80ba90f803d79d0383df52c5a4ac5de99ff6fc'
ORIGIN = 'https://github.com/marcusklasson/GroceryStoreDataset'
PREFIX = f'GroceryStoreDataset-{REVISION}/dataset/'
REGISTERED = {28: 'Bravo-Apple-Juice', 29: 'Bravo-Orange-Juice'}
# Digests cover ordered paths and original JPEG bytes; ZIP timestamps/compression may vary.
SPLIT_SHA256 = {
    'train': '88b1a8808c0930fe9ccfecefc3e758332eff694472c1f7e97c208c4c2b563c86',
    'test': 'f10419ba73e615a6e06d48048d986822f007dbcc09633b12bb6d222499f64d50',
    'val': '689739382b97b647454f01ac871c3b2b05459d3e281ea6ac7e16c019ebbe27d6',
    'test_produce': '92662655fc8a3d3c29fefe28449bdaad43480cc1209aac5364489dc4fa6021b7',
}


def select_split(contents, split, group='packages'):
    categories = {'packages': {'Packages'}, 'produce': {'Fruit', 'Vegetables'}}[group]
    selected = []
    for row in csv.reader(io.StringIO(contents)):
        raw_path, fine_id, _ = (field.strip() for field in row)
        path = PurePosixPath(raw_path)
        if path.parts[0] != split:
            raise ValueError(f'unexpected split in {raw_path}')
        fine_id = int(fine_id)
        if path.parts[1] not in categories or (split == 'train' and fine_id not in REGISTERED):
            continue
        product = path.parent.name
        if fine_id in REGISTERED and REGISTERED[fine_id] != product:
            raise ValueError(f'class ID disagrees with the image path {raw_path}')
        selected.append({'path': raw_path, 'product': product, 'class_id': fine_id})
    return selected


def verified_photos(archive, split, seen, group='packages'):
    entries = select_split(archive.read(PREFIX + split + '.txt').decode(), split, group)
    digest = hashlib.sha256()
    for entry in entries:
        data = archive.read(PREFIX + entry['path'])
        file_hash = sha256(data)
        if file_hash in seen:
            raise ValueError(f'duplicate photo bytes at {entry["path"]}')
        seen.add(file_hash)
        digest.update(f'{entry["path"]}\t{file_hash}\n'.encode())
        image, _ = crop_pixels(data, {})
        height, width = image.shape[:2]
        yield {**entry, 'sha256': file_hash, 'width': width, 'height': height}, image
    digest_key = split if group == 'packages' else f'{split}_{group}'
    if digest.hexdigest() != SPLIT_SHA256[digest_key]:
        raise ValueError(f'photo paths/bytes differ from the pinned {split} set')


def register_gallery(archive, original, seen):
    gallery = AppearanceModel()
    registration = []
    embeddings = defaultdict(list)
    for metadata, image in verified_photos(archive, 'train', seen):
        vector, = original.predict([image])
        embeddings[metadata['product']].append(vector['embedding'])
        registration.append(metadata)
    # Same normalized-mean prototype rule as scripts/train_vision.py. The old
    # auxiliary classifier confidence is undefined for the new product names.
    gallery.skus = tuple(REGISTERED.values())
    gallery.prototypes = F.normalize(torch.stack([
        torch.tensor(embeddings[name]).mean(dim=0) for name in gallery.skus
    ]), dim=1)
    return gallery, registration


def grocery_report(archive_path, out):
    original = AppearanceModel()
    seen = set()
    results = []
    with ZipFile(archive_path) as archive:
        gallery, registration = register_gallery(archive, original, seen)
        for metadata, image in verified_photos(archive, 'test', seen):
            results.append(prediction_row(original, image, UNKNOWN, mode='fixed_original_AB', **metadata))
            truth = REGISTERED.get(metadata['class_id'], UNKNOWN)
            results.append(prediction_row(gallery, image, truth, mode='registered_grocery', **metadata))

    counts = Counter(row['product'] for row in registration)
    trials = {}
    for mode in ('fixed_original_AB', 'registered_grocery'):
        by_product = defaultdict(list)
        pairs = []
        for row in results:
            if row['mode'] == mode:
                pair = (row['truth'], row['prediction'])
                pairs.append(pair)
                by_product[row['product']].append(pair)
        trials[mode] = {'metrics': metrics(pairs),
                        'by_product': {k: metrics(v) for k, v in by_product.items()}}
    report = {
        'dataset': 'Grocery Store Dataset, natural smartphone photographs',
        'source': ORIGIN + '/tree/' + REVISION,
        'raw_photo_url_prefix': f'https://raw.githubusercontent.com/marcusklasson/GroceryStoreDataset/{REVISION}/dataset/',
        'revision': REVISION,
        'archive_download': f'https://codeload.github.com/marcusklasson/GroceryStoreDataset/zip/{REVISION}',
        'repository_license': ORIGIN + '/blob/' + REVISION + '/LICENSE',
        'paper': 'https://arxiv.org/abs/1901.00711',
        'ordered_path_and_file_digest_sha256': {k: SPLIT_SHA256[k] for k in ('train', 'test')},
        'checkpoint': checkpoint_details(original),
        'input': 'whole published natural photograph, EXIF-oriented RGB, production 64x64 bilinear resize',
        'registration': {'source_split': 'train', 'images_per_product': dict(counts),
                         'sku_order': gallery.skus, 'prototypes': gallery.prototypes.tolist(),
                         'rule': 'L2-normalized mean of frozen encoder embeddings per registered product'},
        'test_split': 'test', 'test_photos': len(results) // 2, 'test_product_count': len({r['class_id'] for r in results}),
        'trials': trials,
    }
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / 'registration.csv', registration)
    write_csv(out / 'predictions.csv', results)
    write_json(out / 'summary.json', report)
    return report


def conservative_cutoff(unknown_distances, inherited_threshold):
    """Bound validation unknown accepts to floor(n * 5%), including boundary ties."""
    if not unknown_distances:
        raise ValueError('calibration needs unknown examples')
    ordered = sorted(unknown_distances)
    first_excluded = ordered[len(ordered) // 20]
    return min(inherited_threshold, math.nextafter(first_excluded, -math.inf))


def calibrated_report(archive_path, out):
    original = AppearanceModel()
    seen = set()
    all_rows = []
    partitions = {}
    with ZipFile(archive_path) as archive:
        gallery, registration = register_gallery(archive, original, seen)
        for split, group, partition in [('val', 'packages', 'calibration_cartons'),
                                        ('test', 'packages', 'revisited_cartons'),
                                        ('test', 'produce', 'fresh_produce')]:
            rows = []
            for metadata, image in verified_photos(archive, split, seen, group):
                truth = REGISTERED.get(metadata['class_id'], UNKNOWN)
                rows.append(prediction_row(gallery, image, truth, partition=partition, **metadata))
            if split == 'val':
                cutoff = conservative_cutoff([r['distance'] for r in rows if r['truth'] == UNKNOWN],
                                             gallery.distance_threshold)
            for row in rows:
                row['inherited_prediction'] = row['prediction']
                if row['distance'] > cutoff:
                    row['prediction'] = UNKNOWN
                row['outcome'] = outcome(row['truth'], row['prediction'])
            partitions[partition] = {
                'products': len({r['class_id'] for r in rows}),
                'inherited': metrics((r['truth'], r['inherited_prediction']) for r in rows),
                'calibrated': metrics((r['truth'], r['prediction']) for r in rows),
            }
            all_rows.extend(rows)
    summary = {
        'protocol': 'Offline follow-up after reviewing the original 781-carton test results. '
                    'The cutoff rule and the new test population (all test fruit and vegetables) '
                    'were fixed before scoring validation and produce.',
        'source': ORIGIN + '/tree/' + REVISION, 'revision': REVISION,
        'ordered_path_and_file_digest_sha256': SPLIT_SHA256,
        'distinct_input_file_sha256_count': len(seen),
        'checkpoint': checkpoint_details(original),
        'registration_images': dict(Counter(r['product'] for r in registration)),
        'registration_skus': gallery.skus, 'registration_prototypes': gallery.prototypes.tolist(),
        'acceptance_rule': 'Keep the inherited margin and accept distances at most the smaller of '
                           'the inherited cutoff and the float immediately below sorted validation '
                           'unknown distance at zero-based index floor(n/20).',
        'max_validation_unknown_accept_rate': 0.05, 'calibrated_distance_threshold': cutoff,
        'partitions': partitions,
    }
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / 'predictions.csv', all_rows)
    write_json(out / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True, help='pinned GitHub ZIP archive')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--calibrated', action='store_true', help='run the offline follow-up threshold protocol')
    args = parser.parse_args()
    if args.calibrated:
        report = calibrated_report(args.archive, args.out)
        print(json.dumps(report['partitions'], indent=2))
        return
    report = grocery_report(args.archive, args.out)
    print(json.dumps({mode: value['metrics'] for mode, value in report['trials'].items()}, indent=2))


if __name__ == '__main__':
    main()
