"""Rebuild the rejected trial in a new output folder, leaving the shipping source untouched."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRODUCTION = "3f4fb51"


def git_bytes(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("archive", type=Path, help="Pinned GroceryStoreDataset ZIP archive")
    cli.add_argument("out", type=Path, help="New, separate output directory")
    args = cli.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sealed = json.loads((HERE / "freeze.json").read_text())
    rows = (HERE / "addition.json").read_bytes()
    if sha256(rows).hexdigest() != sealed["frozen_files"]["addition.json"]:
        raise ValueError("Additional reference manifest changed")

    with tarfile.open(fileobj=BytesIO(git_bytes("archive", PRODUCTION, "src"))) as bundle:
        bundle.extractall(args.out, filter="data")
    sys.path.insert(0, str(args.out / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_registered_pack_gallery import build
    import numpy as np

    native = git_bytes("show", f"{PRODUCTION}:web/data/registered-pack-gallery.json")
    if sha256(native).hexdigest() != sealed["v2_digest"]:
        raise ValueError("Shipping gallery changed")
    gallery = json.loads(native)
    with ZipFile(args.archive) as archive:
        gallery["templates"].extend(build(json.loads(rows), {}, archive)["templates"])
    encoded = json.dumps(gallery, separators=(",", ":")).encode("ascii")
    expected = sealed["frozen_files"]["registered-pack-gallery.json"]
    if sha256(encoded).hexdigest() != expected:
        raise ValueError("Rebuilt gallery encoding differs from the evaluated trial")
    model = args.out / "src/pickloop"
    npz = model / "data/registered_pack.npz"
    np.savez_compressed(npz, gallery=np.frombuffer(encoded, np.uint8))
    if sha256(npz.read_bytes()).hexdigest() != sealed["frozen_files"]["registered_pack.npz"]:
        raise ValueError("Rebuilt NPZ differs from the evaluated trial")
    source = model / "registered_pack.py"
    text = source.read_text()
    if text.count(sealed["v2_digest"]) != 1:
        raise ValueError("Unexpected gallery verification code")
    source.write_text(text.replace(sealed["v2_digest"], expected))
    print(f"Verified gallery {expected} in {args.out.resolve()}")


if __name__ == "__main__":
    main()
