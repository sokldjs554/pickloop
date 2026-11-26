"""Fetch hash-pinned originals and score a completed browser replay against frozen labels."""
import argparse
import csv
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent


def read_csv(name):
    with (HERE / name).open(newline="") as stream:
        return list(csv.DictReader(stream))


def inputs():
    freeze = json.loads((HERE / "freeze.json").read_text())
    for name, digest in freeze["manifest_sha256"].items():
        if sha256((HERE / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Manifest changed: {name}")
    labels = {row["id"]: row for row in read_csv("labels.csv")}
    blind = read_csv("blind.csv")
    if len(blind) != len(labels) or {r["id"] for r in blind} != set(labels):
        raise ValueError("Manifest populations disagree")
    for row in blind:
        label = labels[row["id"]]
        if row["sha256"] != label["sha256"] or label["truth"] != "UNKNOWN":
            raise ValueError(f"Unexpected hash or label: {row['id']}")
    return labels, blind


def fetch(directory):
    labels, blind = inputs()
    directory.mkdir(parents=True, exist_ok=True)
    for item in blind:
        path = directory / item["path"]
        if path.exists():
            data = path.read_bytes()
        else:
            request = Request(labels[item["id"]]["image_url"], headers={"User-Agent": "PickLoop-study/1.0"})
            with urlopen(request, timeout=45) as response:
                data = response.read()
        if sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"Original bytes changed for {item['id']}")
        if not path.exists():
            path.write_bytes(data)


def reason(row):
    optical, display = row["optical_display"], row["display"]
    if row["barcode_order"]:
        return "false_order"
    if row["product"]:
        return "false_registered_photo"
    if "미등록 바코드" in optical:
        return "explicit_unregistered_barcode"
    if "미등록 용량" in display and "등록 범위 밖의 1.75 L" in display:
        return "incompatible_foreground_capacity"
    if "미등록 제품군" in display:
        return "outside_product_family"
    if "목록 밖" in display:
        return "outside_gallery"
    if "묶음 수량" in display or "품목 또는 맛" in display:
        return "contradictory_package_print"
    if "구별하기 어렵습니다" in display:
        return "ambiguous_hold"
    if "구별할 특징이 부족" in display:
        return "no_evidence_hold"
    raise ValueError(f"Unexpected completed decision: {row['id']} {optical!r} {display!r}")


def score(ledger):
    labels, _ = inputs()
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    if len(rows) != len(labels) or {r["id"] for r in rows} != set(labels):
        raise ValueError("Completed browser IDs disagree with the frozen cohort")
    report = {}
    for cohort in ("strict", "lookalike_control"):
        outcomes = Counter()
        codes = Counter()
        products = set()
        images = photo_errors = order_errors = 0
        outside_barcode_in_identity = 0
        for row in rows:
            label = labels[row["id"]]
            if row["sha256"] != label["sha256"]:
                raise ValueError(f"Browser read unexpected bytes: {row['id']}")
            if label["cohort"] != cohort:
                continue
            observed = reason(row)
            outcomes[observed] += 1
            if observed == "explicit_unregistered_barcode":
                if "미등록 상품" in row["display"]:
                    outside_barcode_in_identity += 1
                decoded = re.findall(r"(?<!\d)\d{13}(?!\d)", row["optical_display"])
                codes["correct" if decoded == [label["gtin"]] else "different"] += 1
            products.add(label["gtin"])
            images += 1
            photo_errors += bool(row["product"])
            order_errors += bool(row["barcode_order"])
        report[cohort] = dict(images=images, distinct_gtins=len(products),
                              false_registered_product=photo_errors, false_order=order_errors,
                              held_product=images-photo_errors, held_order=images-order_errors,
                              reasons=dict(outcomes), decoded_outside_gtin=dict(codes),
                              unregistered_barcode_in_product_status=outside_barcode_in_identity)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch").add_argument("directory", type=Path)
    commands.add_parser("score").add_argument("ledger", type=Path)
    check = commands.add_parser("check-reader")
    check.add_argument("web", type=Path)
    check.add_argument("--phase", choices=["candidate", "final", "endpoint"], default="final")
    options = parser.parse_args()
    if options.command == "fetch":
        fetch(options.directory)
    elif options.command == "check-reader":
        hashes = json.loads((HERE / f"{options.phase}-reader.json").read_text())
        for filename, expected in hashes.items():
            actual = sha256((options.web / filename).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"Reader component changed: {filename}")
        print(f"Verified {len(hashes)} {options.phase} components")
    else:
        print(json.dumps(score(options.ledger), ensure_ascii=False, indent=2))
