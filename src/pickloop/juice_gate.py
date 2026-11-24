"""Read the printed God Morgon flavour before admitting one of three named juices."""
from collections import Counter
from functools import cache
from hashlib import sha256
import os
from pathlib import Path
import re
import subprocess
import unicodedata

import cv2
import numpy as np

from .carton_matcher import CartonMatcher, Template, frame, sift

APPLE = "God-Morgon-Apple-Juice"
ORANGE = "God-Morgon-Orange-Juice"
MIX = "God-Morgon-Orange-Red-Grapefruit-Juice"
TARGETS = frozenset((APPLE, ORANGE, MIX))
GALLERY = Path(__file__).with_name("data") / "juice_gate.npz"
GALLERY_SHA = "496c81c7de627748b79c7661fa7377d6d5e3a62d2cf0dd09f3e2e3a0050b7aea"


def confirmed_flavour(reads, located_panel):
    """Require two corroborating word reads and reject a competing flavour or qualifier."""
    normalized = []
    for line in reads:
        line = unicodedata.normalize("NFKD", line.lower()).encode("ascii", "ignore").decode()
        normalized.append(set(re.findall(r"[a-z]+", line)))
    if not located_panel and not any(
        "godmorgon" in t or ("god" in t and ("morgon" in t or {"mor", "gon"} <= t)) for t in normalized
    ):
        return None, "brand_unverified"
    votes = Counter()
    all_words = set().union(*normalized)
    if all_words & {"selected", "blend", "blood", "blod", "mango", "pear", "pineapple", "mandarin",
                    "passion", "raspberry", "strawberry", "sweet", "lemon", "peach", "crush"}:
        return None, "other_flavour"
    apple = {"apple", "appel", "applejuice", "omena"}
    orange = {"orange", "apelsin", "appelsiini"}
    grapefruit = {"grapefruit", "grapefrukt", "grape", "verigreippi"}
    for words in normalized:
        if words & apple:
            votes[APPLE] += 1
        if words & orange and words & grapefruit:
            votes[MIX] += 1
        elif words & orange and not words & {"red", "rod"}:
            votes[ORANGE] += 1
    if len(votes) != 1:
        return None, "conflicting_or_missing_words"
    name, count = votes.most_common(1)[0]
    if count < 2 or (name != MIX and all_words & (grapefruit | {"red", "rod"})):
        return None, "incomplete_flavour"
    return name, "verified"


@cache
def templates():
    if sha256(GALLERY.read_bytes()).hexdigest() != GALLERY_SHA:
        raise ValueError("juice panel gallery checksum mismatch")
    with np.load(GALLERY, allow_pickle=False) as stored:
        return [Template("God-Morgon", stored[f"polygon{i}"], stored[f"points{i}"],
                         stored[f"descriptors{i}"].astype(np.float32), np.empty(0)) for i in range(4)]


def align_panel(rgb):
    image, _ = frame(rgb)
    points, descriptors = sift(image)
    if len(descriptors) < 6:
        return None
    best, panel = 0, None
    matcher = cv2.BFMatcher()
    for template in templates():
        pairs = [(p.queryIdx, p.trainIdx, p.distance) for p, alt in
                 matcher.knnMatch(template.descriptors, descriptors, k=2) if p.distance < 0.76 * alt.distance]
        hit = CartonMatcher.locate(template, pairs, points, image.shape)
        if hit is not None:
            corners, inliers, quality = hit
            if inliers >= 12 and quality > best:
                best, panel = quality, corners
    if panel is None:
        return None
    target = np.float32([(0, 0), (450, 0), (450, 760), (0, 760)])
    return cv2.warpPerspective(image, cv2.getPerspectiveTransform(panel, target), (450, 760))


def isolated_pack(rgb):
    # A plain light backdrop permits a second route for upright product packshots.
    image, _ = frame(rgb)
    if min(np.median(c) for c in (image[:8, :8], image[-8:, :8], image[:8, -8:], image[-8:, -8:])) < 220:
        return None
    mask = np.uint8(image.min(axis=2) < 214)
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    objects = sorted(stats[1:], key=lambda q: -int(q[cv2.CC_STAT_AREA]))
    if not objects or objects[0][4] < .035 * mask.size or (len(objects) > 1 and objects[1][4] > .22 * objects[0][4]):
        return None
    x, y, w, h, _ = objects[0]
    if h < w * 1.1 or h < 60:
        return None
    box = image[max(y-6, 0):y+h+6, max(x-6, 0):x+w+6]
    scale = 1150 / box.shape[0]
    return cv2.resize(box, (int(box.shape[1] * scale), 1150), interpolation=cv2.INTER_CUBIC)


def ocr(image, mode):
    ok, png = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("cannot encode OCR input")
    read = subprocess.run(["tesseract", "stdin", "stdout", "-l", "eng", "--psm", str(mode)],
                          input=png.tobytes(), capture_output=True, timeout=7, check=True,
                          env={**os.environ, "OMP_THREAD_LIMIT": "1"})
    return " ".join(read.stdout.decode("utf-8", errors="replace").split())


def read_package(rgb):
    panel = align_panel(rgb)
    if panel is not None:
        band = panel[220:518, 12:432]
        gray = cv2.cvtColor(band, cv2.COLOR_RGB2GRAY)
        val = band.max(axis=2)
        binary = cv2.adaptiveThreshold(val, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 61, -12)
        return [ocr(255-gray, 6), ocr(255-val, 6), ocr(255-binary, 6)], True
    pack = isolated_pack(rgb)
    if pack is None:
        return [], False
    gray = cv2.cvtColor(pack, cv2.COLOR_RGB2GRAY)
    return [ocr(gray, 11), ocr(255-gray, 6), ocr(255-pack.max(axis=2), 11)], False


def apply_juice_gate(decision, read_rgb):
    if decision["top1"] not in TARGETS:
        return decision
    previous = decision["prediction"]
    reads = []
    verified, reason = None, "upstream_hold"
    if previous != "UNKNOWN":
        try:
            reads, aligned = read_package(read_rgb())
            verified, reason = confirmed_flavour(reads, aligned) if reads else (None, "no_single_panel")
        except (OSError, subprocess.SubprocessError) as error:
            reason = f"ocr_unavailable:{type(error).__name__}"
    return {**decision, "juice_gate_original": previous, "juice_gate_reason": reason,
            "juice_gate_text": reads, "prediction": verified or "UNKNOWN"}
