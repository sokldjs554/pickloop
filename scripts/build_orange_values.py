"""Build ink-contrast features for the nutrition table's visible right-hand column."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from build_orange_nutrition import ROOT, UNIT, compact, image


def build(row, directory):
    transform = cv2.getPerspectiveTransform(np.float32(row['corners']), UNIT*np.float32([48,49]))
    patch = cv2.warpPerspective(image(row,directory),transform,(49,50)).astype('f')
    r, g, b = patch.transpose(2,0,1)
    luminance = .299*r + .587*g + .114*b
    yellow = np.minimum(r,g)-b
    mask = np.ones((50,49),bool)
    mask[:2] = False
    mask[47:] = False
    mask[:,:3] = False
    mask[26:,:29] = False  # The hand obscures this area in the frontal training reference.
    def contrast(field):
        return compact((field-cv2.GaussianBlur(field,(0,0),1.8))*mask)
    output = dict(g=contrast(luminance), y=contrast(yellow), role=row['role'], gtin=row['gtin'])
    if row['id'] == 'train19':
        # Sparse scan rows match the worker search. Final verification samples the
        # complete geometric projection against every registered and competing source.
        ys = np.array(list(range(25))+list(range(27,48,2)))[:,None]
        xs = np.arange(1,49,3)
        def coarse(field):
            return compact(field[ys,xs]-(field[np.maximum(0,ys-2),xs]+field[np.minimum(49,ys+2),xs])/2)
        output.update(cg=coarse(luminance),cy=coarse(yellow))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('train_originals',type=Path)
    parser.add_argument('competitor_originals',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'web/data/orange-values.json')
    args = parser.parse_args()
    rows = json.loads((ROOT/'docs/experiments/orange-side/values-enrollment.json').read_text())
    templates = {row['id']:build(row,args.train_originals if row['role']=='registered' else args.competitor_originals)
                 for row in rows}
    args.output.write_text(json.dumps(dict(version=1,templates=templates),separators=(',',':'))+'\n')
