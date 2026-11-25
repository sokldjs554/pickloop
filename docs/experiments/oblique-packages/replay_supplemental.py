"""Fetch the three frozen side/reverse controls, or run both Python recognition modes."""

import argparse
from pathlib import Path
import sys
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "scripts"))
import evaluate_registered_recall as replay
from score_oblique_packages import labels_for


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fetch", "infer"))
    parser.add_argument("photos", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    labels = labels_for("supplemental")
    if args.action == "fetch":
        args.photos.mkdir(parents=True, exist_ok=True)
        for row in labels:
            file = args.photos / row["id"]
            if file.exists() and replay.digest(file.read_bytes()) == row["sha256"]:
                continue
            request = Request(row["source_image"], headers={"User-Agent": "PickLoop research photo replay"})
            with urlopen(request, timeout=35) as response:
                binary = response.read()
            if replay.digest(binary) != row["sha256"]:
                raise ValueError(f'Publisher image differs for {row["id"]}')
            file.write_bytes(binary)
    elif args.out:
        replay.STUDY = HERE
        replay.infer(args.photos, "supplemental", args.out)
    else:
        parser.error("inference requires --out")
