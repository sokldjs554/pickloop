"""Rebuild the collar luminance descriptors from hash-checked training originals."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import cv2
import numpy as np


def build(manifest, directory):
    if len({r['sha256'] for r in manifest['references']}) != len(manifest['references']):
        raise ValueError('Each collar source must be a distinct photograph')
    grid = np.float32([(x, y) for y in np.linspace(-.55, 1.32, 11)
                      for x in np.linspace(-1.2, 1.2, 13)])
    references = []
    for source in manifest['references']:
        raw = (directory/source['file']).read_bytes()
        if sha256(raw).hexdigest() != source['sha256']:
            raise ValueError(f"Source changed: {source['file']}")
        bgr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if max(bgr.shape[:2]) != manifest['coordinate_long_edge']:
            raise ValueError(f"Registration image dimensions differ: {source['file']}")
        rgb = cv2.blur(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), (3, 3)).astype(np.float32)
        top = np.asarray(source['top'])
        seam = np.float32(source['bottom']) - top
        tangent = seam[::-1] * [1, -1]
        xy = np.float32(top + grid @ np.array([tangent, seam]))
        patch = cv2.remap(rgb, xy[:,0,None], xy[:,1,None], cv2.INTER_LINEAR)[:,0]
        luminance = np.rint(patch) @ [.25, .5, .25]
        references.append(dict(sha256=source['sha256'], grid=luminance.tolist()))
    return dict(version=1, gtin=manifest['gtin'], logoSources=manifest['logoSources'],
                references=references)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('sources', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    gallery = build(json.loads(args.manifest.read_text()), args.sources)
    args.output.write_text(json.dumps(gallery, separators=(',', ':'))+'\n')
