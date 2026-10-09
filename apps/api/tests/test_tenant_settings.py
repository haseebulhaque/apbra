"""Tenant policy is versioned, typed, permissioned and server-authoritative."""

from __future__ import annotations

import base64
import json
import secrets
from copy import deepcopy
from uuid import UUID

import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

import apbra_api.tenant_settings as tenant_settings_module
from apbra_api.api import create_app
from apbra_api.config import Settings
from apbra_api.domain import Conflict
from apbra_api.persistence import (
    CompanyRow,
    Database,
    ExternalIdentityRow,
    MembershipRow,
    SessionRow,
    TenantSettingsCurrentRow,
    TenantSettingsVersionRow,
)
from apbra_api.tenant_settings import (
    create_private_preview_initial_settings,
    private_preview_onboarding_settings_v1,
)


@pytest.mark.parametrize("role", ["COMPANY_OWNER", "COMPANY_ADMIN", "MEMBER", "EXPERT"])
def test_workspace_branding_projects_only_own_rendering_values_without_writes(
    client: TestClient, database: Database, role: str,
) -> None:
    sign_in(client, "owner")
    before = client.get("/api/tenant-settings").json()
    history = client.get("/api/tenant-settings/history").json()
    member = sign_in(client, "member")
    with database.session() as db:
        row = db.get(MembershipRow, UUID(member["actor"]["membership_id"]))
        assert row is not None
        row.role = role
        db.commit()
    response = client.get("/api/workspace/branding")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "version": before["version"],
        "primary": before["settings"]["generation_policy"]["branding"]["primary"],
        "accent": before["settings"]["generation_policy"]["branding"]["accent"],
    }
    if role in {"MEMBER", "EXPERT"}:
        for path in ("", "/history", "/qualified-profiles"):
            assert client.get("/api/tenant-settings" + path).status_code == 403
        assert client.put("/api/tenant-settings", headers=csrf(member), json={
            "settings": before["settings"], "expected_version": before["version"],
        }).status_code == 403
        assert client.patch(
            "/api/tenant-settings/sections/branding_organisation", headers=csrf(member),
            json={"expected_version": before["version"], "changes": {
                "generation_policy.branding": {
                    **before["settings"]["generation_policy"]["branding"],
                    "primary": "#FF0000",
                },
            }},
        ).status_code == 403
    sign_in(client, "owner")
    assert client.get("/api/tenant-settings").json() == before
    assert client.get("/api/tenant-settings/history").json() == history


@pytest.mark.parametrize(
    "inactive", ["membership", "company", "identity", "selection", "wrong_identity"],
)
def test_workspace_branding_requires_current_active_session_membership(
    client: TestClient, database: Database, inactive: str,
) -> None:
    assert client.get("/api/workspace/branding").status_code == 401
    member = sign_in(client, "member")
    with database.session() as db:
        membership = db.get(MembershipRow, UUID(member["actor"]["membership_id"]))
        assert membership is not None
        membership.role = "EXPERT"  # Expert membership is subject to the same active binding.
        if inactive == "membership":
            membership.active = False
        elif inactive == "company":
            company = db.get(CompanyRow, membership.company_id)
            assert company is not None
            company.active = False
        elif inactive == "identity":
            identity = db.get(ExternalIdentityRow, membership.identity_id)
            assert identity is not None
            identity.active = False
        else:
            session = db.scalar(
                select(SessionRow).where(SessionRow.identity_id == membership.identity_id)
            )
            assert session is not None
            if inactive == "selection":
                session.membership_id = None
            else:
                foreign = db.scalar(
                    select(MembershipRow).where(MembershipRow.company_id != membership.company_id)
                )
                assert foreign is not None
                session.membership_id = foreign.id
        db.commit()
    response = client.get("/api/workspace/branding")
    assert response.status_code == 401
    assert set(response.json()) == {"error"}


