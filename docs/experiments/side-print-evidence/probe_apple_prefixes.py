"""Check whether short quantity/market fragments survive erasure. Offline experiment only."""

import argparse
import hashlib
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.optimize import differential_evolution

from probe_apple import FOOD_FACTS, QUERIES, REFERENCES, load_image, rectify


# Coordinates refer to each source after resize to the specified width. Each triplet
# gives the end of the country abbreviation, the center of the line, and its cap height.
LAYOUT = {
    "Swedish 1 L": (380, {"SE": (24, 23, 13)}),
    "Swedish 1.75 L": (420, {"SE": (25, 16, 10), "FI": (20, 102, 10), "DK": (22, 200, 10),
                             "NO": (25, 262, 10), "UK": (22, 350, 10), "DE": (22, 412, 10)}),
    "Finnish ref": (300, {"FI": (36, 84, 9), "SE": (45, 194, 9), "UK": (48, 288, 9)}),
    "Finnish holdout": (300, {"FI": (18, 42, 9), "SE": (27, 162, 9), "UK": (26, 263, 9)}),
    "Swedish 2014": (711, {"SE": (517, 94, 8), "FI": (517, 131, 8), "DK": (519, 170, 8),
                           "NO": (521, 203, 8), "UK": (525, 235, 7), "DE": (526, 255, 8)}),
    "Swedish orange 1.75 L": (380, {"SE": (17, 35, 11)}),
    "RR-8e14": (330, {"SE": (29, 10, 10), "FI": (28, 112, 10), "DK": (31, 224, 10),
                      "NO": (33, 289, 10), "UK": (35, 389, 10), "DE": (32, 475, 10)}),
    "RR-7660": (330, {"SE": (24, 12, 10), "FI": (24, 116, 10), "DK": (28, 232, 10),
                      "NO": (27, 294, 10), "UK": (27, 392, 10), "DE": (26, 477, 10)}),
}
SOURCES = {
    "Swedish 1 L": REFERENCES["1 L"][:2],
    "Swedish 1.75 L": REFERENCES["1.75 L"][:2],
    "Finnish ref": (f"{FOOD_FACTS}/641/513/005/0506/1.jpg",
                    "8002e17bcce9369fc5e2b5332ab78732b069c4a63762b5b03a9d75304e198360"),
    "Finnish holdout": (f"{FOOD_FACTS}/641/513/005/0506/5.jpg",
                        "53605696c98a19631de8625946c8ddc2b6e4c8e9b61addc3f42aa52f73c79f78"),
    "Swedish orange 1.75 L": (f"{FOOD_FACTS}/731/086/507/4768/4.jpg",
                              "1014461837dafd6c83c7859362c90c43f3e6c147d52cfa80715bb54d4f65120d"),
}
LANGUAGES = ("SE", "FI", "UK")


