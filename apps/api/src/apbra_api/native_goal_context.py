"""Goal-only AI conversation context, without invented evidence or interpretation.

This is source projection, not a report/question generator. Empty evidence cannot
enter the existing evidence-bound confirmation pipeline through this helper.
"""

import json
from typing import Any
from uuid import UUID

from .domain import ApplicationPersistence, CaseRecord, SemanticValidationFailed


def goal_only_context(store: ApplicationPersistence, case: CaseRecord) -> dict[str, Any]:
    request = store.request_version(case.current_request_version_id)
    if request is None or request.id != case.current_request_version_id:
        raise SemanticValidationFailed()
    events = store.conversation_events(case.id)
    if any(event.case_id != case.id for event in events):
        raise SemanticValidationFailed()
    versions = store.case_versions(case.id)
    return {
        "caseId": str(case.id),
        "requestVersionId": str(case.current_request_version_id),
        "requestText": request.request_text,
        "originalRequest": versions[0].request_text if versions else request.request_text,
        "semanticContextVersion": case.semantic_context_version,
        "conversation": [
            {
                "id": str(event.id),
                "sequence": event.sequence,
                "kind": event.kind,
                "payload": json.loads(event.payload_json),
            }
            for event in events
        ],
        "evidence": [],
        "referenceMaterial": [],
    }


def assistant_texts(raw: bytes) -> list[str]:
    """Project assistant text only; never service/tool payloads or diagnostic fields."""
    try:
        body = json.loads(raw)
        if type(body) is not dict or type(body.get("output")) is not list:
            return []
        return [
            part["text"]
            for output in body["output"]
            if type(output) is dict
            and output.get("type") == "message"
            and output.get("role") == "assistant"
            and type(output.get("content")) is list
            for part in output["content"]
            if type(part) is dict
            and part.get("type") == "output_text"
            and type(part.get("text")) is str
        ]
    except (ValueError, UnicodeError, RecursionError):
        return []


def prior_analysis_receipts(db: Any, company_id: Any, case_id: Any, version: int) -> list[Any]:
    """One canonical completed, earlier-context receipt set for send and approval."""
    from sqlalchemy import select

    from .native_response_index import (
        NativeContractBindingRow,
        NativeReceiveCommandRow,
        NativeResponseReceiptRow,
    )

    return list(
        db.scalars(
            select(NativeResponseReceiptRow)
            .join(
                NativeContractBindingRow,
                NativeContractBindingRow.operation_id == NativeResponseReceiptRow.operation_id,
            )
            .join(
                NativeReceiveCommandRow,
                NativeReceiveCommandRow.id == NativeResponseReceiptRow.operation_id,
            )
            .where(
                NativeReceiveCommandRow.state == "RECEIVED",
                NativeReceiveCommandRow.http_status == 200,
                NativeReceiveCommandRow.provider_status == "completed",
                NativeReceiveCommandRow.company_id == company_id,
                NativeReceiveCommandRow.case_id == case_id,
                NativeResponseReceiptRow.company_id == company_id,
                NativeResponseReceiptRow.case_id == case_id,
                NativeResponseReceiptRow.context_version < version,
                NativeContractBindingRow.company_id == company_id,
                NativeContractBindingRow.case_id == case_id,
                NativeContractBindingRow.task == "REQUIREMENT_ANALYSIS",
            )
            .order_by(NativeResponseReceiptRow.created_at, NativeResponseReceiptRow.id)
        )
    )


