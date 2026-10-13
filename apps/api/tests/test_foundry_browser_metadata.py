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

    def app(**kwargs: Any) -> Any:
        captured.update(kwargs)
        assert kwargs.get("foundry_credentials") is None
        return kwargs

    monkeypatch.setattr(m, "create_app", app)
    return SimpleNamespace(
        profile=configured,
        snapshot=snapshot,
        settings=settings,
        captured=captured,
        plan=m.BrowserMetadataPlan(COMPANY, TENANT, CLIENT, time.time() + 200),
    )


@contextmanager
def terminal(*args: Any) -> Any:
    yield io.StringIO()


def execute(context: Any, sdk: SDK, *, fault: str | None = None) -> None:
    def factory(**kwargs: Any) -> SDK:
        assert kwargs["tenant_id"] == str(TENANT) and kwargs["client_id"] == str(CLIENT)
        assert kwargs["cache_persistence_options"] is None
        assert kwargs["disable_automatic_authentication"] is True
        assert kwargs["additionally_allowed_tenants"] == [] and kwargs["retry_total"] == 0
        assert "prompt_callback" not in kwargs
        return sdk

    def confirmation(*args: Any) -> None:
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
