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
    provider_profile_id: str


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
    provider_profile_id: str


class SessionRecord(Protocol):
    id: UUID
    identity_id: UUID
    membership_id: UUID | None
    revoked_at: datetime | None
    provider_profile_id: str


class MembershipRecord(Protocol):
    id: UUID
    company_id: UUID
    identity_id: UUID
    role: str
    active: bool


class CompanyRecord(Protocol):
    id: UUID
    name: str
    active: bool


class CompanyCreationRecord(Protocol):
    identity_id: UUID
    company_id: UUID
    membership_id: UUID
    payload_digest: str


class InvitationRecord(Protocol):
    id: UUID
    company_id: UUID
    invited_issuer: str
    invited_subject: str
    provider_profile_id: str
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
    report_title: str
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


class ClarificationCycleRecord(Protocol):
    id: UUID
    company_id: UUID
    case_id: UUID
    cycle_number: int
    rounds_used: int
    settings_version_id: UUID
    command_key: str
    started_at: datetime
    closed_at: datetime | None


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


class ReferenceMaterialRecord(Protocol):
    id: UUID
    case_id: UUID
    request_version_id: UUID
    filename: str
    media_type: str
    content_digest: str
    storage_key: str
    interpretation_state: str
    capability_profile_id: str | None
    created_at: datetime


class InterpretationRecord(Protocol):
    id: UUID
    case_id: UUID
    request_version_id: UUID
    settings_version_id: UUID | None
    evidence_id: UUID | None
    context_version: int
    session_json: str
    confirmation_summary_json: str
    readiness_binding_digest: str
    state: str
    created_at: datetime


class ConfirmedContractRecord(Protocol):
    id: UUID
    case_id: UUID
    company_id: UUID
    interpretation_id: UUID
    settings_version_id: UUID | None
    contract_json: str
    schema_version: int
    accepted_at: datetime


class ReviewedReportDesignRecord(Protocol):
    id: UUID
    company_id: UUID
    case_id: UUID
    confirmed_contract_id: UUID
    interpretation_id: UUID
    request_version_id: UUID
    semantic_context_version: int
    binding_json: str
    binding_digest: str
    semantic_input_digest: str
    evidence_binding_digest: str
    design_json: str
    content_digest: str
    summary_json: str
    reviewer_membership_id: UUID | None
    reviewer_identity_id: UUID | None
    reviewer_role: str | None
    origin: str
    design_attempt_id: UUID | None
    eligibility_validation_json: str | None
    reviewed_at: datetime


class AutomaticDesignAttemptRecord(Protocol):
    id: UUID
    company_id: UUID
    case_id: UUID
    confirmed_contract_id: UUID
    interpretation_id: UUID
    request_version_id: UUID
    settings_version_id: UUID | None
    semantic_context_version: int
    requested_by_membership_id: UUID
    command_key: str
    command_payload_digest: str
    status: str
    provider_profile_id: str | None
    model_or_deployment: str | None
    prompt_version: str | None
    configuration_id: str | None
    capability_profile_json: str
    usage_json: str
    safe_failure_code: str | None
    requirement_binding_digest: str
    evidence_binding_digest: str
    reference_binding_digest: str
    validation_json: str | None
    candidate_digest: str | None
    created_at: datetime
    completed_at: datetime | None


class GenerationAttemptRecord(Protocol):
    id: UUID
    case_id: UUID
    company_id: UUID
    confirmed_contract_id: UUID
    reviewed_design_id: UUID | None
    interpretation_id: UUID
    request_version_id: UUID
    settings_version_id: UUID | None
    created_by_membership_id: UUID
    command_key: str
    command_payload_digest: str
    input_digest: str
    evidence_binding_digest: str
    status: str
    attempt_number: int
    retry_of_attempt_id: UUID | None
    supersedes_attempt_id: UUID | None
    fence_token: UUID
    provenance_json: str
    validation_json: str | None
    failure_code: str | None
    failure_reason: str | None
    artifact_id: UUID | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None


class GeneratedArtifactRecord(Protocol):
    id: UUID
    attempt_id: UUID
    case_id: UUID
    company_id: UUID
    settings_version_id: UUID | None
    guide_digest: str | None
    storage_key: str
    filename: str
    content_digest: str
    byte_size: int
    validation_status: str
    created_at: datetime


