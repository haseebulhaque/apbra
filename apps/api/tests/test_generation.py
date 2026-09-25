from __future__ import annotations

import hashlib
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from io import BytesIO
from pathlib import Path
from threading import Barrier, Event
from uuid import uuid4

import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from apbra_api.api import create_app
from apbra_api.artifacts import LocalArtifactStore
from apbra_api.config import Settings
from apbra_api.domain import GenerationFailed
from apbra_api.generation import GenerationBridge
from apbra_api.persistence import ApplicationSession, Database


def confirmed_case(
    client: TestClient, session: dict[str, object], request: str, filename: str, content: bytes
) -> tuple[dict[str, object], dict[str, object]]:
    case = client.post(
        "/api/cases",
        json={"request_text": request},
        headers={**csrf(session), "Idempotency-Key": str(uuid4())},
    ).json()["case"]
    evidence = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": filename, "expected_context_version": 1},
        content=content,
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    contract = confirm_current_case(client, session, case["id"], evidence)
    return case, contract


def confirm_current_case(
    client: TestClient,
    session: dict[str, object],
    case_id: str,
    evidence: dict[str, object],
) -> dict[str, object]:
    interpretation = client.post(
        f"/api/cases/{case_id}/interpretations",
        json={"expected_context_version": evidence["semantic_context_version"]},
        headers=csrf(session),
    ).json()["interpretation"]
    if interpretation["state"] == "NEEDS_CLARIFICATION":
        question = interpretation["questions"][0]
        option = question["suggestions"][0]
        event = client.post(
            f"/api/cases/{case_id}/conversation",
            json={
                "kind": "RAW_ANSWER",
                "payload": {
                    "questionId": question["id"],
                    "interpretationId": interpretation["id"],
                    "rawAnswer": option["label"],
                    "suggestionId": option["id"],
                    "decision": "ACCEPT",
                },
                "expected_context_version": evidence["semantic_context_version"],
                "command_key": str(uuid4()),
            },
            headers=csrf(session),
        ).json()["event"]
        interpretation = client.post(
            f"/api/cases/{case_id}/interpretations",
            json={"expected_context_version": event["semantic_context_version"]},
            headers=csrf(session),
        ).json()["interpretation"]
    assert interpretation["state"] == "READY_FOR_CONFIRMATION"
    contract = client.post(
        f"/api/cases/{case_id}/confirm",
        json={
            "interpretation_id": interpretation["id"],
            "expected_context_version": interpretation["context_version"],
        },
        headers=csrf(session),
    ).json()["confirmed_contract"]
    return contract


@pytest.mark.parametrize(
    ("business_request", "filename", "content"),
    [
        (
            "Show total appointment duration by clinic.",
            "appointments.csv",
            b"Clinic,Duration\nNorth,20\nSouth,35\n",
        ),
        (
            "Summarise attendance count by campus.",
            "attendance.csv",
            b"Campus,Attendance\nCity,120\nRural,95\n",
        ),
        (
            "Compare inventory units by storage zone.",
            "inventory.csv",
            b"Zone,Units\nA,40\nB,67\n",
        ),
    ],
)
def test_three_unrelated_domains_use_one_protected_generation_path(
    client: TestClient, business_request: str, filename: str, content: bytes
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(client, session, business_request, filename, content)
    command = str(uuid4())
    response = client.post(
        f"/api/cases/{case['id']}/generation",
        json={"confirmed_contract_id": contract["id"], "command_key": command},
        headers=csrf(session),
    )
    assert response.status_code == 201, response.text
    attempt = response.json()["attempt"]
    assert attempt["status"] == "SUCCEEDED"
    assert attempt["validation"]["status"] == "PASS"
    assert attempt["provenance"]["mode"] == "LOCAL_DETERMINISTIC_NO_MODEL_CALL"
    download = client.get(f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact")
    assert download.status_code == 200
    assert hashlib.sha256(download.content).hexdigest() == attempt["artifact"]["content_digest"]
    assert download.headers["x-content-sha256"] == attempt["artifact"]["content_digest"]
    assert download.headers["cache-control"] == "private, no-store"
    with zipfile.ZipFile(BytesIO(download.content)) as archive:
        assert any(name.endswith(".pbip") for name in archive.namelist())
        assert "ReportDesign.json" in archive.namelist()


def test_generation_is_idempotent_preserves_history_and_rejects_stale_confirmation(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Show total hours by team.",
        "work.csv",
        b"Team,Hours\nAlpha,12\nBeta,18\n",
    )
    command = str(uuid4())
    first = client.post(
        f"/api/cases/{case['id']}/generation",
        json={"confirmed_contract_id": contract["id"], "command_key": command},
        headers=csrf(session),
    ).json()["attempt"]
    repeated = client.post(
        f"/api/cases/{case['id']}/generation",
        json={"confirmed_contract_id": contract["id"], "command_key": command},
        headers=csrf(session),
    )
    assert repeated.status_code == 200
    assert repeated.json()["attempt"]["id"] == first["id"]
    conflicting_command = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "command_key": command,
            "mode": "REGENERATE",
        },
        headers=csrf(session),
    )
    assert conflicting_command.status_code == 409
    assert conflicting_command.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    regenerated = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "command_key": str(uuid4()),
            "mode": "REGENERATE",
        },
        headers=csrf(session),
    ).json()["attempt"]
    assert regenerated["id"] != first["id"]
    assert regenerated["supersedes_attempt_id"] == first["id"]
    history = client.get(f"/api/cases/{case['id']}/generation").json()["items"]
    assert [item["id"] for item in history] == [regenerated["id"], first["id"]]
    updated = client.put(
        f"/api/cases/{case['id']}",
        json={"request_text": "Show a materially changed report.", "expected_version": 1},
        headers=csrf(session),
    )
    assert updated.status_code == 200
    stale = client.post(
        f"/api/cases/{case['id']}/generation",
        json={"confirmed_contract_id": contract["id"], "command_key": str(uuid4())},
        headers=csrf(session),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_VERSION"
    replacement_evidence = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={
            "filename": "revised-work.csv",
            "expected_context_version": updated.json()["case"]["semantic_context_version"],
        },
        content=b"Team,Hours\nGamma,24\nDelta,16\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    replacement_contract = confirm_current_case(client, session, case["id"], replacement_evidence)
    changed = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": replacement_contract["id"],
            "command_key": str(uuid4()),
            "mode": "REGENERATE",
        },
        headers=csrf(session),
    )
    assert changed.status_code == 201
    assert changed.json()["attempt"]["supersedes_attempt_id"] == regenerated["id"]