def collect(cache, figure):
    image_bytes = figure.read_bytes()
    if hashlib.sha256(image_bytes).hexdigest() != "3e4751e3778cc579f56f3c0e9ad8b87d7cd2a497212d4c29e89e0efa029041d0":
        raise ValueError("Expected native PDF image 132")
    source = {"Swedish 2014": cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)}
    for name, (url, digest) in SOURCES.items():
        source[name] = load_image(cache, url, digest, cv2.IMREAD_GRAYSCALE)
    for name, (url, digest, corners) in QUERIES.items():
        photo = load_image(cache, url, digest, cv2.IMREAD_COLOR)
        panel = rectify(photo, corners, 330, 570, cv2.INTER_CUBIC)
        success, jpeg = cv2.imencode(".jpg", panel, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not success:
            raise ValueError("Could not encode panel crop")
        source[name] = cv2.imdecode(jpeg, cv2.IMREAD_GRAYSCALE)
    for key, image in source.items():
        width = LAYOUT[key][0]
        size = (width, round(image.shape[0] * width / image.shape[1]))
        source[key] = cv2.resize(image, size, interpolation=cv2.INTER_AREA).astype("float32")
    return source


def scores(source, observation, language, centers, mode):
    # The first window includes the short amount after the country code. The other
    # two windows separately examine the code itself and the subsequent first word.
    if mode == "amount":
        y, x = np.mgrid[-.65:.66:.12, -.5:3.26:.12]
        candidates = {"1 L": ["Finnish ref", "Swedish 1 L"],
                      "1.75 L": ["Swedish 1.75 L"], "unprinted": ["Swedish 2014"]}
        bounds = [(-.75, .75), (-.40, .40), (.70, 1.30), (.70, 1.30), (-.12, .12)]
        blur, iterations, population = (.13, .22), 30, 7
    elif mode == "country":
        y, x = np.mgrid[-.7:.71:.13, -2.05:.01:.13]
        candidates = {k: ["Swedish 1.75 L", "Finnish ref", "Swedish 2014"] for k in LAYOUT["Swedish 1.75 L"][1]}
        bounds = [(-.45, .45), (-.4, .4), (.77, 1.25), (.77, 1.25), (-.12, .12)]
        blur, iterations, population = (.1, .18), 23, 5
    else:
        y, x = np.mgrid[-.7:.71:.12, 2.3:10:.16]
        candidates = {k: ["Finnish ref", "Swedish 1 L"] for k in LANGUAGES}
        bounds = [(-.6, .6), (-.4, .4), (.68, 1.32), (.7, 1.3), (-.12, .12)]
        blur, iterations, population = (.13, .22), 30, 7
    x, y = x.astype("float32"), y.astype("float32")

    def pattern(image, left, center, height, sx=1, sy=1, slope=0):
        dx = height * sx * x
        crop = cv2.remap(image, (left + dx).astype("float32"),
                         (center + height * sy * y + slope * dx).astype("float32"), cv2.INTER_LINEAR)
        crop -= crop.mean(axis=1, keepdims=True)
        return crop.ravel() / (np.linalg.norm(crop) + 1e-8)

    result = {}
    for candidate, refs in candidates.items():
        templates = []
        for ref in refs:
            key = language if mode == "amount" else candidate
            if key not in LAYOUT[ref][1]:
                continue
            rx, ry, rh = LAYOUT[ref][1][key]
            smoothed = gaussian_filter(source[ref], (blur[0] * rh, blur[1] * rh))
            templates.append(pattern(smoothed, rx, ry, rh))
        if not templates:
            continue
        qx, qy, qh = centers[language]

        def loss(parameters):
            dx, dy, sx, sy, slope = parameters
            patch = pattern(observation, qx + dx * qh, qy + dy * qh, qh, sx, sy, slope)
            return -max(patch @ template for template in templates)

        fit = differential_evolution(loss, bounds, seed=13, maxiter=iterations, popsize=population)
        result[candidate] = round(float(-fit.fun), 3)
    return result


def erase_amounts(image, centers):
    result = image.copy()
    for language in LANGUAGES:
        if language not in centers:
            continue
        x, y, h = centers[language]
        neighborhood = image[max(0, round(y - h)):round(y + h), max(0, x - 4):round(x + 3 * h)]
        result[max(0, round(y - .7 * h)):round(y + .7 * h), x:round(x + 2.4 * h)] = neighborhood.min()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("study_figure", type=Path)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    source = collect(args.cache, args.study_figure)
    for name in ("Finnish holdout", "Swedish orange 1.75 L", "RR-7660", "RR-8e14"):
        centers = LAYOUT[name][1]
        image = source[name]
        erased = erase_amounts(image, centers)
        for language in LANGUAGES:
            if language not in centers:
                continue
            for mode in ("amount", "country", "first word"):
                print(name, language, mode, scores(source, image, language, centers, mode))
            print(name, language, "erased amount", scores(source, erased, language, centers, "amount"))


if __name__ == "__main__":
    main()
