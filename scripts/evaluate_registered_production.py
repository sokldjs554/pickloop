"""Replay and score the follow-up recognition system without modifying the first study."""

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from evaluate_registered_recall import STUDY, digest, fetch, infer, records, verify
from score_registered_recall import TARGETS, ledger, web_exposure


PHASES = ("before", "v1", "production")
COHORTS = ("archive", "public", "legacy-validation")
POLICY_CASE = "RR-cbaea96197c4f7c6"
COMPOSITION_CASE = "RR-08be70619c12080f"


def files_for(folder, cohort):
    verify(cohort)
    ids = [r["id"] for r in records(STUDY / f"{cohort}-blind.csv")]
    phases = ("before", "v1", "production") if cohort == "legacy-validation" else ("before", "after", "production")
    return [ledger(folder, cohort, name, ids) for name in phases]


def seal(folder):
    hashes = {}
    for cohort in COHORTS:
        for path, _ in files_for(folder, cohort):
            hashes[path.name] = digest(path.read_bytes())
    with (folder / "production-prediction-seal.json").open("x") as stream:
        json.dump({"utc": datetime.now(timezone.utc).isoformat(), "sha256": hashes}, stream, indent=2)
        stream.write("\n")


def status(row):
    if row["id"] == COMPOSITION_CASE:
        return "same enrolled composition"
    if row["id"] == POLICY_CASE:
        return "targeted policy retest"
    if row["cohort"] == "public":
        return "untargeted public foil"
    return "archive regression" if row["cohort"] == "archive" else "supplemental validation"


def scores(batch):
    result = {"n": len(batch), "registered": sum(r["truth"] in TARGETS for r in batch)}
    for phase in PHASES:
        for field in (phase, phase + "_order"):
            result[field] = {
                "correct_registered": sum(r["truth"] in TARGETS and r[field] == r["truth"] for r in batch),
                "wrong_name_on_registered": sum(r["truth"] in TARGETS and bool(r[field]) and r[field] != r["truth"]
                                                for r in batch),
                "held_registered": sum(r["truth"] in TARGETS and not r[field] for r in batch),
                "falsely_named_as_registered": sum(r["truth"] not in TARGETS and r[field] in TARGETS for r in batch),
                "other_catalogue_name_on_outside": sum(r["truth"] not in TARGETS and bool(r[field])
                                                       and r[field] not in TARGETS for r in batch),
                "empty_on_outside": sum(r["truth"] not in TARGETS and not r[field] for r in batch),
            }
    result["changed_photo_names_v1_to_production"] = sum(r["v1"] != r["production"] for r in batch)
    result["changed_orders_v1_to_production"] = sum(r["v1_order"] != r["production_order"] for r in batch)
    return result


def score(folder, out):
    hashes = json.loads((folder / "production-prediction-seal.json").read_text())["sha256"]
    prior = json.loads((STUDY / "python-prediction-seal.json").read_text())["sha256"]
    rows = []
    for cohort in COHORTS:
        files = files_for(folder, cohort)
        labels = records(STUDY / f"{cohort}-labels.csv")
        for path, _ in files:
            if digest(path.read_bytes()) != hashes[path.name] or path.name in prior and prior[path.name] != hashes[path.name]:
                raise ValueError(f"Prediction ledger differs for {path.name}")
        for label, *states in zip(labels, *(x[1] for x in files), strict=True):
            if any(s["id"] != label["id"] for s in states):
                raise ValueError(f"Labels differ for {cohort}")
            r = {k: label[k] for k in ("id", "cohort", "gtin", "truth")}
            r["role"] = status(r)
            r["web_developer_exposure"] = web_exposure(label) if cohort == "archive" else ""
            for phase, state in zip(PHASES, states, strict=True):
                r[phase] = state["ordinary"]["photo_name"] or ""
                r[phase + "_order"] = state["strict"]["confirmed_order_sku"] or ""
                r[phase + "_reason"] = state["ordinary"]["photo_name_reason"]
            rows.append(r)
    main = [r for r in rows if r["cohort"] != "legacy-validation"]
    subsets = {k: [r for r in rows if r["cohort"] == k] for k in COHORTS}
    subsets.update({v: [r for r in rows if r["role"] == v] for v in sorted({r["role"] for r in rows})})
    subsets["main excluding enrolled composition"] = [r for r in main if r["id"] != COMPOSITION_CASE]
    subsets["main excluding enrolled composition and policy retest"] = [r for r in main if r["id"] not in (POLICY_CASE, COMPOSITION_CASE)]
    subsets["archive unviewed by browser developer"] = [r for r in main if r["web_developer_exposure"] == "unviewed"]
    out.mkdir(exist_ok=True, parents=True)
    with (out / "production-rows.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    (out / "production-summary.json").write_text(json.dumps({k: scores(b) for k, b in subsets.items()}, indent=2) + "\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("stage", choices=("fetch", "infer", "seal", "score"))
    cli.add_argument("--cohort", choices=COHORTS)
    cli.add_argument("--photos", type=Path)
    cli.add_argument("--ledgers", type=Path, default=STUDY)
    cli.add_argument("--out", type=Path)
    args = cli.parse_args()
    if args.stage in ("fetch", "infer"):
        if not args.cohort or not args.photos:
            cli.error("fetch and inference require --cohort and --photos")
        verify(args.cohort)
        if args.stage == "fetch":
            fetch(args.photos, args.cohort)
        elif args.out:
            infer(args.photos, args.cohort, args.out)
        else:
            cli.error("inference requires --out")
    elif args.stage == "seal":
        seal(args.ledgers)
    elif args.out:
        score(args.ledgers, args.out)
    else:
        cli.error("scoring requires --out")
