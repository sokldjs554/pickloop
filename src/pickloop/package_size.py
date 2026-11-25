"""Read the declared pack volume separately from the brand and fruit words."""
import re
import unicodedata

import cv2
import numpy as np

from .juice_gate import ocr


VOLUME = re.compile(
    r"(?<![\w.,/])(\d{1,4}(?:[.,]\d{1,3})?)\s*[-–]?\s*(ml|cl|dl|l|litres?|liters?)\b"
)
MULTIPACK = re.compile(
    r"\b(?:[2-9]|\d{2,})\s*[x×]\s*\d|\bpack of\s*(?:[2-9]|\d{2,})\b|"
    r"(?:ml|cl|dl|l|litres?|liters?)\s*[x×]\s*(?:[2-9]|\d{2,})\b|"
    r"\d+\s*/\s*\d+\s*(?:ml|cl|dl|l|litres?|liters?)\b"
)
# A corrupted unit may veto a suspected other size. It cannot corroborate 1 L.
DAMAGED_UNIT = re.compile(r"(?<![\w.,])(\d{2,4})\s+m[i1]\b|(?<![\w.,])(\d+[.,]\d+)\s+[ji]ter\b")
REFERENCE_PREFIX = re.compile(r"(?:\b(?:per|pro|par|por|pr|serving size|portion|serving)\s*[:=]?|/|\d\s*[.,])\s*$")
REFERENCE_SUFFIX = re.compile(r"^\s*(?:/|(?:of\s+)?water\b)")
FACTORS = {"ml": 1, "cl": 10, "dl": 100}


def normalized(read):
    return "".join(c for c in unicodedata.normalize("NFKD", read.lower()) if not unicodedata.combining(c))


def reference_quantity(line, match):
    return bool(REFERENCE_PREFIX.search(line[:match.start()]) or REFERENCE_SUFFIX.search(line[match.end():]))


def printed_size(reads):
    evidence = []
    conflict = False
    positive_reads = 0
    for read in reads:
        line = normalized(read)
        positive = False
        for match in MULTIPACK.finditer(line):
            evidence.append(match.group())
            conflict = True
        for match in DAMAGED_UNIT.finditer(line):
            if reference_quantity(line, match):
                continue
            ml, litres = match.groups()
            value_ml = int(ml) if ml else float(litres.replace(",", ".")) * 1000
            if value_ml != 1000:
                evidence.append(match.group())
                conflict = True
        for match in VOLUME.finditer(line):
            if reference_quantity(line, match):
                continue
            evidence.append(match.group())
            amount, unit = match.groups()
            if float(amount.replace(",", ".")) * FACTORS.get(unit, 1000) == 1000:
                positive = True
            else:
                conflict = True
        positive_reads += positive
    if conflict:
        status = "contradictory"
    elif positive_reads >= 2:
        status = "printed_1l"
    else:
        status = "unread"
    return status, list(dict.fromkeys(evidence))


def read_size_band(rgb):
    """Re-read small lower-front quantity print using luminance and neutral-ink contrast."""
    from .product_text import carton_region

    region = carton_region(rgb)
    face = rgb if region is None else region
    # For wide context shots keep the entire lower band so an off-centre carton is eligible.
    band = face[round(.60 * (len(face) - 1)):]
    h, w = band.shape[:2]
    scale = min(4., 1600 / w, 850 / h)
    enlarged = cv2.resize(band, (max(1, round(w * scale)), max(1, round(h * scale))),
                          interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
    gray = cv2.cvtColor(enlarged, cv2.COLOR_RGB2GRAY)
    low = enlarged.min(axis=2).astype(np.int16)
    chroma = enlarged.max(axis=2) - low
    neutral = np.uint8(np.clip(low - 2 * chroma, 0, 255))
    return [ocr(255 - gray, 11), ocr(255 - neutral, 11)]
