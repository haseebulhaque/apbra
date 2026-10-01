"""Tenant policy is versioned, typed, permissioned and server-authoritative."""

from __future__ import annotations

import base64
import json
import secrets
from copy import deepcopy

from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from apbra_api.api import create_app
from apbra_api.config import Settings
from apbra_api.persistence import Database, MembershipRow, TenantSettingsVersionRow


def _synthetic_profile() -> dict[str, object]:
    return {
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


def test_seed_is_explicit_idempotent_and_not_overridden_by_runtime_env(
    client: TestClient, database: Database, settings: Settings
) -> None:
    sign_in(client)
    initial = client.get("/api/tenant-settings")
    assert initial.status_code == 200
    payload = initial.json()
    assert payload["version"] == 1
    assert payload["settings"]["max_clarification_rounds_per_cycle"] == 2
    assert payload["settings"]["max_clarification_rounds_overall"] == 10
    assert payload["credential"]["status"] == "NOT_CONFIGURED"
    from apbra_api.bootstrap import bootstrap

    changed_env = settings.model_copy(update={"invitation_ttl_days": 29})
    bootstrap(changed_env, database)
    after = client.get("/api/tenant-settings").json()
    assert after["version"] == 1
    assert after["settings"]["invitation_ttl_days"] == payload["settings"]["invitation_ttl_days"]


def test_tenant_cannot_disable_mandatory_deterministic_validation(client: TestClient) -> None:
    owner = sign_in(client, "owner")
    current = client.get("/api/tenant-settings").json()
    for section, field in (
        ("generation", "validationRequired"),
        ("governance", "requireValidation"),
    ):
        edited = deepcopy(current["settings"])
        edited["generation_policy"][section][field] = False
        response = client.put(
            "/api/tenant-settings",
            headers=csrf(owner),
            json={"expected_version": current["version"], "settings": edited},
        )
        assert response.status_code == 422


def test_update_history_restore_and_optimistic_concurrency(
    client: TestClient, database: Database
) -> None:
    owner = sign_in(client)
    initial = client.get("/api/tenant-settings").json()
    edited = deepcopy(initial["settings"])
    edited["max_clarification_rounds_per_cycle"] = 3
    update = client.put(
        "/api/tenant-settings",
        headers=csrf(owner),
        json={"expected_version": 1, "settings": edited},
    )
    assert update.status_code == 200
    assert update.json()["version"] == 2
    assert update.json()["settings"]["max_clarification_rounds_per_cycle"] == 3
    stale = client.put(
        "/api/tenant-settings",
        headers=csrf(owner),
        json={"expected_version": 1, "settings": edited},
    )
    assert stale.status_code == 409
    history = client.get("/api/tenant-settings/history").json()["items"]
    assert [item["version"] for item in history] == [2, 1]
    assert history[0]["changed_keys"] == ["max_clarification_rounds_per_cycle"]
    assert history[0]["current"] is True
    restore = client.post(
        "/api/tenant-settings/restore",
        headers=csrf(owner),
        json={"source_version": 1, "expected_version": 2, "confirm_consequences": True},
    )
    assert restore.status_code == 200
    assert restore.json()["version"] == 3
    assert restore.json()["settings"]["max_clarification_rounds_per_cycle"] == 2
    with database.session() as db:
        versions = db.scalars(
            select(TenantSettingsVersionRow).where(
                TenantSettingsVersionRow.company_id == owner["actor"]["company_id"]
            )
        ).all()
        assert len(versions) == 3
        assert versions[-1].restored_from_version_id == versions[0].id


def test_role_and_tenant_boundary(client: TestClient, database: Database) -> None:
    owner = sign_in(client, "owner")
    owner_settings = client.get("/api/tenant-settings").json()
    sign_in(client, "member")
    assert client.get("/api/tenant-settings").status_code == 403
    assert client.get("/api/tenant-settings/history").status_code == 403
    assert (
        client.put(
            "/api/tenant-settings",
            headers=csrf(client.get("/api/auth/session").json()),
            json={"expected_version": 1, "settings": owner_settings["settings"]},
        ).status_code
        == 403
    )
    foreign = sign_in(client, "foreign")
    foreign_settings = client.get("/api/tenant-settings").json()
    assert foreign["actor"]["company_id"] != owner["actor"]["company_id"]
    assert foreign_settings["id"] != owner_settings["id"]
    with database.session() as db:
        member = db.scalar(
            select(MembershipRow).where(MembershipRow.id == foreign["actor"]["membership_id"])
        )
        assert member is not None
        member.active = False
    assert client.get("/api/tenant-settings").status_code == 401


def test_enabled_provider_requires_explicit_profile_and_protected_credential(
    client: TestClient, settings: Settings, database: Database
) -> None:
    owner = sign_in(client)
    initial = client.get("/api/tenant-settings").json()
    enabled = deepcopy(initial["settings"])
    enabled["automatic_generation_enabled"] = True
    assert (
        client.put(
            "/api/tenant-settings",
            headers=csrf(owner),
            json={"expected_version": 1, "settings": enabled},
        ).status_code
        == 422
    )
    enabled["provider_profile"] = _synthetic_profile()
    assert (
        client.put(
            "/api/tenant-settings",
            headers=csrf(owner),
            json={"expected_version": 1, "settings": enabled},
        ).status_code
        == 503
    )
    disabled_profile = deepcopy(enabled)
    disabled_profile["automatic_generation_enabled"] = False
    result = client.put(
        "/api/tenant-settings",
        headers=csrf(owner),
        json={"expected_version": 1, "settings": disabled_profile},
    )
    assert result.status_code == 200
    assert result.json()["credential"]["status"] == "NOT_CONFIGURED"
    keyring = {
        "active_version": "synthetic-test-key-v1",
        "keys": {"synthetic-test-key-v1": base64.b64encode(secrets.token_bytes(32)).decode()},
    }
    runtime = settings.model_copy(
        update={"tenant_secret_keyring_json": SecretStr(json.dumps(keyring))}
    )
    protected = TestClient(create_app(settings=runtime, database=database))
    session = sign_in(protected)
    replaced = protected.post(
        "/api/tenant-settings/credential",
        headers=csrf(session),
        json={
            "expected_version": 2,
            "new_credential": "synthetic-test-only-value",
            "confirm_disruption": True,
        },
    )
    assert replaced.status_code == 200
    assert replaced.json()["credential"]["status"] == "CONFIGURED"
    assert "synthetic-test-only-value" not in replaced.text
    enabled_after = deepcopy(replaced.json()["settings"])
    enabled_after["automatic_generation_enabled"] = True
    activation = protected.put(
        "/api/tenant-settings",
        headers=csrf(session),
        json={"expected_version": 3, "settings": enabled_after},
    )
    assert activation.status_code == 200
    assert activation.json()["settings"]["automatic_generation_enabled"] is True
    assert "synthetic-test-only-value" not in activation.text


def test_compiler_capability_rejected_at_tenant_boundary(client: TestClient) -> None:
    owner = sign_in(client)
    current = client.get("/api/tenant-settings").json()
    invalid = deepcopy(current["settings"])
    invalid["generation_policy"]["governance"]["maxVisualsPerPage"] = 7
    response = client.put(
        "/api/tenant-settings",
        headers=csrf(owner),
        json={"expected_version": 1, "settings": invalid},
    )
    assert response.status_code == 422
    assert client.get("/api/tenant-settings").json()["version"] == 1


def test_restore_does_not_reactivate_a_credential_without_its_current_key(
    client: TestClient, settings: Settings, database: Database
) -> None:
    keyring = {
        "active_version": "synthetic-test-key-v1",
        "keys": {"synthetic-test-key-v1": base64.b64encode(secrets.token_bytes(32)).decode()},
    }
    runtime = settings.model_copy(
        update={"tenant_secret_keyring_json": SecretStr(json.dumps(keyring))}
    )
    protected = TestClient(create_app(settings=runtime, database=database))
    owner = sign_in(protected)
    initial = protected.get("/api/tenant-settings").json()
    with_profile = deepcopy(initial["settings"])
    with_profile["provider_profile"] = _synthetic_profile()
    profile = protected.put(
        "/api/tenant-settings",
        headers=csrf(owner),
        json={"expected_version": 1, "settings": with_profile},
    )
    assert profile.status_code == 200
    credential = protected.post(
        "/api/tenant-settings/credential",
        headers=csrf(owner),
        json={
            "expected_version": 2,
            "new_credential": "synthetic-restore-secret",
            "confirm_disruption": True,
        },
    )
    assert credential.status_code == 200
    enabled = deepcopy(credential.json()["settings"])
    enabled["automatic_generation_enabled"] = True
    activation = protected.put(
        "/api/tenant-settings",
        headers=csrf(owner),
        json={"expected_version": 3, "settings": enabled},
    )
    assert activation.status_code == 200
    disabled = deepcopy(activation.json()["settings"])
    disabled["automatic_generation_enabled"] = False
    assert protected.put(
        "/api/tenant-settings",
        headers=csrf(owner),
        json={"expected_version": 4, "settings": disabled},
    ).status_code == 200

    unavailable_keyring = {
        "active_version": "synthetic-test-key-v2",
        "keys": {"synthetic-test-key-v2": base64.b64encode(secrets.token_bytes(32)).decode()},
    }
    restarted = TestClient(
        create_app(
            settings=settings.model_copy(
                update={"tenant_secret_keyring_json": SecretStr(json.dumps(unavailable_keyring))}
            ),
            database=database,
        )
    )
    restarted_owner = sign_in(restarted)
    rejected = restarted.post(
        "/api/tenant-settings/restore",
        headers=csrf(restarted_owner),
        json={"source_version": 4, "expected_version": 5, "confirm_consequences": True},
    )
    assert rejected.status_code == 503
    assert "synthetic-restore-secret" not in rejected.text
    assert restarted.get("/api/tenant-settings").json()["version"] == 5
    assert restarted.put(
        "/api/tenant-settings",
        headers=csrf(restarted_owner),
        json={"expected_version": 5, "settings": enabled},
    ).status_code == 503
    restored_disabled = restarted.post(
        "/api/tenant-settings/restore",
        headers=csrf(restarted_owner),
        json={"source_version": 3, "expected_version": 5, "confirm_consequences": True},
    )
    assert restored_disabled.status_code == 200
    assert restored_disabled.json()["credential"]["status"] == "NOT_CONFIGURED"
    assert "synthetic-restore-secret" not in restored_disabled.text
    assert "synthetic-restore-secret" not in restarted.get(
        "/api/tenant-settings/history"
    ).text
