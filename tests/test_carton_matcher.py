import cv2
import numpy as np


def test_plain_or_blank_scene_returns_unknown():
    from pickloop.carton_matcher import CartonMatcher

    ref = np.random.default_rng(80).integers(0, 255, (180, 180, 3), dtype=np.uint8)
    poly = np.float32([[8, 8], [172, 8], [172, 172], [8, 172]])
    matcher = CartonMatcher.register([('A', ref, poly), ('B', ref[:, ::-1].copy(), poly)])
    assert matcher.predict(np.zeros_like(ref))['prediction'] == 'UNKNOWN'


def test_planar_packaging_match_distinguishes_print_color_and_rejects_tiny_shelf_logo():
    from pickloop.carton_matcher import CartonMatcher

    def pack(color):
        img = np.full((180, 150, 3), color, np.uint8)
        cv2.putText(img, 'BRAVO', (8, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (245, 245, 245), 3)
        rng = np.random.default_rng(4)
        for x, y in rng.integers([12, 90], [139, 163], size=(24, 2)):
            cv2.circle(img, (int(x), int(y)), 3, (35, 35, 35), -1)
        return img

    a, b = pack((14, 136, 56)), pack((244, 160, 12))
    poly = np.float32([[2, 2], [147, 2], [147, 177], [2, 177]])
    matcher = CartonMatcher.register([('A', a, poly), ('B', b, poly)])
    scene = np.full((280, 320, 3), 125, np.uint8)
    scene[52:232, 103:253] = b
    assert matcher.predict(scene)['prediction'] == 'B'
    scene[:] = 125
    scene[10:46, 10:40] = cv2.resize(b, (30, 36))
    assert matcher.predict(scene)['prediction'] == 'UNKNOWN'
