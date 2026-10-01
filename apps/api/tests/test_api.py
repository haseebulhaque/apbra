import json

import pytest
from fastapi.testclient import TestClient

from apbra_api.api import create_app
from apbra_api.config import Settings
from apbra_api.model_provider import ProviderConfigurationError
from apbra_api.persistence import Database


def test_health_requires_live_database(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok", "database": "ok"}


def test_mutation_requires_csrf(client: TestClient) -> None:
    assert client.post("/api/auth/logout").status_code == 401


def test_validation_errors_do_not_echo_invitation_bearer_input(client: TestClient) -> None:
    raw = "sensitive-invitation-bearer"
    response = client.post("/api/invitations/inspect", json={"token": raw})
    assert response.status_code == 422
    assert raw not in response.text
    assert response.json() == {
        "error": {
            "code": "REQUEST_VALIDATION_FAILED",
            "message": "The request format is invalid.",
        }
    }


def test_non_test_profile_cannot_enable_deterministic_semantic_simulator(
    settings: Settings,
) -> None:
    runtime = settings.model_copy(
        update={"profile": "development", "test_semantic_simulator_enabled": True}
    )
    with pytest.raises(ValueError, match="test-profile only"):
        runtime.validate_security_profile()


def test_disabled_automatic_generation_boots_without_provider_configuration(
    settings: Settings, database: Database
) -> None:
    runtime = settings.model_copy(
        update={
            "automatic_generation_enabled": False,
            "model_provider_profile_json": None,
            "model_provider_api_key": None,
        }
    )
    runtime.validate_security_profile()
    with TestClient(create_app(settings=runtime, database=database)) as client:
        assert client.get("/api/health").json() == {"status": "ok", "database": "ok"}


@pytest.mark.parametrize(
    ("profile", "credential", "code"),
    [
        (None, None, "MODEL_PROFILE_MISSING"),
        ('{"malformed":true}', "synthetic-test-credential", "MODEL_PROFILE_INVALID"),
        (
            json.dumps(
                {
                    "profile_id": "synthetic-test-profile",
                    "protocol": "OPENAI_CHAT_COMPATIBLE",
                    "endpoint": "https://provider.invalid/v1/chat/completions",
                    "model_or_deployment": "synthetic-test-model",
                    "api_version": "synthetic-test-version",
                    "region": "synthetic-test-region",
                    "prompt_version": "synthetic-test-prompt",
                    "configuration_id": "synthetic-test-configuration",
                    "capabilities": {"structured_output": True, "vision": False},
                    "max_calls_per_operation": 1,
                    "max_input_characters": 10_000,
                    "max_output_tokens": 1_000,
                    "time_budget_seconds": 10,
                    "request_timeout_seconds": 2,
                    "retry_limit": 0,
                }
            ),
            None,
            "MODEL_CREDENTIAL_MISSING",
        ),
    ],
)
def test_enabled_automatic_generation_requires_valid_provider_configuration(
    settings: Settings, profile: str | None, credential: str | None, code: str
) -> None:
    runtime = settings.model_copy(
        update={
            "automatic_generation_enabled": True,
            "model_provider_profile_json": profile,
            "model_provider_api_key": credential,
        }
    )
    with pytest.raises(ProviderConfigurationError, match=code):
        runtime.validate_security_profile()


@pytest.mark.parametrize(
    ("field", "value"),
    [("maxVisualsPerPage", 7), ("supportedTrendGrains", ["DAY", "WEEK"])],
)
def test_generation_policy_rejects_unsupported_compiler_capabilities(
    settings: Settings, field: str, value: object
) -> None:
    policy = json.loads(settings.generation_policy_json or "{}")
    target = policy["governance"] if field == "maxVisualsPerPage" else policy["generation"]
    target[field] = value
    runtime = settings.model_copy(update={"generation_policy_json": json.dumps(policy)})
    with pytest.raises(ProviderConfigurationError, match="GENERATION_POLICY_INVALID"):
        runtime.generation_policy()
