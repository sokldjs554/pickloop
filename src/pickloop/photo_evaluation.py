"""Score manually labeled photos with the shipping crop recognizer."""
import argparse
import csv
import hashlib
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .vision_model import AppearanceModel, KNOWN_SKUS, MODEL_ROOT

UNKNOWN = 'UNKNOWN'
BOUNDS = ('x0', 'y0', 'x1', 'y1')
CONDITIONS = ('session', 'item_id', 'view', 'lighting', 'occlusion')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def outcome(truth, prediction):
    if truth == UNKNOWN:
        return 'unknown_rejected' if prediction == UNKNOWN else 'unknown_false_accepts'
    if prediction == UNKNOWN:
        return 'known_rejected'
    return 'known_correct' if truth == prediction else 'known_wrong_label'


def metrics(labeled_predictions):
    counts = dict.fromkeys(('known_correct', 'known_wrong_label', 'known_rejected',
                            'unknown_false_accepts', 'unknown_rejected'), 0)
    confusion = {}
    for truth, prediction in labeled_predictions:
        counts[outcome(truth, prediction)] += 1
        by_prediction = confusion.setdefault(truth, {})
        by_prediction[prediction] = by_prediction.get(prediction, 0) + 1
    known = counts['known_correct'] + counts['known_wrong_label'] + counts['known_rejected']
    unknown = counts['unknown_rejected'] + counts['unknown_false_accepts']
    return {**counts, 'known_total': known, 'unknown_total': unknown, 'confusion': confusion,
            'known_accuracy_after_rejection': counts['known_correct'] / known if known else None,
            'unknown_false_accept_rate': counts['unknown_false_accepts'] / unknown if unknown else None}


def prediction_row(model, image, truth, **metadata):
    # Inference receives only RGB pixels; expected labels enter after prediction.
    prediction, = model.predict([image])
    return {**metadata, 'truth': truth, 'prediction': prediction['sku'],
            'outcome': outcome(truth, prediction['sku']), 'distance': prediction['distance']}


def checkpoint_details(model):
    return {'path': 'models/appearance.pt', 'sha256': sha256((MODEL_ROOT / 'appearance.pt').read_bytes()),
            'distance_threshold': model.distance_threshold, 'margin_threshold': model.margin_threshold}


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def crop_pixels(data, row):
    with Image.open(BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
    values = [row.get(column) for column in BOUNDS]
    if any(values):
        if not all(values):
            raise ValueError('crop requires all four coordinates')
        try:
            x0, y0, x1, y1 = map(int, values)
        except ValueError as error:
            raise ValueError('crop coordinates must be integers') from error
    else:
        x0, y0, x1, y1 = 0, 0, *image.size
    if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height
            and x1 - x0 >= 2 and y1 - y0 >= 2):
        raise ValueError('crop is out of bounds or smaller than two pixels')
    box = (x0, y0, x1, y1)
    return np.asarray(image.crop(box)), dict(zip(BOUNDS, box))


def evaluate_manifest(manifest, out):
    model = AppearanceModel()
    seen = set()
    results = []
    with manifest.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        if not {'path', 'truth'} <= set(reader.fieldnames or ()):
            raise ValueError('manifest requires path and truth columns')
        for index, row in enumerate(reader, 2):
            if row['truth'] not in (*KNOWN_SKUS, UNKNOWN):
                raise ValueError(f'line {index}: unknown truth label {row["truth"]!r}')
            data = (manifest.parent / row['path']).read_bytes()
            digest = sha256(data)
            if digest in seen:
                raise ValueError(f'line {index}: duplicate source photo')
            seen.add(digest)
            image, box = crop_pixels(data, row)
            conditions = {k: row.get(k, '') for k in CONDITIONS}
            results.append(prediction_row(model, image, row['truth'], path=row['path'],
                                          sha256=digest, **box, **conditions))
    if not results:
        raise ValueError('manifest contains no photos')
    summary = {'mode': 'fixed_original_AB', 'checkpoint': checkpoint_details(model),
               'manifest_sha256': sha256(manifest.read_bytes()),
               'metrics': metrics((r['truth'], r['prediction']) for r in results)}
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / 'predictions.csv', results)
    write_json(out / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    manifest = sub.add_parser('manifest', help='score local photographs of the original physical targets')
    manifest.add_argument('path', type=Path)
    manifest.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = evaluate_manifest(args.path, args.out)
    print(json.dumps(report['metrics'], ensure_ascii=False))


if __name__ == '__main__':
    main()
