"""Wholly synthetic accounts/mail; never an owner's identity, inbox or database."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from apbra_api.api import create_app
from apbra_api.password_auth import (
    COOKIE,
    PATH,
    PRE_COOKIE,
    CaptureMailer,
    PasswordAccountRow,
    PasswordAuditRow,
    PasswordAuthSettings,
    PasswordProofRow,
    PasswordSessionRow,
    SmtpMailer,
    digest,
    normalized_email,
    password_hash,
    password_matches,
    password_value,
    register_password_routes,
)

EMAIL = "account@example.org"
FIRST_PHRASE = "Synthetic violet orchard river 284!"
OTHER = "Synthetic silver mountain cloud 539!"


@pytest.fixture
def flow(settings, migrated_database):
    mail = CaptureMailer()
    cfg = settings
    feature = PasswordAuthSettings(_env_file=None, password_auth_enabled=True)
    now = [datetime.now(UTC)]
    app = FastAPI()
    register_password_routes(
        app, migrated_database, cfg, mail, lambda: now[0], password_settings=feature
    )
    client = TestClient(app)
    csrf = client.get(PATH + "/options").json()["csrf"]
    headers = {"Origin": cfg.public_origin, "X-Password-CSRF": csrf}

    def post(action, data):
        return client.post(PATH + "/" + action, json=data, headers=headers)

    return client, post, mail, migrated_database, now, app, headers


def signup(flow, password=FIRST_PHRASE):
    _, post, mail, *_ = flow
    assert post("signup", {"email": EMAIL, "password": password}).status_code == 202
    assert len(mail.messages) >= 1
    return mail.messages[-1][2]


def verified(flow):
    proof = signup(flow)
    assert flow[1]("verify", {"proof": proof, "password": FIRST_PHRASE}).status_code == 200
    return proof


def test_complete_signup_verified_signin_and_logout(flow):
    client, post, mail, db, *_ = flow
    proof = signup(flow)
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(PasswordAccountRow)) == 0
        row = session.get(PasswordProofRow, digest(proof))
        assert row.password_hash.startswith("$argon2id$")
        assert FIRST_PHRASE not in row.password_hash and proof != row.digest
    assert post("signin", {"email": EMAIL, "password": FIRST_PHRASE}).status_code == 401
    assert (
        post("verify", {"proof": proof, "password": FIRST_PHRASE}).json()["status"]
        == "EMAIL_VERIFIED_SIGN_IN_REQUIRED"
    )
    assert not client.cookies.get(COOKIE)  # No automatic login via verification.
    assert post("signin", {"email": EMAIL, "password": FIRST_PHRASE}).status_code == 200
    token = client.cookies.get(COOKIE)
    state = client.get(PATH + "/session").json()
    assert state["authenticated"] and state["account"]["email"] == EMAIL
    assert state["workspace_access"] is False
    assert state["next_step"] == "ORGANISATION_SETUP_NOT_IMPLEMENTED"
    with db.session() as session:
        assert session.get(PasswordSessionRow, digest(token)) is not None
        assert session.scalar(select(func.count()).select_from(PasswordAccountRow)) == 1
    response = post("signout", {})
    assert response.status_code == 200 and not client.cookies.get(COOKIE)
    client.cookies.set(COOKIE, token, path=PATH)
    assert not client.get(PATH + "/session").json()["authenticated"]
    assert mail.messages[0][:2] == (EMAIL, "verify")


def test_proof_wrong_password_purpose_replay_and_expiry(flow):
    proof = signup(flow)
    post = flow[1]
    assert post("verify", {"proof": proof, "password": OTHER}).status_code == 400
    assert post("reset", {"proof": proof, "password": OTHER}).status_code == 400
    assert post("verify", {"proof": proof, "password": FIRST_PHRASE}).status_code == 200
    assert post("verify", {"proof": proof, "password": FIRST_PHRASE}).status_code == 400
    flow[4][0] += timedelta(minutes=31)
    # Refresh pre-CSRF after advancing its clock.
    flow[6]["X-Password-CSRF"] = flow[0].get(PATH + "/options").json()["csrf"]
    assert post("verify", {"proof": proof, "password": FIRST_PHRASE}).status_code == 400


def test_reset_revokes_only_native_account_sessions_and_old_password(flow):
    verified(flow)
    client, post, mail, db, *_ = flow
    assert post("signin", {"email": EMAIL, "password": FIRST_PHRASE}).status_code == 200
    old = client.cookies.get(COOKIE)
    assert post("recover", {"email": EMAIL}).status_code == 202
    proof = mail.messages[-1][2]
    assert post("reset", {"proof": proof, "password": OTHER}).status_code == 200
    assert not client.get(PATH + "/session").json()["authenticated"]
    assert post("signin", {"email": EMAIL, "password": FIRST_PHRASE}).status_code == 401
    assert post("signin", {"email": EMAIL, "password": OTHER}).status_code == 200
    assert post("reset", {"proof": proof, "password": OTHER}).status_code == 400
    with db.session() as session:
        assert session.get(PasswordSessionRow, digest(old)).revoked_at is not None
        assert session.scalar(select(PasswordAccountRow)).epoch == 2


def test_duplicate_registration_cannot_overwrite_or_merge_legacy(flow, settings):
    with flow[3].session() as session:
        memberships_before = session.execute(
            text("SELECT id, company_id, identity_id, role, active FROM memberships ORDER BY id")
        ).all()
        identities_before = session.execute(
            text(
                "SELECT id, provider_profile_id, issuer, subject, active "
                "FROM external_identities ORDER BY id"
            )
        ).all()
    verified(flow)
    post, mail, db = flow[1:4]
    count = len(mail.messages)
    assert post("signup", {"email": EMAIL.upper(), "password": OTHER}).status_code == 202
    assert len(mail.messages) == count
    assert post("signin", {"email": EMAIL.upper(), "password": OTHER}).status_code == 401
    assert post("signin", {"email": EMAIL, "password": FIRST_PHRASE}).status_code == 200
    with db.session() as session:
        assert (
            session.execute(
                text(
                    "SELECT id, company_id, identity_id, role, active FROM memberships ORDER BY id"
                )
            ).all()
            == memberships_before
        )
        assert (
            session.execute(
                text(
                    "SELECT id, provider_profile_id, issuer, subject, active "
                    "FROM external_identities ORDER BY id"
                )
            ).all()
            == identities_before
        )
    # New native cookie is neither read nor recognized by the existing app auth.
    legacy = TestClient(create_app(settings, db))
    legacy.cookies.set("apbra_session", flow[0].cookies.get(COOKIE), path="/")
    assert legacy.get("/api/auth/session").json()["authenticated"] is False
    assert legacy.get("/api/cases").status_code == 401


def test_generic_unknown_signin_recovery_and_signup(flow):
    _, post, mail, *_ = flow
    first = post("signin", {"email": EMAIL, "password": FIRST_PHRASE})
    assert first.status_code == 401 and first.json() == {"status": "SIGNIN_FAILED"}
    unknown = post("recover", {"email": EMAIL})
    assert unknown.status_code == 202 and not mail.messages
    verified(flow)
    known = post("recover", {"email": EMAIL})
    assert known.status_code == unknown.status_code == 202
    for response in (known, unknown):
        assert set(response.json()) == {"status", "support_reference"}
        assert response.json()["status"] == "REQUEST_ACCEPTED"
        assert UUID(response.json()["support_reference"]).version == 4
    assert known.json()["support_reference"] != unknown.json()["support_reference"]


def test_csrf_origin_content_limits_no_credential_echo(flow):
    client, post, _, _, _, _, headers = flow
    credentials = {"email": EMAIL, "password": FIRST_PHRASE}
    for supplied in [
        {},
        {"Origin": "http://evil.invalid", "X-Password-CSRF": headers["X-Password-CSRF"]},
        {"Origin": headers["Origin"], "X-Password-CSRF": "wrong"},
    ]:
        response = client.post(PATH + "/signin", json=credentials, headers=supplied)
        assert (
            response.status_code == 403
            and FIRST_PHRASE not in response.text
            and EMAIL not in response.text
        )
    response = client.post(
        PATH + "/signup",
        content='{"password":"' + FIRST_PHRASE + '","password":"x"}',
        headers={**headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 400 and FIRST_PHRASE not in response.text
    response = client.post(
        PATH + "/signup",
        content="x" * 8193,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert (
        post("signup", {"email": EMAIL, "password": {"sensitive": FIRST_PHRASE}}).status_code == 400
    )
    assert (
        post(
            "signup", {"email": EMAIL, "password": FIRST_PHRASE, "company_id": "injected"}
        ).status_code
        == 400
    )


def test_throttle_before_repeated_hashing_and_short_existing_signin(flow, monkeypatch):
    post = flow[1]
    # Sign-in accepts a short password as input; strength rules belong to signup/reset.
    assert post("signin", {"email": EMAIL, "password": "short"}).status_code == 401
    calls = []
    monkeypatch.setattr(
        "apbra_api.password_auth.password_matches", lambda *_: calls.append(1) or False
    )
    for _ in range(4):
        assert post("signin", {"email": EMAIL, "password": FIRST_PHRASE}).status_code == 401
    assert post("signin", {"email": EMAIL, "password": FIRST_PHRASE}).status_code == 429
    assert len(calls) == 4


def test_session_rotation_absolute_and_idle_expiry(flow):
    verified(flow)
    client, post, *_ = flow
    post("signin", {"email": EMAIL, "password": FIRST_PHRASE})
    first = client.cookies.get(COOKIE)
    post("signin", {"email": EMAIL, "password": FIRST_PHRASE})
    second = client.cookies.get(COOKIE)
    assert first != second
    client.cookies.set(COOKIE, first, path=PATH)
    assert not client.get(PATH + "/session").json()["authenticated"]
    client.cookies.set(COOKIE, second, path=PATH)
    flow[4][0] += timedelta(minutes=31)
    assert not client.get(PATH + "/session").json()["authenticated"]


def test_no_mail_route_disables_registration_but_not_password_service(settings, migrated_database):
    app = FastAPI()
    cfg = settings
    feature = PasswordAuthSettings(_env_file=None, password_auth_enabled=True)
    register_password_routes(app, migrated_database, cfg, password_settings=feature)
    client = TestClient(app)
    options = client.get(PATH + "/options").json()
    assert options["enabled"] and not options["registration"] and not options["recovery"]
    response = client.post(
        PATH + "/signup",
        json={"email": EMAIL, "password": FIRST_PHRASE},
        headers={"Origin": cfg.public_origin, "X-Password-CSRF": options["csrf"]},
    )
    assert response.status_code == 503
    with migrated_database.session() as db:
        assert db.scalar(select(func.count()).select_from(PasswordAccountRow)) == 0


def test_mail_failure_does_not_claim_delivery_or_leave_live_proof(flow, monkeypatch):
    def failed(*_):
        raise RuntimeError("synthetic secret-bearing SMTP error must never escape")

    monkeypatch.setattr(flow[2], "send", failed)
    response = flow[1]("signup", {"email": EMAIL, "password": FIRST_PHRASE})
    assert set(response.json()) == {"status", "support_reference"}
    assert response.json()["status"] == "REQUEST_ACCEPTED" and "secret" not in response.text
    assert UUID(response.json()["support_reference"]).version == 4
    with flow[3].session() as db:
        assert db.scalar(select(PasswordProofRow)).consumed_at is not None
        assert "MAIL_FAILED" in db.scalars(select(PasswordAuditRow.event)).all()


def test_capture_injection_forbidden_outside_test(settings, migrated_database):
    with pytest.raises(ValueError, match="TEST_ONLY"):
        register_password_routes(
            FastAPI(),
            migrated_database,
            settings.model_copy(update={"profile": "development"}),
            CaptureMailer(),
        )


def test_atomic_single_redemption(flow):
    proof = signup(flow)
    app, headers = flow[5], flow[6]
    pre = flow[0].cookies.get(PRE_COOKIE)

    def redeem(_):
        with TestClient(app) as client:
            client.cookies.set(PRE_COOKIE, pre, path=PATH)
            return client.post(
                PATH + "/verify", json={"proof": proof, "password": FIRST_PHRASE}, headers=headers
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(redeem, range(2))) == [200, 400]
    with flow[3].session() as db:
        assert db.scalar(select(func.count()).select_from(PasswordAccountRow)) == 1


def test_hash_normalization_policy_and_email():
    assert password_value("short", new=False) == "short"
    with pytest.raises(ValueError):
        password_value("short", new=True)
    with pytest.raises(ValueError):
        password_value("1234567890123456", new=True)
    long = "Synthetic " + "é" * 100
    encoded = password_hash(password_value(long, new=True))
    assert password_matches(encoded, password_value("Synthetic " + "e\u0301" * 100, new=False))
    assert not password_matches(encoded, OTHER)
    assert normalized_email("Reader+tag@EXAMPLE.ORG")[1] == "reader+tag@example.org"
    assert (
        normalized_email("reader.tag@example.org")[1]
        != normalized_email("readertag@example.org")[1]
    )
    with pytest.raises(ValueError):
        normalized_email("bad\r\n@example.org")


def test_expired_unused_verify_proof(flow):
    proof = signup(flow)
    flow[4][0] += timedelta(minutes=31)
    flow[6]["X-Password-CSRF"] = flow[0].get(PATH + "/options").json()["csrf"]
    assert flow[1]("verify", {"proof": proof, "password": FIRST_PHRASE}).status_code == 400
    with flow[3].session() as db:
        assert db.get(PasswordProofRow, digest(proof)).consumed_at is None
        assert db.scalar(select(func.count()).select_from(PasswordAccountRow)) == 0


def test_recovery_uses_verified_delivery_spelling_and_atomic_reset(flow):
    verified(flow)
    post, mail, db = flow[1:4]
    post("signin", {"email": EMAIL, "password": FIRST_PHRASE})
    assert post("recover", {"email": EMAIL.upper()}).status_code == 202
    assert mail.messages[-1][0] == EMAIL
    proof = mail.messages[-1][2]
    pre = flow[0].cookies.get(PRE_COOKIE)

    def reset(_):
        with TestClient(flow[5]) as client:
            client.cookies.set(PRE_COOKIE, pre, path=PATH)
            return client.post(
                PATH + "/reset", json={"proof": proof, "password": OTHER}, headers=flow[6]
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reset, range(2))) == [200, 400]
    with db.session() as session:
        assert session.scalar(select(PasswordAccountRow)).epoch == 2


def test_reset_expiry_and_unrelated_sessions_preserved(flow, settings):
    from conftest import sign_in

    from apbra_api.persistence import SessionRow

    verified(flow)
    post, mail, db = flow[1:4]
    legacy = TestClient(create_app(settings, db))
    sign_in(legacy, "owner")
    with db.session() as session:
        before = [(r.id, r.revoked_at) for r in session.scalars(select(SessionRow)).all()]
        other_id = uuid4()
        session.add(
            PasswordAccountRow(
                id=other_id,
                email_key="other@example.org",
                email="other@example.org",
                password_hash=password_hash(OTHER),
                epoch=1,
                active=True,
            )
        )
        session.flush()
        other_digest = digest("b" * 43)
        session.add(
            PasswordSessionRow(
                digest=other_digest,
                account_id=other_id,
                epoch=1,
                expires_at=flow[4][0] + timedelta(hours=8),
                touched_at=flow[4][0],
            )
        )
    post("recover", {"email": EMAIL})
    expired = mail.messages[-1][2]
    flow[4][0] += timedelta(minutes=16)
    assert post("reset", {"proof": expired, "password": OTHER}).status_code == 400
    post("recover", {"email": EMAIL})
    fresh = mail.messages[-1][2]
    assert post("reset", {"proof": fresh, "password": OTHER}).status_code == 200
    with db.session() as session:
        assert session.get(PasswordSessionRow, other_digest).revoked_at is None
        assert [(r.id, r.revoked_at) for r in session.scalars(select(SessionRow)).all()] == before
    assert legacy.get("/api/auth/session").json()["authenticated"] is True


def test_absolute_session_expiry_without_idle_expiry(flow):
    verified(flow)
    flow[1]("signin", {"email": EMAIL, "password": FIRST_PHRASE})
    flow[4][0] += timedelta(hours=8, seconds=1)
    with flow[3].session() as db:
        row = db.scalar(select(PasswordSessionRow))
        row.touched_at = flow[4][0]
    assert not flow[0].get(PATH + "/session").json()["authenticated"]


def test_additive_migration_preserves_old_rows_and_refuses_lossy_rollback(flow, settings):
    from conftest import disposable_alembic_config

    from alembic import command

    db = flow[3]
    with db.session() as session:
        before = session.execute(text("SELECT id,name,active FROM companies ORDER BY id")).all()
    config = disposable_alembic_config(settings.database_url)
    command.downgrade(config, "20261105_16")
    command.upgrade(config, "head")
    with db.session() as session:
        assert (
            session.execute(text("SELECT id,name,active FROM companies ORDER BY id")).all()
            == before
        )
    signup(flow)
    with pytest.raises(RuntimeError, match="Retained password"):
        command.downgrade(config, "20261105_16")
    with db.session() as session:
        assert (
            session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "20261106_17"
        )
        assert (
            session.execute(text("SELECT id,name,active FROM companies ORDER BY id")).all()
            == before
        )
        assert session.scalar(select(func.count()).select_from(PasswordProofRow)) == 1


def test_malformed_csrf_and_nested_json_are_controlled(flow):
    client, _, _, _, _, _, headers = flow
    for value in ["é" * 64, "x" * 10000, "A" * 64, "", "0" * 63]:
        response = client.post(
            PATH + "/signin",
            json={"email": EMAIL, "password": FIRST_PHRASE},
            headers={**headers, "X-Password-CSRF": value.encode("latin-1")},
        )
        assert response.status_code == 403
        assert FIRST_PHRASE not in response.text and EMAIL not in response.text
    response = client.post(
        PATH + "/signin",
        content="[" * 3000 + "0" + "]" * 3000,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 400


def test_expiry_after_waiting_for_proof_lock(flow):
    import time

    proof = signup(flow)
    app, headers = flow[5], flow[6]
    pre = flow[0].cookies.get(PRE_COOKIE)
    with flow[3].session() as lock:
        lock.scalar(
            select(PasswordProofRow)
            .where(PasswordProofRow.digest == digest(proof))
            .with_for_update()
        )

        def redeem():
            with TestClient(app) as client:
                client.cookies.set(PRE_COOKIE, pre, path=PATH)
                return client.post(
                    PATH + "/verify",
                    json={"proof": proof, "password": FIRST_PHRASE},
                    headers=headers,
                ).status_code

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(redeem)
            deadline = time.monotonic() + 5
            waiting = False
            while time.monotonic() < deadline:
                with flow[3].session() as probe:
                    waiting = bool(
                        probe.execute(
                            text(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE wait_event_type='Lock' AND query LIKE '%password_proofs%'"
                            )
                        ).scalar_one()
                    )
                if waiting:
                    break
                time.sleep(0.01)
            if waiting:
                flow[4][0] += timedelta(minutes=31)
            lock.commit()
            result = pending.result(timeout=5)
            assert waiting
            assert result == 400
    with flow[3].session() as db:
        assert db.scalar(select(func.count()).select_from(PasswordAccountRow)) == 0
        assert db.get(PasswordProofRow, digest(proof)).consumed_at is None


def test_expiry_after_waiting_for_reset_account_lock(flow):
    import time

    verified(flow)
    flow[1]("recover", {"email": EMAIL})
    proof = flow[2].messages[-1][2]
    pre = flow[0].cookies.get(PRE_COOKIE)
    with flow[3].session() as lock:
        lock.scalar(select(PasswordAccountRow).with_for_update())

        def reset():
            with TestClient(flow[5]) as client:
                client.cookies.set(PRE_COOKIE, pre, path=PATH)
                return client.post(
                    PATH + "/reset", json={"proof": proof, "password": OTHER}, headers=flow[6]
                ).status_code

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(reset)
            deadline = time.monotonic() + 5
            waiting = False
            while time.monotonic() < deadline:
                with flow[3].session() as probe:
                    waiting = bool(
                        probe.execute(
                            text(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE wait_event_type='Lock' AND query LIKE '%password_accounts%'"
                            )
                        ).scalar_one()
                    )
                if waiting:
                    break
                time.sleep(0.01)
            if waiting:
                flow[4][0] += timedelta(minutes=16)
            lock.commit()
            result = pending.result(timeout=5)
            assert waiting and result == 400
    with flow[3].session() as db:
        account = db.scalar(select(PasswordAccountRow))
        assert account.epoch == 1 and password_matches(account.password_hash, FIRST_PHRASE)


def test_smtp_adapter_requires_verified_tls_and_fixed_fragment_link(settings, monkeypatch):
    import ssl

    from pydantic import SecretStr

    calls = []
    messages = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.example.org", 587, 10)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def ehlo(self):
            calls.append("ehlo")

        def starttls(self, context):
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
            calls.append("tls")

        def login(self, *args):
            calls.append("login")

        def send_message(self, message):
            messages.append(message)
            calls.append("send")

    monkeypatch.setattr("apbra_api.password_auth.smtplib.SMTP", FakeSMTP)
    smtp_host, sender, username = "smtp.example.org", "APBRA@example.org", "fixture"
    cfg = PasswordAuthSettings(
        _env_file=None,
        password_smtp_host=smtp_host,
        password_smtp_port=587,
        password_mail_from=sender,
        password_smtp_username=username,
        password_smtp_password=SecretStr("synthetic-fixture-not-a-real-mail-credential"),
    )
    SmtpMailer(cfg, settings.public_origin).send(EMAIL, "verify", "a" * 43)
    assert calls == ["ehlo", "tls", "ehlo", "login", "send"]
    body = messages[0].get_content()
    assert settings.public_origin + "/account#account_action=verify&proof=" in body
    assert "?proof=" not in body and messages[0]["To"] == EMAIL


def test_smtp_config_rejects_plaintext_transport_and_header_injection(settings):
    smtp_host, sender = "smtp.example.org", "sender@example.org"
    injected_sender = "bad\r\nInjected@example.org"
    with pytest.raises(ValueError, match="TLS"):
        SmtpMailer(
            PasswordAuthSettings(
                _env_file=None,
                password_smtp_host=smtp_host,
                password_smtp_port=25,
                password_mail_from=sender,
            ),
            settings.public_origin,
        )
    with pytest.raises(ValueError, match="EMAIL_INVALID"):
        SmtpMailer(
            PasswordAuthSettings(
                _env_file=None,
                password_smtp_host=smtp_host,
                password_mail_from=injected_sender,
            ),
            settings.public_origin,
        )


def test_feature_settings_default_off_without_mutating_core(settings, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in PasswordAuthSettings.model_fields:
        monkeypatch.delenv("APBRA_" + name.upper(), raising=False)
        assert name not in type(settings).model_fields
        assert not hasattr(settings, name)
    feature = PasswordAuthSettings(_env_file=None)
    assert not feature.password_auth_enabled
    assert feature.password_smtp_host is None and feature.password_smtp_password is None


def test_feature_settings_env_dotenv_precedence_and_secret_repr(monkeypatch, tmp_path):
    from pydantic import ValidationError

    monkeypatch.chdir(tmp_path)
    for name in PasswordAuthSettings.model_fields:
        monkeypatch.delenv("APBRA_" + name.upper(), raising=False)
    (tmp_path / ".env").write_text(
        "APBRA_PASSWORD_AUTH_ENABLED=true\n"
        "APBRA_PASSWORD_SMTP_HOST=smtp.fixture.example\n"
        "APBRA_PASSWORD_SMTP_USERNAME=synthetic-user\n"
        "APBRA_PASSWORD_SMTP_PASSWORD=synthetic-password\n"
        "APBRA_PUBLIC_ORIGIN=https://untrusted.fixture.example\n"
    )
    feature = PasswordAuthSettings()
    assert feature.password_auth_enabled
    expected_host = "smtp.fixture.example"
    assert feature.password_smtp_host == expected_host
    assert not hasattr(feature, "public_origin")
    assert "synthetic-user" not in repr(feature) and "synthetic-password" not in repr(feature)
    assert not PasswordAuthSettings(_env_file=None).password_auth_enabled
    monkeypatch.setenv("APBRA_PASSWORD_AUTH_ENABLED", "false")
    assert not PasswordAuthSettings().password_auth_enabled
    assert PasswordAuthSettings(password_auth_enabled=True).password_auth_enabled
    with pytest.raises(ValidationError):
        PasswordAuthSettings(_env_file=None, password_smtp_port=0)
    with pytest.raises(ValidationError):
        feature.password_auth_enabled = False


def test_legacy_model_copy_extra_does_not_enable_password_routes(
    settings, migrated_database, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    for name in PasswordAuthSettings.model_fields:
        monkeypatch.delenv("APBRA_" + name.upper(), raising=False)
    core = settings.model_copy(update={"password_auth_enabled": True})
    app = FastAPI()
    register_password_routes(app, migrated_database, core)
    result = TestClient(app).get(PATH + "/options").json()
    assert result["enabled"] is False and result["registration"] is False


def test_existing_verified_account_signin_still_works_without_mail(flow, settings):
    verified(flow)
    app = FastAPI()
    register_password_routes(
        app,
        flow[3],
        settings,
        password_settings=PasswordAuthSettings(_env_file=None, password_auth_enabled=True),
    )
    client = TestClient(app)
    options = client.get(PATH + "/options").json()
    assert options["enabled"] and not options["registration"] and not options["recovery"]
    result = client.post(
        PATH + "/signin",
        json={"email": EMAIL, "password": FIRST_PHRASE},
        headers={"Origin": settings.public_origin, "X-Password-CSRF": options["csrf"]},
    )
    assert result.status_code == 200
    assert result.json() == {
        "status": "SIGNED_IN",
        "workspace_access": False,
        "next_step": "ORGANISATION_SETUP_NOT_IMPLEMENTED",
    }
    session = client.get(PATH + "/session").json()
    assert session["authenticated"] and session["workspace_access"] is False


def test_application_factory_passes_explicit_feature_settings(settings, migrated_database):
    app = create_app(
        settings,
        migrated_database,
        password_settings=PasswordAuthSettings(_env_file=None, password_auth_enabled=True),
    )
    client = TestClient(app)
    result = client.get(PATH + "/options").json()
    assert result["enabled"] and not result["registration"] and not result["recovery"]
    assert client.get(PATH + "/session").json()["authenticated"] is False
    assert client.get("/api/cases").status_code == 401


@pytest.mark.parametrize("action", ["signup", "recover"])
@pytest.mark.parametrize("failure", ["rejected", "timeout", "disconnect", "unexpected"])
def test_delivery_failure_reference_and_explicit_new_request(
    flow, monkeypatch, caplog, action, failure
):
    import logging
    import smtplib

    if action == "recover":
        verified(flow)
    mail = flow[2]
    original = mail.send
    attempts = []
    errors = {
        "rejected": smtplib.SMTPDataError(550, b"private smtp diagnostic"),
        "timeout": TimeoutError("private smtp diagnostic"),
        "disconnect": smtplib.SMTPServerDisconnected("private smtp diagnostic"),
        "unexpected": RuntimeError("private smtp diagnostic"),
    }

    def fail_after_message(recipient, purpose, proof):
        attempts.append(1)
        original(recipient, purpose, proof)  # May have reached the recipient before failure.
        raise errors[failure]

    # Alembic fileConfig disables pre-existing loggers in the migration fixture.
    # Model the explicitly enabled protected operator sink, without changing app policy.
    monkeypatch.setattr(logging.getLogger("apbra.password_email"), "disabled", False)
    caplog.set_level(logging.INFO, logger="apbra.password_email")
    monkeypatch.setattr(mail, "send", fail_after_message)
    payload = {"email": EMAIL, **({"password": FIRST_PHRASE} if action == "signup" else {})}
    result = flow[1](action, payload)
    body = result.json()
    assert result.status_code == 202 and body["status"] == "REQUEST_ACCEPTED"
    assert set(body) == {"status", "support_reference"}
    assert UUID(body["support_reference"]).version == 4
    assert attempts == [1]
    proof = mail.messages[-1][2]
    with flow[3].session() as db:
        assert db.get(PasswordProofRow, digest(proof)).consumed_at is not None
    redeem = "verify" if action == "signup" else "reset"
    password = FIRST_PHRASE if action == "signup" else OTHER
    assert flow[1](redeem, {"proof": proof, "password": password}).status_code == 400
    records = [r.getMessage() for r in caplog.records if r.name == "apbra.password_email"]
    assert any(body["support_reference"] in r for r in records)
    expected = "SUBMISSION_REJECTED" if failure == "rejected" else (
        "SUBMISSION_UNCONFIRMED" if failure in {"timeout", "disconnect"} else "SUBMISSION_FAILED"
    )
    assert any(expected in r for r in records)
    for forbidden in [EMAIL, FIRST_PHRASE, OTHER, proof, "private smtp diagnostic"]:
        assert forbidden not in " ".join(records) and forbidden not in result.text
    assert flow[0].get(PATH + "/requests/" + body["support_reference"]).status_code == 404
    # Neither a session/read nor a failed redemption causes an automatic retry.
    flow[0].get(PATH + "/session")
    assert attempts == [1]
    monkeypatch.setattr(mail, "send", original)
    before = len(mail.messages)
    retried = flow[1](action, payload)
    assert retried.status_code == 202 and len(mail.messages) == before + 1
    assert retried.json()["support_reference"] != body["support_reference"]
    fresh = mail.messages[-1][2]
    assert fresh != proof
    assert flow[1](redeem, {"proof": fresh, "password": password}).status_code == 200


def test_support_reference_never_identifies_account_or_proof_or_discloses_duplicates(flow):
    first = flow[1]("signup", {"email": EMAIL, "password": FIRST_PHRASE})
    proof = flow[2].messages[-1][2]
    assert flow[1]("verify", {"proof": proof, "password": FIRST_PHRASE}).status_code == 200
    count = len(flow[2].messages)
    duplicate = flow[1]("signup", {"email": EMAIL, "password": OTHER})
    unknown = flow[1]("recover", {"email": "unknown@example.org"})
    assert len(flow[2].messages) == count
    references = []
    with flow[3].session() as db:
        account = db.scalar(select(PasswordAccountRow))
        for response in [first, duplicate, unknown]:
            assert response.status_code == 202
            body = response.json()
            assert set(body) == {"status", "support_reference"}
            assert body["status"] == "REQUEST_ACCEPTED"
            reference = body["support_reference"]
            assert UUID(reference).version == 4 and reference != str(account.id)
            assert reference not in {proof, digest(proof)}
            references.append(reference)
    assert len(set(references)) == 3


def test_manual_requests_preserve_throttle_and_one_attempt(flow):
    for _ in range(5):
        assert flow[1]("signup", {"email": EMAIL, "password": FIRST_PHRASE}).status_code == 202
    assert len(flow[2].messages) == 5
    limited = flow[1]("signup", {"email": EMAIL, "password": FIRST_PHRASE})
    assert limited.status_code == 429 and limited.json() == {"status": "TRY_LATER"}
    assert len(flow[2].messages) == 5
