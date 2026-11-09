"""Explicitly approved browser authentication; no ambient credentials or auto-login.

A controller must verify the requested browser profile and navigate only the
local start URL. The SDK keeps its own PKCE, form-post callback and validation.
This authenticates an account; separate exact-resource grants still authorize IO.
The legacy private-Terminal flow is unchanged.
"""

from __future__ import annotations

import json
import math
import re
import secrets
import socket
import threading
import time
import webbrowser
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

from .foundry_owner_metadata import _Discard, _private_sdk_logging
from .model_provider import FoundryBearer

SCOPE = "https://ai.azure.com/.default"
ERROR = "APPROVED_BROWSER_AUTHENTICATION_UNAVAILABLE"


class BrowserRelayError(ValueError):
    """Nonsecret controlled failure; never wrap raw SDK exception text."""


def require(value: object) -> None:
    if value is not True:
        raise BrowserRelayError(ERROR)


@dataclass(frozen=True, repr=False)
class BrowserLoginPlan:
    tenant_id: UUID
    client_id: UUID
    expected_username: str = field(repr=False)
    authorization_deadline: float

    def validate(self) -> None:
        require(type(self.tenant_id) is UUID and type(self.client_id) is UUID)
        require(
            type(self.expected_username) is str
            and 1 <= len(self.expected_username) <= 255
            and self.expected_username.isprintable()
            and self.expected_username.strip() == self.expected_username
        )
        require(
            type(self.authorization_deadline) in (int, float)
            and math.isfinite(self.authorization_deadline)
            and self.authorization_deadline > time.time()
        )


def _url(value: str) -> Any:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
        return parsed
    except ValueError:
        raise BrowserRelayError(ERROR) from None


