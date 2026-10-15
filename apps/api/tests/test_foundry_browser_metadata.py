"""Offline browser/server seams. No real authentication, DB, network or model."""

from __future__ import annotations

import io
import json
import time
from contextlib import contextmanager
from dataclasses import replace
from threading import Thread
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from test_foundry_agent_details import CANARY, COMPANY, profile, records

from apbra_api import foundry_browser_metadata as m
from apbra_api.config import Settings
from apbra_api.foundry_agent_details import AgentMetadataAccess, agent_details
from apbra_api.model_provider import ProviderConfigurationError
from apbra_api.tenant_settings import (
    TenantSettingsSnapshot,
    private_preview_onboarding_settings_v1,
)

TENANT = UUID("00000000-0000-0000-0000-000000000020")
CLIENT = UUID("00000000-0000-0000-0000-000000000030")


class SDK:
    def __init__(self, fault: str | None = None) -> None:
        self.fault = fault
        self.closed = False
        self.calls: list[str] = []
        self.record = SimpleNamespace(
            tenant_id=str(TENANT),
            client_id=str(CLIENT),
            home_account_id="synthetic.account",
            username="Synthetic Owner",
        )

    def authenticate(self, *, scopes: list[str]) -> Any:
        self.calls.append("authenticate")
        assert scopes == [m._SCOPE]
        if self.fault == "auth":
            raise RuntimeError(CANARY)
        if self.fault == "account":
            self.record.tenant_id = str(uuid4())
        return self.record

    def get_token(self, *scopes: str) -> Any:
        self.calls.append("get_token")
        assert scopes == (m._SCOPE,)
        if self.fault == "token":
            raise RuntimeError(CANARY)
        return SimpleNamespace(
            token=CANARY, expires_on=time.time() + (300 if self.fault != "expiry" else -1)
        )

    def close(self) -> None:
        self.calls.append("close")
        self.closed = True
        if self.fault == "close":
            raise RuntimeError(CANARY)


def setup(monkeypatch: Any, *, version: str | None = "configured-version") -> Any:
    configured = profile(agent_version=version)
    policy = private_preview_onboarding_settings_v1("Synthetic Company").model_copy(
        update={"provider_profile": configured}
    )
    snapshot = TenantSettingsSnapshot(uuid4(), COMPANY, 1, policy, "b" * 64, None, "PASS")
    settings = Settings(
        _env_file=None,
        profile="test",
        database_url="sqlite://",
        session_secret=uuid4().hex + uuid4().hex,
        qualified_provider_profiles_json=json.dumps([configured.model_dump()]),
    )
    captured: dict[str, Any] = {}
    context_holder = SimpleNamespace(runtime=False)

    def app(**kwargs: Any) -> Any:
        captured.update(kwargs)
        if not getattr(context_holder, "runtime", False):
            assert kwargs.get("foundry_credentials") is None
        return kwargs

    monkeypatch.setattr(m, "create_app", app)
    return SimpleNamespace(
        profile=configured,
        snapshot=snapshot,
        settings=settings,
        captured=captured,
        holder=context_holder,
        plan=m.BrowserMetadataPlan(COMPANY, TENANT, CLIENT, time.time() + 200),
    )


@contextmanager
def terminal(*args: Any) -> Any:
    yield io.StringIO()