def test_workspace_branding_cannot_select_another_company_or_modify_branding(
    client: TestClient,
) -> None:
    owner = sign_in(client, "owner")
    before = client.get("/api/tenant-settings").json()
    foreign = sign_in(client, "foreign")
    assert client.patch(
        "/api/tenant-settings/sections/branding_organisation", headers=csrf(foreign),
        json={"expected_version": 1, "changes": {"generation_policy.branding": {
            **before["settings"]["generation_policy"]["branding"], "primary": "#654321",
        }}},
    ).status_code == 200
    assert client.get("/api/workspace/branding").json()["primary"] == "#654321"
    sign_in(client, "member")
    assert client.get("/api/workspace/branding").json()["primary"] == (
        before["settings"]["generation_policy"]["branding"]["primary"]
    )
    for query in (
        {"company_id": foreign["actor"]["company_id"]}, {"tenant": "other"}, {"fields": "settings"},
    ):
        response = client.get("/api/workspace/branding", params=query)
        assert response.status_code == 422
        assert set(response.json()) == {"error"}
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/api/workspace/branding").status_code == 405
    sign_in(client, "owner")
    assert client.get("/api/tenant-settings").json() == before
    assert owner["actor"]["company_id"] != foreign["actor"]["company_id"]


def test_workspace_branding_follows_only_the_explicitly_selected_owned_membership(
    client: TestClient, database: Database,
) -> None:
    foreign_owner = sign_in(client, "foreign")
    foreign_before = client.get("/api/tenant-settings").json()
    changed = client.patch(
        "/api/tenant-settings/sections/branding_organisation", headers=csrf(foreign_owner),
        json={"expected_version": foreign_before["version"], "changes": {
            "generation_policy.branding": {
                **foreign_before["settings"]["generation_policy"]["branding"],
                "primary": "#654321", "accent": "#ABCDEF",
            },
        }},
    )
    assert changed.status_code == 200
    foreign_branding = client.get("/api/workspace/branding").json()
    member = sign_in(client, "member")
    original_branding = client.get("/api/workspace/branding").json()
    assert original_branding["primary"] != foreign_branding["primary"]
    assert original_branding["accent"] != foreign_branding["accent"]
    original_membership = member["actor"]["membership_id"]
    with database.session() as db:
        foreign = db.scalar(
            select(CompanyRow).where(CompanyRow.id != UUID(member["actor"]["company_id"]))
        )
        assert foreign is not None
        other = MembershipRow(
            company_id=foreign.id, identity_id=UUID(member["actor"]["identity_id"]), role="MEMBER",
        )
        db.add(other)
        db.commit()
        other_membership = str(other.id)
    session = sign_in(client, "member")
    assert session["membership_state"] == "COMPANY_SELECTION_REQUIRED"
    assert client.get("/api/workspace/branding").status_code == 401
    for membership_id in (original_membership, other_membership, original_membership):
        selected = client.post(
            "/api/auth/select-company", headers=csrf(session),
            json={"membership_id": membership_id},
        )
        assert selected.status_code == 200
        state = client.get("/api/auth/session").json()
        assert state["actor"]["membership_id"] == membership_id
        response = client.get("/api/workspace/branding")
        assert response.status_code == 200
        assert set(response.json()) == {"version", "primary", "accent"}
        assert response.json() == (
            original_branding if membership_id == original_membership else foreign_branding
        )


def test_section_update_preserves_unrelated_settings_and_versions(client: TestClient) -> None:
    owner = sign_in(client, "owner")
    before = client.get("/api/tenant-settings").json()
    response = client.patch(
        "/api/tenant-settings/sections/budgets_limits",
        headers=csrf(owner),
        json={
            "expected_version": before["version"],
            "changes": {"invitation_ttl_days": before["settings"]["invitation_ttl_days"] - 1},
        },
    )
    assert response.status_code == 200
    after = response.json()
    assert after["version"] == before["version"] + 1
    assert after["settings"]["invitation_ttl_days"] == before["settings"]["invitation_ttl_days"] - 1
    for key in (
        "provider_profile", "automatic_generation_enabled", "generation_policy", "conventions",
    ):
        assert after["settings"][key] == before["settings"][key]
    history = client.get("/api/tenant-settings/history").json()["items"]
    assert history[0]["changed_keys"] == ["invitation_ttl_days"]


