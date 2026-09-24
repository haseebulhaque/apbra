from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from .authorization import authorized_case_access
from .domain import (
    AccessLevel,
    Actor,
    ApplicationPersistence,
    CaseRecord,
    Conflict,
    EvidenceInvalid,
    EvidenceRecord,
    Forbidden,
    IdempotencyConflict,
    IdentityRecord,
    InvitationInvalid,
    InvitationRecord,
    MembershipRecord,
    RequestVersionRecord,
    Role,
    SemanticValidationFailed,
    StaleVersion,
)
from .evidence import (
    EvidenceError,
    LocalEvidenceStore,
    ParsedEvidence,
    parse_evidence,
    schema_digest,
)
from .semantic_bridge import SemanticBridge


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def request_version_json(row: RequestVersionRecord) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "sequence": row.sequence,
        "request_text": row.request_text,
        "created_at": row.created_at.isoformat(),
    }


def case_json(db: ApplicationPersistence, row: CaseRecord) -> dict[str, Any]:
    current = db.request_version(row.current_request_version_id)
    assert current is not None
    return {
        "id": str(row.id),
        "company_id": str(row.company_id),
        "creator_membership_id": str(row.creator_membership_id),
        "current_request_version_id": str(row.current_request_version_id),
        "version": row.version,
        "semantic_context_version": row.semantic_context_version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "current_request": request_version_json(current),
    }


def qualify_evidence_object(
    objects: LocalEvidenceStore, row: EvidenceRecord
) -> tuple[ParsedEvidence, dict[str, Any]]:
    """Re-prove that retained bytes still match their qualified schema."""
    try:
        content = objects.read(row.storage_key, row.content_digest)
        parsed = parse_evidence(content, row.filename)
        schema = json.loads(row.observed_schema_json)
    except (EvidenceError, json.JSONDecodeError) as exc:
        raise EvidenceError("Evidence qualification is unavailable.") from exc
    if not isinstance(schema, dict) or (
        parsed.format != row.format
        or not hmac.compare_digest(schema_digest(schema), row.schema_digest)
        or not hmac.compare_digest(schema_digest(parsed.observed_schema), row.schema_digest)
        or parsed.observed_schema != schema
    ):
        raise EvidenceError("Evidence qualification no longer matches the retained object.")
    return parsed, schema


