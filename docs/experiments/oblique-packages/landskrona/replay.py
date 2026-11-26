"""Recreate the store crops and replay them through a hash-checked Chromium form."""
import argparse
import csv
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_registered_browser import replay


def verify(binary, expected, name):
    if sha256(binary).hexdigest() != expected:
        raise ValueError(f"Unexpected bytes for {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument("--web", type=Path, default=ROOT / "web")
    parser.add_argument("--release", choices=("v23", "recovery", "side-retry"), default="v23")
    args = parser.parse_args()
    web = args.web.resolve()
    freeze = json.loads((HERE.parent / "candidate-models.json").read_text())
    assets = dict(freeze["browser"])
    assets["package-reader.js"] = freeze["browser_release"]["form_script_sha256"]
    manifest = HERE / "inputs.csv"
    if args.release in ("recovery", "side-retry"):
        experiments = HERE.parents[1]
        manifest = experiments / "store-package-recovery/field-inputs.csv"
        study = "side-panel-retry" if args.release == "side-retry" else "store-package-recovery"
        assets = json.loads((experiments / study / "browser-freeze.json").read_text())
    for name, expected in assets.items():
        verify((web / name).read_bytes(), expected, name)
    originals = {}
    with TemporaryDirectory() as tmp, manifest.open(newline="") as stream:
        for row in csv.DictReader(stream):
            url = row["source_url"]
            if url not in originals:
                with urlopen(url, timeout=30) as response:
                    originals[url] = response.read()
            verify(originals[url], row["source_sha256"], url)
            box = tuple(int(row[key]) for key in ("left", "top", "right", "bottom"))
            crop = Path(tmp) / row["path"]
            with Image.open(BytesIO(originals[url])) as photo:
                ImageOps.exif_transpose(photo).crop(box).save(crop, compress_level=6)
            verify(crop.read_bytes(), row["sha256"], row["id"])
        replay(web, manifest, Path(tmp), args.out, args.chromium)


if __name__ == "__main__":
    main()
