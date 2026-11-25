"""Fetch frozen carton photographs and evaluate both normal Python recognition modes."""

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


STUDY = Path(__file__).resolve().parents[1] / "docs/experiments/registered-recall"


def digest(payload):
    return sha256(payload).hexdigest()


def records(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def verify(cohort):
    seal = json.loads((STUDY / f"{cohort}-freeze.json").read_text())
    for name, expected in seal["files"].items():
        if digest((STUDY / name).read_bytes()) != expected:
            raise ValueError(f"Frozen roster changed: {name}")


def fetch(folder, cohort):
    folder.mkdir(parents=True, exist_ok=True)
    mirrors = json.loads((STUDY / "public-alternate-urls.json").read_text()) if cohort == "public" else {}
    for row in records(STUDY / f"{cohort}-labels.csv"):
        path = folder / row["id"]
        if path.exists() and digest(path.read_bytes()) == row["sha256"]:
            continue
        url = mirrors.get(row["id"], row["image_url"])
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 (PickLoop evaluation research)"})
        for attempt in range(4):
            try:
                with urlopen(request, timeout=35) as response:
                    payload = response.read(12 * 1024 * 1024 + 1)
                break
            except (HTTPError, URLError) as err:
                if attempt == 3 or isinstance(err, HTTPError) and err.code < 429:
                    raise
                sleep(1 + attempt)
        if digest(payload) != row["sha256"]:
            raise ValueError(f"Source version mismatch for {row['id']}")
        path.write_bytes(payload)


def infer(folder, cohort, output):
    import cv2
    import numpy as np
    from PIL import Image, ImageOps
    from pickloop.grocery_catalogue import recognize_rgb

    cv2.setNumThreads(1)
    with output.open("x") as stream:
        for row in records(STUDY / f"{cohort}-blind.csv"):
            path = folder / row["id"]
            if digest(path.read_bytes()) != row["sha256"]:
                raise ValueError(f"Wrong input bytes for {row['id']}")
            with Image.open(path) as photo:
                pixels = np.asarray(ImageOps.exif_transpose(photo).convert("RGB"))
            result = {
                "id": row["id"],
                "ordinary": recognize_rgb(pixels),
                "strict": recognize_rgb(pixels, require_gtin=True),
            }
            stream.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("fetch", "infer"))
    cli.add_argument("cohort", choices=("archive", "public"))
    cli.add_argument("folder", type=Path)
    cli.add_argument("--out", type=Path)
    args = cli.parse_args()
    verify(args.cohort)
    if args.action == "fetch":
        fetch(args.folder, args.cohort)
    elif args.out:
        infer(args.folder, args.cohort, args.out)
    else:
        cli.error("inference requires --out")
