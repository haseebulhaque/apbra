from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class Role(StrEnum):
    COMPANY_OWNER = "COMPANY_OWNER"
    COMPANY_ADMIN = "COMPANY_ADMIN"
    MEMBER = "MEMBER"
    EXPERT = "EXPERT"

    @property
    def can_invite(self) -> bool:
        return self in {Role.COMPANY_OWNER, Role.COMPANY_ADMIN}


class AccessLevel(StrEnum):
    OWNER = "OWNER"
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"

    @property
    def can_edit(self) -> bool:
        return self in {AccessLevel.OWNER, AccessLevel.EDITOR}


@dataclass(frozen=True)
class Actor:
    identity_id: UUID
    membership_id: UUID
    company_id: UUID
    issuer: str
    subject: str
    display_name: str
    role: Role


@dataclass(frozen=True)
class OidcClaims:
    issuer: str
    subject: str
    audience: str
    nonce: str
    expires_at: datetime
    display_name: str


class IdentityRecord(Protocol):
    id: UUID
    issuer: str
    subject: str
    display_name: str
    active: bool


class SessionRecord(Protocol):
    identity_id: UUID
    membership_id: UUID | None
    revoked_at: datetime | None


class MembershipRecord(Protocol):
    id: UUID
    company_id: UUID
    identity_id: UUID
    role: str
    active: bool


class InvitationRecord(Protocol):
    id: UUID
    company_id: UUID
    invited_issuer: str
    invited_subject: str
    role: str
    token_digest: str
    expires_at: datetime
    revoked_at: datetime | None
    consumed_at: datetime | None
    consumed_by_identity_id: UUID | None


class CaseRecord(Protocol):
    id: UUID
    company_id: UUID
    creator_membership_id: UUID
    current_request_version_id: UUID
    version: int
    semantic_context_version: int
    created_at: datetime
    updated_at: datetime


class RequestVersionRecord(Protocol):
    id: UUID
    sequence: int
    request_text: str
    created_at: datetime


class AccessRecord(Protocol):
    id: UUID
    case_id: UUID
    company_id: UUID
    membership_id: UUID
    access_level: str
    active: bool
    revoked_at: datetime | None


class IdempotencyRecord(Protocol):
    payload_digest: str
    resource_id: UUID


class ConversationEventRecord(Protocol):
    id: UUID
    case_id: UUID
    sequence: int
    kind: str
    payload_json: str
    command_key: str
    payload_digest: str
    created_at: datetime


class EvidenceRecord(Protocol):
    id: UUID
    case_id: UUID
    request_version_id: UUID
    filename: str
    format: str
    content_digest: str
    storage_key: str
    observed_schema_json: str
    schema_digest: str
    eligible: bool
    created_at: datetime


class InterpretationRecord(Protocol):
    id: UUID
    case_id: UUID
    request_version_id: UUID
    evidence_id: UUID | None
    context_version: int
    session_json: str
    confirmation_summary_json: str
    readiness_binding_digest: str
    state: str
    created_at: datetime


class ConfirmedContractRecord(Protocol):
    id: UUID
    interpretation_id: UUID
    contract_json: str
    schema_version: int
    accepted_at: datetime