class BrowserRelay(webbrowser.BaseBrowser):
    """One-use loopback redirect. No OAuth URL in status, logs, files or repr."""

    def __init__(self, plan: BrowserLoginPlan, *, port: int = 0) -> None:
        super().__init__()
        plan.validate()
        require(type(port) is int and 0 <= port <= 65535)
        self.plan = plan
        self._lock = threading.RLock()
        self._url: str | None = None
        self._used = False
        self._closed = False
        self._status = "WAITING_FOR_SDK"
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port = port
        self._capability: str | None = secrets.token_urlsafe(32)
        self._connection: socket.socket | None = None

    def __repr__(self) -> str:
        return "BrowserRelay(<one-use loopback authentication>)"

    def start(self) -> None:
        with self._lock:
            require(not self._closed and self._server is None)
            relay = self

            class Server(HTTPServer):
                allow_reuse_address = True

                def get_request(self) -> Any:
                    connection, address = super().get_request()
                    with relay._lock:
                        if relay._closed:
                            connection.close()
                            raise OSError("Relay closed")
                        relay._connection = connection
                    connection.settimeout(1)
                    return connection, address

                def close_request(self, request: Any) -> None:
                    with relay._lock:
                        if relay._connection is request:
                            relay._connection = None
                    super().close_request(request)

                def handle_error(self, _request: Any, _address: Any) -> None:
                    pass

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_args: Any) -> None:
                    pass

                def do_GET(self) -> None:
                    self.dispatch("GET")

                def do_POST(self) -> None:
                    self.dispatch("POST")

                def dispatch(self, method: str) -> None:
                    if len(self.headers.get_all("Host", [])) != 1 or any(
                        len(self.headers.get_all(key, [])) > 1
                        for key in ("Origin", "Content-Length", "Content-Type", "Sec-Fetch-Site")
                    ):
                        self.send_error(403, "Unavailable")
                        return
                    body = b""
                    if method == "POST":
                        if self.headers.get("Transfer-Encoding") is not None:
                            self.send_error(400, "Unavailable")
                            return
                        length = self.headers.get("Content-Length", "")
                        if not re.fullmatch(r"[0-9]{1,4}", length) or not 0 < int(length) <= 1024:
                            self.send_error(400, "Unavailable")
                            return
                        body = self.rfile.read(int(length))
                        if len(body) != int(length):
                            self.send_error(400, "Unavailable")
                            return
                    selected = {
                        key: self.headers[key]
                        for key in (
                            "Host",
                            "Origin",
                            "Sec-Fetch-Site",
                            "Sec-Fetch-Mode",
                            "Sec-Fetch-Dest",
                            "Content-Type",
                        )
                        if key in self.headers
                    }
                    code, headers, body = relay.response(method, self.path, selected, body)
                    self.send_response(code)
                    for key, value in headers.items():
                        self.send_header(key, value)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            try:
                self._server = Server(("127.0.0.1", self._port), Handler)
                self._port = self._server.server_address[1]
                self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
                self._thread.start()
            except BaseException:
                self._closed = True
                self._url = self._capability = None
                if self._server is not None:
                    self._server.server_close()
                raise BrowserRelayError(ERROR) from None

    @property
    def start_url(self) -> str:
        """Public passive root; never the capability or Microsoft's private URL."""
        with self._lock:
            require(self._server is not None and not self._closed)
            return f"http://127.0.0.1:{self._port}/"

    def started(self) -> bool:
        with self._lock:
            return (
                self.active()
                and self._server is not None
                and self._thread is not None
                and self._thread.is_alive()
            )

    def active(self) -> bool:
        with self._lock:
            active = not self._closed and time.time() < self.plan.authorization_deadline
            if not active:
                self._url = self._capability = None
            return active

    def open(self, url: str, new: int = 0, autoraise: bool = True) -> bool:
        del new, autoraise
        with self._lock:
            require(
                self.active() and self._server is not None and self._url is None and not self._used
            )
            require(
                type(url) is str
                and 0 < len(url) <= 32768
                and url.isascii()
                and all(33 <= ord(c) <= 126 for c in url)
            )
            parsed = _url(url)
            require(
                parsed.scheme == "https"
                and parsed.hostname == "login.microsoftonline.com"
                and parsed.username is None
                and parsed.password is None
                and parsed.port in (None, 443)
                and not parsed.fragment
                and parsed.path == f"/{self.plan.tenant_id}/oauth2/v2.0/authorize"
            )
            query = parse_qs(parsed.query, keep_blank_values=True)
            require(all(len(values) == 1 and values[0] for values in query.values()))
            require(
                all(
                    key in query
                    for key in (
                        "client_id",
                        "response_type",
                        "state",
                        "code_challenge",
                        "code_challenge_method",
                        "scope",
                        "redirect_uri",
                        "response_mode",
                    )
                )
            )
            require(
                query["client_id"] == [str(self.plan.client_id)]
                and query["response_type"] == ["code"]
                and query["code_challenge_method"] == ["S256"]
                and query["response_mode"] == ["form_post"]
            )
            scopes = set(query["scope"][0].split())
            require(SCOPE in scopes and scopes <= {SCOPE, "openid", "profile", "offline_access"})
            if "login_hint" in query:
                require(query["login_hint"][0].casefold() == self.plan.expected_username.casefold())
            callback = _url(query["redirect_uri"][0])
            require(
                callback.scheme == "http"
                and callback.hostname in {"localhost", "127.0.0.1"}
                and callback.port is not None
                and callback.port != self._port
                and 0 < callback.port <= 65535
                and callback.username is None
                and callback.password is None
                and callback.path in {"", "/"}
                and not callback.query
                and not callback.fragment
            )
            self._url = url  # SDK-produced URL, RAM only; never logged or returned by status.
            self._status = "READY_FOR_APPROVED_BROWSER"
            return True

    def response(
        self, method: str, path: str, headers: dict[str, str], body: bytes = b""
    ) -> tuple[int, dict[str, str], bytes]:
        with self._lock:
            common = {
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
                "Referrer-Policy": "same-origin",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'self' https://login.microsoftonline.com",
                "Content-Type": "text/plain; charset=utf-8",
                "Connection": "close",
            }
            values = {key.lower(): value for key, value in headers.items()}
            origin = f"http://127.0.0.1:{self._port}"
            if values.get("host") != f"127.0.0.1:{self._port}" or values.get("origin") not in (
                None,
                origin,
            ):
                return 403, common, b"Unavailable"
            # The approved Chrome extension starts top-level navigation as cross-site.
            # This only displays a passive document, never consumes its capability.
            passive_document_navigation = (
                method == "GET"
                and path == "/"
                and values.get("sec-fetch-site") == "cross-site"
                and values.get("sec-fetch-mode") == "navigate"
                and values.get("sec-fetch-dest") == "document"
            )
            if (
                values.get("sec-fetch-site") not in (None, "none", "same-origin")
                and not passive_document_navigation
            ):
                return 403, common, b"Unavailable"
            if method == "GET" and path == "/status":
                status = (
                    "CLOSED" if self._closed else "EXPIRED" if not self.active() else self._status
                )
                return 200, common, json.dumps({"status": status}).encode()
            if method == "GET" and path == "/":
                if not self.active() or self._used:
                    return 410, common, b"This sign-in has ended. No automatic retry."
                if self._url is None:
                    return 503, common, b"The SDK sign-in is not ready."
                html = (
                    "<!doctype html><html lang=en><meta charset=utf-8>"
                    "<title>APBRA Microsoft connection</title>"
                    "<h1>Connect your existing Microsoft account</h1>"
                    "<p>Use only the approved Chrome profile. "
                    "Use your existing account. Stop if new permissions or security changes "
                    "are requested.</p>"
                    '<form method="post" action="/start"><input type="hidden" '
                    'name="capability" value="' + str(self._capability) + '">'
                    '<button type="submit">Sign in using Microsoft</button></form></html>'
                ).encode()
                return 200, {**common, "Content-Type": "text/html; charset=utf-8"}, html
            if method != "POST" or path != "/start":
                return 404, common, b"Unavailable"
            if not self.active() or self._used:
                return 410, common, b"This sign-in has ended. No automatic retry."
            if (
                values.get("origin") != origin
                or values.get("sec-fetch-site") != "same-origin"
                or values.get("content-type", "").split(";", 1)[0]
                != "application/x-www-form-urlencoded"
            ):
                return 403, common, b"Unavailable"
            try:
                parsed = parse_qs(
                    body.decode("ascii"),
                    strict_parsing=True,
                    keep_blank_values=True,
                    max_num_fields=1,
                )
            except (UnicodeError, ValueError):
                return 403, common, b"Unavailable"
            if (
                set(parsed) != {"capability"}
                or len(parsed["capability"]) != 1
                or self._capability is None
                or re.fullmatch(r"[A-Za-z0-9_-]{43}", parsed["capability"][0]) is None
                or not secrets.compare_digest(parsed["capability"][0], self._capability)
            ):
                return 403, common, b"Unavailable"
            if self._url is None:
                return 503, common, b"The SDK sign-in is not ready."
            url, self._url = self._url, None
            self._capability = None
            self._used = True
            self._status = "BROWSER_SIGN_IN_IN_PROGRESS"
            return 303, {**common, "Location": url}, b"Continue with Microsoft."

    def mark_authenticated(self) -> None:
        with self._lock:
            require(self.active() and self._used)
            self._status = "MATCHING_ACCOUNT_AUTHENTICATED"

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._url = self._capability = None
            server, thread, connection = self._server, self._thread, self._connection
            self._connection = None
        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        if server is not None:
            if thread is not None and thread.is_alive():
                server.shutdown()
            server.server_close()
        if thread is not None and thread.ident is not None:
            thread.join(timeout=5)
            require(not thread.is_alive())


