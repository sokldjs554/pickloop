"""Reproduce the two apple ingredient-header comparisons. Never used by the app."""

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.optimize import differential_evolution


FOOD_FACTS = "https://images.openfoodfacts.net/images/products"
GROCERY = (
    "https://raw.githubusercontent.com/marcusklasson/GroceryStoreDataset/"
    "fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/"
    "dataset/test/Packages/Juice/God-Morgon-Apple-Juice"
)
# Four corners in original pixels, clockwise from the upper left.
REFERENCES = {
    "1 L": (
        f"{FOOD_FACTS}/731/086/507/4225/3.jpg",
        "00b7083b7cd829cb0b10dd80d7680a67d1f63e7d00879279aa37ca8e4e0a8f4c",
        [(28, 56), (1710, 48), (1695, 316), (29, 321)],
    ),
    "1.75 L": (
        f"{FOOD_FACTS}/731/086/508/1650/2.jpg",
        "7ab853525829a5aae3f9f53039d96fc67277995e7e2c4c04c7a695428747696e",
        [(17, 16), (935, 0), (935, 112), (17, 123)],
    ),
}
QUERIES = {
    "RR-8e14": (
        f"{GROCERY}/God-Morgon-Apple-Juice_018.jpg",
        "8e1405c5d1997279c67f93b9e81effd077c3bc60ac673194e8c1b479337cc800",
        [(127, 92), (198, 78), (205, 265), (147, 307)],
    ),
    "RR-7660": (
        f"{GROCERY}/God-Morgon-Apple-Juice_005.jpg",
        "7660e2282261b043c6cc72f671782a349c095f46a2fb74fb85d8bd51f30df168",
        [(182, 54), (230, 86), (193, 228), (135, 236)],
    ),
}


def load_image(cache, url, digest, mode):
    path = cache / digest
    if path.exists():
        data = path.read_bytes()
    else:
        with urlopen(url, timeout=40) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Unexpected SHA-256 for {url}")
    if not path.exists():
        path.write_bytes(data)
    return cv2.imdecode(np.frombuffer(data, np.uint8), mode)


def rectify(image, corners, width, height, interpolation):
    target = [(0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)]
    transform = cv2.getPerspectiveTransform(np.float32(corners), np.float32(target))
    return cv2.warpPerspective(image, transform, (width, height), flags=interpolation)


def bandpass(image, blur):
    smoothed = gaussian_filter(image.astype(float) / 255, blur)
    return smoothed - gaussian_filter(smoothed, (3, 9))


def fit_correlation(query, reference):
    height, width = reference.shape
    y, x = np.mgrid[1 : height - 1, 2 : width - 2]
    text = reference[1:-1, 2:-2]
    text = text - text.mean(axis=1, keepdims=True)

    def loss(parameters):
        left, top, scale_x, scale_y, skew_x, skew_y, persp_x, persp_y = parameters
        denominator = 1 + persp_x * (x / width - 0.5) + persp_y * (y / height - 0.5)
        query_x = (left + x * scale_x + y * skew_x) / denominator
        query_y = (top + y * scale_y + x * skew_y) / denominator
        patch = cv2.remap(query, query_x.astype("float32"), query_y.astype("float32"), cv2.INTER_LINEAR)
        patch -= patch.mean(axis=1, keepdims=True)
        normalization = max(1e-6, np.sqrt(np.sum(text**2) * np.sum(patch**2)))
        return -np.sum(text * patch) / normalization

    bounds = [(-3, 8), (-1, 6), (0.8, 1.18), (0.65, 0.98),
              (-0.09, 0.09), (-0.06, 0.06), (-0.1, 0.1), (-0.04, 0.04)]
    return -differential_evolution(loss, bounds, seed=12, popsize=8, maxiter=55).fun


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path, help="Working directory for original images named by SHA-256")
    parser.add_argument("--study-figure", type=Path, help="Optional native JPEG XObject 132 extracted from the 2014 thesis")
    args = parser.parse_args()
    cache = args.cache
    cache.mkdir(parents=True, exist_ok=True)
    templates = {}
    for volume, (url, digest, corners) in REFERENCES.items():
        photo = load_image(cache, url, digest, cv2.IMREAD_GRAYSCALE)
        panel = rectify(photo, corners, 160, 33, cv2.INTER_LINEAR)
        templates[volume] = bandpass(panel, (0.6, 1.2))
    if args.study_figure:
        raw = args.study_figure.read_bytes()
        if hashlib.sha256(raw).hexdigest() != "3e4751e3778cc579f56f3c0e9ad8b87d7cd2a497212d4c29e89e0efa029041d0":
            raise ValueError("Expected the unmodified 711 x 404 px apple XObject from Appendix A")
        photo = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
        corners = [(499, 86), (708, 87), (707, 119), (500, 118)]
        templates["2014 1 L"] = bandpass(rectify(photo, corners, 160, 33, cv2.INTER_LINEAR), (0.6, 1.2))
    for sample, (url, digest, corners) in QUERIES.items():
        photo = load_image(cache, url, digest, cv2.IMREAD_COLOR)
        panel = rectify(photo, corners, 330, 570, cv2.INTER_CUBIC)
        # Preserve the JPEG encode/decode used to extract the original diagnostic crops.
        success, jpeg = cv2.imencode(".jpg", panel, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not success:
            raise ValueError("JPEG encoding failed")
        gray = cv2.imdecode(jpeg, cv2.IMREAD_GRAYSCALE)
        query = bandpass(cv2.resize(gray, (160, 280), interpolation=cv2.INTER_AREA), (0.4, 0.6))
        for volume, template in templates.items():
            print(f"{sample} vs {volume}: {fit_correlation(query, template):.3f}", flush=True)


if __name__ == "__main__":
    main()
