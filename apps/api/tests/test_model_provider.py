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
