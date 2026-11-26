"""Diagnostic three-vanishing-point reconstruction. This is never used to classify an upload."""

import argparse
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from probe_apple import FOOD_FACTS, GROCERY, QUERIES, load_image, rectify


FACE_SIZE = (228, 580)
TRAIN_URL = GROCERY.replace("/test/", "/train/") + "/God-Morgon-Apple-Juice_014.jpg"
TRAIN_HASH = "8e04f49f9cca94a658d6fb990eefbf835e0a3d7640b1f30dab26a4f28d0dfaa4"
# The vertical body/roof junction: front outer, shared corner, side outer.
CORNERS = {
    "RR-8e14": [(27, 88), (125, 87), (200, 78)],
    "RR-7660": [(99, 40), (183, 49), (233, 85)],
    "OFF-1L": [(80, 39), (19, 38), (0, 43)],
}
PUBLIC_REFERENCE = (
    f"{FOOD_FACTS}/731/086/507/4225/1.jpg",
    "8b1c4963382970fa6fd05daeb0cf03c37590c1fe678e9441d6bc38285a3e4a53",
    [(18, 40), (0, 45), (0, 163), (18, 173)],
)


def register_front(face, photo):
    detector = cv2.SIFT_create(nfeatures=2100, contrastThreshold=.025)
    keys, descriptors = detector.detectAndCompute(face, None)
    points = np.float32([key.pt for key in keys])
    height, width = photo.shape[:2]
    scale = 720 / max(height, width)
    best_count, best_matrix = 0, None
    for stretch in (1., 1.65, 2.):
        enlarged = cv2.resize(photo, (round(width * scale * stretch), round(height * scale)))
        target_keys, target_desc = detector.detectAndCompute(cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY), None)
        pairs = cv2.BFMatcher().knnMatch(descriptors, target_desc, k=2)
        matches = [first for first, second in pairs if first.distance < .8 * second.distance]
        if len(matches) < 10:
            continue
        target = np.float32([target_keys[m.trainIdx].pt for m in matches])
        matrix, inliers = cv2.findHomography(points[[m.queryIdx for m in matches]], target, cv2.RANSAC, 4)
        if matrix is None or inliers.sum() <= best_count:
            continue
        w, h = FACE_SIZE
        quad = cv2.perspectiveTransform(np.float32([[(0, 0), (w, 0), (w, h), (0, h)]]), matrix)[0]
        if not cv2.isContourConvex(quad) or cv2.contourArea(quad, oriented=True) < .06 * enlarged.shape[0] * enlarged.shape[1]:
            continue
        best_count = inliers.sum()
        best_matrix = np.diag([width / enlarged.shape[1], height / enlarged.shape[0], 1]) @ matrix
    if best_count < 10:
        raise ValueError("Front plane has too few matched points")
    return best_matrix


def printed_baselines(image, panel_corners, left, right):
    w, h = 210, 460
    target = np.float32([(0, 0), (w - 1, 0), (w - 1, h - 1), (0, h - 1)])
    matrix = cv2.getPerspectiveTransform(np.float32(panel_corners), target)
    panel = cv2.warpPerspective(image, matrix, (w, h), flags=cv2.INTER_CUBIC)
    columns = np.linspace(left * w, right * w, 12)
    profiles = []
    for x in columns:
        profile = panel[:, int(x) - 3:int(x) + 4].mean(axis=1)
        profiles.append(profile - gaussian_filter1d(profile, 6))
    center = (len(columns) - 1) // 2
    peaks, _ = find_peaks(gaussian_filter1d(profiles[center], 1.3), distance=6, prominence=5)
    lines = []
    for peak in peaks:
        if not 12 <= peak <= h - 12:
            continue
        rows = np.zeros(len(columns))
        rows[center] = peak
        for step in (-1, 1):
            stop = -1 if step < 0 else len(columns)
            for i in range(center + step, stop, step):
                prior = round(rows[i - step])
                start = max(0, prior - 2)
                profile = profiles[i]
                index = start + np.argmax(profile[start:min(h, prior + 3)])
                rows[i] = index
                if 0 < index < h - 1:
                    a, b, c = profile[index - 1:index + 2]
                    if a - 2 * b + c < 0:
                        rows[i] += np.clip(.5 * (a - c) / (a - 2 * b + c), -.5, .5)
        native = cv2.perspectiveTransform(np.float64([np.c_[columns, rows]]), np.linalg.inv(matrix))[0]
        dx, dy, x, y = cv2.fitLine(native.astype("float32"), cv2.DIST_HUBER, 0, .001, .001).ravel()
        lines.append([dy, -dx, dx * y - dy * x])
    return np.asarray(lines)


