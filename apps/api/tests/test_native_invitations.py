"""Native invitation grants exercised through normal account and workspace entry points."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import String, func, select, table, text
from sqlalchemy.exc import DBAPIError, OperationalError

from apbra_api import native_invitations
from apbra_api.api import create_app
from apbra_api.native_organisation import NativeAccountPrincipalRow, NativeWorkspaceSessionRow
from apbra_api.password_auth import (
    PATH,
    CaptureMailer,
    PasswordAuthSettings,
    digest,
)
from apbra_api.persistence import (
    ExternalIdentityRow,
    MembershipRow,
    NativeInvitationAuditRow,
    NativeInvitationRow,
)

PHRASE = "Synthetic willow amber harbour 614!"
CHANGED = "Synthetic violet harbour valley 925!"
MANAGE = "/api/native-invitations"


class Person:
    def __init__(self, flow, email):
        self.flow, self.email = flow, email
        self.client = TestClient(flow.app)
        self.headers = {
            "Origin": flow.settings.public_origin,
            "X-Password-CSRF": self.client.get(PATH + "/options").json()["csrf"],
        }

    def post(self, action, data=None, key=None):
        return self.client.post(
            PATH + "/" + action,
            json=data or {},
            headers={**self.headers, **({"Idempotency-Key": key} if key else {})},
        )

    def verify(self):
        assert self.post("signup", {"email": self.email, "password": PHRASE}).status_code == 202
        proof = self.flow.proof(self.email, "verify")
        assert self.post("verify", {"proof": proof, "password": PHRASE}).status_code == 200

    def signin(self, phrase=PHRASE):
        assert self.post("signin", {"email": self.email, "password": phrase}).status_code == 200

    def reset(self):
        assert self.post("recover", {"email": self.email}).status_code == 202
        proof = self.flow.proof(self.email, "reset")
        assert self.post("reset", {"proof": proof, "password": CHANGED}).status_code == 200

    def workspace(self):
        return self.client.get("/api/auth/session").json()

    def manage(self, method, route, data=None, key=None):
        headers = {
            "Origin": self.flow.settings.public_origin,
            "X-CSRF-Token": self.workspace()["csrf_token"],
        }
        if key:
            headers["Idempotency-Key"] = key
        return self.client.request(method, route, json=data, headers=headers)

    def organisation(self, name):
        result = self.post("organisation", {"name": name}, "org-command-" + name)
        assert result.status_code == 201
        return result.json()["company"]["id"]

    def issue(self, address, role="MEMBER", key=None):
        return self.manage("POST", MANAGE, {"email": address, "role": role}, key or str(uuid4()))

    def revoke(self, invitation):
        return self.manage("POST", MANAGE + "/" + invitation + "/revoke")

    def redeem(self, proof, *, accept=True):
        return self.post("invitations/" + ("accept" if accept else "inspect"), {"proof": proof})


class Flow:
    def __init__(self, settings, db):
        self.settings, self.db, self.mail = settings, db, CaptureMailer()
        self.app = create_app(
            settings,
            db,
            password_mailer=self.mail,
            password_settings=PasswordAuthSettings(_env_file=None, password_auth_enabled=True),
        )
        self.owner = self.account("owner")
        self.company = self.owner.organisation("Orchard")

    def account(self, name):
        p = Person(self, name + "@example.org")
        p.verify()
        p.signin()
        return p

    def proof(self, email, purpose):
        return next(p for a, k, p in reversed(self.mail.messages) if a == email and k == purpose)

    def invitation(self, person, role="MEMBER", owner=None):
        response = (owner or self.owner).issue(person.email, role)
        assert response.status_code == 201
        row = response.json()["invitation"]
        assert row["state"] == "SUBMITTED"
        return row["id"], self.proof(person.email, "invite")

    def count(self, model, *conditions):
        with self.db.session() as db:
            return db.scalar(select(func.count()).select_from(model).where(*conditions))


@pytest.fixture
def grant(settings, migrated_database):
    return Flow(settings, migrated_database)


@pytest.mark.parametrize("already_verified", [True, False])
def test_explicit_acceptance_from_real_account_journeys(grant, already_verified):
    p = grant.account("colleague") if already_verified else Person(grant, "new@example.org")
    identifier, proof = grant.invitation(p)
    with grant.db.session() as db:
        invitation = db.get(NativeInvitationRow, UUID(identifier))
        assert (invitation.recipient_account_id is not None) == already_verified
        assert invitation.token_digest == digest(proof) and invitation.consumed_at is None
        assert invitation.company_id == UUID(grant.company) and invitation.settings_version_id
    if not already_verified:
        assert p.redeem(proof).status_code == 401
        p.verify()
        assert p.redeem(proof, accept=False).status_code == 401
        p.signin()
    inspected = p.redeem(proof, accept=False)
    assert (
        inspected.status_code == 200 and inspected.json()["invitation"]["company_name"] == "Orchard"
    )
    assert p.client.get("/api/cases").status_code == 401
    first = p.redeem(proof)
    assert first.status_code == 201
    receipt = first.json()["receipt"]
    assert receipt["company_id"] == grant.company and receipt["role_at_accept"] == "MEMBER"
    assert p.workspace()["actor"]["membership_id"] == receipt["membership_id"]
    assert p.client.get("/api/cases").json() == {"items": []}
    replay = p.redeem(proof)
    assert replay.status_code == 200 and replay.json()["receipt"] == receipt
    assert "set-cookie" not in replay.headers and grant.owner.revoke(identifier).status_code == 409
    assert grant.count(NativeInvitationAuditRow, NativeInvitationAuditRow.event == "ACCEPTED") == 1
    assert (
        grant.count(NativeInvitationAuditRow, NativeInvitationAuditRow.event == "RECEIPT_REPLAYED")
        == 1
    )
    with grant.db.session() as db:
        row = db.get(NativeInvitationRow, UUID(identifier))
        assert row.consumed_by_account_id == row.recipient_account_id and row.recipient_epoch == 1
        ident = db.get(
            ExternalIdentityRow, db.get(MembershipRow, row.target_membership_id).identity_id
        )
        assert ident.issuer is None and ident.subject is None


def test_membership_management_labels_only_accepted_invitations_in_current_company(grant):
    first, second, pending = (grant.account(name) for name in ("first", "second", "pending"))
    outsider = grant.account("outside")
    outsider.organisation("Another")
    grant.invitation(pending)
    expected = {}
    for person in (first, second):
        _, proof = grant.invitation(person)
        accepted = person.redeem(proof)
        assert accepted.status_code == 201
        expected[accepted.json()["receipt"]["membership_id"]] = person.email

    route = "/api/memberships"
    labelled = route + "?include_invitation_addresses=true"
    generic = grant.owner.client.get(route)
    assert generic.status_code == 200
    assert all("invitation_address" not in member for member in generic.json()["items"])
    missing_csrf = grant.owner.client.get(labelled)
    assert missing_csrf.status_code == 401
    assert missing_csrf.json()["error"]["code"] == "CSRF_INVALID"
    assert "items" not in missing_csrf.json()
    response = grant.owner.manage("GET", labelled)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    labels = {
        member["id"]: member["invitation_address"]
        for member in response.json()["items"]
        if "invitation_address" in member
    }
    assert labels == expected
    assert first.client.get(route).status_code == 403
    assert first.manage("GET", labelled).status_code == 403
    foreign = outsider.manage("GET", labelled)
    assert foreign.status_code == 200
    assert all("invitation_address" not in member for member in foreign.json()["items"])
    grant.app.state.native_invitation_enabled = False
    disabled = grant.owner.manage("GET", labelled)
    assert disabled.status_code == 200
    assert all("invitation_address" not in member for member in disabled.json()["items"])


def test_idempotency_safe_metadata_roles_and_scoped_history(grant):
    owner = grant.owner
    email = "unknown@example.org"
    first = owner.issue(email, key="same-command")
    repeated = owner.issue(email.upper(), key="same-command")
    assert (first.status_code, repeated.status_code) == (201, 200)
    assert (
        first.json() == repeated.json()
        and owner.issue(email, "EXPERT", "same-command").status_code == 409
    )
    assert len([m for m in grant.mail.messages if m[1] == "invite"]) == 1
    assert set(first.json()["invitation"]) == {
        "id",
        "email",
        "role",
        "state",
        "delivery_state",
        "expires_at",
    }
    assert owner.issue(email, "COMPANY_OWNER").status_code in (403, 422)
    assert (
        owner.manage(
            "POST",
            MANAGE,
            {"email": email, "role": "MEMBER", "company_id": grant.company},
            "invalid-fields",
        ).status_code
        == 422
    )
    owner.issue("second@example.org")
    page = owner.manage("GET", MANAGE + "?limit=1").json()
    cursor = page["next_cursor"]
    assert len(page["items"]) == 1 and cursor
    assert (
        owner.manage("GET", MANAGE + "?limit=1&cursor=" + cursor).json()["items"] != page["items"]
    )
    assert owner.manage("GET", MANAGE + "?limit=101").status_code == 422
    other = grant.account("other")
    other.organisation("Elsewhere")
    assert other.manage("GET", MANAGE).json()["items"] == []
    assert other.manage("GET", MANAGE + "?cursor=" + cursor).status_code >= 400
    assert other.revoke(first.json()["invitation"]["id"]).status_code == 410
    assert owner.revoke(first.json()["invitation"]["id"]).json()["invitation"]["state"] == "REVOKED"
    assert owner.revoke(first.json()["invitation"]["id"]).status_code == 200


@pytest.mark.parametrize("role", ["MEMBER", "EXPERT", "COMPANY_ADMIN"])
def test_current_role_controls_issuing_and_target_membership_conflicts(grant, role):
    person = grant.account("invited")
    _, proof = grant.invitation(person, role)
    accepted = person.redeem(proof).json()["receipt"]
    assert person.issue("next@example.org").status_code == (201 if role == "COMPANY_ADMIN" else 403)
    _, second = grant.invitation(person, "COMPANY_ADMIN")
    assert person.redeem(second).json()["status"] == "MEMBERSHIP_ALREADY_EXISTS"
    assert person.workspace()["actor"]["role"] == role
    assert (
        grant.owner.manage(
            "POST", "/api/memberships/" + accepted["membership_id"] + "/deactivate"
        ).status_code
        == 200
    )
    assert person.redeem(second).json()["status"] == "MEMBERSHIP_UNAVAILABLE"
    assert person.redeem(proof).status_code == 410


def test_wrong_recipient_origin_csrf_revocation_and_private_resources(grant):
    person = grant.account("recipient")
    other = grant.account("other")
    their_company = other.organisation("OtherCompany")
    target, proof = grant.invitation(person)
    result = other.redeem(proof)
    assert result.status_code == 410 and set(result.json()) == {"status", "support_reference"}
    assert UUID(result.json()["support_reference"])
    for headers in (
        {},
        {"Origin": grant.settings.public_origin},
        {"X-Password-CSRF": person.headers["X-Password-CSRF"]},
    ):
        assert (
            person.client.post(
                PATH + "/invitations/accept", json={"proof": proof}, headers=headers
            ).status_code
            == 403
        )
    assert other.workspace()["actor"]["company_id"] == their_company
    assert grant.owner.revoke(target).status_code == 200
    assert person.redeem(proof).status_code == 410
    assert grant.count(NativeInvitationRow, NativeInvitationRow.consumed_at.is_not(None)) == 0


@pytest.mark.parametrize("outcome", ["failed", "uncertain", "revoked", "submitted"])
def test_delivery_activation_only_after_dispatch_returns(grant, outcome):
    import smtplib

    p = grant.account("delivered")
    entered, release = Event(), Event()
    original = grant.mail.send

    def dispatch(recipient, purpose, proof):
        original(recipient, purpose, proof)
        entered.set()
        assert release.wait(8)
        if outcome == "failed":
            raise smtplib.SMTPDataError(550, b"synthetic failure")
        if outcome == "uncertain":
            raise TimeoutError()

    grant.mail.send = dispatch
    with ThreadPoolExecutor(1) as pool:
        writing = pool.submit(grant.owner.issue, p.email, "MEMBER", "one-dispatch")
        assert entered.wait(8)
        try:
            proof = grant.proof(p.email, "invite")
            page = grant.owner.manage("GET", MANAGE).json()["items"]
            assert len(page) == 1 and page[0]["state"] == "PREPARED"
            assert p.redeem(proof).status_code == 410
            if outcome == "revoked":
                assert grant.owner.revoke(page[0]["id"]).status_code == 200
        finally:
            release.set()
        state = writing.result(timeout=8).json()["invitation"]["state"]
    assert (
        state
        == {
            "failed": "FAILED",
            "uncertain": "UNCONFIRMED",
            "revoked": "REVOKED",
            "submitted": "SUBMITTED",
        }[outcome]
    )
    assert p.redeem(proof).status_code == (201 if outcome == "submitted" else 410)
    assert grant.owner.issue(p.email, key="one-dispatch").status_code == 200
    assert len([m for m in grant.mail.messages if m[1] == "invite"]) == 1


@pytest.mark.parametrize("known", [True, False])
def test_recipient_reset_requires_fresh_grant_and_revokes_previous_sessions(grant, known):
    p = grant.account("reset") if known else Person(grant, "reset@example.org")
    _, proof = grant.invitation(p)
    if not known:
        p.verify()
        p.signin()
    p.reset()
    assert p.redeem(proof).status_code == 401
    p.signin(CHANGED)
    assert p.redeem(proof).status_code == 410
    _, fresh = grant.invitation(p)
    assert p.redeem(fresh).status_code == 201


def test_issuer_reset_and_demotion_preserve_committed_receipts(grant):
    admin = grant.account("admin")
    _, first = grant.invitation(admin, "COMPANY_ADMIN")
    admin_member = admin.redeem(first).json()["receipt"]["membership_id"]
    p = grant.account("joined")
    q = grant.account("pending")
    _, used = grant.invitation(p, owner=admin)
    joined = p.redeem(used).json()["receipt"]
    _, pending = grant.invitation(q, owner=admin)

    def change(role):
        return grant.owner.manage(
            "POST", "/api/memberships/" + admin_member + "/role", {"role": role}
        )

    assert change("MEMBER").status_code == 200
    assert change("COMPANY_ADMIN").status_code == 200
    assert q.redeem(pending).status_code == 410
    _, epoch = grant.invitation(q, owner=admin)
    admin.reset()
    assert q.redeem(epoch).status_code == 410
    assert p.redeem(used).json()["receipt"] == joined


@pytest.mark.parametrize("scenario", ["same-proof", "two-proofs", "two-companies", "reverse"])
def test_concurrent_acceptance_serializes_on_actual_authorities(grant, scenario):
    a = grant.account("first")
    b = grant.account("second")
    if scenario in {"two-companies", "reverse"}:
        a.organisation("SecondOrg")
    left = (b, grant.invitation(b)[1])
    if scenario == "reverse":
        left = (a, grant.invitation(a)[1])
        right = (grant.owner, grant.invitation(grant.owner, owner=a)[1])
    elif scenario == "two-companies":
        right = (b, grant.invitation(b, owner=a)[1])
    elif scenario == "two-proofs":
        right = (b, grant.invitation(b, "EXPERT")[1])
    else:
        right = left
    gate = Barrier(2)

    def accept(pair):
        # Each request has its own cookie jar and database session.
        original, proof = pair
        client = TestClient(grant.app)
        client.cookies.update(original.client.cookies)
        gate.wait(timeout=8)
        return client.post(
            PATH + "/invitations/accept", json={"proof": proof}, headers=original.headers
        )

    with ThreadPoolExecutor(2) as pool:
        fut = [pool.submit(accept, pair) for pair in (left, right)]
        responses = [f.result(timeout=10) for f in fut]
    expected = {
        "same-proof": [200, 201],
        "two-proofs": [201, 409],
        "two-companies": [201, 201],
        "reverse": [201, 201],
    }
    assert sorted(r.status_code for r in responses) == expected[scenario]
    if scenario == "same-proof":
        assert responses[0].json()["receipt"] == responses[1].json()["receipt"]
    won = expected[scenario].count(201)
    assert (
        grant.count(NativeInvitationAuditRow, NativeInvitationAuditRow.event == "ACCEPTED") == won
    )


@pytest.mark.parametrize("after_workspace", [False, True])
def test_rollback_releases_no_principal_receipt_or_cookie(grant, monkeypatch, after_workspace):
    p = grant.account("rollback")
    identifier, proof = grant.invitation(p)
    previous = grant.count(NativeAccountPrincipalRow)

    initial_workspaces = grant.count(NativeWorkspaceSessionRow)
    issue_workspace = native_invitations.issue_workspace

    def fail(db, *args, **kwargs):
        if after_workspace:
            issue_workspace(db, *args, **kwargs)
            db.flush()
        raise OperationalError("Synthetic write failure", {}, Exception())

    monkeypatch.setattr(native_invitations, "issue_workspace", fail)
    c = TestClient(grant.app, raise_server_exceptions=False)
    c.cookies.update(p.client.cookies)
    result = c.post(PATH + "/invitations/accept", json={"proof": proof}, headers=p.headers)
    assert result.status_code == 500 and "set-cookie" not in result.headers
    assert grant.count(NativeAccountPrincipalRow) == previous
    assert grant.count(NativeWorkspaceSessionRow) == initial_workspaces
    assert grant.count(NativeInvitationAuditRow, NativeInvitationAuditRow.event == "ACCEPTED") == 0
    assert grant.count(NativeInvitationAuditRow, NativeInvitationAuditRow.event == "REJECTED") >= 1
    with grant.db.session() as db:
        assert db.get(NativeInvitationRow, UUID(identifier)).consumed_at is None


def test_database_guards_preserve_intent_audit_and_populated_downgrade(grant):
    from conftest import disposable_alembic_config

    from alembic import command

    p = grant.account("guard")
    identifier, proof = grant.invitation(p)
    assert p.redeem(proof).status_code == 201
    for sql in (
        "UPDATE native_invitations SET role='EXPERT' WHERE id=:id",
        "DELETE FROM native_invitation_commands WHERE invitation_id=:id",
        "DELETE FROM native_invitation_audit WHERE invitation_id=:id",
    ):
        with pytest.raises(DBAPIError), grant.db.session() as db:
            db.execute(text(sql), {"id": UUID(identifier)})
    with pytest.raises(RuntimeError, match="retained native invitation"):
        command.downgrade(disposable_alembic_config(grant.settings.database_url), "20261108_18")
    with grant.db.session() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "20261118_19"
        assert db.get(NativeInvitationRow, UUID(identifier)).target_membership_id is not None


def race(left, right):
    start = Barrier(2)

    def run(operation):
        start.wait(timeout=10)
        return operation()

    with ThreadPoolExecutor(2) as pool:
        a, b = pool.submit(run, left), pool.submit(run, right)
        return a.result(timeout=10), b.result(timeout=10)


@pytest.mark.parametrize("event", ["revoke", "demote", "deactivate", "issuer-reset"])
def test_pending_authority_loss_and_acceptance_have_one_serial_outcome(grant, event):
    issuer = grant.account("issuer")
    _, inv = grant.invitation(issuer, "COMPANY_ADMIN")
    mid = issuer.redeem(inv).json()["receipt"]["membership_id"]
    recipient = grant.account("recipient")
    identifier, proof = grant.invitation(recipient, owner=issuer)

    def loss():
        if event == "revoke":
            return grant.owner.revoke(identifier).status_code
        if event == "demote":
            return grant.owner.manage(
                "POST", "/api/memberships/" + mid + "/role", {"role": "MEMBER"}
            ).status_code
        if event == "deactivate":
            return grant.owner.manage("POST", "/api/memberships/" + mid + "/deactivate").status_code
        issuer.reset()
        return 200

    accepted, changed = race(lambda: recipient.redeem(proof), loss)
    assert accepted.status_code in (201, 410)
    assert changed == (409 if event == "revoke" and accepted.status_code == 201 else 200)
    with grant.db.session() as db:
        row = db.get(NativeInvitationRow, UUID(identifier))
        assert (row.target_membership_id is not None) == (accepted.status_code == 201)
    replay = recipient.redeem(proof)
    if accepted.status_code == 201:
        assert replay.json()["receipt"] == accepted.json()["receipt"]
    else:
        assert replay.status_code == 410


@pytest.mark.parametrize(
    "operation", ["password-logout", "workspace-logout", "rotate", "reset", "select"]
)
def test_parent_session_changes_linearize_with_acceptance(grant, operation):
    p = grant.account("existing")
    p.organisation("Original")
    old = Person(grant, p.email)
    old.client.cookies.update(p.client.cookies)
    old.headers = p.headers.copy()
    old_workspace = p.workspace()
    _, proof = grant.invitation(p)

    def session_change():
        if operation == "password-logout":
            return p.post("signout").status_code
        if operation == "workspace-logout":
            return p.client.post(
                "/api/auth/logout", headers={"X-CSRF-Token": old_workspace["csrf_token"]}
            ).status_code
        if operation == "select":
            return p.client.post(
                "/api/auth/select-company",
                json={"membership_id": old_workspace["actor"]["membership_id"]},
                headers={"X-CSRF-Token": old_workspace["csrf_token"]},
            ).status_code
        if operation == "rotate":
            p.signin()
        else:
            p.reset()
        return 200

    accepted, changed = race(lambda: old.redeem(proof), session_change)
    assert changed == 200
    if operation == "select":
        assert accepted.status_code == 201
    else:
        assert accepted.status_code in (201, 401)
        assert old.client.get("/api/cases").status_code == 401
    assert grant.count(NativeInvitationRow, NativeInvitationRow.consumed_at.is_not(None)) == (
        1 if accepted.status_code == 201 else 0
    )


def test_same_origin_receipt_error_stale_company_and_private_case_isolation(grant):
    p = grant.account("reader")
    original = p.organisation("PrivateOrg")
    own = grant.owner.manage(
        "POST", "/api/cases", {"request_text": "Private orchard planning"}, str(uuid4())
    )
    other = p.manage(
        "POST", "/api/cases", {"request_text": "Independent private plan"}, str(uuid4())
    )
    assert own.status_code == 201 and other.status_code == 201
    prior = p.workspace()
    private_id = own.json()["case"]["id"]
    _, proof = grant.invitation(p)
    accepted = p.redeem(proof)
    assert accepted.status_code == 201 and p.workspace()["actor"]["company_id"] == grant.company
    assert p.client.get("/api/cases").json() == {"items": []}
    assert p.client.get("/api/cases/" + private_id).status_code in (403, 404)
    assert p.client.get("/api/cases/" + other.json()["case"]["id"]).status_code in (403, 404)
    assert (
        p.manage(
            "POST", "/api/auth/select-company", {"membership_id": prior["actor"]["membership_id"]}
        ).status_code
        == 200
    )
    assert p.workspace()["actor"]["company_id"] == original
    headers = {
        "Origin": grant.settings.public_origin,
        "X-CSRF-Token": p.workspace()["csrf_token"],
        "X-Expected-Membership-Id": accepted.json()["receipt"]["membership_id"],
        "Idempotency-Key": str(uuid4()),
    }
    assert (
        p.client.post(
            MANAGE, json={"email": "next@example.org", "role": "MEMBER"}, headers=headers
        ).status_code
        == 409
    )
    assert p.client.get(MANAGE, headers=headers).status_code == 409
    bad = p.redeem("short")
    assert bad.status_code == 410 and UUID(bad.json()["support_reference"])
    with grant.db.session() as db:
        assert (
            db.get(NativeInvitationAuditRow, UUID(bad.json()["support_reference"])).event
            == "REJECTED"
        )


def test_expired_unused_proof_and_receipt_after_expiry(grant):
    from datetime import UTC, datetime, timedelta

    from apbra_api.native_invitations import Unavailable, recipient
    from apbra_api.password_auth import COOKIE, PasswordSessionRow

    p = grant.account("expiry")
    _, unused = grant.invitation(p)
    _, used = grant.invitation(p)
    first = p.redeem(used).json()["receipt"]
    future = datetime.now(UTC) + timedelta(days=32)
    parent = p.client.cookies.get(COOKIE)
    with grant.db.session() as db:
        session = db.get(PasswordSessionRow, digest(parent))
        session.touched_at = future
        session.expires_at = future + timedelta(hours=1)
    with pytest.raises(Unavailable):
        recipient(grant.db, parent, None, unused, accept=True, now=lambda: future)
    assert (
        recipient(grant.db, parent, None, used, accept=True, now=lambda: future).body["receipt"]
        == first
    )
    assert grant.count(NativeInvitationAuditRow, NativeInvitationAuditRow.event == "EXPIRED") == 1


def test_organisation_retry_and_acceptance_concur_without_replacing_receipt(grant):
    p = grant.account("two")
    p.organisation("Original")
    _, proof = grant.invitation(p)
    clone = TestClient(grant.app)
    clone.cookies.update(p.client.cookies)
    replay, accepted = race(
        lambda: clone.post(
            PATH + "/organisation",
            json={"name": "Original"},
            headers={**p.headers, "Idempotency-Key": "org-command-Original"},
        ),
        lambda: p.redeem(proof),
    )
    assert replay.status_code == 200 and accepted.status_code == 201
    assert replay.json()["company"]["id"] != accepted.json()["receipt"]["company_id"]
    assert grant.count(NativeInvitationAuditRow, NativeInvitationAuditRow.event == "ACCEPTED") == 1


@pytest.mark.parametrize("inactive", ["account", "principal", "company"])
def test_inactive_recipient_or_company_cannot_accept_or_reactivate(grant, inactive):
    from apbra_api.password_auth import PasswordAccountRow
    from apbra_api.persistence import CompanyRow

    p = grant.account("inactive")
    if inactive == "principal":
        p.organisation("Another")
    _, proof = grant.invitation(p)
    with grant.db.session() as db:
        account = db.scalar(
            select(PasswordAccountRow).where(PasswordAccountRow.email_key == p.email)
        )
        if inactive == "account":
            account.active = False
        elif inactive == "company":
            db.get(CompanyRow, UUID(grant.company)).active = False
        else:
            identity = db.scalar(
                select(NativeAccountPrincipalRow.identity_id).where(
                    NativeAccountPrincipalRow.account_id == account.id
                )
            )
            db.get(ExternalIdentityRow, identity).active = False
    assert p.redeem(proof).status_code in (401, 409, 410)
    assert grant.count(NativeInvitationAuditRow, NativeInvitationAuditRow.event == "ACCEPTED") == 0


def test_migration19_preserves_populated_native_and_legacy_row_bytes(grant):
    import hashlib

    from conftest import disposable_alembic_config

    from alembic import command

    target = disposable_alembic_config(grant.settings.database_url)
    command.downgrade(target, "20261108_18")
    from conftest import csrf, sign_in

    provider_client = TestClient(grant.app)
    provider_session = sign_in(provider_client)
    legacy = provider_client.post(
        "/api/invitations",
        headers=csrf(provider_session),
        json={"subject": "synthetic-legacy-colleague", "role": "MEMBER"},
    )
    assert legacy.status_code == 200
    assert legacy.json()["invitation"]["id"]
    tables = (
        "companies",
        "memberships",
        "external_identities",
        "password_accounts",
        "password_proofs",
        "password_sessions",
        "password_audit",
        "native_account_principals",
        "native_workspace_sessions",
        "invitations",
        "authentication_events",
    )

    def snapshot():
        with grant.db.session() as db:
            return {
                name: hashlib.sha256(
                    "\n".join(
                        db.scalars(
                            select(
                                func.to_jsonb(table(name).table_valued()).cast(String).label("row")
                            ).order_by("row")
                        )
                    ).encode()
                ).hexdigest()
                for name in tables
            }

    before = snapshot()
    command.upgrade(target, "20261118_19")
    command.current(target, check_heads=True)
    assert before == snapshot()
    assert grant.owner.workspace()["actor"]["company_id"] == grant.company


def test_workspace_logout_and_issuance_serialize(grant):
    owner = grant.owner
    prior = owner.workspace()
    separate = TestClient(grant.app)
    separate.cookies.update(owner.client.cookies)
    # Both actions present the original real workspace credential on separate HTTP clients.
    logout, issue = race(
        lambda: separate.post("/api/auth/logout", headers={"X-CSRF-Token": prior["csrf_token"]}),
        lambda: owner.client.post(
            MANAGE,
            json={"email": "later@example.org", "role": "MEMBER"},
            headers={
                "Origin": grant.settings.public_origin,
                "X-CSRF-Token": prior["csrf_token"],
                "Idempotency-Key": str(uuid4()),
            },
        ),
    )
    assert logout.status_code == 200 and issue.status_code in (201, 401, 403)
    assert owner.client.get("/api/cases").status_code == 401
    submitted = issue.status_code == 201
    assert len([m for m in grant.mail.messages if m[1] == "invite"]) == int(submitted)
    assert grant.count(NativeInvitationRow) == int(submitted)
