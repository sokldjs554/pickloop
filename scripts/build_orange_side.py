"""Build the adjoining-face descriptors from explicitly enrolled train photographs."""
import argparse
import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
UNIT = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])


def build(row, payload, rectified=False):
    if sha256(payload).hexdigest() != row["sha256"]:
        raise ValueError(f"Checksum mismatch for {row['file']}")
    with Image.open(BytesIO(payload)) as opened:
        rgb = np.asarray(ImageOps.exif_transpose(opened).convert("RGB"))
    height, width = rgb.shape[:2]
    if (width, height) != (348, 348):
        raise ValueError(f"Unexpected enrollment dimensions for {row['file']}")
    scale = 720 / max(width, height)
    frame = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
    corners = np.float32(row["corners"]) * scale
    if rectified:
        # A first pose puts the visitor's print onto the same independently
        # rectified plane. Matching starts again from the image pixels.
        target = UNIT * np.float32([170, 500])
        transform = cv2.getPerspectiveTransform(corners, target)
        frame = cv2.warpPerspective(frame, transform, (170, 500))
        corners = target
    mask = np.zeros(frame.shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, corners.astype(int), 255)
    mask[[0, -1], :] = 0
    mask[:, [0, -1]] = 0
    orb = cv2.ORB_create(nfeatures=1800, edgeThreshold=9, fastThreshold=8)
    keys, descriptors = orb.detectAndCompute(cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY), mask)
    positions = np.float32([key.pt for key in keys])
    matrix = cv2.getPerspectiveTransform(corners, UNIT)
    points = cv2.perspectiveTransform(positions[:, None], matrix)[:, 0]
    # Keep the actual printed material inside the face. The keypoint descriptor
    # uses a 31-pixel window at its pyramid scale, so reject windows on the seam.
    inside = np.zeros(len(keys), dtype=bool)
    border = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    for i, (key, (x, y)) in enumerate(zip(keys, positions)):
        inside[i] = border[round(y), round(x)] > .75 * key.size
    if row["view"] == "front":
        inside &= points[:, 1] < .42  # brand, flavor and script
    else:
        inside &= points[:, 1] < .63  # multilingual paragraphs; omit barcode and fruit area
    selected = np.flatnonzero(inside)
    return dict(rectified=rectified, source=row["sha256"], view=row["view"], gtin=row["gtin"],
                points=np.round(points[selected] * 1000).astype(int).tolist(),
                descriptors=base64.b64encode(descriptors[selected].tobytes()).decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("originals", type=Path, help="Directory holding original ID-named train JPEGs")
    parser.add_argument("--output", type=Path, default=ROOT / "web/data/orange-side.json")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "docs/experiments/orange-side/enrollment.json").read_text())
    templates = [build(row, (args.originals / row["file"]).read_bytes()) for row in manifest]
    templates += [build(row, (args.originals / row["file"]).read_bytes(), True)
                  for row in manifest if row["view"] == "ingredients"]
    args.output.write_text(json.dumps(dict(version=1, templates=templates), separators=(",", ":")) + "\n")
