"""Reproduce ordinary photo names or artwork decisions from original image bytes."""

import argparse
import csv
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image, ImageOps

from pickloop import registered_pack
from pickloop.grocery_catalogue import recognize_rgb


EXPERIMENTS = Path(__file__).resolve().parents[1]


def read_rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def load_rgb(data, expected):
    digest = sha256(data).hexdigest()
    if expected and digest != expected:
        raise ValueError(f'Unexpected photograph bytes for SHA-256 {expected}')
    with Image.open(BytesIO(data)) as image:
        return np.asarray(ImageOps.exif_transpose(image).convert('RGB')), digest


def replay_historical(photos):
    study = EXPERIMENTS / 'new-photos'
    paths = {row['id']: Path(row['path']).name for row in read_rows(study / 'inputs.csv')}
    for row in read_rows(study / 'rows.csv'):
        identifier = row['id']
        if not identifier.startswith('NX-'):
            continue
        rgb, digest = load_rgb((photos / paths[identifier]).read_bytes(), row['sha256'])
        result = recognize_rgb(rgb)
        yield dict(id=identifier, sha256=digest, gtin=row['gtin'], truth=row['exact_truth'],
                   prediction=result['prediction'], reason=result['photo_name_reason'],
                   template=(result['registered_pack'] or {}).get('template'),
                   order=result['confirmed_order_sku'])


def replay_artwork(dataset):
    recall = EXPERIMENTS / 'registered-recall'
    targets = set(registered_pack.REGISTERED_GTINS.values())
    enrolled = {template['id'] for template in registered_pack.gallery()}
    with ZipFile(dataset) as archive:
        root = archive.namelist()[0]
        for member in sorted(archive.namelist()):
            path = Path(member)
            if ('/dataset/train/Packages/Juice/' in member and path.suffix.lower() == '.jpg'
                    and path.stem not in enrolled):
                yield artwork_row(archive.read(member), None, 'unenrolled-training',
                                  path.stem, path.parent.name, targets)
        for cohort in ('legacy-validation', 'archive'):
            for row in read_rows(recall / (cohort + '-labels.csv')):
                data = archive.read(root + 'dataset/' + row['native_id'])
                yield artwork_row(data, row['sha256'], cohort, row['id'], row['truth'], targets)


def artwork_row(data, expected, cohort, identifier, truth, targets):
    rgb, digest = load_rgb(data, expected)
    decision = registered_pack.decide(registered_pack.candidates(rgb))
    prediction = decision['product'] if decision and decision['status'] == 'matched' else None
    return dict(cohort=cohort, id=identifier, sha256=digest, truth=truth if truth in targets else None,
                prediction=prediction, decision=decision)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--historical-photos', type=Path, help='directory of the original blind NX files')
    modes.add_argument('--dataset-zip', type=Path, help='pinned GroceryStoreDataset zip')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    rows = (replay_historical(args.historical_photos) if args.historical_photos
            else replay_artwork(args.dataset_zip))
    with args.out.open('w', encoding='utf-8') as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
