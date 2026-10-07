from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from apbra_api.api import create_app
from apbra_api.auth_boundary import SESSION_COOKIE, digest
from apbra_api.config import Settings
from apbra_api.domain import SemanticValidationFailed
from apbra_api.model_provider import (
    DeterministicFakeProvider,
    OpenAICompatibleProvider,
    ProviderProfile,
)
from apbra_api.persistence import (
    ApplicationSession,
    AuditEventRow,
    CaseAccessRow,
    ConfirmedContractRow,
    Database,
    EvidenceRow,
    InterpretationRow,
    SessionRow,
)
from apbra_api.semantic_bridge import SemanticBridge


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


def provider_profile() -> ProviderProfile:
    return ProviderProfile.model_validate(
        {
            "profile_id": "clarification-test-profile",
            "protocol": "OPENAI_CHAT_COMPATIBLE",
            "endpoint": "https://provider.invalid/v1/chat/completions",
            "model_or_deployment": "synthetic-test-model",
            "api_version": "test-version",
            "region": "test-region",
            "prompt_version": "requirements-test-v1",
            "configuration_id": "clarification-test-configuration",
            "capabilities": {"structured_output": True, "vision": False},
            "max_calls_per_operation": 1,
            "max_input_characters": 200_000,
            "max_output_tokens": 8_000,
            "time_budget_seconds": 30,
            "request_timeout_seconds": 10,
            "retry_limit": 0,
        }
    )


def provider_analysis(*, ready: bool) -> dict[str, object]:
    measure = {
        "id": "visits",
        "name": "Visits",
        "businessDefinition": "Sum of the visits established by the supplied context.",
        "aggregation": "SUM",
        "field": "Metrics.Visits",
        "numeratorMeasureId": "",
        "denominatorMeasureId": "",
        "format": "integer",
        "filterField": "",
        "filterValue": "",
        "contextField": "",
    }
    kpi = {
        "id": "visits-kpi",
        "kind": "KPI",
        "measureNames": ["Visits"],
        "fields": [],
        "pageNames": ["Performance"],
        "required": True,
        "minimumRepresentations": 1,
        "measures": [measure],
        "timeGrain": "NONE",
        "lifecycleValues": [],
    }
    breakdown = {**kpi, "id": "visits-campus", "kind": "BREAKDOWN", "fields": ["Metrics.Campus"]}
    question = "Which business definition should the Visits field represent for this report?"
    interpretation: dict[str, object] = {
        "request_kind": "POWER_BI_REPORT",
        "objective": "Understand visits by campus",
        "businessQuestions": ["How do visits compare by campus?"] if ready else [],
        "kpis": ["Visits"] if ready else [],
        "dimensions": ["Campus"] if ready else [],
        "filters": [],
        "audience": "Business managers",
        "pages": ["Performance"] if ready else [],
        "assumptions": [],
        "ambiguities": [] if ready else ["The meaning of Visits requires user confirmation."],
        "clarifications": [],
        "coverageRequirements": [kpi, breakdown] if ready else [],
        "businessQuestionCoverage": (
            [
                {
                    "question": "How do visits compare by campus?",
                    "coverageRequirementIds": ["visits-kpi", "visits-campus"],
                }
            ]
            if ready
            else []
        ),
    }
    return {
        "state": "READY_FOR_CONFIRMATION" if ready else "NEEDS_CLARIFICATION",
        "interpretation": interpretation,
        "questions": (
            []
            if ready
            else [
                {
                    "id": "provider-visits-meaning",
                    "category": "METRIC_DEFINITION",
                    "question": question,
                    "reason": "The request does not establish that business definition.",
                    "required": True,
                    "suggestions": [],
                    "allowFreeText": True,
                }
            ]
        ),
        "unresolvedAmbiguities": (
            [] if ready else ["The meaning of Visits requires user confirmation."]
        ),
        "confirmationSummary": {
            "objective": "Understand visits by campus",
            "businessQuestions": ["How do visits compare by campus?"] if ready else [],
            "kpiDefinitions": (
                ["Visits uses the user-confirmed business definition."] if ready else []
            ),
            "scopeAndTime": [],
            "dimensionsAndFilters": ["Campus is the confirmed comparison."] if ready else [],
            "lifecycleDefinitions": [],
            "materialPolicyDecisions": [],
        },
        "conflictReasons": [],
    }


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


