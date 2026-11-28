"""Explicit native principal and parent-bound workspace credentials.

The compatibility identity table keeps existing membership/audit foreign keys.
Native principals have NO external issuer or subject. Email never links them.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, mapped_column

from .application import CompanyService
from .auth_boundary import SESSION_COOKIE, digest
from .domain import AuthenticationRequired, CompanyCreationNotAvailable
from .password_auth import PasswordAccountRow, PasswordSessionRow
from .persistence import (
    ApplicationSession,
    Base,
    CompanyRow,
    ExternalIdentityRow,
    MembershipRow,
    SessionIdentityContactRow,
    SessionRow,
    utcnow,
)

# An authentication-method label, never a configured federation provider.
NATIVE_METHOD = "native-password"


class NativeAccountPrincipalRow(Base):
    __tablename__ = "native_account_principals"
    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_identities.id"), primary_key=True
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("password_accounts.id"), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NativeWorkspaceSessionRow(Base):
    __tablename__ = "native_workspace_sessions"
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("application_sessions.id"), primary_key=True
    )
    parent_digest: Mapped[str] = mapped_column(
        String(64), ForeignKey("password_sessions.digest"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def lock_accounts(db: ApplicationSession, ids: Iterable[UUID]) -> dict[UUID, PasswordAccountRow]:
    rows = db.scalars(
        select(PasswordAccountRow)
        .where(PasswordAccountRow.id.in_(set(ids)))
        .order_by(PasswordAccountRow.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return {row.id: row for row in rows}


def live_parent(parent: PasswordSessionRow, account: PasswordAccountRow, now: datetime) -> bool:
    return (
        account.active
        and parent.account_id == account.id
        and parent.epoch == account.epoch
        and parent.revoked_at is None
        and parent.expires_at > now
        and parent.touched_at + timedelta(minutes=30) > now
    )


def native_parent(
    db: ApplicationSession, session: SessionRow, identity: ExternalIdentityRow, now: datetime
) -> PasswordSessionRow | None:
    """Serialize every native workspace credential with password reset, rotation and logout."""
    workspace = db.get(NativeWorkspaceSessionRow, session.id)
    binding = db.get(NativeAccountPrincipalRow, identity.id)
    if workspace is None or binding is None:
        return None
    account = lock_accounts(db, [binding.account_id]).get(binding.account_id)
    parent = db.get(
        PasswordSessionRow, workspace.parent_digest, with_for_update=True, populate_existing=True
    )
    row = db.get(SessionRow, session.id, with_for_update=True, populate_existing=True)
    current = db.get(ExternalIdentityRow, identity.id, populate_existing=True)
    now = max(now, utcnow())
    if (
        account is None
        or parent is None
        or row is None
        or current is None
        or not live_parent(parent, account, now)
        or row.identity_id != current.id
        or row.provider_profile_id != NATIVE_METHOD
        or not current.active
        or current.provider_profile_id != NATIVE_METHOD
        or current.issuer is not None
        or current.subject is not None
        or row.revoked_at is not None
        or row.expires_at <= now
    ):
        return None
    parent.touched_at = now
    return parent


def principal(
    db: ApplicationSession,
    account: PasswordAccountRow,
    *,
    create: bool = False,
) -> ExternalIdentityRow | None:
    binding = db.scalar(
        select(NativeAccountPrincipalRow).where(NativeAccountPrincipalRow.account_id == account.id)
    )
    if binding is None:
        if not create:
            return None
        # Callers hold the immutable account row lock, including first insertion.
        new_identity = ExternalIdentityRow(
            provider_profile_id=NATIVE_METHOD,
            issuer=None,
            subject=None,
            display_name="APBRA user",
            active=True,
        )
        db.add(new_identity)
        db.flush()
        db.add(NativeAccountPrincipalRow(identity_id=new_identity.id, account_id=account.id))
        db.flush()
        return new_identity
    identity = db.get(ExternalIdentityRow, binding.identity_id)
    if (
        identity is None
        or not identity.active
        or identity.issuer is not None
        or identity.subject is not None
        or identity.provider_profile_id != NATIVE_METHOD
    ):
        raise AuthenticationRequired()
    return identity


def memberships(db: ApplicationSession, identity: ExternalIdentityRow) -> list[MembershipRow]:
    return list(
        db.scalars(
            select(MembershipRow)
            .join(CompanyRow)
            .where(
                MembershipRow.identity_id == identity.id,
                MembershipRow.active.is_(True),
                CompanyRow.active.is_(True),
            )
            .order_by(MembershipRow.created_at, MembershipRow.id)
        )
    )


def check_existing_workspace(
    db: ApplicationSession,
    parent: PasswordSessionRow,
    raw: str | None,
) -> SessionRow | None:
    if not raw:
        return None
    row = db.scalar(select(SessionRow).where(SessionRow.token_digest == digest(raw)))
    now = utcnow()
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        return None
    binding = db.get(NativeWorkspaceSessionRow, row.id)
    if binding is None:
        raise CompanyCreationNotAvailable()
    if binding.parent_digest != parent.digest:
        # Never take another account's lock while holding the caller's parent.
        other = db.get(PasswordSessionRow, binding.parent_digest)
        other_account = db.get(PasswordAccountRow, other.account_id) if other else None
        if other and other_account and live_parent(other, other_account, now):
            raise CompanyCreationNotAvailable()
        return None
    row = db.get_one(SessionRow, row.id, with_for_update=True, populate_existing=True)
    principal_binding = db.get(NativeAccountPrincipalRow, row.identity_id)
    if (
        row.revoked_at is not None
        or row.expires_at <= utcnow()
        or row.provider_profile_id != NATIVE_METHOD
        or principal_binding is None
        or principal_binding.account_id != parent.account_id
    ):
        raise CompanyCreationNotAvailable()
    return row


def issue_workspace(
    db: ApplicationSession,
    parent: PasswordSessionRow,
    account: PasswordAccountRow,
    identity: ExternalIdentityRow,
    membership_id: UUID | None,
) -> tuple[str, SessionRow]:
    token = secrets.token_urlsafe(48)
    row = SessionRow(
        token_digest=digest(token),
        provider_profile_id=NATIVE_METHOD,
        identity_id=identity.id,
        membership_id=membership_id,
        expires_at=parent.expires_at,
    )
    db.add(row)
    db.flush()
    db.add(NativeWorkspaceSessionRow(session_id=row.id, parent_digest=parent.digest))
    db.add(
        SessionIdentityContactRow(
            session_id=row.id,
            email=account.email,
            email_verified=True,
        )
    )
    db.flush()
    return token, row


def create_organisation(
    db: ApplicationSession,
    parent: PasswordSessionRow,
    account: PasswordAccountRow,
    name: str,
    key: str,
    current_workspace: str | None,
) -> tuple[dict[str, Any], bool, str]:
    check_existing_workspace(db, parent, current_workspace)
    existing = principal(db, account)
    previous = db.company_creation_command(existing.id, key) if existing is not None else None
    if previous is not None and db.active_company(previous.company_id, lock=True) is None:
        raise CompanyCreationNotAvailable()
    identity = existing or principal(db, account, create=True)
    assert identity is not None
    db.lock_identity_for_membership(identity.id)
    # Historical/inactive membership cannot be escaped through new onboarding.
    if (
        previous is None
        and db.scalar(
            select(MembershipRow.id).where(MembershipRow.identity_id == identity.id).limit(1)
        )
        is not None
    ):
        raise CompanyCreationNotAvailable()
    token, workspace = issue_workspace(db, parent, account, identity, None)
    result, created = CompanyService().create(db, workspace, identity, name, key)
    return result, created, token


def restore_workspace(
    db: ApplicationSession,
    parent: PasswordSessionRow,
    account: PasswordAccountRow,
    current_workspace: str | None,
) -> str:
    prior = check_existing_workspace(db, parent, current_workspace)
    identity = principal(db, account)
    if identity is None:
        raise CompanyCreationNotAvailable()
    active = memberships(db, identity)
    if not active:
        raise CompanyCreationNotAvailable()
    if prior is not None and current_workspace is not None:
        return current_workspace
    token, _ = issue_workspace(
        db, parent, account, identity, active[0].id if len(active) == 1 else None
    )
    return token


def account_workspace_state(
    db: ApplicationSession,
    parent: PasswordSessionRow,
    account: PasswordAccountRow,
    raw: str | None,
) -> dict[str, Any]:
    identity = principal(db, account)
    if identity is None:
        return {"workspace_access": False, "next_step": "ORGANISATION_REQUIRED"}
    active = memberships(db, identity)
    if not active:
        return {"workspace_access": False, "next_step": "ORGANISATION_ACCESS_UNAVAILABLE"}
    row = check_existing_workspace(db, parent, raw)
    actor = db.active_actor(row.membership_id, identity.id) if row and row.membership_id else None
    return {
        "workspace_access": actor is not None,
        "next_step": "WORKSPACE" if actor else "RESTORE_WORKSPACE",
    }


def set_workspace_cookie(response: Any, token: str, secure: bool, max_age: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=max_age,
    )
