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

    def case_access(
        self, actor: Actor, case_id: object
    ) -> tuple[CaseRow, CaseAccessRow] | None:
        pair = self.execute(
            select(CaseRow, CaseAccessRow)
            .join(
                CaseAccessRow,
                (CaseAccessRow.case_id == CaseRow.id)
                & (CaseAccessRow.company_id == CaseRow.company_id),
            )
            .where(
                CaseRow.id == case_id,
                CaseRow.company_id == actor.company_id,
                CaseAccessRow.membership_id == actor.membership_id,
                CaseAccessRow.active.is_(True),
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
                .where(
                    CaseRow.company_id == actor.company_id,
                    CaseAccessRow.membership_id == actor.membership_id,
                    CaseAccessRow.active.is_(True),
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

    def update_case_request(
        self, row: CaseRecord, actor: Actor, request_text: str
    ) -> CaseRow:
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

    def accept_invitation(
        self, row: InvitationRecord, identity: IdentityRecord
    ) -> MembershipRow:
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
