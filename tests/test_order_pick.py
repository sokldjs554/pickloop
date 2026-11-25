import json
from pathlib import Path
import time

import numpy as np
from PIL import Image
import pytest

from pickloop.order_pick import MIX, ORANGE, choose, confirmed_volume, inspect_face, pick_plan, save_depth, shipping_label_decision
from pickloop.types import Observation, OperationError


def candidate(prediction, raw, identifier='a', distance=.2, volume=1000, eligible=True):
    return {'candidate_id': identifier, 'prediction': prediction, 'generic': {'prediction': raw},
            'shipping_label': {'volume_ml': volume, 'volume_status': 'confirmed' if volume else 'unreadable'},
            'pick_plan': {'eligible': eligible, 'approach_distance_m': distance}}


def test_one_copy_is_selected_by_reachable_approach_then_stable_id():
    near = candidate(ORANGE, ORANGE)
    far = candidate(ORANGE, ORANGE, 'b', .3)
    mixed = candidate(MIX, MIX)
    for rows in ([far, mixed, near], [near, mixed, far]):
        assert choose(ORANGE, rows, 1000) is near
    near['pick_plan']['eligible'] = False
    assert choose(ORANGE, [near, far], 1000) is far
    far['pick_plan']['eligible'] = False
    with pytest.raises(OperationError, match='ORDER_NO_SAFE_APPROACH'):
        choose(ORANGE, [near, far], 1000)
    tied = candidate(ORANGE, ORANGE, 'b')
    first = candidate(ORANGE, ORANGE, 'a')
    assert choose(ORANGE, [tied, first], 1000) is first


def test_candidate_approach_checks_cup_clearance_and_planner_before_suction():
    from types import SimpleNamespace

    calls = []
    def blocked(xyz, allow_contact, start=None):
        calls.append((xyz, allow_contact, start))
        raise OperationError('PATH_BLOCKED')

    cell = SimpleNamespace(tcp=[.19, -.32, .34], plan_move=blocked)
    measured = {'position_m': [.30, 0., .11], 'uncertainty_m': .002,
                'corners_base_m': [[.27,-.025,.11],[.33,-.025,.11],[.33,.025,.11],[.27,.025,.11]]}
    plan = pick_plan(cell, measured)
    assert not plan['eligible'] and plan['reason'] == 'PATH_BLOCKED'
    assert len(calls) == 1 and calls[0][1] is False
    measured['position_m'][0] = .328
    plan = pick_plan(cell, measured)
    assert not plan['eligible'] and plan['reason'] == 'INSUFFICIENT_CUP_CLEARANCE'
    assert len(calls) == 1


def test_unconfirmed_identity_and_volume_or_absent_order_hold():
    orange = candidate(ORANGE, ORANGE)
    with pytest.raises(OperationError, match='ORDER_LABEL_UNCONFIRMED'):
        choose(ORANGE, [orange, candidate('UNKNOWN', ORANGE)], 1000)
    disagreement = candidate('UNKNOWN', MIX)
    disagreement['shipping_label']['label_prediction'] = ORANGE
    with pytest.raises(OperationError, match='ORDER_LABEL_UNCONFIRMED'):
        choose(ORANGE, [orange, disagreement], 1000)
    with pytest.raises(OperationError, match='ORDER_NOT_FOUND'):
        choose(ORANGE, [candidate(MIX, MIX), candidate('UNKNOWN', 'UNKNOWN')], 1000)
    with pytest.raises(OperationError, match='ORDER_VOLUME_UNCONFIRMED'):
        choose(ORANGE, [orange, candidate(ORANGE, ORANGE, 'b', volume=None)], 1000)
    with pytest.raises(OperationError, match='ORDER_VOLUME_MISMATCH'):
        choose(ORANGE, [candidate(ORANGE, ORANGE, volume=500)], 1000)
    with pytest.raises(OperationError, match='ORDER_VOLUME_AMBIGUOUS'):
        choose(ORANGE, [orange, candidate(ORANGE, ORANGE, 'b', volume=500)])
    assert choose(ORANGE, [orange, candidate(ORANGE, ORANGE, 'b', volume=500)], 1000) is orange


@pytest.mark.parametrize('reads, expected', [
    (['ORANGE 1 L', 'ORANGE 1000 ML'], (1000, 'confirmed')),
    (['ORANGE 0,5 L', 'ORANGE 500 mL'], (500, 'confirmed')),
    (['ORANGE 1 L', 'ORANGE 500 ML'], (None, 'conflict')),
    (['250 ML 1 L', '1 L'], (None, 'conflict')),
    (['ORANGE 1 L', 'ORANGE'], (None, 'unreadable')),
    (['ORANGE', 'ORANGE'], (None, 'unreadable')),
])
def test_simulated_shipping_label_volume_needs_two_unambiguous_reads(reads, expected):
    assert confirmed_volume(reads) == expected


def test_two_optical_readings_and_accepted_head_required(monkeypatch):
    image = np.zeros((90, 95, 3), np.uint8)
    text = 'GOD MORGON ORANGE'
    results = iter([text, text, text, 'GOD MORGON', text, text, text, text])
    monkeypatch.setattr('pickloop.order_pick.ocr', lambda *_: next(results))
    carton = {'prediction':'UNKNOWN', 'juice_gate_text':[]}
    assert shipping_label_decision({'prediction':'UNKNOWN'}, carton, image, image)['prediction'] == 'UNKNOWN'
    assert shipping_label_decision({'prediction':ORANGE}, carton, image, image)['prediction'] == ORANGE
    assert shipping_label_decision({'prediction':ORANGE}, carton, image, image)['prediction'] == 'UNKNOWN'
    assert shipping_label_decision({'prediction':MIX}, carton, image, image)['prediction'] == 'UNKNOWN'
    partial_carton = {'prediction':'UNKNOWN', 'juice_gate_text':['red grapefruit']}
    assert shipping_label_decision({'prediction':ORANGE}, partial_carton, image, image)['prediction'] == 'UNKNOWN'


