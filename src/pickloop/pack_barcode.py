"""Resolve optically decoded EAN-13 codes for the three registered 1 L cartons."""
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


def read_ean13(rgb):
    """Read all distinct checksum-valid EAN-13/UPC-A codes actually visible in the image."""
    gray = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2GRAY)
    symbols = zxingcpp.read_barcodes(gray, formats=zxingcpp.EAN13 | zxingcpp.UPCA)
    codes = set()
    for symbol in symbols:
        digits = symbol.text
        if symbol.format == zxingcpp.UPCA and len(digits) == 12:
            digits = "0" + digits
        if len(digits) != 13 or not digits.isascii() or not digits.isdigit():
            continue
        checksum = sum(int(digit) * weight for digit, weight in zip(digits, (1, 3) * 6 + (1,)))
        if symbol.valid and checksum % 10 == 0:
            codes.add(digits)
    return tuple(sorted(codes))