def execute(context: Any, sdk: SDK, *, fault: str | None = None) -> None:
    def factory(**kwargs: Any) -> SDK:
        if fault == "construction-drift":
            context.snapshot = replace(context.snapshot, id=uuid4())
        assert kwargs["tenant_id"] == str(TENANT) and kwargs["client_id"] == str(CLIENT)
        assert kwargs["cache_persistence_options"] is None
        assert kwargs["disable_automatic_authentication"] is True
        assert kwargs["additionally_allowed_tenants"] == [] and kwargs["retry_total"] == 0
        assert "prompt_callback" not in kwargs
        return sdk

    def confirmation(*args: Any) -> None:
        if fault == "account-confirm-drift" and args[-1] == "CONFIRM ACCOUNT":
            sdk.record.home_account_id = "changed.account"
        if fault == "confirm" and args[-1] == "CONFIRM ACCOUNT":
            raise RuntimeError(CANARY)
        if fault == "settings-drift" and args[-1] == "CONFIRM ACCOUNT":
            context.snapshot = replace(context.snapshot, id=uuid4())

    def observe(company: UUID, configured: Any, credential: Any) -> dict[str, Any]:
        assert sdk.closed  # No live SDK/refresh while serving or resource GETs.
        assert credential.ready(company, configured)
        if fault == "observe":
            raise RuntimeError(CANARY)
        seen: list[str] = []
        values = records()

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.headers["authorization"] == "Bearer " + CANARY
            seen.append(str(request.url))
            return httpx.Response(200, json=values[len(seen) - 1])

        result = agent_details(
            company, configured, credential, transport=httpx.MockTransport(handler)
        )
        assert len(seen) == (1 if configured.agent_version is None else 2)
        assert all("/agents/configured" in url for url in seen)
        return result

    def serve(app: Any, settings: Any) -> None:
        credentials = app["foundry_metadata_credentials"]
        runtime_credentials = app.get("foundry_credentials")
        if getattr(context, "runtime", False):
            assert runtime_credentials is not None
            assert runtime_credentials.ready(COMPANY, context.profile) is getattr(
                context, "gate", False
            )
            if getattr(context, "gate", False):
                access = runtime_credentials.resolve(COMPANY, context.profile)
                assert access.qualification == "LIVE_METADATA_VERIFIED"
                assert access.knowledge_binding == "explicit-fixture-knowledge"
                assert access.credential().token == CANARY
            else:
                with pytest.raises(ProviderConfigurationError):
                    runtime_credentials.resolve(COMPANY, context.profile)
            assert not runtime_credentials.ready(uuid4(), context.profile)
        assert credentials.ready(COMPANY, context.profile)
        access = credentials.resolve(COMPANY, context.profile)
        assert type(access) is AgentMetadataAccess
        assert not hasattr(access, "qualification") and not hasattr(access, "knowledge_binding")
        assert CANARY not in repr(access)
        # Metadata worker must acquire its quiet-call lock during serving.
        result: list[bool] = []
        worker = Thread(target=lambda: result.append(m._quiet_call(lambda: True)))
        worker.start()
        worker.join(timeout=1)
        assert result == [True]
        assert not credentials.ready(uuid4(), context.profile)
        assert credentials.ready(COMPANY, context.profile)  # Foreign request cannot revoke lease.
        if fault == "serve":
            raise RuntimeError(CANARY)
        if fault == "live-drift":
            context.snapshot = replace(context.snapshot, digest="changed")
            assert not credentials.ready(COMPANY, context.profile)
            with pytest.raises(ProviderConfigurationError):
                access.credential()

    m.run_browser_metadata(
        context.plan,
        settings=context.settings,
        credential_factory=factory,
        snapshot_loader=lambda: context.snapshot,
        terminal_factory=terminal,
        confirm=confirmation,
        observe=observe,
        serve=serve,
        runtime=getattr(context, "runtime", False),
        invocation_gate=(lambda: getattr(context, "gate", False))
        if getattr(context, "runtime", False)
        else None,
    )


@pytest.mark.parametrize("version", ["configured-version", None])
def test_browser_metadata_server_separate_from_paid_credentials_and_cleans_lease(
    monkeypatch: Any,
    capsys: Any,
    version: str | None,
) -> None:
    context = setup(monkeypatch, version=version)
    sdk = SDK()
    execute(context, sdk)
    assert sdk.calls == ["authenticate", "get_token", "close"]
    credentials = context.captured["foundry_metadata_credentials"]
    assert not credentials.ready(COMPANY, context.profile)
    output = capsys.readouterr()
    assert CANARY not in output.out + output.err


