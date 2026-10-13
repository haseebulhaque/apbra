"""Synthetic receiver protocol and selected-company lease boundaries."""

from __future__ import annotations

import io
import json
import threading
import time
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from test_foundry_agent_details import CANARY
from test_foundry_browser_metadata import setup

from apbra_api import foundry_memory_handoff as m
from apbra_api.foundry_memory_handoff import HandoffError

NONCE = "a" * 64


def frame(plan: Any, **changes: Any) -> bytes:
    value = dict(
        v=1,
        nonce=NONCE,
        company=str(plan.company_id),
        tenant=str(plan.tenant_id),
        client=str(plan.client_id),
        deadline=plan.authorization_deadline,
        account="synthetic.account",
        token=CANARY,
        expires=int(time.time() + 100),
    )
    value.update(changes)
    raw = json.dumps(value).encode()
    return len(raw).to_bytes(4, "big") + raw


def account_frame(plan: Any, **changes: Any) -> bytes:
    token_frame = frame(plan, **changes)
    value = json.loads(token_frame[4:])
    value.pop("token")
    value.pop("expires")
    raw = json.dumps(value).encode()
    return len(raw).to_bytes(4, "big") + raw


class Pipe:
    def __init__(self, value: bytes) -> None:
        self.value = io.BytesIO(value)
        self.output = bytearray()
        self.closed = False
        self.alive = True

    def read(self, n: int, deadline: float) -> bytes:
        return self.value.read(min(n, 7))

    def write(self, value: bytes) -> None:
        self.output.extend(value)

    def connected(self, timeout: float) -> bool:
        time.sleep(min(timeout, 0.01))
        return self.alive

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    "changes",
    [
        dict(v=True),
        dict(v=2),
        dict(nonce="b" * 64),
        dict(company=str(uuid4())),
        dict(tenant=str(uuid4())),
        dict(client=str(uuid4())),
        dict(deadline=0),
        dict(account="\n"),
        dict(token=""),
        {"token": "x\n"},
        {"token": "é"},
        dict(expires=True),
        dict(expires=0),
        dict(expires=1.1),
        dict(extra=CANARY),
    ],
)
def test_invalid_frames_never_construct_lease(monkeypatch: Any, changes: Any) -> None:
    c = setup(monkeypatch)
    p = Pipe(frame(c.plan, **changes))
    with pytest.raises(HandoffError, match=m.ERROR) as error:
        m.receive(p, c.plan, NONCE)
    assert CANARY not in str(error.value)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\0\0",
        b"\0\0\0\0",
        (m.MAX_FRAME + 1).to_bytes(4, "big"),
        b"\0\0\0\x02{}",
        b'\0\0\0\x0d{"v":1,"v":1}',
        b"\0\0\0\x04null",
    ],
)
def test_truncation_duplicate_shape_bounds(monkeypatch: Any, payload: bytes) -> None:
    c = setup(monkeypatch)
    with pytest.raises(HandoffError, match=m.ERROR):
        m.receive(Pipe(payload), c.plan, NONCE)


def test_receiver_lease_current_settings_and_company(monkeypatch: Any, capsys: Any) -> None:
    c = setup(monkeypatch)
    monkeypatch.setattr(m, "create_app", lambda **kw: kw)
    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))
    held = []

    def serve(app: Any, settings: Any, stopped: threading.Event) -> None:
        credential = app["foundry_metadata_credentials"]
        held.append(credential)
        assert app["foundry_credentials"] is None
        assert credential.ready(c.plan.company_id, c.profile)
        assert not credential.ready(uuid4(), c.profile)
        assert credential.resolve(c.plan.company_id, c.profile).credential().token == CANARY
        c.snapshot = replace(c.snapshot, id=uuid4())
        assert not credential.ready(c.plan.company_id, c.profile)
        assert stopped.wait(1)
        assert not credential.ready(c.plan.company_id, c.profile)

    m.run_receiver(
        c.plan,
        p,
        settings=c.settings,
        snapshot_loader=lambda: c.snapshot,
        serve=serve,
        nonce_factory=lambda: NONCE,
    )
    assert p.closed and held and not held[0].ready(c.plan.company_id, c.profile)
    assert CANARY.encode() not in p.output
    assert capsys.readouterr().out == ""