@dataclass(frozen=True, repr=False)
class BrowserAccount:
    tenant_id: str
    client_id: str
    home_account_id: str = field(repr=False)
    username: str = field(repr=False)


class BrowserSession:
    """Real SDK account, fixed audience and deadline; never persistent credentials."""

    def __init__(self, plan: BrowserLoginPlan, sdk: Any, record: Any, relay: BrowserRelay) -> None:
        self._plan, self._sdk, self._record, self._relay = plan, sdk, record, relay
        self.account = BrowserAccount(
            record.tenant_id, record.client_id, record.home_account_id, record.username
        )
        require(self.ready())

    def ready(self) -> bool:
        try:
            return (
                self._relay.active()
                and time.time() < self._plan.authorization_deadline
                and self.account.tenant_id == str(self._plan.tenant_id)
                and self.account.client_id == str(self._plan.client_id)
                and self.account.username.casefold() == self._plan.expected_username.casefold()
                and re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", self.account.home_account_id) is not None
                and (
                    self._record.tenant_id,
                    self._record.client_id,
                    self._record.home_account_id,
                    self._record.username,
                )
                == (
                    self.account.tenant_id,
                    self.account.client_id,
                    self.account.home_account_id,
                    self.account.username,
                )
            )
        except Exception:
            return False

    def bearer(self) -> FoundryBearer:
        require(self.ready())
        acquired = self._sdk.get_token(SCOPE)
        require(
            self.ready()
            and type(acquired.token) is str
            and bool(acquired.token)
            and type(acquired.expires_on) in (int, float)
            and math.isfinite(acquired.expires_on)
            and acquired.expires_on > time.time()
        )
        return FoundryBearer(
            acquired.token, min(acquired.expires_on, self._plan.authorization_deadline)
        )


