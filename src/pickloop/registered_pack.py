"""Identify enrolled carton artwork using spatially verified local image correspondences."""
import base64
from functools import cache
from hashlib import sha256
import json
from pathlib import Path

import cv2
import numpy as np

from .pack_barcode import REGISTERED_GTINS

GALLERY = Path(__file__).with_name('data') / 'registered_pack.npz'
# Market-specific package volumes from the source records in fresh-size-eval/labels.csv.
# Keep all unknown-volume and same-volume competitors when comparing 1 L artwork.
OTHER_VOLUMES_ML = {
    "6415130089827": 250, "6415130089834": 250,
    "7310865081650": 1750, "7310865074768": 1750,
}
GALLERY_SHA256 = '14ed14cd1f5df7747fcac02ffa31d04c5258c881407af195e449badac3c1859b'


def orb():
    return cv2.ORB_create(nfeatures=1800, scaleFactor=1.2, nlevels=8, edgeThreshold=9, patchSize=31,
                          fastThreshold=8)


@cache
def gallery():
    with np.load(GALLERY, allow_pickle=False) as file:
        encoded = file['gallery'].tobytes()
    if sha256(encoded).hexdigest() != GALLERY_SHA256:
        raise ValueError('registered pack gallery checksum mismatch')
    data = json.loads(encoded)
    if data['version'] != 1:
        raise ValueError('unsupported registered pack gallery')
    templates = []
    for template in data['templates']:
        points = np.float32(template['points'])
        desc = np.frombuffer(base64.b64decode(template['descriptors']), np.uint8).reshape(len(points), 32)
        appearance = np.frombuffer(base64.b64decode(template['appearance']), np.uint8).reshape(32, 12, 3)
        templates.append(dict(template, points=points, descriptors=desc, appearance=appearance))
    return templates


def locate(template, query_points, query_descriptors, image):
    matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(template['descriptors'], query_descriptors, k=2)
    pairs = [m for m, alt in matches if m.distance <= 64 and m.distance < .79 * alt.distance]
    unique = {}
    for match in sorted(pairs, key=lambda m: m.distance):
        unique.setdefault(match.trainIdx, match.queryIdx)
    if len(unique) < 12:
        return None
    source = template['points'][list(unique.values())]
    target = query_points[list(unique)]
    return geometric_hit(template, source, target, image)


def geometric_hit(template, source, target, image, *, details=False):
    transform, mask = cv2.findHomography(source, target, cv2.RANSAC, 3., maxIters=700)
    if transform is None:
        return None
    keep = mask.ravel().astype(bool)
    count = int(keep.sum())
    if count < 12 or count < .32*len(source):
        return None
    h, w = template['height'], template['width']
    rect = np.float32([(0, 0), (w, 0), (w, h), (0, h)])
    quad = cv2.perspectiveTransform(rect[None], transform)[0]
    if not np.isfinite(quad).all() or not cv2.isContourConvex(quad):
        return None
    area = cv2.contourArea(quad, oriented=True)
    qh, qw = image.shape[:2]
    if not .012*qw*qh <= area <= 2.2*qw*qh:
        return None
    # Reject mirroring, or a spurious projection that extrapolates far beyond the photograph.
    visible, _ = cv2.intersectConvexConvex(quad, np.float32([(0,0),(qw,0),(qw,qh),(0,qh)]))
    if visible < .67*area:
        return None
    support = source[keep]
    coverage = min(cv2.contourArea(cv2.convexHull(support))/(w*h),
                   cv2.contourArea(cv2.convexHull(target[keep]))/area)
    if coverage < .07:
        return None
    votes = []
    for x0, y0, x1, y1 in template['zones']:
        zone = (support[:,0] >= x0) & (support[:,0] <= x1) & (support[:,1] >= y0) & (support[:,1] <= y1)
        votes.append(int(zone.sum()))
    score = count * np.sqrt(coverage)
    appearance = None
    if template['view'] == 'front':
        target_rect = np.float32([(0,0),(47,0),(47,127),(0,127)])
        aligned = cv2.warpPerspective(image, cv2.getPerspectiveTransform(quad, target_rect), (48,128))
        colors = cv2.resize(aligned,(12,32),interpolation=cv2.INTER_AREA)
        appearance = front_similarity(template['appearance'], colors)
        # The shared logo can supply more keypoints than the entire fruit illustration.
        # Make the visible lower-front artwork contribute independent evidence.
        score = np.sqrt(score) * max(0., appearance)**5

    hit = dict(id=template['id'], gtin=template['gtin'], view=template['view'], inliers=count,
               score=round(float(score),3), appearance=appearance, coverage=round(coverage,3), votes=votes)
    if details:
        return hit, support, quad, transform
    return hit


