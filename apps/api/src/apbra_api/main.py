"""Default startup never discovers or authenticates Azure credentials."""

import argparse
import json
import logging
import math
import os
import re
import select
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from threading import RLock, Timer
from typing import Any, Protocol, TextIO
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI

from .api import create_app
from .config import FoundryHostBinding, FoundryQualificationBinding, Settings, get_settings
from .foundry_metadata_projection import (
    _agent_observation as _agent_observation,
)
from .foundry_metadata_projection import (
    _instruction_bytes as _instruction_bytes,
)
from .foundry_metadata_projection import (
    _knowledge_observation as _knowledge_observation,
)
from .foundry_metadata_projection import (
    _public_identifier as _public_identifier,
)
from .model_provider import (
    FoundryAccessToken,
    FoundryMemoryTokenCredential,
    FoundryTokenCredentialProvider,
    ProviderConfigurationError,
)

_SCOPE = "https://ai.azure.com/.default"


class _AuthenticationRecord(Protocol):
    @property
    def tenant_id(self) -> str: ...
    @property
    def client_id(self) -> str: ...
    @property
    def home_account_id(self) -> str: ...


class _DeviceCredential(Protocol):
    def authenticate(self, *, scopes: list[str]) -> _AuthenticationRecord: ...
    def get_token(self, *scopes: str) -> FoundryAccessToken: ...
    def close(self) -> None: ...


def _device_credential(**kwargs: Any) -> _DeviceCredential:
    # Only the separately approved manual flow reaches this import/construction.
    from azure.identity import DeviceCodeCredential

    return DeviceCodeCredential(**kwargs)


def _authorized(settings: Settings, binding: FoundryHostBinding) -> bool:
    try:
        return settings.foundry_host_binding() == binding
    except Exception:
        return False


def create_runtime_app(
    settings: Settings | None = None, token_credential: FoundryMemoryTokenCredential | None = None
) -> FastAPI:
    settings = settings or get_settings()
    if not settings.foundry_host_enabled:
        if token_credential is not None:
            raise ProviderConfigurationError("FOUNDRY_RUNTIME_IDENTITY_UNAVAILABLE")
        return create_app(settings=settings)
    binding = settings.foundry_host_binding()
    if (
        not isinstance(token_credential, FoundryMemoryTokenCredential)
        or token_credential.binding_digest != binding.binding_digest()
        or not token_credential.ready()
    ):
        raise ProviderConfigurationError("FOUNDRY_RUNTIME_IDENTITY_UNAVAILABLE")
    credential = FoundryTokenCredentialProvider(
        company_id=binding.company_id,
        profile=binding.provider_profile,
        token_credential=token_credential,
        enabled=lambda: _authorized(settings, binding) and token_credential.ready(),
        knowledge_binding=binding.knowledge_binding,
        knowledge_scope=binding.knowledge_scope,
        agent_version=binding.agent_version,
        qualification=binding.qualification,
    )
    return create_app(settings=settings, foundry_credentials=credential)


@contextmanager
def _private_terminal() -> Iterator[TextIO]:
    if not sys.stdin.isatty():
        raise ProviderConfigurationError("FOUNDRY_PRIVATE_TERMINAL_REQUIRED")
    # No challenge is sent to stdout, stderr, application logs or an API.
    with open("/dev/tty", "w", encoding="utf-8") as terminal:
        if not terminal.isatty():
            raise ProviderConfigurationError("FOUNDRY_PRIVATE_TERMINAL_REQUIRED")
        yield terminal


@contextmanager
def _private_sdk_logging() -> Iterator[None]:
    # The explicit CLI has not started an application or server yet. SDK warning
    # messages can contain private authentication data even with HTTP logging off.
    previous = logging.root.manager.disable
    logging.disable(max(previous, logging.CRITICAL))
    try:
        yield
    finally:
        logging.disable(previous)


def _local_address(settings: Settings) -> tuple[str, int]:
    try:
        origin = urlparse(settings.api_origin)
        if (
            origin.scheme != "http"
            or origin.hostname not in {"127.0.0.1", "localhost"}
            or origin.port is None
            or origin.port < 1
            or origin.username is not None
            or origin.password is not None
            or origin.path not in {"", "/"}
            or origin.query
            or origin.fragment
        ):
            raise ValueError("Invalid local origin")
        return origin.hostname, origin.port
    except Exception:
        raise ProviderConfigurationError("FOUNDRY_LOCAL_HOST_REQUIRED") from None


