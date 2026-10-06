from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx
import pytest

from apbra_api.model_provider import (
    COMPILER_MAX_VISUALS_PER_PAGE,
    COMPILER_SUPPORTED_TREND_GRAINS,
    OpenAICompatibleProvider,
    ProviderCallError,
    ProviderConfigurationError,
    ProviderProfile,
    ProviderRequest,
    report_design_schema,
    requirement_analysis_schema,
)


def requirement_schema() -> dict[str, Any]:
    return requirement_analysis_schema(COMPILER_SUPPORTED_TREND_GRAINS)


def design_schema(max_visuals: int = COMPILER_MAX_VISUALS_PER_PAGE) -> dict[str, Any]:
    return report_design_schema(
        max_visuals_per_page=max_visuals,
        supported_trend_grains=COMPILER_SUPPORTED_TREND_GRAINS,
    )


def profile(**overrides: object) -> ProviderProfile:
    values: dict[str, object] = {
        "profile_id": "qualified-test-profile",
        "protocol": "OPENAI_CHAT_COMPATIBLE",
        "endpoint": "https://provider.invalid/v1/chat/completions",
        "model_or_deployment": "qualified-test-model",
        "api_version": "test-version",
        "region": "test-region",
        "prompt_version": "prompt-v1",
        "configuration_id": "config-v1",
        "capabilities": {"structured_output": True, "vision": False},
        "max_calls_per_operation": 2,
        "max_input_characters": 10_000,
        "max_output_tokens": 1_000,
        "time_budget_seconds": 10,
        "request_timeout_seconds": 2,
        "retry_limit": 1,
    }
    values.update(overrides)
    return ProviderProfile.model_validate(values)


def request(*, vision: bool = False) -> ProviderRequest:
    return ProviderRequest(
        task="REPORT_DESIGN",
        system_prompt="Return one typed candidate.",
        context={"safe": "context"},
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["pages"],
            "properties": {
                "pages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id"],
                        "properties": {"id": {"type": "string"}},
                    },
                }
            },
        },
        requires_vision=vision,
    )


def test_profile_requires_explicit_credential_free_https_configuration() -> None:
    with pytest.raises(ProviderConfigurationError, match="MODEL_PROFILE_MISSING"):
        ProviderProfile.parse(None)
    with pytest.raises(ProviderConfigurationError, match="MODEL_PROFILE_INVALID"):
        ProviderProfile.parse('{"endpoint":"http://unsafe.invalid"}')
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        profile(endpoint="https://secret@example.invalid/v1/chat/completions")
    with pytest.raises(ProviderConfigurationError, match="MODEL_CREDENTIAL_MISSING"):
        OpenAICompatibleProvider(profile(), "")


def test_exact_endpoint_structured_schema_and_safe_provenance_are_used() -> None:
    observed: list[httpx.Request] = []

    def respond(incoming: httpx.Request) -> httpx.Response:
        observed.append(incoming)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"pages": []})}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            },
        )

    provider = OpenAICompatibleProvider(
        profile(), "server-secret", transport=httpx.MockTransport(respond)
    )
    result = provider.structured(request())
    assert result.value == {"pages": []}
    assert result.call_count == 1
    assert result.profile_id == "qualified-test-profile"
    assert result.usage["total_tokens"] == 18
    assert result.candidate_digest == hashlib.sha256(b'{"pages":[]}').hexdigest()
    assert len(observed) == 1
    assert str(observed[0].url) == "https://provider.invalid/v1/chat/completions"
    assert observed[0].headers["authorization"] == "Bearer server-secret"
    body = json.loads(observed[0].content)
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True


