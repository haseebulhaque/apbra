from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import cast
from uuid import uuid4

import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import text

from apbra_api.api import create_app
from apbra_api.config import Settings
from apbra_api.persistence import ApplicationSession, Database


def create_case(client: TestClient, text: str, key: str | None = None) -> dict[str, object]:
    session = client.get("/api/auth/session").json()
    response = client.post(
        "/api/cases",
        json={"request_text": text},
        headers={**csrf(session), "Idempotency-Key": key or str(uuid4())},
    )
    assert response.status_code in {200, 201}
    return cast(dict[str, object], response.json()["case"])


def session_clone(settings: Settings, database: Database, source: TestClient) -> TestClient:
    clone = TestClient(create_app(settings=settings, database=database))
    clone.cookies.update(source.cookies)
    return clone


def test_create_list_resume_update_history_and_idempotency(client: TestClient) -> None:
    sign_in(client, "owner")
    key = str(uuid4())
    first = create_case(client, "Compare manufacturing throughput by plant.", key)
    repeated = create_case(client, "Compare manufacturing throughput by plant.", key)
    assert repeated["id"] == first["id"]

    session = client.get("/api/auth/session").json()
    conflict = client.post(
        "/api/cases",
        json={"request_text": "Different content"},
        headers={**csrf(session), "Idempotency-Key": key},
    )
    assert conflict.status_code == 409

    listed = client.get("/api/cases").json()["items"]
    assert any(item["id"] == first["id"] for item in listed)
    updated = client.put(
        f"/api/cases/{first['id']}",
        json={
            "request_text": "Compare monthly manufacturing throughput by plant.",
            "expected_version": 1,
        },
        headers=csrf(session),
    )
    assert updated.status_code == 200
    assert updated.json()["case"]["version"] == 2
    stale = client.put(
        f"/api/cases/{first['id']}",
        json={"request_text": "Overwrite stale meaning", "expected_version": 1},
        headers=csrf(session),
    )
    assert stale.status_code == 409
    versions = client.get(f"/api/cases/{first['id']}/versions").json()["items"]
    assert [item["sequence"] for item in versions] == [1, 2]
    assert versions[0]["request_text"] == "Compare manufacturing throughput by plant."


def test_four_unrelated_domains_use_same_case_path(client: TestClient) -> None:
    sign_in(client, "owner")
    requests = [
        "Show patient appointment capacity by clinic and week.",
        "Compare course completion by faculty and cohort.",
        "Track construction safety observations by site.",
        "Summarise subscription renewals by customer segment.",
    ]
    identifiers = {create_case(client, text)["id"] for text in requests}
    assert len(identifiers) == 4


def test_concurrent_equivalent_create_is_one_case_and_conflicting_replay_is_rejected(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")
    command_key = str(uuid4())
    payload = {"request_text": "Compare synthetic inventory movement by warehouse."}
    barrier = Barrier(2)
    clients = [session_clone(settings, database, client) for _ in range(2)]

    def submit(candidate: TestClient) -> tuple[int, dict[str, object]]:
        barrier.wait()
        response = candidate.post(
            "/api/cases",
            json=payload,
            headers={**csrf(session), "Idempotency-Key": command_key},
        )
        return response.status_code, cast(dict[str, object], response.json())

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, clients))
    finally:
        for candidate in clients:
            candidate.close()

    assert sorted(status for status, _ in results) == [200, 201]
    case_ids = {str(body["case"]["id"]) for _, body in results}
    assert len(case_ids) == 1
    case_id = case_ids.pop()
    conflict = client.post(
        "/api/cases",
        json={"request_text": "A different command payload."},
        headers={**csrf(session), "Idempotency-Key": command_key},
    )
    assert conflict.status_code == 409

    with database.session() as db:
        counts = (
            db.execute(
                text(
                    """
                SELECT
                  (SELECT count(*) FROM reporting_cases WHERE id=:case_id) AS cases,
                  (SELECT count(*) FROM case_request_versions WHERE case_id=:case_id) AS versions,
                  (SELECT count(*) FROM case_access WHERE case_id=:case_id) AS access_rows,
                  (SELECT count(*) FROM idempotency_records WHERE resource_id=:case_id) AS commands,
                  (SELECT count(*) FROM audit_events
                     WHERE resource_id=:case_id AND event_type='CASE_CREATED') AS audits
                """
                ),
                {"case_id": case_id},
            )
            .mappings()
            .one()
        )
    assert dict(counts) == {
        "cases": 1,
        "versions": 1,
        "access_rows": 1,
        "commands": 1,
        "audits": 1,
    }


