"""Verify a planar carton panel and classify its color inside the detected region."""
from dataclasses import dataclass

import cv2
import numpy as np

UNKNOWN = 'UNKNOWN'
SIZE = 440


def frame(rgb):
    h, w = rgb.shape[:2]
    scale = SIZE / max(h, w)
    return cv2.resize(rgb, (max(1, round(w * scale)), max(1, round(h * scale))),
                      interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR), scale


def polygon_mask(shape, polygon):
    mask = np.zeros(shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, np.rint(polygon).astype(np.int32), 255)
    return mask


def chroma(hsv, mask):
    pixels = hsv[(mask > 0) & (hsv[:, :, 1] >= 50) & (hsv[:, :, 2] >= 38), 0]
    if len(pixels) < 30:
        return np.zeros(24)
    hist = np.bincount(pixels.astype(int) * 24 // 180, minlength=24).astype(float)
    smooth = .6 * hist + .2 * (np.roll(hist, 1) + np.roll(hist, -1))
    return np.sqrt(smooth / smooth.sum())


def sift(image, mask=None):
    detector = cv2.SIFT_create(nfeatures=900, contrastThreshold=.02)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    keys, descriptors = detector.detectAndCompute(gray, mask)
    points = np.array([k.pt for k in keys], dtype=np.float32).reshape(-1, 2)
    if descriptors is None:
        return points, np.empty((0, 128), np.float32)
    return points, descriptors


@dataclass
class Template:
    name: str
    polygon: np.ndarray
    points: np.ndarray
    descriptors: np.ndarray
    color: np.ndarray


class CartonMatcher:
    def __init__(self, templates):
        self.templates = templates
        self.names = sorted({t.name for t in templates})
        if len(self.names) != 2 or any(len(t.points) < 6 for t in templates):
            raise ValueError('need two registered classes and six keypoints per panel')
        self.descriptors = np.vstack([t.descriptors for t in templates])
        self.offsets = np.cumsum([0] + [len(t.points) for t in templates])

    @classmethod
    def register(cls, regions):
        templates = []
        for name, rgb, poly in regions:
            image, scale = frame(rgb)
            polygon = np.asarray(poly, np.float32) * scale
            mask = polygon_mask(image.shape, polygon)
            pts, desc = sift(image, mask)
            color = chroma(cv2.cvtColor(image, cv2.COLOR_RGB2HSV), mask)
            templates.append(Template(name, polygon, pts, desc, color))
        return cls(templates)

    def save(self, path):
        values = {'version': 1, 'names': [t.name for t in self.templates]}
        for i, t in enumerate(self.templates):
            for key in ('polygon', 'points', 'descriptors', 'color'):
                values[f'{i}_{key}'] = getattr(t, key)
        np.savez_compressed(path, **values)

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as file:
            if file['version'].item() != 1:
                raise ValueError('unsupported gallery version')
            return cls([Template(str(name), *(file[f'{i}_{key}'] for key in
                                              ('polygon', 'points', 'descriptors', 'color')))
                        for i, name in enumerate(file['names'])])

    @staticmethod
    def locate(template, pairs, points, shape):
        # One target point gets at most one vote, including on repeated letters.
        pairs = sorted(pairs, key=lambda p: p[2])
        unique = {}
        for source, target, _ in pairs:
            unique.setdefault(target, source)
        if len(unique) < 6:
            return None
        src = template.points[list(unique.values())]
        dst = points[list(unique)]
        transform, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 4.0, maxIters=600)
        if transform is None:
            return None
        keep = inliers.ravel().astype(bool)
        count = int(keep.sum())
        if count < 6 or count < .30 * len(src):
            return None
        polygon = cv2.perspectiveTransform(template.polygon[None], transform)[0]
        if not np.isfinite(polygon).all() or not cv2.isContourConvex(polygon):
            return None
        area = cv2.contourArea(polygon, oriented=True)
        h, w = shape[:2]
        if not .045 * w * h <= area <= .92 * w * h:
            return None
        center = polygon.mean(axis=0) / (w, h)
        if np.any(np.abs(center - .5) > .34):
            return None
        bounds = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        visible, _ = cv2.intersectConvexConvex(bounds, polygon)
        if visible < .75 * area:
            return None
        coverage = cv2.contourArea(cv2.convexHull(src[keep])) / cv2.contourArea(template.polygon)
        target_coverage = cv2.contourArea(cv2.convexHull(dst[keep])) / area
        if min(coverage, target_coverage) < .045:
            return None
        return polygon, count, count * np.sqrt(min(coverage, target_coverage))

    def predict(self, rgb):
        image, _ = frame(rgb)
        pts, desc = sift(image)
        empty = dict(prediction=UNKNOWN, reason='panel_unverified', inliers=0, color_similarity=0., color_gap=0.)
        if len(desc) < 6:
            return empty
        cv2.setRNGSeed(441)
        matcher = cv2.FlannBasedMatcher(dict(algorithm=1, trees=3), dict(checks=48))
        matches = matcher.knnMatch(self.descriptors, desc, k=2)
        groups = [[] for _ in self.templates]
        for match, alternative in matches:
            if match.distance < .76 * alternative.distance:
                index = int(np.searchsorted(self.offsets, match.queryIdx, side='right') - 1)
                groups[index].append((match.queryIdx - self.offsets[index], match.trainIdx, match.distance))
        locations = []
        for template, pairs in zip(self.templates, groups, strict=True):
            location = self.locate(template, pairs, pts, image.shape)
            if location is not None:
                locations.append(location)
        if not locations:
            return empty
        polygon, count, _ = max(locations, key=lambda loc: loc[2])
        hist = chroma(cv2.cvtColor(image, cv2.COLOR_RGB2HSV), polygon_mask(image.shape, polygon))
        # A single reference side panel can have the color of either SKU.
        similarities = [float(np.median([hist @ t.color for t in self.templates if t.name == name]))
                        for name in self.names]
        best = int(np.argmax(similarities))
        score, gap = similarities[best], abs(similarities[0] - similarities[1])
        accepted = score >= .65 and gap >= .08
        return dict(prediction=self.names[best] if accepted else UNKNOWN,
                    reason='verified' if accepted else 'ambiguous_panel_color', inliers=count,
                    color_similarity=score, color_gap=gap)


def main():
    import argparse
    import json
    from pathlib import Path
    from PIL import Image, ImageOps

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--gallery', type=Path, default=Path(__file__).resolve().parents[2] /
                        'docs/experiments/carton-panels/gallery.npz')
    args = parser.parse_args()
    cv2.setNumThreads(1)
    with Image.open(args.image) as source:
        rgb = np.asarray(ImageOps.exif_transpose(source).convert('RGB'))
    print(json.dumps(CartonMatcher.load(args.gallery).predict(rgb), indent=2))


if __name__ == '__main__':
    main()
