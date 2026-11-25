import pytest

from pickloop.package_size import printed_size


@pytest.mark.parametrize("token", ["1 L", "1-litre", "1000 ml", "100 cl", "10 dl", "1,00 liter"])
def test_equivalent_explicit_volumes_require_corroboration(token):
    assert printed_size(["God Morgon APPLE " + token, token])[0] == "printed_1l"
    assert printed_size([token])[0] == "unread"


@pytest.mark.parametrize("token", ["1.75 L", "250 ml", "250 mi", "6 x 1 L", "1 L × 6", "1L x 6", "pack of 6", "1/2 L"])
def test_conflicts_veto_positive_reads(token):
    assert printed_size(["1 L", "1 L", token])[0] == "contradictory"


@pytest.mark.parametrize("token", ["per 1 L", "serving size 1 L", "1 L of water", "1. 1 L", "1 L/kg", "L", "1", "100%"])
def test_unusable_or_unrelated_size_never_promotes_a_package(token):
    assert printed_size([token, token])[0] != "printed_1l"


@pytest.mark.parametrize("amount", ["100 ml", "180 ml", "100 mi"])
def test_nutrition_reference_is_ignored_in_photo_and_flavour_paths(amount):
    from pickloop.product_text import printed_flavour
    from pickloop.juice_gate import ORANGE

    panel = f"NAHRWERTANGABEN PER/PRO {amount}: Energie 183 kJ / 43 kcal"
    assert printed_size([panel, panel]) == ("unread", [])
    assert printed_size([panel + " NET 250 ml"])[0] == "contradictory"
    assert printed_flavour(["GOD MORGON ORANGE", "ORANGE", panel])[0] == ORANGE
