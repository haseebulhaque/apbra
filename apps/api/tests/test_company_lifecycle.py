"""APBRA-151 company creation and membership security regressions."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apbra_api.api import create_app
from apbra_api.application import CompanyService, InvitationService, MembershipService
from apbra_api.config import Settings
from apbra_api.domain import AuthenticationRequired, Forbidden, Role
from apbra_api.persistence import (
    AuditEventRow,
    CompanyCreationCommandRow,
    CompanyRow,
    Database,
    ExternalIdentityRow,
    InvitationRow,
    MembershipRow,
    SessionRow,
    TenantSettingsCurrentRow,
    TenantSettingsVersionRow,
)
from apbra_api.tenant_settings import current_settings


def creator_client(settings: Settings, database: Database) -> tuple[TestClient, dict]:
    client = TestClient(create_app(settings=settings, database=database))
    session = sign_in(client, "creator")
    assert session["membership_state"] == "COMPANY_CREATION_AVAILABLE"
    return client, session


def create_company(
    client: TestClient, session: dict, name: str, key: str = "create-company-001"
):
    return client.post(
        "/api/companies",
        json={"name": name},
        headers={**csrf(session), "Idempotency-Key": key},
    )


def test_first_company_creation_commits_owner_settings_and_audit_once(
    settings: Settings, database: Database
) -> None:
    client, session = creator_client(settings, database)
    created = create_company(client, session, "  Société Exemple  ")
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["company"]["name"] == "Société Exemple"
    assert payload["membership"]["role"] == "COMPANY_OWNER"
    company_id = UUID(payload["company"]["id"])
    membership_id = UUID(payload["membership"]["id"])
    refreshed = client.get("/api/auth/session").json()
    assert refreshed["membership_state"] == "ACTIVE"
    assert refreshed["actor"]["company_id"] == str(company_id)
    assert refreshed["actor"]["membership_id"] == str(membership_id)
    assert refreshed["actor"]["role"] == "COMPANY_OWNER"
    with database.session() as db:
        company = db.get(CompanyRow, company_id)
        membership = db.get(MembershipRow, membership_id)
        assert company is not None and company.name == "Société Exemple"
        assert membership is not None and membership.company_id == company_id
        assert membership.identity_id == UUID(refreshed["actor"]["identity_id"])
        assert db.scalar(select(func.count()).select_from(MembershipRow).where(
            MembershipRow.company_id == company_id
        )) == 1
        snapshot = current_settings(db, company_id)
        assert snapshot.version == 1
        assert snapshot.settings.generation_policy.organisation.name == company.name
        assert snapshot.settings.generation_policy.organisation.display_name == company.name
        assert snapshot.settings.generation_policy.organisation.locale == "en-AU"
        assert snapshot.settings.generation_policy.organisation.timezone == "Australia/Sydney"
        assert snapshot.settings.generation_policy.branding.primary == "#17635E"
        assert not snapshot.settings.expert_escalation_enabled
        assert not snapshot.settings.automatic_generation_enabled
        assert snapshot.settings.provider_profile is None
        assert snapshot.secret_reference_id is None
        assert snapshot.settings.conventions.report_naming == ""
        assert snapshot.settings.conventions.semantic_modelling == ""
        assert snapshot.settings.conventions.accessibility == ""
        assert snapshot.settings.conventions.terminology == {}
        version = db.get(TenantSettingsVersionRow, snapshot.id)
        pointer = db.get(TenantSettingsCurrentRow, company_id)
        assert version is not None and version.created_by_membership_id == membership_id
        assert pointer is not None and pointer.version_id == snapshot.id
        assert "Jira 10406" in (version.reason or "")
        commands = db.scalars(select(CompanyCreationCommandRow).where(
            CompanyCreationCommandRow.identity_id == membership.identity_id
        )).all()
        assert len(commands) == 1
        assert commands[0].company_id == company_id
        assert commands[0].membership_id == membership_id
        events = db.scalars(select(AuditEventRow).where(
            AuditEventRow.company_id == company_id
        )).all()
        assert {event.event_type for event in events} == {
            "COMPANY_CREATED", "MEMBERSHIP_CREATED"
        }


def test_company_creation_replay_and_conflict(settings: Settings, database: Database) -> None:
    client, session = creator_client(settings, database)
    first = create_company(client, session, "Northwind Studio", "company-replay-001")
    assert first.status_code == 201, first.text
    replay = create_company(client, session, " Northwind Studio ", "company-replay-001")
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    changed = create_company(client, session, "Other Studio", "company-replay-001")
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    second_key = create_company(client, session, "Other Studio", "company-replay-002")
    assert second_key.status_code == 409
    assert second_key.json()["error"]["code"] == "COMPANY_CREATION_NOT_AVAILABLE"
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(CompanyCreationCommandRow)) == 1
        assert db.scalar(select(func.count()).select_from(AuditEventRow).where(
            AuditEventRow.event_type == "COMPANY_CREATED"
        )) == 1


def test_company_creation_rejects_missing_authority_and_spoofed_fields(
    settings: Settings, database: Database
) -> None:
    anonymous = TestClient(create_app(settings=settings, database=database))
    assert anonymous.post(
        "/api/companies", json={"name": "Example"}, headers={"Idempotency-Key": "abcde12345"}
    ).status_code == 401
    client, session = creator_client(settings, database)
    assert client.post(
        "/api/companies", json={"name": "Example"}, headers={"Idempotency-Key": "abcde12345"}
    ).json()["error"]["code"] == "CSRF_INVALID"
    assert client.post(
        "/api/companies", json={"name": "Example"}, headers=csrf(session)
    ).status_code == 409
    assert client.post(
        "/api/companies", json={"name": "Example"},
        headers={**csrf(session), "Idempotency-Key": "bad key"},
    ).status_code == 409
    for forged in (
        {"creator_identity_id": str(uuid4())},
        {"role": "COMPANY_OWNER"},
        {"company_id": str(uuid4())},
        {"domain": "example.com"},
        {"provider_profile_id": "local-test"},
        {"initial_settings": {"automatic_generation_enabled": True}},
    ):
        result = client.post(
            "/api/companies", json={"name": "Example", **forged},
            headers={**csrf(session), "Idempotency-Key": "forged-company-001"},
        )
        assert result.status_code == 422
    assert client.get("/api/auth/session").json()["membership_state"] == (
        "COMPANY_CREATION_AVAILABLE"
    )


@pytest.mark.parametrize("name", ["", "   ", "Bad\nName", "Bad\u202eName", "a" * 201])
def test_company_name_validation_rejects_unsafe_names(
    settings: Settings, database: Database, name: str
) -> None:
    client, session = creator_client(settings, database)
    result = create_company(client, session, name)
    assert result.status_code == 422
    assert result.json()["error"]["code"] == "COMPANY_NAME_INVALID"
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(CompanyCreationCommandRow)) == 0


def test_company_creation_rollback_keeps_no_partial_authority(
    settings: Settings, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apbra_api.tenant_settings as tenant_settings

    client, session = creator_client(settings, database)
    before = {}
    with database.session() as db:
        for table in (CompanyRow, MembershipRow, TenantSettingsVersionRow,
                      TenantSettingsCurrentRow, CompanyCreationCommandRow, AuditEventRow):
            before[table.__tablename__] = db.scalar(select(func.count()).select_from(table))

    original = tenant_settings.create_private_preview_initial_settings

    def fail_settings(*args: object, **kwargs: object) -> None:
        original(*args, **kwargs)
        raise RuntimeError("synthetic settings failure")

    monkeypatch.setattr(tenant_settings, "create_private_preview_initial_settings", fail_settings)
    with pytest.raises(RuntimeError, match="synthetic settings failure"):
        create_company(client, session, "Rollback Company", "rollback-company-001")
    with database.session() as db:
        for table in (CompanyRow, MembershipRow, TenantSettingsVersionRow,
                      TenantSettingsCurrentRow, CompanyCreationCommandRow, AuditEventRow):
            assert db.scalar(select(func.count()).select_from(table)) == before[table.__tablename__]
        identity = db.get(ExternalIdentityRow, UUID(session["identity"]["id"]))
        assert identity is not None
        selected = db.scalar(
            select(SessionRow)
            .where(SessionRow.identity_id == identity.id)
            .order_by(SessionRow.created_at.desc())
        )
        assert selected is not None and selected.membership_id is None


def test_company_creation_rechecks_identity_revocation_after_preload(
    settings: Settings, database: Database
) -> None:
    _client, session = creator_client(settings, database)
    identity_id = UUID(session["identity"]["id"])
    with database.session() as db:
        identity = db.get(ExternalIdentityRow, identity_id)
        selected = db.scalar(select(SessionRow).where(
            SessionRow.identity_id == identity_id,
            SessionRow.revoked_at.is_(None),
        ))
        assert identity is not None and identity.active and selected is not None
        with database.session() as concurrent:
            changed = concurrent.get(ExternalIdentityRow, identity_id)
            assert changed is not None
            changed.active = False
        with pytest.raises(AuthenticationRequired):
            CompanyService().create(
                db, selected, identity, "Should not exist", "revoked-creator-001"
            )
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(CompanyCreationCommandRow)) == 0
        assert db.scalar(select(func.count()).select_from(CompanyRow)) == 2


def test_customer_initial_settings_ignore_bootstrap_policy_and_seed_function(
    settings: Settings, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apbra_api.tenant_settings as tenant_settings

    def forbidden_seed(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("development seed cannot create customer settings")

    monkeypatch.setattr(tenant_settings, "seed_settings", forbidden_seed)
    monkeypatch.setattr(settings, "invitation_ttl_days", 30)
    monkeypatch.setattr(settings, "upload_policy_json", json.dumps({
        "data_extensions": ["CSV"],
        "reference_extensions": ["PNG"],
        "max_file_bytes": 1_000,
        "max_files_per_selection": 1,
        "max_data_items_per_report": 1,
        "max_reference_items_per_report": 1,
    }))
    creator, session = creator_client(settings, database)
    response = create_company(creator, session, "Approved Template Company")
    assert response.status_code == 201, response.text
    with database.session() as db:
        snapshot = current_settings(db, UUID(response.json()["company"]["id"]))
        assert snapshot.settings.invitation_ttl_days == 7
        assert snapshot.settings.upload_policy.max_file_bytes == 5_000_000
        assert snapshot.settings.upload_policy.data_extensions == ["CSV", "XLSX"]
        assert snapshot.settings.generation_policy.branding.primary == "#17635E"
        assert snapshot.settings.provider_profile is None
        assert not snapshot.settings.automatic_generation_enabled


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_first_company_creation_serializes_by_identity(
    settings: Settings, database: Database, same_key: bool
) -> None:
    clients = [TestClient(create_app(settings=settings, database=database)) for _ in range(2)]
    sessions = [sign_in(client, "creator") for client in clients]
    barrier = Barrier(2)

    def attempt(index: int) -> tuple[int, dict]:
        barrier.wait()
        key = "concurrent-company-001" if same_key else f"concurrent-company-00{index + 1}"
        result = create_company(clients[index], sessions[index], "Concurrent Company", key)
        return result.status_code, result.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(status for status, _ in results) == ([200, 201] if same_key else [201, 409])
    if same_key:
        assert results[0][1] == results[1][1]
    else:
        denied = next(body for status, body in results if status == 409)
        assert denied["error"]["code"] == "COMPANY_CREATION_NOT_AVAILABLE"
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(CompanyCreationCommandRow)) == 1
        assert db.scalar(select(func.count()).select_from(CompanyRow)) == 3
        assert db.scalar(select(func.count()).select_from(AuditEventRow).where(
            AuditEventRow.event_type == "COMPANY_CREATED"
        )) == 1


def test_company_creation_key_is_scoped_to_authenticated_identity(
    settings: Settings, database: Database
) -> None:
    creator, creator_session = creator_client(settings, database)
    uninvited = TestClient(create_app(settings=settings, database=database))
    uninvited_session = sign_in(uninvited, "uninvited")
    assert uninvited_session["membership_state"] == "COMPANY_CREATION_AVAILABLE"
    first = create_company(creator, creator_session, "First Owner", "shared-textual-key")
    second = create_company(uninvited, uninvited_session, "Second Owner", "shared-textual-key")
    assert first.status_code == second.status_code == 201
    assert first.json()["company"]["id"] != second.json()["company"]["id"]
    assert first.json()["membership"]["id"] != second.json()["membership"]["id"]


def test_eligible_invitation_precedes_first_company_creation(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    issued = owner.post(
        "/api/invitations",
        json={"subject": "dev-creator", "role": "MEMBER"},
        headers=csrf(owner_session),
    )
    assert issued.status_code == 200
    creator = TestClient(create_app(settings=settings, database=database))
    creator_session = sign_in(creator, "creator")
    assert creator_session["membership_state"] == "INVITATION_AVAILABLE"
    denied = create_company(creator, creator_session, "Avoid accidental new company")
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "COMPANY_CREATION_NOT_AVAILABLE"
    accepted = creator.post(
        "/api/invitations/accept",
        json={"token": issued.json()["token"]},
        headers=csrf(creator_session),
    )
    assert accepted.status_code == 200
    assert creator.get("/api/auth/session").json()["membership_state"] == "ACTIVE"
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(CompanyCreationCommandRow)) == 0


def test_profile_updates_mutable_display_only(settings: Settings, database: Database) -> None:
    creator, session = creator_client(settings, database)
    identity_id = UUID(session["identity"]["id"])
    with database.session() as db:
        identity = db.get(ExternalIdentityRow, identity_id)
        assert identity is not None
        stable = (identity.provider_profile_id, identity.issuer, identity.subject)
    current = creator.get("/api/profile")
    assert current.status_code == 200
    assert current.json() == {"profile": {"display_name": "Cora Creator"}}
    assert creator.patch(
        "/api/profile", json={"display_name": "New"}
    ).json()["error"]["code"] == "CSRF_INVALID"
    forbidden_fields = creator.patch(
        "/api/profile", json={"display_name": "New", "subject": "owner"},
        headers=csrf(session),
    )
    assert forbidden_fields.status_code == 422
    changed = creator.patch(
        "/api/profile", json={"display_name": "  Cora Preview  "},
        headers=csrf(session),
    )
    assert changed.status_code == 200
    assert changed.json() == {"profile": {"display_name": "Cora Preview"}}
    assert creator.get("/api/auth/session").json()["identity"]["display_name"] == "Cora Preview"
    with database.session() as db:
        identity = db.get(ExternalIdentityRow, identity_id)
        assert identity is not None
        assert (identity.provider_profile_id, identity.issuer, identity.subject) == stable
        assert identity.display_name == "Cora Preview"


def test_owner_only_role_mutation_and_last_owner_guard(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    memberships = owner.get("/api/memberships").json()["items"]
    owner_id = next(item["id"] for item in memberships if item["role"] == "COMPANY_OWNER")
    member_id = next(item["id"] for item in memberships if item["role"] == "MEMBER")
    self_deactivate = owner.post(
        f"/api/memberships/{owner_id}/deactivate", headers=csrf(owner_session)
    )
    assert self_deactivate.status_code == 403
    self_demote = owner.post(
        f"/api/memberships/{owner_id}/role", json={"role": "MEMBER"},
        headers=csrf(owner_session),
    )
    assert self_demote.status_code == 409
    assert self_demote.json()["error"]["code"] == "LAST_OWNER_REQUIRED"
    assert owner.post(
        f"/api/memberships/{member_id}/role", json={"role": "COMPANY_OWNER"},
        headers=csrf(owner_session),
    ).status_code == 422
    promoted = owner.post(
        f"/api/memberships/{member_id}/role", json={"role": "COMPANY_ADMIN"},
        headers=csrf(owner_session),
    )
    assert promoted.status_code == 200
    assert promoted.json()["membership"]["role"] == "COMPANY_ADMIN"
    admin = TestClient(create_app(settings=settings, database=database))
    admin_session = sign_in(admin, "member")
    assert admin.post(
        f"/api/memberships/{owner_id}/role", json={"role": "MEMBER"},
        headers=csrf(admin_session),
    ).status_code == 403
    assert admin.post(
        f"/api/memberships/{owner_id}/deactivate", headers=csrf(admin_session)
    ).status_code == 403
    with database.session() as db:
        owner_row = db.get(MembershipRow, UUID(owner_id))
        assert owner_row is not None and owner_row.active and owner_row.role == "COMPANY_OWNER"
        events = db.scalars(select(AuditEventRow).where(
            AuditEventRow.event_type == "MEMBERSHIP_ROLE_CHANGED"
        )).all()
        assert len(events) == 1


def test_admin_cannot_deactivate_company_owner(settings: Settings, database: Database) -> None:
    with database.session() as db:
        member = db.scalar(select(MembershipRow).where(MembershipRow.role == "MEMBER"))
        assert member is not None
        member.role = "COMPANY_ADMIN"

    admin = TestClient(create_app(settings=settings, database=database))
    admin_session = sign_in(admin, "member")
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    owner_id = owner_session["actor"]["membership_id"]

    response = admin.post(
        f"/api/memberships/{owner_id}/deactivate", headers=csrf(admin_session)
    )
    assert response.status_code == 403
    with database.session() as db:
        owner_row = db.get(MembershipRow, UUID(owner_id))
        assert owner_row is not None and owner_row.active


def test_stale_admin_actor_cannot_issue_revoke_or_mutate_membership(
    database: Database,
) -> None:
    with database.session() as db:
        admin = db.scalar(select(MembershipRow).where(MembershipRow.role == "MEMBER"))
        creator_identity = db.scalar(select(ExternalIdentityRow).where(
            ExternalIdentityRow.subject == "dev-creator"
        ))
        assert admin is not None and creator_identity is not None
        admin.role = "COMPANY_ADMIN"
        target = MembershipRow(
            company_id=admin.company_id,
            identity_id=creator_identity.id,
            role="MEMBER",
            active=True,
        )
        db.add(target)
        db.flush()
        stale_admin = db.active_actor(admin.id, admin.identity_id)
        assert stale_admin is not None and stale_admin.role == Role.COMPANY_ADMIN
        invitation, _token = InvitationService().issue(
            db, stale_admin, "new-subject", Role.MEMBER, 7
        )
        admin_id, target_id, invitation_id = admin.id, target.id, invitation.id

    with database.session() as db:
        admin = db.get(MembershipRow, admin_id)
        assert admin is not None and admin.role == "COMPANY_ADMIN"
        with database.session() as concurrent:
            changed = concurrent.get(MembershipRow, admin_id)
            assert changed is not None
            changed.role = "MEMBER"
        with pytest.raises(Forbidden):
            InvitationService().issue(db, stale_admin, "another-subject", Role.MEMBER, 7)
        with pytest.raises(Forbidden):
            InvitationService().revoke(db, stale_admin, invitation_id)
        with pytest.raises(Forbidden):
            MembershipService().deactivate(db, stale_admin, target_id)
        with pytest.raises(Forbidden):
            MembershipService().list(db, stale_admin)

    with database.session() as db:
        target = db.get(MembershipRow, target_id)
        invitation = db.get(InvitationRow, invitation_id)
        assert target is not None and target.active
        assert invitation is not None and invitation.revoked_at is None


def test_stale_owner_actor_cannot_change_roles(database: Database) -> None:
    with database.session() as db:
        owner = db.scalar(select(MembershipRow).where(MembershipRow.role == "COMPANY_OWNER"))
        member = db.scalar(select(MembershipRow).where(MembershipRow.role == "MEMBER"))
        creator_identity = db.scalar(select(ExternalIdentityRow).where(
            ExternalIdentityRow.subject == "dev-creator"
        ))
        assert owner is not None and member is not None and creator_identity is not None
        stale_owner = db.active_actor(owner.id, owner.identity_id)
        assert stale_owner is not None and stale_owner.role == Role.COMPANY_OWNER
        # A separate authorised ownership transition may leave this prior actor
        # active as admin; the captured role must not remain an authority grant.
        target = MembershipRow(
            company_id=owner.company_id,
            identity_id=creator_identity.id,
            role="MEMBER",
            active=True,
        )
        db.add(target)
        db.flush()
        owner_id, member_id, target_id = owner.id, member.id, target.id

    with database.session() as db:
        preloaded = db.get(MembershipRow, owner_id)
        assert preloaded is not None and preloaded.role == "COMPANY_OWNER"
        with database.session() as concurrent:
            changed_owner = concurrent.get(MembershipRow, owner_id)
            changed_member = concurrent.get(MembershipRow, member_id)
            assert changed_owner is not None and changed_member is not None
            changed_member.role = "COMPANY_OWNER"
            changed_owner.role = "COMPANY_ADMIN"
        with pytest.raises(Forbidden):
            MembershipService().change_role(db, stale_owner, target_id, Role.COMPANY_ADMIN)
    with database.session() as db:
        owner = db.get(MembershipRow, owner_id)
        member = db.get(MembershipRow, member_id)
        assert owner is not None and owner.role == "COMPANY_ADMIN"
        assert member is not None and member.role == "COMPANY_OWNER"


def test_consumed_invitation_replay_rejects_inactive_membership(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    issued = owner.post(
        "/api/invitations",
        json={"subject": "dev-uninvited", "role": "MEMBER"},
        headers=csrf(owner_session),
    )
    assert issued.status_code == 200

    invited = TestClient(create_app(settings=settings, database=database))
    invited_session = sign_in(invited, "uninvited")
    accepted = invited.post(
        "/api/invitations/accept",
        json={"token": issued.json()["token"]},
        headers=csrf(invited_session),
    )
    assert accepted.status_code == 200
    membership_id = UUID(accepted.json()["membership"]["id"])
    with database.session() as db:
        membership = db.get(MembershipRow, membership_id)
        assert membership is not None
        membership.active = False

    replay = invited.post(
        "/api/invitations/accept",
        json={"token": issued.json()["token"]},
        headers=csrf(invited_session),
    )
    assert replay.status_code == 410
    with database.session() as db:
        membership = db.get(MembershipRow, membership_id)
        assert membership is not None and not membership.active


def test_inactive_company_invitation_cannot_be_inspected_or_accepted(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    issued = owner.post(
        "/api/invitations",
        json={"subject": "dev-uninvited", "role": "MEMBER"},
        headers=csrf(owner_session),
    )
    assert issued.status_code == 200
    invitation_id = UUID(issued.json()["invitation"]["id"])
    with database.session() as db:
        invitation = db.get(InvitationRow, invitation_id)
        assert invitation is not None
        company = db.get(CompanyRow, invitation.company_id)
        assert company is not None
        company.active = False
    invited = TestClient(create_app(settings=settings, database=database))
    invited_session = sign_in(invited, "uninvited")
    token = issued.json()["token"]
    assert invited.post(
        "/api/invitations/inspect", json={"token": token}
    ).status_code == 410
    assert invited.post(
        "/api/invitations/accept", json={"token": token},
        headers=csrf(invited_session),
    ).status_code == 410
    with database.session() as db:
        invitation = db.get(InvitationRow, invitation_id)
        assert invitation is not None and invitation.consumed_at is None
        assert db.scalar(select(func.count()).select_from(MembershipRow).where(
            MembershipRow.company_id == invitation.company_id,
            MembershipRow.identity_id == UUID(invited_session["identity"]["id"]),
        )) == 0


def test_stale_selected_membership_surfaces_other_active_company(
    settings: Settings, database: Database
) -> None:
    client = TestClient(create_app(settings=settings, database=database))
    session = sign_in(client, "owner")
    actor = session["actor"]
    with database.session() as db:
        company = CompanyRow(name="Second company")
        db.add(company)
        db.flush()
        second = MembershipRow(
            company_id=company.id,
            identity_id=UUID(actor["identity_id"]),
            role="MEMBER",
            active=True,
        )
        db.add(second)
        selected = db.get(MembershipRow, UUID(actor["membership_id"]))
        assert selected is not None
        selected.active = False
        db.flush()
        second_id = second.id

    refreshed = client.get("/api/auth/session")
    assert refreshed.status_code == 200
    state = refreshed.json()
    assert state["membership_state"] == "COMPANY_SELECTION_REQUIRED"
    assert state["available_companies"] == [
        {"membership_id": str(second_id), "company_id": str(company.id),
         "name": "Second company"}
    ]
    assert "actor" not in state
    assert client.get("/api/cases").status_code == 401
