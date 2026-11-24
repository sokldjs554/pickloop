import json
from pathlib import Path
import time

import numpy as np
from PIL import Image
import pytest

from pickloop.order_pick import MIX, ORANGE, choose, inspect_face, save_depth, shipping_label_decision
from pickloop.types import Observation, OperationError


def candidate(prediction, raw):
    return {'prediction': prediction, 'generic': {'prediction': raw}}


def test_unique_order_never_resolves_by_slot_or_fallback():
    orange = candidate(ORANGE, ORANGE)
    mixed = candidate(MIX, MIX)
    assert choose(ORANGE, [mixed, orange]) is orange
    assert choose(ORANGE, [orange, mixed]) is orange
    with pytest.raises(OperationError, match='ORDER_AMBIGUOUS'):
        choose(ORANGE, [orange, dict(orange)])
    with pytest.raises(OperationError, match='ORDER_LABEL_UNCONFIRMED'):
        choose(ORANGE, [orange, candidate('UNKNOWN', ORANGE)])
    with pytest.raises(OperationError, match='ORDER_NOT_FOUND'):
        choose(ORANGE, [mixed, candidate('UNKNOWN', 'UNKNOWN')])


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
    for name in ('orange', 'orange-swapped', 'mixed'):
        case = cases[name]
        assert case['status'] == 'COMPLETED' and case['placement_camera']['verified']
        assert case['evaluation']['verified'] and case['evaluation']['delivered_sku'] == case['order_sku']
        assert not case['evaluation']['attached_at_finish'] and case['evaluation']['collisions'] == case['evaluation']['drops'] == 0
        assert [e['value'] for e in case['trace'] if e['stage'] == 'VALVE_COMMAND'] == [True, False]
        assert case['clip_frames'] > 5 and (root/name/case['clip']).is_file()
    assert cases['orange-swapped']['selected']['position_m'][0] - cases['orange']['selected']['position_m'][0] > .1
    for name, reason in [('mixed-standard','ORDER_NOT_FOUND'), ('unreadable','ORDER_LABEL_UNCONFIRMED'),
                         ('ambiguous','ORDER_AMBIGUOUS'), ('absent','ORDER_NOT_FOUND')]:
        case = cases[name]
        assert case['status'] == 'HELD' and case['reason'] == reason and case['selected'] is None
        assert [e['stage'] for e in case['trace']] == ['OBSERVE', 'HELD']
        assert case['evaluation']['delivered_sku'] is None and case['clip'] is None