def test_deterministic_rejection_gets_one_configured_model_correction() -> None:
    observed: list[httpx.Request] = []

    def respond(incoming: httpx.Request) -> httpx.Response:
        observed.append(incoming)
        value = {"pages": []} if len(observed) == 1 else {"pages": [{"id": "corrected"}]}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(value)}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            },
        )

    def validate(value: dict[str, object]) -> None:
        if not value["pages"]:
            raise RuntimeError("REPORT_DESIGN_SEMANTICS_FAILED")

    provider = OpenAICompatibleProvider(
        profile(), "server-secret", transport=httpx.MockTransport(respond)
    )
    base = request()
    result = provider.structured(
        ProviderRequest(
            task=base.task,
            system_prompt=base.system_prompt,
            context=base.context,
            output_schema=base.output_schema,
            validator=validate,
            retry_instruction=lambda exc: f"Correct this deterministic failure: {exc}",
        )
    )

    assert result.value == {"pages": [{"id": "corrected"}]}
    assert result.call_count == 2
    assert result.usage["total_tokens"] == 36
    assert result.candidate_digest == hashlib.sha256(b'{"pages":[{"id":"corrected"}]}').hexdigest()
    assert len(observed) == 2
    retry_body = json.loads(observed[1].content)
    assert retry_body["messages"][-2] == {
        "role": "assistant",
        "content": json.dumps({"pages": []}),
    }
    assert retry_body["messages"][-1]["role"] == "user"
    assert "REPORT_DESIGN_SEMANTICS_FAILED" in retry_body["messages"][-1]["content"]
    assert "server-secret" not in retry_body["messages"][-1]["content"]


def test_terminal_candidate_rejection_carries_only_safe_observed_provenance() -> None:
    observed: list[httpx.Request] = []

    def respond(incoming: httpx.Request) -> httpx.Response:
        observed.append(incoming)
        value = {"pages": [{"id": f"candidate-{len(observed)}"}]}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(value)}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            },
        )

    provider = OpenAICompatibleProvider(
        profile(), "server-secret", transport=httpx.MockTransport(respond)
    )
    base = request()
    with pytest.raises(ProviderCallError) as captured:
        provider.structured(
            ProviderRequest(
                task=base.task,
                system_prompt=base.system_prompt,
                context=base.context,
                output_schema=base.output_schema,
                validator=lambda _value: (_ for _ in ()).throw(
                    RuntimeError("REPORT_DESIGN_SEMANTICS_FAILED secret=must-not-persist")
                ),
                retry_instruction=lambda _exc: "Correct the structural failure.",
            )
        )

    failure = captured.value
    assert failure.code == "MODEL_CANDIDATE_REJECTED"
    assert str(failure) == "MODEL_CANDIDATE_REJECTED"
    assert "must-not-persist" not in str(failure)
    assert failure.observation is not None
    assert failure.observation.call_count == 2
    assert failure.observation.usage == {
        "prompt_tokens": 22,
        "completion_tokens": 14,
        "total_tokens": 36,
    }
    assert failure.observation.profile_id == "qualified-test-profile"
    assert failure.observation.model_or_deployment == "qualified-test-model"
    assert failure.observation.prompt_version == "prompt-v1"
    assert failure.observation.configuration_id == "config-v1"
    assert failure.observation.capability_profile == {
        "structured_output": True,
        "vision": False,
    }
    assert (
        failure.observation.candidate_digest
        == hashlib.sha256(b'{"pages":[{"id":"candidate-2"}]}').hexdigest()
    )
    assert len(observed) == 2


def test_boolean_usage_is_not_recorded_as_observed_token_counts() -> None:
    def respond(_incoming: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"pages":[{"id":"safe"}]}'}}],
                "usage": {
                    "prompt_tokens": True,
                    "completion_tokens": False,
                    "total_tokens": 9,
                },
            },
        )

    provider = OpenAICompatibleProvider(
        profile(), "server-secret", transport=httpx.MockTransport(respond)
    )
    result = provider.structured(request())
    assert result.usage == {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": 9,
    }


