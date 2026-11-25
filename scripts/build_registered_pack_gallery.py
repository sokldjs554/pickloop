"""Build the barcode-free artwork gallery from hash-checked, explicitly enrolled originals."""
import argparse
import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image, ImageOps

from pickloop.registered_pack import orb

ROOT = Path(__file__).resolve().parents[1]


def rectify(image, row):
    if row.get("rotate") == 90:
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    h, w = image.shape[:2]
    if row["corners"]:
        corners = np.float32(row["corners"]) * (max(w, h) / row["coordinate_long_edge"])
    else:
        corners = np.float32([(0, 0), (w-1, 0), (w-1, h-1), (0, h-1)])
    width = np.linalg.norm(corners[1] - corners[0])
    height = np.linalg.norm(corners[2] - corners[1])
    scale = 580 / max(width, height)
    width, height = round(width*scale), round(height*scale)
    output = np.float32([(0, 0), (width-1, 0), (width-1, height-1), (0, height-1)])
    return cv2.warpPerspective(image, cv2.getPerspectiveTransform(corners, output), (width, height))


def build(rows, sources, archive):
    templates = []
    detector = orb()
    for row in rows:
        if row['source'].startswith('train/'):
            item, = (p for p in archive.namelist() if p.endswith('/dataset/'+row['source']))
            data = archive.read(item)
        else:
            data = sources[row['id']].read_bytes()
        if sha256(data).hexdigest() != row['sha256']:
            raise ValueError(f"reference checksum mismatch for {row['id']}")
        with Image.open(BytesIO(data)) as opened:
            oriented = ImageOps.exif_transpose(opened).convert('RGBA')
            white = Image.new('RGBA', oriented.size, 'white')
            white.alpha_composite(oriented)
            face = rectify(np.asarray(white.convert('RGB')), row)
        keys, descriptors = detector.detectAndCompute(cv2.cvtColor(face, cv2.COLOR_RGB2GRAY), None)
        h, w = face.shape[:2]
        zones = {'front': [[.08,.08,.92,.50],[.02,.55,.98,.98]],
                 'ingredients': [[.01,.01,.95,.47],[.01,.50,.99,.99]],
                 'nutrition': [[.01,.01,.92,.25],[.74,.29,.99,.85],[.01,.68,.65,.99]]}[row['view']]
        appearance = cv2.resize(face,(12,32),interpolation=cv2.INTER_AREA)
        templates.append(dict(appearance=base64.b64encode(appearance.tobytes()).decode('ascii'), id=row['id'], gtin=row['gtin'], view=row['view'], width=w, height=h,
                              zones=[[round(v*s) for v,s in zip(z,(w,h,w,h))] for z in zones],
                              points=[[round(v,1) for v in key.pt] for key in keys],
                              descriptors=base64.b64encode(descriptors.tobytes()).decode('ascii')))
    return {'version':1,'templates':templates}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('originals', type=Path, nargs='+', help='Directories containing the original ID-named photos')
    args = parser.parse_args()
    files = {p.stem: p for root in args.originals for p in root.iterdir() if p.is_file()}
    rows = json.loads((ROOT/'docs/experiments/registered-photo-recall/enrollment.json').read_text())
    with ZipFile(args.archive) as archive:
        gallery = build(rows, files, archive)
    encoded = json.dumps(gallery, separators=(',',':')).encode('ascii')
    (ROOT/'web/data/registered-pack-gallery.json').write_bytes(encoded)
    np.savez_compressed(ROOT/'src/pickloop/data/registered_pack.npz', gallery=np.frombuffer(encoded,np.uint8))
    print(sha256(encoded).hexdigest(), len(encoded), 'bytes')
