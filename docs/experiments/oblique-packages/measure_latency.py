"""Time released Python ordinary recognition or the browser file-chooser replay on fixed inputs."""

import argparse
import csv
import json
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "scripts"))
from evaluate_registered_recall import digest
from score_oblique_packages import TARGETS, labels_for


def roster():
    positives = [r for r in labels_for("archive") if r["truth"] in TARGETS]
    sides = [r for r in positives if r["view"] == "side visible"]
    front = next(r for r in positives if r["view"] == "front")
    # The source manifest is sorted by image ID. Each registered product has one side representative.
    return [next(r for r in sides if r["truth"] == name) for name in sorted(TARGETS)] + [front]


def time_python(photos, rows):
    import cv2
    import numpy as np
    from PIL import Image, ImageOps
    from pickloop.grocery_catalogue import recognize_rgb
    cv2.setNumThreads(1)

    def read(row):
        path = photos / row["id"]
        if digest(path.read_bytes()) != row["sha256"]:
            raise ValueError(f'Image checksum changed for {row["id"]}')
        with Image.open(path) as photo:
            return np.asarray(ImageOps.exif_transpose(photo).convert("RGB"))

    # Initialize DINO, OCR and gallery in the same process. The timed region starts at RGB input.
    recognize_rgb(read(rows[-1]))
    results = []
    for row in rows:
        pixels = read(row)
        start = perf_counter()
        result = recognize_rgb(pixels)
        elapsed = (perf_counter() - start) * 1000
        results.append({"id": row["id"], "view": row["view"], "ms": round(elapsed, 2), "name": result["photo_name"]})
    return results


def time_browser(photos, rows, web, chromium):
    from evaluate_registered_browser import replay
    results = []
    with TemporaryDirectory() as directory:
        folder = Path(directory)
        for row in rows:
            manifest = folder / "input.csv"
            with manifest.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=("id", "sha256"), extrasaction="ignore")
                writer.writeheader()
                writer.writerow(row)
            output = folder / (row["id"] + ".jsonl")
            # Each call owns a new browser, HTTP server, page, and OCR worker.
            start = perf_counter()
            replay(web, manifest, photos, output, chromium)
            elapsed = (perf_counter() - start) * 1000
            result = json.loads(output.read_text())
            results.append({"id": row["id"], "view": row["view"], "ms": round(elapsed, 2), "name": result["product"]})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", choices=("python", "browser"))
    parser.add_argument("photos", type=Path)
    parser.add_argument("--web", type=Path)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = roster()
    if args.runtime == "python":
        results = time_python(args.photos, rows)
    elif args.web:
        results = time_browser(args.photos, rows, args.web, args.chromium)
    else:
        parser.error("browser timing needs --web")
    with args.out.open("x") as stream:
        json.dump({"platform": platform.platform(), "runtime": args.runtime, "rows": results}, stream, indent=2)
        stream.write("\n")
