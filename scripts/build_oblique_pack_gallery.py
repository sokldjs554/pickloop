"""Build the Python oblique-view descriptors from the original 32 registered faces."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image, ImageOps

from build_registered_pack_gallery import ROOT, rectify
from pickloop.oblique_pack import FEATURES


def build(archive, originals, enrollment, output):
    files = {p.stem: p for root in originals for p in root.iterdir() if p.is_file()}
    train = {path.split("/dataset/", 1)[1]: path for path in archive.namelist() if "/dataset/train/" in path}
    sift = cv2.SIFT_create(nfeatures=800, contrastThreshold=.025)
    arrays = {}
    for row in enrollment:
        source = row["source"]
        payload = archive.read(train[source]) if source.startswith("train/") else files[row["id"]].read_bytes()
        if sha256(payload).hexdigest() != row["sha256"]:
            raise ValueError(f"reference checksum mismatch for {row['id']}")
        with Image.open(BytesIO(payload)) as photo:
            oriented = ImageOps.exif_transpose(photo).convert("RGBA")
            white = Image.new("RGBA", oriented.size, "white")
            white.alpha_composite(oriented)
            face = rectify(np.asarray(white.convert("RGB")), row)
        gray = cv2.cvtColor(face, cv2.COLOR_RGB2GRAY)
        keys, desc = sift.detectAndCompute(gray, None)
        points = np.float32([key.pt for key in keys])
        arrays[row["id"] + "-xy"] = np.round(points * 4).astype(np.uint16)
        # OpenCV's SIFT descriptor bins have integer values in [0, 255].
        arrays[row["id"] + "-desc"] = desc.astype(np.uint8)
    np.savez_compressed(output, **arrays)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("originals", type=Path, nargs="+", help="Directories containing the original ID-named photos")
    parser.add_argument("--output", type=Path, default=FEATURES)
    parser.add_argument("--enrollment", type=Path,
                        default=ROOT / "docs/experiments/registered-photo-recall/enrollment.json")
    args = parser.parse_args()
    with ZipFile(args.archive) as source_zip:
        build(source_zip, args.originals, json.loads(args.enrollment.read_text()), args.output)
    print(sha256(args.output.read_bytes()).hexdigest(), args.output)
