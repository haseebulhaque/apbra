from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import cast

from .domain import (
    AccessRecord,
    Actor,
    ApplicationPersistence,
    AuthenticationRequired,
    CaseRecord,
    IdentityRecord,
    ProtectedResourceNotFound,
    SessionRecord,
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def resolve_session(
    db: object, session_token: str | None
) -> tuple[SessionRecord, IdentityRecord]:
    if not session_token:
        raise AuthenticationRequired()
    result = cast(ApplicationPersistence, db).active_session(
        sha256_text(session_token), datetime.now(UTC)
    )
    if result is None:
        raise AuthenticationRequired()
    return result


def resolve_identity(db: object, session_token: str | None) -> IdentityRecord:
    return resolve_session(db, session_token)[1]


def resolve_actor(db: object, session_token: str | None) -> Actor:
    session_row, identity = resolve_session(db, session_token)
    if session_row.membership_id is None:
        raise AuthenticationRequired()
    actor = cast(ApplicationPersistence, db).active_actor(session_row.membership_id, identity.id)
    if actor is None:
        raise AuthenticationRequired()
    return actor


def authorized_case_access(
    db: object, actor: Actor, case_id: object, *, require_edit: bool = False
) -> tuple[CaseRecord, AccessRecord]:
    pair = cast(ApplicationPersistence, db).case_access(actor, case_id)
    if pair is None:
        raise ProtectedResourceNotFound()
    case, access = pair
    if require_edit and access.access_level not in {"OWNER", "EDITOR"}:
        raise ProtectedResourceNotFound()
    return case, access
