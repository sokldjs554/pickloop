"""Resolve foreground cartons with a foreshortened label using SIFT and printed artwork."""
from functools import cache
from hashlib import sha256
from pathlib import Path

import cv2
import numpy as np

from .registered_pack import decide, gallery, geometric_hit

FEATURES = Path(__file__).with_name("data") / "registered_oblique.npz"
FEATURES_SHA256 = "4829c5d7179505b121cbbd436797ac900cff6cc1a531e6bd66cd2d60cba29097"

# The official training fronts use this layout. The lettering below the shared logo
# spells the flavour. Every other enrolled design still participates as a rival.
WORD_FRONTS = {
    "God-Morgon-Apple-Juice_014",
    "God-Morgon-Orange-Juice_010",
    "God-Morgon-Orange-Red-Grapefruit-Juice_008",
    "God-Morgon-Orange-Red-Grapefruit-Juice_016",
}
ORANGE_SIDE = "God-Morgon-Orange-Juice_007"


@cache
def references():
    if sha256(FEATURES.read_bytes()).hexdigest() != FEATURES_SHA256:
        raise ValueError("oblique artwork features checksum mismatch")
    with np.load(FEATURES, allow_pickle=False) as data:
        return [(t, data[t["id"] + "-xy"].astype(np.float32) / 4,
                 data[t["id"] + "-desc"].astype(np.float32))
                for t in gallery() if t["id"] + "-desc" in data]


def has_orange_illustration(image, transform, width, height):
    # Relative to the enrolled ingredient block, this rectangle falls on the
    # centre of the orange segment below it. The barcode sits to its left.
    patch = np.float32([(.64, 1.34), (.78, 1.34), (.78, 1.47), (.64, 1.47)])
    patch *= [width, height]
    projected = cv2.perspectiveTransform(patch[None], transform)[0]
    h, w = image.shape[:2]
    if (not np.isfinite(projected).all() or (projected < 0).any()
            or (projected >= [w, h]).any() or cv2.contourArea(projected) < 16):
        return False
    target = np.float32([(0, 0), (11, 0), (11, 11), (0, 11)])
    crop = cv2.warpPerspective(image, cv2.getPerspectiveTransform(projected, target), (12, 12))
    hue, saturation, value = cv2.split(cv2.cvtColor(crop, cv2.COLOR_RGB2HSV))
    # OpenCV hue units represent two degrees each. The yellow-orange fruit
    # flesh can be distinguished from the red-grapefruit and apple artwork.
    orange = (hue >= 15) & (hue <= 34) & (saturation >= 80) & (value >= 45)
    return np.mean(orange) >= .65


def foreground_hit(template, reference_points, descriptors, matcher, query_points, image):
    pairs = matcher.knnMatch(descriptors, k=2)
    matches = [a for a, b in pairs if a.distance < .78*b.distance and a.distance < 300]
    unique = {}
    for match in sorted(matches, key=lambda m: m.distance):
        unique.setdefault(match.trainIdx, match.queryIdx)
    if len(unique) < 12:
        return None
    result = geometric_hit(template, reference_points[list(unique.values())],
                           query_points[list(unique)], image, details=True)
    if result is None:
        return None
    hit, support, quad, transform = result
    h, w = image.shape[:2]
    center = quad.mean(axis=0) / [w, h]
    if (center < .20).any() or (center > .80).any() or cv2.contourArea(quad) < .08*w*h:
        return None
    hit["distinctive"] = False
    if template["id"] in WORD_FRONTS:
        x, y = (support / [template["width"], template["height"]]).T
        # Correspondences on the flavour lettering corroborate the aligned fruit colours.
        word = (x > .05) & (x < .95) & (y > .25) & (y < .37)
        hit["distinctive"] = int(word.sum()) >= 4
    elif template["id"] == ORANGE_SIDE:
        hit["distinctive"] = has_orange_illustration(image, transform, template["width"], template["height"])
    return hit


def match_oblique(rgb):
    h, w = rgb.shape[:2]
    if min(w, h) < 24:
        return None
    # Undo part of the horizontal compression of an upright panel seen obliquely.
    scale = 720 / max(h, w)
    size = max(1, round(1.65*w*scale)), max(1, round(h*scale))
    image = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    keys, desc = cv2.SIFT_create(nfeatures=2500, contrastThreshold=.025).detectAndCompute(gray, None)
    if desc is None or len(keys) < 12:
        return None
    query_points = np.float32([k.pt for k in keys])
    cv2.setRNGSeed(24)
    matcher = cv2.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=64))
    matcher.add([desc])
    matcher.train()
    hits = []
    for template, points, descriptors in references():
        hit = foreground_hit(template, points, descriptors, matcher, query_points, image)
        if hit is not None:
            hits.append(hit)
    hits.sort(key=lambda hit: -hit["score"])
    if hits and hits[0]["distinctive"]:
        verdict = decide(hits)
        if verdict and verdict["status"] == "matched":
            return dict(verdict, method="oblique_sift")
    return None
