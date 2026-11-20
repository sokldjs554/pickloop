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