def test_disconnect_revokes_and_stops(monkeypatch: Any) -> None:
    c = setup(monkeypatch)
    monkeypatch.setattr(m, "create_app", lambda **kw: kw)
    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))

    def serve(app: Any, settings: Any, stopped: threading.Event) -> None:
        p.alive = False
        assert stopped.wait(1)
        assert not app["foundry_metadata_credentials"].ready(c.plan.company_id, c.profile)

    m.run_receiver(
        c.plan,
        p,
        settings=c.settings,
        snapshot_loader=lambda: c.snapshot,
        serve=serve,
        nonce_factory=lambda: NONCE,
    )
    assert p.closed


def test_cleanup_errors_sanitized_and_all_resources_attempted(
    monkeypatch: Any, capsys: Any
) -> None:
    c = setup(monkeypatch)
    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))

    def broken() -> None:
        p.closed = True
        print(CANARY)
        raise RuntimeError(CANARY)

    p.close = broken
    with pytest.raises(HandoffError, match=m.ERROR):
        m.run_receiver(
            c.plan,
            p,
            settings=c.settings,
            snapshot_loader=lambda: c.snapshot,
            serve=lambda *args: None,
            nonce_factory=lambda: NONCE,
        )
    assert p.closed and CANARY not in capsys.readouterr().out


def test_runtime_attestation_required_before_challenge(monkeypatch: Any) -> None:
    c = setup(monkeypatch)
    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))
    with pytest.raises(HandoffError, match=m.ERROR):
        m.run_receiver(
            c.plan, p, settings=c.settings, snapshot_loader=lambda: c.snapshot, runtime=True
        )
    assert p.closed and p.output == b""


@pytest.mark.parametrize(
    "changes",
    [
        dict(nonce="b" * 64),
        dict(company=str(uuid4())),
        dict(tenant=str(uuid4())),
        dict(client=str(uuid4())),
        dict(account="\n"),
        dict(deadline=0),
    ],
)
def test_account_preflight_refuses_before_bearer(monkeypatch: Any, changes: Any) -> None:
    c = setup(monkeypatch)
    p = Pipe(m.HELLO + account_frame(c.plan, **changes) + frame(c.plan))
    with pytest.raises(HandoffError):
        m.run_receiver(
            c.plan,
            p,
            settings=c.settings,
            snapshot_loader=lambda: c.snapshot,
            serve=lambda *args: None,
            nonce_factory=lambda: NONCE,
        )
    assert b"ACCOUNT_ACCEPTED" not in p.output and b"HANDOFF_READY" not in p.output and p.closed


@pytest.mark.parametrize("gate", [None, lambda: False, lambda: True])
def test_existing_runtime_attestation_and_trusted_gate_only(monkeypatch: Any, gate: Any) -> None:
    from pydantic import SecretStr

    from apbra_api.config import FoundryHostBinding

    c = setup(monkeypatch)
    c.settings.profile = "development"
    binding = FoundryHostBinding(
        company_id=c.plan.company_id,
        tenant_id=c.plan.tenant_id,
        client_id=c.plan.client_id,
        home_account_id="synthetic.account",
        provider_profile=c.profile,
        knowledge_binding="explicit-fixture-knowledge",
        knowledge_scope="TENANT_PRIVATE",
        agent_version="configured-version",
        qualification="LIVE_METADATA_VERIFIED",
        manual_authentication_approved=True,
        authorization_deadline=c.plan.authorization_deadline,
    )
    c.settings.foundry_host_enabled = True
    c.settings.foundry_host_binding_json = SecretStr(binding.model_dump_json())
    monkeypatch.setattr(m, "create_app", lambda **kw: kw)

    def serve(app: Any, *args: Any) -> None:
        assert app["foundry_credentials"].ready(c.plan.company_id, c.profile) is (
            gate is not None and gate()
        )
        assert app["foundry_metadata_credentials"].ready(c.plan.company_id, c.profile)

    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))
    m.run_receiver(
        c.plan,
        p,
        settings=c.settings,
        snapshot_loader=lambda: c.snapshot,
        serve=serve,
        nonce_factory=lambda: NONCE,
        runtime=True,
        invocation_gate=gate,
    )
    assert p.closed