def _serve(application: FastAPI, settings: Settings) -> None:
    import uvicorn

    host, port = _local_address(settings)
    uvicorn.run(
        application,
        host=host,
        port=port,
        workers=1,
        reload=False,
        access_log=False,
        log_config=None,
    )


def run_foundry_device_code(
    settings: Settings | None = None,
    credential_factory: Callable[..., _DeviceCredential] | None = None,
) -> None:
    """Explicit private manual action; offline work does not approve invocation."""
    settings = settings or get_settings()
    binding = settings.foundry_host_binding()
    _local_address(settings)
    snapshot: FoundryMemoryTokenCredential | None = None
    try:
        with _private_terminal() as terminal:
            if not terminal.isatty() or not _authorized(settings, binding):
                raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")
            remaining = int(binding.authorization_deadline - time.time())
            if remaining < 1:
                raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")

            def private_prompt(uri: str, code: str, expires: datetime) -> None:
                if (
                    not terminal.isatty()
                    or not _authorized(settings, binding)
                    or expires.timestamp() <= time.time()
                ):
                    raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")
                terminal.write(f"Complete the approved sign-in at {uri} using code {code}.\n")
                terminal.flush()

            with _private_sdk_logging():
                sdk = (credential_factory or _device_credential)(
                    tenant_id=str(binding.tenant_id),
                    client_id=str(binding.client_id),
                    authority="login.microsoftonline.com",
                    additionally_allowed_tenants=[],
                    disable_automatic_authentication=True,
                    cache_persistence_options=None,
                    enable_support_logging=False,
                    logging_enable=False,
                    prompt_callback=private_prompt,
                    timeout=remaining,
                )
                try:
                    if not _authorized(settings, binding):
                        raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")
                    record = sdk.authenticate(scopes=[_SCOPE])
                    if (
                        not _authorized(settings, binding)
                        or record.tenant_id != str(binding.tenant_id)
                        or record.client_id != str(binding.client_id)
                        or record.home_account_id != binding.home_account_id
                    ):
                        raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")
                    acquired = sdk.get_token(_SCOPE)
                    if not _authorized(settings, binding):
                        raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")
                    snapshot = FoundryMemoryTokenCredential(
                        acquired,
                        authorization_deadline=binding.authorization_deadline,
                        enabled=lambda: _authorized(settings, binding),
                        binding_digest=binding.binding_digest(),
                    )
                    del acquired, record
                finally:
                    try:
                        sdk.close()
                    finally:
                        del sdk
        if not _authorized(settings, binding) or not snapshot.ready():
            raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")
        _serve(create_runtime_app(settings, snapshot), settings)
    except Exception:
        # SDK/terminal/server exceptions can contain private material.
        raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE") from None
    finally:
        if snapshot is not None:
            snapshot.close()


_SEARCH_SCOPE = "https://search.azure.com/.default"
_CAPTURED_TERMINAL_MARKERS = (
    "CODEX_SESSION_ID",
    "CODEX_THREAD_ID",
    "CODEX_CI",
    "GITHUB_ACTIONS",
    "CI",
    "SSH_CONNECTION",
    "SSH_TTY",
    "TMUX",
    "STY",
)


def _qualification_error() -> ProviderConfigurationError:
    return ProviderConfigurationError("FOUNDRY_QUALIFICATION_UNAVAILABLE")