def test_section_update_rejects_cross_section_credential_and_stale_writes(
    client: TestClient,
) -> None:
    owner = sign_in(client, "owner")
    before = client.get("/api/tenant-settings").json()
    version = before["version"]
    route = "/api/tenant-settings/sections/budgets_limits"
    for section, changes in (
        ("budgets_limits", {"automatic_generation_enabled": True}),
        ("budgets_limits", {"credential": "synthetic-must-not-be-accepted"}),
        ("unknown_section", {"invitation_ttl_days": 6}),
    ):
        rejected = client.patch(
            f"/api/tenant-settings/sections/{section}",
            headers=csrf(owner),
            json={"expected_version": version, "changes": changes},
        )
        assert rejected.status_code == 422
        assert "synthetic-must-not-be-accepted" not in rejected.text
        assert client.get("/api/tenant-settings").json()["version"] == version
    assert client.patch(
        route,
        json={"expected_version": version, "changes": {"invitation_ttl_days": 6}},
    ).status_code == 401
    invalid_cross_setting = client.patch(
        route,
        headers=csrf(owner),
        json={"expected_version": version, "changes": {
            "max_clarification_rounds_per_cycle": 11,
        }},
    )
    assert invalid_cross_setting.status_code == 422
    assert client.get("/api/tenant-settings").json()["version"] == version
    saved = client.patch(
        route,
        headers=csrf(owner),
        json={"expected_version": version, "changes": {"invitation_ttl_days": 6}},
    )
    assert saved.status_code == 200
    stale = client.patch(
        route,
        headers=csrf(owner),
        json={"expected_version": version, "changes": {"invitation_ttl_days": 5}},
    )
    assert stale.status_code == 409
    assert client.get("/api/tenant-settings").json()["settings"]["invitation_ttl_days"] == 6


def test_section_update_requires_company_admin_authority(client: TestClient) -> None:
    sign_in(client, "owner")
    before = client.get("/api/tenant-settings").json()
    member = sign_in(client, "member")
    denied = client.patch(
        "/api/tenant-settings/sections/branding_organisation",
        headers=csrf(member),
        json={"expected_version": before["version"], "changes": {
            "generation_policy.branding": before["settings"]["generation_policy"]["branding"],
        }},
    )
    assert denied.status_code == 403
    sign_in(client, "owner")
    assert client.get("/api/tenant-settings").json()["version"] == before["version"]


