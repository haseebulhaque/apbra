"""One-shot owner-attached memory lease receiver; no credential discovery."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import secrets
import select
import sys
import threading
import time
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from .foundry_owner_metadata import _Discard, _private_sdk_logging

if TYPE_CHECKING:
    from .config import Settings
    from .tenant_settings import TenantSettingsSnapshot


ERROR = "FOUNDRY_MEMORY_HANDOFF_UNAVAILABLE"


class HandoffError(ValueError):
    """Fixed public error; no private exception is propagated."""


MAX_FRAME = 65536
MODULE = "apbra_api.foundry_memory_handoff"
CONTAINER_LISTEN = "0.0.0.0"  # noqa: S104 -- existing container interface; publication loopback only
HELLO = b"APBRA_MEMORY_HANDOFF_1\n"


@dataclass(frozen=True)
class HandoffPlan:
    company_id: UUID
    tenant_id: UUID
    client_id: UUID
    authorization_deadline: float

    def validate(self) -> None:
        require(all(type(v) is UUID for v in (self.company_id, self.tenant_id, self.client_id)))
        require(
            type(self.authorization_deadline) in {int, float}
            and math.isfinite(self.authorization_deadline)
            and self.authorization_deadline > time.time()
        )


def create_app(**kwargs: Any) -> Any:
    from .api import create_app as factory

    return factory(**kwargs)


def require(value: object) -> None:
    if not value:
        raise HandoffError(ERROR)


class Channel(Protocol):
    def read(self, size: int, deadline: float) -> bytes: ...
    def write(self, value: bytes) -> None: ...
    def connected(self, timeout: float) -> bool: ...
    def close(self) -> None: ...


class StdioChannel:
    """Non-TTY PID1 stdin only. Output contains challenge/status, never private data."""

    def __init__(self) -> None:
        require(os.getpid() == 1 and not sys.stdin.isatty() and not sys.stdout.isatty())
        self.input = sys.stdin.buffer
        self.output = sys.stdout.buffer

    def read(self, size: int, deadline: float) -> bytes:
        require(size > 0 and time.time() < deadline)
        require(select.select([self.input], [], [], min(300, deadline - time.time()))[0])
        return os.read(self.input.fileno(), size)

    def write(self, value: bytes) -> None:
        self.output.write(value)
        self.output.flush()

    def connected(self, timeout: float) -> bool:
        # After the one frame, any byte (including a second frame) or EOF revokes.
        return not select.select([self.input], [], [], timeout)[0]

    def close(self) -> None:
        self.input.close()


def exact(channel: Channel, size: int, deadline: float) -> bytes:
    value = bytearray()
    try:
        while len(value) < size:
            part = channel.read(size - len(value), deadline)
            require(type(part) is bytes and 0 < len(part) <= size - len(value))
            value.extend(part)
        require(time.time() < deadline)
        return bytes(value)
    finally:
        value[:] = b"\0" * len(value)


def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        require(key not in value)
        value[key] = item
    return value


@dataclass(frozen=True, repr=False)
class MemoryAccessToken:
    token: str
    expires_on: int


def receive_account(channel: Channel, plan: HandoffPlan, nonce: str) -> str:
    value: Any = None
    try:
        length = int.from_bytes(exact(channel, 4, plan.authorization_deadline), "big")
        require(0 < length <= 2048)
        value = json.loads(
            exact(channel, length, plan.authorization_deadline), object_pairs_hook=pairs
        )
        require(
            type(value) is dict
            and set(value) == {"v", "nonce", "company", "tenant", "client", "deadline", "account"}
        )
        require(type(value["v"]) is int and value["v"] == 1 and value["nonce"] == nonce)
        require(all(type(value[k]) is str for k in ("company", "tenant", "client", "account")))
        require(
            (value["company"], value["tenant"], value["client"])
            == tuple(str(v) for v in (plan.company_id, plan.tenant_id, plan.client_id))
        )
        require(
            type(value["deadline"]) in {int, float}
            and value["deadline"] == plan.authorization_deadline
        )
        require(re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", value["account"]))
        account: str = value["account"]
        return account
    except BaseException:
        raise HandoffError(ERROR) from None
    finally:
        if isinstance(value, dict):
            value.clear()


def receive(channel: Channel, plan: HandoffPlan, nonce: str) -> tuple[MemoryAccessToken, str]:
    raw = b""
    value: dict[str, Any] = {}
    try:
        length = int.from_bytes(exact(channel, 4, plan.authorization_deadline), "big")
        require(0 < length <= MAX_FRAME)
        raw = exact(channel, length, plan.authorization_deadline)
        value = json.loads(raw, object_pairs_hook=pairs)
        require(
            type(value) is dict
            and set(value)
            == {
                "v",
                "nonce",
                "company",
                "tenant",
                "client",
                "deadline",
                "account",
                "token",
                "expires",
            }
        )
        require(type(value["v"]) is int and value["v"] == 1 and value["nonce"] == nonce)
        require(
            all(type(value[k]) is str for k in ("company", "tenant", "client", "account", "token"))
        )
        require(
            (value["company"], value["tenant"], value["client"])
            == tuple(str(v) for v in (plan.company_id, plan.tenant_id, plan.client_id))
        )
        require(
            type(value["deadline"]) in {int, float}
            and value["deadline"] == plan.authorization_deadline
        )
        require(re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", value["account"]))
        require(
            0 < len(value["token"]) <= MAX_FRAME // 2
            and value["token"].isascii()
            and all(33 <= ord(c) <= 126 for c in value["token"])
        )
        require(
            type(value["expires"]) is int
            and time.time() < min(value["expires"], plan.authorization_deadline)
        )
        return MemoryAccessToken(value["token"], value["expires"]), value["account"]
    except BaseException:
        raise HandoffError(ERROR) from None
    finally:
        raw = b""
        if isinstance(value, dict):
            value.clear()


def _serve(app: Any, listener: tuple[str, int], stopped: threading.Event) -> None:
    import uvicorn

    host, port = listener
    server = uvicorn.Server(
        uvicorn.Config(app, host=host, port=port, workers=1, access_log=False, log_config=None)
    )

    def watch() -> None:
        stopped.wait()
        server.should_exit = True

    threading.Thread(target=watch, daemon=True).start()
    try:
        server.run()
    finally:
        stopped.set()


def run_receiver(
    plan: HandoffPlan,
    channel: Channel,
    *,
    settings: Settings | None = None,
    snapshot_loader: Callable[[], TenantSettingsSnapshot] | None = None,
    serve: Callable[[Any, Settings, threading.Event], None] | None = None,
    runtime: bool = False,
    invocation_gate: Callable[[], bool] | None = None,
    nonce_factory: Callable[[], str] | None = None,
    listener: tuple[str, int] | None = None,
    published_port: int | None = None,
) -> None:
    """Trusted host entrypoint. CLI cannot enable invocation or manufacture attestation."""
    from .config import get_settings
    from .foundry_browser_metadata import BrowserMetadataCredential, _local_address, _snapshot
    from .model_provider import FoundryMemoryTokenCredential, FoundryTokenCredentialProvider
    from .persistence import Database
    from .tenant_settings import validate_qualified_profile

    token = None
    database = None
    stopped = threading.Event()
    watcher = None
    failed = False
    try:
        with _private_sdk_logging(), redirect_stdout(_Discard()), redirect_stderr(_Discard()):
            plan.validate()
            require(type(runtime) is bool)
            settings = settings or get_settings()
            settings.validate_security_profile()
            _, public = _local_address(settings)
            if serve is None:
                require(
                    listener is not None
                    and listener[0] == CONTAINER_LISTEN
                    and type(listener[1]) is int
                    and 1 <= listener[1] <= 65535
                    and type(published_port) is int
                    and public == published_port
                )
            binding = settings.foundry_host_binding() if runtime else None
            if binding is None:
                require(settings.foundry_host_enabled is False and invocation_gate is None)
            else:
                require(
                    (
                        binding.company_id,
                        binding.tenant_id,
                        binding.client_id,
                        binding.authorization_deadline,
                    )
                    == (
                        plan.company_id,
                        plan.tenant_id,
                        plan.client_id,
                        plan.authorization_deadline,
                    )
                )
            if snapshot_loader is None:
                database = Database(settings.database_url)

                def load() -> TenantSettingsSnapshot:
                    assert database is not None and settings is not None
                    return _snapshot(database, settings, plan.company_id)

                snapshot_loader = load
            initial = snapshot_loader()
            profile = initial.settings.provider_profile
            require(
                initial.company_id == plan.company_id
                and initial.secret_reference_id is None
                and profile is not None
            )
            assert profile is not None
            require(profile.protocol == "FOUNDRY_AGENT_RESPONSES")
            validate_qualified_profile(profile, settings.qualified_provider_profiles())
            if binding is not None:
                require(
                    profile == binding.provider_profile
                    and (
                        profile.agent_version is None
                        or profile.agent_version == binding.agent_version
                    )
                )

            def unchanged() -> bool:
                try:
                    fresh = snapshot_loader()
                    return (
                        time.time() < plan.authorization_deadline
                        and fresh.id == initial.id
                        and fresh.digest == initial.digest
                        and fresh.company_id == initial.company_id
                        and fresh.settings.provider_profile == profile
                        and fresh.secret_reference_id is None
                        and (binding is None or settings.foundry_host_binding() == binding)
                    )
                except Exception:
                    return False

            require(unchanged())
            require(exact(channel, len(HELLO), plan.authorization_deadline) == HELLO)
            nonce = (nonce_factory or (lambda: secrets.token_hex(32)))()
            require(type(nonce) is str and re.fullmatch(r"[a-f0-9]{64}", nonce))
            channel.write(
                json.dumps({"v": 1, "nonce": nonce, "pid": 1}, separators=(",", ":")).encode()
                + b"\n"
            )
            confirmed_account = receive_account(channel, plan, nonce)
            require(
                unchanged() and (binding is None or binding.home_account_id == confirmed_account)
            )
            channel.write(b"ACCOUNT_ACCEPTED\n")
            acquired, account = receive(channel, plan, nonce)
            require(account == confirmed_account)
            del confirmed_account
            require(unchanged() and (binding is None or binding.home_account_id == account))
            digest = hashlib.sha256(
                json.dumps(
                    {
                        "company": str(plan.company_id),
                        "settings": str(initial.id),
                        "digest": initial.digest,
                        "nonce": nonce,
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            token = FoundryMemoryTokenCredential(
                acquired,
                authorization_deadline=plan.authorization_deadline,
                enabled=lambda: not stopped.is_set(),
                binding_digest=digest,
            )
            del acquired, account
            credentials = BrowserMetadataCredential(initial, token, unchanged)
            runtime_credentials = None
            if binding is not None:

                def ready() -> bool:
                    def current() -> bool:
                        if not unchanged():
                            stopped.set()
                            if token is not None:
                                token.close()
                            return False
                        return True

                    try:
                        if not current():
                            return False
                        allowed = invocation_gate is not None and invocation_gate() is True
                        return current() and allowed and token is not None and token.ready()
                    except Exception:
                        return False

                runtime_credentials = FoundryTokenCredentialProvider(
                    company_id=plan.company_id,
                    profile=profile,
                    token_credential=token,
                    enabled=ready,
                    knowledge_binding=binding.knowledge_binding,
                    knowledge_scope=binding.knowledge_scope,
                    agent_version=binding.agent_version,
                    qualification=binding.qualification,
                )
            app = create_app(
                settings=settings,
                foundry_metadata_credentials=credentials,
                foundry_credentials=runtime_credentials,
            )

            def monitor() -> None:
                try:
                    while not stopped.is_set():
                        if not channel.connected(0.1) or token is None or not token.ready():
                            break
                except BaseException:
                    stopped.set()
                finally:
                    stopped.set()
                    if token is not None:
                        token.close()

            watcher = threading.Thread(target=monitor, daemon=True)
            watcher.start()
            require(not stopped.is_set() and credentials.ready(plan.company_id, profile))
            channel.write(b"HANDOFF_READY_INVOCATION_GATED\n")
            if serve is not None:
                serve(app, settings, stopped)
            else:
                assert listener is not None
                _serve(app, listener, stopped)
    except BaseException:
        failed = True
    finally:
        stopped.set()
        with _private_sdk_logging(), redirect_stdout(_Discard()), redirect_stderr(_Discard()):
            for close in (token.close if token is not None else None, channel.close):
                if close is not None:
                    try:
                        close()
                    except BaseException:
                        failed = True
            # Monitor performs only bounded stdin/lease checks, never a DB read.
            # Keep suppression and DB ownership until that worker actually ends.
            if watcher is not None:
                watcher.join()
            if database is not None:
                try:
                    database.engine.dispose()
                except BaseException:
                    failed = True
    if failed:
        raise HandoffError(ERROR) from None


def main() -> None:
    parser = argparse.ArgumentParser(description="Explicit owned-Docker memory lease receiver")
    parser.add_argument("--company-id", required=True, type=UUID)
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--client-id", required=True, type=UUID)
    parser.add_argument("--authorization-deadline", required=True, type=float)
    parser.add_argument("--listen-host", required=True, choices=[CONTAINER_LISTEN])
    parser.add_argument("--listen-port", required=True, type=int)
    parser.add_argument("--published-port", required=True, type=int)
    parser.add_argument("--runtime", action="store_true")
    args = vars(parser.parse_args())
    runtime = args.pop("runtime")
    listener = (args.pop("listen_host"), args.pop("listen_port"))
    published = args.pop("published_port")
    try:
        run_receiver(
            HandoffPlan(**args),
            StdioChannel(),
            runtime=runtime,
            listener=listener,
            published_port=published,
        )
    except BaseException:
        raise SystemExit(ERROR) from None


if __name__ == "__main__":
    main()
