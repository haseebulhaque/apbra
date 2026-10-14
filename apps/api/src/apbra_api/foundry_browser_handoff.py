"""Explicit owner-private Mac browser to exact owned Docker stdin lease."""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import stat
import subprocess
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, TextIO
from uuid import UUID

from .foundry_memory_handoff import (
    CONTAINER_LISTEN,
    ERROR,
    HELLO,
    MAX_FRAME,
    MODULE,
    Channel,
    HandoffError,
    HandoffPlan,
    exact,
    pairs,
    require,
)
from .foundry_owner_metadata import (
    OwnerMetadataPlan,
    _browser_credential,
    _confirm_private,
    _DeviceCredential,
    _Discard,
    _private_sdk_logging,
    _qualification_terminal,
)

_SCOPE = "https://ai.azure.com/.default"


def _private_report_frame(plan: HandoffPlan, approval: Any, nonce: str) -> tuple[bytes, str]:
    """Dependency-qualified host framing; receiver validates every authority fact."""
    value = approval if type(approval) is dict else approval.model_dump(mode="json")
    require(type(value) is dict and type(value.get("binding")) is dict)
    binding = value["binding"]
    require(
        (binding.get("company_id"), binding.get("tenant_id"), binding.get("client_id"),
         binding.get("authorization_deadline"))
        == (str(plan.company_id), str(plan.tenant_id), str(plan.client_id),
            plan.authorization_deadline)
    )
    account = binding.get("home_account_id")
    require(type(account) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", account))
    require(type(nonce) is str and re.fullmatch(r"[a-f0-9]{64}", nonce))
    raw = json.dumps({"v": 1, "nonce": nonce, "approval": value},
                     separators=(",", ":"), allow_nan=False).encode()
    require(0 < len(raw) <= MAX_FRAME)
    return len(raw).to_bytes(4, "big") + raw, account


class DockerAttach:
    """Finite CLI operations on one explicit owner Unix socket/container/image."""

    def __init__(
        self,
        plan: HandoffPlan,
        *,
        socket_path: Path,
        docker_binary: Path,
        container_id: str,
        image_id: str,
        runtime: bool = False,
        listen_host: str,
        listen_port: int,
        published_port: int,
    ) -> None:
        require(
            re.fullmatch(r"[a-f0-9]{64}", container_id)
            and re.fullmatch(r"sha256:[a-f0-9]{64}", image_id)
        )
        require(socket_path.is_absolute() and docker_binary.is_absolute())
        self.socket = socket_path.resolve(strict=True)
        self.binary = docker_binary.resolve(strict=True)
        self.socket_stat = self.socket.stat()
        require(stat.S_ISSOCK(self.socket_stat.st_mode) and self.socket_stat.st_uid == os.getuid())
        binary_stat = self.binary.stat()
        require(
            stat.S_ISREG(binary_stat.st_mode)
            and not binary_stat.st_mode & 0o022
            and os.access(self.binary, os.X_OK)
        )
        self.binary_stat = binary_stat
        self.container_id = container_id
        self.image_id = image_id
        self.plan = plan
        require(
            listen_host == CONTAINER_LISTEN
            and type(listen_port) is int
            and 1 <= listen_port <= 65535
        )
        require(type(published_port) is int and 1 <= published_port <= 65535)
        self.listener = (listen_host, listen_port)
        self.published_port = published_port
        self.runtime = runtime
        self.process: subprocess.Popen[bytes] | None = None
        self.identity: dict[str, Any] | None = None
        self.engine: str | None = None
        self.command = [str(self.binary), "--host", "unix://" + str(self.socket)]
        self.environment = {"PATH": str(self.binary.parent)}

    def _command(self, args: list[str]) -> bytes:
        require(time.time() < self.plan.authorization_deadline)
        result = subprocess.run(  # noqa: S603 -- qualified absolute binary, fixed operations, no shell
            self.command + args,
            env=self.environment,
            capture_output=True,
            timeout=min(30, self.plan.authorization_deadline - time.time()),
            check=False,
        )
        require(result.returncode == 0 and len(result.stdout) <= MAX_FRAME)
        return result.stdout

    def check(self) -> None:
        current = self.socket.stat()
        require(
            (current.st_uid, current.st_dev, current.st_ino)
            == (self.socket_stat.st_uid, self.socket_stat.st_dev, self.socket_stat.st_ino)
        )
        binary = self.binary.stat()
        require(
            all(
                getattr(binary, key) == getattr(self.binary_stat, key)
                for key in (
                    "st_dev",
                    "st_ino",
                    "st_uid",
                    "st_mode",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                )
            )
        )
        # Engine ID and selected container/process fields only; never Config.Env.
        engine = self._command(["info", "--format", "{{.ID}}"]).decode().strip()
        require(engine and (self.engine is None or self.engine == engine))
        self.engine = engine
        template = (
            '{"id":{{json .Id}},"image":{{json .Image}},'
            '"running":{{json .State.Running}},"pid":{{json .State.Pid}},'
            '"started":{{json .State.StartedAt}},"restarts":{{json .RestartCount}},'
            '"tty":{{json .Config.Tty}},"stdin":{{json .Config.OpenStdin}},'
            '"stdin_once":{{json .Config.StdinOnce}},"ports":{{json .HostConfig.PortBindings}},'
            '"path":{{json .Path}},"args":{{json .Args}}}'
        )
        value = json.loads(
            self._command(["inspect", "--format", template, self.container_id]),
            object_pairs_hook=pairs,
        )
        args = [
            "-m",
            MODULE,
            "--company-id",
            str(self.plan.company_id),
            "--tenant-id",
            str(self.plan.tenant_id),
            "--client-id",
            str(self.plan.client_id),
            "--authorization-deadline",
            str(self.plan.authorization_deadline),
        ]
        args += [
            "--listen-host",
            self.listener[0],
            "--listen-port",
            str(self.listener[1]),
            "--published-port",
            str(self.published_port),
        ]
        if self.runtime:
            args.append("--runtime")
        require(
            value["id"] == self.container_id
            and value["image"] == self.image_id
            and value["running"] is True
            and type(value["pid"]) is int
            and value["pid"] > 0
            and value["tty"] is False
            and value["stdin"] is True
            and value["stdin_once"] is True
            and value["ports"]
            == {
                str(self.listener[1]) + "/tcp": [
                    {"HostIp": "127.0.0.1", "HostPort": str(self.published_port)}
                ]
            }
            and value["path"] == "/app/.venv/bin/python"
            and value["args"] == args
        )
        require(self.identity is None or self.identity == value)
        self.identity = value
        require(self.process is None or self.process.poll() is None)

    def attach(self) -> None:
        self.check()
        require(self.process is None)
        self.process = subprocess.Popen(  # noqa: S603 -- fixed attach to exact qualified peer
            self.command + ["attach", "--sig-proxy=false", self.container_id],
            env=self.environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self.check()

    def read(self, size: int, deadline: float) -> bytes:
        require(
            self.process is not None and self.process.stdout is not None and time.time() < deadline
        )
        assert self.process is not None and self.process.stdout is not None
        stream = self.process.stdout
        require(select.select([stream], [], [], min(300, deadline - time.time()))[0])
        return os.read(stream.fileno(), size)

    def write(self, value: bytes) -> None:
        self.check()
        require(
            self.process is not None
            and self.process.stdin is not None
            and len(value) <= MAX_FRAME + 4
        )
        assert self.process is not None and self.process.stdin is not None
        self.process.stdin.write(value)
        self.process.stdin.flush()
        self.check()

    def connected(self, timeout: float) -> bool:
        self.check()
        assert self.process is not None
        assert self.process.stdout is not None
        return not select.select([self.process.stdout], [], [], timeout)[0]

    def close(self) -> None:
        process, self.process = self.process, None
        if process is not None:
            try:
                if process.stdin is not None:
                    process.stdin.close()
            finally:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                finally:
                    if process.stdout is not None:
                        process.stdout.close()


def line(channel: Channel, deadline: float) -> bytes:
    result = bytearray()
    while len(result) < 256:
        value = exact(channel, 1, deadline)
        if value == b"\n":
            return bytes(result)
        result.extend(value)
    raise HandoffError(ERROR)


def run_handoff(
    plan: HandoffPlan,
    peer: Any,
    *,
    credential_factory: Callable[..., _DeviceCredential] | None = None,
    terminal_factory: Callable[..., AbstractContextManager[TextIO]] | None = None,
    confirm: Callable[..., None] | None = None,
    hold: Callable[[], None] | None = None,
    report_approval: Any | None = None,
) -> None:
    """Only independently owner-run private TTY; caller cannot supply persisted bearer."""
    sdk = None
    acquired = None
    record = None
    frame = None
    failed = False
    try:
        with _private_sdk_logging(), redirect_stdout(_Discard()), redirect_stderr(_Discard()):
            plan.validate()
            require(report_approval is not None or getattr(peer, "runtime", False) is False)
            if report_approval is not None:
                require(getattr(peer, "runtime", False) is True)

            def check() -> None:
                require(time.time() < plan.authorization_deadline)
                peer.check()

            terminal_plan = OwnerMetadataPlan(
                tenant_id=str(plan.tenant_id), client_id=str(plan.client_id)
            )
            with (terminal_factory or _qualification_terminal)(terminal_plan) as terminal:
                approval = confirm or _confirm_private
                approval(
                    terminal,
                    terminal_plan,
                    "Approve one temporary memory lease to the exact owned Docker receiver. "
                    + ("No new consent, permissions or token persistence. "
                     "Sign-in itself sends no report request." if report_approval is not None else
                     "No new consent, permissions, token persistence or paid calls."),
                    "CONFIRM PRIVATE MEMORY HANDOFF",
                )
                check()
                peer.attach()
                peer.write(HELLO)
                challenge = json.loads(
                    line(peer, plan.authorization_deadline), object_pairs_hook=pairs
                )
                require(
                    type(challenge) is dict
                    and set(challenge) == {"v", "nonce", "pid"}
                    and type(challenge["v"]) is int
                    and challenge["v"] == 1
                    and type(challenge["pid"]) is int
                    and challenge["pid"] == 1
                    and type(challenge["nonce"]) is str
                    and re.fullmatch(r"[a-f0-9]{64}", challenge["nonce"])
                )
                check()
                if report_approval is not None:
                    approval(
                        terminal,
                        terminal_plan,
                        "Authorize the approved report steps for the selected saved report "
                        "within its explicitly reserved October budget. "
                        "This sign-in sends no report request.",
                        "CONFIRM ONE CASE REPORT",
                    )
                    check()
                    private_frame, expected_account = _private_report_frame(
                        plan, report_approval, challenge["nonce"]
                    )
                    try:
                        peer.write(private_frame)
                    finally:
                        private_frame = b""
                    require(line(peer, plan.authorization_deadline) == b"REPORT_APPROVAL_ACCEPTED")
                    check()
                timeout = min(300, plan.authorization_deadline - time.time())
                require(timeout > 0)
                sdk = (credential_factory or _browser_credential)(
                    tenant_id=str(plan.tenant_id),
                    client_id=str(plan.client_id),
                    authority="login.microsoftonline.com",
                    additionally_allowed_tenants=[],
                    disable_automatic_authentication=True,
                    cache_persistence_options=None,
                    enable_support_logging=False,
                    logging_enable=False,
                    timeout=timeout,
                    connection_timeout=timeout,
                    read_timeout=timeout,
                    retry_total=0,
                )
                check()
                record = sdk.authenticate(scopes=[_SCOPE])
                account = (record.tenant_id, record.client_id, record.home_account_id)
                label = getattr(record, "username", None)
                require(
                    account[:2] == (str(plan.tenant_id), str(plan.client_id))
                    and type(account[2]) is str
                    and re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", account[2])
                    and type(label) is str
                    and 1 <= len(label) <= 255
                    and label.isprintable()
                )
                check()
                if report_approval is not None:
                    require(account[2] == expected_account)
                assert isinstance(label, str)
                approval(
                    terminal,
                    terminal_plan,
                    "Selected existing account: " + label,
                    "CONFIRM ACCOUNT",
                )
                require(account == (record.tenant_id, record.client_id, record.home_account_id))
                check()
                claim = json.dumps(
                    {
                        "v": 1,
                        "nonce": challenge["nonce"],
                        "company": str(plan.company_id),
                        "tenant": str(plan.tenant_id),
                        "client": str(plan.client_id),
                        "deadline": plan.authorization_deadline,
                        "account": account[2],
                    },
                    separators=(",", ":"),
                ).encode()
                require(len(claim) <= 2048)
                peer.write(len(claim).to_bytes(4, "big") + claim)
                del claim
                require(line(peer, plan.authorization_deadline) == b"ACCOUNT_ACCEPTED")
                check()
                require(account == (record.tenant_id, record.client_id, record.home_account_id))
                acquired = sdk.get_token(_SCOPE)
                require(account == (record.tenant_id, record.client_id, record.home_account_id))
                check()
                require(
                    time.time() < plan.authorization_deadline
                    and type(acquired.expires_on) is int
                    and time.time() < acquired.expires_on
                    and type(acquired.token) is str
                    and 0 < len(acquired.token) <= MAX_FRAME // 2
                    and acquired.token.isascii()
                    and all(33 <= ord(c) <= 126 for c in acquired.token)
                )
                sdk.close()
                sdk = None
                check()
                frame = json.dumps(
                    {
                        "v": 1,
                        "nonce": challenge["nonce"],
                        "company": str(plan.company_id),
                        "tenant": str(plan.tenant_id),
                        "client": str(plan.client_id),
                        "deadline": plan.authorization_deadline,
                        "account": account[2],
                        "token": acquired.token,
                        "expires": acquired.expires_on,
                    },
                    separators=(",", ":"),
                ).encode()
                require(len(frame) <= MAX_FRAME)
                peer.write(len(frame).to_bytes(4, "big") + frame)
                frame = acquired = record = None
                del account, label, challenge
                check()
                require(
                    line(peer, plan.authorization_deadline) == b"HANDOFF_READY_INVOCATION_GATED"
                )
                terminal.write(
                    "Company-bound memory receiver ready; "
                    "paid invocation remains separately gated. "
                    "Stop with Ctrl+C.\n"
                )
                terminal.flush()
                if hold is not None:
                    hold()
                else:
                    while time.time() < plan.authorization_deadline:
                        require(peer.connected(0.25))
    except KeyboardInterrupt:
        pass
    except BaseException:
        failed = True
    finally:
        frame = acquired = record = None
        with _private_sdk_logging(), redirect_stdout(_Discard()), redirect_stderr(_Discard()):
            for close in (sdk.close if sdk is not None else None, peer.close):
                if close is not None:
                    try:
                        close()
                    except BaseException:
                        failed = True
    if failed:
        raise HandoffError(ERROR) from None


def main() -> None:
    parser = argparse.ArgumentParser(description="Owner-private Mac-to-Docker memory lease")
    for name in ("company", "tenant", "client"):
        parser.add_argument("--" + name + "-id", required=True, type=UUID)
    parser.add_argument("--authorization-deadline", required=True, type=float)
    parser.add_argument("--socket-path", required=True, type=Path)
    parser.add_argument("--docker-binary", required=True, type=Path)
    parser.add_argument("--container-id", required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--listen-host", required=True, choices=[CONTAINER_LISTEN])
    parser.add_argument("--listen-port", required=True, type=int)
    parser.add_argument("--published-port", required=True, type=int)
    parser.add_argument("--runtime", action="store_true")
    args = vars(parser.parse_args())
    plan = HandoffPlan(
        **{
            key: args.pop(key)
            for key in ("company_id", "tenant_id", "client_id", "authorization_deadline")
        }
    )
    try:
        run_handoff(plan, DockerAttach(plan, **args))
    except BaseException:
        raise SystemExit(ERROR) from None


if __name__ == "__main__":
    main()