class ApplicationPersistence(Protocol):
    """Application-facing persistence port implemented by the SQL adapter."""

    def active_session(
        self, token_digest: str, now: datetime
    ) -> tuple[SessionRecord, IdentityRecord] | None: ...

    def active_actor(self, membership_id: UUID, identity_id: UUID) -> Actor | None: ...

    def case_access(
        self, actor: Actor, case_id: object
    ) -> tuple[CaseRecord, AccessRecord] | None: ...

    def add_audit(
        self,
        actor: Actor,
        event_type: str,
        resource_type: str,
        resource_id: UUID,
        details: str = "{}",
    ) -> None: ...

    def request_version(self, version_id: UUID) -> RequestVersionRecord | None: ...

    def lock_create_case(self, actor: Actor, command_key: str) -> None: ...

    def idempotency_record(
        self, actor: Actor, operation: str, command_key: str
    ) -> IdempotencyRecord | None: ...

    def create_case(
        self,
        actor: Actor,
        request_text: str,
        command_key: str,
        payload_digest: str,
    ) -> CaseRecord: ...

    def accessible_cases(self, actor: Actor) -> list[CaseRecord]: ...

    def case_versions(self, case_id: UUID) -> list[RequestVersionRecord]: ...

    def locked_case(self, case_id: UUID) -> CaseRecord | None: ...

    def update_case_request(
        self, row: CaseRecord, actor: Actor, request_text: str
    ) -> CaseRecord: ...

    def create_invitation(
        self,
        actor: Actor,
        invited_subject: str,
        role: Role,
        token_digest: str,
        expires_at: datetime,
    ) -> InvitationRecord: ...

    def invitation(self, token_digest: str, *, lock: bool = False) -> InvitationRecord | None: ...

    def membership(self, company_id: UUID, identity_id: UUID) -> MembershipRecord | None: ...

    def active_identity_membership(self, identity_id: UUID) -> MembershipRecord | None: ...

    def lock_identity_for_membership(self, identity_id: UUID) -> None: ...

    def accept_invitation(
        self, row: InvitationRecord, identity: IdentityRecord
    ) -> MembershipRecord: ...

    def lock_company_invitation(
        self, company_id: UUID, invitation_id: UUID
    ) -> InvitationRecord | None: ...

    def company_memberships(
        self, company_id: UUID
    ) -> list[tuple[MembershipRecord, IdentityRecord]]: ...

    def lock_company_membership(
        self, company_id: UUID, membership_id: UUID
    ) -> MembershipRecord | None: ...

    def case_access_entries(
        self, case_id: UUID
    ) -> list[tuple[AccessRecord, MembershipRecord, IdentityRecord]]: ...

    def grant_case_access(
        self, actor: Actor, case_id: UUID, membership: MembershipRecord, access_level: AccessLevel
    ) -> AccessRecord: ...

    def lock_case_access(self, case_id: UUID, membership_id: UUID) -> AccessRecord | None: ...

    def append_conversation_event(
        self, actor: Actor, case_id: UUID, kind: str, payload_json: str,
        command_key: str, payload_digest: str,
    ) -> ConversationEventRecord: ...

    def conversation_event_by_command(
        self, case_id: UUID, membership_id: UUID, command_key: str
    ) -> ConversationEventRecord | None: ...

    def conversation_events(self, case_id: UUID) -> list[ConversationEventRecord]: ...

    def add_evidence(
        self,
        actor: Actor,
        case_id: UUID,
        request_version_id: UUID,
        filename: str,
        format_name: str,
        content_digest: str,
        storage_key: str,
        observed_schema_json: str,
        schema_digest: str,
    ) -> EvidenceRecord: ...

    def evidence_items(self, case_id: UUID) -> list[EvidenceRecord]: ...

    def evidence_item(self, case_id: UUID, evidence_id: UUID) -> EvidenceRecord | None: ...

    def evidence_by_digest(
        self, case_id: UUID, request_version_id: UUID, content_digest: str
    ) -> EvidenceRecord | None: ...

    def add_interpretation(
        self,
        actor: Actor,
        case_id: UUID,
        request_version_id: UUID,
        evidence_id: UUID | None,
        context_version: int,
        session_json: str,
        confirmation_summary_json: str,
        readiness_binding_digest: str,
        state: str,
    ) -> InterpretationRecord: ...

    def interpretation(
        self, case_id: UUID, interpretation_id: UUID
    ) -> InterpretationRecord | None: ...

    def latest_interpretation(self, case_id: UUID) -> InterpretationRecord | None: ...

    def interpretation_for_context(
        self, case_id: UUID, context_version: int
    ) -> InterpretationRecord | None: ...

    def confirmed_contract(self, interpretation_id: UUID) -> ConfirmedContractRecord | None: ...

    def accept_interpretation(
        self, actor: Actor, row: InterpretationRecord, contract_json: str
    ) -> ConfirmedContractRecord: ...

    def advance_semantic_context(self, row: CaseRecord) -> None: ...


class ApplicationError(Exception):
    status_code = 400
    code = "INVALID_REQUEST"
    public_message = "The request could not be completed."


class AuthenticationRequired(ApplicationError):
    status_code = 401
    code = "AUTHENTICATION_REQUIRED"
    public_message = "Please sign in to continue."


class Forbidden(ApplicationError):
    status_code = 403
    code = "FORBIDDEN"
    public_message = "You are not permitted to perform this action."


class ProtectedResourceNotFound(ApplicationError):
    status_code = 404
    code = "CASE_NOT_FOUND"
    public_message = "The case was not found."


class Conflict(ApplicationError):
    status_code = 409
    code = "CONFLICT"
    public_message = "The request conflicts with the current state."


class StaleVersion(Conflict):
    code = "STALE_VERSION"
    public_message = "This case changed elsewhere. Reload it before trying again."


class IdempotencyConflict(Conflict):
    code = "IDEMPOTENCY_CONFLICT"
    public_message = "That command key was already used for different content."


class InvitationInvalid(ApplicationError):
    status_code = 410
    code = "INVITATION_INVALID"
    public_message = "This invitation is unavailable, expired, revoked, or already used."


class EvidenceInvalid(ApplicationError):
    status_code = 422
    code = "EVIDENCE_INVALID"
    public_message = "The supplied evidence could not be accepted safely."


class SemanticValidationFailed(ApplicationError):
    status_code = 422
    code = "SEMANTIC_VALIDATION_FAILED"
    public_message = "The proposed interpretation is not ready for confirmation."
