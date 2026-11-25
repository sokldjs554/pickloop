import numpy as np

from pickloop import oblique_pack, registered_pack


def test_side_fruit_patch_needs_visible_orange_artwork():
    transform = np.eye(3)
    reference = np.zeros((200, 100, 3), np.uint8)
    reference[130:150, 60:82] = (225, 163, 41)
    assert oblique_pack.has_orange_illustration(reference, transform, 100, 100)
    reference[130:150, 60:82] = (180, 60, 46)
    assert not oblique_pack.has_orange_illustration(reference, transform, 100, 100)
    assert not oblique_pack.has_orange_illustration(reference[:120], transform, 100, 100)


def test_ambiguous_original_read_is_preserved(monkeypatch):
    hit = dict(id="front", gtin="7310865074225", view="front", inliers=32,
               score=4, appearance=.96, coverage=.35, votes=[10, 4])
    other_market = dict(hit, gtin="6415130050506", score=3.8)
    monkeypatch.setattr(registered_pack, "candidates", lambda rgb: [hit, other_market])

    def unexpected_fallback(rgb):
        raise AssertionError("an ambiguous primary verdict already has a competing market")

    monkeypatch.setattr(oblique_pack, "match_oblique", unexpected_fallback)
    verdict = registered_pack.match_pack(np.zeros((100, 100, 3), np.uint8))
    assert verdict["status"] == "ambiguous"
    assert verdict["product"] is None


def test_sharp_geometry_on_a_background_carton_cannot_name_the_subject():
    import cv2

    points = np.float32([(x, y) for x in (10, 30, 50, 70, 90) for y in (10, 30, 50, 70, 90)])
    descriptors = np.random.default_rng(14).uniform(0, 100, (len(points), 128)).astype(np.float32)
    matcher = cv2.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=64))
    matcher.add([descriptors])
    matcher.train()
    template = dict(id=oblique_pack.ORANGE_SIDE, gtin="7310860007372", view="ingredients",
                    width=100, height=100, zones=[(0, 0, 100, 50), (0, 50, 100, 100)])
    rgb = np.full((500, 500, 3), (225, 163, 41), np.uint8)
    center = oblique_pack.foreground_hit(template, points, descriptors, matcher, 2*points + 110, rgb)
    assert center["distinctive"] and center["inliers"] == len(points)
    corner = oblique_pack.foreground_hit(template, points, descriptors, matcher, 1.5*points + 340, rgb)
    assert corner is None