@pytest.mark.parametrize(
    "fault",
    [
        "auth",
        "account",
        "token",
        "expiry",
        "close",
        "confirm",
        "settings-drift",
        "construction-drift",
        "account-confirm-drift",
        "observe",
        "serve",
    ],
)
def test_private_faults_close_before_any_unauthorized_server_or_secret_output(
    monkeypatch: Any,
    capsys: Any,
    fault: str,
) -> None:
    context = setup(monkeypatch)
    sdk = SDK(fault)
    with pytest.raises(ProviderConfigurationError, match=m._ERROR) as error:
        execute(context, sdk, fault=fault)
    assert sdk.closed
    if fault == "construction-drift":
        assert sdk.calls == ["close"]
    if fault == "account-confirm-drift":
        assert sdk.calls == ["authenticate", "close"]
    assert CANARY not in str(error.value) + capsys.readouterr().out
    if fault not in {"serve"}:
        assert not context.captured


def test_saved_version_change_revokes_served_lease(monkeypatch: Any) -> None:
    context = setup(monkeypatch)
    execute(context, SDK(), fault="live-drift")


@pytest.mark.parametrize(
    "mutation",
    [
        "expired",
        "nan",
        "host-enabled",
        "nonlocal",
        "foreign-company",
        "secret-reference",
        "no-profile",
    ],
)
def test_binding_failure_never_constructs_browser(monkeypatch: Any, mutation: str) -> None:
    context = setup(monkeypatch)
    if mutation == "expired":
        context.plan = replace(context.plan, authorization_deadline=0)
    if mutation == "nan":
        context.plan = replace(context.plan, authorization_deadline=float("nan"))
    if mutation == "host-enabled":
        context.settings.foundry_host_enabled = True
    if mutation == "nonlocal":
        context.settings.api_origin = "https://provider.invalid"
    if mutation == "foreign-company":
        context.snapshot = replace(context.snapshot, company_id=uuid4())
    if mutation == "secret-reference":
        context.snapshot = replace(context.snapshot, secret_reference_id=uuid4())
    if mutation == "no-profile":
        context.snapshot.settings.provider_profile = None
    sdk = SDK()
    with pytest.raises(ProviderConfigurationError, match=m._ERROR):
        execute(context, sdk)
    assert sdk.calls == []
    assert not context.captured


def test_integration_admin_uses_separate_metadata_dependency_with_role_and_target_controls(
    settings: Settings,
    database: Any,
    monkeypatch: Any,
) -> None:
    from conftest import sign_in
    from fastapi.testclient import TestClient

    from apbra_api import api as api_module

    metadata = object()
    calls: list[Any] = []

    def observe(company: UUID, configured: Any, credentials: Any) -> dict[str, Any]:
        assert credentials is metadata
        calls.append((company, configured))
        return {"status": "METADATA_OBSERVED_ONLY", "warnings": []}

    monkeypatch.setattr(api_module, "agent_details", observe)
    app = api_module.create_app(
        settings=settings, database=database, foundry_metadata_credentials=metadata
    )
    with TestClient(app) as client:
        sign_in(client, "owner")
        saved = client.get("/api/tenant-settings").json()
        result = client.get("/api/tenant-settings/agent-details")
        assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
        assert result.json()["settings_version"] == saved["version"]
        assert len(calls) == 1
        assert (
            client.get(
                "/api/tenant-settings/agent-details?endpoint=https://foreign.invalid"
            ).status_code
            == 422
        )
        sign_in(client, "member")
        assert client.get("/api/tenant-settings/agent-details").status_code == 403
        assert len(calls) == 1


@pytest.mark.parametrize("gate", [False, True])
def test_reusable_browser_runtime_retains_attestation_and_default_invocation_gate(
    monkeypatch: Any, gate: bool
) -> None:
    from pydantic import SecretStr

    from apbra_api.config import FoundryHostBinding

    context = setup(monkeypatch)
    context.runtime = True
    context.holder.runtime = True
    context.gate = gate
    context.settings.profile = "development"
    binding = FoundryHostBinding(
        company_id=COMPANY,
        tenant_id=TENANT,
        client_id=CLIENT,
        home_account_id="synthetic.account",
        provider_profile=context.profile,
        knowledge_binding="explicit-fixture-knowledge",
        knowledge_scope="TENANT_PRIVATE",
        agent_version="configured-version",
        qualification="LIVE_METADATA_VERIFIED",
        manual_authentication_approved=True,
        authorization_deadline=context.plan.authorization_deadline,
    )
    context.settings.foundry_host_enabled = True
    context.settings.foundry_host_binding_json = SecretStr(binding.model_dump_json())
    execute(context, SDK())
    assert not context.captured["foundry_credentials"].ready(COMPANY, context.profile)


