"""Recover a God Morgon catalogue flavour from a photographed package label."""
import re
import subprocess
import unicodedata

import cv2
import numpy as np

from .juice_gate import APPLE, MIX, ORANGE, TARGETS, align_panel, ocr
from .pack_barcode import REGISTERED_GTINS, read_ean13


# The sun in the three-line GOD / MOR / GON logo is commonly transcribed as @, 0 or ®.
BRAND = re.compile(r"\bgod\W*(?:mor|mo)\W*g\W*[o0@®eu]\W*n\b|\bgod\s+morgon\b")
OTHER = re.compile(
    r"\b(?:blood\w*|blod\w*|veriappels\w*|sanguin\w*|mango\w*|ananas\w*|pineapple\w*|"
    r"pear\w*|paron\w*|mandarin\w*|clementin\w*|passion\w*|raspberr\w*|strawberr\w*|"
    r"peach\w*|persik\w*|lemon\w*|lime\w*|citron\w*|morot\w*|carrot\w*|ginger\w*|ingef\w*|"
    r"berry|berries|apricot\w*|multifr\w*|tropic\w*|selected|blend|crush|sweet|mild|light|"
    r"organic|ekolog\w*|luomu\w*|smooth|sparkling|nectar|multi.?pack|family.?pack|"
    r"bravo|tropicana|innocent|granini classic|smoo?thie)\b|"
    r"\b(?:pulp\W*free|(?:no|without)\s+pulp|utan\s+fruktkott|vitamin\s+d)\b"
)
SIZE = re.compile(r"(?<![\w.,])(\d{1,4}(?:[.,]\d{1,2})?)\s*[-–]?\s*(ml|cl|dl|l|litre[s]?|liter[s]?)\b")
APPLE_WORD = re.compile(r"\b(?:apple|appel|apfel|omena)(?:juice|mehu|saft)?\b")
ORANGE_WORD = re.compile(r"\b(?:orange|apelsin|appelsin|appelsiini)(?:juice|mehu|saft)?\b")
GRAPE_WORD = re.compile(r"\b(?:red\s*)?(?:grapefruit|grapefrukt|grape|verigreippi)(?:juice|mehu|saft)?\b")
RED_WORD = re.compile(r"\b(?:red|rod|redgrapefruit|verigreippi)\b")


def normalized(read):
    return "".join(c for c in unicodedata.normalize("NFKD", read.lower()) if not unicodedata.combining(c))


def contradictory_size(line):
    for amount, unit in SIZE.findall(line):
        value = float(amount.replace(",", ".")) * {"ml": 1, "cl": 10, "dl": 100}.get(unit, 1000)
        if value != 1000:
            return True
    return re.search(r"\b(?:[2-9]|\d{2})\s*(?:x|×)\s*\d|\bpack of\s*(?:[2-9]|\d{2})\b", line) is not None


def printed_flavour(reads, registered_panel=False, *, veto_size=True):
    """Corroborate brand and flavour, with a veto across all readings of this photograph."""
    texts = [normalized(text) for text in reads]
    if any(OTHER.search(t) or (veto_size and contradictory_size(t)) for t in texts):
        return None, "conflicting_product_or_size"
    if not registered_panel and not any(BRAND.search(re.sub(r"\S+\.(?:com|se|dk|fi|no|net)\b", "", t)) for t in texts):
        return None, "brand_unverified"
    apples = [bool(APPLE_WORD.search(t)) for t in texts]
    oranges = [bool(ORANGE_WORD.search(t)) for t in texts]
    grapes = [bool(GRAPE_WORD.search(t)) for t in texts]
    reds = [bool(RED_WORD.search(t)) for t in texts]
    if any(apples) and (any(oranges) or any(grapes) or any(reds)):
        return None, "conflicting_flavours"
    if any(grapes) or any(reds):
        if sum(o and g and r for o, g, r in zip(oranges, grapes, reds, strict=True)) >= 2:
            return MIX, "brand_and_mixed_flavour"
        return None, "incomplete_mixed_flavour"
    if sum(apples) >= 2:
        return APPLE, "brand_and_apple"
    if sum(oranges) >= 2:
        return ORANGE, "brand_and_orange"
    return None, "flavour_unverified"


