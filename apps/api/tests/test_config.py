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


@pytest.mark.parametrize("where", ["page.width", "page.height", "x", "y", "width", "height",
                                  "z", "tabOrder", "angle"])
@pytest.mark.parametrize("value,accepted", [(9007199254740993, False), (2**60, True),
                                            (-2**60, True), (-0.25, True), (0, True)])
def test_geometry_uses_exact_representation_not_safe_integer_or_magnitude_cap(
    where: str, value: int | float, accepted: bool,
) -> None:
    from apbra_api.generation import (
        GeometryRepresentationUnsupported,
        _assert_geometry_representable,
    )
    design = geometry()
    target = design["pages"][0] if where.startswith("page.") else (
        design["pages"][0]["visuals"][0]["position"])
    target[where.split(".")[-1]] = value
    before = copy.deepcopy(design)
    assert _has_ai_geometry(design) is accepted
    if accepted:
        _assert_geometry_representable(design)
    else:
        with pytest.raises(GeometryRepresentationUnsupported):
            _assert_geometry_representable(design)
    assert design == before


def test_direct_generation_bridge_rejects_precision_loss_before_process_creation(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil
    from pathlib import Path

    import apbra_api.generation as generation_module
    from apbra_api.generation import GenerationBridge, GeometryRepresentationUnsupported

    executable = tmp_path / "bridge.mjs"
    executable.write_text("throw new Error('bridge must not run');")
    bridge = GenerationBridge(executable, node_executable=Path(shutil.which("node")),
                              timeout_seconds=1)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("No process may observe rounded geometry")

    monkeypatch.setattr(generation_module.subprocess, "Popen", forbidden)
    design = geometry()
    design["pages"][0]["visuals"][0]["position"]["x"] = 9007199254740993
    with pytest.raises(GeometryRepresentationUnsupported):
        bridge._call({"operation": "generate", "reportDesign": design}, validate_candidate=True)
    assert calls == []


@pytest.mark.parametrize("version", [1, 2])
def test_geometry_wire_spelling_preserves_exact_large_float_without_mutating_saved_input(
    version: int,
) -> None:
    import json

    from apbra_api.generation import _geometry_wire_payload

    design = geometry()
    design["schema_version"] = version
    design["pages"][0]["width"] = float(2**60)
    design["pages"][0]["visuals"][0]["position"]["z"] = float(2**60)
    payload = {"reportDesign": design, "binding": {"synthetic": "unchanged"}}
    before = copy.deepcopy(payload)
    wire = _geometry_wire_payload(payload)
    assert payload == before
    if version == 2:
        assert type(wire["reportDesign"]["pages"][0]["width"]) is int
        assert str(2**60) in json.dumps(wire)
        assert wire["reportDesign"]["pages"][0]["width"] == 2**60
    else:
        assert json.dumps(wire) == json.dumps(payload)
    assert wire["binding"] == payload["binding"]