def test_lossless_camera_depth_encoding(tmp_path):
    depth = np.array([[1.2, 1.199, np.nan], [.1, np.inf, .9]], np.float32)
    path = tmp_path/'depth.npz'
    save_depth(path, depth)
    with np.load(path) as packed:
        restored = packed['depth_f32_u32_dx'].cumsum(axis=1, dtype=np.uint32).view(np.float32)
    assert np.array_equal(restored.view('u4'), depth.view('u4'))


def test_measured_crop_reconstructs_from_published_rgb_depth():
    root = Path(__file__).resolve().parents[1] / 'runs/order-pick/orange'
    data = json.loads((root/'result.json').read_text())
    selected = next(c for c in data['candidates'] if c['candidate_id'] == data['selected']['candidate_id'])
    c = selected['zoom']
    with np.load(root/selected['zoom_depth']) as packed:
        depth = packed['depth_f32_u32_dx'].cumsum(axis=1, dtype=np.uint32).view(np.float32)
    obs = Observation('replay', c['observation_id'], c['sim_time_s'], time.monotonic_ns(),
                      np.asarray(Image.open(root/selected['zoom_camera'])), depth, np.asarray(c['K']),
                      np.asarray(c['T_base_camera']), c['calibration_id'])
    face, geometry = inspect_face(obs, selected['position_m'])
    assert np.array_equal(face, np.asarray(Image.open(root/selected['crop'])))
    assert np.allclose(geometry['corners_base_m'], selected['corners_base_m'])
    assert c['observation_id'] != selected['confirmation']['camera']['observation_id']
    assert not np.allclose(c['K'], selected['confirmation']['camera']['K'])


def test_physical_identity_and_no_motion_holds_have_saved_evidence():
    root = Path(__file__).resolve().parents[1] / 'runs/order-pick'
    index = json.loads((root/'index.json').read_text())
    cases = {item['id']: json.loads((root/item['result']).read_text()) for item in index['runs']}
    for name in ('orange', 'orange-swapped', 'mixed', 'duplicate'):
        case = cases[name]
        assert case['status'] == 'COMPLETED' and case['placement_camera']['verified']
        assert case['evaluation']['verified'] and case['evaluation']['delivered_sku'] == case['order_sku']
        assert case['evaluation']['count_in_bin'] == 1 and case['evaluation']['wrong_placements'] == 0
        assert not case['evaluation']['attached_at_finish'] and case['evaluation']['collisions'] == case['evaluation']['drops'] == 0
        assert [e['value'] for e in case['trace'] if e['stage'] == 'VALVE_COMMAND'] == [True, False]
        assert case['clip_frames'] > 5 and (root/name/case['clip']).is_file()
    assert cases['orange-swapped']['selected']['position_m'][0] - cases['orange']['selected']['position_m'][0] > .1
    duplicate = cases['duplicate']
    matching = [c for c in duplicate['candidates'] if c['prediction'] == ORANGE]
    assert len(matching) == 2
    for candidate in matching:
        assert confirmed_volume(candidate['shipping_label']['reads']) == (1000, 'confirmed')
        assert candidate['pick_plan']['eligible']
    closest = min(matching, key=lambda c: c['pick_plan']['approach_distance_m'])
    assert duplicate['selected']['candidate_id'] == closest['candidate_id']
    assert duplicate['selected']['volume_ml'] == duplicate['evaluation']['delivered_volume_ml'] == 1000
    assert confirmed_volume(duplicate['placement_camera']['candidates'][0]['shipping_label']['reads']) == (1000, 'confirmed')
    copies = [obj for obj in duplicate['evaluation']['objects'] if obj['sku'] == ORANGE]
    assert len(copies) == 2 and sum(obj['in_bin'] for obj in copies) == 1
    other = next(obj for obj in copies if not obj['in_bin'])
    other_candidate = next(c for c in matching if c is not closest)
    assert np.linalg.norm(np.array(other['position_m'][:2]) - other_candidate['position_m'][:2]) < .003
    history = json.loads((root/'ambiguous/result.json').read_text())
    assert history['reason'] == 'ORDER_AMBIGUOUS' and 'ambiguous' not in cases
    for name, reason in [('mixed-standard','ORDER_NOT_FOUND'), ('unreadable','ORDER_LABEL_UNCONFIRMED'),
                         ('wrong-volume','ORDER_VOLUME_MISMATCH'), ('unspecified-volume','ORDER_VOLUME_AMBIGUOUS'),
                         ('unreadable-volume','ORDER_VOLUME_UNCONFIRMED'), ('absent','ORDER_NOT_FOUND')]:
        case = cases[name]
        assert case['status'] == 'HELD' and case['reason'] == reason and case['selected'] is None
        assert [e['stage'] for e in case['trace']] == ['OBSERVE', 'HELD']
        assert case['evaluation']['delivered_sku'] is None and case['clip'] is None