def carton_region(rgb):
    """Locate a dominant dark body while preserving the original resolution of its print."""
    h, w = rgb.shape[:2]
    scale = 640 / max(h, w)
    small = cv2.resize(rgb, (max(1, round(w*scale)), max(1, round(h*scale))), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    mask = np.uint8(gray < 83) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 13))
    contours, _ = cv2.findContours(cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel),
                                   cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if (area > .025 * gray.size and height > .75 * width and area > .32 * width * height
                and abs(x + width/2 - gray.shape[1]/2) < .32 * gray.shape[1]):
            boxes.append((area, x, y, width, height))
    if not boxes:
        return None
    _, x, y, width, height = max(boxes)
    pad = .04 * max(width, height)
    return rgb[max(0, int((y-pad)/scale)):int((y+height+pad)/scale),
               max(0, int((x-pad)/scale)):int((x+width+pad)/scale)]


def reading_image(rgb):
    h, w = rgb.shape[:2]
    scale = min(1100/h, 1600/w)
    return cv2.resize(rgb, (max(1, round(w*scale)), max(1, round(h*scale))),
                      interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)


def read_print(rgb, candidate):
    if min(rgb.shape[:2]) < 32:
        return None, "insufficient_resolution", [], "none"
    # Always inspect the full photograph: a tighter flavour crop can hide a variant or size.
    full = reading_image(rgb)
    reads = [ocr(cv2.cvtColor(full, cv2.COLOR_RGB2GRAY), 11)]
    region = carton_region(rgb)
    face = reading_image(region) if region is not None else full
    gray = cv2.cvtColor(face, cv2.COLOR_RGB2GRAY)
    reads.extend((ocr(255-gray, 6), ocr(255-face.max(axis=2), 11)))
    name, reason = printed_flavour(reads)
    if name is not None or reason in ("conflicting_product_or_size", "conflicting_flavours"):
        return name, reason, reads, "package_text"
    if region is not None:
        reads.append(ocr(gray, 11))
        name, reason = printed_flavour(reads)
        if name is not None or reason in ("conflicting_product_or_size", "conflicting_flavours"):
            return name, reason, reads, "package_text"
    if reason == "brand_unverified":
        # Isolate the stacked wordmark above the flavour from the shelf and fine print.
        reads.append(ocr(gray[:round(.55 * len(gray))], 11))
        name, reason = printed_flavour(reads)
        if name is not None or reason in ("conflicting_product_or_size", "conflicting_flavours"):
            return name, reason, reads, "package_text"
    if candidate in TARGETS:
        panel = align_panel(rgb)
        if panel is not None:
            band = panel[220:518, 12:432]
            val = band.max(axis=2)
            binary = cv2.adaptiveThreshold(val, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 61, -12)
            reads.extend((ocr(255-cv2.cvtColor(band, cv2.COLOR_RGB2GRAY), 6), ocr(255-val, 6), ocr(255-binary, 6)))
            name, reason = printed_flavour(reads, registered_panel=True)
            return name, reason, reads, "registered_panel_and_text"
    return None, reason, reads, "package_text"


def recognize_exact(baseline, read_rgb):
    """Resolve an upstream hold or one of three named juices using the photographed package.

    A single registered EAN identifies the trade item. Conflicting printed evidence,
    an unregistered EAN or multiple EANs hold. Without visible bars, the print route
    identifies the catalogue flavour; size and GTIN can be obscured on a front view.
    """
    before = baseline["prediction"]
    if before != "UNKNOWN" and before not in TARGETS:
        return dict(baseline, baseline_prediction=before, recognition_source="baseline", recognition_reason="outside_route",
                    recognition_text=[], recognition_gtins=[])
    rgb = read_rgb()
    codes = list(read_ean13(rgb))
    if len(codes) > 1 or (codes and codes[0] not in REGISTERED_GTINS):
        name, reads, source = None, [], "barcode"
        reason = "multiple_gtins" if len(codes) > 1 else "unregistered_gtin"
    else:
        try:
            name, reason, reads, source = read_print(rgb, baseline["top1"])
        except (OSError, subprocess.SubprocessError) as error:
            name, reason, reads, source = None, f"ocr_unavailable:{type(error).__name__}", [], "package_text"
        if codes:
            sku = REGISTERED_GTINS[codes[0]]
            conflict = reason in ("conflicting_product_or_size", "conflicting_flavours") or (name and name != sku)
            incompatible = {APPLE: (ORANGE_WORD, GRAPE_WORD), ORANGE: (APPLE_WORD, GRAPE_WORD), MIX: (APPLE_WORD,)}
            for word in incompatible[sku]:
                if sum(bool(word.search(normalized(read))) for read in reads) >= 2:
                    conflict = True
            name, reason = (None, "barcode_text_conflict") if conflict else (sku, "registered_gtin")
            source = "barcode"
    return dict(baseline, baseline_prediction=before, prediction=name or "UNKNOWN", recognition_source=source,
                recognition_reason=reason, recognition_text=reads, recognition_gtins=codes)