def test_transient_failure_retries_only_within_the_exact_call_budget() -> None:
    calls = 0

    def respond(_incoming: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    provider = OpenAICompatibleProvider(
        profile(), "server-secret", transport=httpx.MockTransport(respond)
    )
    with pytest.raises(ProviderCallError, match="MODEL_PROVIDER_TRANSIENT_FAILURE"):
        provider.structured(request())
    assert calls == 2


@pytest.mark.parametrize(
    ("handler", "code"),
    [
        (
            lambda _request: httpx.Response(
                200, json={"choices": [{"message": {"content": "not-json"}}]}
            ),
            "MODEL_OUTPUT_INVALID",
        ),
        (
            lambda _request: httpx.Response(403, text="credential=server-secret"),
            "MODEL_PROVIDER_REJECTED",
        ),
        (
            lambda incoming: (_ for _ in ()).throw(httpx.ReadTimeout("late", request=incoming)),
            "MODEL_PROVIDER_TIMEOUT",
        ),
    ],
)
def test_failures_are_bounded_and_do_not_disclose_provider_content(
    handler: object, code: str
) -> None:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    provider = OpenAICompatibleProvider(profile(), "server-secret", transport=transport)
    with pytest.raises(ProviderCallError) as captured:
        provider.structured(request())
    assert captured.value.code == code
    assert "server-secret" not in str(captured.value)
    assert captured.value.observation is not None
    assert captured.value.observation.call_count >= 1
    assert captured.value.observation.profile_id == "qualified-test-profile"
    assert captured.value.observation.model_or_deployment == "qualified-test-model"
    assert "server-secret" not in json.dumps(captured.value.observation.__dict__)


def test_vision_and_input_budgets_fail_closed_without_a_provider_call() -> None:
    calls = 0

    def respond(_incoming: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    provider = OpenAICompatibleProvider(
        profile(), "server-secret", transport=httpx.MockTransport(respond)
    )
    with pytest.raises(ProviderConfigurationError, match="VISION_UNSUPPORTED"):
        provider.structured(request(vision=True))
    constrained = OpenAICompatibleProvider(
        profile(max_input_characters=1_000),
        "server-secret",
        transport=httpx.MockTransport(respond),
    )
    oversized = ProviderRequest(
        task="REQUIREMENT_ANALYSIS",
        system_prompt="x" * 1_001,
        context={},
        output_schema={"type": "object"},
    )
    with pytest.raises(ProviderCallError, match="MODEL_INPUT_BUDGET_EXCEEDED"):
        constrained.structured(oversized)
    assert calls == 0


@pytest.mark.parametrize("schema", [requirement_schema(), design_schema()])
def test_real_provider_schemas_are_closed_and_fully_required(schema: dict[str, object]) -> None:
    def inspect(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value.get("additionalProperties") is False
                properties = value.get("properties")
                assert isinstance(properties, dict)
                assert set(value.get("required", [])) == set(properties)
            for nested in value.values():
                inspect(nested)
        elif isinstance(value, list):
            for nested in value:
                inspect(nested)

    inspect(schema)


@pytest.mark.parametrize("schema", [requirement_schema(), design_schema()])
def test_exact_provider_wire_schemas_fit_foundry_strict_profile(schema: dict[str, Any]) -> None:
    object_properties = 0
    object_depth = 0
    unsupported = {
        "minimum", "maximum", "multipleOf", "minItems", "maxItems", "uniqueItems",
        "minLength", "maxLength", "pattern", "format", "minProperties", "maxProperties",
    }

    def inspect(node: dict[str, Any], depth: int) -> None:
        nonlocal object_properties, object_depth
        assert not unsupported.intersection(node)
        if node.get("type") == "object":
            properties = node["properties"]
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(properties)
            object_properties += len(properties)
            object_depth = max(object_depth, depth)
            for child in properties.values():
                inspect(child, depth + 1)
        elif node.get("type") == "array":
            inspect(node["items"], depth)

    inspect(schema, 1)
    assert object_properties <= 100
    assert object_depth <= 5


@pytest.mark.parametrize(
    "failure_kind",
    [
        "unsupported_minimum", "unsupported_max_items", "six_object_levels",
        "too_many_properties", "missing_required", "open_object", "malformed_required",
    ],
)
def test_invalid_wire_schema_is_rejected_before_any_provider_request(
    failure_kind: str,
) -> None:
    observed: list[httpx.Request] = []

    def respond(incoming: httpx.Request) -> httpx.Response:
        observed.append(incoming)
        return httpx.Response(400, json={"error": "schema rejected"})

    provider = OpenAICompatibleProvider(
        profile(), "server-secret", transport=httpx.MockTransport(respond)
    )
    bad = requirement_schema()
    if failure_kind == "unsupported_minimum":
        bad["properties"]["interpretation"]["properties"]["coverageRequirements"]["items"][
            "properties"
        ]["minimumRepresentations"]["minimum"] = 0
    elif failure_kind == "unsupported_max_items":
        bad = design_schema()
        bad["properties"]["pages"]["items"]["properties"]["visuals"]["maxItems"] = 6
    elif failure_kind == "six_object_levels":
        nested: dict[str, Any] = {"type": "string"}
        for _ in range(5):
            nested = {
                "type": "object", "properties": {"child": nested},
                "required": ["child"], "additionalProperties": False,
            }
        bad = {
            "type": "object", "properties": {"child": nested},
            "required": ["child"], "additionalProperties": False,
        }
    elif failure_kind == "too_many_properties":
        properties = {f"field{index}": {"type": "string"} for index in range(101)}
        bad = {
            "type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False,
        }
    elif failure_kind == "missing_required":
        bad["required"].remove("state")
    elif failure_kind == "open_object":
        bad["additionalProperties"] = True
    else:
        bad["required"] = [[]]
    with pytest.raises(ProviderCallError, match="MODEL_SCHEMA_UNSUPPORTED") as captured:
        provider.structured(
            ProviderRequest(
                task="REQUIREMENT_ANALYSIS",
                system_prompt="Return a typed proposal.",
                context={"synthetic": True},
                output_schema=bad,
            )
        )
    assert captured.value.observation is not None
    assert captured.value.observation.call_count == 0
    assert observed == []


def test_report_design_schema_exposes_existing_compiler_visual_bounds() -> None:
    schema = design_schema()
    properties = schema["properties"]
    visuals = properties["pages"]["items"]["properties"]["visuals"]
    assert "maxItems" not in visuals
    assert f"at most {COMPILER_MAX_VISUALS_PER_PAGE} visuals" in visuals["description"]
    assert "four non-card slots and two additional card-only slots" in visuals["description"]
    filters = properties["filters"]
    assert "must not also be represented by a slicer" in filters["description"]


def test_provider_schemas_derive_capacity_and_grains_from_validated_capability() -> None:
    requirement = requirement_analysis_schema(["DAY", "MONTH"])
    requirement_grains = requirement["properties"]["interpretation"]["properties"][
        "coverageRequirements"
    ]["items"]["properties"]["timeGrain"]["enum"]
    design = report_design_schema(
        max_visuals_per_page=4, supported_trend_grains=["DAY", "MONTH"]
    )
    visual = design["properties"]["pages"]["items"]["properties"]["visuals"]
    design_grains = visual["items"]["properties"]["timeGrain"]["enum"]
    assert requirement_grains == ["NONE", "DAY", "MONTH"]
    assert design_grains == ["NONE", "DAY", "MONTH"]
    assert "maxItems" not in visual
    assert "at most 4 visuals" in visual["description"]
    assert "WEEK" not in requirement_grains
    assert "WEEK" not in design_grains
    with pytest.raises(ValueError, match="exceed the active compiler"):
        report_design_schema(
            max_visuals_per_page=COMPILER_MAX_VISUALS_PER_PAGE + 1,
            supported_trend_grains=COMPILER_SUPPORTED_TREND_GRAINS,
        )
    with pytest.raises(ValueError, match="exceed the active compiler"):
        requirement_analysis_schema(["WEEK"])