class CaseService:
    def create(
        self, db: object, actor: Actor, request_text: str, command_key: str
    ) -> tuple[dict[str, Any], bool]:
        store = cast(ApplicationPersistence, db)
        text = request_text.strip()
        if not text:
            raise Conflict()
        payload_digest = canonical_payload({"request_text": text})
        store.lock_create_case(actor, command_key)
        existing = store.idempotency_record(actor, "CREATE_CASE", command_key)
        if existing:
            if not hmac.compare_digest(existing.payload_digest, payload_digest):
                raise IdempotencyConflict()
            case, _ = authorized_case_access(store, actor, existing.resource_id)
            return case_json(store, case), False

        case = store.create_case(actor, text, command_key, payload_digest)
        return case_json(store, case), True

    def list_cases(self, db: object, actor: Actor) -> list[dict[str, Any]]:
        store = cast(ApplicationPersistence, db)
        return [case_json(store, row) for row in store.accessible_cases(actor)]

    def get(self, db: object, actor: Actor, case_id: UUID) -> dict[str, Any]:
        store = cast(ApplicationPersistence, db)
        row, _ = authorized_case_access(db, actor, case_id)
        return case_json(store, row)

    def versions(self, db: object, actor: Actor, case_id: UUID) -> list[dict[str, Any]]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(db, actor, case_id)
        return [request_version_json(row) for row in store.case_versions(case_id)]

    def update(
        self, db: object, actor: Actor, case_id: UUID, request_text: str, expected_version: int
    ) -> dict[str, Any]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(db, actor, case_id, require_edit=True)
        row = store.locked_case(case_id)
        assert row is not None
        if row.version != expected_version:
            raise StaleVersion()
        text = request_text.strip()
        if not text:
            raise Conflict()
        return case_json(store, store.update_case_request(row, actor, text))

    def list_access(self, db: object, actor: Actor, case_id: UUID) -> list[dict[str, Any]]:
        store = cast(ApplicationPersistence, db)
        _, actor_access = authorized_case_access(store, actor, case_id)
        if actor_access.access_level != AccessLevel.OWNER:
            raise Forbidden()
        return [
            {
                "membership_id": str(membership.id),
                "display_name": identity.display_name,
                "subject": identity.subject,
                "access_level": access.access_level,
                "active": access.active,
            }
            for access, membership, identity in store.case_access_entries(case_id)
        ]

    def grant_access(
        self,
        db: object,
        actor: Actor,
        case_id: UUID,
        membership_id: UUID,
        access_level: AccessLevel,
    ) -> None:
        store = cast(ApplicationPersistence, db)
        _, actor_access = authorized_case_access(store, actor, case_id)
        if actor_access.access_level != AccessLevel.OWNER or access_level == AccessLevel.OWNER:
            raise Forbidden()
        membership = store.lock_company_membership(actor.company_id, membership_id)
        if membership is None or not membership.active:
            raise Forbidden()
        store.grant_case_access(actor, case_id, membership, access_level)

    def revoke_access(self, db: object, actor: Actor, case_id: UUID, membership_id: UUID) -> None:
        store = cast(ApplicationPersistence, db)
        _, actor_access = authorized_case_access(store, actor, case_id)
        if actor_access.access_level != AccessLevel.OWNER or membership_id == actor.membership_id:
            raise Forbidden()
        access = store.lock_case_access(case_id, membership_id)
        if access is None or access.company_id != actor.company_id:
            raise Forbidden()
        if access.active:
            access.active = False
            access.revoked_at = datetime.now(UTC)
            store.add_audit(
                actor,
                "CASE_ACCESS_REVOKED",
                "REPORTING_CASE",
                case_id,
                json.dumps(
                    {"membership_id": str(membership_id)},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )


class InvitationService:
    def issue(
        self,
        db: object,
        actor: Actor,
        invited_subject: str,
        role: Role,
        expires_in_days: int,
    ) -> tuple[InvitationRecord, str]:
        if not actor.role.can_invite:
            raise Forbidden()
        if role == Role.COMPANY_OWNER:
            raise Forbidden()
        subject = invited_subject.strip()
        if not subject:
            raise Conflict()
        raw_token = secrets.token_urlsafe(48)
        row = cast(ApplicationPersistence, db).create_invitation(
            actor,
            subject,
            role,
            sha256_text(raw_token),
            datetime.now(UTC) + timedelta(days=expires_in_days),
        )
        return row, raw_token

    def inspect(self, db: object, raw_token: str) -> InvitationRecord:
        row = cast(ApplicationPersistence, db).invitation(sha256_text(raw_token))
        if (
            row is None
            or row.revoked_at is not None
            or row.consumed_at is not None
            or row.expires_at <= datetime.now(UTC)
        ):
            raise InvitationInvalid()
        return row

    def accept(self, db: object, identity: IdentityRecord, raw_token: str) -> MembershipRecord:
        store = cast(ApplicationPersistence, db)
        digest = sha256_text(raw_token)
        row = store.invitation(digest, lock=True)
        if row is None or not hmac.compare_digest(row.token_digest, digest):
            raise InvitationInvalid()
        if row.consumed_at is not None:
            existing = store.membership(row.company_id, identity.id)
            if row.consumed_by_identity_id == identity.id and existing is not None:
                return existing
            raise InvitationInvalid()
        if row.revoked_at is not None or row.expires_at <= datetime.now(UTC):
            raise InvitationInvalid()
        if row.invited_subject != identity.subject or row.invited_issuer != identity.issuer:
            raise InvitationInvalid()
        store.lock_identity_for_membership(identity.id)
        active_membership = store.active_identity_membership(identity.id)
        if active_membership is not None and active_membership.company_id != row.company_id:
            raise Conflict()
        existing = store.membership(row.company_id, identity.id)
        if existing is not None:
            raise Conflict()
        return store.accept_invitation(row, identity)

    def revoke(self, db: object, actor: Actor, invitation_id: UUID) -> None:
        if not actor.role.can_invite:
            raise Forbidden()
        store = cast(ApplicationPersistence, db)
        row = store.lock_company_invitation(actor.company_id, invitation_id)
        if row is None or row.consumed_at is not None:
            raise InvitationInvalid()
        row.revoked_at = datetime.now(UTC)
        store.add_audit(actor, "INVITATION_REVOKED", "INVITATION", row.id)


class MembershipService:
    def list(self, db: object, actor: Actor) -> list[dict[str, Any]]:
        if not actor.role.can_invite:
            raise Forbidden()
        rows = cast(ApplicationPersistence, db).company_memberships(actor.company_id)
        return [
            {
                "id": str(membership.id),
                "display_name": identity.display_name,
                "subject": identity.subject,
                "role": membership.role,
                "active": membership.active,
            }
            for membership, identity in rows
        ]

    def deactivate(self, db: object, actor: Actor, membership_id: UUID) -> None:
        if not actor.role.can_invite or membership_id == actor.membership_id:
            raise Forbidden()
        store = cast(ApplicationPersistence, db)
        membership = store.lock_company_membership(actor.company_id, membership_id)
        if membership is None:
            raise Forbidden()
        if membership.active:
            membership.active = False
            store.add_audit(actor, "MEMBERSHIP_DEACTIVATED", "MEMBERSHIP", membership.id)


class ConversationService:
    _CLIENT_EVENT_KINDS = {"USER_MESSAGE", "RAW_ANSWER", "CORRECTION"}

    @staticmethod
    def _validated_answer(
        store: ApplicationPersistence, case: CaseRecord, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], str | None]:
        if set(payload) - {
            "questionId",
            "rawAnswer",
            "suggestionId",
            "decision",
            "interpretationId",
        }:
            raise Conflict()
        question_id = payload.get("questionId")
        interpretation_id = payload.get("interpretationId")
        raw_answer = payload.get("rawAnswer")
        suggestion_id = payload.get("suggestionId", "")
        decision = payload.get("decision", "FREE_TEXT")
        if (
            not isinstance(question_id, str)
            or not question_id.strip()
            or not isinstance(interpretation_id, str)
            or not interpretation_id.strip()
            or not isinstance(raw_answer, str)
            or not raw_answer.strip()
            or len(raw_answer) > 500
            or not isinstance(suggestion_id, str)
            or decision not in {"ACCEPT", "DECLINE", "FREE_TEXT"}
        ):
            raise Conflict()
        interpretation = store.latest_interpretation(case.id)
        if (
            interpretation is None
            or interpretation_id != str(interpretation.id)
            or interpretation.context_version != case.semantic_context_version
            or interpretation.state != "NEEDS_CLARIFICATION"
        ):
            raise StaleVersion()
        session = json.loads(interpretation.session_json)
        rounds = session.get("rounds")
        questions = rounds[-1].get("questions") if isinstance(rounds, list) and rounds else None
        if not isinstance(questions, list):
            raise Conflict()
        question = next(
            (
                item
                for item in questions
                if isinstance(item, dict) and item.get("id") == question_id
            ),
            None,
        )
        if question is None:
            raise Conflict()
        suggestions = question.get("suggestions")
        suggestions = suggestions if isinstance(suggestions, list) else []
        suggestion = next(
            (
                item
                for item in suggestions
                if isinstance(item, dict) and item.get("id") == suggestion_id
            ),
            None,
        )
        if decision == "ACCEPT" and suggestion is None:
            raise Conflict()
        if decision != "ACCEPT" and suggestion_id:
            raise Conflict()
        submitted_text = raw_answer
        if decision == "ACCEPT":
            label = suggestion.get("label") if suggestion is not None else None
            if not isinstance(label, str) or not label.strip():
                raise Conflict()
            raw_answer = label
        elif decision == "DECLINE":
            raw_answer = "Declined the proposed supported choices."
        exact = {
            "questionId": question_id,
            "rawAnswer": raw_answer,
            "suggestionId": suggestion_id,
            "decision": decision,
            "submittedText": submitted_text,
            "requestVersionId": str(case.current_request_version_id),
            "interpretationId": str(interpretation.id),
            "interpretationContextVersion": interpretation.context_version,
        }
        return exact, str(suggestion.get("label")) if suggestion is not None else None

    def list_events(self, db: object, actor: Actor, case_id: UUID) -> list[dict[str, Any]]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(store, actor, case_id)
        return [
            {
                "id": str(row.id),
                "sequence": row.sequence,
                "kind": row.kind,
                "payload": json.loads(row.payload_json),
                "created_at": row.created_at.isoformat(),
            }
            for row in store.conversation_events(case_id)
        ]

    def append_event(
        self,
        db: object,
        actor: Actor,
        case_id: UUID,
        *,
        kind: str,
        payload: dict[str, Any],
        expected_context_version: int,
        command_key: str,
    ) -> dict[str, Any]:
        if kind not in self._CLIENT_EVENT_KINDS:
            raise Forbidden()
        store = cast(ApplicationPersistence, db)
        authorized_case_access(store, actor, case_id, require_edit=True)
        if kind == "RAW_ANSWER":
            payload = {
                **payload,
                "suggestionId": payload.get("suggestionId", ""),
                "decision": payload.get("decision", "FREE_TEXT"),
            }
        retry_digest = canonical_payload({"kind": kind, "payload": payload})
        # Serialize command lookup and creation with all other case mutations.
        # A concurrent retry must observe the committed command rather than
        # falling through to a stale-context failure.
        case = store.locked_case(case_id)
        existing = store.conversation_event_by_command(case_id, actor.membership_id, command_key)
        if existing is not None:
            if not hmac.compare_digest(existing.payload_digest, retry_digest):
                raise IdempotencyConflict()
            current = store.locked_case(case_id)
            assert current is not None
            return {
                "id": str(existing.id),
                "sequence": existing.sequence,
                "kind": existing.kind,
                "payload": json.loads(existing.payload_json),
                "created_at": existing.created_at.isoformat(),
                "semantic_context_version": current.semantic_context_version,
            }
        if case is None or case.semantic_context_version != expected_context_version:
            raise StaleVersion()
        alternative_label: str | None = None
        if kind == "RAW_ANSWER":
            payload, alternative_label = self._validated_answer(store, case, payload)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if len(encoded) > 20_000:
            raise Conflict()
        # The command identity is bound to the normalized client command, not
        # to server-enriched provenance fields. Exact transport retries must
        # compare against the same digest that was persisted initially.
        payload_digest = retry_digest
        row = store.append_conversation_event(
            actor, case_id, kind, encoded, command_key, payload_digest
        )
        if kind == "RAW_ANSWER" and payload.get("decision") in {"ACCEPT", "DECLINE"}:
            decision_kind = (
                "ALTERNATIVE_ACCEPTED"
                if payload["decision"] == "ACCEPT"
                else "ALTERNATIVE_DECLINED"
            )
            decision_payload = {
                "questionId": payload["questionId"],
                "suggestionId": payload["suggestionId"],
                "label": alternative_label or "Supported choice declined",
                "requestVersionId": payload["requestVersionId"],
                "interpretationId": payload["interpretationId"],
            }
            store.append_conversation_event(
                actor,
                case_id,
                decision_kind,
                json.dumps(decision_payload, sort_keys=True, separators=(",", ":")),
                f"{command_key}:decision",
                canonical_payload({"kind": decision_kind, "payload": decision_payload}),
            )
        store.advance_semantic_context(case)
        store.add_audit(actor, "CONVERSATION_EVENT_ADDED", "REPORTING_CASE", case_id)
        return {
            "id": str(row.id),
            "sequence": row.sequence,
            "kind": row.kind,
            "payload": payload,
            "created_at": row.created_at.isoformat(),
            "semantic_context_version": case.semantic_context_version,
        }


