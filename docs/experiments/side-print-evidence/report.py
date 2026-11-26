"""Rebuild the side-photo comparison from the two complete browser ledgers."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
WEB = STUDIES.parent.parent / 'web'


def ledger(path):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    index = {row['id']: row for row in rows}
    if len(index) != 118 or len(index) != len(rows):
        raise ValueError(f'expected 118 distinct browser records in {path}')
    return index


def compare():
    before = ledger(STUDIES / 'side-panel-retry/browser.jsonl')
    after = ledger(HERE / 'browser.jsonl')
    if before.keys() != after.keys() or any(
        entry['sha256'] != before[key]['sha256'] for key, entry in after.items()
    ):
        raise ValueError('unpaired browser records')
    for path, digest in json.loads((HERE / 'browser-freeze.json').read_text()).items():
        if hashlib.sha256((WEB / path).read_bytes()).hexdigest() != digest:
            raise ValueError(f'expected the recorded browser version for {path}')
    output = io.StringIO()
    writer = csv.DictWriter(output, ('id', 'sha256', 'truth', 'before_product', 'after_product',
                                     'order', 'after_display', 'image_url'), lineterminator='\n')
    writer.writeheader()
    with (STUDIES / 'registered-recall/archive-labels.csv').open(newline='') as source:
        for row in csv.DictReader(source):
            if row['truth'] == 'UNKNOWN' or row['view'] != 'side visible':
                continue
            key = row['id']
            if row['sha256'] != after[key]['sha256']:
                raise ValueError(f'label checksum mismatch for {key}')
            writer.writerow(dict(id=key, sha256=row['sha256'], truth=row['truth'],
                                 before_product=before[key]['product'], after_product=after[key]['product'],
                                 order=after[key]['barcode_order'], after_display=after[key]['display'],
                                 image_url=row['image_url']))
    return output.getvalue()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = compare()
    path = HERE / 'side-photos.csv'
    if args.check:
        if result != path.read_text():
            raise SystemExit('side-photos.csv differs from the paired browser records')
    else:
        path.write_text(result)
