from __future__ import annotations

import json

import httpx
import pytest

from apbra_api.model_provider import (
    OpenAICompatibleProvider,
    ProviderCallError,
    ProviderConfigurationError,
    ProviderProfile,
    ProviderRequest,
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
        output_schema={"type": "object"},
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
    assert len(observed) == 1
    assert str(observed[0].url) == "https://provider.invalid/v1/chat/completions"
    assert observed[0].headers["authorization"] == "Bearer server-secret"
    body = json.loads(observed[0].content)
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True


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
