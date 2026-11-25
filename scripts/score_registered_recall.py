"""Check the paired ledgers and reduce the three registered 1 L photo decisions."""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from evaluate_registered_recall import STUDY, digest, records, verify


TARGETS = {"God-Morgon-Apple-Juice", "God-Morgon-Orange-Juice", "God-Morgon-Orange-Red-Grapefruit-Juice"}
COHORTS = ("archive", "public")


def ledger(folder, cohort, phase, ids):
    file = folder / f"{cohort}-{phase}.jsonl"
    rows = [json.loads(line) for line in file.read_text().splitlines()]
    if [r["id"] for r in rows] != ids:
        raise ValueError(f"Prediction IDs or order differ for {file.name}")
    return file, rows


def seal(folder):
    for cohorts, name in ((COHORTS, "python-prediction-seal.json"), (("folds",), "folds-prediction-seal.json")):
        hashes = {}
        for cohort in cohorts:
            verify(cohort)
            ids = [r["id"] for r in records(STUDY / f"{cohort}-blind.csv")]
            for phase in ("before", "after"):
                file, _ = ledger(folder, cohort, phase, ids)
                hashes[file.name] = digest(file.read_bytes())
        path = folder / name
        if path.exists():
            if json.loads(path.read_text())["sha256"] != hashes:
                raise ValueError(f"Existing prediction seal differs for {name}")
            continue
        with path.open("x") as stream:
            json.dump({"utc": datetime.now(timezone.utc).isoformat(), "sha256": hashes}, stream, indent=2)
            stream.write("\n")


def web_exposure(row):
    if row["cohort"] == "public":
        return "unviewed"
    suffix = int(row["native_id"][-7:-4])
    if suffix in (1, 10, 12):
        return "early worker"
    return "contact sheet only" if row["gtin"] in ("7310865074225", "7310860007396") else "unviewed"


def outcome(row, field):
    prediction = row[field]
    if row["truth"] == "UNKNOWN":
        return "outside_falsely_named_registered" if prediction in TARGETS else "outside_no_registered_name"
    if prediction == row["truth"]:
        return "registered_correct"
    return "registered_wrong_name" if prediction else "registered_held"


def metrics(batch):
    result = {"n": len(batch), "registered": sum(r["truth"] != "UNKNOWN" for r in batch)}
    for key in ("before", "after", "before_order", "after_order"):
        counts = Counter(outcome(r, key) for r in batch)
        result[key] = {k: counts[k] for k in ("registered_correct", "registered_wrong_name", "registered_held",
                                              "outside_falsely_named_registered", "outside_no_registered_name")}
        result[key]["other_catalogue_names"] = dict(Counter(r[key] for r in batch if r[key] and r[key] not in TARGETS))
        result[key]["total_empty"] = sum(not r[key] for r in batch)
    result["gained_correct_registered"] = sum(r["truth"] != "UNKNOWN" and r["before"] != r["truth"]
                                             and r["after"] == r["truth"] for r in batch)
    result["lost_correct_registered"] = sum(r["truth"] != "UNKNOWN" and r["before"] == r["truth"]
                                            and r["after"] != r["truth"] for r in batch)
    return result


def score_folds(folder, out):
    verify("folds")
    labels = records(STUDY / "folds-labels.csv")
    ids = [r["id"] for r in records(STUDY / "folds-blind.csv")]
    if [r["id"] for r in labels] != ids or len(set(ids)) != len(ids):
        raise ValueError("Historical fold label IDs differ")
    hashes = json.loads((folder / "folds-prediction-seal.json").read_text())["sha256"]
    for phase in ("before", "after"):
        file, entries = ledger(folder, "folds", phase, ids)
        if digest(file.read_bytes()) != hashes[file.name]:
            raise ValueError(f"Prediction checksum failed for {file.name}")
        for row, data in zip(labels, entries, strict=True):
            row[phase] = data["ordinary"]["photo_name"] or ""
            row[phase + "_reason"] = data["ordinary"]["photo_name_reason"]
    fields = ["id", "prior_id", "gtin", "truth", "view", "fold", "before", "after", "before_reason", "after_reason"]
    with (out / "folds-rows.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(labels)


def score(folder, out):
    seals = json.loads((folder / "python-prediction-seal.json").read_text())["sha256"]
    out.mkdir(exist_ok=True, parents=True)
    combined, summary = [], {}
    for cohort in COHORTS:
        verify(cohort)
        labels = records(STUDY / f"{cohort}-labels.csv")
        ids = [r["id"] for r in records(STUDY / f"{cohort}-blind.csv")]
        if [r["id"] for r in labels] != ids or len(set(ids)) != len(ids):
            raise ValueError(f"Labels differ from blind IDs in {cohort}")
        ledgers = []
        for phase in ("before", "after"):
            path, entries = ledger(folder, cohort, phase, ids)
            if digest(path.read_bytes()) != seals[path.name]:
                raise ValueError(f"Prediction ledgers changed: {path.name}")
            ledgers.append(entries)
        group = []
        for truth, old, new in zip(labels, *ledgers, strict=True):
            row = {k: truth[k] for k in ("id", "cohort", "gtin", "truth", "view", "barcode_visible")}
            row["web_developer_exposure"] = web_exposure(truth)
            for phase, data in (("before", old), ("after", new)):
                ordinary = data["ordinary"]
                row[phase] = ordinary["photo_name"] or ""
                row[phase + "_reason"] = ordinary["photo_name_reason"]
                row[phase + "_flavour"] = ordinary["flavour_candidate"] or ""
                row[phase + "_order"] = data["strict"]["confirmed_order_sku"] or ""
                row[phase + "_codes"] = "|".join(data["strict"]["order_check_gtins"])
            group.append(row)
        combined.extend(group)
        strata = {"all": metrics(group)}
        for key in ("gtin", "view", "barcode_visible", "web_developer_exposure"):
            strata[key] = {value: metrics([r for r in group if r[key] == value]) for value in sorted({r[key] for r in group})}
        summary[cohort] = strata
    with (out / "python-rows.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=combined[0])
        writer.writeheader()
        writer.writerows(combined)
    (out / "python-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    score_folds(folder, out)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--ledgers", type=Path, default=STUDY)
    stage = cli.add_mutually_exclusive_group(required=True)
    stage.add_argument("--seal", action="store_true")
    stage.add_argument("--out", type=Path)
    args = cli.parse_args()
    if args.seal:
        seal(args.ledgers)
    else:
        score(args.ledgers, args.out)
