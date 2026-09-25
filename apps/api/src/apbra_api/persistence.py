from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from .domain import (
    AccessLevel,
    Actor,
    CaseRecord,
    IdentityRecord,
    InterpretationRecord,
    InvitationRecord,
    MembershipRecord,
    Role,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class CompanyRow(Base):
    __tablename__ = "companies"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExternalIdentityRow(Base):
    __tablename__ = "external_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_identity_issuer_subject"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MembershipRow(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_membership_company"),
        UniqueConstraint("company_id", "identity_id", name="uq_membership_company_identity"),
        CheckConstraint(
            "role IN ('COMPANY_OWNER','COMPANY_ADMIN','MEMBER','EXPERT')",
            name="ck_membership_role",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    identity_id: Mapped[UUID] = mapped_column(ForeignKey("external_identities.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InvitationRow(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        UniqueConstraint("token_digest", name="uq_invitation_token_digest"),
        ForeignKeyConstraint(
            ["issued_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_invitation_issuer_company",
        ),
        CheckConstraint("role IN ('COMPANY_ADMIN','MEMBER','EXPERT')", name="ck_invitation_role"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    issued_by_membership_id: Mapped[UUID] = mapped_column(nullable=False)
    invited_issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    invited_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_by_identity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("external_identities.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CaseRow(Base):
    __tablename__ = "reporting_cases"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_case_company"),
        UniqueConstraint("id", "company_id", "current_request_version_id", name="uq_case_current"),
        CheckConstraint("version >= 1", name="ck_case_version_positive"),
        ForeignKeyConstraint(
            ["creator_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_case_creator_company",
        ),
        ForeignKeyConstraint(
            ["current_request_version_id", "id", "company_id"],
            [
                "case_request_versions.id",
                "case_request_versions.case_id",
                "case_request_versions.company_id",
            ],
            name="fk_case_current_version",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    creator_membership_id: Mapped[UUID] = mapped_column(nullable=False)
    current_request_version_id: Mapped[UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    semantic_context_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    request_versions: Mapped[list[RequestVersionRow]] = relationship(
        back_populates="case", foreign_keys="RequestVersionRow.case_id"
    )


class RequestVersionRow(Base):
    __tablename__ = "case_request_versions"
    __table_args__ = (
        UniqueConstraint("id", "case_id", "company_id", name="uq_request_version_case_company"),
        UniqueConstraint("case_id", "sequence", name="uq_request_version_sequence"),
        CheckConstraint("sequence >= 1", name="ck_request_version_sequence_positive"),
        ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_request_version_case_company",
        ),
        ForeignKeyConstraint(
            ["created_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_request_version_actor_company",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(nullable=False)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_membership_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    case: Mapped[CaseRow] = relationship(back_populates="request_versions", foreign_keys=[case_id])


class CaseAccessRow(Base):
    __tablename__ = "case_access"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_access_case_company",
        ),
        ForeignKeyConstraint(
            ["membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_access_membership_company",
        ),
        UniqueConstraint("case_id", "membership_id", name="uq_case_access_membership"),
        CheckConstraint("access_level IN ('OWNER','EDITOR','VIEWER')", name="ck_access_level"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(nullable=False)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    membership_id: Mapped[UUID] = mapped_column(nullable=False)
    access_level: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdempotencyRow(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "membership_id", "operation", "command_key", name="uq_idempotency_scope"
        ),
        ForeignKeyConstraint(
            ["membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_idempotency_actor_company",
        ),
        ForeignKeyConstraint(
            ["resource_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_idempotency_case_company",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    membership_id: Mapped[UUID] = mapped_column(nullable=False)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    command_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["actor_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_audit_actor_company",
        ),
        Index("ix_audit_company_resource", "company_id", "resource_type", "resource_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    actor_membership_id: Mapped[UUID] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversationEventRow(Base):
    __tablename__ = "case_conversation_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_conversation_event_case_company",
        ),
        ForeignKeyConstraint(
            ["created_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_conversation_event_actor_company",
        ),
        UniqueConstraint("case_id", "sequence", name="uq_conversation_event_sequence"),
        UniqueConstraint(
            "case_id", "created_by_membership_id", "command_key",
            name="uq_conversation_event_command",
        ),
        CheckConstraint(
            "kind IN ('USER_MESSAGE','RAW_ANSWER','CLARIFICATION_QUESTION',"
            "'AI_ANALYSIS','CORRECTION','ALTERNATIVE_PROPOSED',"
            "'ALTERNATIVE_ACCEPTED','ALTERNATIVE_DECLINED')",
            name="ck_conversation_event_kind",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(nullable=False)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    command_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_membership_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceRow(Base):
    __tablename__ = "case_evidence_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_evidence_case_company",
        ),
        ForeignKeyConstraint(
            ["request_version_id", "case_id", "company_id"],
            [
                "case_request_versions.id",
                "case_request_versions.case_id",
                "case_request_versions.company_id",
            ],
            name="fk_evidence_request_version",
        ),
        ForeignKeyConstraint(
            ["uploaded_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_evidence_actor_company",
        ),
        UniqueConstraint(
            "case_id", "request_version_id", "content_digest",
            name="uq_case_request_evidence_digest",
        ),
        UniqueConstraint("id", "case_id", "company_id", name="uq_evidence_case_company"),
        CheckConstraint("format IN ('CSV','XLSX')", name="ck_evidence_format"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(nullable=False)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    request_version_id: Mapped[UUID] = mapped_column(nullable=False)
    uploaded_by_membership_id: Mapped[UUID] = mapped_column(nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    observed_schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    schema_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InterpretationRow(Base):
    __tablename__ = "case_interpretation_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_interpretation_case_company",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "case_id", "company_id"],
            [
                "case_evidence_versions.id",
                "case_evidence_versions.case_id",
                "case_evidence_versions.company_id",
            ],
            name="fk_interpretation_evidence_case_company",
        ),
        ForeignKeyConstraint(
            ["request_version_id", "case_id", "company_id"],
            [
                "case_request_versions.id",
                "case_request_versions.case_id",
                "case_request_versions.company_id",
            ],
            name="fk_interpretation_request_version",
        ),
        ForeignKeyConstraint(
            ["created_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_interpretation_actor_company",
        ),
        CheckConstraint(
            "state IN ('NEEDS_CLARIFICATION','READY_FOR_CONFIRMATION')",
            name="ck_interpretation_state",
        ),
        UniqueConstraint(
            "case_id", "context_version", name="uq_interpretation_case_context"
        ),
        UniqueConstraint("id", "case_id", "company_id", name="uq_interpretation_case_company"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(nullable=False)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    request_version_id: Mapped[UUID] = mapped_column(nullable=False)
    evidence_id: Mapped[UUID | None] = mapped_column(ForeignKey("case_evidence_versions.id"))
    context_version: Mapped[int] = mapped_column(Integer, nullable=False)
    session_json: Mapped[str] = mapped_column(Text, nullable=False)
    confirmation_summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    readiness_binding_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_membership_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConfirmedContractRow(Base):
    __tablename__ = "confirmed_requirement_contracts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_confirmed_contract_case_company",
        ),
        ForeignKeyConstraint(
            ["interpretation_id", "case_id", "company_id"],
            [
                "case_interpretation_versions.id",
                "case_interpretation_versions.case_id",
                "case_interpretation_versions.company_id",
            ],
            name="fk_confirmed_contract_interpretation_case_company",
        ),
        ForeignKeyConstraint(
            ["accepted_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_confirmed_contract_actor_company",
        ),
        UniqueConstraint("interpretation_id", name="uq_confirmed_contract_interpretation"),
        CheckConstraint("schema_version = 2", name="ck_confirmed_contract_v2"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(nullable=False)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    interpretation_id: Mapped[UUID] = mapped_column(nullable=False)
    contract_json: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_by_membership_id: Mapped[UUID] = mapped_column(nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthTransactionRow(Base):
    __tablename__ = "auth_transactions"
    __table_args__ = (UniqueConstraint("state_digest", name="uq_auth_state"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    state_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    browser_binding_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    provider_configuration_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    response_issuer_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    nonce: Mapped[str] = mapped_column(String(255), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(255), nullable=False)
    return_to: Mapped[str] = mapped_column(String(300), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthorizationCodeRow(Base):
    __tablename__ = "dev_authorization_codes"
    __table_args__ = (UniqueConstraint("code_digest", name="uq_auth_code"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    nonce: Mapped[str] = mapped_column(String(255), nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(255), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionRow(Base):
    __tablename__ = "application_sessions"
    __table_args__ = (UniqueConstraint("token_digest", name="uq_session_token"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_id: Mapped[UUID] = mapped_column(ForeignKey("external_identities.id"), nullable=False)
    membership_id: Mapped[UUID | None] = mapped_column(ForeignKey("memberships.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApplicationSession(Session):
    """SQLAlchemy adapter for the application-facing persistence port.

    The HTTP/provider layers may still use ordinary ``Session`` operations,
    while application and authorization code depend only on the typed port in
    ``domain.py``.
    """

    def active_session(
        self, token_digest: str, now: datetime
    ) -> tuple[SessionRow, ExternalIdentityRow] | None:
        row = self.scalar(
            select(SessionRow).where(
                SessionRow.token_digest == token_digest,
                SessionRow.revoked_at.is_(None),
                SessionRow.expires_at > now,
            )
        )
        if row is None:
            return None
        identity = self.get(ExternalIdentityRow, row.identity_id)
        if identity is None or not identity.active:
            return None
        return row, identity

    def active_actor(self, membership_id: UUID, identity_id: UUID) -> Actor | None:
        pair = self.execute(
            select(MembershipRow, ExternalIdentityRow)
            .join(ExternalIdentityRow, ExternalIdentityRow.id == MembershipRow.identity_id)
            .join(CompanyRow, CompanyRow.id == MembershipRow.company_id)
            .where(
                MembershipRow.id == membership_id,
                MembershipRow.identity_id == identity_id,
                MembershipRow.active.is_(True),
                ExternalIdentityRow.active.is_(True),
                CompanyRow.active.is_(True),
            )
        ).one_or_none()
        if pair is None:
            return None
        membership, identity = pair
        return Actor(
            identity_id=identity.id,
            membership_id=membership.id,
            company_id=membership.company_id,
            issuer=identity.issuer,
            subject=identity.subject,
            display_name=identity.display_name,
            role=Role(membership.role),
        )

    def case_access(self, actor: Actor, case_id: object) -> tuple[CaseRow, CaseAccessRow] | None:
        pair = self.execute(
            select(CaseRow, CaseAccessRow)
            .join(
                CaseAccessRow,
                (CaseAccessRow.case_id == CaseRow.id)
                & (CaseAccessRow.company_id == CaseRow.company_id),
            )
            .join(MembershipRow, MembershipRow.id == CaseAccessRow.membership_id)
            .join(ExternalIdentityRow, ExternalIdentityRow.id == MembershipRow.identity_id)
            .join(CompanyRow, CompanyRow.id == CaseRow.company_id)
            .where(
                CaseRow.id == case_id,
                CaseRow.company_id == actor.company_id,
                CaseAccessRow.membership_id == actor.membership_id,
                CaseAccessRow.active.is_(True),
                MembershipRow.active.is_(True),
                ExternalIdentityRow.active.is_(True),
                CompanyRow.active.is_(True),
            )
        ).one_or_none()
        if pair is None:
            return None
        return pair[0], pair[1]

    def add_audit(
        self,
        actor: Actor,
        event_type: str,
        resource_type: str,
        resource_id: UUID,
        details: str = "{}",
    ) -> None:
        self.add(
            AuditEventRow(
                company_id=actor.company_id,
                actor_membership_id=actor.membership_id,
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
                details_json=details,
            )
        )

    def request_version(self, version_id: UUID) -> RequestVersionRow | None:
        return self.get(RequestVersionRow, version_id)

    def lock_create_case(self, actor: Actor, command_key: str) -> None:
        lock_seed = int.from_bytes(
            canonical_payload(
                {
                    "company": str(actor.company_id),
                    "membership": str(actor.membership_id),
                    "operation": "CREATE_CASE",
                    "command_key": command_key,
                }
            ).encode()[:8],
            "big",
            signed=False,
        ) % (2**63 - 1)
        self.execute(select(func.pg_advisory_xact_lock(lock_seed)))

    def idempotency_record(
        self, actor: Actor, operation: str, command_key: str
    ) -> IdempotencyRow | None:
        return self.scalar(
            select(IdempotencyRow).where(
                IdempotencyRow.company_id == actor.company_id,
                IdempotencyRow.membership_id == actor.membership_id,
                IdempotencyRow.operation == operation,
                IdempotencyRow.command_key == command_key,
            )
        )

    def create_case(
        self,
        actor: Actor,
        request_text: str,
        command_key: str,
        payload_digest: str,
    ) -> CaseRow:
        case_id, version_id = uuid4(), uuid4()
        row = CaseRow(
            id=case_id,
            company_id=actor.company_id,
            creator_membership_id=actor.membership_id,
            current_request_version_id=version_id,
        )
        self.add(row)
        self.flush()
        self.add(
            RequestVersionRow(
                id=version_id,
                case_id=case_id,
                company_id=actor.company_id,
                sequence=1,
                request_text=request_text,
                created_by_membership_id=actor.membership_id,
            )
        )
        self.flush()
        self.add(
            CaseAccessRow(
                case_id=case_id,
                company_id=actor.company_id,
                membership_id=actor.membership_id,
                access_level="OWNER",
            )
        )
        self.add(
            IdempotencyRow(
                company_id=actor.company_id,
                membership_id=actor.membership_id,
                operation="CREATE_CASE",
                command_key=command_key,
                payload_digest=payload_digest,
                resource_id=case_id,
            )
        )
        self.add_audit(actor, "CASE_CREATED", "REPORTING_CASE", case_id)
        self.flush()
        return row

    def accessible_cases(self, actor: Actor) -> list[CaseRow]:
        return list(
            self.scalars(
                select(CaseRow)
                .join(CaseAccessRow, CaseAccessRow.case_id == CaseRow.id)
                .join(MembershipRow, MembershipRow.id == CaseAccessRow.membership_id)
                .join(ExternalIdentityRow, ExternalIdentityRow.id == MembershipRow.identity_id)
                .join(CompanyRow, CompanyRow.id == CaseRow.company_id)
                .where(
                    CaseRow.company_id == actor.company_id,
                    CaseAccessRow.membership_id == actor.membership_id,
                    CaseAccessRow.active.is_(True),
                    MembershipRow.active.is_(True),
                    ExternalIdentityRow.active.is_(True),
                    CompanyRow.active.is_(True),
                )
                .order_by(CaseRow.updated_at.desc())
            ).all()
        )

    def case_versions(self, case_id: UUID) -> list[RequestVersionRow]:
        return list(
            self.scalars(
                select(RequestVersionRow)
                .where(RequestVersionRow.case_id == case_id)
                .order_by(RequestVersionRow.sequence)
            ).all()
        )

    def locked_case(self, case_id: UUID) -> CaseRow | None:
        return self.scalar(select(CaseRow).where(CaseRow.id == case_id).with_for_update())

    def update_case_request(self, row: CaseRecord, actor: Actor, request_text: str) -> CaseRow:
        assert isinstance(row, CaseRow)
        new_version = RequestVersionRow(
            case_id=row.id,
            company_id=row.company_id,
            sequence=row.version + 1,
            request_text=request_text,
            created_by_membership_id=actor.membership_id,
        )
        self.add(new_version)
        self.flush()
        row.current_request_version_id = new_version.id
        row.version += 1
        row.semantic_context_version += 1
        row.updated_at = utcnow()
        self.add_audit(actor, "CASE_REQUEST_UPDATED", "REPORTING_CASE", row.id)
        self.flush()
        self.refresh(row)
        return row

    def create_invitation(
        self,
        actor: Actor,
        invited_subject: str,
        role: Role,
        token_digest: str,
        expires_at: datetime,
    ) -> InvitationRow:
        row = InvitationRow(
            company_id=actor.company_id,
            issued_by_membership_id=actor.membership_id,
            invited_issuer=actor.issuer,
            invited_subject=invited_subject,
            role=role.value,
            token_digest=token_digest,
            expires_at=expires_at,
        )
        self.add(row)
        self.flush()
        self.add_audit(actor, "INVITATION_ISSUED", "INVITATION", row.id)
        return row

    def invitation(self, token_digest: str, *, lock: bool = False) -> InvitationRow | None:
        statement = select(InvitationRow).where(InvitationRow.token_digest == token_digest)
        if lock:
            statement = statement.with_for_update()
        return self.scalar(statement)

    def membership(self, company_id: UUID, identity_id: UUID) -> MembershipRow | None:
        return self.scalar(
            select(MembershipRow).where(
                MembershipRow.company_id == company_id,
                MembershipRow.identity_id == identity_id,
            )
        )

    def active_identity_membership(self, identity_id: UUID) -> MembershipRow | None:
        return self.scalar(
            select(MembershipRow).where(
                MembershipRow.identity_id == identity_id,
                MembershipRow.active.is_(True),
            )
        )

    def lock_identity_for_membership(self, identity_id: UUID) -> None:
        identity = self.scalar(
            select(ExternalIdentityRow)
            .where(ExternalIdentityRow.id == identity_id)
            .with_for_update()
        )
        if identity is None:
            raise RuntimeError("Invitation identity disappeared during acceptance.")

    def accept_invitation(self, row: InvitationRecord, identity: IdentityRecord) -> MembershipRow:
        assert isinstance(row, InvitationRow)
        membership = MembershipRow(
            company_id=row.company_id,
            identity_id=identity.id,
            role=row.role,
        )
        self.add(membership)
        self.flush()
        row.consumed_at = datetime.now(UTC)
        row.consumed_by_identity_id = identity.id
        self.add(
            AuditEventRow(
                company_id=row.company_id,
                actor_membership_id=membership.id,
                event_type="INVITATION_ACCEPTED",
                resource_type="INVITATION",
                resource_id=row.id,
                details_json="{}",
            )
        )
        return membership

    def lock_company_invitation(
        self, company_id: UUID, invitation_id: UUID
    ) -> InvitationRow | None:
        return self.scalar(
            select(InvitationRow)
            .where(InvitationRow.id == invitation_id, InvitationRow.company_id == company_id)
            .with_for_update()
        )

    def company_memberships(
        self, company_id: UUID
    ) -> list[tuple[MembershipRow, ExternalIdentityRow]]:
        rows = self.execute(
            select(MembershipRow, ExternalIdentityRow)
            .join(ExternalIdentityRow, ExternalIdentityRow.id == MembershipRow.identity_id)
            .where(MembershipRow.company_id == company_id)
            .order_by(MembershipRow.created_at)
        ).all()
        return [(row[0], row[1]) for row in rows]

    def lock_company_membership(
        self, company_id: UUID, membership_id: UUID
    ) -> MembershipRow | None:
        return self.scalar(
            select(MembershipRow)
            .where(MembershipRow.id == membership_id, MembershipRow.company_id == company_id)
            .with_for_update()
        )

    def case_access_entries(
        self, case_id: UUID
    ) -> list[tuple[CaseAccessRow, MembershipRow, ExternalIdentityRow]]:
        rows = self.execute(
            select(CaseAccessRow, MembershipRow, ExternalIdentityRow)
            .join(MembershipRow, MembershipRow.id == CaseAccessRow.membership_id)
            .join(ExternalIdentityRow, ExternalIdentityRow.id == MembershipRow.identity_id)
            .where(CaseAccessRow.case_id == case_id)
            .order_by(CaseAccessRow.created_at)
        ).all()
        return [(row[0], row[1], row[2]) for row in rows]

    def grant_case_access(
        self,
        actor: Actor,
        case_id: UUID,
        membership: MembershipRecord,
        access_level: AccessLevel,
    ) -> CaseAccessRow:
        assert isinstance(membership, MembershipRow)
        row = self.scalar(
            select(CaseAccessRow)
            .where(
                CaseAccessRow.case_id == case_id,
                CaseAccessRow.membership_id == membership.id,
            )
            .with_for_update()
        )
        if row is None:
            row = CaseAccessRow(
                case_id=case_id,
                company_id=actor.company_id,
                membership_id=membership.id,
                access_level=access_level.value,
            )
            self.add(row)
        else:
            row.access_level = access_level.value
            row.active = True
            row.revoked_at = None
        self.flush()
        self.add_audit(
            actor,
            "CASE_ACCESS_GRANTED",
            "REPORTING_CASE",
            case_id,
            json.dumps(
                {
                    "membership_id": str(membership.id),
                    "access_level": access_level.value,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        return row

    def lock_case_access(self, case_id: UUID, membership_id: UUID) -> CaseAccessRow | None:
        return self.scalar(
            select(CaseAccessRow)
            .where(
                CaseAccessRow.case_id == case_id,
                CaseAccessRow.membership_id == membership_id,
            )
            .with_for_update()
        )

    def advance_semantic_context(self, row: CaseRecord) -> None:
        assert isinstance(row, CaseRow)
        row.semantic_context_version += 1
        row.updated_at = utcnow()

    def append_conversation_event(
        self, actor: Actor, case_id: UUID, kind: str, payload_json: str,
        command_key: str, payload_digest: str,
    ) -> ConversationEventRow:
        sequence = self.scalar(
            select(func.coalesce(func.max(ConversationEventRow.sequence), 0) + 1).where(
                ConversationEventRow.case_id == case_id
            )
        )
        row = ConversationEventRow(
            case_id=case_id,
            company_id=actor.company_id,
            sequence=int(sequence or 1),
            kind=kind,
            payload_json=payload_json,
            command_key=command_key,
            payload_digest=payload_digest,
            created_by_membership_id=actor.membership_id,
        )
        self.add(row)
        self.flush()
        return row

    def conversation_event_by_command(
        self, case_id: UUID, membership_id: UUID, command_key: str
    ) -> ConversationEventRow | None:
        return self.scalar(
            select(ConversationEventRow).where(
                ConversationEventRow.case_id == case_id,
                ConversationEventRow.created_by_membership_id == membership_id,
                ConversationEventRow.command_key == command_key,
            )
        )

    def conversation_events(self, case_id: UUID) -> list[ConversationEventRow]:
        return list(
            self.scalars(
                select(ConversationEventRow)
                .where(ConversationEventRow.case_id == case_id)
                .order_by(ConversationEventRow.sequence)
            ).all()
        )

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
    ) -> EvidenceRow:
        row = EvidenceRow(
            case_id=case_id,
            company_id=actor.company_id,
            request_version_id=request_version_id,
            uploaded_by_membership_id=actor.membership_id,
            filename=filename,
            format=format_name,
            content_digest=content_digest,
            storage_key=storage_key,
            observed_schema_json=observed_schema_json,
            schema_digest=schema_digest,
        )
        self.add(row)
        self.flush()
        return row

    def evidence_items(self, case_id: UUID) -> list[EvidenceRow]:
        return list(
            self.scalars(
                select(EvidenceRow)
                .where(EvidenceRow.case_id == case_id, EvidenceRow.eligible.is_(True))
                .order_by(EvidenceRow.created_at)
            ).all()
        )

    def evidence_item(self, case_id: UUID, evidence_id: UUID) -> EvidenceRow | None:
        return self.scalar(
            select(EvidenceRow).where(
                EvidenceRow.case_id == case_id,
                EvidenceRow.id == evidence_id,
                EvidenceRow.eligible.is_(True),
            )
        )

    def evidence_by_digest(
        self, case_id: UUID, request_version_id: UUID, content_digest: str
    ) -> EvidenceRow | None:
        return self.scalar(
            select(EvidenceRow).where(
                EvidenceRow.case_id == case_id,
                EvidenceRow.request_version_id == request_version_id,
                EvidenceRow.content_digest == content_digest,
                EvidenceRow.eligible.is_(True),
            )
        )

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
    ) -> InterpretationRow:
        row = InterpretationRow(
            case_id=case_id,
            company_id=actor.company_id,
            request_version_id=request_version_id,
            evidence_id=evidence_id,
            context_version=context_version,
            session_json=session_json,
            confirmation_summary_json=confirmation_summary_json,
            readiness_binding_digest=readiness_binding_digest,
            state=state,
            created_by_membership_id=actor.membership_id,
        )
        self.add(row)
        self.flush()
        return row

    def interpretation(self, case_id: UUID, interpretation_id: UUID) -> InterpretationRow | None:
        return self.scalar(
            select(InterpretationRow).where(
                InterpretationRow.case_id == case_id,
                InterpretationRow.id == interpretation_id,
            )
        )

    def latest_interpretation(self, case_id: UUID) -> InterpretationRow | None:
        return self.scalar(
            select(InterpretationRow)
            .where(InterpretationRow.case_id == case_id)
            .order_by(InterpretationRow.created_at.desc(), InterpretationRow.id.desc())
            .limit(1)
        )

    def interpretation_for_context(
        self, case_id: UUID, context_version: int
    ) -> InterpretationRow | None:
        return self.scalar(
            select(InterpretationRow).where(
                InterpretationRow.case_id == case_id,
                InterpretationRow.context_version == context_version,
            )
        )

    def confirmed_contract(self, interpretation_id: UUID) -> ConfirmedContractRow | None:
        return self.scalar(
            select(ConfirmedContractRow).where(
                ConfirmedContractRow.interpretation_id == interpretation_id
            )
        )

    def accept_interpretation(
        self, actor: Actor, row: InterpretationRecord, contract_json: str
    ) -> ConfirmedContractRow:
        assert isinstance(row, InterpretationRow)
        existing = self.confirmed_contract(row.id)
        if existing is not None:
            return existing
        contract = ConfirmedContractRow(
            case_id=row.case_id,
            company_id=row.company_id,
            interpretation_id=row.id,
            contract_json=contract_json,
            schema_version=2,
            accepted_by_membership_id=actor.membership_id,
        )
        self.add(contract)
        self.flush()
        self.add_audit(
            actor,
            "REQUIREMENTS_CONFIRMED",
            "REPORTING_CASE",
            row.case_id,
            json.dumps(
                {"interpretation_id": str(row.id), "contract_id": str(contract.id)},
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        return contract


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class Database:
    def __init__(self, url: str) -> None:
        self.engine = create_engine(url, pool_pre_ping=True)
        self.session_factory = sessionmaker(
            self.engine, expire_on_commit=False, class_=ApplicationSession
        )

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
