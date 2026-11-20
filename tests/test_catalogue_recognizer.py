import numpy as np
import pytest


def test_center_color_descriptor_preserves_different_products_and_ignores_border():
    from pickloop.catalogue_features import center_color
    a = np.zeros((90, 120, 3), np.uint8)
    b = a.copy()
    a[15:75, 18:102] = [200, 10, 20]
    b[15:75, 18:102] = [10, 200, 20]
    other_border = a.copy()
    other_border[:8] = 255
    assert np.linalg.norm(center_color(a)) == pytest.approx(1)
    assert np.dot(center_color(a), center_color(b)) < .3
    np.testing.assert_array_equal(center_color(a), center_color(other_border))


def test_same_catalogue_inference_accepts_a_named_item_and_holds_a_distant_input():
    from pickloop.catalogue_model import CatalogueHead

    x = np.eye(3).repeat(4, axis=0)
    head = CatalogueHead.fit(['Milk', 'Pepper', 'Pear'], x, np.arange(3).repeat(4), .5)
    head.min_support = .5
    result = head.predict(np.array([[0, .99, .01], [-.57, -.57, -.57]]))
    assert [r['prediction'] for r in result] == ['Pepper', 'UNKNOWN']
    assert result[0]['top1'] == 'Pepper'


def test_calibration_respects_correct_known_retention_and_uses_negative_examples():
    from pickloop.catalogue_model import calibrate

    known = [{'top1':'Apple','score':float(n)/100,'margin':.5,'support':.9} for n in range(21)]
    outside = [{'top1':'Apple','score':.005,'margin':.5,'support':.9} for _ in range(3)]
    gate = calibrate(known, ['Apple']*21, outside)
    assert gate['known_correct_after'] >= 20
    assert gate['outside_accepted'] == 0


def test_saved_model_repeats_each_decision_and_preserves_a_manual_hold(tmp_path):
    from pickloop.catalogue_model import CatalogueHead
    rng = np.random.default_rng(27)
    x = rng.normal(size=(12, 24)).astype('f')
    head = CatalogueHead.fit(['A', 'B', 'C'], x, np.repeat(np.arange(3), 4), .5)
    head.neighbour_weight = .35
    head.min_margin = .12
    path = tmp_path / 'head.npz'
    head.save(path)
    assert CatalogueHead.load(path).predict(x) == head.predict(x)


def test_gate_can_use_the_negative_boundary_in_a_gap_between_calibration_sets():
    from pickloop.catalogue_model import allowed, calibrate

    def observation(similarity):
        return dict(top1='Apple', support=similarity, score=.4, margin=.2)

    known = [observation(.90), observation(.95)]
    gate = calibrate(known, ['Apple', 'Apple'], [observation(.50)])
    floors = [gate[key] for key in ('support', 'score', 'margin')]
    assert not allowed(observation(.50), *floors)
    assert allowed(observation(.70), *floors)
