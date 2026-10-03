from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from .authorization import authorized_case_access
from .config import ClarificationPolicy, UploadPolicy
from .domain import (
    AccessLevel,
    Actor,
    ApplicationPersistence,
    CaseRecord,
    CompanyCreationNotAvailable,
    CompanyNameInvalid,
    CompanyRecord,
    ConfigurationUnavailable,
    Conflict,
    EvidenceInvalid,
    EvidenceRecord,
    Forbidden,
    IdempotencyConflict,
    IdentityRecord,
    IntelligentAnalysisUnavailable,
    InterpretationRecord,
    InvitationInvalid,
    InvitationRecord,
    LastOwnerRequired,
    MembershipRecord,
    ProfileInvalid,
    RequestVersionRecord,
    Role,
    SemanticValidationFailed,
    SessionRecord,
    StaleVersion,
)
from .evidence import (
    EvidenceError,
    LocalEvidenceStore,
    ParsedEvidence,
    parse_evidence,
    schema_digest,
)
from .model_provider import (
    ModelProvider,
    ProviderCallError,
    ProviderRequest,
    requirement_analysis_schema,
)
from .semantic_bridge import SemanticBridge
from .tenant_settings import (
    TenantSettingsSnapshot,
    interpretation_material_digest,
    settings_version,
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _safe_display_name(value: str, *, company: bool) -> str:
    name = unicodedata.normalize("NFC", value.strip())
    if not name or len(name) > 200 or any(
        unicodedata.category(character) in {"Cc", "Cf"} for character in name
    ):
        raise CompanyNameInvalid() if company else ProfileInvalid()
    return name


def _company_creation_json(company: CompanyRecord, membership: MembershipRecord) -> dict[str, Any]:
    return {
        "company": {"id": str(company.id), "name": company.name},
        "membership": {"id": str(membership.id), "role": membership.role},
    }


class CompanyService:
    """Bootstrap one company from the server-validated APBRA identity only."""

    def create(
        self,
        db: object,
        session: SessionRecord,
        identity: IdentityRecord,
        name: str,
        command_key: str,
    ) -> tuple[dict[str, Any], bool]:
        store = cast(ApplicationPersistence, db)
        canonical_name = _safe_display_name(name, company=True)
        payload_digest = canonical_payload({"name": canonical_name})
        # A row lock serializes both same-key replays and distinct first-company
        # requests from the same identity across API processes.
        store.lock_identity_for_membership(identity.id)
        locked_session = store.lock_active_session_for_creation(
            session.id, identity.id, datetime.now(UTC)
        )
        existing = store.company_creation_command(identity.id, command_key)
        if existing is not None:
            if not hmac.compare_digest(existing.payload_digest, payload_digest):
                raise IdempotencyConflict()
            actor = store.active_actor(existing.membership_id, identity.id)
            company = store.company(existing.company_id)
            membership = store.membership(existing.company_id, identity.id)
            if (
                actor is None
                or company is None
                or membership is None
                or not membership.active
                or membership.id != existing.membership_id
                or actor.company_id != company.id
            ):
                raise CompanyCreationNotAvailable()
            locked_session.membership_id = actor.membership_id
            return _company_creation_json(company, membership), False

        if store.active_identity_membership(identity.id) is not None:
            raise CompanyCreationNotAvailable()
        if store.eligible_invitation_for_identity(identity, datetime.now(UTC)):
            raise CompanyCreationNotAvailable()
        company, membership = store.create_company_with_owner(
            identity, locked_session, canonical_name, command_key, payload_digest
        )
        return _company_creation_json(company, membership), True


class ProfileService:
    def update(self, db: object, identity: IdentityRecord, display_name: str) -> IdentityRecord:
        name = _safe_display_name(display_name, company=False)
        return cast(ApplicationPersistence, db).update_identity_display_name(identity.id, name)


def request_display_title(request_text: str) -> str:
    """Use user-owned request text until an eligible model design supplies a title."""
    return request_text.strip()[:160]


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
        "report_title": row.report_title,
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

        case = store.create_case(
            actor, text, command_key, payload_digest, request_display_title(text)
        )
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
        store = cast(ApplicationPersistence, db)
        store.lock_company_for_membership_management(actor.company_id)
        current_actor = store.active_actor(actor.membership_id, actor.identity_id, lock=True)
        if current_actor is None or not current_actor.role.can_invite:
            raise Forbidden()
        if role == Role.COMPANY_OWNER:
            raise Forbidden()
        subject = invited_subject.strip()
        if not subject:
            raise Conflict()
        raw_token = secrets.token_urlsafe(48)
        row = store.create_invitation(
            current_actor,
            subject,
            role,
            sha256_text(raw_token),
            datetime.now(UTC) + timedelta(days=expires_in_days),
        )
        return row, raw_token

    def inspect(self, db: object, raw_token: str) -> InvitationRecord:
        store = cast(ApplicationPersistence, db)
        row = store.invitation(sha256_text(raw_token))
        if (
            row is None
            or row.revoked_at is not None
            or row.consumed_at is not None
            or row.expires_at <= datetime.now(UTC)
            or store.active_company(row.company_id) is None
        ):
            raise InvitationInvalid()
        return row

    def accept(self, db: object, identity: IdentityRecord, raw_token: str) -> MembershipRecord:
        store = cast(ApplicationPersistence, db)
        digest = sha256_text(raw_token)
        # Lock the company before its invitation so issuer revocation and
        # acceptance share a stable order with company-scoped mutations.
        preliminary = store.invitation(digest)
        if preliminary is None or store.active_company(preliminary.company_id, lock=True) is None:
            raise InvitationInvalid()
        row = store.invitation(digest, lock=True)
        if (
            row is None
            or row.company_id != preliminary.company_id
            or not hmac.compare_digest(row.token_digest, digest)
        ):
            raise InvitationInvalid()
        if row.consumed_at is not None:
            existing = store.membership(row.company_id, identity.id)
            if (
                row.consumed_by_identity_id == identity.id
                and existing is not None
                and existing.active
                and store.active_actor(existing.id, identity.id, lock=True) is not None
            ):
                return existing
            raise InvitationInvalid()
        if row.revoked_at is not None or row.expires_at <= datetime.now(UTC):
            raise InvitationInvalid()
        if (
            row.invited_subject != identity.subject
            or row.invited_issuer != identity.issuer
            or row.provider_profile_id != identity.provider_profile_id
        ):
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
        store = cast(ApplicationPersistence, db)
        store.lock_company_for_membership_management(actor.company_id)
        current_actor = store.active_actor(actor.membership_id, actor.identity_id, lock=True)
        if current_actor is None or not current_actor.role.can_invite:
            raise Forbidden()
        row = store.lock_company_invitation(actor.company_id, invitation_id)
        if row is None or row.consumed_at is not None:
            raise InvitationInvalid()
        row.revoked_at = datetime.now(UTC)
        store.add_audit(current_actor, "INVITATION_REVOKED", "INVITATION", row.id)


class MembershipService:
    def list(self, db: object, actor: Actor) -> list[dict[str, Any]]:
        store = cast(ApplicationPersistence, db)
        store.lock_company_for_membership_management(actor.company_id)
        current_actor = store.active_actor(actor.membership_id, actor.identity_id, lock=True)
        if current_actor is None or not current_actor.role.can_invite:
            raise Forbidden()
        rows = store.company_memberships(actor.company_id)
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
        store = cast(ApplicationPersistence, db)
        store.lock_company_for_membership_management(actor.company_id)
        current_actor = store.active_actor(actor.membership_id, actor.identity_id, lock=True)
        if current_actor is None or not current_actor.role.can_invite:
            raise Forbidden()
        membership = store.lock_company_membership(actor.company_id, membership_id)
        if membership is None:
            raise Forbidden()
        if membership_id == actor.membership_id:
            raise Forbidden()
        if membership.role == Role.COMPANY_OWNER.value:
            if current_actor.role != Role.COMPANY_OWNER:
                raise Forbidden()
            if store.active_owner_count(actor.company_id) <= 1:
                raise LastOwnerRequired()
        if membership.active:
            membership.active = False
            store.add_audit(current_actor, "MEMBERSHIP_DEACTIVATED", "MEMBERSHIP", membership.id)

    def change_role(
        self, db: object, actor: Actor, membership_id: UUID, role: Role
    ) -> MembershipRecord:
        if role not in {Role.MEMBER, Role.COMPANY_ADMIN}:
            raise Forbidden()
        store = cast(ApplicationPersistence, db)
        store.lock_company_for_membership_management(actor.company_id)
        current_actor = store.active_actor(actor.membership_id, actor.identity_id, lock=True)
        if current_actor is None or current_actor.role != Role.COMPANY_OWNER:
            raise Forbidden()
        membership = store.lock_company_membership(actor.company_id, membership_id)
        if membership is None or not membership.active:
            raise Forbidden()
        if membership.role == Role.COMPANY_OWNER.value:
            raise LastOwnerRequired()
        if membership.role not in {Role.MEMBER.value, Role.COMPANY_ADMIN.value}:
            raise Forbidden()
        if membership.role != role.value:
            previous = membership.role
            membership.role = role.value
            store.add_audit(
                current_actor,
                "MEMBERSHIP_ROLE_CHANGED",
                "MEMBERSHIP",
                membership.id,
                json.dumps(
                    {"previous_role": previous, "current_role": role.value},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        return membership


class ConversationService:
    _CLIENT_EVENT_KINDS = {"USER_MESSAGE", "RAW_ANSWER", "CORRECTION"}

    def __init__(self, clarification_policy: ClarificationPolicy | None = None) -> None:
        self.clarification_policy = clarification_policy

    def _validated_answer(
        self, store: ApplicationPersistence, case: CaseRecord, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], str | None]:
        if self.clarification_policy is None:
            raise ConfigurationUnavailable()
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
            or len(raw_answer) > self.clarification_policy.max_answer_characters
            or not isinstance(suggestion_id, str)
            or decision not in {"ACCEPT", "DECLINE", "FREE_TEXT"}
        ):
            raise Conflict()
        interpretation = store.latest_interpretation(case.id)
        if (
            interpretation is None
            or interpretation_id != str(interpretation.id)
            or interpretation.context_version != case.semantic_context_version
            or interpretation.state not in {"NEEDS_CLARIFICATION", "READY_FOR_CONFIRMATION"}
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
    def __init__(self, objects: LocalEvidenceStore, policy: UploadPolicy) -> None:
        self.objects = objects
        self.policy = policy

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
        current_items = [
            row
            for row in store.evidence_items(case_id)
            if row.request_version_id == case.current_request_version_id
        ]
        if len(current_items) >= self.policy.max_data_items_per_report:
            raise EvidenceInvalid()
        extension = Path(filename).suffix.upper().lstrip(".")
        if (
            extension not in set(self.policy.data_extensions)
            or len(content) > self.policy.max_file_bytes
        ):
            raise EvidenceInvalid()
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
    def __init__(
        self,
        bridge: SemanticBridge,
        objects: LocalEvidenceStore,
        *,
        reference_objects: LocalEvidenceStore | None = None,
        model_provider: ModelProvider | None = None,
        clarification_policy: ClarificationPolicy | None = None,
        generation_policy: dict[str, Any] | None = None,
        allow_test_simulator: bool = False,
        tenant_settings: TenantSettingsSnapshot | None = None,
    ) -> None:
        self.bridge = bridge
        self.objects = objects
        self.reference_objects = reference_objects
        self.model_provider = model_provider
        self.clarification_policy = clarification_policy
        self.generation_policy = generation_policy
        self.allow_test_simulator = allow_test_simulator
        self.tenant_settings = tenant_settings

    def _settings_still_materially_current(
        self, db: object, interpretation: InterpretationRecord, company_id: UUID
    ) -> bool:
        if self.tenant_settings is None or interpretation.settings_version_id is None:
            # Pre-APBRA-174 historical records remain readable, but new records
            # carry an explicit immutable settings version.
            return True
        historic = settings_version(db, company_id, interpretation.settings_version_id)
        return interpretation_material_digest(historic.settings) == interpretation_material_digest(
            self.tenant_settings.settings
        )

    def clarification_state(self, store: ApplicationPersistence, case_id: UUID) -> dict[str, Any]:
        cycles = store.clarification_cycles(case_id)
        current = cycles[-1] if cycles else None
        overall = sum(item.rounds_used for item in cycles)
        policy = self.tenant_settings.settings if self.tenant_settings else None
        per_limit = policy.max_clarification_rounds_per_cycle if policy else None
        overall_limit = policy.max_clarification_rounds_overall if policy else None
        return {
            "cycle_id": str(current.id) if current else None,
            "cycle_number": current.cycle_number if current else 0,
            "rounds_used_in_cycle": current.rounds_used if current else 0,
            "rounds_used_overall": overall,
            "max_rounds_per_cycle": per_limit,
            "max_rounds_overall": overall_limit,
            "clarification_enabled": policy.clarification_enabled if policy else True,
            "per_cycle_limit_reached": bool(
                current and per_limit is not None and current.rounds_used >= per_limit
            ),
            "overall_limit_reached": bool(overall_limit is not None and overall >= overall_limit),
        }

    def start_refinement_cycle(
        self,
        db: object,
        actor: Actor,
        case_id: UUID,
        *,
        expected_context_version: int,
        command_key: str,
        enhancement: str,
    ) -> dict[str, Any]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(store, actor, case_id, require_edit=True)
        case = store.locked_case(case_id)
        existing = store.clarification_cycle_by_command(case_id, actor.membership_id, command_key)
        if existing is not None:
            assert case is not None
            return {
                "clarification": self.clarification_state(store, case_id),
                "semantic_context_version": case.semantic_context_version,
            }
        if case is None or case.semantic_context_version != expected_context_version:
            raise StaleVersion()
        if self.tenant_settings is None or not self.tenant_settings.settings.clarification_enabled:
            raise ConfigurationUnavailable()
        state = self.clarification_state(store, case_id)
        if state["overall_limit_reached"]:
            raise Conflict()
        if (
            len(enhancement)
            > self.tenant_settings.settings.clarification_policy.max_answer_characters
        ):
            raise Conflict()
        cycle = store.create_clarification_cycle(
            actor, case_id, self.tenant_settings.id, command_key
        )
        event_kind = "USER_MESSAGE" if enhancement.strip() else "CLARIFICATION_CYCLE_STARTED"
        event_payload: dict[str, str | int] = (
            {"text": enhancement.strip()}
            if enhancement.strip()
            else {"cycleNumber": cycle.cycle_number}
        )
        encoded = json.dumps(event_payload, sort_keys=True, separators=(",", ":"))
        store.append_conversation_event(
            actor,
            case_id,
            event_kind,
            encoded,
            f"{command_key}:cycle",
            canonical_payload({"kind": event_kind, "payload": event_payload}),
        )
        store.advance_semantic_context(case)
        store.add_audit(actor, "CLARIFICATION_CYCLE_STARTED", "REPORTING_CASE", case_id)
        return {
            "clarification": self.clarification_state(store, case_id),
            "semantic_context_version": case.semantic_context_version,
        }

    def _current_context(
        self, store: ApplicationPersistence, case: CaseRecord, *,
        include_history: bool = False,
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
        references: list[dict[str, Any]] = []
        for reference_row in store.reference_materials(case.id):
            if reference_row.request_version_id != case.current_request_version_id:
                continue
            if self.reference_objects is None:
                raise SemanticValidationFailed()
            try:
                self.reference_objects.read(reference_row.storage_key, reference_row.content_digest)
            except EvidenceError as exc:
                raise SemanticValidationFailed() from exc
            references.append(
                {
                    "id": str(reference_row.id),
                    "filename": reference_row.filename,
                    "mediaType": reference_row.media_type,
                    "contentDigest": reference_row.content_digest,
                    "interpretationState": reference_row.interpretation_state,
                }
            )
        versions = store.case_versions(case.id)
        original_request = versions[0].request_text if versions else request.request_text
        context: dict[str, Any] = {
                "caseId": str(case.id),
                "requestVersionId": str(case.current_request_version_id),
                "requestText": request.request_text,
                "originalRequest": original_request,
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
                "referenceMaterial": references,
            }
        if include_history:
            # APBRA-174 explicitly authorises full prior interpretation context
            # for the tenant's configured model. Project only safe structured
            # meaning, summary and questions; never provider responses, headers,
            # credentials, diagnostics, or arbitrary stored session metadata.
            context["priorInterpretations"] = [
                {
                    "contextVersion": prior.context_version,
                    "state": prior.state,
                    "interpretation": json.loads(prior.session_json).get("currentInterpretation"),
                    "summary": json.loads(prior.confirmation_summary_json),
                    "questions": (
                        json.loads(prior.session_json)["rounds"][-1]["questions"]
                        if json.loads(prior.session_json).get("rounds") else []
                    ),
                }
                for prior in store.earlier_interpretations(case.id, case.semantic_context_version)
            ]
            if self.tenant_settings is not None:
                context["settingsMaterialDigest"] = interpretation_material_digest(
                    self.tenant_settings.settings
                )
                context["tenantConventions"] = (
                    self.tenant_settings.settings.conventions.model_dump(mode="json")
                )
        binding = json.dumps(context, sort_keys=True, separators=(",", ":"))
        return structure, binding, evidence

    def _validated_interpretation_context(
        self,
        store: ApplicationPersistence,
        case: CaseRecord,
        interpretation: InterpretationRecord,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Re-prove current evidence and the exact context shown to the accepter."""
        schema, current_context_binding, _evidence = self._current_context(
            store, case, include_history=interpretation.settings_version_id is not None
        )
        try:
            session = json.loads(interpretation.session_json)
        except json.JSONDecodeError as exc:
            raise SemanticValidationFailed() from exc
        if not isinstance(session, dict):
            raise SemanticValidationFailed()
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
        return schema, session

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
        existing = store.interpretation_for_context(case_id, case.semantic_context_version)
        if existing is not None:
            # Reuse is safe only while the exact evidence/context originally
            # shown remains current. A reduced eligible set must not revive an
            # interpretation prepared from a different evidence set.
            _schema, existing_session = self._validated_interpretation_context(
                store, case, existing
            )
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
                "simulation": (
                    "QUALIFIED_SERVER_MODEL"
                    if existing_session.get("providerProvenance")
                    else "LOCAL_DETERMINISTIC_NO_MODEL_CALL"
                ),
                "clarification": self.clarification_state(store, case_id),
            }
        if self.tenant_settings is not None:
            cycles = store.clarification_cycles(case_id)
            if not cycles:
                store.create_clarification_cycle(
                    actor, case_id, self.tenant_settings.id, f"initial:{case_id}"
                )
            clarification_state = self.clarification_state(store, case_id)
            if clarification_state["overall_limit_reached"]:
                events = store.conversation_events(case_id)
                # The answer to the final already-asked question may receive a
                # question-free synthesis; no further clarification is permitted.
                last_is_answer = bool(
                    events
                    and (
                        events[-1].kind == "RAW_ANSWER"
                        or (
                            events[-1].kind in {"ALTERNATIVE_ACCEPTED", "ALTERNATIVE_DECLINED"}
                            and len(events) >= 2
                            and events[-2].kind == "RAW_ANSWER"
                        )
                    )
                )
                if not last_is_answer:
                    raise Conflict()
        # Re-qualify every retained evidence object before preparing a new
        # interpretation. Persisted metadata alone is not proof that the
        # protected bytes remain available and intact.
        schema, context_binding, evidence = self._current_context(
            store, case, include_history=self.tenant_settings is not None
        )
        material_context = json.loads(context_binding)
        original_request = material_context.get("originalRequest")
        if not isinstance(original_request, str) or not original_request:
            raise SemanticValidationFailed()
        analysed_at = datetime.now(UTC)
        if self.model_provider is not None:
            if self.clarification_policy is None or self.generation_policy is None:
                raise IntelligentAnalysisUnavailable()
            try:
                result = self.model_provider.structured(
                    ProviderRequest(
                        task="REQUIREMENT_ANALYSIS",
                        system_prompt=(
                            "Interpret the complete report-requirement context for an ordinary "
                            "business user. Preserve the immutable original request, "
                            "durable additions, corrections, accepted answers and "
                            "qualified schema. Support multiple measures and dimensions, "
                            "and express only user- or evidence-established subtraction "
                            "and ratio semantics with typed operands. Ask only useful "
                            "unanswered questions. Questions are optional refinements, "
                            "not prerequisites to accepting a fully disclosed current "
                            "interpretation. Return READY_FOR_CONFIRMATION when a meaningful "
                            "supported report scope can be offered, even with optional "
                            "questions. Disclose assumptions, limitations and omitted "
                            "unsupported scope; do not invent absent data or business meaning. "
                            "Populate requestedScope, deliverableScope, unsupportedScope, "
                            "omittedScope, limitations and suggestedAlternatives explicitly. "
                            "Only the deliverable scope may become required business questions "
                            "and typed obligations; never represent omitted scope as generated. "
                            "Return NEEDS_CLARIFICATION only when no meaningful supported "
                            "scope is safe to offer. Respect the supplied per-cycle and "
                            "overall clarification limits: if either is reached, return no "
                            "new questions and disclose the currently supported scope. "
                            "Put questions "
                            "only in the top-level questions array and keep the legacy "
                            "interpretation.clarifications array empty in every state. "
                            "When ready, use only exact fully qualified Table.Column "
                            "references from the supplied schema. Every pageNames entry "
                            "must exactly match one value in interpretation.pages. Give "
                            "every obligation a stable unique ID, an explicit required "
                            "flag, a consistent minimumRepresentations value, and "
                            "complete typed measure semantics. Every measureName must "
                            "resolve to a complete measure in that obligation. When a "
                            "measure is reused across obligations, repeat its full JSON "
                            "object exactly without changing any value; "
                            "include the complete operand closure for difference and ratio "
                            "measures and reuse the exact measure ID, name and definition "
                            "wherever referenced. KPI obligations use measures and no "
                            "fields; FILTER obligations use fields and no measures; "
                            "BREAKDOWN obligations use measures and fields; TREND "
                            "obligations use measures plus exactly one schema date field "
                            "and a supported non-NONE time grain. Each confirmed dimension "
                            "and filter must be covered by a required obligation. Map every "
                            "exact business question to one or more required obligation "
                            "IDs. Keep the confirmed contract concise and use the smallest "
                            "set of obligations that completely covers the request; share "
                            "obligations across business questions and never duplicate "
                            "equivalent measures. "
                            "Never assert access, confirmation, approval or eligibility. "
                            "Image references marked NOT_INTERPRETED convey no visual semantics."
                        ),
                        context={
                            "materialContext": material_context,
                            "clarificationState": self.clarification_state(store, case_id),
                            "dataStructure": schema,
                            "clarificationPolicy": {
                                "maxRounds": self.clarification_policy.max_rounds,
                                "maxQuestionsPerRound": (
                                    self.clarification_policy.max_questions_per_round
                                ),
                                "maxAnswerCharacters": (
                                    self.clarification_policy.max_answer_characters
                                ),
                            },
                            "generationPolicy": self.generation_policy,
                        },
                        output_schema=requirement_analysis_schema(
                            self.generation_policy["generation"]["supportedTrendGrains"]
                        ),
                    )
                )
                session = self.bridge.analysis(
                    session_id=f"case-{case.id}-context-{case.semantic_context_version}",
                    original_request=original_request,
                    context_binding=context_binding,
                    analysed_at=analysed_at,
                    data_structure=schema,
                    analysis=result.value,
                    limits={
                        "maxRounds": self.clarification_policy.max_rounds,
                        "maxQuestionsPerRound": (self.clarification_policy.max_questions_per_round),
                        "maxAnswerCharacters": (self.clarification_policy.max_answer_characters),
                    },
                ).session
                session["providerProvenance"] = {
                    "profileId": result.profile_id,
                    "modelOrDeployment": result.model_or_deployment,
                    "promptVersion": result.prompt_version,
                    "configurationId": result.configuration_id,
                    "capabilityProfile": result.capability_profile,
                    "usage": result.usage,
                    "latencyMs": result.latency_ms,
                    "callCount": result.call_count,
                }
            except (ProviderCallError, SemanticValidationFailed) as exc:
                raise IntelligentAnalysisUnavailable() from exc
        elif self.allow_test_simulator:
            session = self.bridge.simulate(
                session_id=f"case-{case.id}-context-{case.semantic_context_version}",
                original_request=original_request,
                context_binding=context_binding,
                analysed_at=analysed_at,
                data_structure=schema,
            ).session
        else:
            raise IntelligentAnalysisUnavailable()
        state = session.get("state")
        if state not in {"NEEDS_CLARIFICATION", "READY_FOR_CONFIRMATION"}:
            raise SemanticValidationFailed()
        if self.tenant_settings is not None:
            cycles = store.clarification_cycles(case_id)
            current_cycle = cycles[-1]
            latest_questions = (
                session.get("rounds", [])[-1].get("questions", []) if session.get("rounds") else []
            )
            if latest_questions:
                if (
                    current_cycle.rounds_used
                    >= self.tenant_settings.settings.max_clarification_rounds_per_cycle
                    or sum(item.rounds_used for item in cycles)
                    >= self.tenant_settings.settings.max_clarification_rounds_overall
                ):
                    raise SemanticValidationFailed()
                current_cycle.rounds_used += 1
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
            settings_version_id=(self.tenant_settings.id if self.tenant_settings else None),
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
            "simulation": (
                "QUALIFIED_SERVER_MODEL"
                if session.get("providerProvenance")
                else "LOCAL_DETERMINISTIC_NO_MODEL_CALL"
            ),
            "clarification": self.clarification_state(store, case_id),
        }

    def state(self, db: object, actor: Actor, case_id: UUID) -> dict[str, Any]:
        store = cast(ApplicationPersistence, db)
        case, _ = authorized_case_access(store, actor, case_id)
        row = store.latest_interpretation(case_id)
        if row is None:
            return {
                "interpretation": None,
                "confirmed_contract": None,
                "clarification": self.clarification_state(store, case_id),
            }
        contract = store.confirmed_contract(row.id)
        session = json.loads(row.session_json)
        current = (
            row.context_version == case.semantic_context_version
            and row.request_version_id == case.current_request_version_id
            and self._settings_still_materially_current(db, row, actor.company_id)
        )
        if current:
            try:
                self._validated_interpretation_context(store, case, row)
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
                "simulation": (
                    "QUALIFIED_SERVER_MODEL"
                    if session.get("providerProvenance")
                    else "LOCAL_DETERMINISTIC_NO_MODEL_CALL"
                ),
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
            "clarification": self.clarification_state(store, case_id),
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
            or not self._settings_still_materially_current(db, interpretation, actor.company_id)
        ):
            raise StaleVersion()
        schema, session = self._validated_interpretation_context(store, case, interpretation)
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
        context_binding = session.get("contextBinding")
        readiness_binding = session.get("readinessBinding")
        assert isinstance(context_binding, str)
        assert isinstance(readiness_binding, str)
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