def test_pipeline_failure_is_durable_and_never_downloadable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Show total cost by category.",
        "costs.csv",
        b"Category,Cost\nA,10\nB,20\n",
    )

    def fail(_self: GenerationBridge, _payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("synthetic bridge failure")

    monkeypatch.setattr(GenerationBridge, "generate", fail)
    response = client.post(
        f"/api/cases/{case['id']}/generation",
        json={"confirmed_contract_id": contract["id"], "command_key": str(uuid4())},
        headers=csrf(session),
    )
    assert response.status_code == 201
    attempt = response.json()["attempt"]
    assert attempt["status"] == "FAILED"
    assert attempt["artifact"] is None
    assert (
        client.get(f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact").status_code
        == 404
    )


def test_equivalent_concurrent_commands_collapse_to_one_durable_attempt(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Compare completed work by department.",
        "work.csv",
        b"Department,Completed\nOperations,14\nFinance,9\n",
    )
    command = str(uuid4())
    barrier = Barrier(2)
    candidates = [TestClient(create_app(settings=settings, database=database)) for _ in range(2)]
    for candidate in candidates:
        candidate.cookies.update(client.cookies)

    def build(candidate: TestClient) -> tuple[int, str]:
        barrier.wait()
        response = candidate.post(
            f"/api/cases/{case['id']}/generation",
            json={"confirmed_contract_id": contract["id"], "command_key": command},
            headers=csrf(session),
        )
        return response.status_code, response.json()["attempt"]["id"]

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(build, candidates))
    finally:
        for candidate in candidates:
            candidate.close()

    assert sorted(status for status, _identifier in results) == [200, 201]
    assert len({identifier for _status, identifier in results}) == 1
    history = client.get(f"/api/cases/{case['id']}/generation").json()["items"]
    assert len(history) == 1
    assert history[0]["status"] == "SUCCEEDED"


def test_cancel_fences_late_pipeline_result_and_retry_creates_new_attempt(
    client: TestClient,
    settings: Settings,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Show processed claims by queue.",
        "claims.csv",
        b"Queue,Processed\nStandard,21\nPriority,8\n",
    )
    entered, release = Event(), Event()
    original = GenerationBridge.generate

    def wait_then_generate(
        bridge: GenerationBridge, payload: dict[str, object]
    ) -> dict[str, object]:
        entered.set()
        assert release.wait(timeout=10)
        return original(bridge, payload)

    monkeypatch.setattr(GenerationBridge, "generate", wait_then_generate)
    candidate = TestClient(create_app(settings=settings, database=database))
    candidate.cookies.update(client.cookies)

    def build():
        return candidate.post(
            f"/api/cases/{case['id']}/generation",
            json={
                "confirmed_contract_id": contract["id"],
                "command_key": str(uuid4()),
            },
            headers=csrf(session),
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(build)
            assert entered.wait(timeout=10)
            running = client.get(f"/api/cases/{case['id']}/generation").json()["items"][0]
            cancelled = client.post(
                f"/api/cases/{case['id']}/generation/{running['id']}/cancel",
                headers=csrf(session),
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["attempt"]["status"] == "CANCELLED"
            release.set()
            completed = future.result(timeout=15)
    finally:
        release.set()
        candidate.close()

    assert completed.status_code == 201
    assert completed.json()["attempt"]["status"] == "CANCELLED"
    assert completed.json()["attempt"]["artifact"] is None
    monkeypatch.setattr(GenerationBridge, "generate", original)
    retry = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "command_key": str(uuid4()),
            "mode": "RETRY",
            "source_attempt_id": completed.json()["attempt"]["id"],
        },
        headers=csrf(session),
    )
    assert retry.status_code == 201
    assert retry.json()["attempt"]["status"] == "SUCCEEDED"
    assert retry.json()["attempt"]["retry_of_attempt_id"] == completed.json()["attempt"]["id"]


def test_history_and_artifact_survive_restart_but_remain_company_private(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Summarise approved applications by region.",
        "applications.csv",
        b"Region,Approved\nEast,17\nWest,22\n",
    )
    attempt = client.post(
        f"/api/cases/{case['id']}/generation",
        json={"confirmed_contract_id": contract["id"], "command_key": str(uuid4())},
        headers=csrf(session),
    ).json()["attempt"]

    restarted_database = Database(settings.database_url)
    history_only_settings = settings.model_copy(
        update={"generation_bridge_path": Path("/nonexistent/generation-bridge.mjs")}
    )
    with TestClient(
        create_app(settings=history_only_settings, database=restarted_database)
    ) as restarted:
        restarted.cookies.update(client.cookies)
        history = restarted.get(f"/api/cases/{case['id']}/generation")
        assert history.status_code == 200
        assert history.json()["items"][0]["id"] == attempt["id"]
        artifact = restarted.get(f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact")
        assert artifact.status_code == 200
        assert hashlib.sha256(artifact.content).hexdigest() == attempt["artifact"]["content_digest"]
        unavailable = restarted.post(
            f"/api/cases/{case['id']}/generation",
            json={
                "confirmed_contract_id": contract["id"],
                "command_key": str(uuid4()),
                "mode": "REGENERATE",
            },
            headers=csrf(session),
        )
        assert unavailable.status_code == 422
        assert unavailable.json()["error"]["code"] == "GENERATION_FAILED"
    restarted_database.engine.dispose()

    foreign = TestClient(create_app(settings=settings, database=database))
    try:
        sign_in(foreign, "foreign")
        assert foreign.get(f"/api/cases/{case['id']}/generation").status_code == 404
        assert (
            foreign.get(f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact").status_code
            == 404
        )
    finally:
        foreign.close()


def test_artifact_integrity_failure_is_fail_closed(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Show resolved tickets by service.",
        "tickets.csv",
        b"Service,Resolved\nNetwork,11\nDevices,7\n",
    )
    attempt = client.post(
        f"/api/cases/{case['id']}/generation",
        json={"confirmed_contract_id": contract["id"], "command_key": str(uuid4())},
        headers=csrf(session),
    ).json()["attempt"]
    with database.session() as db:
        storage_key = db.scalar(
            text("SELECT storage_key FROM generated_artifacts WHERE id=:artifact_id"),
            {"artifact_id": attempt["artifact"]["id"]},
        )
    assert isinstance(storage_key, str)
    settings.artifact_root.joinpath(*storage_key.split("/")).write_bytes(b"tampered")
    response = client.get(f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ARTIFACT_NOT_FOUND"


def test_terminal_attempt_and_artifact_history_are_database_immutable(
    client: TestClient, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Compare dispatched orders by route.",
        "dispatch.csv",
        b"Route,Dispatched\nNorth,19\nSouth,23\n",
    )
    attempt = client.post(
        f"/api/cases/{case['id']}/generation",
        json={"confirmed_contract_id": contract["id"], "command_key": str(uuid4())},
        headers=csrf(session),
    ).json()["attempt"]
    with database.session() as db:
        with pytest.raises(DBAPIError, match="terminal generation attempt is immutable"):
            db.execute(
                text("UPDATE generation_attempts SET status='FAILED' WHERE id=:id"),
                {"id": attempt["id"]},
            )
        db.rollback()
        with pytest.raises(DBAPIError, match="generated artifact is immutable"):
            db.execute(
                text("UPDATE generated_artifacts SET filename='changed.zip' WHERE id=:id"),
                {"id": attempt["artifact"]["id"]},
            )
        db.rollback()


def test_generation_bridge_rejects_unsafe_executables_timeout_and_malformed_output(
    tmp_path: Path,
) -> None:
    node = Path(shutil.which("node") or "/nonexistent/node")
    valid = tmp_path / "bridge.mjs"
    valid.write_text(
        "process.stdout.write(JSON.stringify({ok:true,value:{files:{'../escape':'x'},"
        "validation:{status:'PASS'}}}))",
        encoding="utf-8",
    )
    symlink = tmp_path / "bridge-link.mjs"
    symlink.symlink_to(valid)
    with pytest.raises(ValueError, match="fixed regular file"):
        GenerationBridge(symlink, node_executable=node, timeout_seconds=1)

    bridge = GenerationBridge(valid, node_executable=node, timeout_seconds=1)
    marker = tmp_path / "must-not-exist"
    with pytest.raises(GenerationFailed):
        bridge.generate({"untrusted": f"$(touch {marker})"})
    assert not marker.exists()

    valid.write_text("setTimeout(()=>{}, 5000)", encoding="utf-8")
    with pytest.raises(GenerationFailed):
        bridge.generate({"bounded": True})
    with pytest.raises(GenerationFailed):
        GenerationBridge(valid, node_executable=node, timeout_seconds=1).generate(
            {"bounded": True}
        )

    oversized = tmp_path / "oversized.mjs"
    oversized.write_text("process.stdout.write('x'.repeat(20000001))", encoding="utf-8")
    with pytest.raises(GenerationFailed):
        GenerationBridge(oversized, node_executable=node, timeout_seconds=5).generate(
            {"binding": {}, "execution": {}}
        )

    mismatched = tmp_path / "mismatched.mjs"
    mismatched.write_text(
        "process.stdout.write(JSON.stringify({ok:true,value:{files:{'safe.txt':'x'},"
        "validation:{status:'PASS'},provenance:{binding:{caseId:'wrong'},"
        "execution:{inputDigest:'wrong'}}}}))",
        encoding="utf-8",
    )
    with pytest.raises(GenerationFailed):
        GenerationBridge(mismatched, node_executable=node, timeout_seconds=2).generate(
            {"binding": {"caseId": "expected"}, "execution": {"inputDigest": "expected"}}
        )


def test_authorization_revocation_waits_for_eligibility_commit(
    client: TestClient,
    settings: Settings,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Compare verified shipments by depot.",
        "shipments.csv",
        b"Depot,Verified\nNorth,13\nSouth,17\n",
    )
    entered, release = Event(), Event()
    original_write = LocalArtifactStore.write

    def blocked_write(self, company_id, case_id, attempt_id, content):
        entered.set()
        assert release.wait(timeout=10)
        return original_write(self, company_id, case_id, attempt_id, content)

    monkeypatch.setattr(LocalArtifactStore, "write", blocked_write)
    candidate = TestClient(create_app(settings=settings, database=database))
    candidate.cookies.update(client.cookies)

    def revoke() -> None:
        with database.session() as db:
            db.execute(
                text("UPDATE memberships SET active=false WHERE id=:id"),
                {"id": session["actor"]["membership_id"]},
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            build = executor.submit(
                candidate.post,
                f"/api/cases/{case['id']}/generation",
                json={
                    "confirmed_contract_id": contract["id"],
                    "command_key": str(uuid4()),
                },
                headers=csrf(session),
            )
            assert entered.wait(timeout=10)
            revocation = executor.submit(revoke)
            with pytest.raises(FutureTimeoutError):
                revocation.result(timeout=0.25)
            release.set()
            response = build.result(timeout=15)
            revocation.result(timeout=10)
    finally:
        release.set()
        candidate.close()
    assert response.json()["attempt"]["status"] == "SUCCEEDED"
    assert client.get(f"/api/cases/{case['id']}/generation").status_code in {401, 404}


def test_nonterminal_identity_and_cross_attempt_artifact_binding_are_rejected(
    client: TestClient,
    settings: Settings,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = sign_in(client, "member")
    first_case, first_contract = confirmed_case(
        client,
        session,
        "Show accepted invoices by ledger.",
        "invoices.csv",
        b"Ledger,Accepted\nA,8\nB,12\n",
    )
    first = client.post(
        f"/api/cases/{first_case['id']}/generation",
        json={"confirmed_contract_id": first_contract["id"], "command_key": str(uuid4())},
        headers=csrf(session),
    ).json()["attempt"]
    second_case, second_contract = confirmed_case(
        client,
        session,
        "Show reviewed invoices by ledger.",
        "reviewed.csv",
        b"Ledger,Reviewed\nA,9\nB,14\n",
    )
    entered, release = Event(), Event()
    original = GenerationBridge.generate

    def wait_then_generate(bridge: GenerationBridge, payload: dict[str, object]):
        entered.set()
        assert release.wait(timeout=10)
        return original(bridge, payload)

    monkeypatch.setattr(GenerationBridge, "generate", wait_then_generate)
    candidate = TestClient(create_app(settings=settings, database=database))
    candidate.cookies.update(client.cookies)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                candidate.post,
                f"/api/cases/{second_case['id']}/generation",
                json={
                    "confirmed_contract_id": second_contract["id"],
                    "command_key": str(uuid4()),
                },
                headers=csrf(session),
            )
            assert entered.wait(timeout=10)
            with database.session() as db:
                running_id = db.scalar(
                    text(
                        "SELECT id FROM generation_attempts "
                        "WHERE case_id=:case_id AND status='RUNNING'"
                    ),
                    {"case_id": second_case["id"]},
                )
                with pytest.raises(DBAPIError, match="generation identity is immutable"):
                    db.execute(
                        text(
                            "UPDATE generation_attempts SET "
                            "created_at=created_at + interval '1 second' "
                            "WHERE id=:id"
                        ),
                        {"id": running_id},
                    )
                db.rollback()
                with pytest.raises(DBAPIError):
                    db.execute(
                        text(
                            "UPDATE generation_attempts SET status='SUCCEEDED', "
                            "artifact_id=:artifact_id, validation_json='{}', completed_at=now() "
                            "WHERE id=:id"
                        ),
                        {"id": running_id, "artifact_id": first["artifact"]["id"]},
                    )
                db.rollback()
            release.set()
            response = future.result(timeout=15)
    finally:
        release.set()
        candidate.close()
    assert response.json()["attempt"]["status"] == "SUCCEEDED"


def test_revoked_membership_before_late_result_prevents_artifact_eligibility(
    client: TestClient,
    settings: Settings,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Compare completed deliveries by hub.",
        "deliveries.csv",
        b"Hub,Completed\nEast,15\nWest,19\n",
    )
    entered, release = Event(), Event()
    original = GenerationBridge.generate

    def wait_then_generate(
        bridge: GenerationBridge, payload: dict[str, object]
    ) -> dict[str, object]:
        entered.set()
        assert release.wait(timeout=10)
        return original(bridge, payload)

    monkeypatch.setattr(GenerationBridge, "generate", wait_then_generate)
    candidate = TestClient(create_app(settings=settings, database=database))
    candidate.cookies.update(client.cookies)
    prior_artifacts = set(settings.artifact_root.rglob("*.zip"))
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                candidate.post,
                f"/api/cases/{case['id']}/generation",
                json={
                    "confirmed_contract_id": contract["id"],
                    "command_key": str(uuid4()),
                },
                headers=csrf(session),
            )
            assert entered.wait(timeout=10)
            with database.session() as db:
                db.execute(
                    text("UPDATE memberships SET active=false WHERE id=:id"),
                    {"id": session["actor"]["membership_id"]},
                )
            release.set()
            response = future.result(timeout=15)
    finally:
        release.set()
        candidate.close()
    attempt = response.json()["attempt"]
    assert attempt["status"] == "FAILED"
    assert attempt["artifact"] is None
    assert set(settings.artifact_root.rglob("*.zip")) == prior_artifacts


def test_database_failure_after_artifact_write_removes_uncommitted_bytes(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Compare reconciled balances by account group.",
        "balances.csv",
        b"AccountGroup,Balance\nCurrent,31\nReserve,12\n",
    )

    def reject_artifact(*_args, **_kwargs):
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr(ApplicationSession, "add_generated_artifact", reject_artifact)
    prior_artifacts = set(settings.artifact_root.rglob("*.zip"))
    response = client.post(
        f"/api/cases/{case['id']}/generation",
        json={"confirmed_contract_id": contract["id"], "command_key": str(uuid4())},
        headers=csrf(session),
    )
    assert response.status_code == 201
    assert response.json()["attempt"]["status"] == "FAILED"
    assert response.json()["attempt"]["artifact"] is None
    assert set(settings.artifact_root.rglob("*.zip")) == prior_artifacts
