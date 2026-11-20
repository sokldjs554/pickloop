"""Register selected train panels or evaluate a frozen panel gallery."""
import argparse
import csv
from functools import partial
import json
from multiprocessing import Pool
from pathlib import Path
from zipfile import ZipFile

import cv2
import numpy as np

from pickloop.carton_matcher import CartonMatcher
from pickloop.grocery_evaluation import PREFIX, REGISTERED, REVISION, SPLIT_SHA256
from pickloop.grocery_transfer import input_digest, records
from pickloop.photo_evaluation import UNKNOWN, crop_pixels, metrics, outcome, sha256, write_csv, write_json
from pickloop.product_recognition import development_product

ROOT = Path(__file__).resolve().parents[1]
REGIONS = ROOT / 'configs/bravo-template-regions.json'


def make_gallery(archive, out):
    regions = []
    sources = []
    annotations = json.loads(REGIONS.read_text())['templates']
    for name, panels in annotations.items():
        for number, corners in panels.items():
            path = f'train/Packages/Juice/{name}/{name}_{number}.jpg'
            data = archive.read(PREFIX + path)
            rgb, _ = crop_pixels(data, {})
            h, w = rgb.shape[:2]
            poly = np.float32(corners) * np.float32([w / 220, h / 220])
            regions.append((name, rgb, poly))
            sources.append(dict(path=path, sha256=sha256(data), product=name))
    matcher = CartonMatcher.register(regions)
    matcher.save(out / 'gallery.npz')
    for row, template in zip(sources, matcher.templates, strict=True):
        row['keypoints'] = len(template.points)
    write_csv(out / 'templates.csv', sources)
    return sources


def score_chunk(tasks, archive_path, model_path):
    cv2.setNumThreads(1)
    matcher = CartonMatcher.load(model_path)
    output = []
    with ZipFile(archive_path) as archive:
        for group, path, class_id in tasks:
            data = archive.read(PREFIX + path)
            rgb, _ = crop_pixels(data, {})
            pred = matcher.predict(rgb)
            truth = REGISTERED.get(class_id, UNKNOWN)
            output.append(dict(partition=group, path=path, class_id=class_id, sha256=sha256(data),
                               truth=truth, **pred, outcome=outcome(truth, pred['prediction'])))
    return output


def score(tasks, archive_path, model_path, workers):
    chunks = [tasks[i:i + 48] for i in range(0, len(tasks), 48)]
    run = partial(score_chunk, archive_path=archive_path, model_path=model_path)
    with Pool(workers) as pool:
        return [r for chunk in pool.imap(run, chunks) for r in chunk]


def counts(rows):
    return metrics((r['truth'], r['prediction']) for r in rows)


def load_csv(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('register', 'evaluate'))
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--workers', type=int, default=4)
    args = p.parse_args()
    if args.workers < 1:
        p.error('--workers must be positive')
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    model = out / 'gallery.npz'
    cv2.setNumThreads(1)
    with ZipFile(args.archive) as archive:
        if args.command == 'register':
            templates = make_gallery(archive, out)
            paths = {t['path'] for t in templates}
            tasks = [('unused_train_known', path, n) for path, n in records(archive, 'train')
                     if n in REGISTERED and path not in paths]
            tasks += [('validation_cartons', path, n) for path, n in records(archive, 'val')]
        else:
            templates = load_csv(out / 'templates.csv')
            tasks = [('test_cartons' if '/Packages/' in path else 'test_produce', path, n)
                     for path, n in records(archive, 'test')]
            tasks += [('catalogue', path, n) for path, n in records(archive, 'catalogue')]
            tasks += [('fresh_validation_produce', path.strip(), int(n)) for path, n, _ in
                      csv.reader(archive.read(PREFIX + 'val.txt').decode().splitlines())
                      if '/Packages/' not in path]

    scored = score(tasks, args.archive, model, args.workers)
    groups = {group: [r for r in scored if r['partition'] == group] for group in dict.fromkeys(t[0] for t in tasks)}
    previous = templates if args.command == 'register' else templates + load_csv(out / 'development.csv')
    fingerprints = [r['sha256'] for r in previous + scored]
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError('overlapping photo bytes across the gallery, development or evaluation')
    if args.command == 'evaluate':
        if (input_digest(groups['test_cartons']) != SPLIT_SHA256['test']
                or input_digest(groups['test_produce']) != SPLIT_SHA256['test_produce']):
            raise ValueError('historical comparison images differ')
        groups['reserved_cartons'] = [r for r in groups['test_cartons'] if not development_product(r['class_id'])]
    report = dict(revision=REVISION, gallery_sha256=sha256(model.read_bytes()), templates=len(templates),
                  regions_sha256=sha256(REGIONS.read_bytes()), distinct_image_hashes=len(fingerprints),
                  partitions={k: counts(v) for k, v in groups.items()})
    filename = 'development' if args.command == 'register' else 'predictions'
    write_csv(out / f'{filename}.csv', scored)
    write_json(out / ('development.json' if args.command == 'register' else 'summary.json'), report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