def _owner_terminal_provenance(binding: FoundryQualificationBinding) -> None:
    if sys.platform != "darwin" or any(name in os.environ for name in _CAPTURED_TERMINAL_MARKERS):
        raise _qualification_error()
    pid = os.getpid()
    seen: set[int] = set()
    terminal_found = False
    for _ in range(16):
        if pid <= 1:
            if terminal_found:
                return
            break
        if pid in seen:
            break
        seen.add(pid)
        remaining = binding.authorization_deadline - time.time()
        if remaining <= 0:
            break
        # Only parent PID and executable name are inspected, never command arguments.
        result = subprocess.run(  # noqa: S603 - fixed executable/options and validated integer PID
            ["/bin/ps", "-o", "ppid=,comm=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=True,
            timeout=min(remaining, binding.request_timeout_seconds),
        )
        match = re.fullmatch(r"\s*(\d+)\s+([^\n]+)\s*", result.stdout)
        if match is None:
            break
        name = os.path.basename(match.group(2).strip()).lower()
        if any(value in name for value in ("codex", "electron", "ssh", "sandbox-exec")):
            break
        terminal_found = terminal_found or name in {"terminal", "iterm", "iterm2"}
        pid = int(match.group(1))
    raise _qualification_error()


@contextmanager
def _qualification_terminal(binding: FoundryQualificationBinding) -> Iterator[TextIO]:
    _owner_terminal_provenance(binding)
    if not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        raise _qualification_error()
    with open("/dev/tty", "r+", encoding="utf-8") as terminal:
        if not terminal.isatty():
            raise _qualification_error()
        yield terminal


def _confirm_private(
    terminal: TextIO,
    binding: FoundryQualificationBinding,
    message: str,
    reply: str,
) -> None:
    if not terminal.isatty():
        raise _qualification_error()
    terminal.write(message + "\nType " + reply + " to continue, or anything else to stop.\n")
    terminal.flush()
    received = bytearray()
    while len(received) <= len(reply):
        remaining = binding.authorization_deadline - time.time()
        if remaining <= 0 or not select.select([terminal], [], [], remaining)[0]:
            raise _qualification_error()
        character = os.read(terminal.fileno(), 1)
        if character in {b"", b"\n", b"\r"}:
            break
        received.extend(character)
    if time.time() >= binding.authorization_deadline or bytes(received).strip() != reply.encode():
        raise _qualification_error()


class _QualificationMemory:
    """Deadline-owned private state, never exported into the app or runtime binding."""

    def __init__(self, settings: Settings, binding: FoundryQualificationBinding) -> None:
        self.settings = settings
        self.binding = binding
        self._lock = RLock()
        self._closed = False
        self._sdk: _DeviceCredential | None = None
        self._client: httpx.Client | None = None
        self._record: _AuthenticationRecord | None = None
        self._account: tuple[str, str, str] | None = None
        self._confirmed = False
        self._cleanup_failed = False
        self._search_origin: str | None = None
        self._requested: set[str] = set()
        self._tokens: dict[str, tuple[str, float]] = {}
        self._documents: list[dict[str, Any]] = []
        self._buffers: list[bytearray] = []
        self._timer = Timer(max(0, binding.authorization_deadline - time.time()), self.close)
        self._timer.daemon = True
        self._timer.start()

    def guard(self, *, confirmed: bool = True) -> None:
        with self._lock:
            if (
                self._closed
                or self.settings.foundry_qualification_binding() != self.binding
                or (confirmed and not self._confirmed)
                or any(expiry <= time.time() for _, expiry in self._tokens.values())
            ):
                raise _qualification_error()
            if self._record is not None and self._account != (
                self._record.tenant_id,
                self._record.client_id,
                self._record.home_account_id,
            ):
                raise _qualification_error()

    def install_sdk(self, sdk: _DeviceCredential) -> None:
        with self._lock:
            if self._closed:
                sdk.close()
                raise _qualification_error()
            self._sdk = sdk
        self.guard(confirmed=False)

    def authenticate(self) -> str:
        self.guard(confirmed=False)
        assert self._sdk is not None
        record = self._sdk.authenticate(scopes=[_SCOPE])
        with self._lock:
            self.guard(confirmed=False)
            if (
                record.tenant_id != self.binding.tenant_id
                or record.client_id != self.binding.client_id
                or not isinstance(record.home_account_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", record.home_account_id)
            ):
                raise _qualification_error()
            label = getattr(record, "username", None)
            if (
                not isinstance(label, str)
                or not 1 <= len(label) <= 255
                or not all(character.isprintable() for character in label)
            ):
                raise _qualification_error()
            self._record = record
            self._account = (record.tenant_id, record.client_id, record.home_account_id)
            return label

    def confirm_account(self) -> None:
        self.guard(confirmed=False)
        with self._lock:
            self._confirmed = True
        self.guard()

    def acquire(self, scope: str) -> None:
        self.guard()
        if (
            scope not in {_SCOPE, _SEARCH_SCOPE}
            or scope in self._tokens
            or (scope == _SEARCH_SCOPE and self._search_origin is None)
        ):
            raise _qualification_error()
        assert self._sdk is not None
        acquired = self._sdk.get_token(scope)
        self.guard()
        if (
            type(acquired.token) is not str
            or not acquired.token
            or type(acquired.expires_on) not in {int, float}
            or not math.isfinite(acquired.expires_on)
            or acquired.expires_on <= time.time()
        ):
            raise _qualification_error()
        with self._lock:
            self.guard()
            self._tokens[scope] = (
                acquired.token,
                min(acquired.expires_on, self.binding.authorization_deadline),
            )
            self._timer.cancel()
            expiry = min(expiry for _, expiry in self._tokens.values())
            self._timer = Timer(max(0, expiry - time.time()), self.close)
            self._timer.daemon = True
            self._timer.start()
        del acquired

    def confirm_search(self, origin: str) -> None:
        self.guard()
        if re.fullmatch(r"https://[a-z0-9][a-z0-9-]*\.search\.windows\.net", origin) is None:
            raise _qualification_error()
        with self._lock:
            self.guard()
            self._search_origin = origin

    def get(
        self, url: str, scope: str, client_factory: Callable[..., httpx.Client]
    ) -> dict[str, Any]:
        self.guard()
        base = self.binding.project_endpoint + "/agents/" + self.binding.agent_name
        allowed = {
            base + "?api-version=" + self.binding.agent_api_version: _SCOPE,
            base
            + "/versions/"
            + self.binding.agent_version
            + "?api-version="
            + self.binding.agent_api_version: _SCOPE,
        }
        if self._search_origin is not None:
            allowed[
                self._search_origin
                + "/knowledgebases('"
                + self.binding.knowledge_base
                + "')?api-version="
                + self.binding.search_api_version
            ] = _SEARCH_SCOPE
        if allowed.get(url) != scope or url in self._requested:
            raise _qualification_error()
        self._requested.add(url)
        if scope not in self._tokens:
            raise _qualification_error()
        bearer, expiry = self._tokens[scope]
        timeout = min(self.binding.request_timeout_seconds, expiry - time.time())
        if timeout <= 0:
            raise _qualification_error()
        with self._lock:
            self.guard()
            if self._client is None:
                self._client = client_factory(
                    trust_env=False,
                    follow_redirects=False,
                    verify=True,
                    timeout=timeout,
                )
            client = self._client
        self.guard()
        data = bytearray()
        with self._lock:
            self._buffers.append(data)
        with client.stream(
            "GET",
            url,
            headers={"Authorization": "Bearer " + bearer, "Accept-Encoding": "identity"},
            timeout=timeout,
        ) as response:
            self.guard()
            media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            encoding = response.headers.get("content-encoding", "identity").strip().lower()
            if (
                response.status_code != 200
                or media_type != "application/json"
                or encoding != "identity"
            ):
                raise _qualification_error()
            length = response.headers.get("content-length")
            if length is not None and (
                not length.isdigit() or int(length) > self.binding.max_metadata_response_bytes
            ):
                raise _qualification_error()
            for chunk in response.iter_bytes():
                self.guard()
                if len(data) + len(chunk) > self.binding.max_metadata_response_bytes:
                    raise _qualification_error()
                data.extend(chunk)
        self.guard()

        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise _qualification_error()
                result[key] = value
            return result

        def invalid_constant(value: str) -> None:
            raise _qualification_error()

        document = json.loads(data, object_pairs_hook=unique, parse_constant=invalid_constant)
        if not isinstance(document, dict):
            raise _qualification_error()
        with self._lock:
            self.guard()
            self._documents.append(document)
            data.clear()
        return document

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._timer.cancel()
            self._tokens.clear()
            self._record = None
            self._account = None
            self._confirmed = False
            for document in self._documents:
                document.clear()
            self._documents.clear()
            for buffer in self._buffers:
                buffer.clear()
            self._buffers.clear()
            client, sdk = self._client, self._sdk
            self._client = None
            self._sdk = None
            for resource in (client, sdk):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        # Timers must never print SDK exceptions through threading.excepthook.
                        self._cleanup_failed = True


def run_foundry_qualification(
    settings: Settings | None = None,
    credential_factory: Callable[..., _DeviceCredential] | None = None,
    client_factory: Callable[..., httpx.Client] | None = None,
) -> dict[str, Any]:
    """Explicit owner-terminal metadata observation; no app, provider or activation."""
    memory: _QualificationMemory | None = None
    try:
        settings = settings or get_settings()
        binding = settings.foundry_qualification_binding()
        with _private_sdk_logging(), _qualification_terminal(binding) as terminal:
            memory = _QualificationMemory(settings, binding)
            try:
                memory.guard(confirmed=False)
                remaining = int(binding.authorization_deadline - time.time())
                if remaining < 1:
                    raise _qualification_error()

                def prompt(uri: str, code: str, expires: datetime) -> None:
                    assert memory is not None
                    memory.guard(confirmed=False)
                    if not terminal.isatty() or expires.timestamp() <= time.time():
                        raise _qualification_error()
                    terminal.write(f"Complete the approved sign-in at {uri} using code {code}.\n")
                    terminal.flush()

                _confirm_private(
                    terminal,
                    binding,
                    "Use only this independently opened, unrecorded owner terminal. "
                    "Stop if Microsoft asks for new consent or permissions. "
                    "This command only reads approved metadata and never starts the app.",
                    "CONFIRM PRIVATE TERMINAL",
                )
                memory.guard(confirmed=False)
                remaining = int(binding.authorization_deadline - time.time())
                if remaining < 1:
                    raise _qualification_error()
                network_timeout = min(remaining, binding.request_timeout_seconds)
                memory.install_sdk(
                    (credential_factory or _device_credential)(
                        tenant_id=binding.tenant_id,
                        client_id=binding.client_id,
                        authority="login.microsoftonline.com",
                        additionally_allowed_tenants=[],
                        disable_automatic_authentication=True,
                        cache_persistence_options=None,
                        enable_support_logging=False,
                        logging_enable=False,
                        prompt_callback=prompt,
                        timeout=remaining,
                        connection_timeout=network_timeout,
                        read_timeout=network_timeout,
                        retry_total=0,
                    )
                )
                label = memory.authenticate()
                _confirm_private(
                    terminal,
                    binding,
                    "Selected existing account: " + label,
                    "CONFIRM ACCOUNT",
                )
                del label
                memory.confirm_account()
                memory.acquire(_SCOPE)
                factory = client_factory or httpx.Client
                base = binding.project_endpoint + "/agents/" + binding.agent_name
                properties = memory.get(
                    base + "?api-version=" + binding.agent_api_version, _SCOPE, factory
                )
                version = memory.get(
                    base
                    + "/versions/"
                    + binding.agent_version
                    + "?api-version="
                    + binding.agent_api_version,
                    _SCOPE,
                    factory,
                )
                observation, search_origin = _agent_observation(properties, version, binding)
                memory.guard()
                _confirm_private(
                    terminal,
                    binding,
                    "Confirm the exact existing Search origin: " + search_origin,
                    "CONFIRM SEARCH",
                )
                memory.guard()
                memory.confirm_search(search_origin)
                memory.acquire(_SEARCH_SCOPE)
                knowledge = memory.get(
                    search_origin
                    + "/knowledgebases('"
                    + binding.knowledge_base
                    + "')?api-version="
                    + binding.search_api_version,
                    _SEARCH_SCOPE,
                    factory,
                )
                result = {
                    "status": "METADATA_OBSERVED_ONLY",
                    "project": "s08-cloud-ai-agent",
                    **observation,
                    **_knowledge_observation(knowledge, binding),
                    "routingVerified": False,
                    "groundingVerified": False,
                    "tenantIsolationVerified": False,
                    "runtimeActivated": False,
                }
                memory.guard()
                return result
            finally:
                memory.close()
                if memory._cleanup_failed:
                    raise _qualification_error()
    except Exception:
        raise _qualification_error() from None


def main() -> None:
    parser = argparse.ArgumentParser(description="Explicit approved local Foundry host")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--foundry-device-code", action="store_true")
    actions.add_argument("--foundry-qualify", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.foundry_qualify:
            print(json.dumps(run_foundry_qualification(), sort_keys=True))
        else:
            run_foundry_device_code()
    except ProviderConfigurationError:
        message = (
            "Foundry qualification is unavailable. Review its approved configuration."
            if arguments.foundry_qualify
            else "Foundry host is unavailable. Review its approved configuration."
        )
        raise SystemExit(message) from None


if __name__ == "__main__":
    main()
else:
    app = create_runtime_app()
