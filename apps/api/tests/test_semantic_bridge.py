from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from apbra_api.domain import SemanticValidationFailed
from apbra_api.semantic_bridge import SemanticBridge

NODE = Path(shutil.which("node") or "/nonexistent/node")
BRIDGE = Path(os.environ.get("APBRA_TEST_SEMANTIC_BRIDGE", "/nonexistent/bridge.mjs"))
REQUEST_VERSION_ID = "00000000-0000-0000-0000-000000000123"


def context_binding(conversation: list[dict[str, object]] | None = None) -> str:
    return json.dumps(
        {
            "requestVersionId": REQUEST_VERSION_ID,
            "semanticContextVersion": 2,
            "conversation": conversation or [],
        }
    )


def canonical(value: object) -> object:
    if isinstance(value, list):
        return [canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: canonical(value[key]) for key in sorted(value)}
    return value


def ready_session() -> tuple[dict[str, object], dict[str, object]]:
    schema = {
        "kind": "REQUEST_DATA_STRUCTURE",
        "tables": [
            {
                "name": "Ledger",
                "columns": [
                    {"name": "Amount", "type": "decimal", "nullable": False},
                    {"name": "Division", "type": "text", "nullable": False},
                ],
            }
        ],
    }
    measure = {
        "id": "amount-total",
        "name": "Total Amount",
        "businessDefinition": "Sum of recorded amount",
        "aggregation": "SUM",
        "field": "Ledger.Amount",
        "numeratorMeasureId": "",
        "denominatorMeasureId": "",
        "format": "decimal",
        "filterField": "",
        "filterValue": "",
        "contextField": "",
    }
    obligation = {
        "id": "amount-kpi",
        "kind": "KPI",
        "measureNames": ["Total Amount"],
        "fields": [],
        "pageNames": ["Overview"],
        "required": True,
        "minimumRepresentations": 1,
        "measures": [measure],
        "timeGrain": "NONE",
        "lifecycleValues": [],
    }
    breakdown = {
        **obligation,
        "id": "amount-by-division",
        "kind": "BREAKDOWN",
        "fields": ["Ledger.Division"],
    }
    division_filter = {
        **obligation,
        "id": "division-filter",
        "kind": "FILTER",
        "measureNames": [],
        "fields": ["Ledger.Division"],
        "measures": [],
    }
    interpretation = {
        "request_kind": "POWER_BI_REPORT",
        "objective": "Understand recorded amount",
        "businessQuestions": ["What is the total amount?"],
        "kpis": ["Total Amount"],
        "dimensions": ["Division"],
        "filters": ["Ledger.Division"],
        "audience": "Business managers",
        "pages": ["Overview"],
        "assumptions": [],
        "ambiguities": [],
        "clarifications": [],
        "coverageRequirements": [obligation, breakdown, division_filter],
        "businessQuestionCoverage": [
            {
                "question": "What is the total amount?",
                "coverageRequirementIds": [
                    "amount-kpi",
                    "amount-by-division",
                    "division-filter",
                ],
            }
        ],
    }
    summary = {
        "objective": "Understand recorded amount",
        "businessQuestions": ["What is the total amount?"],
        "kpiDefinitions": ["Total Amount is the sum of Ledger.Amount."],
        "scopeAndTime": ["Use all supplied rows."],
        "dimensionsAndFilters": ["Division is available as a filter."],
        "lifecycleDefinitions": [],
        "materialPolicyDecisions": [],
    }
    analysis = {
        "analysedAt": "2026-09-24T00:00:00Z",
        "proposedState": "READY_FOR_CONFIRMATION",
        "interpretation": interpretation,
        "questions": [],
        "unresolvedAmbiguities": [],
        "confirmationSummary": summary,
        "conflictReasons": [],
        "knowledgeSources": [],
    }
    session: dict[str, object] = {
        "schemaVersion": 2,
        "sessionId": "api-test",
        "mode": "BUSINESS",
        "state": "READY_FOR_CONFIRMATION",
        "originalRequest": "Create a report of total amount by division.",
        "limits": {"maxRounds": 3, "maxQuestionsPerRound": 3, "maxAnswerCharacters": 500},
        "rounds": [],
        "analyses": [analysis],
        "corrections": [],
        "designConflicts": [],
        "currentInterpretation": interpretation,
        "unresolvedAmbiguities": [],
        "confirmationSummary": summary,
        "conflictReasons": [],
        "confirmedAt": "",
        "contextBinding": "case-context-v1",
        "readinessBinding": "",
    }
    readiness_projection = {
        "sessionId": session["sessionId"],
        "contextBinding": session["contextBinding"],
        "originalRequest": session["originalRequest"],
        "mode": session["mode"],
        "limits": session["limits"],
        "rounds": session["rounds"],
        "corrections": session["corrections"],
        "designConflicts": session["designConflicts"],
        "currentInterpretation": session["currentInterpretation"],
        "unresolvedAmbiguities": session["unresolvedAmbiguities"],
        "confirmationSummary": session["confirmationSummary"],
        "lastAnalysis": analysis,
    }
    session["readinessBinding"] = json.dumps(canonical(readiness_projection), separators=(",", ":"))
    return session, schema


