"""Build part descriptors from source images checked against their enrollment hashes."""
import argparse
import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


def build(row, payload):
    if sha256(payload).hexdigest() != row["sha256"]:
        raise ValueError("Reference image checksum mismatch: " + row["id"])
    with Image.open(BytesIO(payload)) as opened:
        oriented = ImageOps.exif_transpose(opened).convert("RGBA")
        white = Image.new("RGBA", oriented.size, "white")
        white.alpha_composite(oriented)
        image = np.asarray(white.convert("RGB"))
    if "face" in row:
        from build_registered_pack_gallery import rectify
        image = rectify(image, row["face"])
    x, y, x1, y1 = row["crop"]
    crop = image[y:y1, x:x1]
    scale = 420 / max(crop.shape[:2])
    face = cv2.resize(crop, None, fx=scale, fy=scale)
    gray = cv2.cvtColor(face, cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(nfeatures=1800, edgeThreshold=9, fastThreshold=8)
    keys, desc = orb.detectAndCompute(gray, None)
    zones = []
    for box, minimum in zip(row["zones"], row["minima"], strict=True):
        xx, yy, right, bottom = np.rint((np.array(box) - [x,y,x,y]) * scale).astype(int)
        area = gray[yy:bottom, xx:right]
        size = (max(15, area.shape[1]//4), max(8, area.shape[0]//4))
        small = cv2.resize(area, size, interpolation=cv2.INTER_AREA).astype(np.float32)
        contrast = small - cv2.GaussianBlur(small, (0,0), 2.)
        # NCC is invariant to a positive uniform rescaling of the reference patch.
        compact = np.rint(127 * contrast / np.max(np.abs(contrast))).astype(np.int8)
        zones.append(dict(box=[int(xx), int(yy), int(right), int(bottom)], size=list(size),
                          minimum=minimum, contrast=base64.b64encode(compact.tobytes()).decode()))
    return dict(id=row["id"], gtin=row["gtin"], width=gray.shape[1], height=gray.shape[0],
                points=[[round(k.pt[0],2),round(k.pt[1],2)] for k in keys],
                descriptors=base64.b64encode(desc.tobytes()).decode(), details=zones)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("sources", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    refs = [build(row, (args.sources/row["file"]).read_bytes())
            for row in json.loads(args.manifest.read_text())]
    args.output.write_text(json.dumps(dict(version=1, templates=refs), separators=(',',':'))+'\n')
