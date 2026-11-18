"""Date display never changes tenant policy digests, UTC storage, or authority."""

from copy import deepcopy
from uuid import UUID

import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from apbra_api.persistence import Database, MembershipRow, TenantDateDisplayVersionRow
from apbra_api.tenant_date_display import DateDisplayUpdate


def headers(session):
    return {**csrf(session), "X-Expected-Membership-Id": session["actor"]["membership_id"]}


@pytest.mark.parametrize(
    "zone", ["Australia/Sydney", "Australia/Perth", "UTC", "America/New_York", "Asia/Kolkata", None]
)
def test_valid_iana_preference(zone):
    assert DateDisplayUpdate(expected_version=0, time_zone=zone).time_zone == zone


@pytest.mark.parametrize(
    "zone",
    [
        "",
        "Sydney",
        "../etc/passwd",
        "/etc/localtime",
        "+11:00",
        "UTC+11",
        " Australia/Sydney",
        "Factory",
        "localtime",
        1,
        True,
    ],
)
def test_invalid_iana_preference(zone):
    with pytest.raises(ValidationError):
        DateDisplayUpdate(expected_version=0, time_zone=zone)


def test_unset_is_read_only_browser_local_default(client: TestClient, database: Database):
    owner = sign_in(client, "owner")
    expected = {"company_id": owner["actor"]["company_id"], "version": 0, "time_zone": None}
    for _ in range(2):
        response = client.get("/api/workspace/date-display")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == expected
    with database.session() as db:
        assert list(db.scalars(select(TenantDateDisplayVersionRow))) == []
    assert client.get(
        "/api/tenant-settings/date-display/history", headers=headers(owner)
    ).json() == {"items": []}


def test_versioned_tenant_preference_preserves_policy_and_foreign_default(client: TestClient):
    owner = sign_in(client, "owner")
    before = deepcopy(client.get("/api/tenant-settings").json())
    before_history = deepcopy(client.get("/api/tenant-settings/history").json())
    path = "/api/tenant-settings/date-display"
    saved = client.patch(
        path, headers=headers(owner), json={"expected_version": 0, "time_zone": "Australia/Perth"}
    )
    assert saved.status_code == 200
    assert saved.json() == {
        "company_id": owner["actor"]["company_id"],
        "version": 1,
        "time_zone": "Australia/Perth",
    }
    assert client.get("/api/tenant-settings").json() == before
    assert client.get("/api/tenant-settings/history").json() == before_history
    sign_in(client, "member")
    assert client.get("/api/workspace/date-display").json() == saved.json()
    foreign = sign_in(client, "foreign")
    assert client.get("/api/workspace/date-display").json() == {
        "company_id": foreign["actor"]["company_id"],
        "version": 0,
        "time_zone": None,
    }
    owner = sign_in(client, "owner")
    assert (
        client.patch(
            path, headers=headers(owner), json={"expected_version": 0, "time_zone": "UTC"}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            path, headers=headers(owner), json={"expected_version": 1, "time_zone": None}
        ).status_code
        == 200
    )
    history = client.get(path + "/history", headers=headers(owner)).json()["items"]
    assert [item["version"] for item in history] == [2, 1]
    assert [item["time_zone"] for item in history] == [None, "Australia/Perth"]
    assert all(item["created_at"].endswith("+00:00") for item in history)


@pytest.mark.parametrize("role", ["MEMBER", "EXPERT"])
def test_non_admin_cannot_read_admin_history_or_change_dates(
    client: TestClient, database: Database, role: str
):
    session = sign_in(client, "member")
    with database.session() as db:
        row = db.get(MembershipRow, UUID(session["actor"]["membership_id"]))
        assert row is not None
        row.role = role
        db.commit()
    for suffix in ["", "/history"]:
        assert (
            client.get(
                "/api/tenant-settings/date-display" + suffix, headers=headers(session)
            ).status_code
            == 403
        )
    assert (
        client.patch(
            "/api/tenant-settings/date-display",
            headers=headers(session),
            json={"expected_version": 0, "time_zone": "UTC"},
        ).status_code
        == 403
    )
    assert client.get("/api/workspace/date-display").status_code == 200


