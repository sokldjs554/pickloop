"""Replay the inspected 33 juice photos and seven earlier development photos using the live recognizer."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from pickloop.grocery_catalogue import recognize_rgb

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "docs/experiments/new-photos"
OUTCOMES = ("known_correct", "known_wrong_name", "known_hold", "unknown_false_accept", "unknown_hold")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def outcome(truth, name):
    if truth == "UNKNOWN":
        return "unknown_hold" if name == "UNKNOWN" else "unknown_false_accept"
    if name == "UNKNOWN":
        return "known_hold"
    return "known_correct" if truth == name else "known_wrong_name"


def summarize(rows):
    def counts(field):
        values = Counter(row[field] for row in rows)
        return {key: values[key] for key in OUTCOMES}

    return dict(photos=len(rows), known=sum(r["exact_truth"] != "UNKNOWN" for r in rows),
                unknown=sum(r["exact_truth"] == "UNKNOWN" for r in rows), before=counts("before_outcome"),
                after=counts("after_outcome"), confirmed_order_skus=sum(r["confirmed_order_sku"] is not None for r in rows))


def replay(root, out):
    seal = json.loads((FROZEN / "predictions-seal.json").read_text())
    ledger = FROZEN / "predictions-blind.jsonl"
    if digest(ledger) != seal["predictions_sha256"]:
        raise ValueError("original prediction ledger differs from its seal")
    frozen_rows_hash = json.loads((FROZEN / "summary.json").read_text())["files"]["rows.csv"]
    if digest(FROZEN / "rows.csv") != frozen_rows_hash:
        raise ValueError("original labels and predictions differ from the frozen rows")
    raw = {r["id"]: r for r in map(json.loads, ledger.read_text().splitlines())}
    blind = {}
    for cohort in ("new", "prior"):
        with (root / cohort / "blind.csv").open(newline="") as stream:
            for r in csv.DictReader(stream):
                blind[r.get("id") or r["sample_id"]] = root / cohort / r["path"]
    blind_answers = {}
    # The original IDs were assigned from digests. Inference receives only pixels.
    for id_ in sorted(raw.keys() & blind.keys()):
        path = blind[id_]
        if digest(path) != raw[id_]["sha256"]:
            raise ValueError(f"image checksum mismatch for {id_}")
        with Image.open(path) as im:
            rgb = np.asarray(ImageOps.exif_transpose(im).convert("RGB"))
        result = recognize_rgb(rgb)
        blind_answers[id_] = {k: result[k] for k in (
            "prediction", "photo_name", "photo_name_reason", "flavour_candidate", "size_status", "size_evidence",
            "size_readings", "recognition_text", "recognition_gtins", "recognition_source", "recognition_reason",
            "confirmed_order_sku", "confirmed_gtin")}
    rows = []
    with (FROZEN / "rows.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["role"] not in ("new_primary", "alternate_gtin_challenge", "prior_development"):
                continue
            id_, truth = row["id"], row["exact_truth"]
            previous = raw[id_]["after"]
            if row["after_prediction"] != previous["prediction"] or row["sha256"] != raw[id_]["sha256"]:
                raise ValueError(f"row drift for {id_}")
            answer = blind_answers[id_]
            rows.append(dict(id=id_, sha256=row["sha256"], role=row["role"], source_group=row["source_group"],
                             view=row["view_type"], gtin_truth=row["gtin"], exact_truth=truth, family_truth=row["family_truth"],
                             source_notes=row["notes"], before=previous["prediction"],
                             before_reason=previous["recognition_reason"], before_outcome=outcome(truth, previous["prediction"]),
                             after_outcome=outcome(truth, answer["prediction"]), **answer))
    regression = [r for r in rows if r["role"] != "prior_development"]
    prior = [r for r in rows if r["role"] == "prior_development"]
    if len(regression) != 33 or len(prior) != 7 or len(blind_answers) != len(rows):
        raise ValueError("incomplete or changed cohort")
    # Hash every decision stage needed to reproduce this paired replay.
    files = ["src/pickloop/" + name for name in ("photo_readout.py", "package_size.py", "product_text.py",
             "grocery_catalogue.py", "catalogue_features.py", "catalogue_model.py", "juice_gate.py", "pack_barcode.py",
             "carton_matcher.py", "data/grocery_catalogue.npz", "data/bravo_carton_panels.npz", "data/juice_gate.npz")]
    record = {"method": "Post-inspection regression replay from verified original RGB through recognize_rgb. Before is the sealed package-text decision. Labels joined after current inference.",
              "frozen_ledger_sha256": digest(ledger), "frozen_rows_sha256": digest(FROZEN / "rows.csv"),
              "source_sha256": {name: digest(ROOT / name) for name in files},
              "juice_33": summarize(regression), "earlier_development_7": summarize(prior),
              "original_six": [r["id"] for r in regression if r["before_outcome"] == "unknown_false_accept"],
              "rows": rows}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: record[k] for k in ("juice_33", "earlier_development_7")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", type=Path, required=True, help="parent of reconstructed new/blind.csv and prior/blind.csv")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    replay(args.photos, args.out)
