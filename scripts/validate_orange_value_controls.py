"""Challenge the visible nutrition-column matcher on genuine foil photos under pose and occlusion changes."""
import argparse
import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageEnhance

from build_orange_nutrition import ROOT, UNIT


def unit(field):
    flat = field.ravel()
    return flat / max(1, np.linalg.norm(flat))


def variation(patch, mode):
    if mode == 0:
        return patch
    image = patch.copy()
    if mode == 1:
        image[:, :13] = 0
    elif mode == 2:
        image[:15, :24] = (168,102,82)
    elif mode == 3:
        image[12:29, :20] = (112,73,67)
    else:
        image[:, :9] = (224,225,225)
    return image


def accepted(patch, grey_sources, yellow_sources, roles, primary):
    r, g, b = patch.astype('f').transpose(2,0,1)
    grey = .299*r + .587*g + .114*b
    yellow = np.minimum(r,g)-b
    ends = []
    for field, ink, gap, left, right in [
        (yellow,[3,4],[1,5],2,40), (yellow,[6,7],[5,9],2,40),
        (grey,[16,17],[14,18],17,46), (grey,[20,21],[18,23],17,46),
    ]:
        profile = (field[ink].sum(0)-field[gap].sum(0))/2
        profile = cv2.GaussianBlur(profile[None],(7,1),1,borderType=cv2.BORDER_REPLICATE)[0]
        section = np.sort(profile[left:right])
        peak = section[int(.9*(len(section)-1))]
        if peak <= 5:
            return False
        visible = np.flatnonzero(profile[:47] > max(3,.33*peak))
        ends.append(visible[-1] if len(visible) else -1)
    y1,y2,w1,w2 = ends
    if min(y1,y2) < 2 or abs(y1-y2)>5 or abs(w1-w2)>4 or not 1 <= min(w1,w2)-max(y1,y2) <= 15:
        return False

    def contrast(field):
        values = field-cv2.GaussianBlur(field,(0,0),1.8)
        values[:2] = values[47:] = 0
        values[:,:3] = 0
        values[26:,:29] = 0
        return unit(values)

    scores = .4*grey_sources@contrast(grey) + .6*yellow_sources@contrast(yellow)
    support = sorted(scores[roles],reverse=True)
    return bool(scores[primary] >= .50 and support[1] >= .45 and support[1]-max(scores[~roles]) >= .15)


def main(originals, brightness=1, jpeg_quality=None):
    rows = json.loads((ROOT/'docs/experiments/orange-side/values-enrollment.json').read_text())
    gallery = json.loads((ROOT/'web/data/orange-values.json').read_text())['templates']
    for row in rows:
        if row['role'] != 'competing':
            continue
        path = originals/row['file']
        if sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError(f"Checksum mismatch for {path.name}")
        with Image.open(path) as opened:
            photo = opened.convert('RGB')
        if brightness != 1:
            photo = ImageEnhance.Brightness(photo).enhance(brightness)
        if jpeg_quality is not None:
            encoded = BytesIO()
            photo.save(encoded, 'JPEG', quality=jpeg_quality)
            encoded.seek(0)
            with Image.open(encoded) as compressed:
                photo = compressed.convert('RGB')
        rgb = np.asarray(photo)
        # Exclude this photograph from the rival gallery while it is the query.
        sources = [source for key,source in gallery.items() if key != row['id']]
        roles = np.array([item['role']=='registered' for item in sources])
        primary, = [i for i,source in enumerate(sources) if 'cg' in source]
        def matrix(channel):
            return np.stack([unit(np.frombuffer(base64.b64decode(s[channel]),np.int8).astype('f')) for s in sources])
        grey, yellow = matrix('g'), matrix('y')
        quad = np.float32(row['corners'])
        across, down = quad[1]-quad[0], quad[3]-quad[0]
        random = np.random.default_rng(3111)
        count = wrong = 0
        for trial in range(1050):
            v = np.zeros(6) if trial == 0 else random.uniform(-1,1,6)
            origin = quad[0]+.22*v[0]*across+.25*v[1]*down
            x = across*(1+.38*v[2])+.12*v[4]*down
            y = down*(1+.38*v[3])+.13*v[5]*across
            proposal = np.float32([origin,origin+x,origin+x+y,origin+y])
            transform = cv2.getPerspectiveTransform(proposal,UNIT*np.float32([48,49]))
            patch = cv2.warpPerspective(rgb,transform,(49,50))
            for mode in range(5):
                count += 1
                wrong += accepted(variation(patch,mode),grey,yellow,roles,primary)
        print(f"{row['id']}: {wrong} accepted in {count} pose/occlusion trials",flush=True)
        if wrong:
            raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('originals',type=Path,help='Directory containing the hash-pinned Open Food Facts images')
    parser.add_argument('--brightness', type=float, default=1.0)
    parser.add_argument('--jpeg-quality', type=int)
    args = parser.parse_args()
    if args.brightness <= 0 or (args.jpeg_quality is not None and not 1 <= args.jpeg_quality <= 100):
        parser.error('Expected positive brightness and JPEG quality from 1 to 100')
    main(args.originals,args.brightness,args.jpeg_quality)
