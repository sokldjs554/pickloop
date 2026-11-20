"""Fetch the PickLoop Freiburg research evaluation photos.

Run python scripts/catalogue_outside_source.py /path/to/local/fixture.
manifest.csv contains path,label,split,sha256. Paths are relative to the output
directory. The original fold-0 labels define the eligible images. We exclude
JUICE and MILK (catalogue categories), plus SPICES (possible garlic/ginger).
Assign alternating sorted classes to calibration and test, starting with BEANS
in calibration. Per class, take the 16 lowest SHA-256 digests of the ASCII
string "pickloop-freiburg-v1/" followed by the original relative image path.
No model predictions enter selection. Labels describe a photographed target
category; additional groceries may be visible in the scene.

Data: Jund, Abdo, Eitel and Burgard, The Freiburg Groceries Dataset (2016),
https://arxiv.org/abs/1611.05799. The authors provide the data for research
and require consent for commercial use. See
http://aisdatasets.informatik.uni-freiburg.de/freiburg_groceries_dataset/.
Files come from the pinned 224px mirror of Aleksandar Aleksandrov. Source
files and output manifest are locked below. Fetch photos into a local cache
outside the repository. This fixture measures these Freiburg categories only.
"""
import argparse
import csv
import hashlib
import io
import os
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

RAW = "https://raw.githubusercontent.com"
FOLD_URL = (
    f"{RAW}/PhilJd/freiburg_groceries_dataset/"
    "8827d2f61c2838756a069562b1c2ff53568ae33b/splits/test0.txt"
)
FOLD_SHA256 = "20086a597ad75c265e0eb63a74d48aa6f1d049b19433e6cb4d8c6d67073cad50"
IMAGE_BASE = (
    f"{RAW}/aleksandar-aleksandrov/groceries-object-detection-dataset/"
    "456a9cbbdfdb1695d0050a0d9431a6298604bc15/dataset/images/"
)
MANIFEST_SHA256 = "364b17c60a0d8a9caf08a0951bc8bc5fc59d62e11136453eb0a001c2ce60e935"
EXCLUDED = {"JUICE", "MILK", "SPICES"}
IMAGES_PER_CLASS = 16


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def download(url):
    for attempt in range(4):
        try:
            with urlopen(url, timeout=30) as response:
                return response.read()
        except (URLError, TimeoutError) as error:
            if isinstance(error, HTTPError) and 400 <= error.code < 500 and error.code != 429:
                raise
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = tempfile.NamedTemporaryFile(dir=path.parent, delete=False)
    temporary = Path(staged.name)
    try:
        with staged:
            staged.write(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def select_images(fold):
    if sha256(fold) != FOLD_SHA256:
        raise ValueError("Freiburg fold-0 source checksum mismatch")
    groups = defaultdict(list)
    for line in fold.decode("ascii").splitlines():
        image, _ = line.split()
        label, _ = image.split("/")
        if label not in EXCLUDED:
            groups[label].append(image)

    selected = []
    for index, label in enumerate(sorted(groups)):
        split = ("calibration", "test")[index % 2]
        ordered = sorted(
            groups[label],
            key=lambda name: sha256(("pickloop-freiburg-v1/" + name).encode("ascii")),
        )
        for image in ordered[:IMAGES_PER_CLASS]:
            filename = image.split("/")[1]
            selected.append((label.lower(), filename, split))
    return selected


def build_fixture(root):
    root.mkdir(parents=True, exist_ok=True)
    fold_path = root / "test0.txt"
    if not fold_path.exists():
        write_atomic(fold_path, download(FOLD_URL))
    selected = select_images(fold_path.read_bytes())

    def retrieve(item):
        label, filename, split = item
        relative = f"images/{label}/{filename}"
        target = root / relative
        if not target.exists():
            write_atomic(target, download(f"{IMAGE_BASE}{label}/{filename}"))
        return relative, label, split, sha256(target.read_bytes())

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("path", "label", "split", "sha256"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(retrieve, selected))
    if len({row[3] for row in rows}) != len(rows):
        raise ValueError("Duplicate photo bytes in the Freiburg selection")
    writer.writerows(rows)
    data = buffer.getvalue().encode("utf-8")
    digest = sha256(data)
    if digest != MANIFEST_SHA256:
        raise ValueError(f"Unexpected fixture checksum {digest}. Check or refresh the local cache.")
    write_atomic(root / "manifest.csv", data)
    print(f"{len(rows)} photos. Wrote {root / 'manifest.csv'} (SHA-256 {digest}).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path, help="Local fixture directory")
    build_fixture(parser.parse_args().output)