def recover(front, depth, corners):
    horizontal, vertical = (front[:2, i] / front[2, i] for i in (0, 1))
    rows = np.stack((horizontal - depth, vertical - depth))
    right = np.array([vertical @ rows[0], horizontal @ rows[1]])
    try:
        center = np.linalg.solve(rows, right)
    except np.linalg.LinAlgError:
        return None
    focal_squared = -(horizontal - center) @ (vertical - center)
    if focal_squared <= 0:
        return None
    focal = np.sqrt(focal_squared)
    inverse = np.linalg.inv([[focal, 0, center[0]], [0, focal, center[1]], [0, 0, 1]])
    metric = inverse @ front
    width, height = FACE_SIZE
    height_ratio = height * np.linalg.norm(metric[:, 1]) / (width * np.linalg.norm(metric[:, 0]))
    # Fit relative physical lengths of the two top segments from their shared 3-D point.
    rays = inverse @ np.c_[corners, np.ones(3)].T
    lengths = []
    for point, vanishing in ((0, horizontal), (2, depth)):
        axis = inverse @ np.r_[vanishing, 1.]
        axis /= np.linalg.norm(axis)
        system = np.stack((rays[:, point], -axis), axis=1)
        lengths.append(np.linalg.lstsq(system, rays[:, 1], rcond=None)[0][1])
    return [height_ratio, abs(lengths[1] / lengths[0])]


def synthetic_check():
    rotation, _ = cv2.Rodrigues(np.array([.3, .59, .2]))
    camera = np.array([[375, 0, 170], [0, 375, 174], [0, 0, 1]])
    origin = np.array([-.3, -.4, 3.7])

    def pixel(point):
        projected = camera @ point
        return projected[:2] / projected[2]

    horizontal, vertical, depth = rotation.T
    matrix = camera @ np.stack((horizontal / 228, vertical * 2.6 / 580, origin), axis=1)
    corners = [pixel(origin), pixel(origin + horizontal), pixel(origin + horizontal + depth * 1.1)]
    np.testing.assert_allclose(recover(matrix, pixel(depth), corners), [2.6, 1.1], atol=1e-9)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    cache = parser.parse_args().cache
    cache.mkdir(parents=True, exist_ok=True)
    synthetic_check()
    cv2.setNumThreads(1)
    train = load_image(cache, TRAIN_URL, TRAIN_HASH, cv2.IMREAD_COLOR)
    face = rectify(train, [(71, 80), (181, 52), (252, 332), (151, 347)], *FACE_SIZE, cv2.INTER_LINEAR)
    face = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    rng = np.random.default_rng(2026)
    for case, (url, digest, panel) in {**QUERIES, "OFF-1L": PUBLIC_REFERENCE}.items():
        color = load_image(cache, url, digest, cv2.IMREAD_COLOR)
        # Preserve the interpolation order used to register the original colour photo.
        matrix = register_front(face, color)
        gray = load_image(cache, url, digest, cv2.IMREAD_GRAYSCALE)
        for left, right in ((.08, .49), (.23, .66), (.08, .83), (.45, .90)):
            lines = printed_baselines(gray, panel, left, right)
            for label, chosen in (("all", lines), ("even", lines[::2]), ("odd", lines[1::2])):
                samples = []
                for _ in range(500):
                    selected = chosen[rng.integers(len(chosen), size=len(chosen))]
                    depth = np.linalg.lstsq(selected[:, :2], -selected[:, 2], rcond=None)[0]
                    corners = np.asarray(CORNERS[case]) + rng.normal(0, 1, (3, 2))
                    result = recover(matrix, depth, corners)
                    if result is not None:
                        samples.append(result)
                bounds = np.round(np.quantile(samples, [.05, .95], axis=0), 2).T if samples else "n/a"
                print(case, (left, right), label, len(chosen), "H/W, D/W", np.asarray(bounds).tolist())


if __name__ == "__main__":
    main()
