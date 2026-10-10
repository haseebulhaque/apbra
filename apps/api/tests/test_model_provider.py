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
    assert "Exact Table.Column" in filters["description"]
    assert "chosen by the model" in filters["description"]
    assert "editable draft" in filters["description"]


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


def foundry_profile(**overrides: object) -> ProviderProfile:
    return profile(
        protocol="FOUNDRY_AGENT_RESPONSES",
        api_version="v1",
        endpoint="https://provider.invalid/api/projects/project/agents/agent/endpoint/protocols/openai/responses",
        **overrides,
    )


def foundry_adapter(handler: Any, **overrides: Any) -> Any:
    import time
    from uuid import UUID

    from apbra_api.model_provider import FoundryAccess, FoundryAgentResponsesProvider, FoundryBearer

    company = UUID("00000000-0000-0000-0000-000000000001")
    qualified = foundry_profile(**overrides.pop("profile_overrides", {}))
    access = FoundryAccess(
        company_id=company,
        profile_id=qualified.profile_id,
        configuration_id=qualified.configuration_id,
        credential=overrides.pop(
            "credential", lambda: FoundryBearer("synthetic-token", time.time() + 300)
        ),
        knowledge_binding="synthetic-shared-standards",
        knowledge_scope="SHARED_STANDARDS",
        agent_version="6",
        **overrides,
    )
    return FoundryAgentResponsesProvider(
        qualified, access, company_id=company, transport=httpx.MockTransport(handler)
    )


def token_credential_host(**overrides: Any) -> Any:
    import time
    from types import SimpleNamespace
    from uuid import UUID

    from apbra_api.model_provider import FoundryTokenCredentialProvider

    class SyntheticCredential:
        def __init__(self) -> None:
            self.scopes: list[tuple[str, ...]] = []
            self.result: Any = SimpleNamespace(
                **{"token": "synthetic-bearer", "expires_on": time.time() + 300},
            )
            self.error: Exception | None = None

        def get_token(self, *scopes: str) -> Any:
            self.scopes.append(scopes)
            if self.error is not None:
                raise self.error
            return self.result

    credential = SyntheticCredential()
    company = UUID("00000000-0000-0000-0000-000000000001")
    qualified = foundry_profile()
    activation = {"enabled": False}
    provider = FoundryTokenCredentialProvider(
        company_id=company, profile=qualified, token_credential=credential,
        enabled=overrides.pop("enabled", lambda: activation["enabled"]),
        knowledge_binding=overrides.pop("knowledge_binding", "synthetic-shared-standards"),
        knowledge_scope=overrides.pop("knowledge_scope", "SHARED_STANDARDS"),
        agent_version=overrides.pop("agent_version", "6"),
        qualification=overrides.pop("qualification", "OFFLINE_FIXTURE"),
        **overrides,
    )
    return provider, credential, company, qualified, activation


def test_token_credential_host_is_disabled_and_metadata_reads_do_not_acquire_tokens() -> None:
    host, credential, company, qualified, activation = token_credential_host()
    assert not host.ready(company, qualified)
    with pytest.raises(ProviderConfigurationError, match="FOUNDRY_RUNTIME_IDENTITY_UNAVAILABLE"):
        host.resolve(company, qualified)
    assert credential.scopes == []
    activation["enabled"] = True
    assert host.ready(company, qualified)
    access = host.resolve(company, qualified)
    assert credential.scopes == []
    bearer = access.credential()
    assert bearer.audience == "https://ai.azure.com"
    assert credential.scopes == [("https://ai.azure.com/.default",)]
    assert "synthetic-bearer" not in repr(bearer)
    assert "synthetic-bearer" not in repr(host)
    assert "synthetic-bearer" not in repr(access)


@pytest.mark.parametrize("field,value", [
    ("profile_id", "foreign-profile"), ("configuration_id", "foreign-config"),
    ("endpoint", "https://foreign.invalid/api/projects/project/agents/agent/endpoint/protocols/openai/responses"),
    ("model_or_deployment", "foreign-model"), ("max_output_tokens", 500),
    ("capabilities", {"structured_output": True, "vision": True}),
])
def test_token_credential_host_rejects_any_changed_profile_before_acquisition(
    field: str, value: Any,
) -> None:
    host, credential, company, qualified, activation = token_credential_host()
    activation["enabled"] = True
    changed = qualified.model_copy(update={field: value})
    if field == "capabilities":
        changed = type(qualified).model_validate({**qualified.model_dump(), field: value})
    assert not host.ready(company, changed)
    with pytest.raises(ProviderConfigurationError, match="FOUNDRY_RUNTIME_IDENTITY_UNAVAILABLE"):
        host.resolve(company, changed)
    assert credential.scopes == []


def test_token_credential_host_rejects_foreign_company_and_preserves_profile_copy() -> None:
    from uuid import UUID

    host, credential, company, qualified, activation = token_credential_host()
    activation["enabled"] = True
    foreign = UUID("00000000-0000-0000-0000-000000000002")
    assert not host.ready(foreign, qualified)
    with pytest.raises(ProviderConfigurationError, match="FOUNDRY_RUNTIME_IDENTITY_UNAVAILABLE"):
        host.resolve(foreign, qualified)
    qualified.capabilities.vision = True
    assert not host.ready(company, qualified)
    assert credential.scopes == []


@pytest.mark.parametrize("enabled", [lambda: 1, lambda: "yes", lambda: None])
def test_token_credential_host_requires_explicit_boolean_enable(enabled: Any) -> None:
    host, credential, company, qualified, _ = token_credential_host(enabled=enabled)
    assert not host.ready(company, qualified)
    assert credential.scopes == []


def test_token_credential_host_enable_failure_and_revocation_fail_closed() -> None:
    def unavailable() -> bool:
        raise RuntimeError("synthetic-private-host-detail")

    host, credential, company, qualified, _ = token_credential_host(enabled=unavailable)
    assert not host.ready(company, qualified)
    assert credential.scopes == []
    host, credential, company, qualified, activation = token_credential_host()
    activation["enabled"] = True
    access = host.resolve(company, qualified)
    activation["enabled"] = False
    with pytest.raises(ProviderConfigurationError, match="FOUNDRY_RUNTIME_IDENTITY_UNAVAILABLE"):
        access.credential()
    assert credential.scopes == []


@pytest.mark.parametrize("token,expiry", [
    ("", 9999999999), (None, 9999999999), (b"synthetic", 9999999999),
    ("synthetic", True), ("synthetic", "9999999999"),
    ("synthetic", float("nan")), ("synthetic", float("inf")), ("synthetic", 0),
])
def test_token_credential_host_rejects_invalid_capability(token: Any, expiry: Any) -> None:
    from types import SimpleNamespace

    host, credential, company, qualified, activation = token_credential_host()
    activation["enabled"] = True
    credential.result = SimpleNamespace(token=token, expires_on=expiry)
    with pytest.raises(ProviderConfigurationError, match="FOUNDRY_CREDENTIAL_UNAVAILABLE"):
        host.resolve(company, qualified).credential()
    assert credential.scopes == [("https://ai.azure.com/.default",)]


def test_token_credential_host_sanitizes_sdk_failure_before_provider_http() -> None:
    from apbra_api.model_provider import FoundryAgentResponsesProvider

    host, credential, company, qualified, activation = token_credential_host()
    activation["enabled"] = True
    credential.error = RuntimeError("synthetic-private-authentication-detail")
    requests: list[Any] = []
    adapter = FoundryAgentResponsesProvider(
        qualified, host.resolve(company, qualified), company_id=company,
        transport=httpx.MockTransport(lambda wire: requests.append(wire) or httpx.Response(200)),
    )
    with pytest.raises(ProviderCallError, match="MODEL_CREDENTIAL_UNAVAILABLE") as caught:
        adapter.structured(request())
    assert requests == []
    assert caught.value.observation.call_count == 0
    assert "synthetic-private" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_token_credential_host_refreshes_scope_for_each_mocked_provider_attempt() -> None:
    from apbra_api.model_provider import FoundryAgentResponsesProvider

    host, credential, company, qualified, activation = token_credential_host()
    activation["enabled"] = True
    attempts: list[Any] = []

    def handler(wire: Any) -> httpx.Response:
        attempts.append(wire)
        if len(attempts) == 1:
            raise httpx.ReadTimeout("synthetic timeout")
        assert wire.headers["authorization"] == "Bearer synthetic-bearer"
        return httpx.Response(200, json=responses_payload())

    result = FoundryAgentResponsesProvider(
        qualified, host.resolve(company, qualified), company_id=company,
        transport=httpx.MockTransport(handler),
    ).structured(request())
    assert result.call_count == 2
    assert credential.scopes == [("https://ai.azure.com/.default",)] * 2
    assert result.grounding["qualification"] == "OFFLINE_FIXTURE"


def test_token_credential_host_revocation_during_acquisition_blocks_provider_http() -> None:
    from apbra_api.model_provider import FoundryAgentResponsesProvider

    host, credential, company, qualified, activation = token_credential_host()
    activation["enabled"] = True
    acquire = credential.get_token

    def revoke_during_acquisition(*scopes: str) -> Any:
        activation["enabled"] = False
        return acquire(*scopes)

    credential.get_token = revoke_during_acquisition
    requests: list[Any] = []
    adapter = FoundryAgentResponsesProvider(
        qualified, host.resolve(company, qualified), company_id=company,
        transport=httpx.MockTransport(lambda wire: requests.append(wire) or httpx.Response(200)),
    )
    with pytest.raises(ProviderCallError, match="MODEL_CREDENTIAL_UNAVAILABLE") as caught:
        adapter.structured(request())
    assert credential.scopes == [("https://ai.azure.com/.default",)]
    assert not host.ready(company, qualified)
    assert requests == []
    assert caught.value.observation.call_count == 0


@pytest.mark.parametrize("overrides", [
    {"knowledge_binding": "invalid/private binding"}, {"knowledge_scope": "FOREIGN"},
    {"agent_version": "invalid version"}, {"qualification": "UNVERIFIED"},
])
def test_token_credential_host_validates_qualification_without_acquisition(overrides: Any) -> None:
    with pytest.raises(ProviderConfigurationError, match="FOUNDRY_QUALIFICATION_INVALID"):
        token_credential_host(**overrides)


def responses_payload(value: Any = None, annotations: list[Any] | None = None) -> dict[str, Any]:
    return {
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(value or {"pages": []}),
                        "annotations": annotations or [],
                    }
                ],
            }
        ],
        "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
    }