class EvidenceService:
    def __init__(self, objects: LocalEvidenceStore) -> None:
        self.objects = objects

    @staticmethod
    def _json(row: Any) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "request_version_id": str(row.request_version_id),
            "filename": row.filename,
            "format": row.format,
            "content_digest": row.content_digest,
            "schema_digest": row.schema_digest,
            "observed_schema": json.loads(row.observed_schema_json),
            "created_at": row.created_at.isoformat(),
        }

    def list(self, db: object, actor: Actor, case_id: UUID) -> list[dict[str, Any]]:
        store = cast(ApplicationPersistence, db)
        case, _ = authorized_case_access(store, actor, case_id)
        qualified: list[dict[str, Any]] = []
        for row in store.evidence_items(case_id):
            if row.request_version_id != case.current_request_version_id:
                continue
            try:
                qualify_evidence_object(self.objects, row)
            except EvidenceError:
                continue
            qualified.append(self._json(row))
        return qualified

    def add(
        self,
        db: object,
        actor: Actor,
        case_id: UUID,
        *,
        filename: str,
        content: bytes,
        expected_context_version: int,
    ) -> tuple[dict[str, Any], str | None]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(store, actor, case_id, require_edit=True)
        case = store.locked_case(case_id)
        if case is None or case.semantic_context_version != expected_context_version:
            raise StaleVersion()
        try:
            parsed = parse_evidence(content, filename)
        except EvidenceError as exc:
            raise EvidenceInvalid() from exc
        digest = hashlib.sha256(content).hexdigest()
        duplicate = store.evidence_by_digest(case_id, case.current_request_version_id, digest)
        if duplicate is not None:
            try:
                qualify_evidence_object(self.objects, duplicate)
            except EvidenceError:
                self.objects.restore(duplicate.storage_key, content, duplicate.content_digest)
                store.add_audit(actor, "EVIDENCE_OBJECT_RESTORED", "REPORTING_CASE", case_id)
            result = self._json(duplicate)
            result["semantic_context_version"] = case.semantic_context_version
            return result, None
        storage_key, stored_digest = self.objects.write(actor.company_id, case_id, content)
        assert hmac.compare_digest(digest, stored_digest)
        try:
            schema_json = json.dumps(parsed.observed_schema, sort_keys=True, separators=(",", ":"))
            row = store.add_evidence(
                actor,
                case_id,
                case.current_request_version_id,
                filename,
                parsed.format,
                stored_digest,
                storage_key,
                schema_json,
                schema_digest(parsed.observed_schema),
            )
            store.advance_semantic_context(case)
            store.add_audit(actor, "EVIDENCE_ADDED", "REPORTING_CASE", case_id)
        except Exception:
            self.objects.delete(storage_key)
            raise
        result = self._json(row)
        result["semantic_context_version"] = case.semantic_context_version
        return result, storage_key


