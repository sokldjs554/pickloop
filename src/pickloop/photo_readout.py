"""Describe photographed evidence independently of the catalogue naming decision."""
from .pack_barcode import REGISTERED_GTINS, read_ean13
from .product_text import APPLE_WORD, GRAPE_WORD, ORANGE_WORD, normalized, recognize_exact


def photo_readout(result, require_gtin=False, rgb=None):
    candidate = result["prediction"]
    identity = result
    # The ordinary classifier skips package text on strong, unrelated visual classes.
    # A visible registered code should still be checked when explicitly scanning for an order.
    if require_gtin and rgb is not None and result["recognition_source"] == "baseline" and read_ean13(rgb):
        identity = recognize_exact(dict(result, prediction="UNKNOWN"), lambda: rgb)
    codes = identity["recognition_gtins"]
    confirmed = None
    if identity["recognition_source"] == "barcode" and identity["recognition_reason"] == "registered_gtin" and len(codes) == 1:
        sku = REGISTERED_GTINS.get(codes[0])
        if sku == identity["prediction"]:
            confirmed = sku
    reads = [normalized(line) for line in identity["recognition_text"]]
    words = [name for name, pattern in (("apple", APPLE_WORD), ("orange", ORANGE_WORD), ("grapefruit", GRAPE_WORD))
             if sum(bool(pattern.search(line)) for line in reads) >= 2]
    return dict(result, photo_name=None if candidate == "UNKNOWN" else candidate, printed_fruit_words=words,
                confirmed_order_sku=confirmed, confirmed_gtin=codes[0] if confirmed else None,
                order_check_reason=identity["recognition_reason"], order_check_gtins=codes,
                prediction=(confirmed or "UNKNOWN") if require_gtin else candidate)
