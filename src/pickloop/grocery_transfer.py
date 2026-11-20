"""Fit, evaluate or use the offline real-package classifier on an individual image."""
import argparse
import csv
import hashlib
import json
from itertools import islice
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import torch

from .grocery_evaluation import ORIGIN, PREFIX, REGISTERED, REVISION, SPLIT_SHA256
from .photo_evaluation import UNKNOWN, crop_pixels, metrics, outcome, sha256, write_csv, write_json
from .product_recognition import (NAMES, SCHEMA, WEIGHTS_SHA256, PhotoEncoder, ProductRecognizer,
                                  development_product, fit_head, product_margins, validation_boundary)


def records(archive, split):
    if split == 'catalogue':
        rows = csv.DictReader(archive.read(PREFIX + 'classes.csv').decode().splitlines())
        for row in rows:
            path = row['Iconic Image Path (str)'].lstrip('/')
            if '/Packages/' in path:
                yield path, int(row['Class ID (int)'])
        return
    rows = csv.reader(archive.read(PREFIX + split + '.txt').decode().splitlines())
    for path, fine, _ in rows:
        path, class_id = path.strip(), int(fine)
        if path.split('/')[0] != split:
            raise ValueError(f'unexpected split: {path}')
        if split in ('train', 'val') and ('/Packages/' not in path or not development_product(class_id)):
            continue
        yield path, class_id


def extract(archive, split, encoder, seen):
    inputs = iter(records(archive, split))
    rows, features = [], []
    while batch := list(islice(inputs, 16)):
        images = []
        for path, class_id in batch:
            data = archive.read(PREFIX + path)
            digest = sha256(data)
            if digest in seen:
                raise ValueError(f'repeated image bytes: {path}')
            seen.add(digest)
            image, _ = crop_pixels(data, {})
            product = path.split('/')[-2]
            truth = REGISTERED.get(class_id, UNKNOWN)
            if truth != UNKNOWN and truth != product:
                raise ValueError(f'conflicting SKU for {path}')
            rows.append(dict(split=split, path=path, class_id=class_id, product=product, sha256=digest, truth=truth))
            images.append(image)
        features.append(encoder.encode(images))
    if not rows:
        raise ValueError(f'empty split {split}')
    return rows, np.concatenate(features)


def score_rows(rows, recognizer, vectors):
    predictions, margins = recognizer.predict(vectors)
    return [{**row, 'prediction': pred, 'outcome': outcome(row['truth'], pred), 'margin': float(score)}
            for row, pred, score in zip(rows, predictions, margins, strict=True)]


def summarize(rows):
    return metrics((row['truth'], row['prediction']) for row in rows)


def input_digest(rows):
    fingerprint = hashlib.sha256()
    for row in rows:
        fingerprint.update(f"{row['path']}\t{row['sha256']}\n".encode())
    return fingerprint.hexdigest()


def fit(archive, encoder, dest):
    seen = set()
    train, vectors = extract(archive, 'train', encoder, seen)
    val, calibration = extract(archive, 'val', encoder, seen)
    classes = [*NAMES, UNKNOWN]
    weights, intercept = fit_head(vectors, [classes.index(row['truth']) for row in train])
    _, margins = product_margins(calibration @ weights + intercept)
    cutoff = validation_boundary([m for row, m in zip(val, margins, strict=True) if row['truth'] == UNKNOWN])
    head = dict(schema=SCHEMA, classes=classes, weights_sha256=WEIGHTS_SHA256, slopes=weights.tolist(),
                intercept=intercept.tolist(), boundary=cutoff, source_revision=REVISION,
                training_inputs_sha256=input_digest(train), calibration_inputs_sha256=input_digest(val))
    scored_val = score_rows(val, ProductRecognizer(head), calibration)
    dest.mkdir(parents=True, exist_ok=True)
    write_csv(dest / 'development-inputs.csv', train + val)
    write_csv(dest / 'validation.csv', scored_val)
    write_json(dest / 'model.json', head)
    return dict(train=len(train), validation=summarize(scored_val), boundary=cutoff)


def evaluate(archive, encoder, fit_dir, dest):
    head_path = fit_dir / 'model.json'
    head = json.loads(head_path.read_text())
    recognizer = ProductRecognizer(head)
    with (fit_dir / 'development-inputs.csv').open(newline='') as f:
        dev = list(csv.DictReader(f))
    for split, key in [('train', 'training_inputs_sha256'), ('val', 'calibration_inputs_sha256')]:
        if input_digest([r for r in dev if r['split'] == split]) != head[key]:
            raise ValueError('development inventory does not match the frozen model')
    with (fit_dir / 'validation.csv').open(newline='') as f:
        validation = list(csv.DictReader(f))
    if input_digest(validation) != head['calibration_inputs_sha256']:
        raise ValueError('validation results do not match calibration inputs')
    seen = {row['sha256'] for row in dev}
    rows, vectors = extract(archive, 'test', encoder, seen)
    scored = score_rows(rows, recognizer, vectors)
    cat, cat_vectors = extract(archive, 'catalogue', encoder, seen)
    catalogue = score_rows(cat, recognizer, cat_vectors)
    cartons = [r for r in scored if '/Packages/' in r['path']]
    produce = [r for r in scored if '/Packages/' not in r['path']]
    if input_digest(cartons) != SPLIT_SHA256['test'] or input_digest(produce) != SPLIT_SHA256['test_produce']:
        raise ValueError('test photos differ from the earlier comparison')
    withheld = [r for r in cartons if not development_product(r['class_id'])]
    report = dict(source=ORIGIN + '/tree/' + REVISION, revision=REVISION, encoder_sha256=WEIGHTS_SHA256,
                  head_sha256=sha256(head_path.read_bytes()), boundary=head['boundary'], distinct_image_hashes=len(seen),
                  fit_photos=sum(r['split'] == 'train' for r in dev), validation=summarize(validation),
                  revisited_cartons=summarize(cartons), revisited_produce=summarize(produce),
                  reserved_carton_ids=sorted({r['class_id'] for r in withheld}), reserved_cartons=summarize(withheld),
                  new_catalogue=summarize(catalogue), catalogue_input_sha256=input_digest(catalogue))
    dest.mkdir(parents=True, exist_ok=True)
    write_csv(dest / 'predictions.csv', scored + catalogue)
    write_json(dest / 'summary.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('fit', 'evaluate', 'predict'):
        command = commands.add_parser(name)
        command.add_argument('--weights', type=Path, required=True, help='the pinned torchvision ResNet-18 .pth file')
        if name == 'predict':
            command.add_argument('--head', type=Path, required=True)
            command.add_argument('image', type=Path)
        else:
            command.add_argument('--archive', type=Path, required=True)
            command.add_argument('--out', type=Path, required=True)
            if name == 'evaluate':
                command.add_argument('--fit-dir', type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(min(torch.get_num_threads(), 4))
    encoder = PhotoEncoder(args.weights)
    if args.command == 'predict':
        classifier = ProductRecognizer(json.loads(args.head.read_text()))
        image, _ = crop_pixels(args.image.read_bytes(), {})
        prediction, margin = classifier.predict(encoder.encode([image]))
        report = dict(prediction=prediction[0], margin=float(margin[0]), boundary=classifier.boundary)
    else:
        with ZipFile(args.archive) as archive:
            report = (fit(archive, encoder, args.out) if args.command == 'fit'
                      else evaluate(archive, encoder, args.fit_dir, args.out))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
