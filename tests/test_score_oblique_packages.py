import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import score_oblique_packages as scorer


def test_wrong_registered_false_accept_and_broader_names_have_distinct_counts():
    apple = "God-Morgon-Apple-Juice"
    assert scorer.outcome("UNKNOWN", "7310860007396", apple) == "wrong_registered"
    assert scorer.outcome("UNKNOWN", "7310860007396", scorer.PLAIN_RED) == "correct_broad"
    assert scorer.outcome(apple, "7310865074225", scorer.PLAIN_RED) == "wrong_broad"
    assert scorer.outcome(apple, "7310865074225", None) == "held"


def test_equal_count_with_duplicate_id_or_wrong_hash_is_rejected(tmp_path):
    labels = [{"id": "a", "sha256": "ha"}, {"id": "b", "sha256": "hb"}]
    path = tmp_path / "ledger"
    for payload, error in [([labels[1], labels[1]], "IDs"), ([labels[1], {"id": "a", "sha256": "x"}], "checksum")]:
        path.write_text("".join(json.dumps(row) + "\n" for row in payload))
        with pytest.raises(ValueError, match=error):
            scorer.predictions(path, labels)
    path.write_text("".join(json.dumps(row) + "\n" for row in reversed(labels)))
    assert set(scorer.predictions(path, labels)) == {"a", "b"}


def test_frozen_views_reproduce_shipped_baselines():
    labels = scorer.labels_for("archive")
    flags = {r["id"]: r["suspected_same_gtin_setting"] for r in scorer.records(scorer.STUDY / "expanded-acquisition-review.csv")}
    for runtime, fronts, sides, false_accepts in [("python", 33, 2, 0), ("browser", 29, 1, 1)]:
        path, checksum = scorer.baseline_path(runtime, "archive")
        data = scorer.predictions(path, labels, checksum)
        paired = [scorer.row_for(l, runtime, flags[l["id"]], data[l["id"]], data[l["id"]]) for l in labels]
        scores = scorer.strata(paired)
        assert scores["archive_registered_side_visible"]["n"] == 15
        assert scores["archive_registered_side_visible"]["baseline"]["correct_registered"] == sides
        assert scores["archive_registered_front"]["baseline"]["correct_registered"] == fronts
        assert scores["archive_controls"]["baseline"]["wrong_registered"] == false_accepts
        assert scores["archive_registered_side_excluding_flagged_setting"]["n"] == 12


def test_product_timeout_is_distinct_from_a_hold():
    label = {"id": "photo", "sha256": "hash", "cohort": "supplemental", "gtin": "other", "truth": "UNKNOWN"}
    row = scorer.row_for(label, "browser", "", {"product": None, "barcode_order": None}, {"status": "timeout"})
    stats = scorer.metric([row])
    assert stats["baseline"]["held"] == 1
    assert stats["candidate"]["held"] == 0
    assert stats["candidate"]["runtime_error"] == 1