class AcceptanceService:
    def __init__(self, bridge: SemanticBridge, objects: LocalEvidenceStore) -> None:
        self.bridge = bridge
        self.objects = objects

    def _current_context(
        self, store: ApplicationPersistence, case: CaseRecord
    ) -> tuple[dict[str, Any], str, list[EvidenceRecord]]:
        request = store.request_version(case.current_request_version_id)
        if request is None:
            raise SemanticValidationFailed()
        evidence = [
            row
            for row in store.evidence_items(case.id)
            if row.request_version_id == case.current_request_version_id
        ]
        if not evidence:
            raise SemanticValidationFailed()
        tables: list[dict[str, Any]] = []
        names: set[str] = set()
        for row in evidence:
            try:
                parsed, schema = qualify_evidence_object(self.objects, row)
            except EvidenceError as exc:
                raise SemanticValidationFailed() from exc
            for table in schema.get("tables", []):
                name = table.get("name") if isinstance(table, dict) else None
                if not isinstance(name, str) or not name or name in names:
                    raise SemanticValidationFailed()
                names.add(name)
                tables.append(table)
        structure = {
            "kind": "REQUEST_DATA_STRUCTURE",
            "fileName": "qualified-case-evidence",
            "format": "XLSX" if any(row.format == "XLSX" for row in evidence) else "CSV",
            "tables": tables,
            "relationships": [],
            "parsedAt": max(row.created_at for row in evidence).isoformat(),
        }
        binding = json.dumps(
            {
                "caseId": str(case.id),
                "requestVersionId": str(case.current_request_version_id),
                "requestText": request.request_text,
                "semanticContextVersion": case.semantic_context_version,
                "conversation": [
                    {
                        "id": str(row.id),
                        "sequence": row.sequence,
                        "kind": row.kind,
                        "payload": json.loads(row.payload_json),
                    }
                    for row in store.conversation_events(case.id)
                ],
                "evidence": [
                    {
                        "id": str(row.id),
                        "requestVersionId": str(row.request_version_id),
                        "contentDigest": row.content_digest,
                        "schemaDigest": row.schema_digest,
                    }
                    for row in evidence
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return structure, binding, evidence

    def create_interpretation(
        self,
        db: object,
        actor: Actor,
        case_id: UUID,
        *,
        expected_context_version: int,
    ) -> dict[str, Any]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(store, actor, case_id, require_edit=True)
        case = store.locked_case(case_id)
        if case is None or case.semantic_context_version != expected_context_version:
            raise StaleVersion()
        current_request = store.request_version(case.current_request_version_id)
        if current_request is None:
            raise SemanticValidationFailed()
        # Re-qualify the retained evidence object before reusing even an
        # idempotently prepared interpretation. Persisted metadata alone is
        # not proof that the protected bytes remain available and intact.
        schema, context_binding, evidence = self._current_context(store, case)
        existing = store.interpretation_for_context(case_id, case.semantic_context_version)
        if existing is not None:
            existing_session = json.loads(existing.session_json)
            return {
                "id": str(existing.id),
                "state": existing.state,
                "current": True,
                "context_version": existing.context_version,
                "confirmation_summary": json.loads(existing.confirmation_summary_json),
                "interpretation": existing_session.get("currentInterpretation"),
                "questions": existing_session.get("rounds", [])[-1].get("questions", [])
                if existing_session.get("rounds")
                else [],
                "unresolved_ambiguities": existing_session.get("unresolvedAmbiguities", []),
                "simulation": "LOCAL_DETERMINISTIC_NO_MODEL_CALL",
            }
        session = self.bridge.simulate(
            session_id=f"case-{case.id}-context-{case.semantic_context_version}",
            original_request=current_request.request_text,
            context_binding=context_binding,
            analysed_at=datetime.now(UTC),
            data_structure=schema,
        ).session
        state = session.get("state")
        if state not in {"NEEDS_CLARIFICATION", "READY_FOR_CONFIRMATION"}:
            raise SemanticValidationFailed()
        confirmation_summary: dict[str, Any]
        if state == "READY_FOR_CONFIRMATION":
            readiness = self.bridge.readiness(session, schema)
            confirmation_summary = readiness.confirmation_summary
            readiness_digest = sha256_text(readiness.readiness_binding)
        else:
            raw_summary = session.get("confirmationSummary")
            if not isinstance(raw_summary, dict):
                raise SemanticValidationFailed()
            confirmation_summary = raw_summary
            readiness_digest = sha256_text("")
        row = store.add_interpretation(
            actor,
            case_id,
            case.current_request_version_id,
            evidence[-1].id,
            case.semantic_context_version,
            json.dumps(session, sort_keys=True, separators=(",", ":")),
            json.dumps(confirmation_summary, sort_keys=True, separators=(",", ":")),
            readiness_digest,
            state,
        )
        store.add_audit(
            actor,
            (
                "INTERPRETATION_READY"
                if state == "READY_FOR_CONFIRMATION"
                else "CLARIFICATION_REQUIRED"
            ),
            "REPORTING_CASE",
            case_id,
        )
        return {
            "id": str(row.id),
            "state": state,
            "current": True,
            "context_version": row.context_version,
            "confirmation_summary": confirmation_summary,
            "interpretation": session.get("currentInterpretation"),
            "questions": session.get("rounds", [])[-1].get("questions", [])
            if session.get("rounds")
            else [],
            "unresolved_ambiguities": session.get("unresolvedAmbiguities", []),
            "simulation": "LOCAL_DETERMINISTIC_NO_MODEL_CALL",
        }

    def state(self, db: object, actor: Actor, case_id: UUID) -> dict[str, Any]:
        store = cast(ApplicationPersistence, db)
        case, _ = authorized_case_access(store, actor, case_id)
        row = store.latest_interpretation(case_id)
        if row is None:
            return {"interpretation": None, "confirmed_contract": None}
        contract = store.confirmed_contract(row.id)
        session = json.loads(row.session_json)
        current = (
            row.context_version == case.semantic_context_version
            and row.request_version_id == case.current_request_version_id
        )
        if current:
            try:
                self._current_context(store, case)
            except SemanticValidationFailed:
                current = False
        return {
            "interpretation": {
                "id": str(row.id),
                "state": "CONFIRMED" if contract is not None and current else row.state,
                "current": current,
                "context_version": row.context_version,
                "confirmation_summary": json.loads(row.confirmation_summary_json),
                "interpretation": session.get("currentInterpretation"),
                "questions": session.get("rounds", [])[-1].get("questions", [])
                if session.get("rounds")
                else [],
                "unresolved_ambiguities": session.get("unresolvedAmbiguities", []),
                "simulation": "LOCAL_DETERMINISTIC_NO_MODEL_CALL",
            },
            "confirmed_contract": (
                {
                    "id": str(contract.id),
                    "interpretation_id": str(contract.interpretation_id),
                    "schema_version": contract.schema_version,
                    "accepted_at": contract.accepted_at.isoformat(),
                    "contract": json.loads(contract.contract_json),
                    "current": current,
                }
                if contract is not None
                else None
            ),
        }

    def confirm(
        self,
        db: object,
        actor: Actor,
        case_id: UUID,
        *,
        interpretation_id: UUID,
        expected_context_version: int,
    ) -> dict[str, Any]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(store, actor, case_id, require_edit=True)
        case = store.locked_case(case_id)
        if case is None or case.semantic_context_version != expected_context_version:
            raise StaleVersion()
        interpretation = store.interpretation(case_id, interpretation_id)
        latest = store.latest_interpretation(case_id)
        if (
            interpretation is None
            or latest is None
            or latest.id != interpretation.id
            or interpretation.state != "READY_FOR_CONFIRMATION"
            or interpretation.context_version != case.semantic_context_version
            or interpretation.request_version_id != case.current_request_version_id
            or interpretation.evidence_id is None
        ):
            raise StaleVersion()
        existing = store.confirmed_contract(interpretation.id)
        if existing is not None:
            return {
                "id": str(existing.id),
                "interpretation_id": str(existing.interpretation_id),
                "schema_version": existing.schema_version,
                "accepted_at": existing.accepted_at.isoformat(),
                "contract": json.loads(existing.contract_json),
                "current": True,
            }
        schema, current_context_binding, _evidence = self._current_context(store, case)
        session = json.loads(interpretation.session_json)
        context_binding = session.get("contextBinding")
        readiness_binding = session.get("readinessBinding")
        if (
            not isinstance(context_binding, str)
            or not isinstance(readiness_binding, str)
            or not hmac.compare_digest(
                sha256_text(readiness_binding), interpretation.readiness_binding_digest
            )
            or not hmac.compare_digest(context_binding, current_context_binding)
        ):
            raise SemanticValidationFailed()
        result = self.bridge.confirm(
            session,
            schema,
            confirmed_at=datetime.now(UTC),
            readiness_binding=readiness_binding,
            context_binding=context_binding,
        )
        contract = store.accept_interpretation(
            actor,
            interpretation,
            json.dumps(result.contract, sort_keys=True, separators=(",", ":")),
        )
        return {
            "id": str(contract.id),
            "interpretation_id": str(contract.interpretation_id),
            "schema_version": contract.schema_version,
            "accepted_at": contract.accepted_at.isoformat(),
            "contract": result.contract,
            "current": True,
        }
