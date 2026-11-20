"""Verify the full Grocery Store Dataset prediction ledger and regenerate its reports."""
import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/experiments/grocery-catalogue"
PHOTO_URL = ("https://raw.githubusercontent.com/marcusklasson/GroceryStoreDataset/"
             "fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/")
UNKNOWN = "UNKNOWN"
KNOWN_SPLITS = ("test", "val", "catalogue")
PREVIOUS_SPLITS = {"test_cartons": "test", "test_produce": "test",
                   "fresh_validation_produce": "val", "catalogue": "catalogue"}

# Original JPG bytes and official fine IDs at GroceryStoreDataset fc80ba90.
# Each digest hashes sorted UTF-8 rows; see manifest_hash for the serialization.
POPULATIONS = {
    "train": (2640, "f65ce985be4ae210271c6136cd96e805fcd3b64f9da8575d4b55c0e40402603c"),
    "test": (2485, "b9071fe2dca5bded45ae63a37d6d015910d0e32fe3111f93ae7d6acf69e4b756"),
    "val": (296, "bba6d3df2138bb6dee1ba0497019f43b5ca8988d34ec16999a18fc5d436c8173"),
    "catalogue": (81, "a3caca5662d7fa147fdad5fb54613989d3a5c2c290255d61c275d49e419ae2c6"),
    # The 11 held-out Freiburg categories in catalogue_outside_source.py.
    "outside_test": (176, "abc8410aecc39125c5d14fbe0d74969c19d62b64413fd88342357caa1c58158c"),
}
REGISTRY_HASH = "e80ddc641e0c4b3cc3f25f33114c4c354d47c7eb67bfc19950dc5abd14172d1a"
PREVIOUS_HASH = "3298f61bc5692da720b4050468f49c76e771ca4d216d63f3129e3a50079366c0"


def digest_records(records):
    digest = hashlib.sha256()
    for record in sorted(records):
        digest.update(("\t".join(map(str, record)) + "\n").encode("utf-8"))
    return digest.hexdigest()


def manifest_hash(rows):
    return digest_records((row["path"], int(row["class_id"]), row["sha256"]) for row in rows)


def verify_population(split, rows):
    if (len(rows), manifest_hash(rows)) != POPULATIONS[split]:
        raise ValueError(f"{split} population differs from the pinned paths, labels or image hashes")


def verify_populations(registry, predictions, previous, train=None):
    registry_hash = digest_records((int(c["id"]), c["name"], c["group"], c["coarse"]) for c in registry)
    if (len(registry), registry_hash) != (81, REGISTRY_HASH):
        raise ValueError("registry differs from the 81 official fine classes")
    populations = {split: [r for r in predictions if r["split"] == split] for split in (*KNOWN_SPLITS, "outside_test")}
    if train is not None:
        populations["train"] = train
    for split, rows in populations.items():
        verify_population(split, rows)
    previous_hash = digest_records(
        (r["sha256"], r["path"], int(r["class_id"]), r["partition"], r["truth"], r["prediction"])
        for r in previous)
    if (len(previous), previous_hash) != (2712, PREVIOUS_HASH):
        raise ValueError("previous evidence differs from the 2,712 prior panel-verifier rows")


def outcome(row):
    if row["prediction"] == UNKNOWN:
        return "held"
    return "correct" if row["prediction"] == row["truth"] else "wrong"


def named_metrics(rows):
    counts = Counter(outcome(row) for row in rows)
    total = len(rows)
    accepted = counts["correct"] + counts["wrong"]
    return {
        "total": total, "correct": counts["correct"], "wrong": counts["wrong"], "held": counts["held"],
        "accepted": accepted, "top1_correct": sum(r["top1"] == r["truth"] for r in rows),
        "recall": counts["correct"] / total if total else None,
        "coverage": accepted / total if total else None,
        "accepted_accuracy": counts["correct"] / accepted if accepted else None,
    }


def validate_unique_images(predictions, train):
    hashes, paths = {}, set()
    for row in [*predictions, *(train or [])]:
        digest, path = row["sha256"], row["path"]
        if not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError(f"invalid sha256 at {path}")
        if digest in hashes:
            raise ValueError(f"duplicate image bytes in {hashes[digest]} and {path}")
        if not path or path in paths:
            raise ValueError(f"empty or duplicate image path: {path}")
        hashes[digest] = path
        paths.add(path)


