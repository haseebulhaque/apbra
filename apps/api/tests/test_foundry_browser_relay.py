"""Synthetic SDK and owned loopback relay only; never a real sign-in/browser."""

from __future__ import annotations

import http.client
import json
import time
import webbrowser
from types import SimpleNamespace
from urllib.parse import urlencode
from uuid import uuid4

import pytest

from apbra_api.foundry_browser_relay import (
    ERROR,
    SCOPE,
    BrowserLoginPlan,
    BrowserRelay,
    BrowserRelayError,
    run_approved_browser_session,
)

CANARY = "synthetic-private-authorization-value"
PORT = 18400  # Allowed solely in the disposable internal test namespace.


def auth_url(plan, **changes):
    query = dict(
        client_id=str(plan.client_id),
        response_type="code",
        state=CANARY,
        code_challenge=CANARY,
        code_challenge_method="S256",
        scope=SCOPE + " openid profile offline_access",
        redirect_uri="http://localhost:8400",
        response_mode="form_post",
        login_hint=plan.expected_username,
    )
    query.update(changes)
    return f"https://login.microsoftonline.com/{plan.tenant_id}/oauth2/v2.0/authorize?" + urlencode(
        query
    )


@pytest.fixture
def relay():
    plan = BrowserLoginPlan(uuid4(), uuid4(), "owner@example.invalid", time.time() + 60)
    r = BrowserRelay(plan, port=PORT)
    r.start()
    yield r
    r.close()


def local_read(
    path, *, host=None, origin=None, site=None, method="GET", body=None, mode=None, dest=None
):
    connection = http.client.HTTPConnection("127.0.0.1", PORT, timeout=2)
    try:
        headers = {}
        if host is not None:
            headers["Host"] = host
        if origin is not None:
            headers["Origin"] = origin
        if site is not None:
            headers["Sec-Fetch-Site"] = site
        if mode is not None:
            headers["Sec-Fetch-Mode"] = mode
        if dest is not None:
            headers["Sec-Fetch-Dest"] = dest
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def consume_root():
    import re

    code, headers, body = local_read("/")
    assert code == 200 and headers["X-Frame-Options"] == "DENY"
    assert CANARY.encode() not in body
    capability = re.search(rb'name="capability" value="([A-Za-z0-9_-]{43})"', body).group(1)
    return local_read(
        "/start",
        method="POST",
        origin=f"http://127.0.0.1:{PORT}",
        site="same-origin",
        body=b"capability=" + capability,
    )


def test_actual_relay_one_use_redirect_and_nonsecret_status(relay, capsys):
    assert local_read("/")[0] == 503
    uri = auth_url(relay.plan)
    assert relay.open(uri)
    capability = relay._capability
    code, headers, body = local_read("/status")
    assert code == 200 and json.loads(body)["status"] == "READY_FOR_APPROVED_BROWSER"
    assert CANARY not in json.dumps(headers) and CANARY.encode() not in body
    assert capability.encode() not in body
    code, headers, body = consume_root()
    assert code == 303 and headers["Location"] == uri
    assert headers["Cache-Control"] == "no-store" and headers["Referrer-Policy"] == "same-origin"
    assert CANARY.encode() not in body
    assert (
        local_read(
            "/start",
            method="POST",
            origin=f"http://127.0.0.1:{PORT}",
            site="same-origin",
            body=b"capability=" + capability.encode(),
        )[0]
        == 410
    )
    assert relay._url is None and relay._capability is None
    assert CANARY not in repr(relay) and capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "change",
    [
        {"client_id": str(uuid4())},
        {"response_type": "token"},
        {"scope": "https://graph.microsoft.com/.default"},
        {"scope": SCOPE + " https://storage.azure.com/.default"},
        {"response_mode": "query"},
        {"code_challenge_method": "plain"},
        {"login_hint": "foreign@example.invalid"},
        {"redirect_uri": "https://outside.invalid"},
        {"redirect_uri": "http://localhost.evil:8400"},
        {"redirect_uri": "http://localhost:8400/path?code=private"},
        {"redirect_uri": "http://localhost:bad"},
        {"redirect_uri": f"http://127.0.0.1:{PORT}"},
        {"state": ""},
    ],
)
def test_wrong_auth_scope_client_callback_or_account_hint_never_opens(relay, change):
    with pytest.raises(BrowserRelayError, match=ERROR):
        relay.open(auth_url(relay.plan, **change))
    assert local_read("/")[0] == 503


