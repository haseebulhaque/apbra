"""Durable native-receipt metadata; private bodies remain in protected objects."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from .native_response_archive import NativeResponseReceipt, NativeResponseScope
from .persistence import Base, Database, utcnow


class NativeReceiveCommandRow(Base):
    __tablename__ = "native_receive_commands"
    __table_args__ = (
        UniqueConstraint(
            "id", "company_id", "case_id", "context_version", name="uq_native_command_scope"
        ),
        UniqueConstraint("company_id", "case_id", "command_key", name="uq_native_command_key"),
        ForeignKeyConstraint(
            ["case_id", "company_id"], ["reporting_cases.id", "reporting_cases.company_id"]
        ),
        ForeignKeyConstraint(
            ["actor_membership_id", "company_id"], ["memberships.id", "memberships.company_id"]
        ),
        CheckConstraint("context_version >= 1", name="ck_native_command_context"),
        CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599", name="ck_native_command_http"
        ),
        CheckConstraint(
            "provider_status IS NULL OR provider_status IN "
            "('completed','failed','incomplete','queued','in_progress','cancelled','UNKNOWN')",
            name="ck_native_command_provider_status",
        ),
        CheckConstraint(
            "diagnostic_json IS NULL OR octet_length(diagnostic_json) <= 4096",
            name="ck_native_command_diagnostic",
        ),
        CheckConstraint(
            "state IN ('ADMITTED','RECEIVED','HTTP_ERROR','UNCERTAIN')",
            name="ck_native_command_state",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    case_id: Mapped[UUID] = mapped_column(nullable=False)
    actor_membership_id: Mapped[UUID] = mapped_column(nullable=False)
    context_version: Mapped[int] = mapped_column(Integer, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    provider_status: Mapped[str | None] = mapped_column(String(16))
    diagnostic_json: Mapped[str | None] = mapped_column(Text)
    settings_id: Mapped[UUID] = mapped_column(nullable=False)
    command_key: Mapped[UUID] = mapped_column(nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NativeResponseReceiptRow(Base):
    __tablename__ = "native_response_receipts"
    __table_args__ = (
        UniqueConstraint("operation_id", name="uq_native_receipt_operation"),
        UniqueConstraint("id", "case_id", "company_id", name="uq_native_receipt_case_company"),
        ForeignKeyConstraint(
            ["operation_id", "company_id", "case_id", "context_version"],
            [
                "native_receive_commands.id",
                "native_receive_commands.company_id",
                "native_receive_commands.case_id",
                "native_receive_commands.context_version",
            ],
        ),
        CheckConstraint("size BETWEEN 1 AND 4000000", name="ck_native_receipt_size"),
        CheckConstraint("length(digest) = 64", name="ck_native_receipt_digest"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(nullable=False)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    case_id: Mapped[UUID] = mapped_column(nullable=False)
    context_version: Mapped[int] = mapped_column(Integer, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DatabaseNativeResponseIndex:
    def __init__(self, database: Database):
        self.database = database

    def commit(self, receipt: NativeResponseReceipt) -> None:
        # A separate transaction retains the original even if the HTTP request
        # later rolls back or the browser disconnects. No output interpretation.
        with self.database.session() as db:
            db.add(
                NativeResponseReceiptRow(
                    id=receipt.id,
                    operation_id=receipt.scope.operation_id,
                    company_id=receipt.scope.company_id,
                    case_id=receipt.scope.case_id,
                    context_version=receipt.scope.context_version,
                    digest=receipt.digest,
                    size=receipt.size,
                    storage_key=receipt.storage_key,
                )
            )

    def load(self, scope: NativeResponseScope, reference: UUID) -> NativeResponseReceipt:
        with self.database.session() as db:
            row = db.scalar(
                select(NativeResponseReceiptRow).where(
                    NativeResponseReceiptRow.id == reference,
                    NativeResponseReceiptRow.operation_id == scope.operation_id,
                    NativeResponseReceiptRow.company_id == scope.company_id,
                    NativeResponseReceiptRow.case_id == scope.case_id,
                    NativeResponseReceiptRow.context_version == scope.context_version,
                )
            )
            if row is None:
                raise ValueError("NATIVE_RESPONSE_NOT_FOUND")
            return NativeResponseReceipt(row.id, scope, row.digest, row.size, row.storage_key)


class NativeContractBindingRow(Base):
    """Server admission facts only; originals without these remain readable."""

    __tablename__ = "native_contract_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["operation_id", "company_id", "case_id", "context_version"],
            ["native_receive_commands.id", "native_receive_commands.company_id",
             "native_receive_commands.case_id", "native_receive_commands.context_version"],
        ),
        CheckConstraint(
            "(task = 'REQUIREMENT_ANALYSIS' AND contract_id IS NULL) OR "
            "(task = 'REPORT_DESIGN' AND contract_id IS NOT NULL)",
            name="ck_native_binding_stage",
        ),
        CheckConstraint("length(input_digest) = 64 AND length(profile_digest) = 64",
                        name="ck_native_binding_digests"),
        CheckConstraint("octet_length(metadata_json) <= 4096", name="ck_native_binding_metadata"),
    )
    operation_id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    case_id: Mapped[UUID] = mapped_column(nullable=False)
    context_version: Mapped[int] = mapped_column(Integer, nullable=False)
    task: Mapped[str] = mapped_column(String(32), nullable=False)
    contract_id: Mapped[UUID | None] = mapped_column()
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
