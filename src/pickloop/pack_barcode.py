"""Resolve optically decoded retail codes for the three registered 1 L cartons."""
import cv2
import numpy as np
import zxingcpp


# The package identities come from the original registration ledger; new test photos
# never add entries. An unlisted code cannot confirm any of these three products.
REGISTERED_GTINS = {
    "7310865074225": "God-Morgon-Apple-Juice",
    "7310860007372": "God-Morgon-Orange-Juice",
    "7310860007259": "God-Morgon-Orange-Red-Grapefruit-Juice",
}


def _expanded_upce(digits):
    # UPC-E suppresses zeros from the manufacturer and item fields of a UPC-A.
    system, a, b, c, d, e, tail, check = digits
    if tail in "012":
        body = a + b + tail + "0000" + c + d + e
    elif tail == "3":
        body = a + b + c + "00000" + d + e
    elif tail == "4":
        body = a + b + c + d + "00000" + e
    else:
        body = a + b + c + d + e + "0000" + tail
    return "0" + system + body + check


def read_retail_codes(rgb, formats=zxingcpp.EAN13 | zxingcpp.UPCA | zxingcpp.EAN8 | zxingcpp.UPCE):
    """Return distinct optically decoded, checksum-valid GTINs for an order decision."""
    gray = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2GRAY)
    codes = {}
    for symbol in zxingcpp.read_barcodes(gray, formats=formats):
        digits = symbol.text
        if not symbol.valid or not digits.isascii() or not digits.isdigit():
            continue
        if symbol.format == zxingcpp.UPCE and len(digits) == 8:
            if digits[0] not in "01":
                continue
            digits = _expanded_upce(digits)
        elif symbol.format == zxingcpp.UPCA and len(digits) == 12:
            digits = "0" + digits
        if len(digits) != (8 if symbol.format == zxingcpp.EAN8 else 13):
            continue
        key = digits.zfill(14)
        checksum = sum(int(digit) * weight for digit, weight in zip(key, (3, 1) * 7))
        if checksum % 10 == 0 and (key not in codes or len(digits) < len(codes[key])):
            codes[key] = digits
    return tuple(sorted(codes.values()))


def read_ean13(rgb):
    """Compatibility entry point for EAN-13/UPC-A-only consumers."""
    return read_retail_codes(rgb, formats=zxingcpp.EAN13 | zxingcpp.UPCA)
