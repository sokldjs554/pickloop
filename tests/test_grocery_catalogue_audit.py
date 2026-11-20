"""Independent examples for the full-catalogue evidence audit."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/audit_grocery_catalogue.py"
REGISTRY = [
    {"id": 0, "name": "Lime", "group": "Fruit", "coarse": "Lime"},
    {"id": 1, "name": "Pear", "group": "Fruit", "coarse": "Pear"},
]


def load_audit():
    assert SCRIPT.is_file(), "The standalone grocery catalogue audit is missing"
    spec = importlib.util.spec_from_file_location("grocery_catalogue_audit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observation(split, path, class_id, truth, top1, prediction):
    return dict(split=split, path=path, sha256=hashlib.sha256(path.encode()).hexdigest(),
                class_id=str(class_id), truth=truth, top1=top1, prediction=prediction,
                score="0.9", margin="0.18")


def examples():
    return [
        observation("test", "test/Fruit/Lime/1.jpg", 0, "Lime", "Lime", "Lime"),
        observation("test", "test/Fruit/Lime/2.jpg", 0, "Lime", "Pear", "Pear"),
        observation("test", "test/Fruit/Pear/3.jpg", 1, "Pear", "Pear", "UNKNOWN"),
        observation("val", "val/Fruit/Lime/1.jpg", 0, "Lime", "Lime", "Lime"),
        observation("catalogue", "iconic-images-and-descriptions/Fruit/Lime/icon.jpg", 0, "Lime", "Pear", "Pear"),
        observation("catalogue", "iconic-images-and-descriptions/Fruit/Pear/icon.jpg", 1, "Pear", "Pear", "Pear"),
        observation("outside_test", "outside/a.jpg", -1, "UNKNOWN", "Pear", "UNKNOWN"),
        observation("outside_test", "outside/b.jpg", -1, "UNKNOWN", "Lime", "Lime"),
    ]


def previous(rows):
    # The old panel verifier recognized only Pear in this example. A closed gate
    # on a registered Pear is part of the previous known cohort.
    return [
        {"partition": part, "path": rows[i]["path"], "sha256": rows[i]["sha256"],
         "class_id": rows[i]["class_id"], "truth": truth, "prediction": prediction}
        for i, part, truth, prediction in [
            (4, "catalogue", "UNKNOWN", "UNKNOWN"), (0, "test_produce", "UNKNOWN", "UNKNOWN"),
            (2, "test_produce", "Pear", "UNKNOWN"), (3, "fresh_validation_produce", "UNKNOWN", "UNKNOWN"),
        ]
    ]


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def test_report_joins_by_hash_and_accounts_for_each_decision(tmp_path):
    audit = load_audit()
    rows = examples()
    report = audit.audit(REGISTRY, rows, previous(rows))
    output = tmp_path / "report"
    ui = tmp_path / "web/grocery-catalogue.json"
    audit.write_reports(report, output, ui)
    summary = json.loads((output / "summary.json").read_text())
    browser = json.loads(ui.read_text())
    assert browser["counts"] == dict(registered=2, test_total=3, correct=1, wrong=1,
                                     held=1, outside_total=2, outside_false_accepts=1)
    assert browser["previous_unknown"] == dict(total=3, correct=2, wrong=1, held=0)
    assert browser["classes"] == [
        dict(id=0, name="Lime", group="Fruit", test_total=2, correct=1, wrong=1, held=0),
        dict(id=1, name="Pear", group="Fruit", test_total=1, correct=0, wrong=0, held=1),
    ]
    assert summary["previous"]["known"]["held"] == 1
    assert summary["previous"]["by_partition"]["test_produce"]["unknown"]["correct"] == 1
    assert summary["previous"]["by_partition"]["test_produce"]["known"]["held"] == 1
    assert summary["splits"]["test"]["coverage"] == pytest.approx(2 / 3)
    assert summary["splits"]["test"]["accepted_accuracy"] == 0.5
    assert summary["splits"]["test"]["top1_correct"] == 2
    assert summary["groups"]["val"]["Fruit"]["correct"] == 1
    assert summary["class_coverage"]["test"] == {"evaluated": 2, "correctly_named_at_least_once": 1,
                                                 "zero_correct_names": ["Pear"], "macro_recall": 0.25}
    assert summary["class_coverage"]["val"]["evaluated"] == 1
    assert summary["class_coverage"]["val"]["zero_correct_names"] == []
    assert summary["outside"]["held"] == 1
    assert summary["outside"]["false_accepts_by_name"] == {"Lime": 1}
    assert summary["test_common_confusions"] == [{"truth": "Lime", "prediction": "Pear", "count": 1}]
    assert summary["test_lowest_recall"][0]["name"] == "Pear"
    classes = read_csv(output / "per-class.csv")
    pear_val = next(row for row in classes if row["split"] == "val" and row["name"] == "Pear")
    assert (pear_val["total"], pear_val["recall"], pear_val["coverage"]) == ("0", "", "")
    assert {"split": "test", "truth": "Pear", "prediction": "UNKNOWN", "count": "1"} in read_csv(output / "confusion.csv")
    joined = {row["sha256"]: row for row in read_csv(output / "previous-cohort.csv")}
    assert len(joined) == 4
    assert (joined[rows[4]["sha256"]]["truth"], joined[rows[4]["sha256"]]["outcome"]) == ("Lime", "wrong")
    assert (joined[rows[2]["sha256"]]["previous_truth"], joined[rows[2]["sha256"]]["outcome"]) == ("Pear", "held")


@pytest.mark.parametrize(("index", "field", "value", "error"), [
    (0, "truth", "Pear", "truth"), (0, "class_id", "1", "truth"),
    (0, "top1", "UNKNOWN", "top1"), (0, "prediction", "Pear", "top1"),
    (0, "score", "nan", "score"), (0, "margin", "inf", "margin"),
    (4, "sha256", "truncated", "sha256"),
    (6, "class_id", "1", "outside"), (6, "truth", "Pear", "outside"),
])
def test_invalid_provenance_or_predictions_fail_audit(index, field, value, error):
    audit = load_audit()
    rows = examples()
    prior = previous(rows)
    rows[index][field] = value
    with pytest.raises(ValueError, match=error):
        audit.audit(REGISTRY, rows, prior)


def test_train_overlap_and_duplicate_test_bytes_fail_audit():
    audit = load_audit()
    rows = examples()
    prior = previous(rows)
    with pytest.raises(ValueError, match="duplicate"):
        audit.audit(REGISTRY, rows, prior, [dict(path="train/Fruit/Lime/x.jpg", class_id=0, sha256=rows[0]["sha256"])])
    rows[6]["sha256"] = rows[3]["sha256"]
    with pytest.raises(ValueError, match="duplicate"):
        audit.audit(REGISTRY, rows, prior)


@pytest.mark.parametrize(("field", "value"), [
    ("sha256", "0" * 64), ("path", "test/Fruit/Lime/unrelated.jpg"), ("class_id", "1"),
    ("truth", "Pear"), ("partition", "fresh_validation_produce"),
])
def test_join_rejects_missing_bytes_or_conflicting_prior_identity(field, value):
    audit = load_audit()
    rows = examples()
    prior = previous(rows)
    prior[1][field] = value
    with pytest.raises(ValueError, match="previous"):
        audit.audit(REGISTRY, rows, prior)


def test_published_audit_rejects_alternative_registry_or_incomplete_group():
    audit = load_audit()
    rows = examples()
    with pytest.raises(ValueError, match="registry"):
        audit.verify_populations(REGISTRY, rows, previous(rows))
    with pytest.raises(ValueError, match="registry"):
        audit.audit([REGISTRY[0], REGISTRY[0]], rows, previous(rows))
    with pytest.raises(ValueError, match="outside"):
        audit.audit(REGISTRY, rows[:6], previous(rows))


def test_manifest_digest_covers_class_identity_and_ignores_row_order():
    audit = load_audit()
    rows = [{"path": "z.jpg", "class_id": "2", "sha256": "e" * 64},
            {"path": "a.jpg", "class_id": "0", "sha256": "f" * 64}]
    literal = hashlib.sha256(("a.jpg\t0\t" + "f" * 64 + "\nz.jpg\t2\t" + "e" * 64 + "\n").encode()).hexdigest()
    assert audit.manifest_hash(rows) == literal
    assert audit.manifest_hash(rows[::-1]) == literal
    rows[0]["class_id"] = "3"
    assert audit.manifest_hash(rows) != literal


def test_official_test_identity_rejects_same_size_label_substitution():
    audit = load_audit()
    previous_rows = read_csv(ROOT / "docs/experiments/carton-panels/predictions.csv")
    photos = [row for row in previous_rows if row["partition"] in ("test_cartons", "test_produce")]
    audit.verify_population("test", photos)
    photos[0]["class_id"] = "1"
    with pytest.raises(ValueError, match="test population"):
        audit.verify_population("test", photos)


def test_external_audit_rejects_missing_or_unrelated_negative_photos():
    audit = load_audit()
    outsides = examples()[-2:]
    with pytest.raises(ValueError, match="outside_test population"):
        audit.verify_population("outside_test", outsides)


def test_report_automatically_checks_training_manifest_next_to_predictions(tmp_path):
    audit = load_audit()
    assert audit.read_training(tmp_path) is None
    manifest = tmp_path / "training.csv"
    manifest.write_text("path,class_id,sha256\ntrain/Fruit/Pear/one.jpg,1," + "a" * 64 + "\n")
    assert audit.read_training(tmp_path) == [{"path": "train/Fruit/Pear/one.jpg",
                                              "class_id": "1", "sha256": "a" * 64}]
    with pytest.raises(FileNotFoundError):
        audit.read_training(tmp_path, tmp_path / "missing-explicit-manifest.csv")


def test_review_lists_only_named_mistakes_and_holds_from_previously_unknown_cases(tmp_path):
    audit = load_audit()
    rows = examples()
    prior = previous(rows)
    rows[5]["prediction"] = "UNKNOWN"
    prior.append(dict(partition="catalogue", path=rows[5]["path"], sha256=rows[5]["sha256"],
                      class_id="1", truth="UNKNOWN", prediction="UNKNOWN"))
    audit.write_reports(audit.audit(REGISTRY, rows, prior), tmp_path, tmp_path / "ui.json")
    review = read_csv(tmp_path / "previous-unknown-review.csv")
    assert [(r["truth"], r["top1"], r["prediction"], r["outcome"]) for r in review] == [
        ("Lime", "Pear", "Pear", "wrong"), ("Pear", "Pear", "UNKNOWN", "held")]
    assert [r["path"] for r in review] == [
        "iconic-images-and-descriptions/Fruit/Lime/icon.jpg", "iconic-images-and-descriptions/Fruit/Pear/icon.jpg"]
    assert [r["sha256"] for r in review] == [rows[4]["sha256"], rows[5]["sha256"]]
    assert review[0]["source_url"] == (
        "https://raw.githubusercontent.com/marcusklasson/GroceryStoreDataset/"
        "fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/iconic-images-and-descriptions/Fruit/Lime/icon.jpg")


def test_review_with_no_remaining_cases_still_writes_csv_headers(tmp_path):
    audit = load_audit()
    rows = examples()
    audit.write_reports(audit.audit(REGISTRY, rows, [previous(rows)[1]]), tmp_path, tmp_path / "ui.json")
    with (tmp_path / "previous-unknown-review.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        assert "truth" in reader.fieldnames
        assert list(reader) == []
