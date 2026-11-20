"""Extract frozen descriptors for a single declared split; no labels are passed to the encoder."""
import argparse
import csv
import json
from contextlib import ExitStack
from itertools import islice
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from pickloop.catalogue_features import CatalogueEncoder, FEATURE_VERSION
from pickloop.grocery_evaluation import PREFIX
from pickloop.photo_evaluation import UNKNOWN, crop_pixels, sha256, write_csv


def registry(archive):
    fields = csv.DictReader(archive.read(PREFIX + 'classes.csv').decode().splitlines())
    return sorted([dict(id=int(r['Class ID (int)']), name=r['Class Name (str)'],
                        coarse=r['Coarse Class Name (str)'], group=r['Iconic Image Path (str)'].split('/')[2],
                        iconic=r['Iconic Image Path (str)'].lstrip('/')) for r in fields], key=lambda r: r['id'])


def official(archive, split):
    labels = registry(archive)
    if [r['id'] for r in labels] != list(range(81)):
        raise ValueError('unexpected catalogue registry')
    if split == 'catalogue':
        cases = [(r['iconic'], r['id']) for r in labels]
    else:
        cases = [(path.strip(), int(fine)) for path, fine, _ in
                 csv.reader(archive.read(PREFIX + split + '.txt').decode().splitlines())]
    for path, n in cases:
        if path.split('/')[-2] != labels[n]['name'] and labels[n]['name'] not in path.split('/'):
            raise ValueError(f'inconsistent official name at {path}')
        yield path, n, labels[n]['name'], archive.read(PREFIX + path)


def external(manifest, split):
    with manifest.open(newline='') as f:
        for row in csv.DictReader(f):
            if row['split'] != split.removeprefix('outside_'):
                continue
            data = (manifest.parent / row['path']).read_bytes()
            if sha256(data) != row['sha256']:
                raise ValueError(f"external photo bytes changed: {row['path']}")
            yield row['path'], -1, UNKNOWN, data


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path)
    p.add_argument('--outside-manifest', type=Path)
    p.add_argument('--weights', type=Path)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('splits', nargs='+', choices=['train','val','test','catalogue','outside_calibration','outside_test'])
    args = p.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    encoder = CatalogueEncoder(args.weights)
    with ExitStack() as stack:
        archive = stack.enter_context(ZipFile(args.archive)) if args.archive else None
        for split in args.splits:
            if split.startswith('outside_'):
                source = external(args.outside_manifest, split)
            else:
                source = official(archive, split)
                labels = [{k:v for k,v in row.items() if k != 'iconic'} for row in registry(archive)]
                (args.cache / 'registry.json').write_text(json.dumps(labels, indent=2, ensure_ascii=False)+'\n')
            rows, batches = [], []
            while batch := list(islice(source, 12)):
                images = []
                for path, n, truth, data in batch:
                    rgb, _ = crop_pixels(data, {})
                    images.append(rgb)
                    rows.append(dict(split=split, path=path, sha256=sha256(data), class_id=n, truth=truth))
                batches.append(encoder.encode(images))
                if len(rows) % 600 == 0:
                    print(split, len(rows), flush=True)
            if not rows or len({r['sha256'] for r in rows}) != len(rows):
                raise ValueError(f'empty or duplicate inputs for {split}')
            write_csv(args.cache / f'{split}.csv', rows)
            np.savez(args.cache / f'{split}.npz', vectors=np.vstack(batches), feature_version=FEATURE_VERSION,
                     hashes=[r['sha256'] for r in rows])
            print('complete', split, len(rows), flush=True)


if __name__ == '__main__':
    main()
