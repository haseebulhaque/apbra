from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import cast
from uuid import uuid4

import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient

from apbra_api.api import create_app
from apbra_api.config import Settings
from apbra_api.persistence import Database


def create_case(client: TestClient, session: dict[str, object]) -> dict[str, object]:
    response = client.post(
        "/api/cases",
        json={"request_text": "Create a report of total amount by division."},
        headers={**csrf(session), "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201
    return response.json()["case"]


def session_clone(settings: Settings, database: Database, source: TestClient) -> TestClient:
    clone = TestClient(create_app(settings=settings, database=database))
    clone.cookies.update(source.cookies)
    return clone


def prepare_ambiguous_case(
    client: TestClient, session: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    created = client.post(
        "/api/cases",
        json={"request_text": "Help managers understand the supplied evidence."},
        headers={**csrf(session), "Idempotency-Key": str(uuid4())},
    ).json()["case"]
    uploaded = client.post(
        f"/api/cases/{created['id']}/evidence",
        params={"filename": "observations.csv", "expected_context_version": 1},
        content=b"Campus,Visits\nNorth,12\nSouth,9\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    prepared = client.post(
        f"/api/cases/{created['id']}/interpretations",
        json={"expected_context_version": uploaded["semantic_context_version"]},
        headers=csrf(session),
    )
    assert prepared.status_code == 200, prepared.text
    return cast(dict[str, object], created), cast(
        dict[str, object], prepared.json()["interpretation"]
    )


def test_durable_conversation_evidence_and_exact_acceptance(client: TestClient) -> None:
    session = sign_in(client, "owner")
    case = create_case(client, session)
    case_id = case["id"]
    event = client.post(
        f"/api/cases/{case_id}/conversation",
        json={
            "kind": "USER_MESSAGE",
            "payload": {"text": "Create a report of total amount by division."},
            "expected_context_version": 1,
            "command_key": "message-command-1",
        },
        headers=csrf(session),
    )
    assert event.status_code == 200
    assert event.json()["event"]["semantic_context_version"] == 2

    evidence = client.post(
        f"/api/cases/{case_id}/evidence",
        params={"filename": "Ledger.csv", "expected_context_version": 2},
        content=b"Amount,Division\n12.5,North\n7,South\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert evidence.status_code == 200
    evidence_json = evidence.json()["evidence"]
    assert evidence_json["semantic_context_version"] == 3

    interpretation = client.post(
        f"/api/cases/{case_id}/interpretations",
        json={
            "expected_context_version": 3,
        },
        headers=csrf(session),
    )
    assert interpretation.status_code == 200, interpretation.text
    interpretation_json = interpretation.json()["interpretation"]
    assert interpretation_json["state"] == "READY_FOR_CONFIRMATION"

    confirmed = client.post(
        f"/api/cases/{case_id}/confirm",
        json={
            "interpretation_id": interpretation_json["id"],
            "expected_context_version": 3,
        },
        headers=csrf(session),
    )
    assert confirmed.status_code == 200, confirmed.text
    contract = confirmed.json()["confirmed_contract"]
    assert contract["schema_version"] == 2
    assert contract["contract"]["objective"] == "Create a report of total amount by division."

    repeated = client.post(
        f"/api/cases/{case_id}/confirm",
        json={
            "interpretation_id": interpretation_json["id"],
            "expected_context_version": 3,
        },
        headers=csrf(session),
    )
    assert repeated.status_code == 200
    assert repeated.json()["confirmed_contract"]["id"] == contract["id"]

    transcript = client.get(f"/api/cases/{case_id}/conversation")
    assert transcript.status_code == 200
    assert transcript.json()["items"][0]["payload"]["text"].startswith("Create")


def test_confirmed_meaning_survives_api_restart(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "owner")
    case = create_case(client, session)
    case_id = case["id"]
    uploaded = client.post(
        f"/api/cases/{case_id}/evidence",
        params={"filename": "ledger.csv", "expected_context_version": 1},
        content=b"Amount,Division\n12,North\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    interpretation = client.post(
        f"/api/cases/{case_id}/interpretations",
        json={"expected_context_version": uploaded["semantic_context_version"]},
        headers=csrf(session),
    ).json()["interpretation"]
    confirmed = client.post(
        f"/api/cases/{case_id}/confirm",
        json={
            "interpretation_id": interpretation["id"],
            "expected_context_version": uploaded["semantic_context_version"],
        },
        headers=csrf(session),
    ).json()["confirmed_contract"]
    with TestClient(create_app(settings=settings, database=database)) as restarted:
        restarted.cookies.update(client.cookies)
        state = restarted.get(f"/api/cases/{case_id}/acceptance")
    assert state.status_code == 200, state.text
    assert state.json()["confirmed_contract"]["id"] == confirmed["id"]
    assert state.json()["confirmed_contract"]["schema_version"] == 2


def test_changed_request_invalidates_ready_interpretation(client: TestClient) -> None:
    session = sign_in(client, "owner")
    case = create_case(client, session)
    case_id = case["id"]
    evidence = client.post(
        f"/api/cases/{case_id}/evidence",
        params={"filename": "Ledger.csv", "expected_context_version": 1},
        content=b"Amount,Division\n12.5,North\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    assert evidence["id"]
    interpretation = client.post(
        f"/api/cases/{case_id}/interpretations",
        json={
            "expected_context_version": 2,
        },
        headers=csrf(session),
    ).json()["interpretation"]
    updated = client.put(
        f"/api/cases/{case_id}",
        json={"request_text": "Create a different report.", "expected_version": 1},
        headers=csrf(session),
    )
    assert updated.status_code == 200
    rejected = client.post(
        f"/api/cases/{case_id}/confirm",
        json={"interpretation_id": interpretation["id"], "expected_context_version": 2},
        headers=csrf(session),
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "STALE_VERSION"


def test_client_cannot_supply_semantic_authority(client: TestClient) -> None:
    session = sign_in(client, "owner")
    case = create_case(client, session)
    response = client.post(
        f"/api/cases/{case['id']}/interpretations",
        json={
            "session": {"state": "CONFIRMED"},
            "evidence_id": str(uuid4()),
            "expected_context_version": 1,
            "command_key": "member-message-command-1",
        },
        headers=csrf(session),
    )
    assert response.status_code == 422


def test_invited_member_retains_access_after_advancing_semantic_context(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    case = create_case(client, session)
    case_id = case["id"]
    appended = client.post(
        f"/api/cases/{case_id}/conversation",
        json={
            "kind": "USER_MESSAGE",
            "payload": {"text": "Use monthly periods."},
            "expected_context_version": 1,
            "command_key": "member-message-command-1",
        },
        headers=csrf(session),
    )
    assert appended.status_code == 200, appended.text
    transcript = client.get(f"/api/cases/{case_id}/conversation")
    assert transcript.status_code == 200, transcript.text
    assert transcript.json()["items"][0]["payload"] == {"text": "Use monthly periods."}


def test_message_retry_is_idempotent_and_conflicting_payload_is_rejected(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    case = create_case(client, session)
    case_id = case["id"]
    payload = {
        "kind": "USER_MESSAGE",
        "payload": {"text": "Retain the submitted context."},
        "expected_context_version": 1,
        "command_key": "stable-message-command",
    }
    first = client.post(f"/api/cases/{case_id}/conversation", json=payload, headers=csrf(session))
    repeated = client.post(
        f"/api/cases/{case_id}/conversation", json=payload, headers=csrf(session)
    )
    assert first.status_code == repeated.status_code == 200
    assert first.json()["event"]["id"] == repeated.json()["event"]["id"]
    assert repeated.json()["event"]["semantic_context_version"] == 2
    conflicting = client.post(
        f"/api/cases/{case_id}/conversation",
        json={**payload, "payload": {"text": "Different unseen content."}},
        headers=csrf(session),
    )
    assert conflicting.status_code == 409
    assert conflicting.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_material_clarification_and_supported_choice_are_durable(client: TestClient) -> None:
    session = sign_in(client, "member")
    case = client.post(
        "/api/cases",
        json={"request_text": "Help managers understand the supplied evidence."},
        headers={**csrf(session), "Idempotency-Key": str(uuid4())},
    ).json()["case"]
    case_id = case["id"]
    uploaded = client.post(
        f"/api/cases/{case_id}/evidence",
        params={"filename": "observations.csv", "expected_context_version": 1},
        content=b"Campus,Visits\nNorth,12\nSouth,9\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    first = client.post(
        f"/api/cases/{case_id}/interpretations",
        json={"expected_context_version": uploaded["semantic_context_version"]},
        headers=csrf(session),
    )
    assert first.status_code == 200, first.text
    interpretation = first.json()["interpretation"]
    assert interpretation["state"] == "NEEDS_CLARIFICATION"
    question = interpretation["questions"][0]
    option = question["suggestions"][0]
    answer = client.post(
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
            "expected_context_version": uploaded["semantic_context_version"],
            "command_key": "accepted-supported-choice",
        },
        headers=csrf(session),
    )
    assert answer.status_code == 200, answer.text
    next_context = answer.json()["event"]["semantic_context_version"]
    ready = client.post(
        f"/api/cases/{case_id}/interpretations",
        json={"expected_context_version": next_context},
        headers=csrf(session),
    )
    assert ready.status_code == 200, ready.text
    assert ready.json()["interpretation"]["state"] == "READY_FOR_CONFIRMATION"
    transcript = client.get(f"/api/cases/{case_id}/conversation").json()["items"]
    assert [item["kind"] for item in transcript] == ["RAW_ANSWER", "ALTERNATIVE_ACCEPTED"]
    assert transcript[0]["payload"]["rawAnswer"] == option["label"]


def test_raw_answer_retries_are_payload_bound_and_do_not_duplicate_events(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    for index, decision in enumerate(("ACCEPT", "FREE_TEXT", "DECLINE")):
        case, interpretation = prepare_ambiguous_case(client, session)
        question = cast(list[dict[str, object]], interpretation["questions"])[0]
        option = cast(list[dict[str, str]], question["suggestions"])[0]
        payload = {
            "questionId": question["id"],
            "interpretationId": interpretation["id"],
            "rawAnswer": option["label"] if decision == "ACCEPT" else "Visits by Campus",
            "suggestionId": option["id"] if decision == "ACCEPT" else "",
            "decision": decision,
        }
        command_key = f"answer-retry-{index}"
        request = {
            "kind": "RAW_ANSWER",
            "payload": payload,
            "expected_context_version": interpretation["context_version"],
            "command_key": command_key,
        }
        first = client.post(
            f"/api/cases/{case['id']}/conversation", json=request, headers=csrf(session)
        )
        repeated = client.post(
            f"/api/cases/{case['id']}/conversation", json=request, headers=csrf(session)
        )
        assert first.status_code == repeated.status_code == 200
        assert first.json()["event"]["id"] == repeated.json()["event"]["id"]
        changed = {
            **request,
            "payload": {**payload, "rawAnswer": f"{payload['rawAnswer']} changed"},
        }
        conflict = client.post(
            f"/api/cases/{case['id']}/conversation", json=changed, headers=csrf(session)
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        transcript = client.get(f"/api/cases/{case['id']}/conversation").json()["items"]
        assert sum(item["kind"] == "RAW_ANSWER" for item in transcript) == 1


def test_old_same_request_interpretation_cannot_answer_after_context_changes(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    case, old = prepare_ambiguous_case(client, session)
    old_question = cast(list[dict[str, object]], old["questions"])[0]
    old_option = cast(list[dict[str, str]], old_question["suggestions"])[0]
    message = client.post(
        f"/api/cases/{case['id']}/conversation",
        json={
            "kind": "USER_MESSAGE",
            "payload": {"text": "Please include the newest qualified context."},
            "expected_context_version": old["context_version"],
            "command_key": "same-request-context-change",
        },
        headers=csrf(session),
    ).json()["event"]
    current = client.post(
        f"/api/cases/{case['id']}/interpretations",
        json={"expected_context_version": message["semantic_context_version"]},
        headers=csrf(session),
    ).json()["interpretation"]
    assert current["id"] != old["id"]
    assert current["questions"][0]["id"] != old_question["id"]
    stale = client.post(
        f"/api/cases/{case['id']}/conversation",
        json={
            "kind": "RAW_ANSWER",
            "payload": {
                "questionId": old_question["id"],
                "interpretationId": old["id"],
                "rawAnswer": old_option["label"],
                "suggestionId": old_option["id"],
                "decision": "ACCEPT",
            },
            "expected_context_version": current["context_version"],
            "command_key": "stale-same-request-answer",
        },
        headers=csrf(session),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_VERSION"


def test_missing_or_tampered_evidence_cannot_authorize_interpretation(
    client: TestClient, settings: Settings
) -> None:
    session = sign_in(client, "member")
    for mode in ("missing", "tampered"):
        case = create_case(client, session)
        content = f"Amount,Division\n{12 if mode == 'missing' else 14},North\n".encode()
        uploaded = client.post(
            f"/api/cases/{case['id']}/evidence",
            params={"filename": f"{mode}.csv", "expected_context_version": 1},
            content=content,
            headers={**csrf(session), "Content-Type": "application/octet-stream"},
        ).json()["evidence"]
        object_path = next(
            path
            for path in settings.evidence_root.rglob("*.bin")
            if path.parent.name == case["id"]
            and hashlib.sha256(path.read_bytes()).hexdigest() == uploaded["content_digest"]
        )
        if mode == "missing":
            object_path.unlink()
        else:
            object_path.write_bytes(b"Amount,Division\n999,Changed\n")
        rejected = client.post(
            f"/api/cases/{case['id']}/interpretations",
            json={"expected_context_version": uploaded["semantic_context_version"]},
            headers=csrf(session),
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "SEMANTIC_VALIDATION_FAILED"


def test_prepared_interpretation_and_confirmation_recheck_evidence_integrity(
    client: TestClient, settings: Settings
) -> None:
    session = sign_in(client, "member")
    case = create_case(client, session)
    content = b"Amount,Division\n12,North\n"
    uploaded = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "qualified.csv", "expected_context_version": 1},
        content=content,
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    interpretation = client.post(
        f"/api/cases/{case['id']}/interpretations",
        json={"expected_context_version": uploaded["semantic_context_version"]},
        headers=csrf(session),
    ).json()["interpretation"]
    assert interpretation["state"] == "READY_FOR_CONFIRMATION"
    object_path = next(
        path
        for path in settings.evidence_root.rglob("*.bin")
        if path.parent.name == case["id"]
        and hashlib.sha256(path.read_bytes()).hexdigest() == uploaded["content_digest"]
    )
    object_path.write_bytes(b"Amount,Division\n999,Changed\n")
    repeated_prepare = client.post(
        f"/api/cases/{case['id']}/interpretations",
        json={"expected_context_version": uploaded["semantic_context_version"]},
        headers=csrf(session),
    )
    assert repeated_prepare.status_code == 422
    confirmation = client.post(
        f"/api/cases/{case['id']}/confirm",
        json={
            "interpretation_id": interpretation["id"],
            "expected_context_version": uploaded["semantic_context_version"],
        },
        headers=csrf(session),
    )
    assert confirmation.status_code == 422
    assert confirmation.json()["error"]["code"] == "SEMANTIC_VALIDATION_FAILED"


@pytest.mark.parametrize("damage", ["missing", "tampered"])
def test_reload_hides_unavailable_evidence_and_exact_reupload_restores_it(
    client: TestClient, settings: Settings, damage: str
) -> None:
    session = sign_in(client, "member")
    case = create_case(client, session)
    content = b"Amount,Division\n12,North\n"
    uploaded = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "recoverable.csv", "expected_context_version": 1},
        content=content,
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    interpretation = client.post(
        f"/api/cases/{case['id']}/interpretations",
        json={"expected_context_version": uploaded["semantic_context_version"]},
        headers=csrf(session),
    ).json()["interpretation"]
    confirmed = client.post(
        f"/api/cases/{case['id']}/confirm",
        json={
            "interpretation_id": interpretation["id"],
            "expected_context_version": uploaded["semantic_context_version"],
        },
        headers=csrf(session),
    )
    assert confirmed.status_code == 200
    object_path = next(
        path
        for path in settings.evidence_root.rglob("*.bin")
        if path.parent.name == case["id"]
        and hashlib.sha256(path.read_bytes()).hexdigest() == uploaded["content_digest"]
    )
    if damage == "missing":
        object_path.unlink()
    else:
        object_path.write_bytes(b"Amount,Division\n999,Changed\n")

    listed = client.get(f"/api/cases/{case['id']}/evidence")
    assert listed.status_code == 200
    assert listed.json()["items"] == []
    stale_state = client.get(f"/api/cases/{case['id']}/acceptance").json()
    assert stale_state["interpretation"]["current"] is False
    assert stale_state["confirmed_contract"]["current"] is False

    restored = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={
            "filename": "recoverable.csv",
            "expected_context_version": uploaded["semantic_context_version"],
        },
        content=content,
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["evidence"]["id"] == uploaded["id"]
    assert len(client.get(f"/api/cases/{case['id']}/evidence").json()["items"]) == 1
    recovered_state = client.get(f"/api/cases/{case['id']}/acceptance").json()
    assert recovered_state["interpretation"]["current"] is True
    assert recovered_state["confirmed_contract"]["current"] is True


def test_accepted_choice_is_normalized_and_decline_cannot_authorize_meaning(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    case, interpretation = prepare_ambiguous_case(client, session)
    question = cast(list[dict[str, object]], interpretation["questions"])[0]
    option = cast(list[dict[str, str]], question["suggestions"])[0]
    accepted = client.post(
        f"/api/cases/{case['id']}/conversation",
        json={
            "kind": "RAW_ANSWER",
            "payload": {
                "questionId": question["id"],
                "interpretationId": interpretation["id"],
                "rawAnswer": "Summarise an unseen field and compare it by another choice.",
                "suggestionId": option["id"],
                "decision": "ACCEPT",
            },
            "expected_context_version": interpretation["context_version"],
            "command_key": "normalize-exact-choice",
        },
        headers=csrf(session),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["event"]["payload"]["rawAnswer"] == option["label"]
    assert accepted.json()["event"]["payload"]["submittedText"].startswith("Summarise an unseen")
    ready = client.post(
        f"/api/cases/{case['id']}/interpretations",
        json={"expected_context_version": accepted.json()["event"]["semantic_context_version"]},
        headers=csrf(session),
    ).json()["interpretation"]
    assert ready["state"] == "READY_FOR_CONFIRMATION"
    assert any("Visits" in item for item in ready["confirmation_summary"]["kpiDefinitions"])

    declined_case, declined_interpretation = prepare_ambiguous_case(client, session)
    declined_question = cast(
        list[dict[str, object]], declined_interpretation["questions"]
    )[0]
    declined = client.post(
        f"/api/cases/{declined_case['id']}/conversation",
        json={
            "kind": "RAW_ANSWER",
            "payload": {
                "questionId": declined_question["id"],
                "interpretationId": declined_interpretation["id"],
                "rawAnswer": "Visits Campus",
                "suggestionId": "",
                "decision": "DECLINE",
            },
            "expected_context_version": declined_interpretation["context_version"],
            "command_key": "decline-does-not-authorize",
        },
        headers=csrf(session),
    )
    assert declined.status_code == 200, declined.text
    still_ambiguous = client.post(
        f"/api/cases/{declined_case['id']}/interpretations",
        json={"expected_context_version": declined.json()["event"]["semantic_context_version"]},
        headers=csrf(session),
    ).json()["interpretation"]
    assert still_ambiguous["state"] == "NEEDS_CLARIFICATION"


def test_old_clarification_answer_cannot_authorize_a_new_request_version(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    case, interpretation = prepare_ambiguous_case(client, session)
    old_question = cast(list[dict[str, object]], interpretation["questions"])[0]
    option = cast(list[dict[str, str]], old_question["suggestions"])[0]
    accepted = client.post(
        f"/api/cases/{case['id']}/conversation",
        json={
            "kind": "RAW_ANSWER",
            "payload": {
                "questionId": old_question["id"],
                "interpretationId": interpretation["id"],
                "rawAnswer": option["label"],
                "suggestionId": option["id"],
                "decision": "ACCEPT",
            },
            "expected_context_version": interpretation["context_version"],
            "command_key": "old-request-choice",
        },
        headers=csrf(session),
    ).json()["event"]
    updated = client.put(
        f"/api/cases/{case['id']}",
        json={
            "request_text": "Help managers understand the revised qualified evidence.",
            "expected_version": 1,
        },
        headers=csrf(session),
    ).json()["case"]
    uploaded = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={
            "filename": "revised.csv",
            "expected_context_version": updated["semantic_context_version"],
        },
        content=b"Clinic,WaitMinutes\nEast,14\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    replacement = client.post(
        f"/api/cases/{case['id']}/interpretations",
        json={"expected_context_version": uploaded["semantic_context_version"]},
        headers=csrf(session),
    ).json()["interpretation"]
    assert replacement["state"] == "NEEDS_CLARIFICATION"
    replacement_question = replacement["questions"][0]
    assert replacement_question["id"] != old_question["id"]
    stale_answer = client.post(
        f"/api/cases/{case['id']}/conversation",
        json={
            "kind": "RAW_ANSWER",
            "payload": {
                "questionId": old_question["id"],
                "interpretationId": interpretation["id"],
                "rawAnswer": option["label"],
                "suggestionId": option["id"],
                "decision": "ACCEPT",
            },
            "expected_context_version": replacement["context_version"],
            "command_key": "stale-question-choice",
        },
        headers=csrf(session),
    )
    assert accepted["semantic_context_version"] < replacement["context_version"]
    assert stale_answer.status_code == 409


def test_interpretation_preparation_is_sequentially_and_concurrently_idempotent(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")
    case = create_case(client, session)
    uploaded = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "ledger.csv", "expected_context_version": 1},
        content=b"Amount,Division\n12,North\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    payload = {"expected_context_version": uploaded["semantic_context_version"]}
    first = client.post(
        f"/api/cases/{case['id']}/interpretations", json=payload, headers=csrf(session)
    )
    repeated = client.post(
        f"/api/cases/{case['id']}/interpretations", json=payload, headers=csrf(session)
    )
    assert first.status_code == repeated.status_code == 200
    assert first.json()["interpretation"]["id"] == repeated.json()["interpretation"]["id"]

    second_case = create_case(client, session)
    second_upload = client.post(
        f"/api/cases/{second_case['id']}/evidence",
        params={"filename": "ledger.csv", "expected_context_version": 1},
        content=b"Amount,Division\n12,North\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    barrier = Barrier(2)
    clients = [session_clone(settings, database, client) for _ in range(2)]

    def prepare(candidate: TestClient) -> tuple[int, str]:
        barrier.wait()
        response = candidate.post(
            f"/api/cases/{second_case['id']}/interpretations",
            json={"expected_context_version": second_upload["semantic_context_version"]},
            headers=csrf(session),
        )
        return response.status_code, str(response.json().get("interpretation", {}).get("id"))

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(prepare, clients))
    finally:
        for candidate in clients:
            candidate.close()
    assert [status for status, _ in results] == [200, 200]
    assert len({identifier for _, identifier in results}) == 1


def test_concurrent_conversation_commands_are_idempotent_or_conflict(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")

    def execute_pair(
        case_id: str, payloads: tuple[dict[str, str], dict[str, str]], command_key: str
    ) -> list[tuple[int, str, str]]:
        barrier = Barrier(2)
        clients = [session_clone(settings, database, client) for _ in range(2)]

        def append(candidate_payload: tuple[TestClient, dict[str, str]]) -> tuple[int, str, str]:
            candidate, payload = candidate_payload
            barrier.wait()
            response = candidate.post(
                f"/api/cases/{case_id}/conversation",
                json={
                    "kind": "USER_MESSAGE",
                    "payload": payload,
                    "expected_context_version": 1,
                    "command_key": command_key,
                },
                headers=csrf(session),
            )
            body = response.json()
            return (
                response.status_code,
                str(body.get("event", {}).get("id", "")),
                str(body.get("error", {}).get("code", "")),
            )

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                return list(executor.map(append, zip(clients, payloads, strict=True)))
        finally:
            for candidate in clients:
                candidate.close()

    identical_case = create_case(client, session)
    identical = execute_pair(
        str(identical_case["id"]),
        ({"text": "Same durable command."}, {"text": "Same durable command."}),
        "concurrent-identical-message",
    )
    assert [status for status, _identifier, _code in identical] == [200, 200]
    assert len({identifier for _status, identifier, _code in identical}) == 1
    identical_events = client.get(
        f"/api/cases/{identical_case['id']}/conversation"
    ).json()["items"]
    assert len(identical_events) == 1

    conflicting_case = create_case(client, session)
    conflicting = execute_pair(
        str(conflicting_case["id"]),
        ({"text": "First payload."}, {"text": "Different payload."}),
        "concurrent-conflicting-message",
    )
    assert sorted(status for status, _identifier, _code in conflicting) == [200, 409]
    assert "IDEMPOTENCY_CONFLICT" in {code for _status, _identifier, code in conflicting}
    conflicting_events = client.get(
        f"/api/cases/{conflicting_case['id']}/conversation"
    ).json()["items"]
    assert len(conflicting_events) == 1


def test_evidence_duplicate_is_scoped_to_the_current_request_version(client: TestClient) -> None:
    session = sign_in(client, "member")
    case = create_case(client, session)
    case_id = case["id"]
    content = b"Division,Amount\nNorth,12\n"
    first = client.post(
        f"/api/cases/{case_id}/evidence",
        params={"filename": "observations.csv", "expected_context_version": 1},
        content=content,
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    repeated = client.post(
        f"/api/cases/{case_id}/evidence",
        params={"filename": "renamed.csv", "expected_context_version": 2},
        content=content,
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    assert repeated["id"] == first["id"]
    assert repeated["semantic_context_version"] == 2
    updated = client.put(
        f"/api/cases/{case_id}",
        json={
            "request_text": "Create a revised report of Amount by Division.",
            "expected_version": 1,
        },
        headers=csrf(session),
    ).json()["case"]
    current = client.post(
        f"/api/cases/{case_id}/evidence",
        params={
            "filename": "observations.csv",
            "expected_context_version": updated["semantic_context_version"],
        },
        content=content,
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    assert current["id"] != first["id"]
    assert current["request_version_id"] == updated["current_request_version_id"]


def test_new_case_context_endpoints_do_not_reveal_an_ungranted_private_case(
    client: TestClient,
) -> None:
    owner = sign_in(client, "owner")
    case = create_case(client, owner)
    sign_in(client, "member")
    for method, path, kwargs in [
        ("get", f"/api/cases/{case['id']}/conversation", {}),
        ("get", f"/api/cases/{case['id']}/evidence", {}),
        ("get", f"/api/cases/{case['id']}/acceptance", {}),
    ]:
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_answer_cannot_invent_or_replace_a_server_issued_question(client: TestClient) -> None:
    session = sign_in(client, "member")
    case = create_case(client, session)
    response = client.post(
        f"/api/cases/{case['id']}/conversation",
        json={
            "kind": "RAW_ANSWER",
            "payload": {
                "questionId": "client-invented-question",
                "interpretationId": str(uuid4()),
                "rawAnswer": "Trust this client assertion.",
                "suggestionId": "client-invented-option",
                "decision": "ACCEPT",
            },
            "expected_context_version": 1,
            "command_key": "invented-semantic-authority",
        },
        headers=csrf(session),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_VERSION"