def test_normal_runtime_without_a_provider_never_uses_the_test_simulator(
    settings: Settings, database: Database
) -> None:
    runtime_settings = settings.model_copy(update={"test_semantic_simulator_enabled": False})
    with TestClient(create_app(settings=runtime_settings, database=database)) as runtime:
        session = sign_in(runtime, "member")
        case = create_case(runtime, session)
        uploaded = runtime.post(
            f"/api/cases/{case['id']}/evidence",
            params={"filename": "metrics.csv", "expected_context_version": 1},
            content=b"Campus,Visits\nNorth,12\nSouth,9\n",
            headers={**csrf(session), "Content-Type": "application/octet-stream"},
        ).json()["evidence"]
        response = runtime.post(
            f"/api/cases/{case['id']}/interpretations",
            json={"expected_context_version": uploaded["semantic_context_version"]},
            headers=csrf(session),
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INTELLIGENT_ANALYSIS_UNAVAILABLE"


@pytest.mark.parametrize(
    ("failure_kind", "expected_code"),
    [
        ("provider_4xx", "MODEL_PROVIDER_REJECTED"),
        ("timeout", "MODEL_PROVIDER_TIMEOUT"),
        ("malformed_2xx", "MODEL_OUTPUT_INVALID"),
    ],
)
def test_failed_provider_attempt_has_durable_safe_observation(
    settings: Settings, database: Database, failure_kind: str, expected_code: str
) -> None:
    def respond(incoming: httpx.Request) -> httpx.Response:
        if failure_kind == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=incoming)
        if failure_kind == "malformed_2xx":
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "not-json"}}],
                    "usage": {
                        "prompt_tokens": 7,
                        "completion_tokens": 3,
                        "total_tokens": 10,
                    },
                },
            )
        return httpx.Response(403, text="credential=server-secret")

    provider = OpenAICompatibleProvider(
        provider_profile(), "server-secret", transport=httpx.MockTransport(respond)
    )
    with TestClient(
        create_app(settings=settings, database=database, model_provider=provider)
    ) as runtime:
        session = sign_in(runtime, "member")
        case = create_case(runtime, session)
        uploaded = runtime.post(
            f"/api/cases/{case['id']}/evidence",
            params={"filename": "synthetic.csv", "expected_context_version": 1},
            content=b"Campus,Visits\nNorth,12\nSouth,9\n",
            headers={**csrf(session), "Content-Type": "application/octet-stream"},
        ).json()["evidence"]
        failed = runtime.post(
            f"/api/cases/{case['id']}/interpretations",
            json={"expected_context_version": uploaded["semantic_context_version"]},
            headers=csrf(session),
        )
        assert failed.status_code == 409, failed.text
        assert failed.json()["error"]["code"] == "INTELLIGENT_ANALYSIS_UNAVAILABLE"

    with database.session() as db:
        audit = db.scalars(
            select(AuditEventRow).where(
                AuditEventRow.resource_id == UUID(str(case["id"])),
                AuditEventRow.event_type == "INTERPRETATION_ATTEMPT_FAILED",
            )
        ).all()
        interpretation_count = db.scalar(
            select(func.count()).select_from(InterpretationRow).where(
                InterpretationRow.case_id == UUID(str(case["id"]))
            )
        )
        evidence_count = db.scalar(
            select(func.count()).select_from(EvidenceRow).where(
                EvidenceRow.case_id == UUID(str(case["id"]))
            )
        )
    assert len(audit) == 1
    details = json.loads(audit[0].details_json)
    assert details == {
        "stage": "PROVIDER_CALL",
        "error_code": expected_code,
        "call_count": 1,
        "usage": {
            "prompt_tokens": 7 if failure_kind == "malformed_2xx" else None,
            "completion_tokens": 3 if failure_kind == "malformed_2xx" else None,
            "total_tokens": 10 if failure_kind == "malformed_2xx" else None,
        },
    }
    assert interpretation_count == 0
    assert evidence_count == 1
    assert "server-secret" not in audit[0].details_json


