from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID

from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import select

from apbra_api.api import create_app
from apbra_api.config import Settings
from apbra_api.persistence import (
    AuditEventRow,
    Database,
    ExternalIdentityRow,
    InvitationRow,
    MembershipRow,
)


def test_single_use_digest_only_invitation_acceptance(
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
    raw = issued.json()["token"]
    invitation_id = issued.json()["invitation"]["id"]
    with database.session() as db:
        row = db.scalar(select(InvitationRow).where(InvitationRow.id == invitation_id))
        assert row is not None
        assert row.token_digest != raw
        assert raw not in row.token_digest

    invited = TestClient(create_app(settings=settings, database=database))
    invited_session = sign_in(invited, "uninvited")
    accepted = invited.post(
        "/api/invitations/accept", json={"token": raw}, headers=csrf(invited_session)
    )
    assert accepted.status_code == 200
    repeated = invited.post(
        "/api/invitations/accept", json={"token": raw}, headers=csrf(invited_session)
    )
    assert repeated.status_code == 200
    assert raw not in str(repeated.json())


def test_invitation_profile_mismatch_cannot_join_with_same_issuer_subject(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    issued = owner.post(
        "/api/invitations",
        json={"subject": "dev-uninvited", "role": "MEMBER"},
        headers=csrf(owner_session),
    ).json()
    with database.session() as db:
        row = db.get(InvitationRow, UUID(issued["invitation"]["id"]))
        assert row is not None and row.provider_profile_id == "legacy-unqualified"
        row.provider_profile_id = "different-qualified-profile"
    invited = TestClient(create_app(settings=settings, database=database))
    invited_session = sign_in(invited, "uninvited")
    assert (
        invited.post(
            "/api/invitations/accept",
            json={"token": issued["token"]},
            headers=csrf(invited_session),
        ).status_code
        == 410
    )


def test_expired_invitation_is_terminal(settings: Settings, database: Database) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    session = sign_in(owner, "owner")
    issued = owner.post(
        "/api/invitations",
        json={"subject": "dev-uninvited", "role": "MEMBER"},
        headers=csrf(session),
    ).json()
    with database.session() as db:
        row = db.get(InvitationRow, UUID(issued["invitation"]["id"]))
        assert row is not None
        row.expires_at = datetime(2000, 1, 1, tzinfo=UTC)
    inspected = owner.post("/api/invitations/inspect", json={"token": issued["token"]})
    assert inspected.status_code == 410


def test_revoked_and_cross_subject_invitations_fail_without_token_echo(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    issued = owner.post(
        "/api/invitations",
        json={"subject": "dev-uninvited", "role": "MEMBER"},
        headers=csrf(owner_session),
    ).json()
    foreign = TestClient(create_app(settings=settings, database=database))
    foreign_session = sign_in(foreign, "foreign")
    rejected = foreign.post(
        "/api/invitations/accept",
        json={"token": issued["token"]},
        headers=csrf(foreign_session),
    )
    assert rejected.status_code == 410
    assert issued["token"] not in rejected.text

    revoked = owner.post(
        f"/api/invitations/{issued['invitation']['id']}/revoke",
        headers=csrf(owner_session),
    )
    assert revoked.status_code == 200
    assert (
        owner.post("/api/invitations/inspect", json={"token": issued["token"]}).status_code == 410
    )


def test_concurrent_single_use_acceptance_is_idempotent_for_same_identity(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    issued = owner.post(
        "/api/invitations",
        json={"subject": "dev-uninvited", "role": "MEMBER"},
        headers=csrf(owner_session),
    ).json()
    clients = [TestClient(create_app(settings=settings, database=database)) for _ in range(2)]
    sessions = [sign_in(item, "uninvited") for item in clients]
    barrier = Barrier(2)

    def accept(index: int) -> tuple[int, str]:
        barrier.wait()
        response = clients[index].post(
            "/api/invitations/accept",
            json={"token": issued["token"]},
            headers=csrf(sessions[index]),
        )
        return response.status_code, response.json()["membership"]["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, range(2)))
    assert [status for status, _ in results] == [200, 200]
    assert len({membership_id for _, membership_id in results}) == 1


def test_active_member_accepts_exact_second_company_invitation_without_private_grants(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    foreign = TestClient(create_app(settings=settings, database=database))
    foreign_session = sign_in(foreign, "foreign")
    owner_actor = owner_session["actor"]
    foreign_actor = foreign_session["actor"]
    assert owner_actor["company_id"] != foreign_actor["company_id"]
    owner_case = owner.post(
        "/api/cases",
        json={"request_text": "Private owner-company operations"},
        headers={**csrf(owner_session), "Idempotency-Key": "invitation-f1-owner-case"},
    ).json()["case"]
    foreign_case = foreign.post(
        "/api/cases",
        json={"request_text": "Private existing-company operations"},
        headers={**csrf(foreign_session), "Idempotency-Key": "invitation-f1-foreign-case"},
    ).json()["case"]
    issued = owner.post(
        "/api/invitations",
        json={"subject": "dev-foreign", "role": "EXPERT"},
        headers=csrf(owner_session),
    ).json()
    accepted = foreign.post(
        "/api/invitations/accept",
        json={"token": issued["token"]},
        headers=csrf(foreign_session),
    )
    assert accepted.status_code == 200
    target_id = accepted.json()["membership"]["id"]
    assert accepted.json()["membership"]["role"] == "EXPERT"
    current = foreign.get("/api/auth/session").json()
    assert current["membership_state"] == "ACTIVE"
    assert current["actor"]["membership_id"] == target_id
    assert current["actor"]["company_id"] == owner_actor["company_id"]
    assert foreign.get(f"/api/cases/{owner_case['id']}").status_code == 404
    assert foreign.get(f"/api/cases/{foreign_case['id']}").status_code == 404

    repeated = foreign.post(
        "/api/invitations/accept",
        json={"token": issued["token"]},
        headers=csrf(current),
    )
    assert repeated.status_code == 200
    assert repeated.json()["membership"]["id"] == target_id
    with database.session() as db:
        memberships = list(
            db.scalars(
                select(MembershipRow).where(
                    MembershipRow.identity_id == UUID(foreign_actor["identity_id"])
                )
            )
        )
        assert len(memberships) == 2
        assert {str(row.id) for row in memberships} == {
            foreign_actor["membership_id"],
            target_id,
        }
        assert {str(row.company_id) for row in memberships} == {
            foreign_actor["company_id"],
            owner_actor["company_id"],
        }
        assert all(row.active for row in memberships)
        invitation = db.get(InvitationRow, UUID(issued["invitation"]["id"]))
        assert invitation is not None and invitation.consumed_at is not None
        assert invitation.consumed_by_identity_id == UUID(foreign_actor["identity_id"])
        audits = list(
            db.scalars(
                select(AuditEventRow).where(
                    AuditEventRow.event_type == "INVITATION_ACCEPTED",
                    AuditEventRow.resource_id == invitation.id,
                )
            )
        )
        assert len(audits) == 1

    fresh = TestClient(create_app(settings=settings, database=database))
    fresh_session = sign_in(fresh, "foreign")
    assert fresh_session["membership_state"] == "COMPANY_SELECTION_REQUIRED"
    assert "actor" not in fresh_session
    companies = fresh_session["available_companies"]
    assert len(companies) == 2
    assert {item["membership_id"] for item in companies} == {
        foreign_actor["membership_id"],
        target_id,
    }
    assert {item["company_id"] for item in companies} == {
        foreign_actor["company_id"],
        owner_actor["company_id"],
    }
    assert fresh.get(f"/api/cases/{owner_case['id']}").status_code == 401

    selected_foreign = fresh.post(
        "/api/auth/select-company",
        json={"membership_id": foreign_actor["membership_id"]},
        headers=csrf(fresh_session),
    )
    assert selected_foreign.status_code == 200
    assert (
        fresh.get("/api/auth/session").json()["actor"]["company_id"]
        == (foreign_actor["company_id"])
    )
    assert fresh.get(f"/api/cases/{foreign_case['id']}").status_code == 200
    assert fresh.get(f"/api/cases/{owner_case['id']}").status_code == 404

    selected_target = fresh.post(
        "/api/auth/select-company",
        json={"membership_id": target_id},
        headers=csrf(fresh_session),
    )
    assert selected_target.status_code == 200
    assert (
        fresh.get("/api/auth/session").json()["actor"]["company_id"] == (owner_actor["company_id"])
    )
    assert fresh.get(f"/api/cases/{owner_case['id']}").status_code == 404
    assert fresh.get(f"/api/cases/{foreign_case['id']}").status_code == 404


def test_existing_target_memberships_are_never_duplicated_or_reactivated(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    member = TestClient(create_app(settings=settings, database=database))
    member_session = sign_in(member, "member")
    active_invitation = owner.post(
        "/api/invitations",
        json={"subject": "dev-member", "role": "EXPERT"},
        headers=csrf(owner_session),
    ).json()
    assert (
        member.post(
            "/api/invitations/accept",
            json={"token": active_invitation["token"]},
            headers=csrf(member_session),
        ).status_code
        == 409
    )

    foreign = TestClient(create_app(settings=settings, database=database))
    foreign_session = sign_in(foreign, "foreign")
    with database.session() as db:
        inactive = MembershipRow(
            company_id=UUID(owner_session["actor"]["company_id"]),
            identity_id=UUID(foreign_session["actor"]["identity_id"]),
            role="MEMBER",
            active=False,
        )
        db.add(inactive)
        db.flush()
        inactive_id = inactive.id
    inactive_invitation = owner.post(
        "/api/invitations",
        json={"subject": "dev-foreign", "role": "EXPERT"},
        headers=csrf(owner_session),
    ).json()
    assert (
        foreign.post(
            "/api/invitations/accept",
            json={"token": inactive_invitation["token"]},
            headers=csrf(foreign_session),
        ).status_code
        == 409
    )
    with database.session() as db:
        active = db.get(InvitationRow, UUID(active_invitation["invitation"]["id"]))
        rejected = db.get(InvitationRow, UUID(inactive_invitation["invitation"]["id"]))
        target = db.get(MembershipRow, inactive_id)
        assert active is not None and active.consumed_at is None
        assert rejected is not None and rejected.consumed_at is None
        assert target is not None and not target.active and target.role == "MEMBER"
        target_membership = db.scalar(
            select(MembershipRow).where(
                MembershipRow.identity_id == UUID(foreign_session["actor"]["identity_id"]),
                MembershipRow.company_id == UUID(owner_session["actor"]["company_id"]),
            )
        )
        assert target_membership is not None and target_membership.id == inactive_id
    assert (
        foreign.get("/api/auth/session").json()["actor"]["membership_id"]
        == (foreign_session["actor"]["membership_id"])
    )


def test_invitation_issuer_mismatch_cannot_join(settings: Settings, database: Database) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    issued = owner.post(
        "/api/invitations",
        json={"subject": "dev-uninvited", "role": "MEMBER"},
        headers=csrf(owner_session),
    ).json()
    with database.session() as db:
        invitation = db.get(InvitationRow, UUID(issued["invitation"]["id"]))
        assert invitation is not None
        invitation.invited_issuer = "https://untrusted-issuer.invalid"
    invited = TestClient(create_app(settings=settings, database=database))
    invited_session = sign_in(invited, "uninvited")
    assert (
        invited.post(
            "/api/invitations/accept",
            json={"token": issued["token"]},
            headers=csrf(invited_session),
        ).status_code
        == 410
    )


def test_concurrent_cross_company_acceptance_preserves_both_memberships(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    foreign = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    foreign_session = sign_in(foreign, "foreign")
    invitations = [
        owner.post(
            "/api/invitations",
            json={"subject": "dev-uninvited", "role": "MEMBER"},
            headers=csrf(owner_session),
        ).json(),
        foreign.post(
            "/api/invitations",
            json={"subject": "dev-uninvited", "role": "MEMBER"},
            headers=csrf(foreign_session),
        ).json(),
    ]
    clients = [TestClient(create_app(settings=settings, database=database)) for _ in range(2)]
    sessions = [sign_in(client, "uninvited") for client in clients]
    barrier = Barrier(2)

    def accept(index: int) -> int:
        barrier.wait()
        return (
            clients[index]
            .post(
                "/api/invitations/accept",
                json={"token": invitations[index]["token"]},
                headers=csrf(sessions[index]),
            )
            .status_code
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(accept, range(2)))
    assert statuses == [200, 200]

    with database.session() as db:
        identity = db.scalar(
            select(ExternalIdentityRow).where(ExternalIdentityRow.subject == "dev-uninvited")
        )
        assert identity is not None
        memberships = list(
            db.scalars(
                select(MembershipRow).where(
                    MembershipRow.identity_id == identity.id,
                    MembershipRow.active.is_(True),
                )
            )
        )
        rows = list(
            db.scalars(
                select(InvitationRow).where(
                    InvitationRow.id.in_([UUID(item["invitation"]["id"]) for item in invitations])
                )
            )
        )
        audits = list(
            db.scalars(
                select(AuditEventRow).where(
                    AuditEventRow.event_type == "INVITATION_ACCEPTED",
                    AuditEventRow.resource_id.in_([row.id for row in rows]),
                )
            )
        )
        assert len(memberships) == 2
        assert {row.company_id for row in memberships} == {row.company_id for row in rows}
        assert len({row.id for row in memberships}) == 2
        assert all(row.consumed_at is not None for row in rows)
        assert {audit.resource_id for audit in audits} == {row.id for row in rows}
        assert len(audits) == 2


def test_concurrent_distinct_same_company_invitations_conflict_explicitly(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    invitations = [
        owner.post(
            "/api/invitations",
            json={"subject": "dev-uninvited", "role": "MEMBER"},
            headers=csrf(owner_session),
        ).json()
        for _ in range(2)
    ]
    clients = [TestClient(create_app(settings=settings, database=database)) for _ in range(2)]
    sessions = [sign_in(client, "uninvited") for client in clients]
    barrier = Barrier(2)

    def accept(index: int) -> int:
        barrier.wait()
        return (
            clients[index]
            .post(
                "/api/invitations/accept",
                json={"token": invitations[index]["token"]},
                headers=csrf(sessions[index]),
            )
            .status_code
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(accept, range(2)))
    assert sorted(statuses) == [200, 409]

    with database.session() as db:
        identity = db.scalar(
            select(ExternalIdentityRow).where(ExternalIdentityRow.subject == "dev-uninvited")
        )
        assert identity is not None
        memberships = list(
            db.scalars(
                select(MembershipRow).where(
                    MembershipRow.identity_id == identity.id,
                    MembershipRow.active.is_(True),
                )
            )
        )
        rows = list(
            db.scalars(
                select(InvitationRow).where(
                    InvitationRow.id.in_([UUID(item["invitation"]["id"]) for item in invitations])
                )
            )
        )
        audits = list(
            db.scalars(
                select(AuditEventRow).where(
                    AuditEventRow.event_type == "INVITATION_ACCEPTED",
                    AuditEventRow.resource_id.in_([row.id for row in rows]),
                )
            )
        )
        assert len(memberships) == 1
        assert sum(row.consumed_at is not None for row in rows) == 1
        assert len(audits) == 1
