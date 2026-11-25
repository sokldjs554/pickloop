"""Score the post-freeze gallery expansion against the production comparison."""

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from evaluate_registered_recall import STUDY, digest, records, verify
from score_registered_recall import TARGETS, ledger, web_exposure


def outcomes(batch, phase):
    known = [r for r in batch if r["truth"] in TARGETS]
    outside = [r for r in batch if r["truth"] not in TARGETS]
    return dict(correct=sum(r[phase] == r["truth"] for r in known),
                held_registered=sum(not r[phase] for r in known),
                wrong_on_registered=sum(bool(r[phase]) and r[phase] != r["truth"] for r in known),
                false_registered_on_outside=sum(r[phase] in TARGETS for r in outside),
                optical_orders=sum(bool(r[phase + "_order"]) for r in batch))


def metrics(batch):
    return dict(n=len(batch), registered=sum(r["truth"] in TARGETS for r in batch),
                v2=outcomes(batch, "v2"), expanded=outcomes(batch, "expanded"),
                gained=sum(r["truth"] in TARGETS and r["v2"] != r["truth"] and r["expanded"] == r["truth"] for r in batch),
                lost=sum(r["truth"] in TARGETS and r["v2"] == r["truth"] and r["expanded"] != r["truth"] for r in batch))


def reduce(folder, out, sealing):
    hashes, all_rows = {}, []
    overlap = {r["id"]: r["suspected_same_gtin_setting"] for r in records(STUDY / "expanded-acquisition-review.csv")}
    production = json.loads((folder / "production-prediction-seal.json").read_text())["sha256"]
    for cohort in ("archive", "public"):
        verify(cohort)
        blind = records(STUDY / f"{cohort}-blind.csv")
        ids = [r["id"] for r in blind]
        previous, before = ledger(folder, cohort, "production", ids)
        if digest(previous.read_bytes()) != production[previous.name]:
            raise ValueError("Production result changed")
        file, after = ledger(folder, cohort, "expanded", ids)
        hashes[file.name] = digest(file.read_bytes())
        if sealing:
            continue
        for label, v2, expanded in zip(records(STUDY / f"{cohort}-labels.csv"), before, after, strict=True):
            if not label["id"] == v2["id"] == expanded["id"]:
                raise ValueError("Label order changed")
            row = {k: label[k] for k in ("id", "cohort", "gtin", "truth", "view", "barcode_visible")}
            row["early_exposure"] = web_exposure(label) if cohort == "archive" else ""
            row["suspected_same_gtin_setting"] = overlap.get(row["id"], "")
            for name, data in (("v2", v2), ("expanded", expanded)):
                row[name] = data["ordinary"]["photo_name"] or ""
                row[name + "_order"] = data["strict"]["confirmed_order_sku"] or ""
            all_rows.append(row)
    seal_file = folder / "expanded-prediction-seal.json"
    if sealing:
        with seal_file.open("x") as stream:
            json.dump({"utc": datetime.now(timezone.utc).isoformat(), "sha256": hashes}, stream, indent=2)
            stream.write("\n")
        return
    if hashes != json.loads(seal_file.read_text())["sha256"]:
        raise ValueError("Expanded ledgers have changed")
    archive = [r for r in all_rows if r["cohort"] == "archive"]
    public = [r for r in all_rows if r["cohort"] == "public"]
    groups = {"archive": archive, "public": public,
              "archive excluding plausible same-GTIN setting": [r for r in archive if r["suspected_same_gtin_setting"] == "0"]}
    for key in ("view", "gtin", "early_exposure", "barcode_visible"):
        for value in sorted({r[key] for r in archive}):
            groups[key + " " + value] = [r for r in archive if r[key] == value]
    out.mkdir(parents=True, exist_ok=True)
    with (out / "expanded-rows.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=all_rows[0])
        writer.writeheader()
        writer.writerows(all_rows)
    (out / "expanded-summary.json").write_text(json.dumps({k: metrics(v) for k, v in groups.items()}, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledgers", type=Path, default=STUDY)
    stage = parser.add_mutually_exclusive_group(required=True)
    stage.add_argument("--out", type=Path)
    stage.add_argument("--seal", action="store_true")
    args = parser.parse_args()
    reduce(args.ledgers, args.out, args.seal)
