"""Build compact printed-region features from the enrolled original train photographs."""
import argparse
import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from build_orange_side import ROOT, UNIT


def image(row, directory):
    payload = (directory / row['file']).read_bytes()
    if sha256(payload).hexdigest() != row['sha256']:
        raise ValueError(f"Checksum mismatch for {row['file']}")
    with Image.open(BytesIO(payload)) as original:
        return np.asarray(ImageOps.exif_transpose(original).convert('RGB'))


def compact(array):
    return base64.b64encode(np.clip(np.rint(array), -127, 127).astype(np.int8).tobytes()).decode()


def header(row, directory):
    inverse = cv2.getPerspectiveTransform(UNIT, np.float32(row['corners']))
    corners = cv2.perspectiveTransform(np.float32(row['crop'])[None], inverse)[0]
    transform = cv2.getPerspectiveTransform(corners, UNIT * np.float32([55, 18]))
    patch = cv2.warpPerspective(image(row, directory), transform, (56, 19))
    # Same sparse sampling lattice as the worker. Preserve vertical contrast
    # to distinguish the short third printed line from two long yellow lines.
    yy, xx = np.mgrid[:19, :12]
    y, x = yy / 18 * 17.99, (xx + .5) / 12 * 54.99
    iy, ix = np.floor(y).astype(int), np.floor(x).astype(int)
    dx, dy = (x - ix)[:, :, None], (y - iy)[:, :, None]
    rgb = ((1 - dy) * ((1 - dx) * patch[iy, ix] + dx * patch[iy, ix+1]) +
           dy * ((1 - dx) * patch[iy+1, ix] + dx * patch[iy+1, ix+1]))
    r, g, b = rgb.transpose(2, 0, 1)

    def highpass(channel):
        neighbors = channel[np.maximum(0, yy-2), xx] + channel[np.minimum(18, yy+2), xx]
        return compact(channel - neighbors/2)

    return dict(grey=highpass(.299*r + .587*g + .114*b), yellow=highpass(np.minimum(r, g)-b))


def front(row, directory):
    transform = cv2.getPerspectiveTransform(np.float32(row['corners']), UNIT * np.float32([96, 240]))
    aligned = cv2.warpPerspective(image(row, directory), transform, (96, 240))
    result = []
    for box in row['patches']:
        x, y, right, bottom = box
        gray = cv2.cvtColor(aligned[y:bottom, x:right].astype('f'), cv2.COLOR_RGB2GRAY)
        reduced = cv2.resize(gray, (28, 9), interpolation=cv2.INTER_AREA)
        reduced -= cv2.GaussianBlur(reduced, (0, 0), 1.5)
        result.append(dict(box=box, pattern=compact(126 * reduced / max(1, np.max(abs(reduced))))))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('originals', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'web/data/orange-nutrition.json')
    args = parser.parse_args()
    records = json.loads((ROOT / 'docs/experiments/orange-side/nutrition-enrollment.json').read_text())
    output = dict(version=1, header=header(records['header'], args.originals),
                  fronts={row['sha256']: front(row, args.originals) for row in records['fronts']})
    args.output.write_text(json.dumps(output, separators=(',', ':')) + '\n')
