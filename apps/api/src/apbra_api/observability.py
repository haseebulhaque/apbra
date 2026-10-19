"""Tenant-bound audit projections and immutable, content-free error occurrences.

Writes join the caller's transaction. No commit, retry, retention or external logging
is performed here. Request handlers decide how to handle a failed diagnostic write.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select

from .domain import Actor, ApplicationError, Forbidden, ProtectedResourceNotFound, Role
from .model_provider import ProviderCallError
from .persistence import (
    ApplicationSession,
    AuditEventRow,
    SystemErrorDiagnosticRow,
    SystemErrorRow,
)
from .provider_diagnostics import safe_provider_diagnostic

CURRENT_CORRELATION: ContextVar[UUID | None] = ContextVar("apbra_correlation", default=None)
MODULES = frozenset({"Identity", "Company", "Reports", "Settings", "Documents", "API", "Other"})
MESSAGES = {
    "VALIDATION": (
        "The request could not be processed. Review its inputs or contact your administrator."
    ),
    "ACCESS": "The operation was rejected because access was unavailable.",
    "CONFLICT": "The operation conflicted with the current state. Refresh before trying again.",
    "PROVIDER": "A required service did not complete the operation. Contact your administrator.",
    "INTERNAL": "The system could not complete the operation. Contact your administrator.",
}
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,99}\Z")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}\Z")
# Only these structural audit details are exposed; arbitrary historical JSON is not a public log.
_UUID_DETAILS = frozenset(
    {
        "artifact_id",
        "membership_id",
        "identity_id",
        "request_version_id",
        "case_id",
        "settings_version_id",
        "document_id",
        "revision_id",
        "invitation_id",
        "correlation_id",
    }
)
_HASH_DETAILS = frozenset({"digest", "content_digest", "payload_digest"})
_INT_DETAILS = frozenset({"version", "settings_version", "revision", "byte_size"})


class HistoryQueryInvalid(ApplicationError):
    status_code = 422
    code = "HISTORY_QUERY_INVALID"
    public_message = "The history query is invalid. Refresh the filters and try again."


@dataclass(frozen=True)
class HistoryFilters:
    from_time: datetime | None = None
    to_time: datetime | None = None
    module: str | None = None
    actor_id: UUID | None = None
    operation: str | None = None
    outcome: str | None = None
    support_reference: UUID | None = None
    limit: int = 50
    cursor: str | None = None

    def __post_init__(self) -> None:
        if type(self.limit) is not int or not 1 <= self.limit <= 100:
            raise ValueError("History limit must be between 1 and 100")
        for name in ("from_time", "to_time"):
            value = getattr(self, name)
            if value is not None:
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError("History timestamps require a timezone")
                object.__setattr__(self, name, value.astimezone(UTC))
        if self.from_time and self.to_time and self.from_time > self.to_time:
            raise ValueError("History time range is invalid")
        if self.module is not None and self.module not in MODULES:
            raise ValueError("History module is invalid")
        if self.operation is not None and not _CODE.fullmatch(self.operation):
            raise ValueError("History operation is invalid")
        if self.outcome not in {None, "SUCCEEDED", "FAILED", "REJECTED", "UNSPECIFIED"}:
            raise ValueError("History outcome is invalid")
        if self.cursor is not None and len(self.cursor) > 2048:
            raise ValueError("History cursor is invalid")


def _category(error: Exception) -> tuple[str, str]:
    if isinstance(error, ProviderCallError):
        return "PROVIDER", "PROVIDER_OPERATION_FAILED"
    cls = type(error)
    # Application exceptions own static codes. Instance args/code/message are never inspected.
    if isinstance(error, ApplicationError) and cls.__module__ in {
        "apbra_api.domain",
        "apbra_api.observability",
    }:
        status = type(error).status_code
        category = (
            "ACCESS"
            if status in {401, 403, 404}
            else "CONFLICT"
            if status == 409
            else "PROVIDER"
            if status >= 500
            else "VALIDATION"
        )
        code = type(error).code
        if type(code) is str and _CODE.fullmatch(code):
            return category, code
    return "INTERNAL", "SYSTEM_OPERATION_FAILED"


def diagnostic_json(error: Exception) -> tuple[str, bool]:
    """Structural frames only; never format exception values or traceback source lines."""
    name = type(error).__name__
    frames: list[dict[str, Any]] = []
    total = 0
    trace = error.__traceback__
    while trace is not None:
        total += 1
        module = trace.tb_frame.f_globals.get("__name__", "unknown")
        module = module.rsplit(".", 1)[-1] if isinstance(module, str) else "unknown"
        function = trace.tb_frame.f_code.co_name
        frames.append(
            {
                "module": module if _NAME.fullmatch(module) else "unknown",
                "function": function if _NAME.fullmatch(function) else "unknown",
                "line": trace.tb_lineno,
            }
        )
        frames = frames[-8:]
        trace = trace.tb_next
    payload: dict[str, Any] = {
        "exception_type": name if _NAME.fullmatch(name) else "Exception", "frames": frames
    }
    causes: list[dict[str, Any]] = []
    cause_frames_truncated = False
    cause = error.__cause__
    visited = {id(error)}
    while cause is not None and len(causes) < 2 and id(cause) not in visited:
        visited.add(id(cause))
        cause_name = type(cause).__name__
        cause_frames = []
        cause_trace = cause.__traceback__
        cause_total = 0
        while cause_trace is not None:
            cause_total += 1
            module = cause_trace.tb_frame.f_globals.get("__name__", "unknown")
            module = module.rsplit(".", 1)[-1] if isinstance(module, str) else "unknown"
            function = cause_trace.tb_frame.f_code.co_name
            cause_frames.append({
                "module": module if _NAME.fullmatch(module) else "unknown",
                "function": function if _NAME.fullmatch(function) else "unknown",
                "line": cause_trace.tb_lineno,
            })
            cause_frames = cause_frames[-3:]
            cause_trace = cause_trace.tb_next
        cause_frames_truncated = cause_frames_truncated or cause_total > 3
        causes.append({
            "exception_type": cause_name if _NAME.fullmatch(cause_name) else "Exception",
            "frames": cause_frames,
        })
        cause = cause.__cause__
    if causes:
        payload["causes"] = causes
    cause_frames_truncated = cause_frames_truncated or cause is not None
    provider = safe_provider_diagnostic(getattr(error, "diagnostic", None))
    details = getattr(error, "audit_details", None)
    if not provider and isinstance(details, dict):
        provider = safe_provider_diagnostic(details.get("provider_diagnostic"))
    if provider:
        payload["provider"] = provider
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    truncated = total > 8 or cause_frames_truncated
    while len(encoded.encode("utf-8")) > 4096:
        frames.pop(0)
        truncated = True
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return encoded, truncated


def error_reference(
    db: ApplicationSession,
    company_id: UUID,
    source_kind: str,
    source_id: UUID,
) -> UUID | None:
    return db.scalar(
        select(SystemErrorRow.id).where(
            SystemErrorRow.company_id == company_id,
            SystemErrorRow.source_kind == source_kind,
            SystemErrorRow.source_id == source_id,
        )
    )


def record_system_error(
    db: ApplicationSession,
    actor: Actor,
    case_id: UUID | None,
    operation: str,
    error: Exception,
    *,
    source_kind: str | None = None,
    source_id: UUID | None = None,
    module: str = "Reports",
    correlation_id: UUID | None = None,
) -> UUID:
    if module not in MODULES or not _CODE.fullmatch(operation):
        raise ValueError("Invalid error metadata")
    if (source_kind is None) != (source_id is None) or source_kind not in {
        None,
        "AUTOMATIC_DESIGN",
        "GENERATION",
        "INTERPRETATION",
    }:
        raise ValueError("Invalid error source")
    if source_kind is not None and source_id is not None:
        existing = error_reference(db, actor.company_id, source_kind, source_id)
        if existing is not None:
            return existing
    category, code = _category(error)
    reference = uuid4()
    technical_json, truncated = diagnostic_json(error)
    db.add(
        SystemErrorRow(
            id=reference,
            company_id=actor.company_id,
            actor_membership_id=actor.membership_id,
            case_id=case_id,
            occurred_at=datetime.now(UTC),
            module=module,
            operation=operation,
            category=category,
            safe_code=code,
            message=MESSAGES[category],
            outcome="REJECTED" if category in {"ACCESS", "VALIDATION", "CONFLICT"} else "FAILED",
            correlation_id=correlation_id or CURRENT_CORRELATION.get() or uuid4(),
            source_kind=source_kind,
            source_id=source_id,
        )
    )
    # Flush occurrence first: no ORM relationship is needed to order the diagnostic insert.
    db.flush()
    db.add(
        SystemErrorDiagnosticRow(
            error_id=reference,
            company_id=actor.company_id,
            technical_json=technical_json,
            truncated=truncated,
        )
    )
    db.flush()
    return reference


def _authorize(db: ApplicationSession, actor: Actor, case_id: UUID | None = None) -> Actor:
    current = db.active_actor(actor.membership_id, actor.identity_id)
    if current is None or current.company_id != actor.company_id:
        raise Forbidden()
    if case_id is None:
        if current.role not in {Role.COMPANY_ADMIN, Role.COMPANY_OWNER}:
            raise Forbidden()
    elif db.case_access(current, case_id) is None:
        raise ProtectedResourceNotFound()
    return current


def _audit_module(operation: str) -> str:
    if operation.startswith(("MEMBERSHIP", "INVITATION", "COMPANY", "PROFILE")):
        return "Company"
    if operation.startswith(("TENANT_SETTINGS", "SETTINGS", "SECRET")):
        return "Settings"
    if operation.startswith(("KNOWLEDGE", "DOCUMENT")):
        return "Documents"
    if operation.startswith(("AUTH", "SESSION", "SIGN")):
        return "Identity"
    if operation.startswith(
        (
            "CASE",
            "GENERATION",
            "AUTOMATIC",
            "DESIGN",
            "INTERPRETATION",
            "REPORT",
            "EVIDENCE",
            "CLARIFICATION",
            "CONTRACT",
            "REFERENCE",
        )
    ):
        return "Reports"
    return "Other"


def _audit_details(raw: str) -> dict[str, Any]:
    if len(raw.encode("utf-8")) > 4096:
        return {}
    try:
        details = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(details, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, value in details.items():
        if (
            key == "stage" and isinstance(value, str)
            and value in {"PROVIDER_CALL", "SEMANTIC_VALIDATION"}
        ):
            safe[key] = value
        elif key == "error_code" and isinstance(value, str) and value in {
            "MODEL_PROVIDER_REJECTED", "MODEL_PROVIDER_TRANSIENT_FAILURE", "MODEL_PROVIDER_TIMEOUT",
            "MODEL_PROVIDER_FAILED", "MODEL_CANDIDATE_REJECTED", "MODEL_OUTPUT_INVALID",
            "MODEL_SCHEMA_UNSUPPORTED", "MODEL_INPUT_BUDGET_EXCEEDED", "MODEL_TIME_BUDGET_EXCEEDED",
            "MODEL_RETRY_INSTRUCTION_INVALID", "SEMANTIC_VALIDATION_FAILED",
            "FAKE_PROVIDER_EXHAUSTED",
        }:
            safe[key] = value
        elif key == "call_count" and type(value) is int and 0 <= value <= 20:
            safe[key] = value
        elif key in _UUID_DETAILS and isinstance(value, str):
            try:
                safe[key] = str(UUID(value))
            except ValueError:
                pass
        elif (
            key in _HASH_DETAILS and isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value)
        ):
            safe[key] = value
        elif key in _INT_DETAILS and type(value) is int and 0 <= value <= 2**63 - 1:
            safe[key] = value
        elif (
            key in {"role", "previous_role"}
            and isinstance(value, str)
            and value in {r.value for r in Role}
        ):
            safe[key] = value
        elif (
            key == "outcome"
            and isinstance(value, str)
            and value in {"SUCCEEDED", "FAILED", "REJECTED"}
        ):
            safe[key] = value
    return safe


def _audit_item(row: AuditEventRow) -> dict[str, Any]:
    details = _audit_details(row.details_json)
    return {
        "id": str(row.id),
        "occurred_at": row.created_at.isoformat(),
        "module": _audit_module(row.event_type),
        "operation": row.event_type,
        "outcome": details.get("outcome", "UNSPECIFIED"),
        "actor_id": str(row.actor_membership_id),
        "target_type": row.resource_type,
        "target_id": str(row.resource_id),
        "correlation_id": details.get("correlation_id"),
        "details": details,
    }


def _error_item(row: SystemErrorRow) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "support_reference": str(row.id),
        "occurred_at": row.occurred_at.isoformat(),
        "module": row.module,
        "operation": row.operation,
        "outcome": row.outcome,
        "actor_id": str(row.actor_membership_id),
        "target_type": "REPORT" if row.case_id else row.module,
        "target_id": str(row.case_id) if row.case_id else None,
        "category": row.category,
        "safe_code": row.safe_code,
        "message": row.message,
        "correlation_id": str(row.correlation_id),
        "case_id": str(row.case_id) if row.case_id else None,
        "source_kind": row.source_kind,
        "source_id": str(row.source_id) if row.source_id else None,
    }


def _binding(actor: Actor, filters: HistoryFilters, case_id: UUID | None, kind: str) -> str:
    values = {
        "company": str(actor.company_id),
        "case": str(case_id) if case_id else None,
        "kind": kind,
        "from": filters.from_time.isoformat() if filters.from_time else None,
        "to": filters.to_time.isoformat() if filters.to_time else None,
        "module": filters.module,
        "actor": str(filters.actor_id) if filters.actor_id else None,
        "operation": filters.operation,
        "outcome": filters.outcome,
        "support": str(filters.support_reference) if filters.support_reference else None,
        "limit": filters.limit,
    }
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def _cursor_encode(position: tuple[datetime, UUID], binding: str, secret: str) -> str:
    payload = json.dumps(
        [position[0].isoformat(), str(position[1]), binding], separators=(",", ":")
    )
    signature = hmac.new(secret.encode(), b"apbra-history-v1:" + payload.encode(), hashlib.sha256)
    return base64.urlsafe_b64encode(
        payload.encode() + b"." + signature.hexdigest().encode()
    ).decode()


def _cursor_decode(value: str, binding: str, secret: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.b64decode(value, altchars=b"-_", validate=True)
        payload, signature = raw.rsplit(b".", 1)
        expected = hmac.new(
            secret.encode(), b"apbra-history-v1:" + payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected.encode()):
            raise ValueError
        timestamp, identifier, scope = json.loads(payload)
        if scope != binding:
            raise ValueError
        occurred_at = datetime.fromisoformat(timestamp)
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError
        return occurred_at.astimezone(UTC), UUID(identifier)
    except (ValueError, TypeError, UnicodeError, KeyError) as exc:
        raise ValueError("History cursor is invalid") from exc


def _conditions(
    model: Any,
    time_column: Any,
    actor: Actor,
    filters: HistoryFilters,
    case_id: UUID | None,
    kind: str,
    secret: str,
) -> tuple[list[Any], str]:
    conditions = [model.company_id == actor.company_id]
    if filters.from_time:
        conditions.append(time_column >= filters.from_time)
    if filters.to_time:
        conditions.append(time_column <= filters.to_time)
    if filters.actor_id:
        conditions.append(model.actor_membership_id == filters.actor_id)
    if filters.operation:
        conditions.append(
            (model.event_type if kind == "audit" else model.operation) == filters.operation
        )
    if case_id is not None:
        conditions.append(model.case_id == case_id)
    if kind == "errors":
        if filters.module:
            conditions.append(model.module == filters.module)
        if filters.outcome:
            conditions.append(model.outcome == filters.outcome)
        if filters.support_reference:
            conditions.append(model.id == filters.support_reference)
    binding = _binding(actor, filters, case_id, kind)
    if filters.cursor:
        try:
            timestamp, identifier = _cursor_decode(filters.cursor, binding, secret)
        except ValueError:
            raise HistoryQueryInvalid() from None
        conditions.append(
            or_(time_column < timestamp, and_(time_column == timestamp, model.id < identifier))
        )
    return conditions, binding


def list_audit(
    db: ApplicationSession,
    actor: Actor,
    filters: HistoryFilters,
    *,
    cursor_secret: str,
) -> dict[str, Any]:
    _authorize(db, actor)
    if filters.support_reference:
        raise HistoryQueryInvalid()
    conditions, binding = _conditions(
        AuditEventRow,
        AuditEventRow.created_at,
        actor,
        filters,
        None,
        "audit",
        cursor_secret,
    )
    # Derive modules from controlled event prefixes in SQL, before the bounded LIMIT.
    if filters.module:
        from sqlalchemy import case

        conditions.append(
            case(
                *[
                    (AuditEventRow.event_type.like(prefix + "%"), _audit_module(prefix))
                    for prefix in (
                        "MEMBERSHIP",
                        "INVITATION",
                        "COMPANY",
                        "PROFILE",
                        "TENANT_SETTINGS",
                        "SETTINGS",
                        "SECRET",
                        "KNOWLEDGE",
                        "DOCUMENT",
                        "AUTH",
                        "SESSION",
                        "SIGN",
                        "CASE",
                        "GENERATION",
                        "AUTOMATIC",
                        "DESIGN",
                        "INTERPRETATION",
                        "REPORT",
                        "EVIDENCE",
                        "CLARIFICATION",
                        "CONTRACT",
                        "REFERENCE",
                    )
                ],
                else_="Other",
            )
            == filters.module
        )
    rows = list(
        db.scalars(
            select(AuditEventRow)
            .where(*conditions)
            .order_by(AuditEventRow.created_at.desc(), AuditEventRow.id.desc())
            .limit(filters.limit + 1)
        )
    )
    page = rows[: filters.limit]
    return {
        "company_id": str(actor.company_id),
        # Bounded scans can yield sparse pages for legacy JSON outcome filters.
        "items": [
            item
            for row in page
            if (item := _audit_item(row))
            and (filters.outcome is None or item["outcome"] == filters.outcome)
        ],
        "next_cursor": _cursor_encode((page[-1].created_at, page[-1].id), binding, cursor_secret)
        if len(rows) > filters.limit
        else None,
    }


def audit_detail(db: ApplicationSession, actor: Actor, event_id: UUID) -> dict[str, Any]:
    _authorize(db, actor)
    row = db.scalar(
        select(AuditEventRow).where(
            AuditEventRow.company_id == actor.company_id,
            AuditEventRow.id == event_id,
        )
    )
    if row is None:
        raise ProtectedResourceNotFound()
    return _audit_item(row)


def list_errors(
    db: ApplicationSession,
    actor: Actor,
    filters: HistoryFilters,
    case_id: UUID | None = None,
    *,
    cursor_secret: str,
) -> dict[str, Any]:
    _authorize(db, actor, case_id)
    conditions, binding = _conditions(
        SystemErrorRow,
        SystemErrorRow.occurred_at,
        actor,
        filters,
        case_id,
        "errors",
        cursor_secret,
    )
    rows = list(
        db.scalars(
            select(SystemErrorRow)
            .where(*conditions)
            .order_by(SystemErrorRow.occurred_at.desc(), SystemErrorRow.id.desc())
            .limit(filters.limit + 1)
        )
    )
    page = rows[: filters.limit]
    return {
        "company_id": str(actor.company_id),
        "case_id": str(case_id) if case_id else None,
        "items": [_error_item(row) for row in page],
        "next_cursor": _cursor_encode((page[-1].occurred_at, page[-1].id), binding, cursor_secret)
        if len(rows) > filters.limit
        else None,
    }


def _safe_diagnostic(raw: str, truncated: bool) -> dict[str, Any] | None:
    if len(raw.encode("utf-8")) > 4096:
        return None
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    name, frames = payload.get("exception_type"), payload.get("frames")
    if not isinstance(name, str) or not _NAME.fullmatch(name) or not isinstance(frames, list):
        return None
    if len(frames) > 8:
        return None
    safe_frames = []
    for frame in frames:
        if not isinstance(frame, dict):
            return None
        module, function, line = frame.get("module"), frame.get("function"), frame.get("line")
        if (
            not isinstance(module, str)
            or not _NAME.fullmatch(module)
            or not isinstance(function, str)
            or not _NAME.fullmatch(function)
            or type(line) is not int
            or not 0 <= line <= 2**31 - 1
        ):
            return None
        safe_frames.append({"module": module, "function": function, "line": line})
    safe_causes = []
    causes = payload.get("causes")
    if isinstance(causes, list):
        for cause in causes[:2]:
            if not isinstance(cause, dict):
                continue
            # Deliberately discard nested causes, messages and all unknown fields.
            projected = {key: cause.get(key) for key in ("exception_type", "frames")}
            checked = _safe_diagnostic(json.dumps(projected), False)
            if checked:
                safe_causes.append(checked["diagnostic"])
    return {
        "diagnostic": {
            "exception_type": name, "frames": safe_frames,
            **({"causes": safe_causes} if safe_causes else {}),
            **({"provider": provider} if (
                provider := safe_provider_diagnostic(payload.get("provider"))
            ) else {}),
        },
        "truncated": bool(truncated),
    }


def error_detail(
    db: ApplicationSession,
    actor: Actor,
    error_id: UUID,
    case_id: UUID | None = None,
    *,
    technical: bool = False,
) -> dict[str, Any]:
    current = _authorize(db, actor, case_id)
    if technical and current.role not in {Role.COMPANY_ADMIN, Role.COMPANY_OWNER}:
        raise Forbidden()
    conditions = [SystemErrorRow.company_id == actor.company_id, SystemErrorRow.id == error_id]
    if case_id is not None:
        conditions.append(SystemErrorRow.case_id == case_id)
    row = db.scalar(select(SystemErrorRow).where(*conditions))
    if row is None:
        raise ProtectedResourceNotFound()
    result = _error_item(row)
    if technical:
        diagnostic = db.scalar(
            select(SystemErrorDiagnosticRow).where(
                SystemErrorDiagnosticRow.error_id == row.id,
                SystemErrorDiagnosticRow.company_id == actor.company_id,
            )
        )
        result["technical"] = (
            _safe_diagnostic(diagnostic.technical_json, diagnostic.truncated)
            if diagnostic
            else None
        )
    return result
