#!/usr/bin/env python3
"""Reduce the paired frozen photo predictions into registry-specific counts."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import csv
import json
from pathlib import Path

from evaluate_fresh_size import STUDY, digest, rows, verify_manifest, write_json


def load_ledger(folder, file, ids):
    records = [json.loads(line) for line in (folder / file).read_text().splitlines()]
    if [r["id"] for r in records] != ids:
        raise ValueError(f"Ledger IDs or order differ from blind manifest in {file}")
    return {r["id"]: r for r in records}


LEDGERS = ("python-before.jsonl", "python-after.jsonl", "browser.jsonl")


def seal_run(folder):
    verify_manifest()
    ids = [r["id"] for r in rows(STUDY / "blind.csv")]
    for name in LEDGERS:
        load_ledger(folder, name, ids)
    seal = {"sealed_utc": datetime.now(timezone.utc).isoformat(), "n": len(ids),
            "sha256": {name: digest(folder / name) for name in LEDGERS}}
    with (folder / "prediction-seal.json").open("x") as stream:
        stream.write(json.dumps(seal, indent=2) + "\n")


def joined(folder):
    verify_manifest()
    seal = json.loads((folder / "prediction-seal.json").read_text())
    for name in LEDGERS:
        if digest(folder / name) != seal["sha256"][name]:
            raise ValueError(f"Prediction checksum failed: {name}")
    ids = [r["id"] for r in rows(STUDY / "blind.csv")]
    before, after, browser = [load_ledger(folder, name, ids) for name in LEDGERS]
    labels = rows(STUDY / "labels.csv")
    if [r["id"] for r in labels] != ids or len(set(ids)) != len(ids):
        raise ValueError("Blind IDs and label IDs differ")
    output = []
    for row in labels:
        key = row["id"]
        old, new, web = before[key], after[key], browser[key]["decision"]
        new_name = new["ordinary"]
        output.append({**row,
            "before": old["ordinary"]["photo_name"] or "", "after": new_name["photo_name"] or "",
            "before_order": old["strict"]["confirmed_order_sku"] or "",
            "order": new["strict"]["confirmed_order_sku"] or "",
            "browser": web.get("product", ""), "browser_kind": web["kind"],
            "browser_codes": " ".join(web["codes"]),
            "order_codes": " ".join(new["strict"]["order_check_gtins"]),
            "flavour_candidate": new_name["flavour_candidate"] or "", "size_status": new_name["size_status"],
            "size_evidence": json.dumps(new_name["size_evidence"]), "name_reason": new_name["photo_name_reason"]})
    for r in output:
        if any(s["split"] != r["split"] and s["group"] == r["group"] for s in output):
            raise ValueError("Product group crosses splits")
    return output


def counts(batch, method):
    truth = "browser_truth" if method == "browser" else "python_truth"
    known = [r for r in batch if r[truth]]
    unknown = [r for r in batch if not r[truth]]
    correct = sum(r[method] == r[truth] for r in known)
    held = sum(not r[method] for r in batch)
    return {"correct": correct, "wrong": len(batch) - correct - held, "held": held,
            "known": len(known), "known_held": sum(not r[method] for r in known),
            "unknown": len(unknown), "unknown_held": sum(not r[method] for r in unknown),
            "unknown_falsely_named": sum(bool(r[method]) for r in unknown)}


def subset(batch):
    modes = {k: counts(batch, k) for k in ("before", "after", "before_order", "order", "browser")}
    return {"n": len(batch), "groups": len({r["group"] for r in batch}), **modes,
            "visibly_coded": sum(r["barcode_visible"] == "1" for r in batch),
            "visible_correctly_decoded": sum(r["barcode_visible"] == "1" and r["browser_codes"] == r["gtin"]
                                            for r in batch)}


def public_example(row, role):
    return {"role": role, "id": row["id"], "image_url": row["image_url"],
            "gtin": row["gtin"], "photo_name": row["after"] or None, "browser_product": row["browser"] or None}


def score(folder, out):
    data = joined(folder)
    summary, compact = {}, []
    for split in ("dev", "final"):
        batch = [r for r in data if r["split"] == split]
        groups = {}
        for field in ("gtin", "volume_ml", "volume_print", "view", "barcode_visible", "visible_glare", "visible_blur"):
            values = sorted({r[field] for r in batch})
            groups[field] = {v: subset([r for r in batch if r[field] == v]) for v in values}
        result = subset(batch)
        result["name_transitions"] = dict(Counter(f"{r['before'] or 'HOLD'} -> {r['after'] or 'HOLD'}" for r in batch))
        summary[split] = {**result, "strata": groups}
        compact.append({"split": split, "n": len(batch), "model_known": result["after"]["known"],
                        "web_known": result["browser"]["known"],
                        **{k: {i: result[k][i] for i in ("correct", "wrong", "held")}
                           for k in ("before", "after", "order", "browser")}})
    final = [r for r in data if r["split"] == "final"]
    registered = next(r for r in final if r["python_truth"])
    similar = next(r for r in final if r["gtin"] == "6415130089834")
    alt = next(r for r in final if r["gtin"] == "6415130050490" and r["view"] == "front")
    compact_data = {"subsets": compact, "examples": [
        public_example(registered, "registered_1l_reverse"), public_example(similar, "demo_only_250ml_front"),
        public_example(alt, "unregistered_alternate_1l_front")]}
    out.mkdir(exist_ok=True, parents=True)
    write_json(out / "public-summary.json", compact_data)
    write_json(out / "metrics.json", summary)
    with (out / "rows.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledgers", type=Path, default=STUDY)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--seal", action="store_true", help="Seal a fresh blind run before joining truth")
    args = parser.parse_args()
    if args.seal:
        seal_run(args.ledgers)
    if args.out:
        score(args.ledgers, args.out)
    elif not args.seal:
        parser.error("use --seal or --out")