def test_rejects_selectors_missing_membership_csrf_invalid_extra_and_stale_inputs(
    client: TestClient,
):
    assert client.get("/api/workspace/date-display").status_code == 401
    session = sign_in(client, "owner")
    path = "/api/tenant-settings/date-display"
    valid = {"expected_version": 0, "time_zone": "UTC"}
    assert (
        client.patch(
            path,
            headers={"X-Expected-Membership-Id": session["actor"]["membership_id"]},
            json=valid,
        ).status_code
        == 401
    )
    assert client.patch(path, headers=csrf(session), json=valid).status_code == 409
    for patch in [
        {"time_zone": "Australia/Invalid"},
        {"expected_version": True},
        {"expected_version": -1},
        {"company_id": "foreign"},
    ]:
        assert (
            client.patch(path, headers=headers(session), json={**valid, **patch}).status_code == 422
        )
    for url in ["/api/workspace/date-display", path, path + "/history"]:
        assert client.get(url + "?company_id=foreign", headers=headers(session)).status_code == 422
    assert client.get("/api/workspace/date-display").json()["version"] == 0


def test_date_history_is_immutable_in_database(client: TestClient, database: Database):
    owner = sign_in(client, "owner")
    assert (
        client.patch(
            "/api/tenant-settings/date-display",
            headers=headers(owner),
            json={"expected_version": 0, "time_zone": "UTC"},
        ).status_code
        == 200
    )
    for operation in ["update", "delete"]:
        with database.session() as db:
            row = db.scalar(
                select(TenantDateDisplayVersionRow).where(
                    TenantDateDisplayVersionRow.company_id == UUID(owner["actor"]["company_id"])
                )
            )
            assert row is not None
            if operation == "delete":
                db.delete(row)
            else:
                row.time_zone = "Europe/London"
            with pytest.raises(DBAPIError):
                db.commit()
            db.rollback()


def test_simultaneous_first_save_has_one_winner(client: TestClient, database: Database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from apbra_api.domain import Actor, Conflict, Role
    from apbra_api.tenant_date_display import update

    owner = sign_in(client, "owner")
    with database.session() as db:
        membership = db.get(MembershipRow, UUID(owner["actor"]["membership_id"]))
        assert membership is not None
        actor = Actor(
            membership.identity_id,
            membership.id,
            membership.company_id,
            "synthetic",
            "synthetic",
            "Synthetic owner",
            Role.COMPANY_OWNER,
            "synthetic",
        )
    barrier = Barrier(2)

    def save(zone):
        with database.session() as db:
            barrier.wait(timeout=5)
            try:
                value = update(db, actor, DateDisplayUpdate(expected_version=0, time_zone=zone))
                db.commit()
                return value["version"]
            except Conflict:
                db.rollback()
                return "CONFLICT"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["Australia/Perth", "Europe/London"]))
    assert results.count(1) == results.count("CONFLICT") == 1
    assert (
        len(
            client.get("/api/tenant-settings/date-display/history", headers=headers(owner)).json()[
                "items"
            ]
        )
        == 1
    )


@pytest.mark.parametrize("state", ["membership", "company", "identity", "selection"])
def test_date_preferences_require_current_active_identity_and_membership(
    client: TestClient, database: Database, state: str
):
    from apbra_api.persistence import CompanyRow, ExternalIdentityRow, SessionRow

    session = sign_in(client, "owner")
    with database.session() as db:
        member = db.get(MembershipRow, UUID(session["actor"]["membership_id"]))
        assert member is not None
        if state == "membership":
            member.active = False
        elif state == "company":
            db.get(CompanyRow, member.company_id).active = False
        elif state == "identity":
            db.get(ExternalIdentityRow, member.identity_id).active = False
        else:
            db.scalar(
                select(SessionRow).where(SessionRow.identity_id == member.identity_id)
            ).membership_id = None
        db.commit()
    for path in [
        "/api/workspace/date-display",
        "/api/tenant-settings/date-display",
        "/api/tenant-settings/date-display/history",
    ]:
        assert client.get(path, headers=headers(session)).status_code == 401
    assert (
        client.patch(
            "/api/tenant-settings/date-display",
            headers=headers(session),
            json={"expected_version": 0, "time_zone": "UTC"},
        ).status_code
        == 401
    )


def test_existing_company_admin_can_save_without_provider_authentication(
    client: TestClient, database: Database
):
    session = sign_in(client, "member")
    with database.session() as db:
        member = db.get(MembershipRow, UUID(session["actor"]["membership_id"]))
        assert member is not None
        member.role = "COMPANY_ADMIN"
        db.commit()
    response = client.patch(
        "/api/tenant-settings/date-display",
        headers=headers(session),
        json={"expected_version": 0, "time_zone": "Europe/London"},
    )
    assert response.status_code == 200
    history = client.get(
        "/api/tenant-settings/audit-events",
        headers=headers(session),
        params={
            "module": "Settings",
            "operation": "TENANT_DATE_DISPLAY_UPDATED",
            "page": 1,
            "limit": 10,
        },
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["outcome"] == "SUCCEEDED"
