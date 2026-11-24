import hashlib
import json
from pathlib import Path

import pytest

from pickloop.produce_rescue import PRODUCE, TARGETS, apply_produce_rescue, decide, eligibility, verified_weights


def held(**args):
    return dict(dict(prediction='UNKNOWN', generic_prediction='UNKNOWN', generic_top1='Banana',
                     support=.70, recognition_source='package_text', recognition_reason='brand_unverified',
                     recognition_text=[], recognition_gtins=[]), **args)


def two(name='banana', p=.95):
    return [dict(label=name, probability=p, margin=.9)]*2


def test_different_produce_candidate_needs_stronger_consensus():
    assert decide(held(), two(p=.80))[0] == 'Banana'
    assert decide(held(generic_top1='Zucchini'), two('cucumber',.89))[0] is None
    assert decide(held(generic_top1='Zucchini', support=.49), two('cucumber',.99))[0] is None
    assert decide(held(generic_top1='Zucchini'), two('cucumber',.95))[0] == 'Cucumber'
    assert decide(held(), two('strawberry'))[0] is None
    assert decide(held(), [two('banana')[0],two('cucumber')[0]])[0] is None


def test_named_upstream_or_package_hold_cannot_be_promoted():
    def must_not_read():
        raise AssertionError('vetoed image reached auxiliary classifier')
    for row in [held(prediction='Orange'), held(generic_top1='God-Morgon-Apple-Juice'),
                held(generic_prediction='Banana'), held(recognition_gtins=['1234567890128']),
                held(recognition_source='barcode'), held(recognition_text=['GOD MORGON apple JUICE']),
                held(recognition_reason='conflicting_flavours')]:
        assert eligibility(row) is not None
        out = apply_produce_rescue(row, must_not_read)
        assert out['prediction'] == row['prediction'] and not out['produce_rescue']['views']


def test_registry_only_has_fine_grained_counterparts():
    reg = json.loads((Path(__file__).resolve().parents[1]/'docs/experiments/grocery-catalogue/registry.json').read_text())
    assert PRODUCE == {r['name'] for r in reg if r['group'] in ('Fruit','Vegetables')}
    assert set(TARGETS.values()) == {'Banana','Pineapple','Cucumber'}


def test_rejects_untrusted_weights(tmp_path):
    bad = tmp_path/'resnet18.pth'; bad.write_bytes(b'not the published state dict')
    with pytest.raises(ValueError, match='SHA-256'):
        verified_weights(bad)
