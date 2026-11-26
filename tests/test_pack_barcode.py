"""Rendered bars are the input. No product identifiers are passed beside the pixels."""
import numpy as np


def ean_image(digits):
    odd = ("0001101", "0011001", "0010011", "0111101", "0100011",
           "0110001", "0101111", "0111011", "0110111", "0001011")
    right = [s.translate(str.maketrans("01", "10")) for s in odd]
    even = [s[::-1] for s in right]
    parity = ("LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
              "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL")
    left = "".join((odd if group == "L" else even)[int(d)]
                   for d, group in zip(digits[1:7], parity[int(digits[0])]))
    bars = "101" + left + "01010" + "".join(right[int(d)] for d in digits[7:]) + "101"
    line = np.uint8([0 if bit == "1" else 255 for bit in "0"*12 + bars + "0"*12])
    image = np.full((132, len(line)*3, 3), 255, np.uint8)
    image[15:111] = np.repeat(line, 3)[None, :, None]
    return image


def test_decode_distinguishes_an_exact_registered_code_from_another_flavour_and_rotates():
    from pickloop.pack_barcode import REGISTERED_GTINS, read_ean13
    first = ean_image("7310860007259")
    second = ean_image("7313619002413")
    assert read_ean13(np.rot90(first).copy()) == ("7310860007259",)
    assert REGISTERED_GTINS["7310860007259"] == "God-Morgon-Orange-Red-Grapefruit-Juice"
    codes = read_ean13(np.vstack((first, second)))
    assert set(codes) == {"7310860007259", "7313619002413"}
    assert "7313619002413" not in REGISTERED_GTINS


def test_missing_or_invalid_bars_never_supply_a_product_id():
    from pickloop.pack_barcode import read_ean13
    assert read_ean13(np.full((120, 160, 3), 220, np.uint8)) == ()
    assert read_ean13(ean_image("7310860007258")) == ()


def test_short_code_prevents_selecting_an_order_from_a_two_package_scene():
    from pathlib import Path
    from PIL import Image
    from pickloop.pack_barcode import read_ean13, read_retail_codes

    with Image.open(Path(__file__).parent / "fixtures/two-retail-codes.png") as fixture:
        scene = np.asarray(fixture.convert("RGB"))
    assert read_ean13(scene) == ("7310865074225",)
    assert read_retail_codes(scene) == ("48512343", "7310865074225")
