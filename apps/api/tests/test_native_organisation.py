"""Synthetic native accounts only, disposable database, no external mail/provider."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from apbra_api.api import create_app
from apbra_api.auth_boundary import SESSION_COOKIE
from apbra_api.native_organisation import NativeAccountPrincipalRow, NativeWorkspaceSessionRow
from apbra_api.password_auth import (
    COOKIE,
    PATH,
    CaptureMailer,
    PasswordAccountRow,
    PasswordAuthSettings,
    PasswordSessionRow,
    digest,
    password_hash,
)
from apbra_api.persistence import CompanyRow, ExternalIdentityRow, MembershipRow, SessionRow

EMAIL = "native-owner@example.org"
PHRASE = "Synthetic orchid horizon cedar 281!"


@pytest.fixture
def native(settings, migrated_database):
    with migrated_database.session() as db:
        account = PasswordAccountRow(
            email_key=EMAIL,
            email=EMAIL,
            password_hash=password_hash(PHRASE),
        )
        db.add(account)
        db.flush()
        account_id = account.id
    app = create_app(
        settings,
        migrated_database,
        password_mailer=CaptureMailer(),
        password_settings=PasswordAuthSettings(_env_file=None, password_auth_enabled=True),
    )
    client = TestClient(app)
    challenge = client.get(PATH + "/options").json()
    headers = {"Origin": settings.public_origin, "X-Password-CSRF": challenge["csrf"]}
    assert (
        client.post(
            PATH + "/signin", json={"email": EMAIL, "password": PHRASE}, headers=headers
        ).status_code
        == 200
    )

    def post(action, data=None, key="native-first-command", target=None):
        return (target or client).post(
            PATH + "/" + action, json=data or {}, headers={**headers, "Idempotency-Key": key}
        )

    return client, post, migrated_database, account_id, settings, headers, app


def create(native, name="Synthetic Orchard"):
    response = native[1]("organisation", {"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def test_native_full_journey_actual_workspace_and_return(native):
    client, post, db, _, _, headers, _ = native
    assert client.get("/api/cases").status_code == 401
    assert client.get(PATH + "/session").json()["next_step"] == "ORGANISATION_REQUIRED"
    created = create(native)
    session = client.get("/api/auth/session").json()
    assert session["actor"]["company_id"] == created["company"]["id"]
    assert session["actor"]["company_name"] == "Synthetic Orchard"
    assert session["actor"]["role"] == "COMPANY_OWNER"
    assert session["authentication_kind"] == "NATIVE"
    assert client.get("/api/cases").json() == {"items": []}
    assert client.get(PATH + "/session").json()["workspace_access"] is True
    before = created["membership"]["id"]
    assert post("signout").status_code == 200
    assert client.get("/api/cases").status_code == 401
    assert (
        client.post(
            PATH + "/signin", json={"email": EMAIL, "password": PHRASE}, headers=headers
        ).status_code
        == 200
    )
    assert post("workspace").status_code == 200
    assert client.get("/api/auth/session").json()["actor"]["membership_id"] == before
    with db.session() as session_db:
        principal = session_db.scalar(select(ExternalIdentityRow).join(NativeAccountPrincipalRow))
        assert principal.issuer is None and principal.subject is None
        assert session_db.scalar(select(func.count()).select_from(NativeAccountPrincipalRow)) == 1


def test_replay_conflict_and_atomic_settings(native):
    client, post, db, *_ = native
    first = create(native)
    assert post("organisation", {"name": "Synthetic Orchard"}).status_code == 200
    assert post("organisation", {"name": "Different"}).status_code == 409
    assert (
        post("organisation", {"name": "Synthetic Orchard"}, key="different-command").status_code
        == 409
    )
    with db.session() as session_db:
        company_id = UUID(first["company"]["id"])
        assert (
            session_db.scalar(
                select(func.count())
                .select_from(MembershipRow)
                .where(MembershipRow.company_id == company_id)
            )
            == 1
        )
        policy = session_db.execute(
            text(
                "SELECT v.settings_json FROM tenant_settings_versions v "
                "JOIN tenant_settings_current c ON c.version_id=v.id "
                "WHERE c.company_id=:company"
            ),
            {"company": company_id},
        ).scalar_one()
        policy = json.loads(policy)
        assert policy["provider_profile"] is None
        assert policy["automatic_generation_enabled"] is False


def test_parallel_first_commands_share_one_owner(native):
    client, post, db, _, _, _, app = native
    cookies = dict(client.cookies)

    def request(index):
        with TestClient(app) as other:
            other.cookies.update(cookies)
            return post("organisation", {"name": "Synthetic Orchard"}, target=other).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(request, range(2))) == [200, 201]
    with db.session() as session_db:
        assert session_db.scalar(select(func.count()).select_from(NativeAccountPrincipalRow)) == 1
        assert (
            session_db.scalar(
                select(func.count())
                .select_from(MembershipRow)
                .join(
                    NativeAccountPrincipalRow,
                    NativeAccountPrincipalRow.identity_id == MembershipRow.identity_id,
                )
            )
            == 1
        )


def test_failed_settings_transaction_retains_no_partial_native_organisation(native, monkeypatch):
    _, post, db, *_ = native
    import apbra_api.tenant_settings as settings_module

    original = settings_module.create_private_preview_initial_settings

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic transaction failure")

    monkeypatch.setattr(settings_module, "create_private_preview_initial_settings", fail)
    with pytest.raises(RuntimeError, match="synthetic transaction"):
        post("organisation", {"name": "Synthetic Orchard"})
    with db.session() as session_db:
        assert session_db.scalar(select(func.count()).select_from(NativeAccountPrincipalRow)) == 0
        assert session_db.scalar(select(func.count()).select_from(NativeWorkspaceSessionRow)) == 0
        assert (
            session_db.scalar(select(CompanyRow).where(CompanyRow.name == "Synthetic Orchard"))
            is None
        )
    monkeypatch.setattr(settings_module, "create_private_preview_initial_settings", original)
    create(native)


@pytest.mark.parametrize("field", ["revoked", "epoch", "inactive", "expired", "idle"])
def test_parent_invalidation_denies_workspace(native, field):
    client, _, db, account_id, *_ = native
    create(native)
    with db.session() as session_db:
        parent = session_db.get(PasswordSessionRow, digest(client.cookies.get(COOKIE)))
        account = session_db.get(PasswordAccountRow, account_id)
        if field == "revoked":
            parent.revoked_at = datetime.now(UTC)
        elif field == "epoch":
            account.epoch += 1
        elif field == "inactive":
            account.active = False
        elif field == "expired":
            parent.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        else:
            parent.touched_at = datetime.now(UTC) - timedelta(minutes=31)
    assert client.get("/api/cases").status_code == 401
    assert not client.get("/api/auth/session").json()["authenticated"]


def test_workspace_logout_revokes_password_parent(native):
    client, *_ = native
    create(native)
    session = client.get("/api/auth/session").json()
    assert (
        client.post("/api/auth/logout", headers={"X-CSRF-Token": session["csrf_token"]}).status_code
        == 200
    )
    assert not client.get(PATH + "/session").json()["authenticated"]
    assert client.get("/api/cases").status_code == 401


@pytest.mark.parametrize("inactive", ["membership", "company"])
def test_revoked_membership_cannot_create_another_company(native, inactive):
    client, post, db, *_ = native
    created = create(native)
    with db.session() as session_db:
        target = (
            session_db.get(MembershipRow, UUID(created["membership"]["id"]))
            if inactive == "membership"
            else session_db.get(CompanyRow, UUID(created["company"]["id"]))
        )
        target.active = False
    assert client.get("/api/cases").status_code == 401
    assert post("organisation", {"name": "Escape"}, key="new-native-command").status_code == 409
    session = client.get("/api/auth/session").json()
    assert session["authentication_kind"] == "NATIVE"
    assert session["membership_state"] == "MEMBERSHIP_INACTIVE"
    assert "actor" not in session
    assert (
        client.post(
            "/api/companies",
            json={"name": "Escape"},
            headers={
                "X-CSRF-Token": session["csrf_token"],
                "Idempotency-Key": "native-escape-key",
            },
        ).status_code
        == 409
    )


def test_forged_membership_and_private_case_denied_and_no_native_invites(native):
    client, *_ = native
    create(native)
    session = client.get("/api/auth/session").json()
    headers = {"X-CSRF-Token": session["csrf_token"]}
    assert (
        client.post(
            "/api/auth/select-company", json={"membership_id": str(uuid4())}, headers=headers
        ).status_code
        == 401
    )
    assert client.get("/api/cases/" + str(uuid4())).status_code == 404
    response = client.post(
        "/api/invitations", json={"subject": "someone", "role": "MEMBER"}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NATIVE_INVITATIONS_UNSUPPORTED"


def test_csrf_origin_and_body_cannot_select_authority(native):
    client, post, *_ = native
    assert client.post(PATH + "/organisation", json={"name": "Bad"}).status_code == 403
    assert post("organisation", {"name": "Bad", "role": "COMPANY_OWNER"}).status_code == 400
    assert post("organisation", {"name": "Bad", "account_id": str(uuid4())}).status_code == 400
    assert post("organisation", {"name": "\u200b"}).status_code == 422
    assert client.get("/api/cases").status_code == 401


def test_actual_password_reset_revokes_workspace_then_restores_same_membership(native):
    from apbra_api.password_auth import PasswordProofRow

    client, post, db, account_id, _, headers, _ = native
    first = create(native)
    proof = "s" * 43
    with db.session() as session_db:
        account = session_db.get(PasswordAccountRow, account_id)
        session_db.add(
            PasswordProofRow(
                digest=digest(proof),
                purpose="reset",
                email_key=EMAIL,
                email=EMAIL,
                account_id=account_id,
                epoch=account.epoch,
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
    new_phrase = "Synthetic maple valley horizon 672!"
    assert post("reset", {"proof": proof, "password": new_phrase}).status_code == 200
    assert client.get("/api/cases").status_code == 401
    assert (
        client.post(
            PATH + "/signin", json={"email": EMAIL, "password": PHRASE}, headers=headers
        ).status_code
        == 401
    )
    assert (
        client.post(
            PATH + "/signin", json={"email": EMAIL, "password": new_phrase}, headers=headers
        ).status_code
        == 200
    )
    assert post("workspace").status_code == 200
    assert (
        client.get("/api/auth/session").json()["actor"]["membership_id"]
        == first["membership"]["id"]
    )


def test_multiple_current_memberships_require_selection_and_reject_cross_account(native):
    client, post, db, _, *_ = native
    created = create(native)
    with db.session() as session_db:
        original = session_db.get(MembershipRow, UUID(created["membership"]["id"]))
        company = CompanyRow(name="Synthetic Second Company")
        session_db.add(company)
        session_db.flush()
        second = MembershipRow(
            company_id=company.id, identity_id=original.identity_id, role="MEMBER"
        )
        session_db.add(second)
        session_db.flush()
        second_id = second.id
    client.cookies.delete(SESSION_COOKIE)
    assert post("workspace").status_code == 200
    session = client.get("/api/auth/session").json()
    assert session["membership_state"] == "COMPANY_SELECTION_REQUIRED"
    assert "actor" not in session
    assert client.get("/api/cases").status_code == 401
    assert (
        client.post(
            "/api/auth/select-company",
            json={"membership_id": str(second_id)},
            headers={"X-CSRF-Token": session["csrf_token"]},
        ).status_code
        == 200
    )
    assert client.get("/api/auth/session").json()["actor"]["role"] == "MEMBER"
    assert client.get("/api/cases").status_code == 200


def test_owner_cannot_read_other_private_cases_or_escalate(native):
    client, _, db, _, _, _, app = native
    first = create(native)
    with db.session() as session_db:
        other = PasswordAccountRow(
            email="second@example.org",
            email_key="second@example.org",
            password_hash=password_hash(PHRASE),
        )
        session_db.add(other)
    with TestClient(app) as second:
        token = second.get(PATH + "/options").json()["csrf"]
        headers = {"Origin": native[4].public_origin, "X-Password-CSRF": token}
        assert (
            second.post(
                PATH + "/signin",
                json={"email": "second@example.org", "password": PHRASE},
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            second.post(
                PATH + "/organisation",
                json={"name": "Synthetic Other"},
                headers={**headers, "Idempotency-Key": "second-first-command"},
            ).status_code
            == 201
        )
        context = second.get("/api/auth/session").json()
        response = second.post(
            "/api/cases",
            json={"request_text": "Synthetic private sales overview"},
            headers={
                "X-CSRF-Token": context["csrf_token"],
                "Idempotency-Key": "synthetic-private-case",
            },
        )
        assert response.status_code == 201, response.text
        case_id = response.json()["case"]["id"]
        assert client.get("/api/cases/" + case_id).status_code == 404
        context_first = client.get("/api/auth/session").json()
        assert (
            client.post(
                "/api/auth/select-company",
                json={
                    "membership_id": context["actor"]["membership_id"],
                },
                headers={"X-CSRF-Token": context_first["csrf_token"]},
            ).status_code
            == 401
        )
        assert context_first["actor"]["company_id"] == first["company"]["id"]


def test_additive_migration_preserves_prior_rows_and_refuses_lossy_native_downgrade(native):
    from conftest import disposable_alembic_config

    from alembic import command

    _, _, db, _, settings, *_ = native
    queries = {
        "identities": (
            "SELECT id,provider_profile_id,issuer,subject,active "
            "FROM external_identities ORDER BY id"
        ),
        "memberships": "SELECT id,company_id,identity_id,role,active FROM memberships ORDER BY id",
        "companies": "SELECT id,name,active FROM companies ORDER BY id",
    }

    def snapshot():
        with db.session() as session_db:
            return {key: session_db.execute(text(sql)).all() for key, sql in queries.items()}

    before = snapshot()
    config = disposable_alembic_config(settings.database_url)
    command.downgrade(config, "20261106_17")
    command.upgrade(config, "20261108_18")
    assert snapshot() == before
    create(native)
    with pytest.raises(RuntimeError, match="preservation"):
        command.downgrade(config, "20261106_17")
    with db.session() as session_db:
        assert session_db.scalar(text("SELECT version_num FROM alembic_version")) == "20261108_18"
        assert session_db.scalar(select(func.count()).select_from(NativeAccountPrincipalRow)) == 1


def test_enabled_native_feature_refuses_unmigrated_database(native):
    from conftest import disposable_alembic_config

    from alembic import command

    _, _, db, _, settings, *_ = native
    command.downgrade(disposable_alembic_config(settings.database_url), "20261106_17")
    with pytest.raises(ValueError, match="PASSWORD_SCHEMA_NOT_READY"):
        create_app(
            settings,
            db,
            password_settings=PasswordAuthSettings(
                _env_file=None,
                password_auth_enabled=True,
            ),
        )


def test_unbound_native_identity_and_workspace_label_cannot_authorise(native):
    client, _, db, *_ = native
    raw = "z" * 64
    with db.session() as session_db:
        identity = ExternalIdentityRow(
            provider_profile_id="native-password",
            issuer=None,
            subject=None,
            display_name="Unbound synthetic",
        )
        session_db.add(identity)
        session_db.flush()
        session_db.add(
            SessionRow(
                token_digest=digest(raw),
                identity_id=identity.id,
                provider_profile_id="native-password",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    client.cookies.set(SESSION_COOKIE, raw)
    assert client.get("/api/cases").status_code == 401
    assert not client.get("/api/auth/session").json()["authenticated"]