def bridge() -> SemanticBridge:
    return SemanticBridge(BRIDGE, node_executable=NODE)


def test_bridge_uses_canonical_readiness_and_materializes_v2() -> None:
    session, schema = ready_session()
    readiness = bridge().readiness(session, schema)
    assert readiness.readiness_binding == session["readinessBinding"]
    result = bridge().confirm(
        session,
        schema,
        confirmed_at=__import__("datetime").datetime.fromisoformat("2026-09-24T00:01:00+00:00"),
        readiness_binding=readiness.readiness_binding,
        context_binding=readiness.context_binding,
    )
    assert result.contract["schema_version"] == 2
    assert result.contract["provenance"]["humanConfirmation"]["mode"] == "BUSINESS"


def test_bridge_rejects_tampered_visible_meaning() -> None:
    session, schema = ready_session()
    session["currentInterpretation"]["objective"] = "Unseen changed meaning"  # type: ignore[index]
    with pytest.raises(SemanticValidationFailed):
        bridge().readiness(session, schema)


def test_bridge_simulates_generic_ready_session_without_a_second_semantic_engine() -> None:
    _session, schema = ready_session()
    binding = context_binding()
    result = bridge().simulate(
        session_id="server-session",
        original_request="Create a report of total Amount by Division.",
        context_binding=binding,
        analysed_at=__import__("datetime").datetime.fromisoformat("2026-09-24T00:00:00+00:00"),
        data_structure=schema,
    )
    assert result.session["state"] == "READY_FOR_CONFIRMATION"
    assert result.session["contextBinding"] == binding
    assert result.session["currentInterpretation"]["coverageRequirements"][0]["measures"][0][
        "field"
    ] == "Ledger.Amount"


@pytest.mark.parametrize(
    ("business_request", "measure", "dimension"),
    [
        ("Compare Visits by Campus.", "Visits", "Campus"),
        ("Summarise Units by Depot.", "Units", "Depot"),
        ("Review WaitMinutes by Clinic.", "WaitMinutes", "Clinic"),
        ("Track Quantity by Habitat.", "Quantity", "Habitat"),
    ],
)
def test_bridge_uses_the_same_generic_path_for_unrelated_domains(
    business_request: str, measure: str, dimension: str
) -> None:
    schema = {
        "kind": "REQUEST_DATA_STRUCTURE",
        "tables": [
            {
                "name": "ObservedData",
                "columns": [
                    {"name": measure, "type": "decimal", "nullable": False},
                    {"name": dimension, "type": "text", "nullable": False},
                ],
            }
        ],
    }
    result = bridge().simulate(
        session_id="generic-domain",
        original_request=business_request,
        context_binding=context_binding(),
        analysed_at=__import__("datetime").datetime.fromisoformat("2026-09-24T00:00:00+00:00"),
        data_structure=schema,
    )
    assert result.session["state"] == "READY_FOR_CONFIRMATION"
    assert result.session["currentInterpretation"]["dimensions"] == [dimension]


