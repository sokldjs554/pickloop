"""Apply the post-study order rule to the sealed juice predictions, without refitting."""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
from pickloop.photo_readout import photo_readout


STUDY = Path(__file__).resolve().parents[1] / "docs/experiments/new-photos"


def report():
    ledger = (STUDY / "predictions-blind.jsonl").read_bytes()
    digest = sha256(ledger).hexdigest()
    seals = json.loads((STUDY / "predictions-seal.json").read_bytes())
    if digest != seals["predictions_sha256"]:
        raise ValueError("prediction ledger no longer matches its seal")
    raw = {row["id"]: row["after"] for row in map(json.loads, ledger.splitlines())}
    with (STUDY / "rows.csv").open(newline="") as stream:
        targets = [row for row in csv.DictReader(stream) if row["role"] in {"new_primary", "alternate_gtin_challenge"}]
    rows = []
    for row in targets:
        evidence = raw[row["id"]]
        if evidence["recognition_source"] == "baseline":
            raise ValueError("re-read this image in strict mode before claiming a confirmed SKU")
        decision = photo_readout(evidence, require_gtin=True)
        # This historical report used the frozen pre-size flavour as its photo name.
        decision["photo_name"] = None if evidence["prediction"] == "UNKNOWN" else evidence["prediction"]
        rows.append({key:decision[key] for key in ("photo_name", "printed_fruit_words", "confirmed_order_sku",
                                                   "confirmed_gtin", "order_check_gtins")} | {"id": row["id"]})
    return {"ledger_sha256": digest, "total": len(rows),
            "confirmed": sum(row["confirmed_order_sku"] is not None for row in rows),
            "method": "Post-study order confirmation on the frozen predictions. Not a separately trained or tested model.", "rows": rows}


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--check", action="store_true")
    check = args.parse_args().check
    path = STUDY / "order-readouts.json"
    data = json.dumps(report(), ensure_ascii=False, indent=2) + "\n"
    if check:
        if path.read_text() != data:
            raise SystemExit("order readouts differ from the frozen evidence")
    else:
        path.write_text(data)