def validate_predictions(registry, predictions, train):
    by_id = {int(c["id"]): c["name"] for c in registry}
    names = set(by_id.values())
    if len(names) != len(registry) or set(by_id) != set(range(len(registry))) or UNKNOWN in names:
        raise ValueError("registry must contain unique fine names and consecutive zero-based IDs")
    validate_unique_images(predictions, train)
    observed = set()
    for row in predictions:
        split, path = row["split"], row["path"]
        observed.add(split)
        if split == "outside_test":
            if int(row["class_id"]) != -1 or row["truth"] != UNKNOWN:
                raise ValueError(f"outside rows require class_id -1 and UNKNOWN truth at {path}")
        elif split in KNOWN_SPLITS:
            if row["truth"] != by_id.get(int(row["class_id"])):
                raise ValueError(f"fine class ID and truth disagree at {path}")
        else:
            raise ValueError(f"unexpected split {split} at {path}")
        if row["top1"] not in names or row["prediction"] not in (row["top1"], UNKNOWN):
            raise ValueError(f"invalid top1 name or gated prediction at {path}")
        for field in ("score", "margin"):
            if not math.isfinite(float(row[field])):
                raise ValueError(f"invalid {field} at {path}")
    missing = set((*KNOWN_SPLITS, "outside_test")) - observed
    if missing:
        raise ValueError(f"missing evidence for {', '.join(sorted(missing))}")


def compare_previous(predictions, previous):
    by_hash = {row["sha256"]: row for row in predictions}
    cohort = []
    seen = set()
    for old in previous:
        digest = old["sha256"]
        new = by_hash.get(digest)
        if new is None or digest in seen:
            raise ValueError(f"missing or duplicate previous image {old['path']}")
        seen.add(digest)
        if (old["path"] != new["path"] or int(old["class_id"]) != int(new["class_id"])
                or new["split"] != PREVIOUS_SPLITS.get(old["partition"])
                or old["truth"] not in (UNKNOWN, new["truth"])):
            raise ValueError(f"previous identity disagrees at {old['path']}")
        cohort.append({
            "sha256": digest, "path": new["path"], "partition": old["partition"], "split": new["split"],
            "previous_truth": old["truth"], "previous_prediction": old["prediction"],
            "class_id": new["class_id"], "truth": new["truth"], "top1": new["top1"],
            "prediction": new["prediction"], "outcome": outcome(new),
        })

    def cohorts(rows):
        return {"unknown": named_metrics([r for r in rows if r["previous_truth"] == UNKNOWN]),
                "known": named_metrics([r for r in rows if r["previous_truth"] != UNKNOWN])}

    partitions = sorted({row["partition"] for row in cohort})
    stats = {"total": len(cohort), **cohorts(cohort),
             "by_partition": {p: cohorts([r for r in cohort if r["partition"] == p]) for p in partitions}}
    return cohort, stats