@pytest.mark.parametrize(
    "mutation", ["account", "profile", "deadline", "company", "withdrawn", "absent"]
)
def test_runtime_private_attestation_mismatch_cannot_acquire_or_enable(
    monkeypatch: Any, mutation: str
) -> None:
    from pydantic import SecretStr

    from apbra_api.config import FoundryHostBinding

    context = setup(monkeypatch)
    context.runtime = True
    context.holder.runtime = True
    context.gate = True
    context.settings.profile = "development"
    context.settings.foundry_host_enabled = True
    fields = dict(
        company_id=COMPANY,
        tenant_id=TENANT,
        client_id=CLIENT,
        home_account_id="synthetic.account",
        provider_profile=context.profile,
        knowledge_binding="explicit-fixture-knowledge",
        knowledge_scope="TENANT_PRIVATE",
        agent_version="configured-version",
        qualification="LIVE_METADATA_VERIFIED",
        manual_authentication_approved=True,
        authorization_deadline=context.plan.authorization_deadline,
    )
    if mutation == "account":
        fields["home_account_id"] = "wrong.account"
    if mutation == "profile":
        fields["provider_profile"] = context.profile.model_copy(
            update={"configuration_id": "other"}
        )
    if mutation == "deadline":
        fields["authorization_deadline"] += 1
    if mutation == "company":
        fields["company_id"] = uuid4()
    if mutation == "withdrawn":
        fields["manual_authentication_approved"] = False
    if mutation != "absent":
        context.settings.foundry_host_binding_json = SecretStr(
            FoundryHostBinding(**fields).model_dump_json()
        )
    sdk = SDK()
    with pytest.raises(ProviderConfigurationError, match=m._ERROR):
        execute(context, sdk)
    assert "get_token" not in sdk.calls and not context.captured


@pytest.mark.parametrize("fault", ["snapshot", "dispose"])
def test_private_database_failures_are_quiet_and_all_credentials_cleaned(
    monkeypatch: Any,
    capsys: Any,
    fault: str,
) -> None:
    context = setup(monkeypatch)
    sdk = SDK()
    closed: list[bool] = []

    def dispose() -> None:
        closed.append(True)
        print(CANARY)
        if fault == "dispose":
            raise RuntimeError(CANARY)

    def load(*args: Any) -> TenantSettingsSnapshot:
        print(CANARY)
        if fault == "snapshot":
            raise RuntimeError(CANARY)
        return context.snapshot

    monkeypatch.setattr(
        m, "Database", lambda *args: SimpleNamespace(engine=SimpleNamespace(dispose=dispose))
    )
    monkeypatch.setattr(m, "_snapshot", load)
    with pytest.raises(ProviderConfigurationError, match=m._ERROR) as error:
        m.run_browser_metadata(
            context.plan,
            settings=context.settings,
            credential_factory=lambda **kwargs: sdk,
            terminal_factory=terminal,
            confirm=lambda *args: None,
            observe=lambda *args: {"status": "METADATA_OBSERVED_ONLY"},
            serve=lambda *args: None,
        )
    assert closed == [True]
    if fault == "dispose":
        assert sdk.closed
        assert not context.captured["foundry_metadata_credentials"].ready(COMPANY, context.profile)
    else:
        assert sdk.calls == []
    output = capsys.readouterr()
    assert CANARY not in output.out + output.err + str(error.value)


def _settings_credential(database: Any, company: UUID) -> Any:
    from apbra_api.model_provider import FoundryMemoryTokenCredential
    from apbra_api.tenant_settings import current_settings

    with database.session() as db:
        snapshot = current_settings(db, company)

    def unchanged() -> bool:
        with database.session() as db:
            return current_settings(db, company).id == snapshot.id

    token = FoundryMemoryTokenCredential(
        SimpleNamespace(token=CANARY, expires_on=time.time() + 300),
        authorization_deadline=time.time() + 300, enabled=lambda: True, binding_digest="a" * 64,
    )
    identity = m.BrowserMetadataCredential(snapshot, token, unchanged)
    return identity, token


