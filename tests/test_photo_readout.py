import pytest

APPLE = "God-Morgon-Apple-Juice"

def decision(name=APPLE, reason="brand_and_apple", route="package_text", codes=()):
    return dict(prediction=name, recognition_source=route, recognition_reason=reason,
                recognition_gtins=list(codes), recognition_text=["GOD MORGON Äppeljuice", "APPELJUICE"])


def test_strict_preserves_printed_words_and_name_but_holds_unverified_package():
    from pickloop.photo_readout import photo_readout
    evidence = decision()
    evidence["recognition_text"] = ["GOD MORGON APPLE 1 L", "APPLE 1000 ml"]
    strict = photo_readout(evidence, require_gtin=True)
    assert strict["photo_name"] == APPLE
    assert strict["printed_fruit_words"] == ["apple"]
    assert strict["confirmed_order_sku"] is None
    assert strict["prediction"] == "UNKNOWN"
    assert photo_readout(evidence)["prediction"] == APPLE
    assert evidence["prediction"] == APPLE


@pytest.mark.parametrize("source,reason,codes,expected", [
    ("barcode", "registered_gtin", ["7310865074225"], APPLE),
    ("barcode", "barcode_text_conflict", ["7310865074225"], None),
    ("barcode", "registered_gtin", ["7310860007372"], None),
    ("barcode", "registered_gtin", ["7310865074225", "7310860007372"], None),
    ("package_text", "brand_and_apple", ["7310865074225"], None),
])
def test_confirmation_requires_a_single_matching_registered_optical_read(source, reason, codes, expected):
    from pickloop.photo_readout import photo_readout
    strict = photo_readout(decision(route=source, reason=reason, codes=codes), require_gtin=True)
    assert strict["confirmed_order_sku"] == expected
    assert strict["prediction"] == (expected or "UNKNOWN")


def test_two_readings_needed_for_fruit_words_and_an_unread_photo_has_no_candidate():
    from pickloop.photo_readout import photo_readout
    d = decision(name="UNKNOWN", reason="brand_unverified")
    d["recognition_text"] = ["ORANGE red GRAPEFRUIT apple", "appelsin og grapefrukt"]
    result = photo_readout(d)
    assert result["printed_fruit_words"] == ["orange", "grapefruit"]
    assert result["photo_name"] is None


def test_generic_product_keeps_its_name_and_has_no_verified_trade_item():
    from pickloop.photo_readout import photo_readout
    result = photo_readout(decision(name="Banana", route="baseline", reason="outside_route"))
    assert result["photo_name"] == "Banana"
    assert result["confirmed_order_sku"] is None


def test_strict_scans_registered_bars_even_when_the_visual_head_picked_another_class():
    from test_pack_barcode import ean_image
    from pickloop.photo_readout import photo_readout
    unrelated = decision(name="Banana", route="baseline", reason="outside_route")
    unrelated.update(top1="Banana", recognition_text=[])
    result = photo_readout(unrelated, require_gtin=True, rgb=ean_image("7310865074225"))
    assert result["photo_name"] == "Banana"
    assert result["confirmed_order_sku"] == result["prediction"] == APPLE
    assert result["confirmed_gtin"] == "7310865074225"


def test_recognize_rgb_exposes_opt_in_produce_name_separately_from_order_confirmation(monkeypatch):
    from types import SimpleNamespace
    import numpy as np
    from pickloop import grocery_catalogue, product_text, produce_rescue
    head = SimpleNamespace(predict=lambda features: [dict(prediction="UNKNOWN", top1="Cucumber")])
    encoder = SimpleNamespace(encode=lambda photos: [0])
    monkeypatch.setattr(grocery_catalogue, "_default_models", lambda: (head, encoder))
    monkeypatch.setattr(product_text, "recognize_exact", lambda result, read_rgb:
                        dict(result, recognition_source="package_text", recognition_reason="brand_unverified",
                             recognition_gtins=[], recognition_text=[]))
    monkeypatch.setattr(produce_rescue, "apply_produce_rescue", lambda result, read_rgb:
                        dict(result, prediction="Cucumber", recognition_source="produce_rescue"))
    rgb = np.zeros((15, 20, 3), dtype=np.uint8)
    strict = grocery_catalogue.recognize_rgb(rgb, produce=True, require_gtin=True)
    assert strict["photo_name"] == "Cucumber" and strict["prediction"] == "UNKNOWN"
    assert grocery_catalogue.recognize_rgb(rgb)["photo_name"] is None


def test_flavour_without_size_returns_candidate_and_holds_exact_name():
    from pickloop.photo_readout import photo_readout
    result = photo_readout(decision())
    assert result["flavour_candidate"] == APPLE
    assert result["size_status"] == "unread"
    assert result["prediction"] == "UNKNOWN" and result["photo_name"] is None
    assert result["photo_name_reason"] == "size_unverified"


def test_smaller_size_is_a_hold_with_readable_flavour():
    from pickloop.photo_readout import photo_readout
    d = decision(name="UNKNOWN", reason="conflicting_product_or_size")
    d["recognition_text"] = ["GOD MORGON APPLE 250 ml", "APPLE"]
    result = photo_readout(d)
    assert result["flavour_candidate"] == APPLE and result["photo_name"] is None
    assert result["size_status"] == "contradictory" and result["size_evidence"] == ["250 ml"]


def test_conflicting_secondary_quantity_vetoes_order_even_with_registered_code(monkeypatch):
    from pickloop import photo_readout
    import numpy as np
    monkeypatch.setattr(photo_readout, "read_size_band", lambda rgb: ["250 ml", ""])
    result = photo_readout.photo_readout(decision(route="barcode", reason="registered_gtin", codes=["7310865074225"]),
                                         require_gtin=True, rgb=np.zeros((8, 8, 3), dtype=np.uint8))
    assert result["confirmed_order_sku"] is result["photo_name"] is None
    assert result["prediction"] == "UNKNOWN" and result["order_check_reason"] == "barcode_text_conflict"
