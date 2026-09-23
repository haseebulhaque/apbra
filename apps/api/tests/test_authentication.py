import json
import secrets
from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread
from typing import Any
from urllib.parse import SplitResult, parse_qs, urlsplit

import httpx
import pytest
from authlib.jose import JsonWebKey, jwt
from conftest import sign_in
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select

from apbra_api.api import create_app
from apbra_api.auth_boundary import SESSION_COOKIE, cookie_secure, digest
from apbra_api.config import Settings
from apbra_api.persistence import AuthorizationCodeRow, AuthTransactionRow, Database

TEST_SESSION_SECRET = "s" * 48
TEST_TOKEN_ENDPOINT = "https://issuer.example/" + "token"
HOSTED_ISSUER = "https://issuer.example/tenant/v2.0"
HOSTED_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
HOSTED_PUBLIC_PEM = HOSTED_PRIVATE_KEY.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
)
HOSTED_PUBLIC_JWK = JsonWebKey.import_key(HOSTED_PUBLIC_PEM, {"kid": "hosted-test-key"})
HOSTED_JWKS = json.dumps({"keys": [HOSTED_PUBLIC_JWK.as_dict(is_private=False)]})


def hosted_settings(
    database_url: str,
    *,
    policy: str = "required",
    response_issuer_supported: bool = True,
) -> Settings:
    return Settings.model_validate(
        {
            "profile": "hosted",
            "database_url": database_url,
            "public_origin": "https://app.example",
            "api_origin": "https://api.example",
            "session_secret": TEST_SESSION_SECRET,
            "bootstrap_enabled": False,
            "oidc_issuer": HOSTED_ISSUER,
            "oidc_jwks_json": HOSTED_JWKS,
            "oidc_authorization_endpoint": "https://issuer.example/authorize",
            "oidc_token_endpoint": TEST_TOKEN_ENDPOINT,
            "oidc_response_issuer_policy": policy,
            "oidc_authorization_response_iss_parameter_supported": (
                response_issuer_supported
            ),
        }
    )