def test_bridge_preserves_a_material_clarification_round_before_readiness() -> None:
    _session, schema = ready_session()
    first = bridge().simulate(
        session_id="clarification-session",
        original_request="Help managers understand this qualified evidence.",
        context_binding=context_binding(),
        analysed_at=__import__("datetime").datetime.fromisoformat("2026-09-24T00:00:00+00:00"),
        data_structure=schema,
    )
    assert first.session["state"] == "NEEDS_CLARIFICATION"
    question = first.session["rounds"][0]["questions"][0]
    answer = question["suggestions"][0]
    second = bridge().simulate(
        session_id="clarification-session",
        original_request="Help managers understand this qualified evidence.",
        context_binding=context_binding(
            [
                {
                    "kind": "RAW_ANSWER",
                    "payload": {
                        "questionId": question["id"],
                        "rawAnswer": answer["label"],
                        "suggestionId": answer["id"],
                        "decision": "ACCEPT",
                        "requestVersionId": REQUEST_VERSION_ID,
                        "interpretationContextVersion": 2,
                    },
                }
            ]
        ),
        analysed_at=__import__("datetime").datetime.fromisoformat("2026-09-24T00:01:00+00:00"),
        data_structure=schema,
    )
    assert second.session["state"] == "READY_FOR_CONFIRMATION"
    assert second.session["rounds"][0]["answers"][0]["rawAnswer"] == answer["label"]