class ApplicationPersistence(Protocol):
    """Application-facing persistence port implemented by the SQL adapter."""

    def resolve_external_identity(
        self,
        profile_id: str,
        issuer: str,
        subject: str,
        display_name: str,
        *,
        allow_legacy_local: bool,
    ) -> tuple[IdentityRecord, bool]: ...

    def add_auth_event(
        self,
        profile_id: str,
        event_type: str,
        *,
        identity_id: UUID | None = None,
        session_id: UUID | None = None,
        reason: str | None = None,
    ) -> None: ...

    def active_session(
        self, token_digest: str, now: datetime
    ) -> tuple[SessionRecord, IdentityRecord] | None: ...

    def lock_active_session_for_creation(
        self, session_id: UUID, identity_id: UUID, now: datetime
    ) -> SessionRecord: ...

    def company_creation_command(
        self, identity_id: UUID, command_key: str
    ) -> CompanyCreationRecord | None: ...

    def company(self, company_id: UUID) -> CompanyRecord | None: ...

    def active_company(
        self, company_id: UUID, *, lock: bool = False
    ) -> CompanyRecord | None: ...

    def create_company_with_owner(
        self,
        identity: IdentityRecord,
        session: SessionRecord,
        name: str,
        command_key: str,
        payload_digest: str,
    ) -> tuple[CompanyRecord, MembershipRecord]: ...

    def eligible_invitation_for_identity(self, identity: IdentityRecord, now: datetime) -> bool: ...

    def update_identity_display_name(
        self, identity_id: UUID, display_name: str
    ) -> IdentityRecord: ...

    def lock_company_for_membership_management(self, company_id: UUID) -> None: ...

    def active_owner_count(self, company_id: UUID) -> int: ...

    def active_actor(
        self, membership_id: UUID, identity_id: UUID, *, lock: bool = False
    ) -> Actor | None: ...

    def case_access(
        self, actor: Actor, case_id: object, *, lock: bool = False
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
        report_title: str,
    ) -> CaseRecord: ...

    def update_case_report_title(self, case: CaseRecord, report_title: str) -> None: ...

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
        self,
        actor: Actor,
        case_id: UUID,
        kind: str,
        payload_json: str,
        command_key: str,
        payload_digest: str,
    ) -> ConversationEventRecord: ...

    def conversation_event_by_command(
        self, case_id: UUID, membership_id: UUID, command_key: str
    ) -> ConversationEventRecord | None: ...

    def conversation_events(self, case_id: UUID) -> list[ConversationEventRecord]: ...

    def clarification_cycles(self, case_id: UUID) -> list[ClarificationCycleRecord]: ...

    def clarification_cycle_by_command(
        self, case_id: UUID, membership_id: UUID, command_key: str
    ) -> ClarificationCycleRecord | None: ...

    def create_clarification_cycle(
        self, actor: Actor, case_id: UUID, settings_version_id: UUID, command_key: str
    ) -> ClarificationCycleRecord: ...

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

    def add_reference_material(
        self,
        actor: Actor,
        case_id: UUID,
        request_version_id: UUID,
        filename: str,
        media_type: str,
        content_digest: str,
        storage_key: str,
        interpretation_state: str,
        capability_profile_id: str | None,
    ) -> ReferenceMaterialRecord: ...

    def reference_materials(self, case_id: UUID) -> list[ReferenceMaterialRecord]: ...

    def reference_by_digest(
        self, case_id: UUID, request_version_id: UUID, content_digest: str
    ) -> ReferenceMaterialRecord | None: ...

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
        *,
        settings_version_id: UUID | None = None,
    ) -> InterpretationRecord: ...

    def interpretation(
        self, case_id: UUID, interpretation_id: UUID
    ) -> InterpretationRecord | None: ...

    def latest_interpretation(self, case_id: UUID) -> InterpretationRecord | None: ...

    def earlier_interpretations(
        self, case_id: UUID, before_context_version: int
    ) -> list[InterpretationRecord]: ...

    def interpretation_for_context(
        self, case_id: UUID, context_version: int
    ) -> InterpretationRecord | None: ...

    def confirmed_contract(self, interpretation_id: UUID) -> ConfirmedContractRecord | None: ...

    def accept_interpretation(
        self, actor: Actor, row: InterpretationRecord, contract_json: str
    ) -> ConfirmedContractRecord: ...

    def advance_semantic_context(self, row: CaseRecord) -> None: ...

    def confirmed_contract_for_case(
        self, case_id: UUID, contract_id: UUID
    ) -> ConfirmedContractRecord | None: ...

    def add_reviewed_design(
        self,
        actor: Actor,
        case_id: UUID,
        contract_id: UUID,
        interpretation_id: UUID,
        request_version_id: UUID,
        semantic_context_version: int,
        binding_json: str,
        binding_digest: str,
        semantic_input_digest: str,
        evidence_binding_digest: str,
        design_json: str,
        content_digest: str,
        summary_json: str,
        *,
        origin: str = "EXPERT_REVIEWED",
        design_attempt_id: UUID | None = None,
        eligibility_validation_json: str | None = None,
    ) -> ReviewedReportDesignRecord: ...

    def create_design_attempt(
        self,
        actor: Actor,
        case_id: UUID,
        contract_id: UUID,
        interpretation_id: UUID,
        request_version_id: UUID,
        semantic_context_version: int,
        command_key: str,
        command_payload_digest: str,
        requirement_binding_digest: str,
        evidence_binding_digest: str,
        reference_binding_digest: str,
        *,
        settings_version_id: UUID | None = None,
    ) -> AutomaticDesignAttemptRecord: ...

    def design_attempt_by_command(
        self, actor: Actor, case_id: UUID, command_key: str
    ) -> AutomaticDesignAttemptRecord | None: ...

    def design_attempts(
        self, case_id: UUID, contract_id: UUID
    ) -> list[AutomaticDesignAttemptRecord]: ...

    def reviewed_design(
        self, case_id: UUID, design_id: UUID
    ) -> ReviewedReportDesignRecord | None: ...

    def reviewed_designs(
        self, case_id: UUID, contract_id: UUID
    ) -> list[ReviewedReportDesignRecord]: ...

    def generation_attempt_by_command(
        self, actor: Actor, case_id: UUID, command_key: str
    ) -> GenerationAttemptRecord | None: ...

    def equivalent_generation_attempt(
        self, case_id: UUID, input_digest: str
    ) -> GenerationAttemptRecord | None: ...

    def active_generation_attempt(self, case_id: UUID) -> GenerationAttemptRecord | None: ...

    def create_generation_attempt(
        self,
        actor: Actor,
        case_id: UUID,
        contract_id: UUID,
        interpretation_id: UUID,
        request_version_id: UUID,
        command_key: str,
        command_payload_digest: str,
        input_digest: str,
        evidence_binding_digest: str,
        provenance_json: str,
        reviewed_design_id: UUID,
        *,
        settings_version_id: UUID | None = None,
        retry_of_attempt_id: UUID | None = None,
        supersedes_attempt_id: UUID | None = None,
    ) -> GenerationAttemptRecord: ...

    def generation_attempt(
        self, case_id: UUID, attempt_id: UUID, *, lock: bool = False
    ) -> GenerationAttemptRecord | None: ...

    def generation_attempts(self, case_id: UUID) -> list[GenerationAttemptRecord]: ...

    def generated_artifact(self, artifact_id: UUID) -> GeneratedArtifactRecord | None: ...

    def add_generated_artifact(
        self,
        attempt: GenerationAttemptRecord,
        storage_key: str,
        filename: str,
        content_digest: str,
        byte_size: int,
        guide_digest: str | None = None,
    ) -> GeneratedArtifactRecord: ...


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


