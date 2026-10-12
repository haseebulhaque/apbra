from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from apbra_api.config import GovernancePolicy
from apbra_api.generation import _has_ai_geometry


@pytest.mark.parametrize("count", [6, 7, 20, 101, 501])
def test_historical_policy_metadata_is_preserved_without_compiler_capacity(count: int) -> None:
    original = {"requireKnowledge": True, "requireAccessibility": True,
                "requireValidation": True, "maxVisualsPerPage": count,
                "maxPages": 5, "humanReviewAtVisuals": 6}
    assert GovernancePolicy.model_validate(original).model_dump(by_alias=True) == original


def geometry() -> dict:
    return {"schema_version": 2, "pages": [{"displayOption": "ActualSizeTopLeft",
        "width": None, "height": -0.5, "visuals": [{"position": {
            "x": -100.25, "y": 900.5, "width": 0, "height": -2.5,
            "z": 1.25, "tabOrder": None, "angle": 2.75}} for _ in range(21)]}]}


def test_schema_valid_geometry_is_not_a_layout_quality_gate() -> None:
    value = geometry()
    before = copy.deepcopy(value)
    assert _has_ai_geometry(value)
    assert value == before
    del value["pages"][0]["width"]
    del value["pages"][0]["height"]
    del value["pages"][0]["visuals"][0]["position"]["z"]
    assert _has_ai_geometry(value)


@pytest.mark.parametrize("bad", [True, "1", None, float("nan"), float("inf"), 10**1000])
def test_geometry_required_coordinates_reject_only_nonfinite_or_nonnumeric(bad: object) -> None:
    value = geometry()
    value["pages"][0]["visuals"][0]["position"]["x"] = bad
    assert not _has_ai_geometry(value)


@pytest.mark.parametrize("field", ["z", "tabOrder", "angle"])
def test_optional_geometry_rejects_boolean_without_supplying_a_default(field: str) -> None:
    value = geometry()
    value["pages"][0]["visuals"][0]["position"][field] = False
    assert not _has_ai_geometry(value)


@pytest.mark.parametrize("version", [1, 3, None, "2"])
def test_legacy_and_unknown_versions_are_not_new_geometry(version: object) -> None:
    value = geometry()
    value["schema_version"] = version
    assert not _has_ai_geometry(value)


def test_historical_policy_metadata_still_rejects_invalid_types() -> None:
    with pytest.raises(ValidationError):
        GovernancePolicy.model_validate({"requireKnowledge": True, "requireAccessibility": True,
            "requireValidation": True, "maxVisualsPerPage": "not-a-number",
            "maxPages": 5, "humanReviewAtVisuals": 6})