def test_bridge_uses_exact_suggestion_identity_when_labels_repeat() -> None:
    schema = {
        "kind": "REQUEST_DATA_STRUCTURE",
        "tables": [
            {
                "name": "First",
                "columns": [
                    {"name": "Amount", "type": "decimal", "nullable": False},
                    {"name": "Group", "type": "text", "nullable": False},
                ],
            },
            {
                "name": "Second",
                "columns": [
                    {"name": "Amount", "type": "decimal", "nullable": False},
                    {"name": "Group", "type": "text", "nullable": False},
                ],
            },
        ],
    }
    first = bridge().simulate(
        session_id="duplicate-labels",
        original_request="Help managers understand the qualified evidence.",
        context_binding=context_binding(),
        analysed_at=__import__("datetime").datetime.fromisoformat("2026-09-24T00:00:00+00:00"),
        data_structure=schema,
    )
    question = first.session["rounds"][0]["questions"][0]
    assert question["suggestions"][0]["label"] == question["suggestions"][1]["label"]
    selected = question["suggestions"][1]
    second = bridge().simulate(
        session_id="duplicate-labels",
        original_request="Help managers understand the qualified evidence.",
        context_binding=context_binding(
            [
                {
                    "kind": "RAW_ANSWER",
                    "payload": {
                        "questionId": question["id"],
                        "rawAnswer": selected["label"],
                        "suggestionId": selected["id"],
                        "decision": "ACCEPT",
                        "requestVersionId": REQUEST_VERSION_ID,
                        "interpretationContextVersion": 2,
                    },
                }
            ]
        ),
        analysed_at=__import__("datetime").datetime.fromisoformat("2026-09-24T00:01:00+00:00"),
        data_structure=schema,
    )
    assert second.session["state"] == "READY_FOR_CONFIRMATION"
    assert second.session["currentInterpretation"]["coverageRequirements"][1]["fields"] == [
        "Second.Group"
    ]


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("AI returned more questions than the configured per-round limit.",
         "QUESTION_LIMIT_EXCEEDED"),
        ("Analysis knowledge provenance is malformed.", "KNOWLEDGE_PROVENANCE_INVALID"),
        (
            "Ready for confirmation requires a supported interpretation with no unresolved "
            "ambiguity in the deliverable scope.",
            "CONFIRMATION_SCOPE_UNRESOLVED",
        ),
        ("Analysis history is malformed.", "ANALYSIS_HISTORY_INVALID"),
        ("private-candidate=synthetic-secret", "SEMANTIC_RULE_UNCLASSIFIED"),
        ("CLARIFICATION_STATE_INVALID: Analysis history is malformed. "
         "private-candidate=synthetic-secret",
         "SEMANTIC_RULE_UNCLASSIFIED"),
    ],
)
def test_bridge_rejection_retains_only_curated_reason(
    monkeypatch: pytest.MonkeyPatch, message: str, reason: str
) -> None:
    import subprocess

    if reason != "SEMANTIC_RULE_UNCLASSIFIED":
        message = "CLARIFICATION_STATE_INVALID: " + message
    response = json.dumps({"ok": False, "error": {
        "code": "SEMANTIC_VALIDATION_FAILED", "message": message,
    }}).encode()
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess([], 1, response, b""))
    with pytest.raises(SemanticValidationFailed) as caught:
        bridge()._call({"operation": "analysis"})
    assert getattr(caught.value, "reason_code", None) == reason
    assert "synthetic-secret" not in str(caught.value)
    assert message not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    ("returncode", "response", "reason"),
    [
        (1, b'{"ok":true,"value":{"session":{}}}', "BRIDGE_PROCESS_FAILED"),
        (0, b'private-candidate=synthetic-secret', "BRIDGE_RESPONSE_INVALID"),
        (1, b'private-candidate=synthetic-secret', "BRIDGE_PROCESS_FAILED"),
        (0, b'{"ok":true,"value":[]}', "BRIDGE_VALUE_INVALID"),
        (0, b'{"ok":true,"value":{}}', "BRIDGE_VALUE_INVALID"),
        (0, b'{"ok":false,"error":{"code":"OTHER","message":'
         b'"Analysis history is malformed."}}', "SEMANTIC_RULE_UNCLASSIFIED"),
        (0, b'[]', "BRIDGE_RESPONSE_INVALID"),
        (0, b'"synthetic-secret"', "BRIDGE_RESPONSE_INVALID"),
        (0, b'\xff', "BRIDGE_RESPONSE_INVALID"),
    ],
)
def test_bridge_protocol_failures_remain_rejected_and_redacted(
    monkeypatch: pytest.MonkeyPatch, returncode: int, response: bytes, reason: str
) -> None:
    import subprocess
    from datetime import UTC, datetime

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess([], returncode, response, b""))
    with pytest.raises(SemanticValidationFailed) as caught:
        bridge().analysis(session_id="synthetic", original_request="synthetic",
                          context_binding="synthetic", analysed_at=datetime.now(UTC),
                          data_structure={}, analysis={}, limits={})
    assert getattr(caught.value, "reason_code", None) == reason
    assert "synthetic-secret" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("kind", ["timeout", "process", "input_size", "output_size"])
def test_bridge_transport_failures_have_constant_reasons(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    import subprocess

    from apbra_api.semantic_bridge import MAX_BRIDGE_BYTES

    def respond(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if kind == "timeout":
            raise subprocess.TimeoutExpired("synthetic-secret", 1, output=b"synthetic-secret")
        if kind == "process":
            raise OSError("synthetic-secret")
        return subprocess.CompletedProcess([], 0, b"x" * (MAX_BRIDGE_BYTES + 1), b"")

    monkeypatch.setattr(subprocess, "run", respond)
    with pytest.raises(SemanticValidationFailed) as caught:
        bridge()._call({"operation": "analysis", "synthetic":
                        "x" * (MAX_BRIDGE_BYTES + 1) if kind == "input_size" else ""})
    expected = {"timeout": "BRIDGE_TIMEOUT", "process": "BRIDGE_PROCESS_FAILED",
                "input_size": "BRIDGE_INPUT_TOO_LARGE", "output_size": "BRIDGE_OUTPUT_TOO_LARGE"}
    assert getattr(caught.value, "reason_code", None) == expected[kind]
    assert "synthetic-secret" not in str(caught.value)
    assert caught.value.__cause__ is None
