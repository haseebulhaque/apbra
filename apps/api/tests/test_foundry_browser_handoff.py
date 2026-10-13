"""Fake browser/owned-Docker attachment only; no auth or Docker commands."""

from __future__ import annotations

import io
import json
from typing import Any
from uuid import uuid4

import pytest
from test_foundry_agent_details import CANARY
from test_foundry_browser_metadata import SDK, setup, terminal
from test_foundry_memory_handoff import NONCE, Pipe

from apbra_api import foundry_browser_handoff as m
from apbra_api import foundry_memory_handoff as receiver
from apbra_api.foundry_memory_handoff import HandoffError


class Browser(SDK):
    def get_token(self, *args: str) -> Any:
        result = super().get_token(*args)
        result.expires_on = int(result.expires_on)
        return result


class Peer:
    def __init__(self, fault: str | None = None) -> None:
        self.fault = fault
        self.closed = False
        self.sent = []
        self.checks = 0
        self.stream = io.BytesIO(
            json.dumps(dict(v=1, nonce=NONCE, pid=1)).encode()
            + b"\nACCOUNT_ACCEPTED\nHANDOFF_READY_INVOCATION_GATED\n"
        )

    def check(self) -> None:
        self.checks += 1
        if self.fault == "peer" and self.checks == 2:
            raise RuntimeError(CANARY)

    def attach(self) -> None:
        pass

    def read(self, n: int, deadline: float) -> bytes:
        return self.stream.read(n)

    def write(self, value: bytes) -> None:
        if self.fault == "write":
            raise RuntimeError(CANARY)
        if value != receiver.HELLO and "token" in json.loads(value[4:]):
            self.sent.append(value)

    def close(self) -> None:
        self.closed = True


def execute(c: Any, sdk: Any, p: Any, **kwargs: Any) -> None:
    m.run_handoff(
        c.plan,
        p,
        credential_factory=lambda **kw: sdk,
        terminal_factory=terminal,
        confirm=kwargs.pop("confirm", lambda *args: None),
        hold=lambda: None,
        **kwargs,
    )


def test_browser_callback_closed_before_only_frame(monkeypatch: Any, capsys: Any) -> None:
    c = setup(monkeypatch)
    sdk = Browser()
    p = Peer()
    original = p.write

    def write(value: bytes) -> None:
        if value == receiver.HELLO or "token" not in json.loads(value[4:]):
            return
        assert sdk.closed and sdk.calls == ["authenticate", "get_token", "close"]
        original(value)

    p.write = write
    execute(c, sdk, p)
    assert p.closed and len(p.sent) == 1
    raw = p.sent[0]
    value = json.loads(raw[4:])
    assert int.from_bytes(raw[:4], "big") == len(raw[4:])
    assert value["token"] == CANARY and value["nonce"] == NONCE
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("fault", ["auth", "account", "token", "expiry", "close", "peer", "write"])
def test_failure_cleanup_no_private_output(monkeypatch: Any, capsys: Any, fault: str) -> None:
    c = setup(monkeypatch)
    sdk = Browser(fault)
    p = Peer(fault)
    with pytest.raises(HandoffError, match=m.ERROR) as error:
        execute(c, sdk, p)
    assert p.closed and CANARY not in str(error.value)
    assert CANARY not in capsys.readouterr().out
    if fault != "write":
        assert p.sent == []


def test_account_mutation_after_private_confirmation_prevents_token(monkeypatch: Any) -> None:
    c = setup(monkeypatch)
    sdk = Browser()
    p = Peer()

    def confirm(*args: Any) -> None:
        if args[-1] == "CONFIRM ACCOUNT":
            sdk.record.client_id = str(uuid4())

    with pytest.raises(HandoffError, match=m.ERROR):
        execute(c, sdk, p, confirm=confirm)
    assert sdk.calls == ["authenticate", "close"] and not p.sent and p.closed


def test_peer_drift_after_constructor_prevents_auth(monkeypatch: Any) -> None:
    c = setup(monkeypatch)
    sdk = Browser()
    p = Peer()

    def factory(**kwargs: Any) -> Any:
        p.check = lambda: (_ for _ in ()).throw(RuntimeError(CANARY))
        return sdk

    with pytest.raises(HandoffError, match=m.ERROR):
        m.run_handoff(
            c.plan,
            p,
            credential_factory=factory,
            terminal_factory=terminal,
            confirm=lambda *args: None,
            hold=lambda: None,
        )
    assert sdk.calls == ["close"] and not p.sent and p.closed


@pytest.mark.parametrize(
    "challenge", [b"", b"{}\n", b"x" * 256, b'{"v":1,"v":1}\n', b'{"v":1,"pid":2,"nonce":"a"}\n']
)
def test_bad_receiver_challenge_before_sdk(monkeypatch: Any, challenge: bytes) -> None:
    c = setup(monkeypatch)
    sdk = Browser()
    p = Peer()
    p.stream = io.BytesIO(challenge)
    with pytest.raises(HandoffError, match=m.ERROR):
        execute(c, sdk, p)
    assert not sdk.calls and not p.sent and p.closed


