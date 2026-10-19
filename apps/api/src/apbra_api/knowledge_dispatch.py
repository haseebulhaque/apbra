"""Durable source-neutral provider operations; no live provider is configured.

Only a test-profile adapter can cross this seam. A send claim is committed before
adapter IO. Missing receipts are UNKNOWN, never permission to send again.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import ProtectedResourceNotFound
from .knowledge_documents import (
    DraftContext,
    KnowledgeDocumentsError,
    KnowledgeDocumentsService,
    _decode,
    _iso,
    canonical_uuid,
    conflict,
    invalid,
    unavailable,
)
from .persistence import (
    KnowledgeCommandRow,
    KnowledgeDispatchCallRow,
    KnowledgeDispatchReceiptRow,
    KnowledgeDispatchRow,
    KnowledgeRevisionRow,
)
from .tenant_settings import current_settings


@dataclass(frozen=True, slots=True)
class Submission:
    operation_id: UUID
    company_id: UUID
    document_id: UUID
    revision_id: UUID
    settings_id: UUID
    settings_version: int
    action: str
    title: str = field(repr=False)
    source_version: str = field(repr=False)
    text: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """Explicit per-key write acknowledgement, not indexing/removal evidence."""

    operation_id: UUID
    call_id: UUID
    results: tuple[tuple[str, bool], ...] = field(repr=False)


class KnowledgeProvider(Protocol):
    def prepare(self, submission: Submission) -> tuple[str, ...]:
        """Pure planning only: no IO or external writes."""
        ...

    def send(
        self, submission: Submission, call_id: UUID, keys: tuple[str, ...]
    ) -> ProviderResult: ...

    def reconcile(
        self, submission: Submission, call_id: UUID, keys: tuple[str, ...]
    ) -> ProviderResult: ...


def parse_request(raw: bytes, prepare: bool) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise invalid()
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
        expected = (
            {
                "expected_current_revision_id",
                "expected_current_operation_id",
                "expected_settings_version",
                "retry_of",
            }
            if prepare
            else set()
        )
        if type(value) is not dict or set(value) != expected:
            raise invalid()
        if prepare:
            canonical_uuid(value["expected_current_revision_id"])
            canonical_uuid(value["expected_current_operation_id"])
            if (
                type(value["expected_settings_version"]) is not int
                or value["expected_settings_version"] < 1
            ):
                raise invalid()
            if value["retry_of"] is not None:
                canonical_uuid(value["retry_of"])
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise invalid() from None


def provider_unconfigured() -> KnowledgeDocumentsError:
    return KnowledgeDocumentsError(
        "KNOWLEDGE_PROVIDER_UNCONFIGURED",
        409,
        "No source-native document provider is configured. The operation remains local.",
    )


def calls(db: Session, row: KnowledgeDispatchRow) -> list[KnowledgeDispatchCallRow]:
    return list(
        db.scalars(
            select(KnowledgeDispatchCallRow)
            .where(
                KnowledgeDispatchCallRow.dispatch_id == row.id,
                KnowledgeDispatchCallRow.company_id == row.company_id,
            )
            .order_by(KnowledgeDispatchCallRow.sequence)
        )
    )


def receipt(db: Session, call: KnowledgeDispatchCallRow) -> KnowledgeDispatchReceiptRow | None:
    return db.scalar(
        select(KnowledgeDispatchReceiptRow).where(
            KnowledgeDispatchReceiptRow.call_id == call.id,
            KnowledgeDispatchReceiptRow.company_id == call.company_id,
        )
    )


def summary(db: Session, row: KnowledgeDispatchRow) -> dict[str, Any]:
    history = []
    for call in calls(db, row):
        result = receipt(db, call)
        history.append(
            {
                "call_id": str(call.id),
                "sequence": call.sequence,
                "kind": call.kind,
                "created_at": _iso(call.created_at),
                "outcome": result.outcome if result else "UNKNOWN",
                "reason": result.reason if result else "PENDING_RECEIPT",
                "acknowledged": result.acknowledged if result else 0,
                "rejected": result.rejected if result else 0,
            }
        )
    latest = history[-1] if history else None
    state = latest["outcome"] if latest else "NOT_SENT"
    # Contradictory observations cannot erase a durable acknowledgement and
    # thereby authorize a duplicate send. Preserve every receipt as history.
    contradictory = any(c["outcome"] == "ACKNOWLEDGED" for c in history) and state in {
        "FAILED",
        "PARTIAL",
    }
    write_state = "UNKNOWN" if contradictory or state == "PARTIAL" else state
    return {
        "operation_id": str(row.id),
        "command_key": str(row.command_key),
        "document_id": str(row.document_id),
        "revision_id": str(row.revision_id),
        "local_operation_id": str(row.command_id),
        "settings_version": row.settings_version,
        "action": row.action,
        "sequence": row.sequence,
        "created_at": _iso(row.created_at),
        "provider_write_outcome": write_state,
        "write_evidence": "CONFLICTING" if contradictory else "RECORDED",
        "receipt_outcome": state,
        "indexing": "UNVERIFIED",
        "removal": "UNVERIFIED",
        "ai_availability": "UNVERIFIED",
        "calls": history,
    }


def command_outcome(db: Session, command_id: UUID) -> str:
    row = db.scalar(
        select(KnowledgeDispatchRow)
        .where(KnowledgeDispatchRow.command_id == command_id)
        .order_by(KnowledgeDispatchRow.sequence.desc())
        .limit(1)
    )
    return str(summary(db, row)["provider_write_outcome"]) if row else "NOT_SENT"


def revision_outcome(db: Session, revision_id: UUID) -> str:
    row = db.scalar(
        select(KnowledgeDispatchRow)
        .where(KnowledgeDispatchRow.revision_id == revision_id)
        .order_by(KnowledgeDispatchRow.sequence.desc())
        .limit(1)
    )
    return str(summary(db, row)["provider_write_outcome"]) if row else "NOT_SENT"


def normalize(
    row: KnowledgeDispatchRow, call: KnowledgeDispatchCallRow, result: object
) -> tuple[str, int, int, str]:
    """Reject partial coverage/foreign keys/types without exposing provider values."""
    try:
        keys = json.loads(call.manifest_json)
        if (
            type(result) is not ProviderResult
            or result.operation_id != row.id
            or result.call_id != call.id
            or type(result.results) is not tuple
        ):
            return "UNKNOWN", 0, 0, "INVALID_RECEIPT"
        outcomes: dict[str, bool] = {}
        for item in result.results:
            if (
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) is not bool
                or item[0] in outcomes
            ):
                return "UNKNOWN", 0, 0, "INVALID_RECEIPT"
            outcomes[item[0]] = item[1]
        if set(outcomes) != set(keys):
            return "UNKNOWN", 0, 0, "INVALID_RECEIPT"
        accepted = sum(outcomes.values())
        rejected = len(keys) - accepted
        state = "ACKNOWLEDGED" if not rejected else "FAILED" if not accepted else "PARTIAL"
        return state, accepted, rejected, "PER_KEY_ACKNOWLEDGEMENT"
    except (ValueError, TypeError, AttributeError):
        return "UNKNOWN", 0, 0, "INVALID_RECEIPT"


class KnowledgeDispatchService:
    def __init__(self, provider: KnowledgeProvider | None = None) -> None:
        self.provider = provider
        self.documents = KnowledgeDocumentsService()

    def rows(
        self, db: Session, context: DraftContext, document_id: UUID
    ) -> list[KnowledgeDispatchRow]:
        self.documents.document(db, context.actor, document_id)
        return list(
            db.scalars(
                select(KnowledgeDispatchRow)
                .where(
                    KnowledgeDispatchRow.company_id == context.actor.company_id,
                    KnowledgeDispatchRow.document_id == document_id,
                )
                .order_by(KnowledgeDispatchRow.sequence)
            )
        )

    def status(self, db: Session, context: DraftContext, document_id: UUID) -> dict[str, Any]:
        rows = self.rows(db, context, document_id)
        return {
            "company_id": str(context.actor.company_id),
            "document_id": str(document_id),
            "configured": self.provider is not None,
            "current_settings_version": current_settings(db, context.actor.company_id).version,
            "operations": [summary(db, row) for row in rows],
        }

    def recover(self, db: Session, context: DraftContext, key: UUID) -> dict[str, Any]:
        row = db.scalar(
            select(KnowledgeDispatchRow).where(
                KnowledgeDispatchRow.company_id == context.actor.company_id,
                KnowledgeDispatchRow.command_key == key,
                KnowledgeDispatchRow.initiator_identity_id == context.actor.identity_id,
            )
        )
        if row is not None and row.initiator_membership_id != context.actor.membership_id:
            raise ProtectedResourceNotFound()
        return {
            "company_id": str(context.actor.company_id),
            "reconciliation": "COMMITTED" if row else "NOT_OBSERVED",
            "operation": summary(db, row) if row else None,
        }

    def prepare(
        self,
        db: Session,
        context: DraftContext,
        document_id: UUID,
        key: UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        document = self.documents.document(db, context.actor, document_id)
        rows = self.rows(db, context, document_id)
        digest = hashlib.sha256(
            json.dumps(
                {
                    **payload,
                    "document_id": str(document_id),
                    "membership_id": str(context.actor.membership_id),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        existing = db.scalar(
            select(KnowledgeDispatchRow).where(
                KnowledgeDispatchRow.company_id == context.actor.company_id,
                KnowledgeDispatchRow.command_key == key,
                KnowledgeDispatchRow.initiator_identity_id == context.actor.identity_id,
            )
        )
        if existing:
            if existing.payload_digest != digest:
                raise conflict("KNOWLEDGE_COMMAND_CONFLICT")
            return summary(db, existing)
        snapshot = current_settings(db, context.actor.company_id, lock=True)
        if (
            str(document.current_revision_id) != payload["expected_current_revision_id"]
            or str(document.current_operation_id) != payload["expected_current_operation_id"]
            or snapshot.version != payload["expected_settings_version"]
        ):
            raise conflict("KNOWLEDGE_CONTEXT_CHANGED")
        equivalents = [r for r in rows if r.command_id == document.current_operation_id]
        latest = equivalents[-1] if equivalents else None
        if latest:
            previous_state = summary(db, latest)["provider_write_outcome"]
            explicit_replacement = (
                previous_state == "NOT_SENT" and latest.settings_id != snapshot.id
            )
            if payload["retry_of"] != str(latest.id) or (
                previous_state != "FAILED" and not explicit_replacement
            ):
                raise conflict("KNOWLEDGE_OPERATION_EXISTS")
        elif payload["retry_of"] is not None:
            raise conflict("KNOWLEDGE_OPERATION_EXISTS")
        command = db.get(KnowledgeCommandRow, document.current_operation_id)
        if command is None:
            raise unavailable()
        row = KnowledgeDispatchRow(
            id=uuid4(),
            company_id=context.actor.company_id,
            document_id=document_id,
            command_id=command.id,
            revision_id=command.target_revision_id,
            settings_id=snapshot.id,
            settings_version=snapshot.version,
            command_key=key,
            initiator_identity_id=context.actor.identity_id,
            initiator_membership_id=context.actor.membership_id,
            action={"CREATE": "UPLOAD", "REVISION": "UPDATE", "ARCHIVE": "DELETE"}[command.kind],
            payload_digest=digest,
            sequence=len(rows) + 1,
            created_at=datetime.now(UTC),
        )
        db.add(row)
        db.flush()
        return summary(db, row)

    def claim(
        self,
        db: Session,
        context: DraftContext,
        document_id: UUID,
        operation_id: UUID,
        reconcile: bool,
    ) -> tuple[Submission, UUID, tuple[str, ...]] | None:
        rows = self.rows(db, context, document_id)
        row = next((r for r in rows if r.id == operation_id), None)
        if row is None:
            raise ProtectedResourceNotFound()
        if self.provider is None:
            raise provider_unconfigured()
        history = calls(db, row)
        if history and not reconcile:
            return None  # A committed SEND claim must never be repeated.
        if reconcile and not history:
            raise conflict("KNOWLEDGE_NOT_SENT")
        document = self.documents.document(db, context.actor, document_id)
        if not reconcile:
            snapshot = current_settings(db, context.actor.company_id, lock=True)
            if (
                snapshot.id != row.settings_id
                or document.current_operation_id != row.command_id
                or document.current_revision_id != row.revision_id
            ):
                raise conflict("KNOWLEDGE_CONTEXT_CHANGED")
            # Preparation is not send authority: earlier evidence may have
            # changed while this explicit retry/replacement remained unsent.
            same_command = [r for r in rows if r.command_id == row.command_id]
            if same_command[-1].id != row.id or any(
                r.id != row.id and summary(db, r)["provider_write_outcome"] == "ACKNOWLEDGED"
                for r in same_command
            ):
                raise conflict("KNOWLEDGE_PRIOR_WRITE_ACKNOWLEDGED")
            # A prior uncertain write must be observed before a newer send.
            if any(
                r.id != row.id and summary(db, r)["provider_write_outcome"] == "UNKNOWN"
                for r in rows
            ):
                raise conflict("KNOWLEDGE_PRIOR_WRITE_UNKNOWN")
        revision = db.get(KnowledgeRevisionRow, row.revision_id)
        if revision is None:
            raise unavailable()
        title, version, text = _decode(revision)
        submission = Submission(
            row.id,
            row.company_id,
            row.document_id,
            row.revision_id,
            row.settings_id,
            row.settings_version,
            row.action,
            title,
            version,
            text,
        )
        if history:
            keys = tuple(json.loads(history[0].manifest_json))
        else:
            try:
                keys = self.provider.prepare(submission)
                if (
                    type(keys) is not tuple
                    or not keys
                    or any(type(k) is not str or not k for k in keys)
                    or len(set(keys)) != len(keys)
                ):
                    raise ValueError
                encoded = json.dumps(keys).encode("utf-8")
                if len(encoded) > context.maximum_request_bytes:
                    raise ValueError
            except Exception:
                raise unavailable() from None
        call = KnowledgeDispatchCallRow(
            id=uuid4(),
            company_id=row.company_id,
            document_id=row.document_id,
            dispatch_id=row.id,
            sequence=len(history) + 1,
            kind="RECONCILE" if reconcile else "SEND",
            manifest_json=json.dumps(keys).encode(),
            created_at=datetime.now(UTC),
        )
        db.add(call)
        db.flush()
        return submission, call.id, keys

    def invoke(self, claimed: tuple[Submission, UUID, tuple[str, ...]], reconcile: bool) -> object:
        submission, call_id, keys = claimed
        if self.provider is None:
            raise provider_unconfigured()
        try:
            method = self.provider.reconcile if reconcile else self.provider.send
            return method(submission, call_id, keys)
        except Exception:
            return None  # No exception text or provider response enters persistence/logs.

    def complete(self, db: Session, call_id: UUID, result: object) -> None:
        call = db.scalar(
            select(KnowledgeDispatchCallRow)
            .where(KnowledgeDispatchCallRow.id == call_id)
            .with_for_update()
        )
        if call is None:
            raise unavailable()
        row = db.get(KnowledgeDispatchRow, call.dispatch_id)
        if row is None:
            raise unavailable()
        outcome, accepted, rejected, reason = normalize(row, call, result)
        digest = hashlib.sha256(
            json.dumps(
                [
                    outcome,
                    accepted,
                    rejected,
                    reason,
                    sorted(result.results)
                    if type(result) is ProviderResult and reason == "PER_KEY_ACKNOWLEDGEMENT"
                    else None,
                ]
            ).encode()
        ).hexdigest()
        existing = receipt(db, call)
        if existing:
            if existing.payload_digest != digest:
                raise conflict("KNOWLEDGE_RECEIPT_CONFLICT")
            return
        db.add(
            KnowledgeDispatchReceiptRow(
                id=uuid4(),
                company_id=row.company_id,
                document_id=row.document_id,
                dispatch_id=row.id,
                call_id=call.id,
                outcome=outcome,
                acknowledged=accepted,
                rejected=rejected,
                reason=reason,
                payload_digest=digest,
                created_at=datetime.now(UTC),
            )
        )
        db.flush()
