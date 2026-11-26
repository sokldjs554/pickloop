"""Experimental single-face evidence for outside product families. No SKU or order output."""
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps

cv2.setNumThreads(1)

@dataclass
class Features:
    gray: np.ndarray
    points: np.ndarray
    descriptors: np.ndarray


def pixels(path):
    image = ImageOps.exif_transpose(Image.open(path)).convert('RGBA')
    canvas = Image.new('RGBA', image.size, 'white')
    canvas.alpha_composite(image)
    return np.asarray(canvas.convert('RGB'))


def features(image, maxdim):
    height, width = image.shape[:2]
    scale = maxdim / max(width, height)
    size = max(1, round(width * scale)), max(1, round(height * scale))
    image = cv2.resize(image, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    points, descriptors = cv2.ORB_create(nfeatures=2400, edgeThreshold=9, fastThreshold=8).detectAndCompute(gray, None)
    return Features(gray, np.float32([p.pt for p in points]).reshape(-1, 2), descriptors)


def matte_crop(image):
    corners = np.stack((image[0,0], image[-1,0], image[0,-1], image[-1,-1]))
    if np.min(corners) < 218:
        return image
    y, x = np.where(np.min(image, axis=2) < 215)
    return image[y.min():y.max()+1, x.min():x.max()+1] if len(y) else image


def template(image, annotation):
    image = matte_crop(image) if annotation.get('trim') else image
    ref = features(image, 700)
    height, width = ref.gray.shape
    zones = [np.rint(np.array(box) * [width, height, width, height]).astype(int) for box in annotation['regions']]
    return ref, zones


def descriptor_pairs(ref, query):
    if ref.descriptors is None or query.descriptors is None or len(query.descriptors) < 2:
        return []
    best = {}
    for choices in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(ref.descriptors, query.descriptors, k=2):
        if len(choices) != 2:
            continue
        match, other = choices
        if match.distance >= .79 * other.distance or match.distance > 64:
            continue
        if match.trainIdx not in best or match.distance < best[match.trainIdx].distance:
            best[match.trainIdx] = match
    return list(best.values())


def zone_correlation(ref, aligned, zone):
    x, y, right, bottom = zone
    width, height = right - x, bottom - y
    scale = min(1., 80 / width, 24 / height)
    size = max(12, round(width * scale)), max(8, round(height * scale))
    ref_patch = cv2.resize(ref[y:bottom,x:right], size, interpolation=cv2.INTER_AREA)
    query_patch = cv2.resize(aligned[y:bottom,x:right], size, interpolation=cv2.INTER_AREA)
    def highpass(a):
        a = a.astype(np.float32)
        return a - cv2.GaussianBlur(a, (0,0), 2)
    aa, bb = highpass(ref_patch), highpass(query_patch)
    return float(np.sum(aa * bb) / max(1., np.linalg.norm(aa) * np.linalg.norm(bb)))


def projected(ref, query, matched):
    if len(matched) < 12:
        return None
    a = np.float32([ref.points[m.queryIdx] for m in matched])
    b = np.float32([query.points[m.trainIdx] for m in matched])
    hom, sel = cv2.findHomography(a, b, cv2.RANSAC, 3.5, maxIters=1000, confidence=.995)
    if hom is None or int(sel.sum()) < 12:
        return None
    return hom, a[sel.ravel() != 0]


def observe(ref, zones, query):
    """One registered logo and all title bands must occupy one dominant front plane."""
    matches = descriptor_pairs(ref, query)
    projected_face = projected(ref, query, matches)
    if projected_face is None:
        return None
    hom, selected = projected_face
    rh, rw = ref.gray.shape
    qh, qw = query.gray.shape
    quad = cv2.perspectiveTransform(np.float32([[[0,0],[rw,0],[rw,rh],[0,rh]]]), hom)[0]
    if not np.isfinite(quad).all() or not cv2.isContourConvex(quad):
        return None
    area = cv2.contourArea(quad, oriented=True)
    frame = np.float32([[0,0],[qw,0],[qw,qh],[0,qh]])
    if not .18 < area / (qw * qh) < 2.15 or cv2.intersectConvexConvex(quad, frame)[0] < .66 * area:
        return None
    center = quad.mean(0) / [qw, qh]
    if abs(center[0]-.5) > .17 or abs(center[1]-.5) > .24 or np.ptp(quad[:,0]) < .55 * min(qw, qh):
        return None
    # All complete bands, not merely the fitted package boundary, must be visible.
    aligned = cv2.warpPerspective(query.gray, hom, (rw,rh), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    ncc, counts = [], []
    for x,y,right,bottom in zones:
        zone_quad = cv2.perspectiveTransform(np.float32([[[x,y],[right,y],[right,bottom],[x,bottom]]]), hom)[0]
        if not cv2.isContourConvex(zone_quad) or not all(cv2.pointPolygonTest(frame, tuple(map(float, p)), False) >= 0 for p in zone_quad):
            return None
        local = selected[(selected[:,0]>=x)&(selected[:,0]<=right)&(selected[:,1]>=y)&(selected[:,1]<=bottom)]
        if len(local) < 3 or np.ptp(local[:,0]) < .30 * (right-x):
            return None
        counts.append(len(local))
        ncc.append(round(zone_correlation(ref.gray, aligned, (x,y,right,bottom)),4))
    if min(ncc) < .60:
        return None
    # Seek an independent second copy of this brand mark away from the chosen
    # face. Recompute the nearest-neighbour set after removing foreground points.
    others = [i for i,p in enumerate(query.points) if cv2.pointPolygonTest(quad, tuple(map(float,p)), False) < 0]
    x,y,right,bottom=zones[0]
    brand=(ref.points[:,0]>=x)&(ref.points[:,0]<=right)&(ref.points[:,1]>=y)&(ref.points[:,1]<=bottom)
    if len(others)>=12 and sum(brand)>=12:
        logo=Features(ref.gray,ref.points[brand],ref.descriptors[brand])
        rest=Features(query.gray,query.points[others],query.descriptors[others])
        if projected(logo, rest, descriptor_pairs(logo, rest)) is not None:
            return None
    return {'ncc':ncc,'local_inliers':counts,'pose_inliers':len(selected)}


def read(image, templates):
    if image.shape[1] > image.shape[0] * 1.35:
        return {}
    evidence = {}
    for size in (640,1000):
        query = features(image, size)
        for family, source_id, (ref, zones) in templates:
            hit = observe(ref, zones, query)
            if hit:
                evidence.setdefault(family, []).append(dict(source=source_id,scale=size,**hit))
    return evidence