@pytest.mark.parametrize("fault", ["host", "tenant", "fragment", "duplicate", "newline"])
def test_wrong_authority_and_malformed_url_never_forwarded(relay, fault):
    url = auth_url(relay.plan)
    if fault == "host":
        url = url.replace("login.microsoftonline.com", "outside.invalid")
    elif fault == "tenant":
        url = url.replace(str(relay.plan.tenant_id), str(uuid4()))
    elif fault == "fragment":
        url += "#private"
    elif fault == "duplicate":
        url += "&client_id=" + str(relay.plan.client_id)
    else:
        url += "\r\nInjected:private"
    with pytest.raises(BrowserRelayError, match=ERROR):
        relay.open(url)
    assert local_read("/")[0] == 503


def test_foreign_host_origin_or_unknown_path_cannot_consume_redirect(relay):
    relay.open(auth_url(relay.plan))
    assert local_read("/", host="outside.invalid")[0] == 403
    assert local_read("/", origin="https://outside.invalid")[0] == 403
    for site in ["cross-site", "same-site"]:
        assert local_read("/", site=site)[0] == 403
    assert local_read("/unknown")[0] == 404
    assert consume_root()[0] == 303


@pytest.mark.parametrize(
    "fault",
    [
        "wrong",
        "missing-origin",
        "null-origin",
        "missing-site",
        "cross-site",
        "unicode",
        "duplicate",
    ],
)
def test_wrong_or_foreign_start_capability_never_consumes(relay, fault):
    relay.open(auth_url(relay.plan))
    origin, site = f"http://127.0.0.1:{PORT}", "same-origin"
    body = b"capability=" + relay._capability.encode()
    if fault == "wrong":
        body = b"capability=" + b"wrong" * 9
    elif fault == "missing-origin":
        origin = None
    elif fault == "null-origin":
        origin = "null"
    elif fault == "missing-site":
        site = None
    elif fault == "cross-site":
        site = "cross-site"
    elif fault == "unicode":
        body = b"capability=%E2%98%83"
    else:
        body += b"&capability=duplicate"
    assert local_read("/start", method="POST", origin=origin, site=site, body=body)[0] == 403
    assert consume_root()[0] == 303


def test_expiry_and_close_zero_capability_and_join_listener(relay, monkeypatch):
    relay.open(auth_url(relay.plan))
    monkeypatch.setattr(time, "time", lambda: relay.plan.authorization_deadline + 1)
    assert local_read("/")[0] == 410
    assert relay._url is None and relay._capability is None
    relay.close()
    assert not relay._thread.is_alive() and not relay.active()
    relay.close()
    with pytest.raises(BrowserRelayError):
        relay.start()


def test_close_unblocks_incomplete_headers_and_confirms_no_handler_survives(relay):
    import socket

    client = socket.create_connection(("127.0.0.1", PORT), timeout=2)
    try:
        client.sendall(b"GET / HTTP/1.1\r\nHost:")
        for _ in range(100):
            if relay._connection is not None:
                break
            time.sleep(0.01)
        assert relay._connection is not None
        started = time.monotonic()
        relay.close()
        assert time.monotonic() - started < 2
        assert not relay._thread.is_alive() and relay._connection is None
        try:
            assert client.recv(1) == b""
        except (ConnectionResetError, OSError):
            pass
    finally:
        client.close()


def test_close_during_bounded_active_response_joins_owned_server(relay, monkeypatch):
    import threading

    entered = threading.Event()
    original = relay.response

    def delayed(*args, **kwargs):
        entered.set()
        time.sleep(0.1)
        return original(*args, **kwargs)

    monkeypatch.setattr(relay, "response", delayed)
    outcomes = []

    def read():
        try:
            local_read("/status")
        except (OSError, http.client.HTTPException):
            outcomes.append("closed")

    thread = threading.Thread(target=read)
    thread.start()
    assert entered.wait(2)
    relay.close()
    thread.join(timeout=2)
    assert not relay._thread.is_alive() and not thread.is_alive()


