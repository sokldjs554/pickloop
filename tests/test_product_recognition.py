import numpy as np
import pytest


def test_logit_margin_rejects_background_ties_and_ambiguous_juice():
    from pickloop.product_recognition import decide, product_margins

    logits = np.array([[3, 1, 0], [1, 3, 4], [2, 2, -1], [1, 2, 1]])
    winner, margin = product_margins(logits)
    assert list(margin) == [2, -1, 0, 1]
    assert decide(winner, margin, 1) == ['Bravo-Apple-Juice', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN']


def test_negative_validation_budget_accounts_for_ties_and_background_gate():
    from pickloop.product_recognition import validation_boundary

    assert validation_boundary([1, 1] + [0] * 18) == 1
    assert validation_boundary([-2, -1, -3]) == 0
    with pytest.raises(ValueError):
        validation_boundary([])


def test_balanced_linear_head_separates_positive_classes_and_unknown():
    from pickloop.product_recognition import fit_head, product_margins, decide

    vectors = np.array([[1, 0, 0], [.99, .05, 0], [0, 1, 0], [.02, .99, 0]] + [[0, 0, 1]] * 12)
    weights, intercept = fit_head(vectors, [0, 0, 1, 1] + [2] * 12)
    logits = np.array([[.9, .1, 0], [.1, .9, 0], [0, .2, .8]]) @ weights + intercept
    assert decide(*product_margins(logits), 0) == ['Bravo-Apple-Juice', 'Bravo-Orange-Juice', 'UNKNOWN']


def test_development_excludes_entire_negative_product_families():
    from pickloop.product_recognition import development_product

    assert development_product(28) and development_product(29)
    assert development_product(31)
    assert not development_product(30) and not development_product(57)


def test_published_carton_comparison_uses_the_same_images_and_excludes_reserved_training_ids():
    import csv
    import json
    from hashlib import sha256
    from pathlib import Path

    from pickloop.photo_evaluation import metrics

    root = Path(__file__).resolve().parents[1] / 'docs/experiments'
    release = root / 'grocery-transfer'

    def read(path):
        with path.open(newline='') as stream:
            return list(csv.DictReader(stream))

    def counts(rows):
        return metrics((row['truth'], row['prediction']) for row in rows)

    report = json.loads((release / 'summary.json').read_text())
    assert sha256((release / 'model.json').read_bytes()).hexdigest() == report['head_sha256']
    dev = read(release / 'development-inputs.csv')
    assert all(int(row['class_id']) not in range(30, 59, 3) for row in dev)
    scored = read(release / 'predictions.csv')
    cases = [row for row in scored if row['split'] == 'test' and '/Packages/' in row['path']]
    previous = [row for row in read(root / 'real-photos-calibrated/predictions.csv')
                if row['partition'] == 'revisited_cartons']
    assert {row['sha256']: row['truth'] for row in cases} == {row['sha256']: row['truth'] for row in previous}
    assert len(cases) == 781 and counts(cases) == report['revisited_cartons']
    assert counts(row for row in cases if int(row['class_id']) in range(30, 59, 3)) == report['reserved_cartons']
    assert counts(row for row in scored if row['split'] == 'catalogue') == report['new_catalogue']
    assert len({row['sha256'] for row in dev + scored}) == len(dev) + len(scored) == report['distinct_image_hashes']
