"""Regression tests for split integrity and the photo evaluation CLI."""
import csv
import json
import subprocess
import sys

import pytest
from PIL import Image

MODULE = 'pickloop.photo_evaluation'


def test_metrics_distinguish_wrong_sku_reject_and_unknown_false_accept():
    from pickloop.photo_evaluation import metrics

    rows = [('A', 'A'), ('A', 'UNKNOWN'), ('A', 'B'), ('UNKNOWN', 'A'), ('UNKNOWN', 'UNKNOWN')]
    result = metrics(rows)
    assert (result['known_total'], result['known_correct'], result['known_rejected'],
            result['known_wrong_label']) == (3, 1, 1, 1)
    assert (result['unknown_total'], result['unknown_rejected'], result['unknown_false_accepts']) == (2, 1, 1)
    assert result['known_accuracy_after_rejection'] == pytest.approx(1/3)
    assert result['unknown_false_accept_rate'] == .5
    assert metrics([('UNKNOWN', 'UNKNOWN')])['known_accuracy_after_rejection'] is None


def test_manifest_cli_scores_only_requested_pixels_and_preserves_conditions(tmp_path):
    image = Image.new('RGB', (140, 140), 'green')
    from test_vision_model import fixture_crop
    mark = Image.fromarray(fixture_crop('a'))
    image.paste(mark, (25, 35))
    image.save(tmp_path / 'capture.png')
    manifest = tmp_path / 'labels.csv'
    manifest.write_text('path,truth,x0,y0,x1,y1,lighting\ncapture.png,SKU-RED-A,25,35,121,131,diffuse\n')
    target = tmp_path / 'report'
    run = subprocess.run([sys.executable, '-m', MODULE, 'manifest', str(manifest), '--out', str(target)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    with (target / 'predictions.csv').open() as stream:
        photo, = csv.DictReader(stream)
    assert (photo['truth'], photo['prediction'], photo['lighting']) == ('SKU-RED-A', 'SKU-RED-A', 'diffuse')
    assert [int(photo[c]) for c in ('x0','y0','x1','y1')] == [25,35,121,131]
    from pickloop.vision_model import AppearanceModel
    import numpy as np
    direct, = AppearanceModel().predict([np.asarray(mark)])
    assert float(photo['distance']) == pytest.approx(direct['distance'])
    summary = json.loads((target / 'summary.json').read_text())
    assert summary['metrics']['known_correct'] == 1
    assert summary['metrics']['unknown_false_accept_rate'] is None


def test_manifest_rejects_miscoded_label_invalid_crop_and_duplicate_image(tmp_path):
    from pickloop.photo_evaluation import evaluate_manifest

    photo = tmp_path / 'a.png'
    Image.new('RGB', (12, 14), 'red').save(photo)
    (tmp_path / 'b.png').write_bytes(photo.read_bytes())
    manifest = tmp_path / 'labels.csv'
    for rows, error in [
        ('a.png,SKU-RED-C,,,,', 'truth'),
        ('a.png,UNKNOWN,0,0,13,14', 'crop'),
        ('a.png,UNKNOWN,2,,,', 'crop'),
        ('a.png,UNKNOWN,,,,\nb.png,SKU-RED-B,,,,', 'duplicate'),
    ]:
        manifest.write_text('path,truth,x0,y0,x1,y1\n' + rows + '\n')
        with pytest.raises(ValueError, match=error):
            evaluate_manifest(manifest, tmp_path / 'report')


def test_grocery_selection_uses_only_registered_products_from_train_and_all_test_packages():
    from pickloop.grocery_evaluation import select_split
    sample = ('train/Packages/Juice/Bravo-Apple-Juice/a.jpg,28,19\n'
              'train/Packages/Juice/Bravo-Orange-Juice/b.jpg,29,19\n'
              'train/Packages/Milk/Test-Milk/c.jpg,40,20\n'
              'train/Fruit/Apple/d.jpg,0,0\n')
    train = select_split(sample, 'train')
    test = select_split(sample.replace('train/', 'test/'), 'test')
    assert [entry['product'] for entry in train] == ['Bravo-Apple-Juice', 'Bravo-Orange-Juice']
    assert [entry['product'] for entry in test] == ['Bravo-Apple-Juice', 'Bravo-Orange-Juice', 'Test-Milk']
    with pytest.raises(ValueError, match='split'):
        select_split(sample, 'test')


def test_calibration_caps_false_accepts_without_splitting_equal_distances():
    from pickloop import grocery_evaluation
    cutoff = grocery_evaluation.conservative_cutoff
    distances = [0.01, 0.01] + [0.5] * 18
    # A 5% budget allows one of 20. Both nearest unknowns tie, so both must be rejected.
    assert 0 < cutoff(distances, 1.0) < 0.01
    assert cutoff([0.6] * 20, 0.3) == 0.3
    with pytest.raises(ValueError, match='unknown'):
        cutoff([], 1.0)


def test_fresh_unknown_selection_excludes_all_cartons():
    from pickloop.grocery_evaluation import select_split
    sample = ('test/Packages/Juice/Bravo-Apple-Juice/a.jpg,28,19\n'
              'test/Fruit/Apple/Golden-Delicious/b.jpg,0,0\n'
              'test/Vegetables/Asparagus/c.jpg,59,28\n')
    assert [p['class_id'] for p in select_split(sample, 'test', group='produce')] == [0, 59]
