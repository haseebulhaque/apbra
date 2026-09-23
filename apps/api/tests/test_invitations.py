from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID

from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import select

from apbra_api.api import create_app
from apbra_api.config import Settings
from apbra_api.persistence import Database, InvitationRow


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


def test_active_member_cannot_accept_cross_company_membership(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    issued = owner.post(
        "/api/invitations",
        json={"subject": "dev-foreign", "role": "MEMBER"},
        headers=csrf(owner_session),
    ).json()
    foreign = TestClient(create_app(settings=settings, database=database))
    foreign_session = sign_in(foreign, "foreign")
    rejected = foreign.post(
        "/api/invitations/accept",
        json={"token": issued["token"]},
        headers=csrf(foreign_session),
    )
    assert rejected.status_code == 409
    assert sign_in(TestClient(create_app(settings=settings, database=database)), "foreign")[
        "actor"
    ]