@pytest.mark.parametrize("task", ["REQUIREMENT_ANALYSIS", "REPORT_DESIGN"])
def test_foundry_agent_context_without_instruction_model_or_tool_override(task: Any) -> None:
    received: list[httpx.Request] = []

    def handler(wire: httpx.Request) -> httpx.Response:
        received.append(wire)
        return httpx.Response(200, json=responses_payload())

    adapter = foundry_adapter(handler)
    candidate = ProviderRequest(
        task=task,
        system_prompt="APPLICATION PROMPT MUST NOT OVERRIDE AGENT",
        context={
            "originalRequest": "Synthetic full request",
            "history": ["turn"],
            "tables": [{"name": "Sales"}],
            "branding": {"primary": "#17635E"},
        },
        output_schema=request().output_schema,
    )
    result = adapter.structured(candidate)
    body = json.loads(received[0].content)
    assert set(body) == {"input", "text", "max_output_tokens", "store", "stream"}
    assert body["store"] is False and body["stream"] is False
    assert json.loads(body["input"][0]["content"]) == {"task": task, "context": candidate.context}
    assert body["text"]["format"]["schema"] == candidate.output_schema
    assert received[0].url.path == adapter.profile.endpoint.split("provider.invalid")[1]
    assert received[0].headers["authorization"] == "Bearer synthetic-token"
    assert "api-key" not in received[0].headers
    assert result.usage == {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
    assert result.grounding["references"] == []
    assert result.grounding["retrievalEvidence"] == "NO_OBSERVED_RETRIEVAL"
    assert result.grounding["qualification"] == "OFFLINE_FIXTURE"


def test_foundry_safe_observed_references_without_raw_tool_payload() -> None:
    source = "https://documents.invalid/standard?private=signed-synthetic-value"
    payload = responses_payload(
        {"pages": [], "standardsApplied": [{"citation": source, "decision": "Synthetic decision"}]},
        [
            {
                "type": "url_citation",
                "url": source,
                "title": "Private title",
                "start_index": 0,
                "end_index": 1,
            }
        ],
    )
    payload["output"].insert(
        0,
        {
            "type": "mcp_call",
            "status": "completed",
            "error": None,
            "output": "PRIVATE RAW TOOL PAYLOAD",
            "arguments": "PRIVATE QUERY",
        },
    )
    captured: list[dict[str, Any]] = []
    original = request()
    candidate = ProviderRequest(
        task=original.task,
        system_prompt=original.system_prompt,
        context=original.context,
        output_schema=original.output_schema,
        grounding_validator=lambda value, grounding: captured.append(grounding),
    )
    result = foundry_adapter(lambda _: httpx.Response(200, json=payload)).structured(candidate)
    assert result.value["standardsApplied"][0]["citation"] in result.grounding["references"]
    assert result.grounding["observedToolCount"] == 1
    safe = json.dumps(result.grounding)
    assert "signed-synthetic" not in safe and "PRIVATE" not in safe and source not in safe
    assert captured == [result.grounding]


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda p: p.update(status="incomplete"), "MODEL_RESPONSE_NOT_COMPLETED"),
        (lambda p: p.update(status="queued"), "MODEL_RESPONSE_NOT_COMPLETED"),
        (lambda p: p.update(error={"message": "private failure"}), "MODEL_RESPONSE_NOT_COMPLETED"),
        (lambda p: p["output"].append(p["output"][0]), "MODEL_OUTPUT_INVALID"),
        (lambda p: p["output"][0]["content"][0].update(text="not json"), "MODEL_OUTPUT_INVALID"),
        (lambda p: p["output"][0]["content"][0].update(type="refusal"), "MODEL_RESPONSE_REFUSED"),
        (
            lambda p: p["output"].insert(0, {"type": "mcp_approval_request"}),
            "MODEL_TOOL_ACTION_UNSUPPORTED",
        ),
        (
            lambda p: p["output"].insert(0, {"type": "function_call"}),
            "MODEL_TOOL_ACTION_UNSUPPORTED",
        ),
        (
            lambda p: p["output"].insert(0, {"type": "mcp_call", "error": "private"}),
            "MODEL_TOOL_FAILED",
        ),
        (
            lambda p: p["output"][0]["content"][0].update(
                text=json.dumps({"standardsApplied": [{"citation": "forged", "decision": "x"}]})
            ),
            "MODEL_GROUNDING_INVALID",
        ),
        (lambda p: p["usage"].update(output_tokens=1001), "MODEL_OUTPUT_BUDGET_EXCEEDED"),
    ],
)
def test_foundry_failures_preserve_safe_observed_usage(mutation: Any, code: str) -> None:
    payload = responses_payload()
    mutation(payload)
    with pytest.raises(ProviderCallError) as caught:
        foundry_adapter(lambda _: httpx.Response(200, json=payload)).structured(request())
    assert caught.value.code == code
    assert caught.value.observation.call_count == 1
    assert caught.value.observation.usage["prompt_tokens"] == 5
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("status", [302, 401, 403])
def test_foundry_never_redirects_or_falls_back(status: int) -> None:
    calls: list[str] = []

    def handler(wire: httpx.Request) -> httpx.Response:
        calls.append(str(wire.url))
        return httpx.Response(status, headers={"Location": "https://other.invalid/"}, json={})

    with pytest.raises(ProviderCallError, match="MODEL_PROVIDER_REJECTED"):
        foundry_adapter(handler).structured(request())
    assert len(calls) == 1 and "other.invalid" not in calls[0]


@pytest.mark.parametrize(
    "credential", [None, "static-key", "expired", "wrong-audience", "nonfinite"]
)
def test_foundry_unavailable_credential_never_calls_transport(credential: Any) -> None:
    import time

    from apbra_api.model_provider import FoundryBearer

    choices = {
        None: None,
        "static-key": "not a token capability",
        "expired": FoundryBearer("synthetic", time.time() - 1),
        "wrong-audience": FoundryBearer("synthetic", time.time() + 300, "wrong"),
        "nonfinite": FoundryBearer("synthetic", float("nan")),
    }
    calls: list[object] = []
    adapter = foundry_adapter(
        lambda wire: calls.append(wire), credential=lambda: choices[credential]
    )
    with pytest.raises(ProviderCallError, match="MODEL_CREDENTIAL_UNAVAILABLE") as caught:
        adapter.structured(request())
    assert calls == [] and caught.value.observation.call_count == 0


def test_foundry_bounded_retry_retains_context_and_usage() -> None:
    calls: list[dict[str, Any]] = []

    def handler(wire: httpx.Request) -> httpx.Response:
        calls.append(json.loads(wire.content))
        return httpx.Response(200, json=responses_payload({"pages": [{"id": str(len(calls))}]}))

    def validate(value: dict[str, Any], grounding: dict[str, Any]) -> None:
        if len(calls) == 1:
            raise ValueError("typed constraint")

    original = request()
    candidate = ProviderRequest(
        task=original.task,
        system_prompt=original.system_prompt,
        context=original.context,
        output_schema=original.output_schema,
        grounding_validator=validate,
        retry_instruction=lambda _: "Correct typed IDs",
    )
    result = foundry_adapter(handler).structured(candidate)
    assert result.call_count == 2 and result.usage["total_tokens"] == 16
    assert len(calls[1]["input"]) == 3
    assert "previous_response_id" not in calls[1] and "conversation" not in calls[1]


def test_foundry_rejects_key_adapter_foreign_tenant_and_unqualified_live_transport() -> None:
    from dataclasses import replace
    from uuid import uuid4

    from apbra_api.model_provider import FoundryAgentResponsesProvider

    with pytest.raises(ProviderConfigurationError, match="MODEL_PROTOCOL_UNSUPPORTED"):
        OpenAICompatibleProvider(foundry_profile(), "synthetic-api-key")
    adapter = foundry_adapter(lambda _: httpx.Response(200, json=responses_payload()))
    with pytest.raises(ProviderConfigurationError, match="FOUNDRY_QUALIFICATION_INVALID"):
        FoundryAgentResponsesProvider(
            adapter.profile,
            replace(adapter._access, company_id=uuid4()),
            company_id=adapter._access.company_id,
            transport=httpx.MockTransport(lambda _: httpx.Response(200)),
        )
    with pytest.raises(ProviderConfigurationError, match="FOUNDRY_QUALIFICATION_INVALID"):
        FoundryAgentResponsesProvider(
            adapter.profile, adapter._access, company_id=adapter._access.company_id
        )


def test_foundry_input_retry_response_and_remaining_time_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[httpx.Request] = []

    def handler(wire: httpx.Request) -> httpx.Response:
        calls.append(wire)
        return httpx.Response(200, json=responses_payload())

    adapter = foundry_adapter(handler, profile_overrides={"time_budget_seconds": 0.5})
    adapter.structured(request())
    assert 0 < calls[0].extensions["timeout"]["read"] <= 0.5
    big = ProviderRequest(
        task="REPORT_DESIGN",
        system_prompt="ignored",
        context={"full": "x" * 10_001},
        output_schema=request().output_schema,
    )
    with pytest.raises(ProviderCallError, match="MODEL_INPUT_BUDGET_EXCEEDED") as caught:
        adapter.structured(big)
    assert caught.value.observation.call_count == 0 and len(calls) == 1
    huge = foundry_adapter(lambda _: httpx.Response(200, content=b"x" * 4_000_001))
    with pytest.raises(ProviderCallError, match="MODEL_OUTPUT_BUDGET_EXCEEDED"):
        huge.structured(request())
    transient = foundry_adapter(
        lambda _: httpx.Response(
            429,
            json={
                "usage": {
                    "input_tokens": 7,
                    "output_tokens": False,
                    "total_tokens": 7,
                }
            },
        )
    )
    with pytest.raises(ProviderCallError, match="MODEL_PROVIDER_TRANSIENT_FAILURE") as caught:
        transient.structured(request())
    assert caught.value.observation.call_count == 2
    assert caught.value.observation.usage == {
        "prompt_tokens": 14,
        "completion_tokens": None,
        "total_tokens": 14,
    }


def test_foundry_foreign_reference_and_raw_signed_reference_rejected() -> None:
    import copy

    annotation = {
        "type": "file_citation",
        "file_id": "file-synthetic",
        "index": 0,
        "filename": "synthetic-standard.md",
    }
    grounded = responses_payload(
        {"standardsApplied": [{"citation": "file-synthetic", "decision": "x"}]}, [annotation]
    )
    result = foundry_adapter(lambda _: httpx.Response(200, json=grounded)).structured(request())
    foreign = copy.deepcopy(grounded)
    foreign["output"][0]["content"][0]["text"] = json.dumps(result.value)
    other = foundry_adapter(lambda _: httpx.Response(200, json=foreign))
    from dataclasses import replace

    other._access = replace(other._access, knowledge_binding="foreign-knowledge")
    with pytest.raises(ProviderCallError, match="MODEL_GROUNDING_INVALID"):
        other.structured(request())
    source = "https://documents.invalid/private?signed=synthetic"
    unsafe = responses_payload(
        {"standardsApplied": [{"citation": source, "decision": source}]},
        [{"type": "url_citation", "url": source}],
    )
    with pytest.raises(ProviderCallError, match="MODEL_GROUNDING_UNSAFE"):
        foundry_adapter(lambda _: httpx.Response(200, json=unsafe)).structured(request())


