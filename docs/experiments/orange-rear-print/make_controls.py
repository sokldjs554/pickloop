"""Construct diagnostic edits of one reviewed camera image. These annotations run only during replay."""
import argparse
import csv
from hashlib import sha256
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photos", type=Path, help="Originals in inputs.csv and red-grapefruit train picture 021")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = args.photos / "RR-398059de4d64a316"
    if sha256(source.read_bytes()).hexdigest() != "398059de4d64a3169d7550b97ae43d5ce37df4991595c8b2bafcca1f8146788a":
        raise ValueError("The diagnostic annotations refer to a different source image")
    args.output.mkdir(exist_ok=True, parents=True)
    original = Image.open(source).convert("RGB")
    original.save(args.output / (source.name + "-jpeg85.jpg"), quality=85)
    ImageEnhance.Brightness(original).enhance(.9).save(args.output / (source.name + "-dim.jpg"), quality=85)

    edit_regions = [
        ("no-flap", [(182,143),(224,152),(216,118),(208,111)], (29,28,23)),
        ("no-word", [(119,104),(178,108),(175,124),(116,124)], (26,26,25)),
        ("no-copy", [(82,162),(174,173),(150,350),(68,332)], (27,25,22)),
        ("separate-packs", [(184,131),(190,135),(155,337),(148,334)], (218,218,214)),
    ]
    for name, vertices, color in edit_regions:
        rgb = np.array(original)
        cv2.fillConvexPoly(rgb, np.int32(vertices), color)
        Image.fromarray(rgb).save(args.output / (name + "-edit.png"))

    dest = np.float32([[182,108],[224,113],[184,284],[145,315]]) * np.float32([1,4/3])
    base = cv2.cvtColor(cv2.imread(str(source)), cv2.COLOR_BGR2RGB)
    mask = np.zeros(base.shape[:2], dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.int32(dest), 255)
    donors = [
        ("fi", "6415130050490-2", [(3,195),(905,197),(971,1164),(54,1166)]),
        ("big", "7310865074768-3", [(16,26),(856,26),(856,490),(16,490)]),
        ("red", "God-Morgon-Red-Grapefruit-Juice_021.jpg", [(100,89),(198,68),(193,252),(103,275)]),
    ]
    for name, filename, vertices in donors:
        donor = np.asarray(ImageOps.exif_transpose(Image.open(args.photos / filename)).convert("RGB"))
        transform = cv2.getPerspectiveTransform(np.float32(vertices), dest)
        side = cv2.warpPerspective(donor, transform, base.shape[:2][::-1])
        rgb = base.copy()
        rgb[mask > 0] = cv2.GaussianBlur(side, (3,3), .67)[mask > 0]
        Image.fromarray(rgb).save(args.output / (name + "-mod.png"))
    rgb = base.copy()
    rgb[mask > 0] = [27,22,16]
    Image.fromarray(rgb).save(args.output / "missing-mod.png")

    with Path(__file__).with_name("controls.csv").open(newline="") as expected:
        for row in csv.DictReader(expected):
            if sha256((args.output / row["id"]).read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError(f"Different encoded fixture for {row['id']}")


if __name__ == "__main__":
    main()
