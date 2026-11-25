"""Pair shipped and candidate package decisions using the original image IDs and view labels."""

import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
from statistics import median

from evaluate_registered_recall import STUDY, digest, records, verify
from score_registered_recall import TARGETS

EXPERIMENT = STUDY.parent / "oblique-packages"
RUNTIMES = ("python", "browser")
OUTCOMES = ("correct_registered", "held", "wrong_registered", "wrong_broad", "correct_broad", "runtime_error")
TIMINGS = ("elapsed_ms", "ordinary_ms", "strict_ms")
COHORTS = ("archive", "public", "legacy-validation", "supplemental")
PLAIN_RED = "God-Morgon-Red-Grapefruit-Juice"


def predictions(path, labels, expected_hash=None):
    binary = path.read_bytes()
    if expected_hash and digest(binary) != expected_hash:
        raise ValueError(f"Prediction checksum changed for {path}")
    entries = [json.loads(line) for line in binary.splitlines()]
    ids = [label["id"] for label in labels]
    by_id = {entry["id"]: entry for entry in entries}
    if len(set(ids)) != len(ids) or len(by_id) != len(entries) or set(by_id) != set(ids):
        raise ValueError(f"Duplicate, missing or unexpected IDs in {path}")
    for label in labels:
        entry = by_id[label["id"]]
        if "sha256" in entry and entry["sha256"] != label["sha256"]:
            raise ValueError(f'Image checksum changed for {label["id"]}')
    return by_id


def outcome(truth, gtin, name):
    if not name:
        return "held"
    if name in TARGETS:
        return "correct_registered" if name == truth else "wrong_registered"
    if gtin == "7310860007396" and name == PLAIN_RED:
        return "correct_broad"
    return "wrong_broad"


def decision(runtime, entry):
    if runtime == "python":
        return entry["ordinary"]["photo_name"], entry["strict"]["confirmed_order_sku"]
    return entry["product"], entry["barcode_order"]


def metric(rows):
    result = {"n": len(rows)}
    for phase in ("baseline", "candidate"):
        counts = Counter(row[phase + "_outcome"] for row in rows)
        result[phase] = {key: counts[key] for key in OUTCOMES}
        result[phase]["completed"] = len(rows) - counts["runtime_error"]
        result[phase]["orders"] = sum(bool(row[phase + "_order"]) for row in rows)
        result[phase]["wrong_orders"] = sum(bool(row[phase + "_order"]) and row[phase + "_order"] != row["truth"] for row in rows)
        for timing in TIMINGS:
            timed = [row[phase + "_" + timing] for row in rows if row[phase + "_" + timing] is not None]
            if timed:
                result[phase][timing] = {"n": len(timed), "median": round(median(timed), 2), "max": round(max(timed), 2)}
    result["gained_correct_registered"] = sum(row["baseline_outcome"] != "correct_registered" and row["candidate_outcome"] == "correct_registered" for row in rows)
    result["lost_correct_registered"] = sum(row["baseline_outcome"] == "correct_registered" and row["candidate_outcome"] != "correct_registered" for row in rows)
    return result


def baseline_path(runtime, cohort):
    if cohort == "supplemental" or (cohort == "legacy-validation" and runtime == "browser"):
        path = EXPERIMENT / f"{cohort}-{runtime}-baseline.jsonl"
        seal = json.loads((EXPERIMENT / "additional-baselines.json").read_text())
        return path, seal["files"][path.name]
    if runtime == "python":
        path = STUDY / f"{cohort}-production.jsonl"
        seal = json.loads((STUDY / "production-prediction-seal.json").read_text())
        return path, seal["sha256"][path.name]
    check = json.loads((STUDY / "browser-release-check.json").read_text())["comparisons"][cohort]
    return STUDY / check["ledger"], check["sha256"]


def row_for(label, runtime, flag, baseline, candidate):
    row = {k: label[k] for k in ("id", "sha256", "cohort", "gtin", "truth")}
    row["view"] = label.get("view", "")
    row["acquisition_group"] = label.get("acquisition_group", "")
    row["runtime"] = runtime
    row["possible_training_setting"] = flag
    for phase, entry in (("baseline", baseline), ("candidate", candidate)):
        if entry.get("status") == "timeout":
            row[phase + "_name"] = None
            row[phase + "_order"] = None
            row[phase + "_outcome"] = "runtime_error"
        else:
            name, order = decision(runtime, entry)
            row[phase + "_name"], row[phase + "_order"] = name, order
            row[phase + "_outcome"] = outcome(label["truth"], label["gtin"], name)
        for key in TIMINGS:
            value = entry.get(key)
            if value is not None and (type(value) not in (float, int) or not math.isfinite(value) or value < 0):
                raise ValueError(f'Invalid {key} for {row["id"]}')
            row[phase + "_" + key] = value
    return row


def strata(rows):
    groups = {}
    for row in rows:
        cohort = row["cohort"]
        positive = row["truth"] in TARGETS
        keys = [cohort + "_all", cohort + ("_registered" if positive else "_controls")]
        if row["acquisition_group"]:
            keys.append(cohort + "_group_" + row["acquisition_group"])
        if positive and row["view"]:
            keys.append(cohort + "_registered_" + row["view"].replace(" ", "_"))
            if cohort == "archive" and row["view"] == "side visible":
                keys.append("archive_registered_side_gtin_" + row["gtin"])
                if row["possible_training_setting"] == "0":
                    keys.append("archive_registered_side_excluding_flagged_setting")
        for key in keys:
            groups.setdefault(key, []).append(row)
    return {key: metric(batch) for key, batch in sorted(groups.items())}


def labels_for(cohort):
    if cohort == "supplemental":
        seal = json.loads((EXPERIMENT / "protocol-freeze.json").read_text())
        for name, expected in seal["files"].items():
            if digest((EXPERIMENT / name).read_bytes()) != expected:
                raise ValueError(f"Frozen protocol or supplemental cohort changed: {name}")
        folder = EXPERIMENT
    else:
        verify(cohort)
        folder = STUDY
    labels = records(folder / f"{cohort}-labels.csv")
    blind = records(folder / f"{cohort}-blind.csv")
    keys = ("id", "sha256")
    if [[r[k] for k in keys] for r in blind] != [[r[k] for k in keys] for r in labels]:
        raise ValueError(f"Blind manifest differs from labels for {cohort}")
    return labels


def score(folder, out):
    audit = records(STUDY / "expanded-acquisition-review.csv")
    flags = {r["id"]: r["suspected_same_gtin_setting"] for r in audit}
    rows, summary, hashes = [], {}, {}
    for runtime in RUNTIMES:
        paired = []
        for cohort in COHORTS:
            labels = labels_for(cohort)
            before_path, expected = baseline_path(runtime, cohort)
            before = predictions(before_path, labels, expected)
            path = folder / f"{cohort}-{runtime}.jsonl"
            after = predictions(path, labels)
            hashes[path.name] = digest(path.read_bytes())
            for label in labels:
                key = label["id"]
                paired.append(row_for(label, runtime, flags[key] if cohort == "archive" else "", before[key], after[key]))
        rows.extend(paired)
        summary[runtime] = strata(paired)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "paired.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    (out / "scores.json").write_text(json.dumps({"ledgers_sha256": hashes, "scores": summary}, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledgers", type=Path, default=EXPERIMENT)
    parser.add_argument("--out", type=Path, default=EXPERIMENT)
    args = parser.parse_args()
    score(args.ledgers, args.out)