def hosted_id_token(
    *,
    nonce: str,
    issuer: str = HOSTED_ISSUER,
    audience: str | list[str] = "apbra-local-client",
    expires_delta: timedelta = timedelta(minutes=5),
    signing_key: Any = HOSTED_PRIVATE_KEY,
    authorized_party: str | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "iss": issuer,
        "sub": "hosted-user-1",
        "aud": audience,
        "iat": int(now.timestamp()),
        "nbf": int((now - timedelta(seconds=1)).timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "nonce": nonce,
        "name": "Hosted Test User",
    }
    if authorized_party is not None:
        payload["azp"] = authorized_party
    encoded = jwt.encode(
        {"alg": "RS256", "typ": "JWT", "kid": "hosted-test-key"},
        payload,
        signing_key,
    )
    return encoded.decode() if isinstance(encoded, bytes) else str(encoded)


def hosted_login(
    settings: Settings, database: Database
) -> tuple[TestClient, str, AuthTransactionRow]:
    client = TestClient(
        create_app(settings=settings, database=database), base_url=settings.api_origin
    )
    start = client.get("/api/auth/login", follow_redirects=False)
    assert start.status_code == 302
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    with database.session() as db:
        transaction = db.scalar(
            select(AuthTransactionRow).where(AuthTransactionRow.state_digest == digest(state))
        )
        assert transaction is not None
        db.expunge(transaction)
    return client, state, transaction


def install_hosted_token_response(
    monkeypatch: pytest.MonkeyPatch,
    token: str,
    *,
    expected_verifier: str | None = None,
    used_codes: set[str] | None = None,
) -> None:
    def post(url: str, *, data: dict[str, str], timeout: float) -> httpx.Response:
        assert url == TEST_TOKEN_ENDPOINT
        assert timeout == 10.0
        if expected_verifier is not None and data["code_verifier"] != expected_verifier:
            return httpx.Response(
                400,
                json={"error": "invalid_grant"},
                request=httpx.Request("POST", url),
            )
        if used_codes is not None:
            if data["code"] in used_codes:
                return httpx.Response(
                    400,
                    json={"error": "invalid_grant"},
                    request=httpx.Request("POST", url),
                )
            used_codes.add(data["code"])
        return httpx.Response(
            200,
            json={"id_token": token, "access_token": "provider-only"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("apbra_api.oidc_adapter.httpx.post", post)


def authorization_callback(client: TestClient) -> tuple[SplitResult, dict[str, list[str]]]:
    start = client.get("/api/auth/login?identity=owner", follow_redirects=False)
    authorize_url = urlsplit(start.headers["location"])
    authorize = client.get(f"{authorize_url.path}?{authorize_url.query}", follow_redirects=False)
    callback_url = urlsplit(authorize.headers["location"])
    return callback_url, parse_qs(callback_url.query)


def test_authorization_code_pkce_session_and_callback_replay(client: TestClient) -> None:
    start = client.get("/api/auth/login?identity=owner", follow_redirects=False)
    assert start.status_code == 302
    authorize_url = urlsplit(start.headers["location"])
    parameters = parse_qs(authorize_url.query)
    assert parameters["code_challenge_method"] == ["S256"]
    assert parameters["state"][0]
    assert parameters["nonce"][0]

    authorize = client.get(f"{authorize_url.path}?{authorize_url.query}", follow_redirects=False)
    callback_url = urlsplit(authorize.headers["location"])
    callback_path = f"{callback_url.path}?{callback_url.query}"
    assert client.get(callback_path, follow_redirects=False).status_code == 302
    assert client.get(callback_path, follow_redirects=False).status_code == 401


def test_wrong_state_issuer_pkce_downgrade_and_unknown_identity_fail_closed(
    client: TestClient,
) -> None:
    assert client.get("/api/auth/login?identity=missing", follow_redirects=False).status_code == 401
    start = client.get("/api/auth/login?identity=owner", follow_redirects=False)
    authorize_url = urlsplit(start.headers["location"])
    parameters = parse_qs(authorize_url.query)
    wrong_state = client.get(
        "/api/auth/callback",
        params={"state": "wrong", "code": "wrong", "iss": "http://127.0.0.1:8000/dev/oidc"},
        follow_redirects=False,
    )
    assert wrong_state.status_code == 401
    downgraded = {key: value[0] for key, value in parameters.items()}
    downgraded["code_challenge_method"] = "plain"
    assert (
        client.get(authorize_url.path, params=downgraded, follow_redirects=False).status_code == 401
    )
    authorize = client.get(f"{authorize_url.path}?{authorize_url.query}", follow_redirects=False)
    callback_url = urlsplit(authorize.headers["location"])
    query = parse_qs(callback_url.query)
    query["iss"] = ["https://wrong.example"]
    wrong = client.get(
        callback_url.path,
        params={key: value[0] for key, value in query.items()},
        follow_redirects=False,
    )
    assert wrong.status_code == 401


def test_failed_code_exchange_burns_callback_state(client: TestClient, database: Database) -> None:
    start = client.get("/api/auth/login?identity=owner", follow_redirects=False)
    authorize_url = urlsplit(start.headers["location"])
    authorize = client.get(f"{authorize_url.path}?{authorize_url.query}", follow_redirects=False)
    callback_url = urlsplit(authorize.headers["location"])
    query = parse_qs(callback_url.query)
    with database.session() as db:
        transaction = db.scalar(
            select(AuthTransactionRow).where(
                AuthTransactionRow.state_digest == digest(query["state"][0])
            )
        )
        assert transaction is not None
        transaction.code_verifier = "wrong-verifier-that-cannot-match-the-code-challenge"
    callback_path = f"{callback_url.path}?{callback_url.query}"
    assert client.get(callback_path, follow_redirects=False).status_code == 401
    assert client.get(callback_path, follow_redirects=False).status_code == 401


@pytest.mark.parametrize("mutation", ["nonce", "redirect"])
def test_nonce_and_redirect_mismatch_fail_closed(
    client: TestClient, database: Database, mutation: str
) -> None:
    callback_url, query = authorization_callback(client)
    with database.session() as db:
        if mutation == "nonce":
            transaction = db.scalar(
                select(AuthTransactionRow).where(
                    AuthTransactionRow.state_digest == digest(query["state"][0])
                )
            )
            assert transaction is not None
            transaction.nonce = "mismatched-nonce"
        else:
            code = db.scalar(
                select(AuthorizationCodeRow).where(
                    AuthorizationCodeRow.code_digest == digest(query["code"][0])
                )
            )
            assert code is not None
            code.redirect_uri = "http://127.0.0.1:8000/not-the-callback"
    assert (
        client.get(
            callback_url.path,
            params={key: values[0] for key, values in query.items()},
            follow_redirects=False,
        ).status_code
        == 401
    )


def test_injected_code_and_missing_local_response_issuer_fail_closed(client: TestClient) -> None:
    callback_url, query = authorization_callback(client)
    injected = dict(query)
    injected["code"] = [secrets.token_urlsafe(48)]
    assert (
        client.get(
            callback_url.path,
            params={key: values[0] for key, values in injected.items()},
            follow_redirects=False,
        ).status_code
        == 401
    )

    callback_url, query = authorization_callback(client)
    query.pop("iss")
    assert (
        client.get(
            callback_url.path,
            params={key: values[0] for key, values in query.items()},
            follow_redirects=False,
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    ("policy", "advertised", "callback_issuer", "expected_status"),
    [
        ("required", True, None, 401),
        ("required", True, HOSTED_ISSUER, 302),
        ("required", True, "https://wrong.example", 401),
        ("single_issuer_compatibility", False, None, 302),
        ("single_issuer_compatibility", False, HOSTED_ISSUER, 302),
        # Trusted metadata advertising the RFC 9207 parameter makes it mandatory
        # even when the client selected the bounded compatibility policy.
        ("single_issuer_compatibility", True, None, 401),
    ],
)
def test_hosted_response_issuer_policy_through_real_callback(
    database_url: str,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    policy: str,
    advertised: bool,
    callback_issuer: str | None,
    expected_status: int,
) -> None:
    settings = hosted_settings(
        database_url, policy=policy, response_issuer_supported=advertised
    )
    client, state, transaction = hosted_login(settings, database)
    install_hosted_token_response(
        monkeypatch, hosted_id_token(nonce=transaction.nonce)
    )
    parameters = {"state": state, "code": secrets.token_urlsafe(32)}
    if callback_issuer is not None:
        parameters["iss"] = callback_issuer
    response = client.get("/api/auth/callback", params=parameters, follow_redirects=False)
    assert response.status_code == expected_status
    session = client.get("/api/auth/session").json()
    assert session["authenticated"] is (expected_status == 302)
    if expected_status == 302:
        # Authentication alone does not manufacture APBRA membership authority.
        assert client.get("/api/cases").status_code == 401


@pytest.mark.parametrize(
    "query",
    [
        [("state", "STATE"), ("code", "CODE"), ("iss", "")],
        [("state", "STATE"), ("code", "CODE"), ("iss", "not-an-issuer")],
        [("state", "STATE"), ("code", "CODE"), ("iss", HOSTED_ISSUER), ("iss", HOSTED_ISSUER)],
        [
            ("state", "STATE"),
            ("code", "CODE"),
            ("iss", HOSTED_ISSUER),
            ("iss", "https://wrong.example"),
        ],
        [("state", "STATE"), ("state", "OTHER"), ("code", "CODE")],
        [("state", "STATE"), ("code", "CODE"), ("code", "OTHER")],
    ],
)
def test_duplicate_empty_or_conflicting_callback_parameters_fail_closed(
    database_url: str,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    query: list[tuple[str, str]],
) -> None:
    settings = hosted_settings(
        database_url,
        policy="single_issuer_compatibility",
        response_issuer_supported=False,
    )
    client, state, transaction = hosted_login(settings, database)
    install_hosted_token_response(monkeypatch, hosted_id_token(nonce=transaction.nonce))
    actual = [(key, state if value == "STATE" else value) for key, value in query]
    response = client.get("/api/auth/callback", params=actual, follow_redirects=False)
    assert response.status_code == 401
    assert client.get("/api/auth/session").json() == {"authenticated": False}


def test_different_browser_and_provider_configuration_change_fail_closed(
    database_url: str, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = hosted_settings(
        database_url,
        policy="single_issuer_compatibility",
        response_issuer_supported=False,
    )
    client, state, transaction = hosted_login(settings, database)
    install_hosted_token_response(monkeypatch, hosted_id_token(nonce=transaction.nonce))
    other_browser = TestClient(
        create_app(settings=settings, database=database), base_url=settings.api_origin
    )
    assert (
        other_browser.get(
            "/api/auth/callback",
            params={"state": state, "code": "different-browser"},
            follow_redirects=False,
        ).status_code
        == 401
    )

    client, state, transaction = hosted_login(settings, database)
    install_hosted_token_response(monkeypatch, hosted_id_token(nonce=transaction.nonce))
    settings.oidc_authorization_endpoint = "https://issuer.example/changed-authorize"
    assert (
        client.get(
            "/api/auth/callback",
            params={"state": state, "code": "configuration-changed"},
            follow_redirects=False,
        ).status_code
        == 401
    )
    assert client.get("/api/auth/session").json() == {"authenticated": False}


def test_expired_callback_transaction_fails_closed(
    database_url: str, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = hosted_settings(
        database_url,
        policy="single_issuer_compatibility",
        response_issuer_supported=False,
    )
    client, state, transaction = hosted_login(settings, database)
    with database.session() as db:
        current = db.get(AuthTransactionRow, transaction.id)
        assert current is not None
        current.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    install_hosted_token_response(monkeypatch, hosted_id_token(nonce=transaction.nonce))
    assert (
        client.get(
            "/api/auth/callback",
            params={"state": state, "code": "expired-transaction"},
            follow_redirects=False,
        ).status_code
        == 401
    )
    assert client.get("/api/auth/session").json() == {"authenticated": False}


@pytest.mark.parametrize(
    "claim_case",
    ["issuer", "audience", "signature", "expired", "nonce", "azp"],
)
def test_invalid_hosted_id_token_never_creates_session(
    database_url: str,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    claim_case: str,
) -> None:
    settings = hosted_settings(
        database_url,
        policy="single_issuer_compatibility",
        response_issuer_supported=False,
    )
    client, state, transaction = hosted_login(settings, database)
    arguments: dict[str, Any] = {"nonce": transaction.nonce}
    if claim_case == "issuer":
        arguments["issuer"] = "https://wrong.example"
    elif claim_case == "audience":
        arguments["audience"] = "other-client"
    elif claim_case == "signature":
        arguments["signing_key"] = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )
    elif claim_case == "expired":
        arguments["expires_delta"] = timedelta(minutes=-1)
    elif claim_case == "nonce":
        arguments["nonce"] = "wrong-nonce"
    elif claim_case == "azp":
        arguments["audience"] = [settings.oidc_audience, "another-client"]
        arguments["authorized_party"] = "another-client"
    install_hosted_token_response(monkeypatch, hosted_id_token(**arguments))
    assert (
        client.get(
            "/api/auth/callback",
            params={"state": state, "code": f"invalid-{claim_case}"},
            follow_redirects=False,
        ).status_code
        == 401
    )
    assert client.get("/api/auth/session").json() == {"authenticated": False}


def test_multiple_id_token_audiences_require_matching_authorized_party(
    database_url: str, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = hosted_settings(
        database_url,
        policy="single_issuer_compatibility",
        response_issuer_supported=False,
    )
    client, state, transaction = hosted_login(settings, database)
    install_hosted_token_response(
        monkeypatch,
        hosted_id_token(
            nonce=transaction.nonce,
            audience=[settings.oidc_audience, "another-client"],
            authorized_party=settings.oidc_audience,
        ),
    )
    assert (
        client.get(
            "/api/auth/callback",
            params={"state": state, "code": "valid-authorized-party"},
            follow_redirects=False,
        ).status_code
        == 302
    )


def test_hosted_pkce_failure_and_reused_code_fail_closed(
    database_url: str, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = hosted_settings(
        database_url,
        policy="single_issuer_compatibility",
        response_issuer_supported=False,
    )
    client, state, transaction = hosted_login(settings, database)
    install_hosted_token_response(
        monkeypatch,
        hosted_id_token(nonce=transaction.nonce),
        expected_verifier="a-different-verifier",
    )
    assert (
        client.get(
            "/api/auth/callback",
            params={"state": state, "code": "pkce-rejected"},
            follow_redirects=False,
        ).status_code
        == 401
    )

    used_codes: set[str] = set()
    client, state, transaction = hosted_login(settings, database)
    install_hosted_token_response(
        monkeypatch, hosted_id_token(nonce=transaction.nonce), used_codes=used_codes
    )
    assert (
        client.get(
            "/api/auth/callback",
            params={"state": state, "code": "single-use-provider-code"},
            follow_redirects=False,
        ).status_code
        == 302
    )
    client.cookies.clear()
    client, state, transaction = hosted_login(settings, database)
    install_hosted_token_response(
        monkeypatch, hosted_id_token(nonce=transaction.nonce), used_codes=used_codes
    )
    assert (
        client.get(
            "/api/auth/callback",
            params={"state": state, "code": "single-use-provider-code"},
            follow_redirects=False,
        ).status_code
        == 401
    )


def test_concurrent_callback_consumption_creates_only_one_session(
    database_url: str, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = hosted_settings(
        database_url,
        policy="single_issuer_compatibility",
        response_issuer_supported=False,
    )
    app = create_app(settings=settings, database=database)
    initiating = TestClient(app, base_url=settings.api_origin)
    start = initiating.get("/api/auth/login", follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    with database.session() as db:
        transaction = db.scalar(
            select(AuthTransactionRow).where(AuthTransactionRow.state_digest == digest(state))
        )
        assert transaction is not None
        nonce = transaction.nonce
    install_hosted_token_response(monkeypatch, hosted_id_token(nonce=nonce))
    binding = initiating.cookies.get("apbra_auth_binding")
    assert binding
    barrier = Barrier(2)
    statuses: list[int] = []

    def complete() -> None:
        concurrent = TestClient(app, base_url=settings.api_origin)
        concurrent.cookies.set("apbra_auth_binding", binding, path="/api/auth/callback")
        barrier.wait()
        response = concurrent.get(
            "/api/auth/callback",
            params={"state": state, "code": "concurrent-code"},
            follow_redirects=False,
        )
        statuses.append(response.status_code)

    first = Thread(target=complete)
    second = Thread(target=complete)
    first.start()
    second.start()
    first.join()
    second.join()
    assert sorted(statuses) == [302, 401]


def test_external_return_target_is_reduced_to_safe_local_path(client: TestClient) -> None:
    start = client.get(
        "/api/auth/login",
        params={"identity": "owner", "return_to": "https://attacker.example/steal"},
        follow_redirects=False,
    )
    authorize_url = urlsplit(start.headers["location"])
    authorize = client.get(f"{authorize_url.path}?{authorize_url.query}", follow_redirects=False)
    callback_url = urlsplit(authorize.headers["location"])
    callback = client.get(f"{callback_url.path}?{callback_url.query}", follow_redirects=False)
    assert callback.headers["location"] == "http://127.0.0.1:5173/"


def test_provider_tokens_are_not_returned_to_browser(client: TestClient) -> None:
    session = sign_in(client)
    body = str(session).lower()
    assert "id_token" not in body
    assert "access_token" not in body
    assert "refresh_token" not in body


def test_repeated_independent_sign_ins_use_distinct_valid_one_time_state(
    client: TestClient,
) -> None:
    first = sign_in(client, "owner")
    client.cookies.clear()
    second = sign_in(client, "owner")
    assert first["actor"] == second["actor"]


def test_csrf_and_cookie_security_profiles(client: TestClient) -> None:
    start = client.get("/api/auth/login?identity=owner", follow_redirects=False)
    authorize_url = urlsplit(start.headers["location"])
    authorize = client.get(f"{authorize_url.path}?{authorize_url.query}", follow_redirects=False)
    callback_url = urlsplit(authorize.headers["location"])
    callback = client.get(f"{callback_url.path}?{callback_url.query}", follow_redirects=False)
    cookie = callback.headers["set-cookie"].lower()
    assert f"{SESSION_COOKIE}=" in cookie
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 401

    hosted = Settings(
        profile="hosted",
        database_url="postgresql+psycopg://db.example/apbra",
        public_origin="https://app.example",
        api_origin="https://api.example",
        session_secret=TEST_SESSION_SECRET,
        bootstrap_enabled=False,
        oidc_issuer="https://issuer.example/tenant/v2.0",
        oidc_jwks_json='{"keys":[]}',
        oidc_authorization_endpoint="https://issuer.example/authorize",
        oidc_token_endpoint=TEST_TOKEN_ENDPOINT,
    )
    hosted.validate_security_profile()
    assert cookie_secure(hosted)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("public_origin", "https://"),
        ("api_origin", "https://:password@api.example"),
        ("oidc_issuer", "http://issuer.example/tenant"),
        ("oidc_authorization_endpoint", "http://issuer.example/authorize"),
        ("oidc_token_endpoint", "http://issuer.example/token"),
    ],
)
def test_hosted_profile_rejects_malformed_or_unsafe_urls(field: str, value: str) -> None:
    values: dict[str, object] = {
        "profile": "hosted",
        "database_url": "postgresql+psycopg://db.example/apbra",
        "public_origin": "https://app.example",
        "api_origin": "https://api.example",
        "session_secret": TEST_SESSION_SECRET,
        "bootstrap_enabled": False,
        "oidc_issuer": "https://issuer.example/tenant/v2.0",
        "oidc_jwks_json": '{"keys":[]}',
        "oidc_authorization_endpoint": "https://issuer.example/authorize",
        "oidc_token_endpoint": TEST_TOKEN_ENDPOINT,
    }
    values[field] = value
    with pytest.raises(ValueError):
        settings = Settings.model_validate(values)
        settings.validate_security_profile()


def test_local_profile_cannot_enable_response_issuer_compatibility(
    database_url: str,
) -> None:
    settings = Settings(
        profile="test",
        database_url=database_url,
        public_origin="http://127.0.0.1:5173",
        api_origin="http://127.0.0.1:8000",
        session_secret=TEST_SESSION_SECRET,
        oidc_response_issuer_policy="single_issuer_compatibility",
    )
    with pytest.raises(ValueError, match="strict response-issuer policy"):
        settings.validate_security_profile()