class CompanyCreationNotAvailable(Conflict):
    code = "COMPANY_CREATION_NOT_AVAILABLE"
    public_message = "Company creation is not available for this account right now."


class CompanyNameInvalid(ApplicationError):
    status_code = 422
    code = "COMPANY_NAME_INVALID"
    public_message = "Enter a valid company name of at most 200 characters."


class ProfileInvalid(ApplicationError):
    status_code = 422
    code = "PROFILE_INVALID"
    public_message = "Enter a valid display name of at most 200 characters."


class LastOwnerRequired(Conflict):
    code = "LAST_OWNER_REQUIRED"
    public_message = "This company must retain an active owner."


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


class IntelligentAnalysisUnavailable(ApplicationError):
    status_code = 409
    code = "INTELLIGENT_ANALYSIS_UNAVAILABLE"
    public_message = (
        "APBRA could not safely complete the requirement analysis. Your report request "
        "and supporting information remain saved; retry later or ask for expert assistance."
    )


class GenerationUnavailable(ApplicationError):
    status_code = 422
    code = "GENERATION_UNAVAILABLE"
    public_message = "A current confirmed requirement is required before building a report."


class ReviewedDesignRequired(GenerationUnavailable):
    code = "TRUSTED_REPORT_DESIGN_REQUIRED"
    public_message = "A current eligible report plan is required before building."


class DesignProposalUnavailable(ApplicationError):
    status_code = 409
    code = "AUTOMATIC_DESIGN_UNAVAILABLE"
    public_message = (
        "APBRA could not create an eligible report design. Your confirmed requirements "
        "remain saved; retry later or ask for expert assistance."
    )


class ConfigurationUnavailable(ApplicationError):
    status_code = 503
    code = "CONFIGURATION_UNAVAILABLE"
    public_message = "This report capability is not configured and qualified for this runtime."


class GenerationFailed(ApplicationError):
    status_code = 422
    code = "GENERATION_FAILED"
    public_message = "The report candidate could not be generated and validated."


class ArtifactUnavailable(ApplicationError):
    status_code = 404
    code = "ARTIFACT_NOT_FOUND"
    public_message = "The generated report is unavailable."
