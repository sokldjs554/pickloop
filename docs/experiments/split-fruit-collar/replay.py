"""Replay the collar-only stress check. The production brand/geometry gates run separately in Chromium."""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import cv2

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
NODE = '''
const fs = require("node:fs");
const [source, gallery, width, height] = process.argv.slice(1);
const detect = Function(fs.readFileSync(source,"utf8")+"\\nreturn matchSplitCollar;")();
const refs = JSON.parse(fs.readFileSync(gallery,"utf8")).references;
process.stdout.write(JSON.stringify(detect(fs.readFileSync(0),Number(width),Number(height),refs)));
'''


def measure(row, path):
    if sha256(path.read_bytes()).hexdigest() != row['sha256']:
        raise ValueError(f'Changed image bytes for {row["id"]}')
    im = cv2.imread(str(path))
    h,w = im.shape[:2]
    scale = 348/max(w,h)
    small = cv2.resize(im,(round(w*scale),round(h*scale)),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_LINEAR)
    pixels = cv2.cvtColor(cv2.blur(small,(3,3)),cv2.COLOR_BGR2RGB)
    width, height = pixels.shape[1], pixels.shape[0]
    out = subprocess.check_output(['node','-e',NODE,
                  str(ROOT/'web/vendor/package-reader/split-collar.js'),
                  str(ROOT/'web/data/registered-collar.json'),str(width),str(height)],input=pixels.tobytes())
    scores = json.loads(out)
    return {**row, **{k:round(scores[k],6) if scores else None for k in ['first','second']},
            'accept':bool(scores and scores['second'] >= .88)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('photos',type=Path,help='Prior archived, public, validation and folds bytes named by ID')
    parser.add_argument('train',type=Path,help='Official red-grapefruit training JPGs named by basename')
    parser.add_argument('output',type=Path,help='New output CSV')
    args = parser.parse_args()
    with (HERE/'collar-only.csv').open() as original, args.output.open('x') as out:
        reader = csv.DictReader(original)
        writer = csv.DictWriter(out,reader.fieldnames)
        writer.writeheader()
        for row in reader:
            directory = args.train if row['group']=='red-only-train-challenge' else args.photos
            writer.writerow(measure(row,directory/row['id']))