@pytest.fixture
def settings_identity(settings: Settings, database: Any) -> Any:
    from conftest import csrf, sign_in
    from fastapi.testclient import TestClient

    from apbra_api.api import create_app

    configured = profile(agent_version=None)
    runtime = settings.model_copy(update={
        "qualified_provider_profiles_json": json.dumps([configured.model_dump()]),
        "test_semantic_simulator_enabled": False,
    })
    client = TestClient(create_app(settings=runtime, database=database))
    owner = sign_in(client, "owner")
    current = client.get("/api/tenant-settings").json()
    policy = {**current["settings"], "provider_profile": configured.model_dump(mode="json"),
              "automatic_generation_enabled": False}
    saved = client.put("/api/tenant-settings", headers=csrf(owner), json={
        "expected_version": current["version"], "settings": policy,
    })
    assert saved.status_code == 200
    company = UUID(owner["actor"]["company_id"])
    identity, token = _settings_credential(database, company)
    private = TestClient(create_app(settings=runtime, database=database,
                                   foundry_metadata_credentials=identity))
    session = sign_in(private, "owner")
    return SimpleNamespace(client=private, session=session, current=saved.json(),
                           identity=identity, token=token, profile=configured,
                           company=company, runtime=runtime, database=database)


@pytest.mark.parametrize("method", ["patch", "put", "restore"])
def test_scoped_identity_can_save_generation_policy_without_granting_invocation(
    settings_identity: Any, method: str, monkeypatch: Any,
) -> None:
    from conftest import csrf

    from apbra_api import api as api_module

    s = settings_identity
    assert s.identity.ready(s.company, s.profile)
    resolved: list[Any] = []

    def forbidden(*args: Any) -> Any:
        resolved.append(args)
        raise AssertionError("Settings readiness cannot export a bearer or dispatch")

    monkeypatch.setattr(s.identity, "resolve", forbidden)
    before = s.current
    if method == "restore":
        # Retain a real enabled historical version, disable, then attach a fresh
        # identity to that disabled snapshot before exercising restore.
        enabled = s.client.patch("/api/tenant-settings/sections/ai_models",
            headers=csrf(s.session), json={"expected_version": before["version"],
            "changes": {"automatic_generation_enabled": True}})
        assert enabled.status_code == 200
        disabled = s.client.patch("/api/tenant-settings/sections/ai_models",
            headers=csrf(s.session), json={"expected_version": enabled.json()["version"],
            "changes": {"automatic_generation_enabled": False}})
        assert disabled.status_code == 200
        identity, token = _settings_credential(s.database, s.company)
        monkeypatch.setattr(identity, "resolve", forbidden)
        from conftest import sign_in
        from fastapi.testclient import TestClient
        s.client = TestClient(api_module.create_app(settings=s.runtime, database=s.database,
                                                   foundry_metadata_credentials=identity))
        s.session = sign_in(s.client, "owner")
        before = disabled.json()
        result = s.client.post("/api/tenant-settings/restore", headers=csrf(s.session), json={
            "expected_version": before["version"], "source_version": enabled.json()["version"],
            "confirm_consequences": True})
    elif method == "put":
        result = s.client.put("/api/tenant-settings", headers=csrf(s.session), json={
            "expected_version": before["version"],
            "settings": {**before["settings"], "automatic_generation_enabled": True}})
    else:
        result = s.client.patch("/api/tenant-settings/sections/ai_models",
            headers=csrf(s.session), json={"expected_version": before["version"],
            "changes": {"automatic_generation_enabled": True}})
    assert result.status_code == 200, result.text
    assert result.json()["version"] == before["version"] + 1
    assert result.json()["settings"]["automatic_generation_enabled"] is True
    assert result.json()["credential"]["status"] == "NOT_CONFIGURED"
    created = s.client.post("/api/cases", headers={**csrf(s.session),
        "Idempotency-Key": str(uuid4())}, json={"request_text": "Synthetic report request."})
    assert created.status_code == 201
    case = created.json()["case"]
    monkeypatch.setattr(api_module, "FoundryAgentResponsesProvider", forbidden)
    denied = s.client.post(f"/api/cases/{case['id']}/interpretations",
        headers=csrf(s.session), json={"expected_context_version": 1})
    assert denied.status_code == 503  # Enabled policy still grants no paid capability.
    assert resolved == []
    if method == "restore":
        assert not identity.ready(s.company, s.profile)
        assert not token.ready()
    assert not s.identity.ready(s.company, s.profile)  # Saved drift still revokes.
    assert not s.token.ready()
    assert CANARY not in result.text