def test_foundry_tool_listing_and_missing_usage_do_not_claim_retrieval() -> None:
    payload = responses_payload()
    payload.pop("usage")
    payload["output"].insert(0, {"type": "mcp_list_tools"})
    result = foundry_adapter(lambda _: httpx.Response(200, json=payload)).structured(request())
    assert result.grounding["observedToolCount"] == 0
    assert result.grounding["retrievalEvidence"] == "NO_OBSERVED_RETRIEVAL"
    assert all(amount is None for amount in result.usage.values())


def test_foundry_bootstrap_cannot_reinterpret_a_protected_api_key_as_entra(settings) -> None:
    from pydantic import SecretStr

    configured = settings.model_copy(update={
        "model_provider_profile_json": foundry_profile().model_dump_json(),
        "model_provider_api_key": SecretStr("synthetic-must-not-be-reinterpreted"),
    })
    with pytest.raises(ProviderConfigurationError, match="FOUNDRY_SERVER_IDENTITY_REQUIRED"):
        configured.model_credential()


@pytest.mark.parametrize("unknown_first", [False, True])
def test_foundry_mixed_known_and_missing_retry_usage_stays_unknown(unknown_first: bool) -> None:
    calls = 0

    def handler(wire: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = responses_payload()
        if (calls == 1) == unknown_first:
            payload.pop("usage")
        return httpx.Response(200, json=payload)

    def validator(value: dict[str, Any], grounding: dict[str, Any]) -> None:
        if calls == 1:
            raise ValueError("synthetic typed correction")

    original = request()
    candidate = ProviderRequest(task=original.task, system_prompt=original.system_prompt,
                                context=original.context, output_schema=original.output_schema,
                                grounding_validator=validator)
    result = foundry_adapter(handler).structured(candidate)
    assert result.call_count == 2
    assert all(result.usage[name] is None for name in (
        "prompt_tokens", "completion_tokens", "total_tokens",
    ))
    assert result.usage["observed_prompt_tokens"] == 5
    assert result.usage["observed_completion_tokens"] == 3
    assert result.usage["observed_total_tokens"] == 8
    assert result.usage["total_tokens_reported_calls"] == 1


def test_foundry_unknown_transport_retry_cannot_turn_known_usage_into_total() -> None:
    calls = 0

    def handler(wire: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("synthetic timeout", request=wire)
        return httpx.Response(200, json=responses_payload())

    result = foundry_adapter(handler).structured(request())
    assert result.call_count == 2
    assert result.usage["total_tokens"] is None
    assert result.usage["observed_total_tokens"] == 8
    assert result.usage["total_tokens_reported_calls"] == 1


def host_runtime_settings(**changes: Any) -> Any:
    import time

    from apbra_api.config import Settings

    binding = {
        "company_id": "00000000-0000-0000-0000-000000000001",
        "tenant_id": "00000000-0000-0000-0000-000000000002",
        "client_id": "00000000-0000-0000-0000-000000000003",
        "home_account_id": "synthetic-account",
        "provider_profile": foundry_profile().model_dump(),
        "knowledge_binding": "synthetic-standards",
        "knowledge_scope": "SHARED_STANDARDS",
        "agent_version": "6",
        "qualification": "LIVE_METADATA_VERIFIED",
        "manual_authentication_approved": True,
        "authorization_deadline": time.time() + 300,
    }
    binding.update(changes)
    return Settings(
        profile="development",
        database_url="postgresql+psycopg://synthetic@127.0.0.1:15432/apbra_test",
        session_secret="synthetic-" + "session-secret-more-than-32-characters",
        _env_file=None,
        foundry_host_enabled=True,
        foundry_host_binding_json=json.dumps(binding),
        qualified_provider_profiles_json=json.dumps([foundry_profile().model_dump()]),
    )


def host_runtime_module(monkeypatch: pytest.MonkeyPatch) -> Any:
    import importlib
    import sys

    from apbra_api import api, config

    configured = host_runtime_settings().model_copy(update={"foundry_host_enabled": False})
    monkeypatch.setattr(config, "get_settings", lambda: configured)
    monkeypatch.setattr(api, "create_app", lambda **kwargs: kwargs)
    monkeypatch.delitem(sys.modules, "apbra_api.main", raising=False)
    module = importlib.import_module("apbra_api.main")
    monkeypatch.setitem(sys.modules, "apbra_api.main", module)
    return module


def test_host_runtime_default_and_flag_only_do_not_authenticate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = host_runtime_module(monkeypatch)
    calls: list[Any] = []
    monkeypatch.setattr(module, "_device_credential", lambda **kwargs: calls.append(kwargs))
    disabled = host_runtime_settings().model_copy(update={"foundry_host_enabled": False})
    assert "foundry_credentials" not in module.create_runtime_app(disabled)
    with pytest.raises(ProviderConfigurationError):
        module.create_runtime_app(host_runtime_settings())
    assert calls == []


@pytest.mark.parametrize(
    "change",
    [
        {"manual_authentication_approved": False},
        {"authorization_deadline": 1},
        {"provider_profile": profile().model_dump()},
    ],
)
def test_host_runtime_unqualified_configuration_stops_before_factory(
    monkeypatch: pytest.MonkeyPatch,
    change: Any,
) -> None:
    module = host_runtime_module(monkeypatch)
    calls: list[Any] = []
    with pytest.raises(ProviderConfigurationError):
        module.run_foundry_device_code(
            host_runtime_settings(**change), lambda **kwargs: calls.append(kwargs)
        )
    assert calls == []


def test_host_runtime_snapshot_is_bound_expiring_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time
    from types import SimpleNamespace

    from apbra_api.model_provider import FoundryMemoryTokenCredential

    module = host_runtime_module(monkeypatch)
    settings = host_runtime_settings()
    binding = settings.foundry_host_binding()
    snapshot = FoundryMemoryTokenCredential(
        SimpleNamespace(**{"token": "synthetic-private-token"}, expires_on=int(time.time() + 600)),
        authorization_deadline=binding.authorization_deadline,
        enabled=lambda: True,
        binding_digest=binding.binding_digest(),
    )
    try:
        token = snapshot.get_token("https://ai.azure.com/.default")
        assert token.expires_on <= binding.authorization_deadline
        assert "synthetic-private-token" not in repr(token)
        assert "synthetic-private-token" not in repr(snapshot)
        foreign = host_runtime_settings(company_id="00000000-0000-0000-0000-000000000004")
        with pytest.raises(ProviderConfigurationError):
            module.create_runtime_app(foreign, snapshot)
        snapshot.close()
        snapshot.close()
        with pytest.raises(ProviderConfigurationError):
            snapshot.get_token("https://ai.azure.com/.default")
    finally:
        snapshot.close()


def test_host_runtime_manual_flow_closes_sdk_before_server_and_never_refreshes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import time
    from contextlib import nullcontext
    from types import SimpleNamespace

    module = host_runtime_module(monkeypatch)
    settings = host_runtime_settings()
    binding = settings.foundry_host_binding()
    events: list[str] = []
    options: dict[str, Any] = {}

    class FakeSdk:
        def authenticate(self, *, scopes: list[str]) -> Any:
            assert scopes == ["https://ai.azure.com/.default"]
            events.append("authenticate")
            return SimpleNamespace(
                tenant_id=str(binding.tenant_id),
                client_id=str(binding.client_id),
                home_account_id=binding.home_account_id,
            )

        def get_token(self, *scopes: str) -> Any:
            events.append("sdk-token")
            return SimpleNamespace(
                **{"token": "synthetic-private-token"}, expires_on=int(time.time() + 600)
            )

        def close(self) -> None:
            events.append("sdk-close")

    def factory(**kwargs: Any) -> Any:
        options.update(kwargs)
        return FakeSdk()

    monkeypatch.setattr(
        module, "_private_terminal", lambda: nullcontext(SimpleNamespace(isatty=lambda: True))
    )

    def serve(app: Any, _: Any) -> None:
        assert events == ["authenticate", "sdk-token", "sdk-close"]
        host = app["foundry_credentials"]
        host.resolve(binding.company_id, binding.provider_profile).credential()
        host.resolve(binding.company_id, binding.provider_profile).credential()
        events.append("serve")

    monkeypatch.setattr(module, "_serve", serve)
    module.run_foundry_device_code(settings, factory)
    assert events == ["authenticate", "sdk-token", "sdk-close", "serve"]
    assert options["disable_automatic_authentication"] is True
    assert options["cache_persistence_options"] is None
    assert options["enable_support_logging"] is False
    assert options["additionally_allowed_tenants"] == []
    assert 0 < options["timeout"] <= 300
    assert "synthetic-private-token" not in capsys.readouterr().out


def test_host_runtime_missing_port_blocks_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    module = host_runtime_module(monkeypatch)
    settings = host_runtime_settings().model_copy(update={"api_origin": "http://127.0.0.1"})
    calls: list[Any] = []
    with pytest.raises(ProviderConfigurationError):
        module.run_foundry_device_code(settings, lambda **kwargs: calls.append(kwargs))
    assert calls == []


def test_host_runtime_factory_revocation_blocks_auth_and_closes_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextlib import nullcontext
    from types import SimpleNamespace
    module = host_runtime_module(monkeypatch)
    settings = host_runtime_settings()
    calls: list[str] = []
    monkeypatch.setattr(module, "_private_terminal",
                        lambda: nullcontext(SimpleNamespace(isatty=lambda: True)))
    def factory(**kwargs: Any) -> Any:
        settings.foundry_host_enabled = False
        return SimpleNamespace(authenticate=lambda **kw: calls.append("authenticate"),
                               get_token=lambda *args: calls.append("token"),
                               close=lambda: calls.append("close"))
    with pytest.raises(ProviderConfigurationError):
        module.run_foundry_device_code(settings, factory)
    assert calls == ["close"]


def test_host_runtime_import_never_imports_azure(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    original = builtins.__import__
    imports: list[str] = []

    def guarded(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "azure" or name.startswith("azure."):
            imports.append(name)
            raise AssertionError("Default startup reached the Azure SDK")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    module = host_runtime_module(monkeypatch)
    assert module.app is not None
    assert imports == []


@pytest.mark.parametrize("identity", ["tenant_id", "client_id", "home_account_id"])
def test_host_runtime_account_mismatch_stops_before_token(
    monkeypatch: pytest.MonkeyPatch, identity: str,
) -> None:
    module, settings, sdk, events, _ = fake_host_flow(monkeypatch)
    setattr(sdk.record, identity, "synthetic-foreign-account")
    with pytest.raises(ProviderConfigurationError, match="^FOUNDRY_HOST_UNAVAILABLE$"):
        module.run_foundry_device_code(settings, lambda **kwargs: sdk)
    assert events == ["authenticate", "close"]


def fake_host_flow(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any, Any, list[str], Any]:
    import io
    import time
    from contextlib import nullcontext
    from types import SimpleNamespace

    module = host_runtime_module(monkeypatch)
    settings = host_runtime_settings()
    binding = settings.foundry_host_binding()
    events: list[str] = []

    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    terminal = Terminal()

    class FakeSdk:
        record = SimpleNamespace(tenant_id=str(binding.tenant_id),
                                 client_id=str(binding.client_id),
                                 home_account_id=binding.home_account_id)

        def authenticate(self, *, scopes: list[str]) -> Any:
            events.append("authenticate")
            return self.record

        def get_token(self, *scopes: str) -> Any:
            events.append("token")
            return SimpleNamespace(**{"token": "synthetic-secret-canary"},
                                   expires_on=int(time.time() + 600))

        def close(self) -> None:
            events.append("close")

    monkeypatch.setattr(module, "_private_terminal", lambda: nullcontext(terminal))
    monkeypatch.setattr(module, "_serve", lambda *args: events.append("serve"))
    return module, settings, FakeSdk(), events, terminal


@pytest.mark.parametrize("phase", ["authenticate", "get_token"])
@pytest.mark.parametrize("change", ["revoke", "expire"])
def test_host_runtime_authorization_change_during_sdk_operation(
    monkeypatch: pytest.MonkeyPatch, phase: str, change: str,
) -> None:
    from pydantic import SecretStr

    module, settings, sdk, events, _ = fake_host_flow(monkeypatch)
    operation = getattr(sdk, phase)

    def altered(*args: Any, **kwargs: Any) -> Any:
        result = operation(*args, **kwargs)
        if change == "revoke":
            settings.foundry_host_enabled = False
        else:
            binding = settings.foundry_host_binding().model_dump(mode="json")
            binding["authorization_deadline"] = 1
            settings.foundry_host_binding_json = SecretStr(json.dumps(binding))
        return result

    monkeypatch.setattr(sdk, phase, altered)
    with pytest.raises(ProviderConfigurationError, match="^FOUNDRY_HOST_UNAVAILABLE$"):
        module.run_foundry_device_code(settings, lambda **kwargs: sdk)
    assert events == (["authenticate", "close"] if phase == "authenticate"
                      else ["authenticate", "token", "close"])


@pytest.mark.parametrize("phase", ["factory", "authenticate", "get_token", "close", "serve"])
def test_host_runtime_errors_are_private_and_cleanup_is_attempted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture, phase: str,
) -> None:
    import traceback

    module, settings, sdk, events, _ = fake_host_flow(monkeypatch)
    canary = "synthetic-secret-error-canary"

    def fail(*args: Any, **kwargs: Any) -> Any:
        events.append(phase + "-failure")
        raise RuntimeError(canary)

    def factory(**kwargs: Any) -> Any:
        return sdk
    if phase == "factory":
        factory = fail
    elif phase == "serve":
        monkeypatch.setattr(module, "_serve", fail)
    else:
        monkeypatch.setattr(sdk, phase, fail)
    with pytest.raises(ProviderConfigurationError, match="^FOUNDRY_HOST_UNAVAILABLE$") as caught:
        module.run_foundry_device_code(settings, factory)
    rendered = "".join(traceback.format_exception(caught.value))
    captured = capsys.readouterr()
    assert canary not in rendered + captured.out + captured.err + caplog.text
    assert caught.value.__suppress_context__ is True
    if phase != "factory":
        assert "close" in events or "close-failure" in events


def test_host_runtime_prompt_is_private_and_refuses_revocation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from datetime import UTC, datetime, timedelta

    module, settings, sdk, events, terminal = fake_host_flow(monkeypatch)
    options: dict[str, Any] = {}

    def factory(**kwargs: Any) -> Any:
        options.update(kwargs)
        return sdk

    original = sdk.authenticate

    def authenticate(**kwargs: Any) -> Any:
        prompt = options["prompt_callback"]
        prompt("https://microsoft.com/devicelogin", "synthetic-device-code",
               datetime.now(UTC) + timedelta(minutes=1))
        with pytest.raises(ProviderConfigurationError):
            prompt("https://microsoft.com/devicelogin", "expired-device-code",
                   datetime.now(UTC) - timedelta(seconds=1))
        settings.foundry_host_enabled = False
        with pytest.raises(ProviderConfigurationError):
            prompt("https://microsoft.com/devicelogin", "revoked-device-code",
                   datetime.now(UTC) + timedelta(minutes=1))
        return original(**kwargs)

    monkeypatch.setattr(sdk, "authenticate", authenticate)
    with pytest.raises(ProviderConfigurationError):
        module.run_foundry_device_code(settings, factory)
    assert "synthetic-device-code" in terminal.getvalue()
    assert "expired-device-code" not in terminal.getvalue()
    assert "revoked-device-code" not in terminal.getvalue()
    output = capsys.readouterr()
    assert "device-code" not in output.out + output.err
    assert events == ["authenticate", "close"]


def test_host_runtime_noninteractive_terminal_blocks_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextlib import nullcontext
    from types import SimpleNamespace

    module = host_runtime_module(monkeypatch)
    monkeypatch.setattr(module, "_private_terminal",
                        lambda: nullcontext(SimpleNamespace(isatty=lambda: False)))
    calls: list[Any] = []
    with pytest.raises(ProviderConfigurationError):
        module.run_foundry_device_code(host_runtime_settings(),
                                      lambda **kwargs: calls.append(kwargs))
    assert calls == []


def test_host_runtime_idle_timer_drops_snapshot_and_teardown_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from apbra_api import model_provider

    timers: list[Any] = []

    class FakeTimer:
        def __init__(self, interval: float, function: Any) -> None:
            self.interval = interval
            self.function = function
            self.started = False
            self.cancelled = False
            self.daemon = False
            timers.append(self)

        def start(self) -> None:
            self.started = True

        def cancel(self) -> None:
            self.cancelled = True

    monkeypatch.setattr(model_provider, "Timer", FakeTimer)
    monkeypatch.setattr(model_provider.time, "time", lambda: 1000.0)
    snapshot = model_provider.FoundryMemoryTokenCredential(
        SimpleNamespace(**{"token": "synthetic-secret-canary"}, expires_on=2000),
        authorization_deadline=1010.75, enabled=lambda: True, binding_digest="a" * 64,
    )
    timer = timers[0]
    assert timer.interval == 10 and timer.started and timer.daemon
    timer.function()  # Deadline timer fires without any request or SDK operation.
    assert snapshot._token is None
    assert timer.cancelled
    with pytest.raises(ProviderConfigurationError):
        snapshot.get_token("https://ai.azure.com/.default")
    snapshot.close()


@pytest.mark.parametrize("state", ["expired", "revoked", "enabled-error"])
def test_host_runtime_snapshot_drops_token_when_authorization_ends(
    monkeypatch: pytest.MonkeyPatch, state: str,
) -> None:
    from types import SimpleNamespace

    from apbra_api import model_provider

    clock = [1000.0]
    active = [True]
    monkeypatch.setattr(model_provider.time, "time", lambda: clock[0])

    def enabled() -> bool:
        if not active[0] and state == "enabled-error":
            raise RuntimeError("synthetic-private-error")
        return active[0]

    snapshot = model_provider.FoundryMemoryTokenCredential(
        SimpleNamespace(**{"token": "synthetic-secret-canary"}, expires_on=2000),
        authorization_deadline=1300, enabled=enabled, binding_digest="a" * 64,
    )
    try:
        if state == "expired":
            clock[0] = 1300
        else:
            active[0] = False
        with pytest.raises(ProviderConfigurationError):
            snapshot.get_token("https://ai.azure.com/.default")
        assert snapshot._token is None
    finally:
        snapshot.close()


@pytest.mark.parametrize("field,value", [
    ("company_id", "00000000-0000-0000-0000-000000000005"),
    ("tenant_id", "00000000-0000-0000-0000-000000000006"),
    ("client_id", "00000000-0000-0000-0000-000000000007"),
    ("home_account_id", "foreign-account"),
    ("knowledge_binding", "foreign-knowledge"),
    ("knowledge_scope", "TENANT_PRIVATE"),
    ("agent_version", "foreign-version"),
    ("authorization_deadline", 9999999999),
])
def test_host_runtime_snapshot_cannot_be_rebound(
    monkeypatch: pytest.MonkeyPatch, field: str, value: Any,
) -> None:
    import time
    from types import SimpleNamespace

    from apbra_api.model_provider import FoundryMemoryTokenCredential

    module = host_runtime_module(monkeypatch)
    settings = host_runtime_settings()
    snapshot = FoundryMemoryTokenCredential(
        SimpleNamespace(**{"token": "synthetic-secret-canary"},
                        expires_on=int(time.time() + 600)),
        authorization_deadline=settings.foundry_host_binding().authorization_deadline,
        enabled=lambda: True, binding_digest=settings.foundry_host_binding().binding_digest(),
    )
    try:
        calls: list[str] = []
        monkeypatch.setattr(snapshot, "get_token", lambda *args: calls.append("token"))
        with pytest.raises(ProviderConfigurationError):
            module.create_runtime_app(
                host_runtime_settings(**{
                    **settings.foundry_host_binding().model_dump(mode="json"), field: value,
                }), snapshot,
            )
        assert calls == []
    finally:
        snapshot.close()


def test_host_runtime_private_terminal_rejects_redirected_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    module = host_runtime_module(monkeypatch)
    opened: list[Any] = []
    monkeypatch.setattr(module.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr("builtins.open", lambda *args, **kwargs: opened.append(args))
    with pytest.raises(ProviderConfigurationError, match="FOUNDRY_PRIVATE_TERMINAL_REQUIRED"):
        with module._private_terminal():
            raise AssertionError("Redirected input reached the private terminal")
    assert opened == []


def test_host_runtime_server_uses_one_local_process_without_access_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uvicorn

    module = host_runtime_module(monkeypatch)
    calls: list[Any] = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    application = object()
    module._serve(application, host_runtime_settings())
    assert len(calls) == 1
    assert calls[0][0] == (application,)
    assert calls[0][1] == {
        "host": "127.0.0.1", "port": 8000, "workers": 1,
        "reload": False, "access_log": False, "log_config": None,
    }


@pytest.mark.parametrize("failure", [False, True])
def test_host_runtime_server_teardown_drops_token_even_on_error(
    monkeypatch: pytest.MonkeyPatch, failure: bool,
) -> None:
    module, settings, sdk, events, _ = fake_host_flow(monkeypatch)
    snapshots: list[Any] = []
    create = module.create_runtime_app

    def capture(configured: Any, snapshot: Any) -> Any:
        snapshots.append(snapshot)
        return create(configured, snapshot)

    def serve(*args: Any) -> None:
        if failure:
            raise RuntimeError("synthetic-server-error")

    monkeypatch.setattr(module, "create_runtime_app", capture)
    monkeypatch.setattr(module, "_serve", serve)
    if failure:
        with pytest.raises(ProviderConfigurationError):
            module.run_foundry_device_code(settings, lambda **kwargs: sdk)
    else:
        module.run_foundry_device_code(settings, lambda **kwargs: sdk)
    assert events == ["authenticate", "token", "close"]
    assert len(snapshots) == 1
    assert snapshots[0]._token is None
    assert not snapshots[0].ready()


def test_host_runtime_full_profile_and_approval_are_part_of_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time
    from types import SimpleNamespace

    from pydantic import SecretStr

    from apbra_api.model_provider import FoundryMemoryTokenCredential

    module = host_runtime_module(monkeypatch)
    settings = host_runtime_settings()
    binding = settings.foundry_host_binding()
    snapshot = FoundryMemoryTokenCredential(
        SimpleNamespace(**{"token": "synthetic-secret-canary"},
                        expires_on=int(time.time() + 600)),
        authorization_deadline=binding.authorization_deadline,
        enabled=lambda: True, binding_digest=binding.binding_digest(),
    )
    try:
        altered = binding.model_dump(mode="json")
        altered["provider_profile"]["model_or_deployment"] = "synthetic-other-model"
        foreign = settings.model_copy(update={
            "foundry_host_binding_json": SecretStr(json.dumps(altered)),
            "qualified_provider_profiles_json": json.dumps([altered["provider_profile"]]),
        })
        # Both profiles are independently in their exact configured catalogs.
        assert (
            foreign.foundry_host_binding().provider_profile.model_or_deployment
            == "synthetic-other-model"
        )
        with pytest.raises(ProviderConfigurationError):
            module.create_runtime_app(foreign, snapshot)
        assert not hasattr(binding, "token")
        assert binding.home_account_id not in repr(binding) + str(binding)
        assert binding.home_account_id not in repr(settings)
    finally:
        snapshot.close()


@pytest.mark.parametrize("token,expiry", [
    ("", 2000), (None, 2000), (False, 2000),
    ("synthetic-token", False), ("synthetic-token", float("inf")),
    ("synthetic-token", float("nan")), ("synthetic-token", 999),
])
def test_host_runtime_malformed_or_expired_snapshot_is_rejected(
    monkeypatch: pytest.MonkeyPatch, token: Any, expiry: Any,
) -> None:
    from types import SimpleNamespace

    from apbra_api import model_provider

    monkeypatch.setattr(model_provider.time, "time", lambda: 1000.0)
    with pytest.raises(ProviderConfigurationError):
        model_provider.FoundryMemoryTokenCredential(
            SimpleNamespace(**{"token": token}, expires_on=expiry),
            authorization_deadline=1300, enabled=lambda: True, binding_digest="a" * 64,
        )


@pytest.mark.parametrize("origin", [
    "http://127.0.0.1", "http://127.0.0.1:0", "http://127.0.0.1:65536",
    "http://127.0.0.1:invalid", "http://external.invalid:8000", "https://localhost:8000",
    "http://user:private-canary@localhost:8000", "http://localhost:8000/path",
    "http://localhost:8000?private-canary", "http://localhost:8000#private-canary",
])
def test_host_runtime_invalid_origin_is_private_and_blocks_sdk(
    monkeypatch: pytest.MonkeyPatch, origin: str,
) -> None:
    module = host_runtime_module(monkeypatch)
    settings = host_runtime_settings().model_copy(update={"api_origin": origin})
    calls: list[Any] = []
    with pytest.raises(ProviderConfigurationError, match="^FOUNDRY_LOCAL_HOST_REQUIRED$"):
        module.run_foundry_device_code(settings, lambda **kwargs: calls.append(kwargs))
    assert calls == []


@pytest.mark.parametrize("failure", [None, "factory", "authenticate", "get_token", "close"])
@pytest.mark.parametrize("previous", [0, 40, 51])
def test_host_runtime_sdk_logs_are_suppressed_and_prior_state_is_restored(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str], failure: str | None, previous: int,
) -> None:
    import logging

    module, settings, sdk, events, _ = fake_host_flow(monkeypatch)
    original_disable = logging.root.manager.disable
    canary = "synthetic-private-sdk-log-canary"
    loggers = [logging.getLogger("azure.identity._internal.interactive"),
               logging.getLogger("msal.application")]
    for logger in loggers:
        monkeypatch.setattr(logger, "level", logging.DEBUG)
        # A direct descendant handler exercises more than a parent logger filter.
        monkeypatch.setattr(logger, "handlers", [caplog.handler])
        monkeypatch.setattr(logger, "propagate", False)

    def emit(phase: str) -> None:
        # SDK imports can create loggers after the suppression boundary starts.
        lazy = logging.getLogger(f"azure.identity.synthetic.lazy.{previous}.{failure}")
        monkeypatch.setattr(lazy, "level", logging.DEBUG)
        monkeypatch.setattr(lazy, "handlers", [caplog.handler])
        monkeypatch.setattr(lazy, "propagate", False)
        try:
            raise RuntimeError(canary)
        except RuntimeError:
            for logger in [*loggers, lazy]:
                logger.debug("%s", canary, exc_info=True)
                logger.warning("%s failed: %s", phase, canary, exc_info=True)
                logger.critical("%s", canary)
        if failure == phase:
            raise RuntimeError(canary)

    for phase in ("authenticate", "get_token", "close"):
        operation = getattr(sdk, phase)

        def wrapped(*args: Any, phase: str = phase, operation: Any = operation,
                    **kwargs: Any) -> Any:
            emit(phase)
            return operation(*args, **kwargs)

        monkeypatch.setattr(sdk, phase, wrapped)

    def factory(**kwargs: Any) -> Any:
        emit("factory")
        return sdk

    def serve(*args: Any) -> None:
        assert logging.root.manager.disable == previous
        events.append("serve")

    monkeypatch.setattr(module, "_serve", serve)
    try:
        logging.disable(previous)
        if failure is None:
            module.run_foundry_device_code(settings, factory)
            assert events == ["authenticate", "token", "close", "serve"]
        else:
            with pytest.raises(ProviderConfigurationError, match="^FOUNDRY_HOST_UNAVAILABLE$"):
                module.run_foundry_device_code(settings, factory)
        assert logging.root.manager.disable == previous
        captured = capsys.readouterr()
        assert canary not in caplog.text + captured.out + captured.err
        assert not any(canary in record.getMessage() for record in caplog.records)
    finally:
        logging.disable(original_disable)


def test_host_runtime_default_startup_never_changes_logging_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import logging

    calls: list[int] = []
    before = logging.root.manager.disable
    monkeypatch.setattr(logging, "disable", lambda level: calls.append(level))
    module = host_runtime_module(monkeypatch)
    disabled = host_runtime_settings().model_copy(update={"foundry_host_enabled": False})
    module.create_runtime_app(disabled)
    with pytest.raises(ProviderConfigurationError):
        module.create_runtime_app(host_runtime_settings())
    assert calls == []
    assert logging.root.manager.disable == before


@pytest.mark.parametrize("profile", ["test", "hosted"])
def test_host_runtime_non_development_profiles_stop_before_sdk(
    monkeypatch: pytest.MonkeyPatch, profile: str,
) -> None:
    module = host_runtime_module(monkeypatch)
    configured = host_runtime_settings().model_copy(update={"profile": profile})
    calls: list[Any] = []
    with pytest.raises(ProviderConfigurationError, match="FOUNDRY_HOST_CONFIGURATION_UNAVAILABLE"):
        module.run_foundry_device_code(configured, lambda **kwargs: calls.append(kwargs))
    with pytest.raises(ProviderConfigurationError, match="FOUNDRY_HOST_CONFIGURATION_UNAVAILABLE"):
        module.create_runtime_app(configured)
    assert calls == []
def qualification_settings(**changes: Any) -> Any:
    from datetime import UTC, datetime

    from apbra_api.config import Settings

    values = {
        "tenant_id": "4825d1f6-89d8-4e38-9418-2827aa59a23c",
        "client_id": "04b07795-8ddb-461a-bbee-02f9e1bf7b46",
        "project_endpoint": "https://s08-cloud-ai-agent-resource.services.ai.azure.com/api/projects/s08-cloud-ai-agent",
        "agent_name": "s08-document-grounded-agent",
        "agent_version": "6",
        "knowledge_base": "s08-knowledge-base",
        "agent_api_version": "v1",
        "search_api_version": "2025-11-01-preview",
        "manual_authentication_approved": True,
        "independent_private_terminal_approved": True,
        "authorization_deadline": datetime(2026, 10, 9, 18, 5, tzinfo=UTC).timestamp(),
        "request_timeout_seconds": 30,
        "max_metadata_response_bytes": 100000,
        "max_projection_items": 16,
        "max_projection_string_characters": 255,
    }
    values.update(changes)
    return Settings(
        profile="development",
        database_url="postgresql+psycopg://synthetic@127.0.0.1:15432/apbra_test",
        session_secret="synthetic-" + "session-secret-more-than-32-characters",
        _env_file=None,
        foundry_qualification_enabled=True,
        foundry_qualification_binding_json=json.dumps(values),
        foundry_host_enabled=False,
    )


def qualification_flow(monkeypatch: pytest.MonkeyPatch) -> Any:
    import io
    from contextlib import nullcontext
    from datetime import UTC, datetime
    from types import SimpleNamespace

    module = host_runtime_module(monkeypatch)
    clock = [datetime(2026, 10, 9, 18, tzinfo=UTC).timestamp()]
    monkeypatch.setattr(module.time, "time", lambda: clock[0])
    configured = qualification_settings()
    binding = configured.foundry_qualification_binding()
    events: list[str] = []
    options: dict[str, Any] = {}
    receipts: list[httpx.Request] = []
    terminal = io.StringIO()
    monkeypatch.setattr(terminal, "isatty", lambda: True)
    monkeypatch.setattr(
        module, "_qualification_terminal", lambda _: nullcontext(terminal)
    )
    memories: list[Any] = []
    original = module._QualificationMemory

    class Memory(original):
        def __init__(self, *args: Any) -> None:
            super().__init__(*args)
            memories.append(self)

    monkeypatch.setattr(module, "_QualificationMemory", Memory)
    canary = "synthetic-private-metadata-canary"
    properties = {
        "object": "agent",
        "name": binding.agent_name,
        "agent_endpoint": {
            "version_selector": {
                "version_selection_rules": [
                    {
                        "type": "FixedRatio",
                        "agent_version": "6",
                        "traffic_percentage": 100,
                    },
                ]
            }
        },
        "versions": {"latest": {"version": "99"}},
        "instructions": canary,
    }
    version = {
        "object": "agent.version",
        "name": binding.agent_name,
        "version": "6",
        "definition": {
            "kind": "prompt",
            "model": "synthetic-agent-model",
            "instructions": canary,
            "tools": [
                {
                    "type": "mcp",
                    "server_label": "standards",
                    "server_url": "https://synthetic-approved.search.windows.net/knowledgebases/s08-knowledge-base/mcp?api-version=2025-11-01-preview",
                    "allowed_tools": ["knowledge_base_retrieve"],
                    "headers": {"Authorization": canary},
                    "authorization": canary,
                    "project_connection_id": canary,
                }
            ],
        },
        "metadata": {"private": canary},
    }
    knowledge = {
        "name": binding.knowledge_base,
        "outputMode": "answerSynthesis",
        "retrievalReasoningEffort": {"kind": "low"},
        "knowledgeSources": [{"name": canary}],
        "models": [
            {
                "kind": "azureOpenAI",
                "azureOpenAIParameters": {
                    "modelName": "synthetic-planning-model",
                    "deploymentId": "synthetic-planning-deployment",
                    "resourceUri": canary,
                    "apiKey": canary,
                },
            }
        ],
        "retrievalInstructions": canary,
        "answerInstructions": canary,
        "encryptionKey": {"accessCredentials": {"applicationSecret": canary}},
    }
    state = SimpleNamespace(
        module=module,
        settings=configured,
        binding=binding,
        clock=clock,
        events=events,
        options=options,
        receipts=receipts,
        terminal=terminal,
        properties=properties,
        version=version,
        knowledge=knowledge,
        memories=memories,
        canary=canary,
        denied=None,
        response=None,
    )

    def confirm(tty: Any, approval: Any, message: str, reply: str) -> None:
        tty.write(message)
        events.append(reply)
        if state.denied == reply:
            raise ProviderConfigurationError("synthetic-denied-private-confirmation")

    monkeypatch.setattr(module, "_confirm_private", confirm)
    monkeypatch.setattr(
        module, "_serve", lambda *args: pytest.fail("Qualification served the app")
    )
    monkeypatch.setattr(
        module,
        "create_runtime_app",
        lambda *args: pytest.fail("Qualification constructed runtime app"),
    )

    class SDK:
        record = SimpleNamespace(
            tenant_id=binding.tenant_id,
            client_id=binding.client_id,
            home_account_id="synthetic-owner-account",
            username="owner@example.invalid",
        )

        def authenticate(self, *, scopes: list[str]) -> Any:
            assert scopes == [module._SCOPE]
            events.append("authenticate")
            return self.record

        def get_token(self, *scopes: str) -> Any:
            assert len(scopes) == 1 and scopes[0] in {
                module._SCOPE,
                module._SEARCH_SCOPE,
            }
            events.append("token:" + scopes[0])
            return SimpleNamespace(
                **{"token": "synthetic-secret-bearer"}, expires_on=clock[0] + 600
            )

        def close(self) -> None:
            events.append("sdk-close")

    sdk = SDK()
    state.sdk = sdk

    def factory(**kwargs: Any) -> Any:
        events.append("sdk-factory")
        options.update(kwargs)
        return sdk

    def handler(request: httpx.Request) -> httpx.Response:
        receipts.append(request)
        events.append("GET:" + request.url.path)
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer synthetic-secret-bearer"
        assert request.headers["Accept-Encoding"] == "identity"
        if state.response is not None:
            return state.response(request)
        if "/versions/6" in request.url.path:
            return httpx.Response(200, json=state.version)
        if "knowledgebases" in request.url.path:
            return httpx.Response(200, json=state.knowledge)
        return httpx.Response(200, json=state.properties)

    clients: list[httpx.Client] = []

    def client_factory(**kwargs: Any) -> httpx.Client:
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        assert kwargs["verify"] is True
        client = httpx.Client(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(client)
        return client

    state.factory = factory
    state.client_factory = client_factory
    state.clients = clients
    return state


def run_qualification(state: Any) -> dict[str, Any]:
    return state.module.run_foundry_qualification(
        state.settings, state.factory, state.client_factory
    )


def assert_qualification_cleanup(state: Any) -> None:
    assert state.events.count("sdk-close") == 1
    assert all(client.is_closed for client in state.clients)
    for memory in state.memories:
        assert memory._sdk is None and memory._client is None
        assert memory._record is None and memory._account is None
        assert (
            memory._tokens == {} and memory._documents == [] and memory._buffers == []
        )
        assert memory._closed


def test_qualification_exact_three_gets_private_confirmations_and_safe_projection(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    state = qualification_flow(monkeypatch)
    result = run_qualification(state)
    assert result["status"] == "METADATA_OBSERVED_ONLY"
    assert result["observedEndpointSelector"] == [
        {"type": "FixedRatio", "version": "6", "trafficPercentage": 100},
    ]
    assert (
        result["observedVersion"] == "6"
    )  # versions.latest=99 is deliberately ignored.
    assert result["modelDeployment"] == "synthetic-agent-model"
    assert result["storedInstructionUtf8Bytes"] == len(state.canary.encode("utf-8"))
    assert result["retrievalInstructionUtf8Bytes"] == len(state.canary.encode("utf-8"))
    assert result["answerInstructionUtf8Bytes"] == len(state.canary.encode("utf-8"))
    assert result["responseConfigurationUtf8Bytes"] == {"response_format": None, "text": None}
    assert result["models"][0]["deploymentId"] == "synthetic-planning-deployment"
    assert result["knowledgeSourceMaxSubQueries"] == [None]
    assert result["numericCaps"] is None and result["retrieveDefaults"] is None
    assert result["allInCostBound"] == "UNKNOWN"
    assert not any(
        result[key]
        for key in (
            "routingVerified",
            "groundingVerified",
            "tenantIsolationVerified",
            "runtimeActivated",
        )
    )
    assert len(state.receipts) == 3
    assert [str(receipt.url) for receipt in state.receipts] == [
        state.binding.project_endpoint
        + "/agents/s08-document-grounded-agent?api-version=v1",
        state.binding.project_endpoint
        + "/agents/s08-document-grounded-agent/versions/6?api-version=v1",
        "https://synthetic-approved.search.windows.net/knowledgebases('s08-knowledge-base')?api-version=2025-11-01-preview",
    ]
    assert state.events.index("CONFIRM ACCOUNT") < state.events.index(
        "token:" + state.module._SCOPE
    )
    assert state.events.index("CONFIRM SEARCH") < state.events.index(
        "token:" + state.module._SEARCH_SCOPE
    )
    assert state.options["tenant_id"] == state.binding.tenant_id
    assert state.options["client_id"] == state.binding.client_id
    assert state.options["cache_persistence_options"] is None
    assert state.options["disable_automatic_authentication"] is True
    assert state.options["additionally_allowed_tenants"] == []
    assert state.options["retry_total"] == 0
    assert state.options["read_timeout"] <= state.binding.request_timeout_seconds
    output = capsys.readouterr()
    projection = json.dumps(result)
    for private in (
        state.canary,
        "owner@example.invalid",
        "synthetic-owner-account",
        "synthetic-secret-bearer",
    ):
        assert private not in projection + output.out + output.err + caplog.text
    assert "owner@example.invalid" in state.terminal.getvalue()
    assert "synthetic-owner-account" not in state.terminal.getvalue()
    assert_qualification_cleanup(state)
    assert state.settings.foundry_host_enabled is False
    assert state.settings.foundry_host_binding_json is None


@pytest.mark.parametrize(
    "reply", ["CONFIRM PRIVATE TERMINAL", "CONFIRM ACCOUNT", "CONFIRM SEARCH"]
)
def test_qualification_declined_confirmation_stops_next_boundary(
    monkeypatch: pytest.MonkeyPatch,
    reply: str,
) -> None:
    state = qualification_flow(monkeypatch)
    state.denied = reply
    with pytest.raises(
        ProviderConfigurationError, match="^FOUNDRY_QUALIFICATION_UNAVAILABLE$"
    ):
        run_qualification(state)
    if reply == "CONFIRM PRIVATE TERMINAL":
        assert state.events == [reply]
    else:
        assert_qualification_cleanup(state)
    if reply == "CONFIRM ACCOUNT":
        assert state.receipts == []
        assert not any(event.startswith("token:") for event in state.events)
    if reply == "CONFIRM SEARCH":
        assert len(state.receipts) == 2
        assert "token:" + state.module._SEARCH_SCOPE not in state.events


@pytest.mark.parametrize("field", ["tenant_id", "client_id", "home_account_id"])
def test_qualification_wrong_account_stops_before_get(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    state = qualification_flow(monkeypatch)
    setattr(state.sdk.record, field, "foreign account")
    with pytest.raises(ProviderConfigurationError):
        run_qualification(state)
    assert state.receipts == []
    assert_qualification_cleanup(state)


@pytest.mark.parametrize(
    "change",
    [
        {"tenant_id": "00000000-0000-0000-0000-000000000002"},
        {"client_id": "00000000-0000-0000-0000-000000000003"},
        {"agent_name": "foreign-agent"},
        {"agent_version": "7"},
        {"knowledge_base": "foreign-kb"},
        {"project_endpoint": "https://foreign.invalid/api/projects/s08-cloud-ai-agent"},
        {"agent_api_version": "foreign"},
        {"search_api_version": "foreign"},
        {"manual_authentication_approved": False},
        {"independent_private_terminal_approved": False},
        {"authorization_deadline": 1},
        {"authorization_deadline": 9999999999},
    ],
)
def test_qualification_configuration_failures_do_not_construct_sdk(
    monkeypatch: pytest.MonkeyPatch,
    change: Any,
) -> None:
    state = qualification_flow(monkeypatch)
    state.settings = qualification_settings(**change)
    with pytest.raises(ProviderConfigurationError):
        run_qualification(state)
    assert state.events == [] and state.receipts == []


@pytest.mark.parametrize(
    "target",
    [
        "properties-name",
        "version-name",
        "version",
        "selector",
        "kb",
        "tool-kb",
        "tool-url",
        "tools-null",
    ],
)
def test_qualification_resource_mismatch_fails_without_followup_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    state = qualification_flow(monkeypatch)
    if target == "properties-name":
        state.properties["name"] = "foreign-agent"
    elif target == "version-name":
        state.version["name"] = "foreign-agent"
    elif target == "version":
        state.version["version"] = "7"
    elif target == "selector":
        state.properties["agent_endpoint"] = {}
    elif target == "kb":
        state.knowledge["name"] = "foreign-kb"
    elif target == "tools-null":
        state.version["definition"]["tools"][0]["allowed_tools"] = None
    elif target == "tool-kb":
        state.version["definition"]["tools"][0]["server_url"] = (
            "https://synthetic-approved.search.windows.net/knowledgebases/foreign-kb/mcp"
        )
    else:
        state.version["definition"]["tools"][0]["server_url"] = (
            "https://private.invalid/knowledgebases/s08-knowledge-base/mcp"
        )
    with pytest.raises(ProviderConfigurationError):
        run_qualification(state)
    assert len(state.receipts) == (3 if target == "kb" else 2)
    if target != "kb":
        assert "token:" + state.module._SEARCH_SCOPE not in state.events
    assert_qualification_cleanup(state)


@pytest.mark.parametrize(
    "response",
    [
        "redirect",
        "denied",
        "oversize",
        "malformed",
        "duplicate",
        "deep",
        "digits",
        "array",
        "wrong-media-type",
        "compressed",
    ],
)
def test_qualification_untrusted_metadata_is_bounded_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    response: str,
) -> None:
    state = qualification_flow(monkeypatch)
    contents = {
        "malformed": b'{"secret":',
        "duplicate": b'{"name":"a","name":"b"}',
        "deep": b"[" * 2000 + b"0" + b"]" * 2000,
        "digits": b'{"number":' + b"1" * 5000 + b"}",
        "array": b"[]",
        "oversize": b"x" * (state.binding.max_metadata_response_bytes + 1),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if response == "redirect":
            return httpx.Response(302, headers={"Location": "https://private.invalid"})
        if response == "denied":
            return httpx.Response(403, json={"error": state.canary})
        if response == "wrong-media-type":
            return httpx.Response(
                200, headers={"content-type": "application/json-private"}, content=b"{}"
            )
        if response == "compressed":
            # Reject the header before any decoder or body iteration.
            return httpx.Response(
                200,
                headers={"content-type": "application/json", "content-encoding": "gzip"},
                stream=httpx.ByteStream(b"synthetic-unused-body"),
            )
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=contents[response],
        )

    state.response = handler
    with pytest.raises(
        ProviderConfigurationError, match="^FOUNDRY_QUALIFICATION_UNAVAILABLE$"
    ):
        run_qualification(state)
    assert len(state.receipts) == 1
    assert_qualification_cleanup(state)


@pytest.mark.parametrize(
    "phase", ["factory", "authenticate", "foundry-token", "search-token", "close"]
)
def test_qualification_sdk_failures_suppress_emitted_logs_and_clear_state(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    phase: str,
) -> None:
    import logging
    import traceback

    state = qualification_flow(monkeypatch)
    previous = logging.root.manager.disable

    def fail(*args: Any, **kwargs: Any) -> Any:
        logger = logging.getLogger("azure.identity.synthetic.qualification.new")
        logger.setLevel(logging.DEBUG)
        monkeypatch.setattr(logger, "handlers", [caplog.handler])
        monkeypatch.setattr(logger, "propagate", False)
        logger.warning("%s", state.canary)
        raise RuntimeError(state.canary)

    if phase == "factory":
        state.factory = fail
    elif phase == "authenticate":
        monkeypatch.setattr(state.sdk, "authenticate", fail)
    elif phase == "close":
        original = state.sdk.close

        def close() -> None:
            original()
            fail()

        monkeypatch.setattr(state.sdk, "close", close)
    else:
        original = state.sdk.get_token

        def token(*scopes: str) -> Any:
            if (scopes[0] == state.module._SEARCH_SCOPE) == (phase == "search-token"):
                return fail()
            return original(*scopes)

        monkeypatch.setattr(state.sdk, "get_token", token)
    with pytest.raises(ProviderConfigurationError) as caught:
        run_qualification(state)
    output = capsys.readouterr()
    rendered = "".join(traceback.format_exception(caught.value))
    assert state.canary not in rendered + output.out + output.err + caplog.text
    assert logging.root.manager.disable == previous
    if phase != "factory":
        assert_qualification_cleanup(state)


@pytest.mark.parametrize(
    "stage,action", [
        (stage, action)
        for stage in ("factory", "authenticate", "token", "first-get", "second-get", "third-get")
        for action in ("expire", "revoke", "change-account")
        if not (action == "change-account" and stage in {"factory", "authenticate"})
    ],
)
def test_qualification_deadline_revocation_account_changes_stop_operations(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    action: str,
) -> None:
    state = qualification_flow(monkeypatch)

    def change() -> None:
        if action == "expire":
            state.clock[0] = state.binding.authorization_deadline
        elif action == "revoke":
            state.settings.foundry_qualification_enabled = False
        else:
            state.sdk.record.home_account_id = "synthetic-other-account"

    if stage == "factory":
        original = state.factory

        def factory(**kwargs: Any) -> Any:
            sdk = original(**kwargs)
            change()
            return sdk

        state.factory = factory
    elif stage in {"authenticate", "token"}:
        operation = "authenticate" if stage == "authenticate" else "get_token"
        original = getattr(state.sdk, operation)

        def altered(*args: Any, **kwargs: Any) -> Any:
            value = original(*args, **kwargs)
            change()
            return value

        monkeypatch.setattr(state.sdk, operation, altered)
    else:
        boundary = {"first-get": 1, "second-get": 2, "third-get": 3}[stage]

        def response(request: httpx.Request) -> httpx.Response:
            if len(state.receipts) == boundary:
                change()
            value = (
                state.knowledge
                if "knowledgebases" in request.url.path
                else (
                    state.version
                    if "versions" in request.url.path
                    else state.properties
                )
            )
            return httpx.Response(200, json=value)

        state.response = response
    with pytest.raises(ProviderConfigurationError):
        run_qualification(state)
    assert_qualification_cleanup(state)
    expected = {
        "factory": 0,
        "authenticate": 0,
        "token": 0,
        "first-get": 1,
        "second-get": 2,
        "third-get": 3,
    }[stage]
    assert len(state.receipts) == expected
@pytest.mark.parametrize(
    "marker",
    [
        "CODEX_THREAD_ID",
        "CODEX_SESSION_ID",
        "CODEX_CI",
        "GITHUB_ACTIONS",
        "CI",
        "SSH_CONNECTION",
        "SSH_TTY",
        "TMUX",
        "STY",
    ],
)
def test_qualification_captured_terminal_markers_stop_before_process_sdk_or_challenge(
    monkeypatch: pytest.MonkeyPatch,
    marker: str,
) -> None:
    from datetime import UTC, datetime

    module = host_runtime_module(monkeypatch)
    monkeypatch.setattr(
        module.time, "time", lambda: datetime(2026, 10, 9, 18, tzinfo=UTC).timestamp()
    )
    monkeypatch.setenv(marker, "synthetic-captured")
    calls: list[Any] = []
    monkeypatch.setattr(
        module.subprocess, "run", lambda *args, **kwargs: calls.append("process")
    )
    with pytest.raises(ProviderConfigurationError):
        module.run_foundry_qualification(
            qualification_settings(), lambda **kwargs: calls.append("sdk")
        )
    assert calls == []


@pytest.mark.parametrize(
    "ancestry,allowed",
    [
        (
            [
                "20 python3",
                "30 zsh",
                "1 /Applications/Utilities/Terminal.app/Contents/MacOS/Terminal",
            ],
            True,
        ),
        (
            ["20 python3", "30 zsh", "1 /Applications/iTerm.app/Contents/MacOS/iTerm2"],
            True,
        ),
        (["20 python3", "30 zsh", "1 launchd"], False),
        (
            [
                "20 python3",
                "30 /Applications/Codex.app/Contents/MacOS/Codex",
                "1 Terminal",
            ],
            False,
        ),
        (["20 python3", "30 Terminal", "1 Electron"], False),
        (["20 python3", "30 sshd", "1 Terminal"], False),
        (["10 python3"], False),
        (["invalid-process-private-canary"], False),
    ],
)
def test_qualification_terminal_provenance_requires_bounded_owner_os_ancestry(
    monkeypatch: pytest.MonkeyPatch,
    ancestry: list[str],
    allowed: bool,
) -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace

    module = host_runtime_module(monkeypatch)
    monkeypatch.setattr(
        module.time, "time", lambda: datetime(2026, 10, 9, 18, tzinfo=UTC).timestamp()
    )
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setattr(module.os, "getpid", lambda: 10)
    for marker in module._CAPTURED_TERMINAL_MARKERS:
        monkeypatch.delenv(marker, raising=False)
    calls: list[Any] = []
    sequence = iter(ancestry)

    def process(arguments: Any, **kwargs: Any) -> Any:
        calls.append(arguments)
        assert arguments[:4] == ["/bin/ps", "-o", "ppid=,comm=", "-p"]
        assert arguments[4].isdigit()
        assert kwargs["capture_output"] is True
        return SimpleNamespace(stdout=next(sequence))

    monkeypatch.setattr(module.subprocess, "run", process)
    if allowed:
        module._owner_terminal_provenance(
            qualification_settings().foundry_qualification_binding()
        )
    else:
        with pytest.raises(ProviderConfigurationError):
            module._owner_terminal_provenance(
                qualification_settings().foundry_qualification_binding()
            )
    assert len(calls) <= 16


def test_qualification_private_confirmation_is_explicit_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io

    state = qualification_flow(monkeypatch)
    # Exercise the production helper separately; fixture confirms only synthetic driver steps.
    source = state.module._confirm_private
    assert callable(source)
    import importlib.util
    from pathlib import Path

    # Its code is not copied: reload a fresh module with the same mocked ordinary startup.
    spec = importlib.util.spec_from_file_location(
        "apbra_api.synthetic_private_confirmation", Path(state.module.__file__)
    )
    actual = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(actual)
    terminal = io.StringIO("CONFIRM ACCOUNT\n")
    monkeypatch.setattr(terminal, "isatty", lambda: True)
    monkeypatch.setattr(terminal, "fileno", lambda: 99)
    characters = iter(b"CONFIRM ACCOUNT\n")
    monkeypatch.setattr(actual.os, "read", lambda *args: bytes([next(characters)]))
    monkeypatch.setattr(actual.select, "select", lambda *args: ([terminal], [], []))
    # Writes should not consume the simulated owner's input.
    writes: list[str] = []
    monkeypatch.setattr(terminal, "write", lambda text: writes.append(text))
    actual._confirm_private(
        terminal, state.binding, "Selected synthetic account", "CONFIRM ACCOUNT"
    )
    assert writes and "CONFIRM ACCOUNT" in writes[0]
    terminal.seek(0)
    monkeypatch.setattr(actual.select, "select", lambda *args: ([], [], []))
    with pytest.raises(ProviderConfigurationError):
        actual._confirm_private(
            terminal, state.binding, "Selected synthetic account", "CONFIRM ACCOUNT"
        )


@pytest.mark.parametrize(
    "scope,url",
    [
        ("https://ai.azure.com/.default", "https://foreign.invalid/agents/x"),
        (
            "https://ai.azure.com/.default",
            "https://synthetic-approved.search.windows.net/knowledgebases('s08-knowledge-base')?api-version=2025-11-01-preview",
        ),
        (
            "https://search.azure.com/.default",
            "https://s08-cloud-ai-agent-resource.services.ai.azure.com/api/projects/s08-cloud-ai-agent/agents/s08-document-grounded-agent?api-version=v1",
        ),
    ],
)
def test_qualification_memory_whitelist_blocks_unknown_url_or_audience_before_client(
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
    url: str,
) -> None:
    state = qualification_flow(monkeypatch)
    with state.module._private_sdk_logging():
        memory = state.module._QualificationMemory(state.settings, state.binding)
        try:
            memory.install_sdk(state.sdk)
            memory.authenticate()
            memory.confirm_account()
            memory.acquire(state.module._SCOPE)
            with pytest.raises(ProviderConfigurationError):
                memory.get(
                    url,
                    scope,
                    lambda **kwargs: pytest.fail("Unknown URL constructed a client"),
                )
            with pytest.raises(ProviderConfigurationError):
                memory.acquire(state.module._SEARCH_SCOPE)
        finally:
            memory.close()
    assert state.receipts == []
    assert_qualification_cleanup(state)


@pytest.mark.parametrize("renewed", [False, True])
def test_qualification_idle_deadline_clears_private_memory_without_request(
    monkeypatch: pytest.MonkeyPatch,
    renewed: bool,
) -> None:
    state = (
        renewed_qualification_flow(monkeypatch)
        if renewed else qualification_flow(monkeypatch)
    )
    timers: list[Any] = []

    class Timer:
        def __init__(self, delay: float, callback: Any) -> None:
            self.delay = delay
            self.callback = callback
            self.daemon = False
            self.cancelled = False
            timers.append(self)

        def start(self) -> None:
            pass

        def cancel(self) -> None:
            self.cancelled = True

    monkeypatch.setattr(state.module, "Timer", Timer)
    with state.module._private_sdk_logging():
        memory = state.module._QualificationMemory(state.settings, state.binding)
        memory.install_sdk(state.sdk)
        memory.authenticate()
        memory.confirm_account()
        memory.acquire(state.module._SCOPE)
        state.clock[0] = state.binding.authorization_deadline
        timers[-1].callback()
        assert_qualification_cleanup(state)
        assert timers[-1].cancelled
        with pytest.raises(ProviderConfigurationError):
            memory.acquire(state.module._SEARCH_SCOPE)
        memory.close()
    assert state.events.count("sdk-close") == 1


def test_qualification_safe_observed_caps_preserve_unknown_and_do_not_qualify_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = qualification_flow(monkeypatch)
    state.knowledge["knowledgeSources"][0]["maxSubQueries"] = 4
    state.knowledge["retrieveDefaults"] = {
        "maxRuntimeInSeconds": 30,
        "maxOutputSize": 2000,
        "privateInstructions": state.canary,
    }
    result = run_qualification(state)
    assert result["knowledgeSourceMaxSubQueries"] == [4]
    assert result["numericCaps"] == {"maxRuntimeInSeconds": 30, "maxOutputSize": 2000}
    assert result["allInCostBound"] == "UNKNOWN"
    assert state.canary not in json.dumps(result)
    assert_qualification_cleanup(state)


def test_qualification_flag_does_not_authenticate_or_export_runtime_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = host_runtime_module(monkeypatch)
    calls: list[Any] = []
    monkeypatch.setattr(
        module, "_device_credential", lambda **kwargs: calls.append("sdk")
    )
    monkeypatch.setattr(
        module, "_QualificationMemory", lambda *args: calls.append("memory")
    )
    configured = qualification_settings()
    application = module.create_runtime_app(configured)
    assert "foundry_credentials" not in application
    assert configured.foundry_host_binding_json is None
    assert calls == []


def test_qualification_cli_selects_discovery_only_and_rejects_ambiguous_modes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = host_runtime_module(monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(module.sys, "argv", ["apbra-api", "--foundry-qualify"])

    def qualify() -> dict[str, str]:
        calls.append("qualification")
        return {"status": "METADATA_OBSERVED_ONLY"}

    monkeypatch.setattr(module, "run_foundry_qualification", qualify)
    monkeypatch.setattr(module, "run_foundry_device_code", lambda: calls.append("host"))
    module.main()
    assert calls == ["qualification"]
    assert json.loads(capsys.readouterr().out) == {"status": "METADATA_OBSERVED_ONLY"}
    monkeypatch.setattr(
        module.sys, "argv", ["apbra-api", "--foundry-qualify", "--foundry-device-code"]
    )
    with pytest.raises(SystemExit) as caught:
        module.main()
    assert caught.value.code == 2
    assert calls == ["qualification"]


@pytest.mark.parametrize("boundary", ["settings-loader", "binding-loader"])
@pytest.mark.parametrize("failure", [ValueError, RuntimeError])
def test_qualification_settings_loader_failure_never_exposes_private_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: type[Exception],
    boundary: str,
) -> None:
    state = qualification_flow(monkeypatch)

    def unavailable(*arguments: Any) -> Any:
        raise failure(state.canary)

    if boundary == "settings-loader":
        monkeypatch.setattr(state.module, "get_settings", unavailable)
    else:
        monkeypatch.setattr(state.module, "get_settings", lambda: state.settings)
        monkeypatch.setattr(type(state.settings), "foundry_qualification_binding", unavailable)
    with pytest.raises(
        ProviderConfigurationError, match="^FOUNDRY_QUALIFICATION_UNAVAILABLE$"
    ) as caught:
        state.module.run_foundry_qualification(
            credential_factory=state.factory, client_factory=state.client_factory
        )
    assert caught.value.__suppress_context__ is True
    assert state.events == [] and state.receipts == [] and state.memories == []
    captured = capsys.readouterr()
    assert state.canary not in captured.out + captured.err + str(caught.value)


def renewed_qualification_flow(monkeypatch: pytest.MonkeyPatch) -> Any:
    from datetime import UTC, datetime

    state = qualification_flow(monkeypatch)
    state.clock[0] = datetime(2026, 10, 10, 1, tzinfo=UTC).timestamp()
    state.settings = qualification_settings(authorization_deadline=1791598140)
    state.binding = state.settings.foundry_qualification_binding()
    return state


@pytest.mark.parametrize("deadline", [1791598139, 1791598140])
def test_qualification_renewed_ceiling_allows_only_metadata_and_cleans_memory(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    deadline: int,
) -> None:
    state = renewed_qualification_flow(monkeypatch)
    state.settings = qualification_settings(authorization_deadline=deadline)
    state.binding = state.settings.foundry_qualification_binding()
    result = run_qualification(state)
    assert result["status"] == "METADATA_OBSERVED_ONLY"
    assert result["allInCostBound"] == "UNKNOWN"
    assert len(state.receipts) == 3
    assert state.events.count("authenticate") == 1
    assert sum(event.startswith("token:") for event in state.events) == 2
    assert_qualification_cleanup(state)
    captured = capsys.readouterr()
    assert state.canary not in captured.out + captured.err + json.dumps(result)


@pytest.mark.parametrize(
    "deadline,now",
    [
        (1791598141, 1791594000),
        (1791598140, 1791598140),
        (1791598140, 1791598141),
        (1791573000, 1791594000),
        (1791585300, 1791594000),
        (None, 1791594000),
        (0, 1791594000),
        (float("nan"), 1791594000),
        (float("inf"), 1791594000),
        ("synthetic-private-invalid-deadline", 1791594000),
        ("MISSING", 1791594000),
    ],
)
def test_qualification_renewal_invalid_deadlines_stop_before_private_terminal_sdk(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    deadline: Any,
    now: int,
) -> None:
    from pydantic import SecretStr

    state = qualification_flow(monkeypatch)
    state.clock[0] = now
    values = json.loads(state.settings.foundry_qualification_binding_json.get_secret_value())
    if deadline == "MISSING":
        values.pop("authorization_deadline")
    else:
        values["authorization_deadline"] = deadline
    state.settings.foundry_qualification_binding_json = SecretStr(json.dumps(values))
    with pytest.raises(
        ProviderConfigurationError, match="^FOUNDRY_QUALIFICATION_UNAVAILABLE$"
    ) as caught:
        run_qualification(state)
    assert caught.value.__suppress_context__ is True
    assert state.events == [] and state.receipts == [] and state.memories == []
    assert state.terminal.getvalue() == ""
    captured = capsys.readouterr()
    assert "synthetic-private" not in captured.out + captured.err + str(caught.value)


@pytest.mark.parametrize("action", ["expire", "revoke"])
def test_qualification_renewed_window_still_stops_after_sdk_factory(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    state = renewed_qualification_flow(monkeypatch)
    factory = state.factory

    def altered_factory(**options: Any) -> Any:
        sdk = factory(**options)
        if action == "expire":
            state.clock[0] = state.binding.authorization_deadline
        else:
            state.settings.foundry_qualification_enabled = False
        return sdk

    state.factory = altered_factory
    with pytest.raises(ProviderConfigurationError):
        run_qualification(state)
    assert "authenticate" not in state.events
    assert not any(event.startswith("token:") for event in state.events)
    assert state.receipts == []
    assert_qualification_cleanup(state)
