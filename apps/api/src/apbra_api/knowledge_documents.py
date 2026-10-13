"""Protected local draft originals and immutable command journal; no dispatch.

This application adapter reuses the pure lifecycle unchanged. Request/session
credentials are never persisted, and original user text is never an error/log.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .authorization import resolve_actor, resolve_session
from .domain import (
    Actor,
    ApplicationError,
    AuthenticationRequired,
    Forbidden,
    ProtectedResourceNotFound,
    Role,
)
from .knowledge_lifecycle import (
    Action,
    Command,
    Journal,
    KnowledgeLifecycleError,
    Operation,
    Revision,
    begin_operation,
)
from .persistence import (
    ApplicationSession,
    KnowledgeCommandRow,
    KnowledgeDocumentRow,
    KnowledgeRevisionRow,
    SessionRow,
)
from .tenant_settings import current_settings

Kind = Literal["CREATE", "REVISION", "ARCHIVE"]


class KnowledgeDocumentsError(ApplicationError):
    def __init__(self, code: str, status: int, message: str) -> None:
        self.code = code
        self.status_code = status
        self.public_message = message
        super().__init__(code)


def invalid() -> KnowledgeDocumentsError:
    return KnowledgeDocumentsError(
        "REQUEST_VALIDATION_FAILED", 422, "The request format is invalid."
    )


def unavailable() -> KnowledgeDocumentsError:
    return KnowledgeDocumentsError(
        "KNOWLEDGE_DOCUMENTS_UNAVAILABLE",
        503,
        "Document state is unavailable. Reconcile the same command before retrying.",
    )


def conflict(code: str) -> KnowledgeDocumentsError:
    return KnowledgeDocumentsError(
        code, 409, "Document state changed. Refresh and review before retrying."
    )


def too_large() -> KnowledgeDocumentsError:
    return KnowledgeDocumentsError(
        "KNOWLEDGE_REQUEST_TOO_LARGE", 413, "The draft request exceeds the current workspace limit."
    )


def canonical_uuid(value: object) -> UUID:
    if type(value) is not str:
        raise invalid()
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise invalid() from None
    if str(parsed) != value:
        raise invalid()
    return parsed


@dataclass(frozen=True)
class DraftPayload:
    title: str = field(repr=False)
    source_version: str = field(repr=False)
    text: str = field(repr=False)
    expected_current_revision_id: UUID | None = None


def parse_payload(raw: bytes, kind: Kind) -> DraftPayload:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise invalid()
            result[key] = value
        return result

    def reject_constant(_value: str) -> None:
        raise invalid()

    try:
        decoded = json.loads(
            raw.decode("utf-8"), object_pairs_hook=object_pairs, parse_constant=reject_constant
        )
        keys = (
            {"expected_current_revision_id"}
            if kind == "ARCHIVE"
            else {"title", "source_version", "text"}
        )
        if kind == "REVISION":
            keys.add("expected_current_revision_id")
        if type(decoded) is not dict or set(decoded) != keys:
            raise invalid()
        strings = []
        for key in ("title", "source_version", "text"):
            value = "" if kind == "ARCHIVE" else decoded[key]
            if type(value) is not str:
                raise invalid()
            value.encode("utf-8", errors="strict")
            strings.append(value)
        expected = (
            None if kind == "CREATE" else canonical_uuid(decoded["expected_current_revision_id"])
        )
        return DraftPayload(strings[0], strings[1], strings[2], expected)
    except (ValueError, UnicodeError, RecursionError):
        raise invalid() from None


@dataclass(frozen=True)
class DraftContext:
    actor: Actor
    session_id: UUID
    maximum_request_bytes: int


def authorize(
    db: Session,
    session_token: str | None,
    expected: str | None,
    *,
    capabilities: bool = False,
    initial: DraftContext | None = None,
) -> DraftContext:
    """Company-first locks match membership management; never hold across body IO."""
    if not isinstance(db, ApplicationSession):
        raise unavailable()
    preliminary = resolve_actor(db, session_token)
    session_row, _ = resolve_session(db, session_token)
    if preliminary.role not in {Role.COMPANY_OWNER, Role.COMPANY_ADMIN}:
        raise Forbidden()
    expected_id = None if capabilities else canonical_uuid(expected)
    if expected_id is not None and expected_id != preliminary.membership_id:
        raise conflict("KNOWLEDGE_CONTEXT_CHANGED")
    if initial is not None and (
        preliminary.company_id != initial.actor.company_id
        or preliminary.membership_id != initial.actor.membership_id
        or preliminary.identity_id != initial.actor.identity_id
        or session_row.id != initial.session_id
    ):
        raise conflict("KNOWLEDGE_CONTEXT_CHANGED")
    # The company chosen for locking is pinned to preliminary/current context.
    db.lock_company_for_membership_management(preliminary.company_id)
    db.lock_identity_for_membership(preliminary.identity_id)
    locked_session = db.scalar(
        select(SessionRow)
        .where(SessionRow.id == session_row.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        locked_session is None
        or locked_session.revoked_at is not None
        or locked_session.expires_at <= datetime.now(UTC)
        or locked_session.identity_id != preliminary.identity_id
    ):
        raise AuthenticationRequired()
    if locked_session.membership_id != preliminary.membership_id:
        raise conflict("KNOWLEDGE_CONTEXT_CHANGED")
    actor = db.active_actor(preliminary.membership_id, preliminary.identity_id, lock=True)
    # Repeat the existing session/profile binding check on refreshed locked rows.
    resolve_session(db, session_token)
    if actor is None:
        raise AuthenticationRequired()
    if actor.company_id != preliminary.company_id or (
        expected_id is not None and actor.membership_id != expected_id
    ):
        raise conflict("KNOWLEDGE_CONTEXT_CHANGED")
    if actor.role not in {Role.COMPANY_OWNER, Role.COMPANY_ADMIN}:
        raise Forbidden()
    snapshot = current_settings(db, actor.company_id, lock=True)
    return DraftContext(actor, locked_session.id, snapshot.settings.upload_policy.max_file_bytes)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decode(row: KnowledgeRevisionRow) -> tuple[str, str, str]:
    try:
        values = (
            row.title_original.decode("utf-8"),
            row.source_version_original.decode("utf-8"),
            row.text_original.decode("utf-8"),
        )
        if len(row.text_original) != row.text_byte_count or not hmac.compare_digest(
            hashlib.sha256(row.text_original).hexdigest(), row.text_sha256
        ):
            raise unavailable()
        return values
    except (UnicodeError, AttributeError):
        raise unavailable() from None


def _revision(row: KnowledgeRevisionRow) -> Revision:
    return Revision(
        row.company_id,
        row.document_id,
        row.id,
        _decode(row)[1],
        row.creator_membership_id,
        row.predecessor_revision_id,
    )


def _command(row: KnowledgeCommandRow, revisions: dict[UUID, KnowledgeRevisionRow]) -> Command:
    action = {"CREATE": Action.UPLOAD, "REVISION": Action.UPDATE, "ARCHIVE": Action.DELETE}.get(
        row.kind
    )
    if action is None or row.target_revision_id not in revisions:
        raise unavailable()
    new_revision = None if action is Action.DELETE else _revision(revisions[row.target_revision_id])
    return Command(
        row.id,
        str(row.command_key),
        action,
        row.company_id,
        row.document_id,
        row.target_revision_id,
        row.expected_current_revision_id,
        row.payload_digest,
        new_revision,
    )


class KnowledgeDocumentsService:
    def capabilities(self, context: DraftContext) -> dict[str, Any]:
        return {
            "company_id": str(context.actor.company_id),
            "membership_id": str(context.actor.membership_id),
            "maximum_request_bytes": context.maximum_request_bytes,
            "storage": "LOCAL_DRAFT_DATABASE",
            "provider_write_outcome": "NOT_SENT",
            "indexed": False,
            "used_by_ai": False,
        }

    def document(self, db: Session, actor: Actor, document_id: UUID) -> KnowledgeDocumentRow:
        row = db.scalar(
            select(KnowledgeDocumentRow)
            .where(
                KnowledgeDocumentRow.id == document_id,
                KnowledgeDocumentRow.company_id == actor.company_id,
            )
            .with_for_update()
        )
        if row is None:
            raise ProtectedResourceNotFound()
        return row

    def rows(
        self, db: Session, document: KnowledgeDocumentRow
    ) -> tuple[list[KnowledgeRevisionRow], list[KnowledgeCommandRow]]:
        commands = list(
            db.scalars(
                select(KnowledgeCommandRow)
                .where(
                    KnowledgeCommandRow.company_id == document.company_id,
                    KnowledgeCommandRow.document_id == document.id,
                )
                .order_by(KnowledgeCommandRow.sequence)
            )
        )
        revisions = list(
            db.scalars(
                select(KnowledgeRevisionRow).where(
                    KnowledgeRevisionRow.company_id == document.company_id,
                    KnowledgeRevisionRow.document_id == document.id,
                )
            )
        )
        return revisions, commands

    def journal(self, db: Session, document: KnowledgeDocumentRow) -> Journal:
        revisions, commands = self.rows(db, document)
        by_id = {row.id: row for row in revisions}
        operations = tuple(
            Operation(_command(row, by_id), row.initiator_identity_id, row.initiator_membership_id)
            for row in commands
        )
        revision_order = tuple(
            operation.command.new_revision
            for operation in operations
            if operation.command.new_revision is not None
        )
        tombstones = tuple(
            dict.fromkeys(row.target_revision_id for row in commands if row.kind == "ARCHIVE")
        )
        return Journal(
            document.company_id,
            document.id,
            revision_order,
            operations,
            document.current_revision_id,
            document.current_operation_id,
            tombstones,
        )

    def revision_metadata(self, row: KnowledgeRevisionRow, archived: bool) -> dict[str, Any]:
        title, version, _ = _decode(row)
        return {
            "revision_id": str(row.id),
            "predecessor_revision_id": str(row.predecessor_revision_id)
            if row.predecessor_revision_id
            else None,
            "title": title,
            "source_version": version,
            "text_sha256": row.text_sha256,
            "text_byte_count": row.text_byte_count,
            "created_at": _iso(row.created_at),
            "local_state": "LOCAL_ARCHIVAL_REQUESTED" if archived else "LOCAL_DRAFT",
            "provider_write_outcome": "NOT_SENT",
            "used_by_ai": False,
        }

    def context(self, db: Session, document: KnowledgeDocumentRow) -> dict[str, Any]:
        revisions, commands = self.rows(db, document)
        current = next((r for r in revisions if r.id == document.current_revision_id), None)
        latest = next((c for c in commands if c.id == document.current_operation_id), None)
        if current is None or latest is None:
            raise unavailable()
        archived = latest.kind == "ARCHIVE"
        return {
            "company_id": str(document.company_id),
            "document_id": str(document.id),
            "current_revision_id": str(document.current_revision_id),
            "current_operation_id": str(document.current_operation_id),
            "current_revision": self.revision_metadata(current, archived),
            "local_state": "LOCAL_ARCHIVAL_REQUESTED" if archived else "LOCAL_DRAFT",
            "provider_write_outcome": "NOT_SENT",
            "used_by_ai": False,
        }

    def command_result(self, row: KnowledgeCommandRow) -> dict[str, Any]:
        return {
            "command_key": str(row.command_key),
            "operation_id": str(row.id),
            "document_id": str(row.document_id),
            "kind": row.kind,
            "target_revision_id": str(row.target_revision_id),
            "expected_current_revision_id": str(row.expected_current_revision_id)
            if row.expected_current_revision_id
            else None,
            "created_at": _iso(row.created_at),
            "provider_write_outcome": "NOT_SENT",
        }

    def list(self, db: Session, context: DraftContext) -> dict[str, Any]:
        rows = db.scalars(
            select(KnowledgeDocumentRow)
            .where(KnowledgeDocumentRow.company_id == context.actor.company_id)
            .order_by(KnowledgeDocumentRow.created_at, KnowledgeDocumentRow.id)
        )
        return {
            "company_id": str(context.actor.company_id),
            "items": [self.context(db, row) for row in rows],
        }

    def detail(self, db: Session, context: DraftContext, document_id: UUID) -> dict[str, Any]:
        return self.context(db, self.document(db, context.actor, document_id))

    def history(self, db: Session, context: DraftContext, document_id: UUID) -> dict[str, Any]:
        document = self.document(db, context.actor, document_id)
        revisions, commands = self.rows(db, document)
        by_id = {row.id: row for row in revisions}
        archived = {row.target_revision_id for row in commands if row.kind == "ARCHIVE"}
        ordered = [by_id[row.target_revision_id] for row in commands if row.kind != "ARCHIVE"]
        return {
            "company_id": str(context.actor.company_id),
            "document": self.context(db, document),
            "revisions": [self.revision_metadata(row, row.id in archived) for row in ordered],
            "operations": [self.command_result(row) for row in commands],
        }

    def original(
        self, db: Session, context: DraftContext, document_id: UUID, revision_id: UUID
    ) -> dict[str, Any]:
        self.document(db, context.actor, document_id)
        row = db.scalar(
            select(KnowledgeRevisionRow).where(
                KnowledgeRevisionRow.id == revision_id,
                KnowledgeRevisionRow.document_id == document_id,
                KnowledgeRevisionRow.company_id == context.actor.company_id,
            )
        )
        if row is None:
            raise ProtectedResourceNotFound()
        title, version, text = _decode(row)
        return {
            "company_id": str(row.company_id),
            "document_id": str(row.document_id),
            "revision_id": str(row.id),
            "title": title,
            "source_version": version,
            "text": text,
            "text_sha256": row.text_sha256,
            "text_byte_count": row.text_byte_count,
            "created_at": _iso(row.created_at),
        }

    def reconcile(self, db: Session, context: DraftContext, key: UUID) -> dict[str, Any]:
        row = db.scalar(
            select(KnowledgeCommandRow).where(
                KnowledgeCommandRow.company_id == context.actor.company_id,
                KnowledgeCommandRow.command_key == key,
                KnowledgeCommandRow.initiator_identity_id == context.actor.identity_id,
            )
        )
        if row is None:
            foreign = db.scalar(
                select(KnowledgeCommandRow.id)
                .where(
                    KnowledgeCommandRow.company_id == context.actor.company_id,
                    KnowledgeCommandRow.command_key == key,
                )
                .limit(1)
            )
            if foreign is not None:
                raise ProtectedResourceNotFound()
        if row is not None and (
            row.initiator_identity_id != context.actor.identity_id
            or row.initiator_membership_id != context.actor.membership_id
        ):
            raise ProtectedResourceNotFound()
        return {
            "company_id": str(context.actor.company_id),
            "reconciliation": "COMMITTED" if row is not None else "NOT_OBSERVED",
            "command": self.command_result(row) if row is not None else None,
            "document": self.detail(db, context, row.document_id) if row is not None else None,
        }

    def apply(
        self,
        db: Session,
        context: DraftContext,
        kind: Kind,
        key: UUID,
        document_id: UUID | None,
        payload: DraftPayload,
    ) -> dict[str, Any]:
        actor = context.actor
        digest = hashlib.sha256(
            json.dumps(
                {
                    "schema": "LOCAL_DRAFT_COMMAND_V1",
                    "kind": kind,
                    "document_id": str(document_id) if document_id else None,
                    "expected_current_revision_id": str(payload.expected_current_revision_id)
                    if payload.expected_current_revision_id
                    else None,
                    "title": payload.title,
                    "source_version": payload.source_version,
                    "text": payload.text,
                    "company_id": str(actor.company_id),
                    "identity_id": str(actor.identity_id),
                    "membership_id": str(actor.membership_id),
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode()
        ).hexdigest()
        existing = db.scalar(
            select(KnowledgeCommandRow).where(
                KnowledgeCommandRow.company_id == actor.company_id,
                KnowledgeCommandRow.command_key == key,
            )
        )
        if existing is not None:
            if (
                existing.initiator_identity_id != actor.identity_id
                or existing.initiator_membership_id != actor.membership_id
                or not hmac.compare_digest(existing.payload_digest, digest)
            ):
                raise conflict("KNOWLEDGE_COMMAND_CONFLICT")
            document = self.document(db, actor, existing.document_id)
            revisions, _ = self.rows(db, document)
            try:
                begin_operation(
                    self.journal(db, document),
                    actor,
                    _command(existing, {r.id: r for r in revisions}),
                )
            except KnowledgeLifecycleError:
                raise unavailable() from None
            return {
                "company_id": str(actor.company_id),
                "disposition": "REPLAY",
                "command": self.command_result(existing),
                "document": self.context(db, document),
            }
        if kind == "CREATE":
            document = KnowledgeDocumentRow(
                id=uuid4(),
                company_id=actor.company_id,
                current_revision_id=None,
                current_operation_id=None,
                created_at=datetime.now(UTC),
            )
            journal = Journal(actor.company_id, document.id)
        else:
            if document_id is None:
                raise invalid()
            document = self.document(db, actor, document_id)
            journal = self.journal(db, document)
        new_id = payload.expected_current_revision_id if kind == "ARCHIVE" else uuid4()
        if new_id is None:
            raise invalid()
        new_revision = (
            None
            if kind == "ARCHIVE"
            else Revision(
                actor.company_id,
                document.id,
                new_id,
                payload.source_version,
                actor.membership_id,
                payload.expected_current_revision_id,
            )
        )
        command = Command(
            uuid4(),
            str(key),
            {"CREATE": Action.UPLOAD, "REVISION": Action.UPDATE, "ARCHIVE": Action.DELETE}[kind],
            actor.company_id,
            document.id,
            new_id,
            payload.expected_current_revision_id,
            digest,
            new_revision,
        )
        try:
            result = begin_operation(journal, actor, command)
        except KnowledgeLifecycleError as exc:
            raise conflict(exc.code.value) from None
        if kind == "CREATE":
            db.add(document)
            db.flush()
        if new_revision is not None:
            text_bytes = payload.text.encode("utf-8")
            db.add(
                KnowledgeRevisionRow(
                    id=new_id,
                    document_id=document.id,
                    company_id=actor.company_id,
                    predecessor_revision_id=payload.expected_current_revision_id,
                    creator_membership_id=actor.membership_id,
                    creator_identity_id=actor.identity_id,
                    title_original=payload.title.encode("utf-8"),
                    source_version_original=payload.source_version.encode("utf-8"),
                    text_original=text_bytes,
                    text_sha256=hashlib.sha256(text_bytes).hexdigest(),
                    text_byte_count=len(text_bytes),
                    created_at=datetime.now(UTC),
                )
            )
            db.flush()
        row = KnowledgeCommandRow(
            id=command.operation_id,
            company_id=actor.company_id,
            document_id=document.id,
            command_key=key,
            initiator_identity_id=actor.identity_id,
            initiator_membership_id=actor.membership_id,
            kind=kind,
            target_revision_id=new_id,
            expected_current_revision_id=payload.expected_current_revision_id,
            payload_digest=digest,
            sequence=len(result.journal.operations),
            created_at=datetime.now(UTC),
        )
        db.add(row)
        db.flush()
        document.current_revision_id = result.journal.current_revision_id
        document.current_operation_id = result.journal.current_operation_id
        db.flush()
        return {
            "company_id": str(actor.company_id),
            "disposition": "APPLIED",
            "command": self.command_result(row),
            "document": self.context(db, document),
        }