@pytest.mark.parametrize(
    ("failure_kind", "reason"),
    [
        ("negative_minimum", "SEMANTIC_RULE_UNCLASSIFIED"),
        ("invalid_obligation_reference", "SEMANTIC_RULE_UNCLASSIFIED"),
        ("invented_field", "SEMANTIC_RULE_UNCLASSIFIED"),
        ("unknown_error", "SEMANTIC_RULE_UNCLASSIFIED"),
        ("tampered_reason", "SEMANTIC_RULE_UNCLASSIFIED"),
    ],
)
def test_semantic_rejection_records_observed_usage_without_accepting_interpretation(
    settings: Settings, database: Database, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture, failure_kind: str, reason: str,
) -> None:
    invalid = provider_analysis(ready=True)
    interpretation = cast(dict[str, object], invalid["interpretation"])
    coverage = cast(list[dict[str, object]], interpretation["coverageRequirements"])
    if failure_kind == "negative_minimum":
        coverage[0]["minimumRepresentations"] = -1
    elif failure_kind == "invalid_obligation_reference":
        interpretation["businessQuestionCoverage"] = [
            {"question": "How do visits compare by campus?",
             "coverageRequirementIds": ["synthetic-private-canary"]}
        ]
    elif failure_kind == "invented_field":
        measures = cast(list[dict[str, object]], coverage[0]["measures"])
        measures[0]["field"] = "Synthetic.Unknown"
    else:
        def reject(*args: object, **kwargs: object) -> object:
            error = SemanticValidationFailed("synthetic-private-canary")
            if failure_kind == "tampered_reason":
                error.reason_code = "synthetic-private-canary"  # type: ignore[attr-defined]
            raise error
        monkeypatch.setattr(SemanticBridge, "analysis", reject)
    provider = DeterministicFakeProvider(provider_profile(), [invalid])
    with TestClient(
        create_app(settings=settings, database=database, model_provider=provider)
    ) as runtime:
        session = sign_in(runtime, "member")
        case = create_case(runtime, session)
        uploaded = runtime.post(
            f"/api/cases/{case['id']}/evidence",
            params={"filename": "synthetic.csv", "expected_context_version": 1},
            content=b"Campus,Visits\nNorth,12\nSouth,9\n",
            headers={**csrf(session), "Content-Type": "application/octet-stream"},
        ).json()["evidence"]
        failed = runtime.post(
            f"/api/cases/{case['id']}/interpretations",
            json={"expected_context_version": uploaded["semantic_context_version"]},
            headers=csrf(session),
        )
        assert failed.status_code == 409, failed.text
    with database.session() as db:
        audit = db.scalars(
            select(AuditEventRow).where(
                AuditEventRow.resource_id == UUID(str(case["id"])),
                AuditEventRow.event_type == "INTERPRETATION_ATTEMPT_FAILED",
            )
        ).all()
    assert len(audit) == 1
    details = json.loads(audit[0].details_json)
    assert details["stage"] == "SEMANTIC_VALIDATION"
    assert details["semantic_reason"] == reason
    assert details["call_count"] == 1
    assert "synthetic-private-canary" not in audit[0].details_json
    assert "synthetic-private-canary" not in failed.text
    assert "synthetic-private-canary" not in caplog.text
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(InterpretationRow).where(
            InterpretationRow.case_id == UUID(str(case["id"]))
        )) == 0
        assert db.scalar(select(func.count()).select_from(EvidenceRow).where(
            EvidenceRow.case_id == UUID(str(case["id"]))
        )) == 1
    assert details["usage"] == {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30,
    }


