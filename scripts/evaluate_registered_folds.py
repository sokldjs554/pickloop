"""Retrospective recognition with all external references of one registered GTIN held out."""

import argparse
from contextlib import nullcontext
import json
from pathlib import Path
from unittest.mock import patch

from evaluate_registered_recall import STUDY, digest, records, verify


def fetch(photos):
    from fetch_recognition_photos import cache_image

    verify("folds")
    previous = STUDY.parent / "new-photos"
    sources = {}
    for path in (previous / "original-labels-new.csv", previous / "original-labels-prior.csv",
                 STUDY.parent / "fresh-size-eval/labels.csv"):
        sources.update({r.get("id") or r["sample_id"]: r for r in records(path)})
    photos.mkdir(exist_ok=True, parents=True)
    for row in records(STUDY / "folds-labels.csv"):
        cache_image(photos / row["id"], row["sha256"], sources[row["prior_id"]])


def run(photos, output, revised):
    import cv2
    import numpy as np
    from PIL import Image, ImageOps
    from pickloop.grocery_catalogue import recognize_rgb

    verify("folds")
    excluded = json.loads((STUDY / "folds-withheld.json").read_text())
    if revised:
        from pickloop import registered_pack
        full = registered_pack.gallery()
        ids = {r["id"] for r in full}
        if any(not set(group) <= ids for group in excluded.values()):
            raise ValueError("Withheld templates do not match the frozen model gallery")
    cv2.setNumThreads(1)
    with output.open("x") as stream:
        for row in records(STUDY / "folds-blind.csv"):
            photo = photos / row["id"]
            if digest(photo.read_bytes()) != row["sha256"]:
                raise ValueError(f"Input mismatch for {row['id']}")
            with Image.open(photo) as source:
                pixels = np.asarray(ImageOps.exif_transpose(source).convert("RGB"))
            dataset = nullcontext()
            if revised:
                keep = [t for t in full if t["id"] not in excluded[row["fold"]]]
                dataset = patch.object(registered_pack, "gallery", return_value=keep)
            with dataset:
                result = recognize_rgb(pixels)
            stream.write(json.dumps({"id": row["id"], "ordinary": result}, allow_nan=False) + "\n")
            stream.flush()


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("photos", type=Path)
    cli.add_argument("--out", type=Path)
    cli.add_argument("--fetch", action="store_true")
    cli.add_argument("--revised", action="store_true")
    args = cli.parse_args()
    if args.fetch:
        fetch(args.photos)
    elif args.out:
        run(args.photos, args.out, args.revised)
    else:
        cli.error("use --fetch or provide --out")
