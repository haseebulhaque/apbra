"""Owner-manual metadata observation only. Import never loads configuration or credentials."""

from __future__ import annotations

import io
import json
import logging
import math
import os
import re
import select
import selectors
import struct
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event, RLock, Thread, Timer
from typing import Any, Protocol, TextIO

import httpx

from .foundry_metadata_projection import _agent_observation, _knowledge_observation
from .model_provider import FoundryAccessToken, ProviderConfigurationError

_SCOPE = "https://ai.azure.com/.default"
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


@dataclass(frozen=True, repr=False)
class OwnerMetadataPlan:
    tenant_id: str = "4825d1f6-89d8-4e38-9418-2827aa59a23c"
    client_id: str = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
    project_endpoint: str = (
        "https://s08-cloud-ai-agent-resource.services.ai.azure.com/api/projects/s08-cloud-ai-agent"
    )
    agent_name: str = "s08-document-grounded-agent"
    agent_version: str = "6"
    knowledge_base: str = "s08-knowledge-base"
    agent_api_version: str = "v1"
    search_api_version: str = "2025-11-01-preview"
    request_timeout_seconds: float = 300
    max_metadata_response_bytes: int = 4000000
    max_projection_items: int = 100
    max_projection_string_characters: int = 255


_PLAN = OwnerMetadataPlan()


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


class _Discard(io.StringIO):
    def write(self, value: str) -> int:
        return len(value)


_SDK_SERIALIZER = RLock()