def test_no_provider_call_is_audited_with_unknown_usage(
    settings: Settings, database: Database
) -> None:
    provider = DeterministicFakeProvider(provider_profile(), [])
    with TestClient(
        create_app(settings=settings, database=database, model_provider=provider)
    ) as runtime:
        session = sign_in(runtime, "member")
        case = create_case(runtime, session)
        uploaded = runtime.post(
            f"/api/cases/{case['id']}/evidence",
            params={"filename": "synthetic.csv", "expected_context_version": 1},
            content=b"Campus,Visits\nNorth,12\nSouth,9\n",
            headers={**csrf(session), "Content-Type": "application/octet-stream"},
        ).json()["evidence"]
        failed = runtime.post(
            f"/api/cases/{case['id']}/interpretations",
            json={"expected_context_version": uploaded["semantic_context_version"]},
            headers=csrf(session),
        )
        assert failed.status_code == 409
    with database.session() as db:
        audit = db.scalars(
            select(AuditEventRow).where(
                AuditEventRow.resource_id == UUID(str(case["id"])),
                AuditEventRow.event_type == "INTERPRETATION_ATTEMPT_FAILED",
            )
        ).all()
    assert len(audit) == 1
    details = json.loads(audit[0].details_json)
    assert details["call_count"] == 0
    assert details["usage"] == {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }


@pytest.mark.parametrize("access_change", ["session_expired", "case_grant_revoked"])
def test_provider_failure_accounting_survives_midcall_access_change(
    settings: Settings, database: Database, access_change: str
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    case = create_case(owner, owner_session)
    member_id: UUID | None = None
    if access_change == "case_grant_revoked":
        member_id = UUID(next(
            str(item["id"])
            for item in owner.get("/api/memberships").json()["items"]
            if item["subject"] == "dev-member"
        ))
        granted = owner.post(
            f"/api/cases/{case['id']}/access",
            json={"membership_id": str(member_id), "access_level": "EDITOR"},
            headers=csrf(owner_session),
        )
        assert granted.status_code == 200

    def respond(incoming: httpx.Request) -> httpx.Response:
        with database.session() as separate:
            if access_change == "session_expired":
                token = runtime.cookies.get(SESSION_COOKIE)
                assert token is not None
                row = separate.scalar(
                    select(SessionRow).where(SessionRow.token_digest == digest(token))
                )
                assert row is not None
                row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            else:
                assert member_id is not None
                separate.execute(
                    delete(CaseAccessRow).where(
                        CaseAccessRow.case_id == UUID(str(case["id"])),
                        CaseAccessRow.membership_id == member_id,
                    )
                )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "not-json"}}],
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 3,
                    "total_tokens": 10,
                },
            },
        )

    provider = OpenAICompatibleProvider(
        provider_profile(), "server-secret", transport=httpx.MockTransport(respond)
    )
    with TestClient(
        create_app(settings=settings, database=database, model_provider=provider)
    ) as runtime:
        session = sign_in(runtime, "owner" if member_id is None else "member")
        uploaded = runtime.post(
            f"/api/cases/{case['id']}/evidence",
            params={"filename": "synthetic.csv", "expected_context_version": 1},
            content=b"Campus,Visits\nNorth,12\nSouth,9\n",
            headers={**csrf(session), "Content-Type": "application/octet-stream"},
        ).json()["evidence"]
        failed = runtime.post(
            f"/api/cases/{case['id']}/interpretations",
            json={"expected_context_version": uploaded["semantic_context_version"]},
            headers=csrf(session),
        )
        assert failed.status_code == (401 if member_id is None else 404), failed.text

    with database.session() as db:
        audit = db.scalars(select(AuditEventRow).where(
            AuditEventRow.resource_id == UUID(str(case["id"])),
            AuditEventRow.event_type == "INTERPRETATION_ATTEMPT_FAILED",
        )).all()
        interpretations = db.scalar(select(func.count()).select_from(InterpretationRow).where(
            InterpretationRow.case_id == UUID(str(case["id"]))
        ))
        evidence = db.scalar(select(func.count()).select_from(EvidenceRow).where(
            EvidenceRow.case_id == UUID(str(case["id"]))
        ))
    assert len(audit) == 1
    details = json.loads(audit[0].details_json)
    assert details["error_code"] == "MODEL_OUTPUT_INVALID"
    assert details["call_count"] == 1
    assert details["usage"] == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "total_tokens": 10,
    }
    assert interpretations == 0
    assert evidence == 1
    assert "server-secret" not in audit[0].details_json


