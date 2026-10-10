from app import shared_config as sc
from app.models import Category


def test_matrix_and_seed_load_from_contracts():
    assert sc.MATRIX_PATH.parent.name == "contracts" and sc.ROUTING_SEED_PATH.parent.name == "contracts"
    assert sc.departments() == ["corporation", "water_board", "electricity", "highways"]


def test_candidates_are_ordered_and_other_is_empty():
    assert sc.candidates_for("waterlogging") == ["corporation", "water_board", "highways"]
    assert sc.candidates_for("streetlight") == ["corporation", "electricity"]
    assert sc.candidates_for("other") == [] and sc.candidates_for("nonsense") == []


def test_first_contact_is_a_guess_not_the_first_candidate():
    assert sc.first_contact("waterlogging") == ("water_board", 0.5)  # differs from the matrix order: that is the point
    assert sc.first_contact("pothole")[0] == "corporation"
    assert sc.first_contact("other") == (None, 0.0) and sc.first_contact("pothole", "W-99") == (None, 0.0)


def test_every_category_in_the_matrix_is_a_known_category():
    assert set(sc.categories()) == {c.value for c in Category}