def front_similarity(reference, query):
    # Color and luminance on the fruit and juice-glass region after geometric alignment.
    left = reference[16:31, 1:11].astype(float)
    right = query[16:31, 1:11].astype(float)
    luma = np.array([.299,.587,.114])
    def vector(colors):
        gray = colors @ luma
        chroma = colors-gray[:,:,None]
        return np.concatenate(((gray-gray.mean()).ravel(), chroma.ravel()))
    a, b = vector(left), vector(right)
    return round(float(a@b / max(1., np.linalg.norm(a)*np.linalg.norm(b))), 4)


def candidates(rgb):
    h, w = rgb.shape[:2]
    if min(h, w) < 24:
        return []
    scale = 720 / max(w,h)
    image = cv2.resize(rgb, (max(1, round(w*scale)),max(1, round(h*scale))),
                       interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    keys, desc = orb().detectAndCompute(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY), None)
    if desc is None or len(keys) < 12:
        return []
    points = np.float32([key.pt for key in keys])
    hits = (locate(t, points, desc, image) for t in gallery())
    return sorted((h for h in hits if h is not None),key=lambda h:-h['score'])


def decide(hits):
    if not hits:
        return None
    best = hits[0]
    product = REGISTERED_GTINS.get(best['gtin'])
    rival = max((hit['score'] for hit in hits if hit['gtin'] != best['gtin']), default=0.)
    ambiguous = False
    if best['view'] == 'front':
        supported = (best['inliers'] >= 17 and best['votes'][0] >= 4 and best['appearance'] >= .88
                     and best['score'] >= 2.8 and best['score'] >= 1.38*rival)
        outside_rivals = [hit for hit in hits if hit['gtin'] not in REGISTERED_GTINS
                          and hit['score'] >= .65 * best['score']]
        # Shared graphics can give a registered front more keypoints. A
        # comparable rival of equal or unknown volume can still win on both
        # aligned artwork and geometric coverage.
        competing_artwork = product is not None and any(
            hit['view'] == 'front' and OTHER_VOLUMES_ML.get(hit['gtin'], 1000) == 1000
            and hit['appearance'] > best['appearance'] and hit['coverage'] >= best['coverage']
            for hit in outside_rivals
        )
        ambiguous = best['score'] >= 2.8 and (competing_artwork or (not supported and bool(outside_rivals)))
    else:
        supported = min(best['votes']) >= 3 and best['coverage'] >= .16 and best['score'] >= max(14,1.45*rival)
    if ambiguous:
        status, product = 'ambiguous', None
    elif supported:
        status = 'matched' if product else 'incompatible'
    else:
        return None
    return dict(status=status, product=product, template=best['id'], view=best['view'],
                inliers=best['inliers'], coverage=best['coverage'])


def match_pack(rgb):
    hits = candidates(rgb)
    verdict = decide(hits)
    if verdict and verdict["status"] == "ambiguous" and hits[0]["gtin"] in REGISTERED_GTINS:
        compatible = [hit for hit in hits if OTHER_VOLUMES_ML.get(hit["gtin"], 1000) == 1000]
        if len(compatible) != len(hits):
            conditional = decide(compatible)
            if conditional and conditional["status"] == "matched":
                verdict["if_printed_one_litre"] = conditional
    if verdict is None:
        from .oblique_pack import match_oblique
        return match_oblique(rgb)
    return verdict