def test_provider_owns_question_and_follow_up_analysis_with_full_durable_context(
    settings: Settings, database: Database
) -> None:
    provider = DeterministicFakeProvider(
        provider_profile(), [provider_analysis(ready=False), provider_analysis(ready=True)]
    )
    with TestClient(
        create_app(settings=settings, database=database, model_provider=provider)
    ) as runtime:
        session = sign_in(runtime, "member")
        case = create_case(runtime, session)
        uploaded = runtime.post(
            f"/api/cases/{case['id']}/evidence",
            params={"filename": "Metrics.csv", "expected_context_version": 1},
            content=b"Campus,Visits\nNorth,12\nSouth,9\n",
            headers={**csrf(session), "Content-Type": "application/octet-stream"},
        ).json()["evidence"]
        first = runtime.post(
            f"/api/cases/{case['id']}/interpretations",
            json={"expected_context_version": uploaded["semantic_context_version"]},
            headers=csrf(session),
        )
        assert first.status_code == 200, first.text
        interpretation = first.json()["interpretation"]
        assert interpretation["simulation"] == "QUALIFIED_SERVER_MODEL"
        assert interpretation["questions"][0]["question"] == (
            "Which business definition should the Visits field represent for this report?"
        )
        answered = runtime.post(
            f"/api/cases/{case['id']}/conversation",
            json={
                "kind": "RAW_ANSWER",
                "payload": {
                    "questionId": "provider-visits-meaning",
                    "interpretationId": interpretation["id"],
                    "rawAnswer": "Visits means the recorded visits in the supplied file.",
                    "decision": "FREE_TEXT",
                },
                "expected_context_version": interpretation["context_version"],
                "command_key": "provider-owned-answer",
            },
            headers=csrf(session),
        )
        assert answered.status_code == 200, answered.text
        ready = runtime.post(
            f"/api/cases/{case['id']}/interpretations",
            json={"expected_context_version": answered.json()["event"]["semantic_context_version"]},
            headers=csrf(session),
        )
        assert ready.status_code == 200, ready.text
        assert ready.json()["interpretation"]["state"] == "READY_FOR_CONFIRMATION"
    assert [request.task for request in provider.requests] == [
        "REQUIREMENT_ANALYSIS",
        "REQUIREMENT_ANALYSIS",
    ]
    second_context = provider.requests[1].context["materialContext"]
    assert isinstance(second_context, dict)
    assert second_context["conversation"][0]["payload"]["rawAnswer"] == (
        "Visits means the recorded visits in the supplied file."
    )


