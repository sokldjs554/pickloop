"""Generate the static lookup for photos treated as unregistered in the two-juice experiment."""
import argparse
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import quote

from audit_grocery_catalogue import EVIDENCE, PHOTO_URL, ROOT, UNKNOWN, audit, read_csv, verify_populations


def generate(evidence, previous):
    registry = json.loads((evidence / "registry.json").read_text(encoding="utf-8"))
    predictions = read_csv(evidence / "predictions.csv")
    old = read_csv(previous)
    verify_populations(registry, predictions, old)
    expected = audit(registry, predictions, old)["cohort"]
    cohort = read_csv(evidence / "previous-cohort.csv")
    if cohort != expected:
        raise ValueError("previous-cohort.csv differs from the pinned cohort joined to the recorded predictions")

    photos = [row for row in cohort if row["previous_truth"] == UNKNOWN]
    reviews = read_csv(evidence / "previous-unknown-review.csv")
    review_fields = ("partition", "split", "path", "sha256", "class_id", "truth", "top1", "prediction", "outcome")
    expected_reviews = [{**{key: row[key] for key in review_fields}, "source_url": PHOTO_URL + quote(row["path"])}
                        for row in photos if row["outcome"] in ("wrong", "held")]
    if reviews != expected_reviews:
        raise ValueError("previous-unknown-review.csv differs from the recorded wrong or held photos")

    # Keep one line per photo so changed predictions have small, readable diffs.
    records = []
    for row in photos:
        record = {"id": row["sha256"], "path": row["path"], "truth": row["truth"],
                  "prediction": row["prediction"], "status": row["outcome"]}
        records.append(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
    return '{"source_base":' + json.dumps(PHOTO_URL) + ',"photos":[\n' + ",\n".join(records) + "\n]}\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--previous", type=Path, default=ROOT / "docs/experiments/carton-panels/predictions.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "web/data/grocery-previous-photos.json")
    parser.add_argument("--check", action="store_true", help="verify the published lookup without writing files")
    args = parser.parse_args()
    result = generate(args.evidence, args.previous).encode("utf-8")
    if args.check:
        if args.output.read_bytes() != result:
            parser.exit(1, f"{args.output} differs from the recorded photo evidence\n")
        print(f"Checked {args.output}")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=args.output.parent, delete=False) as stream:
            stream.write(result)
        Path(stream.name).replace(args.output)
        print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
