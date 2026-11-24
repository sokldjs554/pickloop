import numpy as np
import pytest


def test_two_matching_reads_confirm_a_flavour_and_one_conflicting_read_blocks_it():
    from pickloop.juice_gate import confirmed_flavour
    assert confirmed_flavour(["orange & red grapefruit", "orange red grapefruit", ""], True) == (
        "God-Morgon-Orange-Red-Grapefruit-Juice", "verified")
    assert confirmed_flavour(["apple", "apple", ""], True) == ("God-Morgon-Apple-Juice", "verified")
    for reads in (["orange", "orange", "orange & red"],
                  ["apple", "apple", "blood orange"], ["orange", "", ""]):
        assert confirmed_flavour(reads, True)[0] is None


def test_unregistered_grapefruit_and_unbranded_flavour_text_cannot_verify_an_orange():
    from pickloop.juice_gate import confirmed_flavour
    assert confirmed_flavour(["red grapefruit", "red grapefruit"], True)[0] is None
    assert confirmed_flavour(["orange", "orange"], False)[0] is None
    assert confirmed_flavour(["GOD MOR GON ORANGE", "God Morgon orange"], False)[0] == "God-Morgon-Orange-Juice"


def test_non_target_and_upstream_holds_skip_image_access():
    from pickloop.juice_gate import apply_juice_gate
    def fail():
        pytest.fail("gate accessed an unnecessary image")
    non_target = {"top1": "Banana", "prediction": "Banana"}
    assert apply_juice_gate(non_target, fail) == non_target
    held = {"top1": "God-Morgon-Orange-Juice", "prediction": "UNKNOWN"}
    assert apply_juice_gate(held, fail)["prediction"] == "UNKNOWN"


def test_a_blank_camera_crop_fails_closed():
    from pickloop.juice_gate import apply_juice_gate
    rgb = np.full((160, 200, 3), 80, dtype=np.uint8)
    result = apply_juice_gate({"top1": "God-Morgon-Orange-Juice", "prediction": "God-Morgon-Orange-Juice"},
                              lambda: rgb)
    assert result["prediction"] == "UNKNOWN"
    assert result["juice_gate_reason"] == "no_single_panel"


def test_gate_can_correct_an_accepted_target_using_image_evidence(monkeypatch):
    from pickloop import juice_gate
    monkeypatch.setattr(juice_gate, "read_package", lambda rgb: (["orange & red grapefruit"] * 3, True))
    result = juice_gate.apply_juice_gate({"top1": "God-Morgon-Orange-Juice", "prediction": "God-Morgon-Orange-Juice"},
                                         lambda: np.zeros((12, 12, 3), np.uint8))
    assert result["prediction"] == "God-Morgon-Orange-Red-Grapefruit-Juice"
    assert result["juice_gate_original"] == "God-Morgon-Orange-Juice"


def test_spawn_failure_is_a_hold_and_preserves_general_scores(monkeypatch):
    from pickloop import juice_gate

    def missing(_):
        raise FileNotFoundError("tesseract")

    monkeypatch.setattr(juice_gate, "read_package", missing)
    decision = {"prediction": juice_gate.ORANGE, "top1": juice_gate.ORANGE, "score": 0.87}
    output = juice_gate.apply_juice_gate(decision, lambda: np.zeros((16, 16, 3), np.uint8))
    assert output["prediction"] == "UNKNOWN" and output["score"] == 0.87
    assert output["juice_gate_reason"].startswith("ocr_unavailable")


def test_printed_brand_and_flavour_are_read_from_an_upright_carton():
    from shutil import which
    from PIL import Image, ImageDraw
    from pickloop.juice_gate import APPLE, ORANGE, apply_juice_gate

    if which("tesseract") is None:
        pytest.skip("optional Tesseract CLI unavailable")
    crop = Image.new("RGB", (400, 540), "white")
    draw = ImageDraw.Draw(crop)
    draw.rectangle((85, 25, 315, 515), fill="black")
    draw.text((102, 94), "GOD MORGON", fill="white", font_size=29)
    draw.text((115, 238), "APPLE", fill="white", font_size=44)
    result = apply_juice_gate({"top1": ORANGE, "prediction": ORANGE}, lambda: np.asarray(crop))
    assert result["prediction"] == APPLE and result["juice_gate_reason"] == "verified"