class FakeSDK:
    def __init__(self, relay, fault=None):
        self.relay, self.fault, self.closed, self.tokens = relay, fault, False, 0
        self.record = SimpleNamespace(
            tenant_id=str(relay.plan.tenant_id),
            client_id=str(relay.plan.client_id),
            home_account_id="synthetic.account",
            username=relay.plan.expected_username,
        )

    def authenticate(self, *, scopes):
        assert scopes == [SCOPE]
        print(CANARY)
        if self.fault == "authentication":
            raise RuntimeError(CANARY)
        assert webbrowser.open(auth_url(self.relay.plan))
        if self.fault != "no-browser":
            assert consume_root()[0] == 303
        if self.fault == "tenant":
            self.record.tenant_id = str(uuid4())
        if self.fault == "client":
            self.record.client_id = str(uuid4())
        if self.fault == "username":
            self.record.username = "foreign@example.invalid"
        if self.fault == "account":
            self.record.home_account_id = "bad account"
        return self.record

    def get_token(self, scope):
        assert scope == SCOPE
        self.tokens += 1
        if self.fault == "token":
            raise RuntimeError(CANARY)
        return SimpleNamespace(token=CANARY, expires_on=int(time.time() + 120))

    def close(self):
        self.closed = True
        if self.fault == "close":
            raise RuntimeError(CANARY)


def test_real_sdk_contract_no_disk_cache_fixed_scope_and_cleanup(relay, capsys):
    sdk = FakeSDK(relay)
    kwargs = {}
    seen = []

    def factory(**options):
        kwargs.update(options)
        return sdk

    def callback(session):
        assert session.account.home_account_id == "synthetic.account"
        assert session.bearer().token == CANARY
        seen.append(session)
        print(CANARY)

    run_approved_browser_session(relay.plan, relay, callback, credential_factory=factory)
    assert kwargs["cache_persistence_options"] is None
    assert kwargs["additionally_allowed_tenants"] == [] and kwargs["retry_total"] == 0
    assert kwargs["authority"] == "login.microsoftonline.com"
    assert kwargs["login_hint"] == relay.plan.expected_username
    assert sdk.closed and sdk.tokens == 1 and not seen[0].ready()
    assert not relay._thread.is_alive() and capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "fault",
    ["authentication", "tenant", "client", "username", "account", "no-browser", "token", "close"],
)
def test_failure_never_leaks_or_grants_an_unverified_account(relay, capsys, fault):
    sdk = FakeSDK(relay, fault)
    calls = []

    def callback(session):
        calls.append(True)
        session.bearer()

    with pytest.raises(BrowserRelayError, match=ERROR) as error:
        run_approved_browser_session(
            relay.plan, relay, callback, credential_factory=lambda **kw: sdk
        )
    assert sdk.closed and not relay.active() and not relay._thread.is_alive()
    assert CANARY not in str(error.value) and CANARY not in capsys.readouterr().out
    if fault not in {"token", "close"}:
        assert calls == [] and sdk.tokens == 0


def test_record_drift_prevents_token_access(relay):
    sdk = FakeSDK(relay)

    def callback(session):
        sdk.record.home_account_id = "foreign.account"
        with pytest.raises(BrowserRelayError):
            session.bearer()

    with pytest.raises(BrowserRelayError):
        run_approved_browser_session(
            relay.plan, relay, callback, credential_factory=lambda **kw: sdk
        )
    assert sdk.tokens == 0 and sdk.closed


def test_unstarted_relay_fails_before_sdk_construction():
    plan = BrowserLoginPlan(uuid4(), uuid4(), "owner@example.invalid", time.time() + 30)
    r = BrowserRelay(plan)
    calls = []
    with pytest.raises(BrowserRelayError):
        run_approved_browser_session(
            plan, r, lambda ctx: None, credential_factory=lambda **kw: calls.append(kw)
        )
    assert not calls


def test_cross_site_top_level_document_is_only_a_passive_root(relay):
    relay.open(auth_url(relay.plan))
    before = relay._capability
    code, headers, body = local_read("/", site="cross-site", mode="navigate", dest="document")
    assert code == 200 and b"Sign in using Microsoft" in body
    assert "Location" not in headers and not relay._used
    assert relay._capability == before and CANARY.encode() not in body
    assert local_read("/status", site="cross-site", mode="navigate", dest="document")[0] == 403
    assert local_read("/", site="cross-site", mode="navigate", dest="iframe")[0] == 403
    assert (
        local_read(
            "/start",
            method="POST",
            site="cross-site",
            mode="navigate",
            dest="document",
            origin=f"http://127.0.0.1:{PORT}",
            body=b"capability=" + before.encode(),
        )[0]
        == 403
    )
    assert consume_root()[0] == 303
