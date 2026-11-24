import csv
import os
from pathlib import Path
from shutil import which

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
APPLE = "God-Morgon-Apple-Juice"
ORANGE = "God-Morgon-Orange-Juice"
MIX = "God-Morgon-Orange-Red-Grapefruit-Juice"


def test_readable_print_recovers_an_upstream_hold():
    from pickloop.product_text import recognize_exact

    if which("tesseract") is None:
        pytest.skip("optional Tesseract executable unavailable")
    photo = Image.new("RGB", (410, 520), "white")
    pen = ImageDraw.Draw(photo)
    pen.rectangle((90, 20, 315, 500), fill=(26, 26, 29))
    pen.text((100, 95), "GOD MORGON", font_size=29, fill="white")
    pen.text((115, 205), "APPLE", font_size=42, fill=(232, 220, 121))
    final = recognize_exact({"prediction": "UNKNOWN", "top1": ORANGE}, lambda: np.asarray(photo))
    assert final["prediction"] == APPLE
    assert final["baseline_prediction"] == "UNKNOWN"
    assert final["recognition_source"] == "package_text"


@pytest.mark.parametrize("extra", ["BLOOD ORANGE & APPLE", "BLODAPELSIN", "ORGANIC", "NO PULP", "250 ml", "1.75-litre", "pack of 6", "6 x 1000 ml",
                                   "OTHER BRAND BRAVO", "MANGO", "Ananas", "Breakfast blend"])
def test_visible_qualifier_vetoes_otherwise_consistent_target(extra):
    from pickloop.product_text import printed_flavour

    name, _ = printed_flavour(["GOD MOR G@N ORANGE", "GOD MOR GON ORANGE", extra])
    assert name is None


def test_mixed_flavour_needs_both_fruits_and_matching_brand():
    from pickloop.product_text import printed_flavour

    assert printed_flavour(["GOD MOR G@N ORANGE RED GRAPEFRUIT", "ORANGE & RED GRAPEFRUIT"])[0] == MIX
    assert printed_flavour(["GOD MOR G@N ORANGE", "RED GRAPEFRUIT"])[0] is None
    assert printed_flavour(["TROPICANA ORANGE", "ORANGE"])[0] is None
    assert printed_flavour(["GOD MOR G@N", "ORANGE"])[0] is None
    assert printed_flavour(["GOD MOR G@N APPLE", "APPLE", "ORANGE"])[0] is None


def test_existing_non_target_decision_skips_ocr():
    from pickloop.product_text import recognize_exact

    def unexpected():
        pytest.fail("non-target accepted decision requested pixels")

    assert recognize_exact({"top1":"Banana", "prediction":"Banana"}, unexpected)["prediction"] == "Banana"


@pytest.mark.skipif(not os.environ.get("PICKLOOP_JUICE_DEV_ROOT"), reason="locally fetched original development images")
def test_previous_seven_external_development_cases():
    from hashlib import sha256
    from pickloop.product_text import recognize_exact

    sample_root = Path(os.environ["PICKLOOP_JUICE_DEV_ROOT"])
    evidence = ROOT / "docs/experiments/juice-gate"
    with (evidence / "external-manifest.csv").open() as f:
        samples = list(csv.DictReader(f))
    rows = []
    for file in ("external-predictions.csv", "external-screened-predictions.csv"):
        with (evidence / file).open() as f:
            rows.extend(csv.DictReader(f))
    baseline = {r["id"]: r for r in rows}
    assert len(samples) == 7
    for sample in samples:
        path = sample_root / sample["path"]
        assert sha256(path.read_bytes()).hexdigest() == sample["sha256"]
        before = baseline[sample["sample_id"]]
        with Image.open(path) as f:
            pixels = np.asarray(ImageOps.exif_transpose(f).convert("RGB"))
        after = recognize_exact(dict(prediction=before["before"], top1=before["raw_top1"]), lambda: pixels)
        assert after["prediction"] == sample["truth"], sample["sample_id"]


def test_registered_bars_recover_an_unknown_and_unknown_bars_veto(tmp_path):
    from test_pack_barcode import ean_image
    from pickloop.product_text import recognize_exact

    previous = {"prediction": "UNKNOWN", "top1": ORANGE}
    known = recognize_exact(previous, lambda: ean_image("7310860007259"))
    assert (known["prediction"], known["recognition_source"], known["recognition_gtins"]) == (
        MIX, "barcode", ["7310860007259"])
    outside = recognize_exact({"prediction": ORANGE, "top1": ORANGE}, lambda: ean_image("7313619002413"))
    assert (outside["prediction"], outside["recognition_reason"]) == ("UNKNOWN", "unregistered_gtin")
    pair = np.vstack((ean_image("7310860007259"), ean_image("7310860007372")))
    ambiguous = recognize_exact(previous, lambda: pair)
    assert (ambiguous["prediction"], ambiguous["recognition_reason"]) == ("UNKNOWN", "multiple_gtins")


def test_readable_flavour_does_not_override_a_contradictory_valid_barcode(monkeypatch):
    from test_pack_barcode import ean_image
    from pickloop import product_text

    monkeypatch.setattr(product_text, "read_print", lambda rgb, candidate: (
        APPLE, "brand_and_apple", ["GOD MORGON APPLE", "APPLE"], "package_text"))
    result = product_text.recognize_exact({"prediction": ORANGE, "top1": ORANGE}, lambda: ean_image("7310860007259"))
    assert (result["prediction"], result["recognition_reason"]) == ("UNKNOWN", "barcode_text_conflict")
    assert result["recognition_text"] == ["GOD MORGON APPLE", "APPLE"]


def test_repeated_unregistered_red_grapefruit_print_vetoes_plain_orange_barcode(monkeypatch):
    from test_pack_barcode import ean_image
    from pickloop import product_text

    monkeypatch.setattr(product_text, "read_print", lambda rgb, candidate: (
        None, "incomplete_mixed_flavour", ["GOD MORGON RED GRAPEFRUIT", "RED GRAPEFRUIT"], "package_text"))
    result = product_text.recognize_exact({"prediction": ORANGE, "top1": ORANGE}, lambda: ean_image("7310860007372"))
    assert (result["prediction"], result["recognition_reason"]) == ("UNKNOWN", "barcode_text_conflict")