def test_synthetic_parent_receiver_selected_settings_integration(monkeypatch: Any) -> None:
    c = setup(monkeypatch)
    sdk = Browser()
    p = Peer()
    observed = []
    monkeypatch.setattr(receiver, "create_app", lambda **kw: kw)

    def write(value: bytes) -> None:
        if value == receiver.HELLO:
            return
        if "token" not in json.loads(value[4:]):
            p.claim = value
            return
        assert sdk.closed
        child = Pipe(receiver.HELLO + p.claim + value)

        def serve(app: Any, *args: Any) -> None:
            credentials = app["foundry_metadata_credentials"]
            assert credentials.resolve(c.plan.company_id, c.profile).credential().token == CANARY
            assert app["foundry_credentials"] is None
            observed.append(credentials)

        receiver.run_receiver(
            c.plan,
            child,
            settings=c.settings,
            snapshot_loader=lambda: c.snapshot,
            serve=serve,
            nonce_factory=lambda: NONCE,
        )
        assert child.closed and CANARY.encode() not in child.output

    p.write = write
    execute(c, sdk, p)
    assert len(observed) == 1 and not observed[0].ready(c.plan.company_id, c.profile)


@pytest.mark.parametrize(
    "changes",
    [
        dict(id="b" * 64),
        dict(image="sha256:" + "b" * 64),
        dict(running=False),
        dict(pid=0),
        dict(pid=True),
        dict(tty=True),
        dict(stdin=False),
        dict(stdin_once=False),
        dict(ports={}),
        dict(path="/bin/sh"),
        dict(args=[]),
        dict(restarts=1),
        dict(started="changed"),
    ],
)
def test_exact_container_process_qualification_refuses_drift(
    monkeypatch: Any, changes: Any
) -> None:
    from types import SimpleNamespace

    c = setup(monkeypatch)
    peer = object.__new__(m.DockerAttach)
    socket = SimpleNamespace(st_uid=7, st_dev=8, st_ino=9)
    binary = SimpleNamespace(
        st_uid=7, st_dev=1, st_ino=2, st_mode=0o100500, st_size=123, st_mtime_ns=4, st_ctime_ns=5
    )
    peer.socket = SimpleNamespace(stat=lambda: socket)
    peer.socket_stat = socket
    peer.binary = SimpleNamespace(stat=lambda: binary)
    peer.binary_stat = binary
    peer.container_id = "a" * 64
    peer.image_id = "sha256:" + "a" * 64
    peer.plan = c.plan
    peer.listener = (receiver.CONTAINER_LISTEN, 8000)
    peer.published_port = 8001
    peer.runtime = False
    peer.engine = None
    peer.process = None
    expected = {
        "id": peer.container_id,
        "image": peer.image_id,
        "running": True,
        "pid": 123,
        "started": "initial",
        "restarts": 0,
        "tty": False,
        "stdin": True,
        "stdin_once": True,
        "ports": {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8001"}]},
        "path": "/app/.venv/bin/python",
        "args": [
            "-m",
            receiver.MODULE,
            "--company-id",
            str(c.plan.company_id),
            "--tenant-id",
            str(c.plan.tenant_id),
            "--client-id",
            str(c.plan.client_id),
            "--authorization-deadline",
            str(c.plan.authorization_deadline),
            "--listen-host",
            receiver.CONTAINER_LISTEN,
            "--listen-port",
            "8000",
            "--published-port",
            "8001",
        ],
    }
    peer.identity = expected.copy()
    changed = {**expected, **changes}
    commands = []

    def command(args: Any) -> bytes:
        commands.append(args)
        return b"engine" if args[0] == "info" else json.dumps(changed).encode()

    peer._command = command
    with pytest.raises(HandoffError):
        peer.check()
    assert all("Env" not in " ".join(args) for args in commands)


def test_wrong_account_ack_prevents_token_acquisition(monkeypatch: Any) -> None:
    c = setup(monkeypatch)
    sdk = Browser()
    p = Peer()
    p.stream = io.BytesIO(json.dumps(dict(v=1, nonce=NONCE, pid=1)).encode() + b"\nREFUSED\n")
    with pytest.raises(HandoffError):
        execute(c, sdk, p)
    assert sdk.calls == ["authenticate", "close"] and not p.sent and p.closed


def test_host_import_never_imports_server_or_sdk(monkeypatch: Any) -> None:
    import subprocess
    import sys
    from pathlib import Path

    source = Path(m.__file__).resolve().parents[1]
    code = """import sys
sys.path.insert(0,sys.argv[1])
import apbra_api.foundry_browser_handoff
blocked=('azure.identity','apbra_api.api','apbra_api.config',
         'apbra_api.persistence','apbra_api.main')
assert not any(k in sys.modules for k in blocked)
"""
    result = subprocess.run(  # noqa: S603 -- current interpreter, public import sentinel
        [sys.executable, "-I", "-B", "-c", code, str(source)], capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr.decode()
