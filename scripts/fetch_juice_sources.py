"""Fetch byte-verified external evaluation images to a user-specified local cache."""
import argparse
import csv
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen

MANIFEST = Path(__file__).resolve().parents[1] / "docs/experiments/juice-gate/external-manifest.csv"


def fetch(root):
    data = MANIFEST.read_bytes()
    if sha256(data).hexdigest() != "fa6a3f32e0d98881621ebb48c57502916cb7b95eede614cc79a668e5a244db7d":
        raise ValueError("external manifest differs from frozen source")
    for row in csv.DictReader(data.decode().splitlines()):
        path = root / row["path"]
        if path.is_file() and sha256(path.read_bytes()).hexdigest() == row["sha256"]:
            continue
        request = Request(row["image_url"], headers={"User-Agent": "PickLoop dataset reproduction/1.0"})
        with urlopen(request, timeout=30) as response:
            image = response.read()
        if sha256(image).hexdigest() != row["sha256"]:
            raise ValueError(f"source bytes differ for {row['sample_id']}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
            temp.write(image)
        Path(temp.name).replace(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    fetch(parser.parse_args().cache)
