from typing import cast
from uuid import uuid4

from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import select

from apbra_api.api import create_app
from apbra_api.config import Settings
from apbra_api.persistence import AuditEventRow, CaseAccessRow, Database, MembershipRow


def test_foreign_and_same_company_ungranted_users_receive_same_404(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    sign_in(owner, "owner")
    session = owner.get("/api/auth/session").json()
    created = owner.post(
        "/api/cases",
        json={"request_text": "Private operations report"},
        headers={**csrf(session), "Idempotency-Key": "private-case-denial-001"},
    ).json()["case"]

    same_company = TestClient(create_app(settings=settings, database=database))
    sign_in(same_company, "member")
    foreign = TestClient(create_app(settings=settings, database=database))
    sign_in(foreign, "foreign")
    same = same_company.get(f"/api/cases/{created['id']}")
    other = foreign.get(f"/api/cases/{created['id']}")
    assert (same.status_code, same.json()) == (other.status_code, other.json())
    assert same.status_code == 404


def test_deactivated_membership_and_revoked_private_grant_apply_to_existing_session(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    sign_in(owner, "owner")
    session = owner.get("/api/auth/session").json()
    key = str(uuid4())
    created = owner.post(
        "/api/cases",
        json={"request_text": "Private workforce report"},
        headers={**csrf(session), "Idempotency-Key": key},
    ).json()["case"]
    with database.session() as db:
        access = db.scalar(select(CaseAccessRow).where(CaseAccessRow.case_id == created["id"]))
        assert access is not None
        access.active = False
    assert owner.get(f"/api/cases/{created['id']}").status_code == 404
    replay = owner.post(
        "/api/cases",
        json={"request_text": "Private workforce report"},
        headers={**csrf(session), "Idempotency-Key": key},
    )
    assert replay.status_code == 404

    with database.session() as db:
        membership = db.scalar(
            select(MembershipRow).where(MembershipRow.id == session["actor"]["membership_id"])
        )
        assert membership is not None
        membership.active = False
    assert owner.get("/api/cases").status_code == 401


def test_owner_grants_and_revokes_private_case_access_through_api(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    created = owner.post(
        "/api/cases",
        json={"request_text": "Private logistics exception report"},
        headers={**csrf(owner_session), "Idempotency-Key": "case-access-api-001"},
    ).json()["case"]
    members = owner.get("/api/memberships").json()["items"]
    member_id = next(item["id"] for item in members if item["subject"] == "dev-member")

    granted = owner.post(
        f"/api/cases/{created['id']}/access",
        json={"membership_id": member_id, "access_level": "VIEWER"},
        headers=csrf(owner_session),
    )
    assert granted.status_code == 200
    listed = owner.get(f"/api/cases/{created['id']}/access")
    assert listed.status_code == 200
    assert any(
        item["membership_id"] == member_id
        and item["access_level"] == "VIEWER"
        and item["active"]
        for item in listed.json()["items"]
    )

    member = TestClient(create_app(settings=settings, database=database))
    sign_in(member, "member")
    assert member.get(f"/api/cases/{created['id']}").status_code == 200
    assert member.get(f"/api/cases/{created['id']}/access").status_code == 403

    revoked = owner.post(
        f"/api/cases/{created['id']}/access/{member_id}/revoke",
        headers=csrf(owner_session),
    )
    assert revoked.status_code == 200
    denied = member.get(f"/api/cases/{created['id']}")
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "CASE_NOT_FOUND"

    with database.session() as db:
        events = db.scalars(
            select(AuditEventRow)
            .where(AuditEventRow.resource_id == created["id"])
            .order_by(AuditEventRow.created_at)
        ).all()
        assert [event.event_type for event in events][-2:] == [
            "CASE_ACCESS_GRANTED",
            "CASE_ACCESS_REVOKED",
        ]
        assert member_id in events[-2].details_json
        assert member_id in events[-1].details_json


def test_case_access_grant_rejects_foreign_or_owner_role_without_disclosure(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    created = owner.post(
        "/api/cases",
        json={"request_text": "Private customer retention report"},
        headers={**csrf(owner_session), "Idempotency-Key": "case-access-api-002"},
    ).json()["case"]

    foreign = TestClient(create_app(settings=settings, database=database))
    sign_in(foreign, "foreign")
    foreign_members = foreign.get("/api/memberships").json()["items"]
    foreign_id = foreign_members[0]["id"]
    response = owner.post(
        f"/api/cases/{created['id']}/access",
        json={"membership_id": foreign_id, "access_level": "EDITOR"},
        headers=csrf(owner_session),
    )
    assert response.status_code == 403
    assert "company" not in response.text.lower()

    owner_actor = cast(dict[str, object], owner_session["actor"])
    own_membership = owner_actor["membership_id"]
    owner_level = owner.post(
        f"/api/cases/{created['id']}/access",
        json={"membership_id": own_membership, "access_level": "OWNER"},
        headers=csrf(owner_session),
    )
    assert owner_level.status_code == 403


def test_only_owner_or_admin_can_deactivate_another_company_membership(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    members = owner.get("/api/memberships").json()["items"]
    member = next(item for item in members if item["subject"] == "dev-member")
    response = owner.post(
        f"/api/memberships/{member['id']}/deactivate", headers=csrf(owner_session)
    )
    assert response.status_code == 200

    member_client = TestClient(create_app(settings=settings, database=database))
    sign_in(member_client, "member")
    assert member_client.get("/api/cases").status_code == 401

    actor = cast(dict[str, object], owner_session["actor"])
    owner_id = actor["membership_id"]
    assert (
        owner.post(
            f"/api/memberships/{owner_id}/deactivate", headers=csrf(owner_session)
        ).status_code
        == 403
    )
