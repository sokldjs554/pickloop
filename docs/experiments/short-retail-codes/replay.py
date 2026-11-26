"""Fetch pinned decoder fixtures, compose the two-code control, replay the public form."""
import argparse
import csv
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_registered_browser import replay


def combined_file(folder):
    registered = ROOT / "web/media/new-photos/orange-250ml-original.jpg"
    with Image.open(registered) as source:
        juice = ImageOps.exif_transpose(source).convert("RGB")
    with Image.open(folder / "ean8-1-1.png") as source:
        short = source.convert("RGB")
    juice.thumbnail((1300, 1100))
    short.thumbnail((680, 650))
    scene = Image.new("RGB", (juice.width + short.width + 90, max(juice.height, short.height) + 30), "white")
    scene.paste(juice, (15, 15))
    scene.paste(short, (juice.width + 60, 20))
    target = folder / "two-packs.png"
    scene.save(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", type=Path, default=ROOT / "web")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with TemporaryDirectory() as tmp, (HERE / "inputs.csv").open(newline="") as roster:
        photos = Path(tmp)
        manifest = photos / "inputs.csv"
        with manifest.open("w", newline="") as out:
            writer = csv.DictWriter(out, ["id", "path", "sha256"])
            writer.writeheader()
            for row in csv.DictReader(roster):
                with urlopen(row["source"], timeout=30) as response:
                    raw = response.read()
                if sha256(raw).hexdigest() != row["sha256"]:
                    raise ValueError(f"Source changed for {row['id']}")
                (photos / row["id"]).write_bytes(raw)
                writer.writerow({"id": row["id"], "path": row["id"], "sha256": row["sha256"]})
            composite = combined_file(photos)
            writer.writerow({"id": "two-packs", "path": composite.name,
                             "sha256": sha256(composite.read_bytes()).hexdigest()})
        replay(args.web, manifest, photos, args.out, args.chromium)


if __name__ == "__main__":
    main()