def test_optional_model_question_cycle_limits_and_restart_preserve_acceptance(
    settings: Settings, database: Database
) -> None:
    optional = provider_analysis(ready=True)
    question = cast(list[dict[str, object]], provider_analysis(ready=False)["questions"])[0]
    question["required"] = False
    optional["questions"] = [question]
    provider = DeterministicFakeProvider(
        provider_profile(), [optional, provider_analysis(ready=True), optional]
    )
    with TestClient(
        create_app(settings=settings, database=database, model_provider=provider)
    ) as runtime:
        owner = sign_in(runtime, "owner")
        current = runtime.get("/api/tenant-settings").json()
        policy = current["settings"]
        policy["max_clarification_rounds_per_cycle"] = 1
        policy["max_clarification_rounds_overall"] = 2
        changed = runtime.put(
            "/api/tenant-settings",
            headers=csrf(owner),
            json={"expected_version": current["version"], "settings": policy},
        )
        assert changed.status_code == 200, changed.text
        member = sign_in(runtime, "member")
        case = create_case(runtime, member)
        uploaded = runtime.post(
            f"/api/cases/{case['id']}/evidence",
            params={"filename": "Metrics.csv", "expected_context_version": 1},
            content=b"Campus,Visits\nNorth,12\nSouth,9\n",
            headers={**csrf(member), "Content-Type": "application/octet-stream"},
        ).json()["evidence"]
        first = runtime.post(
            f"/api/cases/{case['id']}/interpretations",
            json={"expected_context_version": uploaded["semantic_context_version"]},
            headers=csrf(member),
        )
        assert first.status_code == 200, first.text
        interpretation = first.json()["interpretation"]
        assert interpretation["state"] == "READY_FOR_CONFIRMATION"
        assert len(interpretation["questions"]) == 1
        assert interpretation["clarification"]["rounds_used_in_cycle"] == 1
        answer = runtime.post(
            f"/api/cases/{case['id']}/conversation",
            json={
                "kind": "RAW_ANSWER",
                "payload": {
                    "questionId": question["id"],
                    "interpretationId": interpretation["id"],
                    "rawAnswer": "Recorded visits in the supplied file.",
                    "decision": "FREE_TEXT",
                },
                "expected_context_version": interpretation["context_version"],
                "command_key": "optional-answer-once",
            },
            headers=csrf(member),
        )
        assert answer.status_code == 200, answer.text
        answered_version = answer.json()["event"]["semantic_context_version"]
        second = runtime.post(
            f"/api/cases/{case['id']}/interpretations",
            json={"expected_context_version": answered_version},
            headers=csrf(member),
        )
        assert second.status_code == 200, second.text
        assert second.json()["interpretation"]["clarification"]["rounds_used_overall"] == 1
        refinement = {
            "expected_context_version": answered_version,
            "command_key": "explicit-cycle-one",
            "enhancement": "Include the current accepted context.",
        }
        cycle = runtime.post(
            f"/api/cases/{case['id']}/clarification-cycles",
            json=refinement,
            headers=csrf(member),
        )
        assert cycle.status_code == 200, cycle.text
        replay = runtime.post(
            f"/api/cases/{case['id']}/clarification-cycles",
            json=refinement,
            headers=csrf(member),
        )
        assert replay.status_code == 200
        assert replay.json()["semantic_context_version"] == cycle.json()["semantic_context_version"]
        third = runtime.post(
            f"/api/cases/{case['id']}/interpretations",
            json={"expected_context_version": cycle.json()["semantic_context_version"]},
            headers=csrf(member),
        )
        assert third.status_code == 200, third.text
        final = third.json()["interpretation"]
        assert final["state"] == "READY_FOR_CONFIRMATION"
        assert final["clarification"]["rounds_used_overall"] == 2
        assert final["clarification"]["overall_limit_reached"] is True
        accepted = runtime.post(
            f"/api/cases/{case['id']}/confirm",
            json={
                "interpretation_id": final["id"],
                "expected_context_version": final["context_version"],
            },
            headers=csrf(member),
        )
        assert accepted.status_code == 200, accepted.text
        blocked = runtime.post(
            f"/api/cases/{case['id']}/clarification-cycles",
            json={
                "expected_context_version": final["context_version"],
                "command_key": "blocked-overall-cycle",
                "enhancement": "Another refinement",
            },
            headers=csrf(member),
        )
        assert blocked.status_code == 409
    with TestClient(create_app(settings=settings, database=database)) as restarted:
        restarted.cookies.update(runtime.cookies)
        state = restarted.get(f"/api/cases/{case['id']}/acceptance")
        assert state.status_code == 200
        assert state.json()["clarification"]["rounds_used_overall"] == 2
        assert state.json()["confirmed_contract"] is not None
    context = provider.requests[2].context["materialContext"]
    assert context["priorInterpretations"]
    assert context["conversation"]


def test_configured_answer_limit_is_enforced_by_the_server(
    settings: Settings, database: Database
) -> None:
    with TestClient(create_app(settings=settings, database=database)) as runtime:
        owner = sign_in(runtime, "owner")
        current = runtime.get("/api/tenant-settings").json()
        policy = current["settings"]
        policy["clarification_policy"]["max_answer_characters"] = 100
        updated = runtime.put(
            "/api/tenant-settings",
            headers=csrf(owner),
            json={"expected_version": current["version"], "settings": policy},
        )
        assert updated.status_code == 200, updated.text
        session = sign_in(runtime, "member")
        case, interpretation = prepare_ambiguous_case(runtime, session)
        question = cast(list[dict[str, object]], interpretation["questions"])[0]
        rejected = runtime.post(
            f"/api/cases/{case['id']}/conversation",
            json={
                "kind": "RAW_ANSWER",
                "payload": {
                    "questionId": question["id"],
                    "interpretationId": interpretation["id"],
                    "rawAnswer": "x" * 101,
                    "decision": "FREE_TEXT",
                },
                "expected_context_version": interpretation["context_version"],
                "command_key": "bounded-answer",
            },
            headers=csrf(session),
        )
    assert rejected.status_code == 409


