"""Register four manually outlined God Morgon fronts using only verified fit-role photos."""
import argparse
import csv
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from pickloop.carton_matcher import frame, polygon_mask, sift
from pickloop.grocery_evaluation import PREFIX
from pickloop.photo_evaluation import crop_pixels

ROOT = Path(__file__).resolve().parents[1]
# Clockwise panel corners in original 348 x 348 source coordinates.
PANELS = [
    ("Apple", 14, [(73,81), (178,53), (226,250), (125,280)]),
    ("Orange", 10, [(175,78), (286,101), (259,280), (153,260)]),
    ("Orange-Red-Grapefruit", 8, [(139,103), (232,87), (231,280), (145,293)]),
    ("Red-Grapefruit", 14, [(99,78), (199,75), (204,264), (109,267)]),
]


def register(archive_path, train, output):
    with train.open() as stream:
        fit = {r["path"]: r["sha256"] for r in csv.DictReader(stream) if r["role"] == "fit"}
    values = {}
    with ZipFile(archive_path) as archive:
        for i, (flavour, number, corners) in enumerate(PANELS):
            name = f"God-Morgon-{flavour}-Juice"
            path = f"train/Packages/Juice/{name}/{name}_{number:03}.jpg"
            data = archive.read(PREFIX + path)
            if sha256(data).hexdigest() != fit.get(path):
                raise ValueError(f"reference differs from the registered fit row: {path}")
            rgb, _ = crop_pixels(data, {})
            image, scale = frame(rgb)
            polygon = np.float32(corners) * scale
            points, desc = sift(image, polygon_mask(image.shape, polygon))
            values.update({f"polygon{i}": polygon, f"points{i}": points, f"descriptors{i}": desc.astype("uint8")})
    np.savez_compressed(output, **values)
    print(sha256(output.read_bytes()).hexdigest(), output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--training", type=Path, default=ROOT / "docs/experiments/grocery-catalogue/training.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "src/pickloop/data/juice_gate.npz")
    args = parser.parse_args()
    register(args.archive, args.training, args.out)
