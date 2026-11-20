from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import cv2
import numpy as np
import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
APPLE = "Bravo-Apple-Juice"
ORANGE = "Bravo-Orange-Juice"


def head(top1, prediction):
    return {"top1": top1, "prediction": prediction, "score": 0.67, "support": 0.73, "margin": 0.21}


def carton(color):
    image = np.full((180, 150, 3), color, dtype=np.uint8)
    cv2.putText(image, "BRAVO", (8, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (245, 245, 245), 3)
    for x, y in np.random.default_rng(4).integers([12, 90], [139, 163], size=(24, 2)):
        cv2.circle(image, (int(x), int(y)), 3, (35, 35, 35), -1)
    return image


@pytest.mark.parametrize("generic_prediction", [APPLE, "UNKNOWN"])
def test_verified_orange_switches_flavor_even_when_the_general_gate_holds(monkeypatch, generic_prediction):
    from pickloop import grocery_catalogue as catalogue
    from pickloop.carton_matcher import CartonMatcher

    apple, orange = carton((14, 136, 56)), carton((244, 160, 12))
    polygon = np.float32([[2, 2], [147, 2], [147, 177], [2, 177]])
    gallery = CartonMatcher.register([(APPLE, apple, polygon), (ORANGE, orange, polygon)])
    monkeypatch.setattr(catalogue, "bravo_matcher", lambda: gallery)
    photo = np.full((280, 320, 3), 125, np.uint8)
    photo[52:232, 103:253] = orange
    generic = head(APPLE, generic_prediction)
    final = catalogue.resolve_decision(generic, lambda: photo)
    assert (final["generic_top1"], final["generic_prediction"], final["top1"], final["prediction"]) == (
        APPLE, generic_prediction, ORANGE, ORANGE)
    assert (final["decision_source"], final["panel_prediction"], final["panel_reason"]) == ("bravo_panel", ORANGE, "verified")
    assert final["panel_inliers"] >= 6
    assert final["score"] == 0.67 and final["support"] == 0.73 and final["margin"] == 0.21
    assert generic == head(APPLE, generic_prediction)


def test_frozen_packaged_gallery_holds_a_blank_candidate():
    from pickloop.grocery_catalogue import BRAVO_GALLERY, resolve_decision

    original = ROOT / "docs/experiments/carton-panels/gallery.npz"
    assert sha256(BRAVO_GALLERY.read_bytes()).hexdigest() == sha256(original.read_bytes()).hexdigest()
    result = resolve_decision(head(ORANGE, ORANGE), lambda: np.zeros((280, 320, 3), np.uint8))
    assert (result["top1"], result["prediction"], result["panel_prediction"]) == (ORANGE, "UNKNOWN", "UNKNOWN")
    assert result["decision_source"] == "bravo_panel" and result["panel_reason"] == "panel_unverified"


@pytest.mark.parametrize("prediction", ["Lime", "UNKNOWN"])
def test_non_bravo_decisions_use_no_panel_pixels_or_assets(monkeypatch, prediction):
    from pickloop import grocery_catalogue as catalogue

    def unexpected():
        pytest.fail("non-Bravo image or gallery was accessed")

    monkeypatch.setattr(catalogue, "bravo_matcher", unexpected)
    result = catalogue.resolve_decision(head("Lime", prediction), unexpected)
    assert (result["generic_top1"], result["generic_prediction"], result["top1"], result["prediction"]) == (
        "Lime", prediction, "Lime", prediction)
    assert result["decision_source"] == "generic" and result["panel_prediction"] is None


def test_original_pixel_loader_checks_cached_hash_and_external_membership(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    from run_grocery_catalogue import verified_pixels
    from pickloop.grocery_evaluation import PREFIX

    buffer = BytesIO()
    Image.new("RGB", (8, 6), (224, 126, 20)).save(buffer, format="PNG")
    data = buffer.getvalue()
    digest = sha256(data).hexdigest()
    path = "test/pack.png"
    with ZipFile(tmp_path / "official.zip", "w") as archive:
        archive.writestr(PREFIX + path, data)
    (tmp_path / "external.png").write_bytes(data)
    with ZipFile(tmp_path / "official.zip") as archive:
        row = dict(path=path, split="test", sha256=digest)
        assert verified_pixels(row, archive, tmp_path, {}).shape == (6, 8, 3)
        with pytest.raises(ValueError, match="checksum"):
            verified_pixels(dict(row, sha256="0" * 64), archive, tmp_path, {})
        external = dict(path="external.png", split="outside_test", sha256=digest)
        with pytest.raises(ValueError, match="manifest"):
            verified_pixels(external, archive, tmp_path, {})
        assert verified_pixels(external, archive, tmp_path, {"external.png": digest})[0, 0].tolist() == [224, 126, 20]
        (tmp_path / "external.png").write_bytes(b"changed")
        with pytest.raises(ValueError, match="checksum"):
            verified_pixels(external, archive, tmp_path, {"external.png": digest})