def test_durable_conversation_evidence_and_exact_acceptance(
    client: TestClient, database: Database
) -> None:
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
    assert repeated.json()["confirmed_contract"]["contract"] == contract["contract"]
    assert repeated.json()["confirmed_contract"]["accepted_at"] == contract["accepted_at"]

    with database.session() as db:
        contract_count = db.scalar(
            select(func.count())
            .select_from(ConfirmedContractRow)
            .where(ConfirmedContractRow.interpretation_id == UUID(interpretation_json["id"]))
        )
        audit_count = db.scalar(
            select(func.count())
            .select_from(AuditEventRow)
            .where(
                AuditEventRow.resource_id == UUID(str(case_id)),
                AuditEventRow.event_type == "REQUIREMENTS_CONFIRMED",
            )
        )
    assert contract_count == 1
    assert audit_count == 1

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
    replay = client.post(
        f"/api/cases/{case['id']}/confirm",
        json={
            "interpretation_id": interpretation["id"],
            "expected_context_version": uploaded["semantic_context_version"],
        },
        headers=csrf(session),
    )
    assert replay.status_code == 422
    assert replay.json()["error"]["code"] == "SEMANTIC_VALIDATION_FAILED"

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


@pytest.mark.parametrize(
    "damage", ["missing-primary", "tampered-secondary", "ineligible-secondary"]
)
def test_confirmation_replay_requalifies_the_complete_evidence_set(
    client: TestClient,
    settings: Settings,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
) -> None:
    session = sign_in(client, "member")
    case = create_case(client, session)
    uploaded: list[dict[str, object]] = []
    context_version = 1
    for filename, content in (
        ("amounts.csv", b"Amount,Division\n12,North\n"),
        ("targets.csv", b"Target,Team\n20,Operations\n"),
    ):
        response = client.post(
            f"/api/cases/{case['id']}/evidence",
            params={"filename": filename, "expected_context_version": context_version},
            content=content,
            headers={**csrf(session), "Content-Type": "application/octet-stream"},
        )
        assert response.status_code == 200, response.text
        record = cast(dict[str, object], response.json()["evidence"])
        uploaded.append(record)
        context_version = cast(int, record["semantic_context_version"])
    interpretation = client.post(
        f"/api/cases/{case['id']}/interpretations",
        json={"expected_context_version": context_version},
        headers=csrf(session),
    ).json()["interpretation"]
    first = client.post(
        f"/api/cases/{case['id']}/confirm",
        json={
            "interpretation_id": interpretation["id"],
            "expected_context_version": context_version,
        },
        headers=csrf(session),
    )
    assert first.status_code == 200, first.text
    historical = first.json()["confirmed_contract"]

    affected = uploaded[0] if damage == "missing-primary" else uploaded[1]
    if damage == "ineligible-secondary":
        original_evidence_items = ApplicationSession.evidence_items

        def eligible_items(store: ApplicationSession, case_id: UUID) -> list[EvidenceRow]:
            return [
                row
                for row in original_evidence_items(store, case_id)
                if row.id != UUID(str(affected["id"]))
            ]

        monkeypatch.setattr(ApplicationSession, "evidence_items", eligible_items)
    else:
        object_path = next(
            path
            for path in settings.evidence_root.rglob("*.bin")
            if path.parent.name == case["id"]
            and hashlib.sha256(path.read_bytes()).hexdigest() == affected["content_digest"]
        )
        if damage == "missing-primary":
            object_path.unlink()
        else:
            object_path.write_bytes(b"Target,Team\n999,Tampered\n")

    state = client.get(f"/api/cases/{case['id']}/acceptance")
    assert state.status_code == 200
    assert state.json()["interpretation"]["current"] is False
    assert state.json()["confirmed_contract"]["current"] is False
    repeated_preparation = client.post(
        f"/api/cases/{case['id']}/interpretations",
        json={"expected_context_version": context_version},
        headers=csrf(session),
    )
    assert repeated_preparation.status_code == 422
    assert repeated_preparation.json()["error"]["code"] == "SEMANTIC_VALIDATION_FAILED"
    replay = client.post(
        f"/api/cases/{case['id']}/confirm",
        json={
            "interpretation_id": interpretation["id"],
            "expected_context_version": context_version,
        },
        headers=csrf(session),
    )
    assert replay.status_code == 422
    assert replay.json()["error"]["code"] == "SEMANTIC_VALIDATION_FAILED"

    with database.session() as db:
        retained = db.scalar(
            select(ConfirmedContractRow).where(ConfirmedContractRow.id == UUID(historical["id"]))
        )
        audit_count = db.scalar(
            select(func.count())
            .select_from(AuditEventRow)
            .where(
                AuditEventRow.resource_id == UUID(str(case["id"])),
                AuditEventRow.event_type == "REQUIREMENTS_CONFIRMED",
            )
        )
    assert retained is not None
    assert retained.contract_json == json.dumps(
        historical["contract"], sort_keys=True, separators=(",", ":")
    )
    assert audit_count == 1