def test_private_preview_onboarding_template_v1_matches_owner_decision() -> None:
    settings = private_preview_onboarding_settings_v1("Aurora Research")
    assert settings.clarification_enabled is True
    assert (
        settings.max_clarification_rounds_per_cycle,
        settings.max_clarification_rounds_overall,
    ) == (2, 10)
    assert settings.expert_escalation_enabled is False
    assert settings.automatic_generation_enabled is False
    assert settings.provider_profile is None
    assert settings.invitation_ttl_days == 7
    assert settings.upload_policy.model_dump() == {
        "data_extensions": ["CSV", "XLSX"],
        "reference_extensions": ["PNG", "JPG", "JPEG"],
        "max_file_bytes": 5_000_000,
        "max_files_per_selection": 8,
        "max_data_items_per_report": 20,
        "max_reference_items_per_report": 20,
    }
    assert settings.clarification_policy.model_dump() == {
        "max_questions_per_round": 5,
        "max_answer_characters": 2_000,
    }
    assert settings.delivery_guide_policy.model_dump() == {
        "enabled": True,
        "include_handover_instructions": True,
    }
    assert settings.conventions.model_dump() == {
        "report_naming": "",
        "semantic_modelling": "",
        "accessibility": "",
        "terminology": {},
    }
    generation = settings.generation_policy.model_dump(by_alias=True)
    assert generation["organisation"] == {
        "name": "Aurora Research",
        "displayName": "Aurora Research",
        "locale": "en-AU",
        "timezone": "Australia/Sydney",
    }
    assert generation["branding"] == {
        "primary": "#17635E",
        "accent": "#2D7D9A",
        "reportNaming": "Concise business report titles",
        "pageNaming": "Short page names",
        "executiveConvention": "Accessible summaries",
        "themeName": "APBRA Default",
    }
    assert generation["generation"] == {
        "enabled": True,
        "supportedCapabilities": [
            "KPI cards",
            "Bar and column charts",
            "Line charts",
            "Tables",
            "Slicers",
            "Multiple pages",
            "Explicit measures",
        ],
        "supportedTrendGrains": ["DAY", "MONTH", "QUARTER", "YEAR"],
        "validationRequired": True,
        "policy": "Governed candidate generation",
    }
    assert generation["governance"] == {
        "requireKnowledge": True,
        "requireAccessibility": True,
        "requireValidation": True,
        "maxVisualsPerPage": 6,
        "maxPages": 5,
        "humanReviewAtVisuals": 6,
    }
    for invalid in ("", " ", " Aurora Research", "Aurora Research ", "Aurora\x00Research"):
        with pytest.raises(ValueError):
            private_preview_onboarding_settings_v1(invalid)