def test_concurrent_updates_accept_one_and_reject_one_stale_version(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")
    created = create_case(client, "Review synthetic workforce capacity by team.")
    case_id = str(created["id"])
    barrier = Barrier(2)
    clients = [session_clone(settings, database, client) for _ in range(2)]

    def update(candidate_and_text: tuple[TestClient, str]) -> int:
        candidate, request_text = candidate_and_text
        barrier.wait()
        return candidate.put(
            f"/api/cases/{case_id}",
            json={"request_text": request_text, "expected_version": 1},
            headers=csrf(session),
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(
                executor.map(
                    update,
                    zip(
                        clients,
                        (
                            "Review monthly workforce capacity by team.",
                            "Review weekly workforce capacity by team.",
                        ),
                        strict=True,
                    ),
                )
            )
    finally:
        for candidate in clients:
            candidate.close()

    assert sorted(statuses) == [200, 409]
    with database.session() as db:
        row = (
            db.execute(
                text(
                    """
                SELECT
                  (SELECT version FROM reporting_cases WHERE id=:case_id) AS current_version,
                  (SELECT count(*) FROM case_request_versions WHERE case_id=:case_id) AS versions,
                  (SELECT count(*) FROM audit_events
                     WHERE resource_id=:case_id AND event_type='CASE_REQUEST_UPDATED') AS updates
                """
                ),
                {"case_id": case_id},
            )
            .mappings()
            .one()
        )
    assert dict(row) == {"current_version": 2, "versions": 2, "updates": 1}


def test_case_create_rolls_back_all_state_when_audit_write_fails(
    client: TestClient, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = sign_in(client, "member")

    def reject_case_audit(
        _self: ApplicationSession,
        _actor: object,
        event_type: str,
        _resource_type: str,
        _resource_id: object,
        _details: str = "{}",
    ) -> None:
        if event_type == "CASE_CREATED":
            raise RuntimeError("synthetic audit persistence failure")

    monkeypatch.setattr(ApplicationSession, "add_audit", reject_case_audit)
    with pytest.raises(RuntimeError, match="synthetic audit persistence failure"):
        client.post(
            "/api/cases",
            json={"request_text": "This command must roll back."},
            headers={**csrf(session), "Idempotency-Key": str(uuid4())},
        )

    with database.session() as db:
        counts = (
            db.execute(
                text(
                    """
                SELECT
                  (SELECT count(*) FROM reporting_cases) AS cases,
                  (SELECT count(*) FROM case_request_versions) AS versions,
                  (SELECT count(*) FROM case_access) AS access_rows,
                  (SELECT count(*) FROM idempotency_records) AS commands,
                  (SELECT count(*) FROM audit_events) AS audits
                """
                )
            )
            .mappings()
            .one()
        )
    assert dict(counts) == {
        "cases": 0,
        "versions": 0,
        "access_rows": 0,
        "commands": 0,
        "audits": 0,
    }


def test_case_remains_available_after_api_and_database_adapter_restart(
    client: TestClient, settings: Settings, database: Database
) -> None:
    sign_in(client, "member")
    created = create_case(client, "Retain this synthetic request across restart.")
    case_id = str(created["id"])
    restarted_database = Database(settings.database_url)
    restarted_client = TestClient(create_app(settings=settings, database=restarted_database))
    restarted_client.cookies.update(client.cookies)
    database.engine.dispose()
    try:
        response = restarted_client.get(f"/api/cases/{case_id}")
        assert response.status_code == 200
        assert response.json()["case"]["current_request"]["request_text"] == (
            "Retain this synthetic request across restart."
        )
    finally:
        restarted_client.close()
        restarted_database.engine.dispose()