def _quiet_call[T](call: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    # Device challenges use /dev/tty. Unexpected SDK stdout/stderr is never retained.
    with _SDK_SERIALIZER:
        previous = logging.root.manager.disable
        logging.disable(max(previous, sys.maxsize))
        try:
            with redirect_stdout(_Discard()), redirect_stderr(_Discard()):
                return call(*args, **kwargs)
        finally:
            logging.disable(previous)


def _device_credential(**kwargs: Any) -> _DeviceCredential:
    # Only the separately approved manual flow reaches this import/construction.
    from azure.identity import DeviceCodeCredential

    return DeviceCodeCredential(**kwargs)


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


def _qualification_error() -> ProviderConfigurationError:
    return ProviderConfigurationError("FOUNDRY_QUALIFICATION_UNAVAILABLE")


def _owner_terminal_provenance(binding: OwnerMetadataPlan) -> None:
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
        # Only parent PID and executable name are inspected, never command arguments.
        result = subprocess.run(  # noqa: S603 - fixed executable/options and validated integer PID
            ["/bin/ps", "-o", "ppid=,comm=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=True,
            timeout=binding.request_timeout_seconds,
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
def _qualification_terminal(binding: OwnerMetadataPlan) -> Iterator[TextIO]:
    _owner_terminal_provenance(binding)
    if not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        raise _qualification_error()
    with open("/dev/tty", "r+", encoding="utf-8") as terminal:
        if not terminal.isatty():
            raise _qualification_error()
        yield terminal


def _confirm_private(
    terminal: TextIO,
    binding: OwnerMetadataPlan,
    message: str,
    reply: str,
) -> None:
    if not terminal.isatty():
        raise _qualification_error()
    terminal.write(message + "\nType " + reply + " to continue, or anything else to stop.\n")
    terminal.flush()
    started = time.monotonic()
    received = bytearray()
    while len(received) <= len(reply):
        remaining = binding.request_timeout_seconds - (time.monotonic() - started)
        if remaining <= 0 or not select.select([terminal], [], [], remaining)[0]:
            raise _qualification_error()
        character = os.read(terminal.fileno(), 1)
        if character == b"":
            raise _qualification_error()
        if character in {b"\n", b"\r"}:
            break
        received.extend(character)
        if len(received) > len(reply):
            raise _qualification_error()
    if (
        time.monotonic() - started >= binding.request_timeout_seconds
        or bytes(received) != reply.encode()
    ):
        raise _qualification_error()


# Owned IPC uses bounded JSON, never pickle or remotely supplied code.
_WORKER_CODE = (
    "import sys;sys.path.insert(0,sys.argv[1]);"
    "from apbra_api.foundry_owner_metadata import _metadata_worker;_metadata_worker()"
)


def _read_http_metadata(
    url: str,
    bearer: str,
    timeout: float,
    cap: int,
    factory: Callable[..., httpx.Client] | None,
) -> bytearray:
    data = bytearray()
    try:
        with (factory or httpx.Client)(
            trust_env=False,
            follow_redirects=False,
            verify=True,
            timeout=timeout,
        ) as client:
            with client.stream(
                "GET",
                url,
                headers={
                    "Authorization": "Bearer " + bearer,
                    "Accept-Encoding": "identity",
                },
                timeout=timeout,
            ) as response:
                if (
                    response.status_code != 200
                    or response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    != "application/json"
                    or response.headers.get("content-encoding", "identity").strip().lower()
                    != "identity"
                ):
                    raise _qualification_error()
                length = response.headers.get("content-length")
                if length is not None and (not length.isdigit() or int(length) > cap):
                    raise _qualification_error()
                for chunk in response.iter_bytes():
                    if len(data) + len(chunk) > cap:
                        raise _qualification_error()
                    data.extend(chunk)
        return data
    except BaseException:
        data.clear()
        raise


def _blocking_exact(fd: int, length: int) -> bytearray:
    result = bytearray()
    while len(result) < length:
        chunk = os.read(fd, min(length - len(result), 65536))
        if not chunk:
            result.clear()
            raise _qualification_error()
        result.extend(chunk)
    return result


def _blocking_write(fd: int, value: bytes | bytearray) -> None:
    view = memoryview(value)
    try:
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise _qualification_error()
            view = view[written:]
    finally:
        view.release()


def _metadata_worker(factory: Callable[..., httpx.Client] | None = None) -> None:
    # This is an owned spawned transport, not a sign-in/CLI mode. No secrets arrive
    # until raw process output has been disconnected from the private response pipe.
    output = os.dup(1)
    null = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null, 1)
    os.dup2(null, 2)
    os.close(null)
    logging.disable(sys.maxsize)
    raw = bytearray()
    data = bytearray()
    packet: dict[str, Any] = {}
    try:
        _blocking_write(output, b"R")
        header = _blocking_exact(0, 4)
        size = struct.unpack("!I", header)[0]
        if not 0 < size <= _PLAN.max_metadata_response_bytes:
            raise _qualification_error()
        raw = _blocking_exact(0, size)
        packet = json.loads(raw)
        raw.clear()
        if (
            type(packet) is not dict
            or set(packet) != {"url", "bearer", "timeout", "cap"}
            or type(packet["url"]) is not str
            or type(packet["bearer"]) is not str
            or not packet["bearer"]
            or packet["cap"] != _PLAN.max_metadata_response_bytes
            or type(packet["timeout"]) not in {int, float}
            or not math.isfinite(packet["timeout"])
            or not 0 < packet["timeout"] <= _PLAN.request_timeout_seconds
        ):
            raise _qualification_error()
        base = _PLAN.project_endpoint + "/agents/" + _PLAN.agent_name
        fixed = {base + "?api-version=v1", base + "/versions/6?api-version=v1"}
        if (
            packet["url"] not in fixed
            and re.fullmatch(
                r"https://[a-z0-9][a-z0-9-]*\.search\.windows\.net/knowledgebases\('s08-knowledge-base'\)\?api-version=2025-11-01-preview",
                packet["url"],
            )
            is None
        ):
            raise _qualification_error()
        data = _read_http_metadata(
            packet["url"], packet["bearer"], packet["timeout"], packet["cap"], factory
        )
        _blocking_write(output, struct.pack("!I", len(data) + 1))
        _blocking_write(output, b"S")
        _blocking_write(output, data)
    except BaseException:
        try:
            _blocking_write(output, struct.pack("!I", 1) + b"E")
        except BaseException:
            data.clear()  # No private child/IPC error is ever logged.
    finally:
        data.clear()
        raw.clear()
        packet.clear()
        os.close(output)


def _worker_command() -> list[str]:
    return [
        sys.executable,
        "-I",
        "-B",
        "-c",
        _WORKER_CODE,
        str(Path(__file__).resolve().parents[1]),
    ]


class _GetOperation:
    """Owns the child and verifies death; no caller-only timeout fiction."""

    def __init__(self, timeout: float) -> None:
        self.deadline = time.monotonic() + timeout
        self.process: subprocess.Popen[bytes] | None = None
        self._lock = RLock()
        self._cancelled = False
        self.death_verified = False
        self._startup_done = Event()
        self._startup_started = False
        self._startup_failed = False

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if self._cancelled or remaining <= 0:
            raise _qualification_error()
        return remaining

    def _spawn(self) -> None:
        # This thread owns only public startup parameters. No private payload is
        # delivered until start completes inside the original operation deadline.
        try:
            process = subprocess.Popen(  # noqa: S603 - isolated own interpreter/fixed worker code
                _worker_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, close_fds=True, cwd="/", env={},
            )
            with self._lock:
                self.process = process
                if self._cancelled:
                    self._reap(process)
                else:
                    assert process.stdin is not None and process.stdout is not None
                    os.set_blocking(process.stdin.fileno(), False)
                    os.set_blocking(process.stdout.fileno(), False)
        except BaseException:
            # Never retain raw startup exception messages or private tracebacks.
            self._startup_failed = True
        finally:
            self._startup_done.set()

    def start(self) -> None:
        self.remaining()
        self._startup_started = True
        Thread(target=self._spawn, daemon=True, name="apbra-public-metadata-start").start()
        if not self._startup_done.wait(self.remaining()):
            raise _qualification_error()
        self.remaining()
        if self._startup_failed or self.process is None:
            raise _qualification_error()

    def transfer(
        self, fd: int, value: bytearray | None, length: int, memory: _OwnerMemory, buffer: bytearray
    ) -> None:
        offset = 0
        with selectors.DefaultSelector() as selector:
            selector.register(
                fd, selectors.EVENT_WRITE if value is not None else selectors.EVENT_READ
            )
            while offset < length:
                memory.guard()
                if not selector.select(self.remaining()):
                    raise _qualification_error()
                self.remaining()
                memory.guard()
                try:
                    if value is not None:
                        count = os.write(fd, memory.private_slice(value, offset, 65536))
                    else:
                        chunk = os.read(fd, min(length - offset, 65536))
                        count = len(chunk)
                        memory.append_private(buffer, chunk)
                except BlockingIOError:
                    continue
                self.remaining()
                memory.guard()
                if count <= 0:
                    raise _qualification_error()
                offset += count

    def finish(self) -> None:
        process = self.process
        if process is None:
            raise _qualification_error()
        process.wait(timeout=self.remaining())
        self.death_verified = process.poll() is not None
        self.remaining()
        if process.returncode != 0:
            raise _qualification_error()

    def _reap(self, process: subprocess.Popen[bytes]) -> None:
        # A separate, explicit one-second verification allowance follows a kill.
        # It is not part of the GET execution deadline or a secure-erasure claim.
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=1.0)
        except BaseException:
            raise _qualification_error() from None
        finally:
            self.death_verified = process.poll() is not None
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()
        if not self.death_verified:
            raise _qualification_error()

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            process = self.process
            if process is not None:
                self._reap(process)
                return
            if not self._startup_started or self._startup_done.is_set():
                self.death_verified = True
                return
        # A hung OS spawn has received no token/URL. Keep ownership visible and
        # let the startup thread kill any eventual child before it can receive it.
        raise _qualification_error()


def _run_owned_get(
    url: str,
    bearer: str,
    timeout: float,
    cap: int,
    factory: Callable[..., httpx.Client] | None,
    memory: _OwnerMemory,
    buffer: bytearray,
) -> None:
    operation = _GetOperation(timeout)
    packet = bytearray()
    header = bytearray()
    try:
        memory.register_operation(operation)
        if factory is not None:
            # Test seams patch this owned-operation boundary, never substitute a
            # transport in an actual owner invocation.
            raise _qualification_error()
        if len(url) + len(bearer) > cap:
            raise _qualification_error()
        encoded = json.dumps(
            {"url": url, "bearer": bearer, "timeout": timeout, "cap": cap}, allow_nan=False
        ).encode("utf-8")
        memory.register_buffer(packet)
        memory.append_private(packet, encoded)
        del encoded
        operation.remaining()
        if not 0 < len(packet) <= cap:
            raise _qualification_error()
        operation.start()
        process = operation.process
        assert process is not None and process.stdin is not None and process.stdout is not None
        memory.register_buffer(header)
        operation.transfer(process.stdout.fileno(), None, 1, memory, header)
        if header != b"R":
            raise _qualification_error()
        header.clear()
        framed = bytearray()
        memory.register_buffer(framed)
        memory.append_private(framed, struct.pack("!I", len(packet)))
        memory.append_private(framed, bytes(packet))
        try:
            operation.transfer(process.stdin.fileno(), framed, len(framed), memory, header)
        finally:
            framed.clear()
        packet.clear()
        operation.transfer(process.stdout.fileno(), None, 4, memory, header)
        size = struct.unpack("!I", header)[0]
        header.clear()
        if not 1 <= size <= cap + 1:
            raise _qualification_error()
        operation.transfer(process.stdout.fileno(), None, size, memory, buffer)
        operation.finish()
        memory.guard()
        if buffer[:1] != b"S":
            raise _qualification_error()
        del buffer[:1]
    finally:
        packet.clear()
        header.clear()
        try:
            operation.cancel()
        finally:
            memory.unregister_operation(operation)


class _OwnerMemory:
    """Outcome-owned private state, never exported into the app or runtime binding."""

    def __init__(self, binding: OwnerMetadataPlan) -> None:
        self.binding = binding
        self._lock = RLock()
        self._closed = False
        self._sdk: _DeviceCredential | None = None
        self._client: httpx.Client | None = None
        self._record: _AuthenticationRecord | None = None
        self._account: tuple[str, str, str] | None = None
        self._confirmed = False
        self._private_approved = False
        self._cleanup_failed = False
        self._failed_buffers: list[Any] = []
        self._cleanup_done = Event()
        self._cleanup_pending = False
        self._cleanup_verified = False
        self._closing_resources: list[Any] = []
        self._operation: _GetOperation | None = None
        self._search_origin: str | None = None
        self._requested: set[str] = set()
        self._tokens: dict[str, tuple[str, float]] = {}
        self._documents: list[dict[str, Any]] = []
        self._buffers: list[bytearray] = []
        self._timer: Timer | None = None
        self._device_expiry: float | None = None

    def guard(self, *, confirmed: bool = True) -> None:
        with self._lock:
            if (
                self._closed
                or self.binding != OwnerMetadataPlan()
                or (self._device_expiry is not None and self._device_expiry <= time.time())
                or (self._sdk is not None and not self._private_approved)
                or (confirmed and (not self._confirmed or self._record is None))
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
            if self._closed or not self._private_approved:
                _quiet_call(sdk.close)
                raise _qualification_error()
            self._sdk = sdk
        self.guard(confirmed=False)

    def authenticate(self) -> str:
        self.guard(confirmed=False)
        if self._record is not None:
            raise _qualification_error()
        assert self._sdk is not None
        record = _quiet_call(self._sdk.authenticate, scopes=[_SCOPE])
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
        if self._record is None:
            raise _qualification_error()
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
        acquired = _quiet_call(self._sdk.get_token, scope)
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
                acquired.expires_on,
            )
            if self._timer is not None:
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

    def _get(
        self, url: str, scope: str, client_factory: Callable[..., httpx.Client] | None
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
        data = bytearray()
        self.register_buffer(data)
        _run_owned_get(
            url,
            bearer,
            timeout,
            self.binding.max_metadata_response_bytes,
            client_factory,
            self,
            data,
        )
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

    def get(
        self, url: str, scope: str, client_factory: Callable[..., httpx.Client] | None
    ) -> dict[str, Any]:
        try:
            return self._get(url, scope, client_factory)
        except BaseException:
            self.close()
            raise

    def register_buffer(self, buffer: bytearray) -> None:
        with self._lock:
            self.guard()
            self._buffers.append(buffer)

    def append_private(self, buffer: bytearray, chunk: bytes) -> None:
        with self._lock:
            self.guard()
            if self._closed or not any(item is buffer for item in self._buffers):
                raise _qualification_error()
            buffer.extend(chunk)

    def private_slice(self, buffer: bytearray, offset: int, length: int) -> bytes:
        # An immutable bounded copy may outlive revocation during the syscall;
        # it never exports the registered mutable buffer or prevents its clearing.
        with self._lock:
            self.guard()
            if not any(item is buffer for item in self._buffers):
                raise _qualification_error()
            return bytes(buffer[offset : offset + length])

    def register_operation(self, operation: _GetOperation) -> None:
        with self._lock:
            self.guard()
            if self._operation is not None:
                raise _qualification_error()
            self._operation = operation

    def unregister_operation(self, operation: _GetOperation) -> None:
        with self._lock:
            if not operation.death_verified:
                self._cleanup_failed = True
                if operation not in self._closing_resources:
                    self._closing_resources.append(operation)
            elif self._operation is operation:
                self._operation = None

    def close(self) -> None:
        with self._lock:
            if self._closed:
                pending = self._cleanup_pending
                resources = None
            else:
                self._closed = True
                self._cleanup_pending = True
                pending = False
                if self._timer is not None:
                    self._timer.cancel()
                self._tokens.clear()
                self._record = None
                self._account = None
                self._confirmed = False
                self._private_approved = False
                self._device_expiry = None
                resources = [self._operation, self._client, self._sdk]
                self._closing_resources = resources
                self._operation = None
                self._client = None
                self._sdk = None
                # A clearing fault must not skip detachment/cancellation or leave
                # the completion event forever unset. Retain failed ownership.
                managed_values: list[Any] = [*self._documents, *self._buffers]
                for value in managed_values:
                    try:
                        value.clear()
                    except BaseException:
                        self._cleanup_failed = True
                        self._failed_buffers.append(value)
                self._documents.clear()
                self._buffers.clear()
        # Never wait on SDK serialization/process death with the memory lock held.
        if resources is None:
            if pending:
                self._cleanup_done.wait()
            return
        failed_resources: list[Any] = []
        try:
            for resource in resources:
                if resource is not None:
                    try:
                        if isinstance(resource, _GetOperation):
                            resource.cancel()
                        else:
                            _quiet_call(resource.close)
                    except BaseException:
                        self._cleanup_failed = True
                        failed_resources.append(resource)
        finally:
            with self._lock:
                self._closing_resources = failed_resources
                self._cleanup_verified = not self._cleanup_failed and not failed_resources
                self._cleanup_pending = False
                self._cleanup_done.set()


def run_owner_metadata(
    *,
    credential_factory: Callable[..., _DeviceCredential] | None = None,
    client_factory: Callable[..., httpx.Client] | None = None,
) -> dict[str, Any]:
    """Explicit private metadata observation; no app/provider/activation.

    SDK authenticate may exchange/cache the initial OAuth grant before account
    confirmation; confirmation gates resource GETs, not OAuth protocol traffic.
    """
    memory: _OwnerMemory | None = None
    try:
        binding = _PLAN
        if binding != OwnerMetadataPlan():
            raise _qualification_error()
        with _private_sdk_logging(), _qualification_terminal(binding) as terminal:
            memory = _OwnerMemory(binding)
            try:
                memory.guard(confirmed=False)
                remaining = int(binding.request_timeout_seconds)
                if remaining < 1:
                    raise _qualification_error()

                def prompt(uri: str, code: str, expires: datetime) -> None:
                    assert memory is not None
                    memory.guard(confirmed=False)
                    expiry = expires.timestamp()
                    if (
                        not terminal.isatty()
                        or not math.isfinite(expiry)
                        or expiry <= time.time()
                        or uri != "https://microsoft.com/devicelogin"
                        or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", code)
                        or memory._device_expiry is not None
                    ):
                        raise _qualification_error()
                    memory._device_expiry = expiry
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
                memory._private_approved = True
                memory.guard(confirmed=False)
                remaining = int(binding.request_timeout_seconds)
                if remaining < 1:
                    raise _qualification_error()
                network_timeout = min(remaining, binding.request_timeout_seconds)
                memory.install_sdk(
                    _quiet_call(
                        credential_factory or _device_credential,
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
                memory._device_expiry = None
                memory.confirm_account()
                memory.acquire(_SCOPE)
                factory = client_factory
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
                    **{key: value for key, value in observation.items() if key != "searchOrigin"},
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
    except (Exception, SystemExit):
        raise _qualification_error() from None


def main() -> None:
    if len(sys.argv) != 1:
        raise SystemExit("Foundry owner metadata is unavailable.")
    try:
        print(json.dumps(run_owner_metadata(), sort_keys=True))
    except BaseException:
        raise SystemExit("Foundry owner metadata is unavailable.") from None


if __name__ == "__main__":
    main()