def test_initial_private_preview_settings_are_versioned_and_never_seeded(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_seed(*args: object, **kwargs: object) -> None:
        raise AssertionError("development seed must not create customer settings")

    monkeypatch.setattr(tenant_settings_module, "seed_settings", forbidden_seed)
    monkeypatch.setenv("APBRA_UPLOAD_POLICY_JSON", "not customer policy")
    monkeypatch.setenv("APBRA_GENERATION_POLICY_JSON", "not customer policy")
    monkeypatch.setenv("APBRA_CLARIFICATION_POLICY_JSON", "not customer policy")
    with database.session() as db:
        creator = db.scalar(
            select(ExternalIdentityRow).where(ExternalIdentityRow.subject == "dev-creator")
        )
        assert creator is not None
        company = CompanyRow(name="Aurora Research")
        db.add(company)
        db.flush()
        membership = MembershipRow(
            company_id=company.id, identity_id=creator.id, role="COMPANY_OWNER"
        )
        db.add(membership)
        db.flush()
        snapshot = create_private_preview_initial_settings(db, company, membership.id)
        assert snapshot.version == 1
        assert snapshot.validation_status == "PASS"
        assert snapshot.secret_reference_id is None
        assert snapshot.settings.provider_profile is None
        assert snapshot.settings.automatic_generation_enabled is False
        assert snapshot.settings.generation_policy.branding.primary == "#17635E"
        row = db.get(TenantSettingsVersionRow, snapshot.id)
        pointer = db.get(TenantSettingsCurrentRow, company.id)
        assert row is not None and pointer is not None
        assert row.created_by_membership_id == membership.id
        assert pointer.version_id == snapshot.id and pointer.version == 1
        with pytest.raises(Conflict):
            create_private_preview_initial_settings(db, company, membership.id)


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
    assert payload["validation_status"] == "PASS"
    assert payload["applicability"] == "COMPANY_NEW_OR_REVALIDATED_OPERATIONS"
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
    assert client.get("/api/tenant-settings/qualified-profiles").status_code == 403
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


def test_server_qualified_catalog_rejects_self_asserted_profile_and_ceiling(
    client: TestClient,
) -> None:
    owner = sign_in(client)
    catalogue = client.get("/api/tenant-settings/qualified-profiles")
    assert catalogue.status_code == 200
    qualified = catalogue.json()["items"]
    assert len(qualified) == 1
    assert qualified[0]["profile_id"] == "synthetic-test-profile"
    current = client.get("/api/tenant-settings").json()
    for mutation in (
        {"profile_id": "owner-self-qualified"},
        {"endpoint": "https://other.invalid/v1/chat/completions"},
        {"capabilities": {"structured_output": True, "vision": True}},
        {"max_calls_per_operation": qualified[0]["max_calls_per_operation"] + 1},
    ):
        proposed = deepcopy(current["settings"])
        proposed["provider_profile"] = {**qualified[0], **mutation}
        result = client.put(
            "/api/tenant-settings",
            headers=csrf(owner),
            json={"expected_version": current["version"], "settings": proposed},
        )
        assert result.status_code == 503
        assert client.get("/api/tenant-settings").json()["version"] == 1
    selected = deepcopy(current["settings"])
    selected["provider_profile"] = {**qualified[0], "max_calls_per_operation": 1, "retry_limit": 0}
    accepted = client.put(
        "/api/tenant-settings",
        headers=csrf(owner),
        json={"expected_version": 1, "settings": selected},
    )
    assert accepted.status_code == 200
    assert accepted.json()["version"] == 2


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
    budget_change = deepcopy(activation.json()["settings"])
    budget_change["provider_profile"]["max_input_characters"] = 9_000
    budget_update = protected.put(
        "/api/tenant-settings",
        headers=csrf(session),
        json={"expected_version": 4, "settings": budget_change},
    )
    assert budget_update.status_code == 200
    assert budget_update.json()["credential"]["status"] == "CONFIGURED"
    replacement_profile = {
        **_synthetic_profile(),
        "endpoint": "https://replacement.invalid/v1/chat/completions",
    }
    requalified_runtime = runtime.model_copy(
        update={"qualified_provider_profiles_json": json.dumps([replacement_profile])}
    )
    changed_qualification = TestClient(create_app(settings=requalified_runtime, database=database))
    changed_owner = sign_in(changed_qualification)
    switched = deepcopy(budget_update.json()["settings"])
    switched["automatic_generation_enabled"] = False
    switched["provider_profile"] = replacement_profile
    switched_result = changed_qualification.put(
        "/api/tenant-settings",
        headers=csrf(changed_owner),
        json={"expected_version": 5, "settings": switched},
    )
    assert switched_result.status_code == 200
    assert switched_result.json()["credential"]["status"] == "NOT_CONFIGURED"


def test_no_qualified_catalog_cannot_authorize_tenant_profile(
    settings: Settings, database: Database
) -> None:
    runtime = settings.model_copy(update={"qualified_provider_profiles_json": None})
    isolated = TestClient(create_app(settings=runtime, database=database))
    owner = sign_in(isolated)
    assert isolated.get("/api/tenant-settings/qualified-profiles").json() == {"items": []}
    current = isolated.get("/api/tenant-settings").json()
    proposed = deepcopy(current["settings"])
    proposed["provider_profile"] = _synthetic_profile()
    result = isolated.put(
        "/api/tenant-settings",
        headers=csrf(owner),
        json={"expected_version": 1, "settings": proposed},
    )
    assert result.status_code == 503
    assert isolated.get("/api/tenant-settings").json()["version"] == 1


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
    assert (
        protected.put(
            "/api/tenant-settings",
            headers=csrf(owner),
            json={"expected_version": 4, "settings": disabled},
        ).status_code
        == 200
    )

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
    assert (
        restarted.put(
            "/api/tenant-settings",
            headers=csrf(restarted_owner),
            json={"expected_version": 5, "settings": enabled},
        ).status_code
        == 503
    )
    restored_disabled = restarted.post(
        "/api/tenant-settings/restore",
        headers=csrf(restarted_owner),
        json={"source_version": 3, "expected_version": 5, "confirm_consequences": True},
    )
    assert restored_disabled.status_code == 200
    assert restored_disabled.json()["credential"]["status"] == "NOT_CONFIGURED"
    assert "synthetic-restore-secret" not in restored_disabled.text
    assert "synthetic-restore-secret" not in restarted.get("/api/tenant-settings/history").text