def native_context_binding(context_binding: str, receipts: list[Any]) -> str:
    """Bind input authority to exact immutable prior-answer metadata, never raw text."""
    return json.dumps(
        {
            "materialContextBinding": context_binding,
            "priorAnalysisReceipts": [
                {
                    "id": str(row.id),
                    "digest": row.digest,
                    "contextVersion": row.context_version,
                    "task": "REQUIREMENT_ANALYSIS",
                }
                for row in receipts
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def analysis_display(
    value: dict[str, Any],
    reference: UUID,
    version: int,
) -> dict[str, Any] | None:
    summary = value.get("confirmationSummary")
    questions = value.get("questions")
    details = value.get("interpretation")
    ambiguities = value.get("unresolvedAmbiguities")
    groups = (
        "businessQuestions",
        "kpiDefinitions",
        "scopeAndTime",
        "dimensionsAndFilters",
        "lifecycleDefinitions",
        "materialPolicyDecisions",
    )

    def strings(items: Any) -> bool:
        return type(items) is list and all(type(item) is str for item in items)

    if (
        type(summary) is not dict
        or type(summary.get("objective")) is not str
        or not all(strings(summary.get(key)) for key in groups)
        or type(questions) is not list
        or type(details) is not dict
        or not strings(ambiguities)
    ):
        return None
    projected = []
    seen: set[str] = set()
    for question in questions:
        if (
            type(question) is not dict
            or not all(type(question.get(key)) is str for key in ("id", "question", "reason"))
            or type(question.get("required")) is not bool
            or type(question.get("allowFreeText")) is not bool
            or type(question.get("suggestions")) is not list
        ):
            return None
        if not question["id"] or question["id"] in seen or not question["question"].strip():
            return None
        seen.add(question["id"])
        options = question["suggestions"]
        if any(
            type(option) is not dict
            or not all(type(option.get(key)) is str for key in ("id", "label"))
            for option in options
        ):
            return None
        if any(not option["id"] or not option["label"].strip() for option in options) or len(
            {option["id"] for option in options}
        ) != len(options):
            return None
        projected.append(
            {
                key: question[key]
                for key in ("id", "question", "reason", "required", "allowFreeText")
            }
            | {"suggestions": [{key: option[key] for key in ("id", "label")} for option in options]}
        )
    material = {}
    for key in (
        "requestedScope",
        "deliverableScope",
        "suggestedAlternatives",
        "assumptions",
        "limitations",
        "omittedScope",
        "unsupportedScope",
    ):
        if key in details:
            if not strings(details[key]):
                return None
            material[key] = details[key]
    return {
        "receipt_id": str(reference),
        "context_version": version,
        "admission": "NOT_ADMITTED",
        "ai_state": value["state"],
        "confirmation_summary": {key: summary[key] for key in ("objective", *groups)},
        "interpretation": material,
        "questions": projected,
        "unresolved_ambiguities": ambiguities,
    }


class ReadOnlyNativeIndex:
    """Read scoped immutable receipts in the caller's existing transaction."""

    def __init__(self, db: Any) -> None:
        self.db = db

    def load(self, scope: Any, reference: UUID) -> Any:
        from sqlalchemy import select

        from .native_response_archive import NativeResponseReceipt
        from .native_response_index import NativeResponseReceiptRow

        row = self.db.scalar(
            select(NativeResponseReceiptRow).where(
                NativeResponseReceiptRow.id == reference,
                NativeResponseReceiptRow.operation_id == scope.operation_id,
                NativeResponseReceiptRow.company_id == scope.company_id,
                NativeResponseReceiptRow.case_id == scope.case_id,
                NativeResponseReceiptRow.context_version == scope.context_version,
            )
        )
        if row is None:
            raise SemanticValidationFailed()
        return NativeResponseReceipt(row.id, scope, row.digest, row.size, row.storage_key)

    def commit(self, receipt: Any) -> None:
        raise SemanticValidationFailed()


def goal_analysis_request(
    db: Any,
    case: Any,
    objects: Any,
    service: Any,
) -> Any:
    """The actual no-file native input, shared by send and later revalidation."""
    from .model_provider import ProviderRequest
    from .native_response_archive import NativeResponseArchive, NativeResponseScope

    current_items = [*db.evidence_items(case.id), *db.reference_materials(case.id)]
    if any(row.request_version_id == case.current_request_version_id for row in current_items):
        raise SemanticValidationFailed()
    if any(row.company_id != case.company_id or row.case_id != case.id for row in current_items):
        raise SemanticValidationFailed()
    snapshot = service.tenant_settings
    if snapshot is None or snapshot.company_id != case.company_id:
        raise SemanticValidationFailed()
    policy = snapshot.settings
    prior_answers = []
    for prior in prior_analysis_receipts(
        db, case.company_id, case.id, case.semantic_context_version
    ):
        raw = NativeResponseArchive(
            NativeResponseScope(
                case.company_id,
                case.id,
                prior.context_version,
                prior.operation_id,
            ),
            objects,
            ReadOnlyNativeIndex(db),
        ).read(prior.id)
        prior_answers.append(
            {
                "receiptId": str(prior.id),
                "contextVersion": prior.context_version,
                "assistantTexts": assistant_texts(raw),
            }
        )
    return ProviderRequest(
        task="REQUIREMENT_ANALYSIS",
        system_prompt="",
        output_schema={},
        requires_vision=False,
        context={
            "materialContext": goal_only_context(db, case),
            "priorAgentAnswers": prior_answers,
            "clarificationState": service.clarification_state(db, case.id),
            "dataStructure": None,
            "caseFiles": [],
            "fileDelivery": {
                "transport": "NO_ATTACHED_FILES",
                "sampled": False,
                "serviceFileUploaded": False,
                "processingVerified": False,
            },
            "clarificationPolicy": {
                "maxRounds": policy.max_clarification_rounds_per_cycle,
                "maxQuestionsPerRound": policy.clarification_policy.max_questions_per_round,
                "maxAnswerCharacters": policy.clarification_policy.max_answer_characters,
            },
            "generationPolicy": policy.generation_policy.model_dump(by_alias=True),
        },
    )


GOAL_INTERPRETATION = "APBRA_NATIVE_GOAL_INTERPRETATION"
GOAL_CONFIRMATION = "APBRA_NATIVE_GOAL_CONFIRMED_REQUIREMENTS"


def native_goal_session(
    db: Any, case: Any, objects: Any, service: Any, reference: UUID
) -> dict[str, Any]:
    """Re-prove the real immutable analysis and exact current input; zero AI calls."""
    from sqlalchemy import select

    from .native_contracts import SavedNativeContract, digest
    from .native_response_archive import NativeResponseArchive, NativeResponseScope
    from .native_response_index import (
        NativeContractBindingRow,
        NativeReceiveCommandRow,
        NativeResponseReceiptRow,
    )

    snapshot = service.tenant_settings
    if snapshot is None or snapshot.company_id != case.company_id:
        raise SemanticValidationFailed()
    profile = snapshot.settings.provider_profile
    if profile is None or profile.protocol != "FOUNDRY_AGENT_RESPONSES":
        raise SemanticValidationFailed()
    row = db.scalar(
        select(NativeResponseReceiptRow).where(
            NativeResponseReceiptRow.id == reference,
            NativeResponseReceiptRow.company_id == case.company_id,
            NativeResponseReceiptRow.case_id == case.id,
            NativeResponseReceiptRow.context_version == case.semantic_context_version,
        )
    )
    if row is None:
        raise SemanticValidationFailed()
    command = db.get(NativeReceiveCommandRow, row.operation_id)
    binding = db.get(NativeContractBindingRow, row.operation_id)
    if (
        command is None
        or binding is None
        or any(
            item.company_id != case.company_id
            or item.case_id != case.id
            or item.context_version != case.semantic_context_version
            for item in (command, binding)
        )
        or command.state != "RECEIVED"
        or command.http_status != 200
        or command.provider_status != "completed"
        or command.settings_id != snapshot.id
        or binding.task != "REQUIREMENT_ANALYSIS"
        or binding.contract_id is not None
        or binding.profile_digest != digest(profile.model_dump())
    ):
        raise SemanticValidationFailed()
    request = goal_analysis_request(db, case, objects, service)
    if binding.input_digest != digest(
        {"task": request.task, "context": request.context, "images": []}
    ):
        raise SemanticValidationFailed()
    raw = NativeResponseArchive(
        NativeResponseScope(
            case.company_id,
            case.id,
            row.context_version,
            row.operation_id,
        ),
        objects,
        ReadOnlyNativeIndex(db),
    ).read(row.id)
    candidate = SavedNativeContract(
        raw,
        profile=profile,
        task="REQUIREMENT_ANALYSIS",
        receipt_id=row.id,
        metadata=json.loads(binding.metadata_json),
    )
    projection = analysis_display(candidate.value, row.id, row.context_version)
    if projection is None or projection["ai_state"] != "READY_FOR_CONFIRMATION":
        raise SemanticValidationFailed()
    # Preview-only transport/admission markers are not model understanding.
    # The immutable source and confirmation record bind these identifiers.
    projection = {key: value for key, value in projection.items()
                  if key not in {"admission", "receipt_id", "context_version"}}
    source = {
        "receipt_id": str(row.id),
        "operation_id": str(row.operation_id),
        "receipt_sha256": row.digest,
        "input_digest": binding.input_digest,
        "profile_digest": binding.profile_digest,
    }
    context = json.dumps(
        {
            "kind": "APBRA_NATIVE_GOAL_CONTEXT",
            "settings_id": str(snapshot.id),
            "input_digest": binding.input_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    readiness = json.dumps(
        {
            "kind": "APBRA_NATIVE_GOAL_READINESS",
            "source": source,
            "contextBinding": context,
            "analysis": projection,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "kind": GOAL_INTERPRETATION,
        "format_version": 1,
        "mode": "NATIVE_GOAL_ONLY",
        "source": source,
        "analysisProjection": projection,
        "contextBinding": context,
        "readinessBinding": readiness,
        "state": projection["ai_state"],
        "currentInterpretation": projection["interpretation"],
        "confirmationSummary": projection["confirmation_summary"],
        "rounds": [{"questions": projection["questions"]}],
        "unresolvedAmbiguities": projection["unresolved_ambiguities"],
        "providerProvenance": {
            "sourceReceiptId": str(row.id),
            "profileId": profile.profile_id,
            "modelOrDeployment": profile.model_or_deployment,
        },
    }


def native_goal_confirmation(interpretation: Any, session: dict[str, Any]) -> dict[str, Any]:
    from .native_contracts import digest

    return {
        "kind": GOAL_CONFIRMATION,
        "schema_version": 2,
        "mode": "NATIVE_GOAL_ONLY",
        "sourceInterpretationId": str(interpretation.id),
        "sourceReceiptId": session["source"]["receipt_id"],
        "contextBindingDigest": digest(session["contextBinding"]),
        "readinessBindingDigest": interpretation.readiness_binding_digest,
        "confirmedUnderstanding": session["analysisProjection"],
        "dataStructure": None,
    }
