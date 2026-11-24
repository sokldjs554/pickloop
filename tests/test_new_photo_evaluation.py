"""Small independent cases for blind inference and exact-SKU reporting."""
import csv
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image
import pytest


@pytest.fixture
def evaluator():
    script = Path(__file__).parents[1]/'scripts/evaluate_new_photos.py'
    spec = importlib.util.spec_from_file_location('new_photo_evaluation', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(truth, before, after, group='package-1'):
    return dict(exact_truth=truth, before_prediction=before, after_prediction=after,
                family_truth=truth, source_group=group)


def test_denominators_keep_unknown_holds_out_of_exact_name_recall(evaluator):
    result = evaluator.paired_metrics([
        row('Lime', 'Lime', 'UNKNOWN'), row('Pear', 'Lime', 'Pear', 'package-2'),
        row('UNKNOWN', 'Lime', 'UNKNOWN'), row('UNKNOWN', 'UNKNOWN', 'Pear'),
    ])
    assert (result['n'], result['known'], result['unknown'], result['source_groups']) == (4, 2, 2, 2)
    assert result['after']['known_exact_recall'] == .5
    assert result['after']['correct_names'] == 1
    assert result['after']['named_wrong'] == 1
    assert result['after']['held'] == 2
    assert result['after']['unknown_false_accepts'] == 1
    assert result['after']['unknown_false_accept_rate'] == .5
    assert result['formerly_correct_to_bad'] == 1
    assert result['paired_transitions']['correct->held'] == 1
    assert result['paired_transitions']['wrong->correct'] == 1
    assert result['paired_transitions']['correct_rejection->false_accept'] == 1


def test_empty_role_has_explicit_zero_denominators(evaluator):
    m = evaluator.paired_metrics([])
    assert m['n'] == m['known'] == m['unknown'] == 0
    assert m['before']['known_exact_recall'] is None
    assert m['after']['unknown_false_accept_rate'] is None


def test_alternate_gtin_is_not_an_exact_name_hit(evaluator):
    label = dict(truth='UNKNOWN', family_truth='God-Morgon-Apple-Juice',
                 gtin='9999999999999', exact_sku_status='alternate_gtin_family')
    assert evaluator.exact_role(label, prior=False) == ('UNKNOWN', 'alternate_gtin_challenge')
    with pytest.raises(ValueError, match='GTIN'):
        evaluator.exact_role({**label, 'truth': 'God-Morgon-Apple-Juice', 'exact_sku_status': 'registered'}, prior=False)


def test_development_is_separate_even_for_registered_photo(evaluator):
    label = dict(truth='God-Morgon-Apple-Juice', gtin='7310865074225', exact_sku_status='registered')
    assert evaluator.exact_role(label, prior=True) == ('God-Morgon-Apple-Juice', 'prior_development')


def test_control_class_identity_is_separate_from_packaged_gtin(evaluator):
    label = dict(truth='Banana', gtin='', exact_sku_status='registered_class')
    assert evaluator.exact_role(label, prior=False, control=True) == ('Banana', 'produce_control')
    with pytest.raises(ValueError, match='exact-SKU'):
        evaluator.exact_role(label, prior=False)


def test_family_match_never_turns_alternate_sku_into_exact_hit(evaluator):
    r = row('UNKNOWN', 'UNKNOWN', 'God-Morgon-Apple-Juice')
    r['family_truth'] = 'God-Morgon-Apple-Juice'
    m = evaluator.paired_metrics([r])
    assert m['after']['family_matches'] == 1
    assert m['after']['correct_names'] == 0
    assert m['after']['unknown_false_accepts'] == 1


def test_dedup_distinguishes_exact_pixels_and_conservative_near_match(evaluator):
    ref = dict(id='old', sha256='a', pixel_sha256='pixels', phash='0000000000000000',
               dhash='0000000000000000', crop_phash='0000000000000000', crop_dhash='0000000000000000')
    assert evaluator.duplicate_reason({**ref, 'sha256': 'b'}, ref) == 'identical_decoded_pixels'
    near = {**ref, 'sha256': 'c', 'pixel_sha256': 'other', 'phash': '000000000000000f', 'dhash': '0000000000000007'}
    assert evaluator.duplicate_reason(near, ref) == 'perceptual_near_duplicate_candidate'
    far = {**near, 'phash': 'ffffffffffffffff', 'dhash': 'ffffffffffffffff',
           'crop_phash': 'ffffffffffffffff', 'crop_dhash': 'ffffffffffffffff'}
    assert evaluator.duplicate_reason(far, ref) is None


def test_blind_loader_rejects_labels_and_mutated_bytes(evaluator, tmp_path):
    picture = tmp_path/'secret-truth.png'
    Image.fromarray(np.full((12, 14, 3), 80, dtype=np.uint8)).save(picture)
    path = tmp_path/'blind.csv'
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, ['id','path','sha256','truth'])
        writer.writeheader(); writer.writerow(dict(id='id-1', path=picture.name, sha256=evaluator.file_hash(picture), truth='Lime'))
    with pytest.raises(ValueError, match='Blind'):
        evaluator.read_blind(path, 'new')
    path.write_text('id,path,sha256\nid-1,secret-truth.png,'+'0'*64+'\n')
    with pytest.raises(ValueError, match='checksum'):
        evaluator.read_blind(path, 'new')


def test_classifier_receives_only_original_rgb_pixels(evaluator, tmp_path):
    picture = tmp_path/'Lime-GTIN-not-a-feature.png'
    rgb = np.arange(12*14*3, dtype=np.uint8).reshape(12, 14, 3)
    Image.fromarray(rgb).save(picture)
    seen = []
    def classifier(pixels):
        assert isinstance(pixels, np.ndarray)
        assert np.array_equal(pixels, rgb)
        seen.append(pixels)
        return {'prediction':'UNKNOWN'}, {'prediction':'Lime'}
    r = evaluator.predict_one(dict(id='opaque-1', path=str(picture), sha256=evaluator.file_hash(picture)), classifier)
    assert len(seen) == 1 and r['id'] == 'opaque-1'
    assert r['before']['prediction'] == 'UNKNOWN' and r['after']['prediction'] == 'Lime'


def test_strata_and_source_groups_do_not_create_independent_sample_claim(evaluator):
    rows = [{**row('Lime','Lime','Lime'), 'id':'a','role':'new_primary','view_type':'front','capture_type':'physical'},
            {**row('Lime','UNKNOWN','UNKNOWN'), 'id':'b','role':'new_primary','view_type':'back','capture_type':'physical'}]
    report = evaluator.summarize(rows)
    assert report['roles']['new_primary']['n'] == 2
    assert report['roles']['new_primary']['source_groups'] == 1
    assert len(report['by_source_group']) == 1
    assert report['by_source_group'][0]['ids'] == ['a','b']
    assert len(report['by_stratum']) == 2