def test_monitor_never_reads_settings_and_cannot_outlive_suppression(
    monkeypatch: Any, capsys: Any
) -> None:
    c = setup(monkeypatch)
    monkeypatch.setattr(m, "create_app", lambda **kw: kw)
    owner = threading.get_ident()
    seen = []
    entered = threading.Event()
    released = threading.Event()
    finished = threading.Event()
    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))

    def load() -> Any:
        seen.append(threading.get_ident())
        assert threading.get_ident() == owner
        return c.snapshot

    def connected(timeout: float) -> bool:
        entered.set()
        assert released.wait(1)
        print(CANARY)
        finished.set()
        return False

    def close() -> None:
        p.closed = True
        released.set()

    p.connected = connected
    p.close = close

    def serve(*args: Any) -> None:
        assert entered.wait(1)

    m.run_receiver(
        c.plan,
        p,
        settings=c.settings,
        snapshot_loader=load,
        serve=serve,
        nonce_factory=lambda: NONCE,
    )
    assert p.closed and finished.is_set() and seen and set(seen) == {owner}
    assert CANARY not in capsys.readouterr().out


def test_docker_server_uses_explicit_internal_listener(monkeypatch: Any) -> None:
    import uvicorn

    captured = {}

    class Server:
        def __init__(self, config: Any) -> None:
            self.should_exit = False

        def run(self) -> None:
            pass

    def config(app: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(uvicorn, "Config", config)
    monkeypatch.setattr(uvicorn, "Server", Server)
    stop = threading.Event()
    m._serve(object(), (m.CONTAINER_LISTEN, 8000), stop)
    assert captured["host"] == m.CONTAINER_LISTEN and captured["port"] == 8000
    assert captured["access_log"] is False and stop.is_set()


def test_runtime_drift_clears_lease_without_metadata_request(monkeypatch: Any) -> None:
    from pydantic import SecretStr
    from apbra_api.config import FoundryHostBinding

    c = setup(monkeypatch)
    c.settings.profile = "development"
    binding = FoundryHostBinding(
        company_id=c.plan.company_id,
        tenant_id=c.plan.tenant_id,
        client_id=c.plan.client_id,
        home_account_id="synthetic.account",
        provider_profile=c.profile,
        knowledge_binding="explicit-fixture-knowledge",
        knowledge_scope="TENANT_PRIVATE",
        agent_version="configured-version",
        qualification="LIVE_METADATA_VERIFIED",
        manual_authentication_approved=True,
        authorization_deadline=c.plan.authorization_deadline,
    )
    c.settings.foundry_host_enabled = True
    c.settings.foundry_host_binding_json = SecretStr(binding.model_dump_json())
    monkeypatch.setattr(m, "create_app", lambda **kw: kw)
    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))

    def serve(app: Any, settings: Any, stopped: threading.Event) -> None:
        runtime = app["foundry_credentials"]
        assert runtime.ready(c.plan.company_id, c.profile)
        c.snapshot = replace(c.snapshot, id=uuid4())
        assert not runtime.ready(c.plan.company_id, c.profile)
        assert stopped.is_set()
        assert not app["foundry_metadata_credentials"]._token.ready()

    m.run_receiver(
        c.plan,
        p,
        settings=c.settings,
        snapshot_loader=lambda: c.snapshot,
        serve=serve,
        nonce_factory=lambda: NONCE,
        runtime=True,
        invocation_gate=lambda: True,
    )
    assert p.closed