def run_approved_browser_session(
    plan: BrowserLoginPlan,
    relay: BrowserRelay,
    callback: Callable[[BrowserSession], None],
    *,
    credential_factory: Callable[..., Any] | None = None,
) -> None:
    """Trusted isolated controller only. Never invoked by an HTTP/model request.

    The controller has the owner's specific browser-login authority. It must stop
    browser interaction on unexpected consent/security/MFA and close the owned
    process if the SDK cannot finish. No legacy Terminal qualification is faked.
    """
    plan.validate()
    require(type(relay) is BrowserRelay and relay.plan == plan and callable(callback))
    require(relay.started())
    sdk = None
    failed = False
    # Registration is process-local. This entrypoint belongs in a dedicated
    # short-lived controller, never a shared web server/browser process.
    opener_name = "apbra-approved-" + uuid4().hex
    try:
        with _private_sdk_logging(), redirect_stdout(_Discard()), redirect_stderr(_Discard()):
            if credential_factory is None:
                from azure.identity import InteractiveBrowserCredential

                credential_factory = InteractiveBrowserCredential
            webbrowser.register(opener_name, None, relay, preferred=True)
            timeout = min(300, plan.authorization_deadline - time.time())
            require(timeout > 0 and relay.active())
            sdk = credential_factory(
                tenant_id=str(plan.tenant_id),
                client_id=str(plan.client_id),
                authority="login.microsoftonline.com",
                additionally_allowed_tenants=[],
                login_hint=plan.expected_username,
                disable_automatic_authentication=True,
                cache_persistence_options=None,
                enable_support_logging=False,
                logging_enable=False,
                timeout=timeout,
                connection_timeout=timeout,
                read_timeout=timeout,
                retry_total=0,
            )
            record = sdk.authenticate(scopes=[SCOPE])
            require(
                relay.active()
                and record.tenant_id == str(plan.tenant_id)
                and record.client_id == str(plan.client_id)
                and type(record.username) is str
                and record.username.casefold() == plan.expected_username.casefold()
                and type(record.home_account_id) is str
                and re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", record.home_account_id) is not None
            )
            session = BrowserSession(plan, sdk, record, relay)
            relay.mark_authenticated()
            callback(session)
            require(session.ready())
            del session, record
    except BaseException:
        failed = True
    finally:
        with _private_sdk_logging(), redirect_stdout(_Discard()), redirect_stderr(_Discard()):
            if sdk is not None:
                try:
                    sdk.close()
                except BaseException:
                    failed = True
            try:
                relay.close()
            except BaseException:
                failed = True
            sdk = None
    if failed:
        raise BrowserRelayError(ERROR) from None