def test_revoked_private_access_blocks_confirmation_replay_and_state(
    settings: Settings, database: Database
) -> None:
    owner = TestClient(create_app(settings=settings, database=database))
    owner_session = sign_in(owner, "owner")
    case = create_case(owner, owner_session)
    member_id = next(
        item["id"]
        for item in owner.get("/api/memberships").json()["items"]
        if item["subject"] == "dev-member"
    )
    granted = owner.post(
        f"/api/cases/{case['id']}/access",
        json={"membership_id": member_id, "access_level": "EDITOR"},
        headers=csrf(owner_session),
    )
    assert granted.status_code == 200

    member = TestClient(create_app(settings=settings, database=database))
    member_session = sign_in(member, "member")
    uploaded = member.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "qualified.csv", "expected_context_version": 1},
        content=b"Amount,Division\n12,North\n",
        headers={**csrf(member_session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    interpretation = member.post(
        f"/api/cases/{case['id']}/interpretations",
        json={"expected_context_version": uploaded["semantic_context_version"]},
        headers=csrf(member_session),
    ).json()["interpretation"]
    confirmed = member.post(
        f"/api/cases/{case['id']}/confirm",
        json={
            "interpretation_id": interpretation["id"],
            "expected_context_version": uploaded["semantic_context_version"],
        },
        headers=csrf(member_session),
    )
    assert confirmed.status_code == 200

    revoked = owner.post(
        f"/api/cases/{case['id']}/access/{member_id}/revoke",
        headers=csrf(owner_session),
    )
    assert revoked.status_code == 200
    replay = member.post(
        f"/api/cases/{case['id']}/confirm",
        json={
            "interpretation_id": interpretation["id"],
            "expected_context_version": uploaded["semantic_context_version"],
        },
        headers=csrf(member_session),
    )
    assert replay.status_code == 404
    assert member.get(f"/api/cases/{case['id']}/acceptance").status_code == 404


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
    declined_question = cast(list[dict[str, object]], declined_interpretation["questions"])[0]
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
    identical_events = client.get(f"/api/cases/{identical_case['id']}/conversation").json()["items"]
    assert len(identical_events) == 1

    conflicting_case = create_case(client, session)
    conflicting = execute_pair(
        str(conflicting_case["id"]),
        ({"text": "First payload."}, {"text": "Different payload."}),
        "concurrent-conflicting-message",
    )
    assert sorted(status for status, _identifier, _code in conflicting) == [200, 409]
    assert "IDEMPOTENCY_CONFLICT" in {code for _status, _identifier, code in conflicting}
    conflicting_events = client.get(f"/api/cases/{conflicting_case['id']}/conversation").json()[
        "items"
    ]
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
