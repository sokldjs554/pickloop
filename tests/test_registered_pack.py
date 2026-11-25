"""Regression checks for registered artwork, ambiguous variants and strict order identity."""
import numpy as np
import pytest

from pickloop import photo_readout, registered_pack
from pickloop.juice_gate import APPLE, ORANGE


def hit(gtin='7310865074225', score=7., view='front', votes=(30, 1), appearance=.95):
    return dict(id='reference', gtin=gtin, view=view, votes=votes, inliers=52,
                coverage=.34, score=score, appearance=appearance)


def test_shared_pack_face_requires_fruit_artwork_and_separation_from_other_market():
    assert registered_pack.decide([hit()])['product'] == APPLE
    assert registered_pack.decide([hit(appearance=.5)]) is None
    finnish_apple = hit(gtin='6415130050506', score=6.5)
    ambiguous = registered_pack.decide([hit(), finnish_apple])
    assert ambiguous['status'] == 'ambiguous' and ambiguous['product'] is None
    negative = registered_pack.decide([finnish_apple])
    assert negative['status'] == 'incompatible' and negative['product'] is None


def test_nutrition_needs_header_numeric_column_and_lower_text():
    missing_numbers = hit(view='nutrition', score=60, votes=(41, 0, 11), appearance=None)
    assert registered_pack.decide([missing_numbers]) is None
    assert registered_pack.decide([dict(missing_numbers, votes=(29, 12, 11))])['product'] == APPLE


@pytest.mark.parametrize('reads,quantity,expected', [
    ([], [], APPLE),
    (['ORANGE', 'ORANGE'], [], None),
    ([], ['1.75 L'], None),
    (['selected blend'], [], None),
])
def test_artwork_readout_vetoes_competing_print_and_never_confirms_order(monkeypatch, reads, quantity, expected):
    image = np.zeros((24, 24, 3), np.uint8)
    panel = registered_pack.decide([hit()])
    monkeypatch.setattr(photo_readout, 'match_pack', lambda image: panel)
    monkeypatch.setattr(photo_readout, 'read_size_band', lambda image: quantity)
    upstream = dict(prediction='UNKNOWN', recognition_source='package_text', recognition_reason='brand_unverified',
                    recognition_text=reads, recognition_gtins=[])
    result = photo_readout.photo_readout(upstream, require_gtin=True, rgb=image)
    assert result['photo_name'] == expected
    assert result['prediction'] == 'UNKNOWN'
    assert result['confirmed_order_sku'] is result['confirmed_gtin'] is None


def test_incompatible_market_vetoes_even_printed_one_litre(monkeypatch):
    image = np.zeros((24, 24, 3), np.uint8)
    panel = registered_pack.decide([hit(gtin='6415130050490')])
    monkeypatch.setattr(photo_readout, 'match_pack', lambda image: panel)
    monkeypatch.setattr(photo_readout, 'read_size_band', lambda image: ['1 L', '1 L'])
    upstream = dict(prediction=ORANGE, recognition_source='package_text', recognition_reason='brand_and_orange',
                    recognition_text=['GOD MORGON ORANGE'], recognition_gtins=[])
    result = photo_readout.photo_readout(upstream, rgb=image)
    assert result['prediction'] == 'UNKNOWN' and result['size_status'] == 'printed_1l'
    assert result['photo_name_reason'] == 'incompatible_pack_artwork'


def test_decoded_unregistered_code_bypasses_artwork(monkeypatch):
    image = np.zeros((24, 24, 3), np.uint8)
    monkeypatch.setattr(photo_readout, 'match_pack', lambda image: pytest.fail('barcode must take priority'))
    upstream = dict(prediction='UNKNOWN', recognition_source='barcode', recognition_reason='unregistered_gtin',
                    recognition_text=[], recognition_gtins=['6415130050490'])
    result = photo_readout.photo_readout(upstream, rgb=image)
    assert result['photo_name'] is result['confirmed_order_sku'] is None
    assert result['registered_pack'] is None