@pytest.mark.parametrize("fault,expected", [
    ("closed", 503), ("foreign-company", 503), ("changed-profile", 503),
    ("unqualified", 503), ("drift", 503), ("ready-error", 503),
    ("missing", 503), ("truthy", 503), ("member", 403), ("csrf", 401), ("stale", 409),
])
def test_settings_identity_preserves_security_and_saved_version_guards(
    settings_identity: Any, fault: str, expected: int, monkeypatch: Any,
) -> None:
    from conftest import csrf, sign_in
    from fastapi.testclient import TestClient

    from apbra_api.api import create_app

    s = settings_identity
    body = {"expected_version": s.current["version"],
            "changes": {"automatic_generation_enabled": True}}
    if fault == "closed":
        s.token.close()
    if fault == "foreign-company":
        s.identity._snapshot = replace(s.identity._snapshot, company_id=uuid4())
    if fault == "changed-profile":
        body["changes"]["provider_profile"] = s.profile.model_copy(
            update={"configuration_id": "different-config"}).model_dump(mode="json")
    if fault == "unqualified":
        s.client = TestClient(create_app(settings=s.runtime.model_copy(
            update={"qualified_provider_profiles_json": "[]"}), database=s.database,
            foundry_metadata_credentials=s.identity))
        s.session = sign_in(s.client, "owner")
    if fault == "drift":
        changed = s.client.patch("/api/tenant-settings/sections/ai_models",
            headers=csrf(s.session), json={"expected_version": s.current["version"],
            "changes": {"expert_escalation_enabled": not s.current["settings"][
                "expert_escalation_enabled"]}})
        assert changed.status_code == 200
        body["expected_version"] = changed.json()["version"]
    if fault == "ready-error":
        def broken(*args: Any) -> bool:
            raise RuntimeError(CANARY)
        monkeypatch.setattr(s.identity, "ready", broken)
    if fault == "truthy":
        monkeypatch.setattr(s.identity, "ready", lambda *args: 1)
    if fault == "missing":
        s.client = TestClient(create_app(settings=s.runtime, database=s.database))
        s.session = sign_in(s.client, "owner")
    if fault == "member":
        s.session = sign_in(s.client, "member")
    if fault == "stale":
        body["expected_version"] -= 1
    result = s.client.patch("/api/tenant-settings/sections/ai_models",
        headers={} if fault == "csrf" else csrf(s.session), json=body)
    assert result.status_code == expected, result.text
    assert CANARY not in result.text
    sign_in(s.client, "owner")
    saved = s.client.get("/api/tenant-settings").json()
    assert saved["version"] == s.current["version"] + (fault == "drift")
    assert saved["settings"]["automatic_generation_enabled"] is False
    s.token.close()


def test_scoped_identity_settings_adapter_never_delegates_bearer_access() -> None:
    from apbra_api.api import _SettingsIdentityReadiness
    from apbra_api.domain import ConfigurationUnavailable

    calls = []
    identity = SimpleNamespace(ready=lambda *args: True,
                               resolve=lambda *args: calls.append(args))
    adapter = _SettingsIdentityReadiness(identity)
    assert adapter.ready(COMPANY, profile()) is True
    with pytest.raises(ConfigurationUnavailable):
        adapter.resolve(COMPANY, profile())
    assert calls == []
