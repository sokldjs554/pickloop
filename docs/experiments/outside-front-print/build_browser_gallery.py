"""Rebuild the four frozen family templates from privately retrieved source photograph bytes."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import cv2
import numpy as np

from family_reader import features, matte_crop, pixels

HERE = Path(__file__).resolve().parent
INCLUDED = {'P0fe958e10359eea', 'Pba45a6307d0e240', 'FI97', 'FAM-65e455524bd717'}
EXPECTED = 'c42008bd80f58bdec6a14008cfe9099b6bd0625132a8c2496f975b8aa98268d3'


def checked(raw, expected):
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f'Source changed; expected {expected}')
    return raw


def fetch_sources(directory):
    directory.mkdir(exist_ok=True, parents=True)
    lock = json.loads((HERE / 'family-freeze.json').read_text())
    papers = {}
    for r in json.loads((HERE / 'family-registrations.json').read_text()):
        if r['id'] not in INCLUDED:
            continue
        out = directory / r['id']
        if out.exists():
            checked(out.read_bytes(), r['sha256'])
            continue
        if r['xref']:
            import fitz
            if r['url'] not in papers:
                with urlopen(r['url'], timeout=90) as response:
                    pdf = checked(response.read(), lock['source_pdfs'][r['url']])
                papers[r['url']] = fitz.open(stream=pdf, filetype='pdf')
            raw = papers[r['url']].extract_image(r['xref'])['image']
        else:
            with urlopen(r['url'], timeout=45) as response:
                raw = response.read()
        out.write_bytes(checked(raw, r['sha256']))
    for paper in papers.values():
        paper.close()


def build(directory, output):
    references = []
    for r in json.loads((HERE / 'family-registrations.json').read_text()):
        if r['id'] not in INCLUDED:
            continue
        source = directory / r['id']
        checked(source.read_bytes(), r['sha256'])
        image = pixels(source)
        if r['matte']:
            image = matte_crop(image)
        desc = features(image, 600)
        height, width = desc.gray.shape
        patches = []
        for a, b, c, d in r['zones']:
            x, y, right, bottom = round(a*width), round(b*height), round(c*width), round(d*height)
            dx, dy = right-x, bottom-y
            scale = min(1., 80/dx, 24/dy)
            size = max(12, round(dx*scale)), max(8, round(dy*scale))
            gray = cv2.resize(desc.gray[y:bottom, x:right], size, interpolation=cv2.INTER_AREA).astype(np.float32)
            contrast = gray - cv2.GaussianBlur(gray, (0,0), 2)
            packed = np.rint(127 * contrast / np.max(abs(contrast))).astype(np.int8)
            patches.append(dict(box=[x,y,right,bottom], size=size, contrast=base64.b64encode(packed.tobytes()).decode()))
        references.append(dict(id=r['id'], family=r['family'], sha256=r['sha256'], width=width, height=height,
                               points=np.round(desc.points,3).tolist(),
                               descriptors=base64.b64encode(desc.descriptors.tobytes()).decode(), patches=patches))
    if {r['id'] for r in references} != INCLUDED:
        raise ValueError('Incomplete gallery')
    raw = (json.dumps(dict(version=1, templates=references), separators=(',',':'))+'\n').encode()
    output.write_bytes(checked(raw, EXPECTED))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_directory', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--fetch', action='store_true', help='Download source documents and extract pinned PDF objects')
    args = parser.parse_args()
    if args.fetch:
        fetch_sources(args.source_directory)
    build(args.source_directory, args.output)