def audit(registry, predictions, previous, train=None):
    validate_predictions(registry, predictions, train)
    cohort, prior_stats = compare_previous(predictions, previous)
    by_split = defaultdict(list)
    by_class = defaultdict(list)
    by_group = defaultdict(list)
    by_id = {int(c["id"]): c for c in registry}
    confusion = Counter()
    for row in predictions:
        split = row["split"]
        by_split[split].append(row)
        confusion[split, row["truth"], row["prediction"]] += 1
        if split in KNOWN_SPLITS:
            class_id = int(row["class_id"])
            by_class[split, class_id].append(row)
            by_group[split, by_id[class_id]["group"]].append(row)

    outside = by_split["outside_test"]
    outside_names = Counter(r["prediction"] for r in outside if r["prediction"] != UNKNOWN)
    outside_accepts = sum(outside_names.values())
    splits = {split: named_metrics(by_split[split]) for split in KNOWN_SPLITS}
    group_names = sorted({c["group"] for c in registry})
    classes = [{"split": split, **by_id[i], **named_metrics(by_class[split, i])}
               for split in KNOWN_SPLITS for i in sorted(by_id)]
    class_coverage = {}
    for split in KNOWN_SPLITS:
        evaluated = [c for c in classes if c["split"] == split and c["total"]]
        missed = [c["name"] for c in evaluated if not c["correct"]]
        class_coverage[split] = {"evaluated": len(evaluated), "correctly_named_at_least_once": len(evaluated) - len(missed),
                                 "zero_correct_names": missed, "macro_recall": sum(c["recall"] for c in evaluated) / len(evaluated)}
    test_classes = [c for c in classes if c["split"] == "test"]
    mistakes = [{"truth": truth, "prediction": prediction, "count": count}
                for (split, truth, prediction), count in sorted(confusion.items(), key=lambda kv: (-kv[1], kv[0]))
                if split == "test" and prediction not in (truth, UNKNOWN)]
    lowest = sorted((c for c in test_classes if c["total"]), key=lambda c: (c["recall"], c["id"]))[:10]
    test = splits["test"]
    counts = {"registered": len(registry), "test_total": test["total"],
              **{k: test[k] for k in ("correct", "wrong", "held")},
              "outside_total": len(outside), "outside_false_accepts": outside_accepts}
    web = {"counts": counts,
           "previous_unknown": {k: prior_stats["unknown"][k] for k in ("total", "correct", "wrong", "held")},
           "classes": [{"id": c["id"], "name": c["name"], "group": c["group"], "test_total": c["total"],
                        "correct": c["correct"], "wrong": c["wrong"], "held": c["held"]} for c in test_classes]}
    summary = {
        "counts": counts, "splits": splits, "class_coverage": class_coverage,
        "groups": {s: {g: named_metrics(by_group[s, g]) for g in group_names} for s in KNOWN_SPLITS},
        "outside": {"total": len(outside), "held": len(outside) - outside_accepts, "false_accepts": outside_accepts,
                    "false_accept_rate": outside_accepts / len(outside), "false_accepts_by_name": dict(sorted(outside_names.items()))},
        "previous": prior_stats, "test_common_confusions": mistakes[:10], "test_lowest_recall": lowest,
        "integrity": {"distinct_evaluation_sha256": len(predictions),
                      "verified_training_hashes": len(train) if train is not None else None,
                      "population_sha256": {s: manifest_hash(by_split[s]) for s in (*KNOWN_SPLITS, "outside_test")}},
    }
    if train is not None:
        summary["integrity"]["population_sha256"]["train"] = manifest_hash(train)
    cells = [{"split": s, "truth": t, "prediction": p, "count": n} for (s, t, p), n in sorted(confusion.items())]
    return {"summary": summary, "web": web, "classes": classes, "confusion": cells, "cohort": cohort}


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def read_training(evidence, supplied=None):
    path = supplied or evidence / "training.csv"
    return read_csv(path) if supplied is not None or path.exists() else None


def write_reports(report, out, web_data):
    out.mkdir(parents=True, exist_ok=True)
    web_data.parent.mkdir(parents=True, exist_ok=True)
    for filename, key in (("per-class.csv", "classes"), ("confusion.csv", "confusion"), ("previous-cohort.csv", "cohort")):
        rows = report[key]
        with (out / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    fields = ("partition", "split", "path", "sha256", "class_id", "truth", "top1", "prediction", "outcome")
    with (out / "previous-unknown-review.csv").open("w", encoding="utf-8", newline="") as stream:
        review = csv.DictWriter(stream, fieldnames=(*fields, "source_url"), lineterminator="\n")
        review.writeheader()
        for row in report["cohort"]:
            if row["previous_truth"] == UNKNOWN and row["outcome"] in ("wrong", "held"):
                review.writerow({**{k: row[k] for k in fields}, "source_url": PHOTO_URL + quote(row["path"])})
    for path, key in ((out / "summary.json", "summary"), (web_data, "web")):
        path.write_text(json.dumps(report[key], indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE, help="directory containing registry.json and predictions.csv")
    parser.add_argument("--previous", type=Path, default=ROOT / "docs/experiments/carton-panels/predictions.csv")
    parser.add_argument("--train-manifest", type=Path, help="override training.csv in the evidence directory")
    parser.add_argument("--web-data", type=Path, default=ROOT / "web/data/grocery-catalogue.json")
    args = parser.parse_args()
    registry = json.loads((args.evidence / "registry.json").read_text(encoding="utf-8"))
    predictions = read_csv(args.evidence / "predictions.csv")
    previous = read_csv(args.previous)
    train = read_training(args.evidence, args.train_manifest)
    verify_populations(registry, predictions, previous, train)
    report = audit(registry, predictions, previous, train)
    write_reports(report, args.evidence, args.web_data)
    print(json.dumps({"counts": report["web"]["counts"], "previous_unknown": report["web"]["previous_unknown"]}, indent=2))


if __name__ == "__main__":
    main()
