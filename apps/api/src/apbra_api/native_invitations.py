"""Native invitation transactions. An email address never supplies membership authority."""

from __future__ import annotations

import re
import secrets
import smtplib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, tuple_
from sqlalchemy.exc import SQLAlchemyError

from .application import canonical_payload
from .auth_boundary import digest
from .domain import (
    Actor,
    ApplicationError,
    AuthenticationRequired,
    Conflict,
    Forbidden,
    IdempotencyConflict,
    InvitationInvalid,
    NativeInvitationConsumed,
    NativeMembershipExists,
    NativeMembershipInactive,
    Role,
)
from .native_organisation import (
    NATIVE_METHOD,
    NativeAccountPrincipalRow,
    NativeWorkspaceSessionRow,
    check_existing_workspace,
    issue_workspace,
    live_parent,
    lock_accounts,
    principal,
)
from .observability import _cursor_decode, _cursor_encode
from .password_auth import TOKEN, Mailer, PasswordAccountRow, PasswordSessionRow, normalized_email
from .persistence import (
    ApplicationSession,
    CompanyRow,
    Database,
    ExternalIdentityRow,
    MembershipRow,
    NativeInvitationAuditRow,
    NativeInvitationCommandRow,
    NativeInvitationRow,
    SessionRow,
    utcnow,
)
from .tenant_settings import current_settings


class Unavailable(InvitationInvalid):
    """Public denials are uniform. Only the audit gets the classified reason and known IDs."""

    def __init__(
        self,
        event: str = "REJECTED",
        invitation: NativeInvitationRow | None = None,
        account_id: UUID | None = None,
    ) -> None:
        super().__init__()
        self.event = event
        self.invitation_id = invitation.id if invitation else None
        self.company_id = invitation.company_id if invitation else None
        self.account_id = account_id


class DeliveryUnavailable(ApplicationError):
    code = "EMAIL_DELIVERY_UNAVAILABLE"
    status_code = 503
    public_message = "Invitation delivery is unavailable. Contact your organisation operator."


def record_denial(database: Database, denial: Unavailable | None = None) -> UUID:
    reference = uuid4()
    try:
        with database.session() as audit_db:
            audit_db.add(
                NativeInvitationAuditRow(
                    id=reference,
                    event=denial.event if denial else "REJECTED",
                    company_id=denial.company_id if denial else None,
                    invitation_id=denial.invitation_id if denial else None,
                    account_id=denial.account_id if denial else None,
                )
            )
    except SQLAlchemyError:
        # The caller must still deny access when the audit store itself is unavailable.
        pass
    return reference


@contextmanager
def transaction(database: Database) -> Iterator[ApplicationSession]:
    try:
        with database.session() as db:
            assert isinstance(db, ApplicationSession)
            yield db
    except Exception as exc:
        # Open the denial transaction only after all business-state changes have rolled back.
        reference = record_denial(database, exc if isinstance(exc, Unavailable) else None)
        if isinstance(exc, ApplicationError):
            exc.support_reference = reference
        raise


def record(
    db: ApplicationSession,
    event: str,
    row: NativeInvitationRow,
    account_id: UUID | None = None,
    membership_id: UUID | None = None,
) -> None:
    db.add(
        NativeInvitationAuditRow(
            event=event,
            invitation_id=row.id,
            company_id=row.company_id,
            account_id=account_id,
            membership_id=membership_id,
        )
    )


def state(row: NativeInvitationRow, now: datetime) -> str:
    if row.consumed_at is not None:
        return "ACCEPTED"
    if row.revoked_at is not None:
        return "REVOKED"
    if row.expires_at <= now:
        return "EXPIRED"
    return row.delivery_state


def management_view(row: NativeInvitationRow, now: datetime) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "email": row.delivery_address,
        "role": row.role,
        "delivery_state": row.delivery_state,
        "state": state(row, now),
        "expires_at": row.expires_at.isoformat(),
    }


def checked_parent(
    db: ApplicationSession,
    parent_digest: str,
    account: PasswordAccountRow,
    now: Callable[[], datetime],
) -> PasswordSessionRow:
    parent = db.get(PasswordSessionRow, parent_digest, with_for_update=True, populate_existing=True)
    if parent is None or not live_parent(parent, account, now()):
        raise AuthenticationRequired()
    return parent


@dataclass
class Manager:
    actor: Actor
    account: PasswordAccountRow
    recipient: PasswordAccountRow | None
    invitation: NativeInvitationRow | None


def manager(
    db: ApplicationSession,
    token: str | None,
    now: Callable[[], datetime],
    *,
    expected_membership: str | None = None,
    recipient_key: str | None = None,
    invitation_id: UUID | None = None,
) -> Manager:
    if not token:
        raise AuthenticationRequired()
    # These reads discover IDs only. All authority is re-read under the ordered locks below.
    workspace = db.scalar(select(SessionRow).where(SessionRow.token_digest == digest(token)))
    binding = db.get(NativeWorkspaceSessionRow, workspace.id) if workspace else None
    if workspace is None or binding is None:
        raise AuthenticationRequired()
    account_id = db.scalar(
        select(PasswordSessionRow.account_id).where(
            PasswordSessionRow.digest == binding.parent_digest
        )
    )
    if account_id is None:
        raise AuthenticationRequired()

    def recipient_id() -> UUID | None:
        return (
            db.scalar(
                select(PasswordAccountRow.id).where(PasswordAccountRow.email_key == recipient_key)
            )
            if recipient_key is not None
            else None
        )

    target = recipient_id()
    accounts = lock_accounts(db, [account_id, target] if target else [account_id])
    owner = accounts.get(account_id)
    if owner is None:
        raise AuthenticationRequired()
    parent = checked_parent(db, binding.parent_digest, owner, now)
    workspace = db.get_one(SessionRow, workspace.id, with_for_update=True, populate_existing=True)
    if workspace.membership_id is None:
        raise Forbidden()
    if expected_membership is not None and expected_membership != str(workspace.membership_id):
        raise Conflict()
    company_id = db.scalar(
        select(MembershipRow.company_id).where(MembershipRow.id == workspace.membership_id)
    )
    if company_id is None or db.active_company(company_id, lock=True) is None:
        raise Forbidden()
    invitation = None
    if invitation_id is not None:
        invitation = db.scalar(
            select(NativeInvitationRow)
            .where(
                NativeInvitationRow.id == invitation_id,
                NativeInvitationRow.company_id == company_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    identity = principal(db, owner)
    if identity is None or workspace.identity_id != identity.id:
        raise Forbidden()
    db.lock_identity_for_membership(identity.id)
    actor = db.active_actor(workspace.membership_id, identity.id, lock=True)
    stamp = now()
    if (
        actor is None
        or actor.company_id != company_id
        or not actor.role.can_invite
        or workspace.provider_profile_id != NATIVE_METHOD
        or workspace.revoked_at is not None
        or workspace.expires_at <= stamp
        or not live_parent(parent, owner, stamp)
    ):
        raise Forbidden()
    if target != recipient_id():
        # Verification raced address discovery. Fresh command can acquire both accounts in order.
        raise Conflict()
    parent.touched_at = stamp
    return Manager(actor, owner, accounts.get(target) if target else None, invitation)


def issue(
    database: Database,
    raw: str | None,
    email: str,
    role: Role,
    days: int | None,
    key: str,
    mailer: Mailer | None,
    now: Callable[[], datetime],
    expected_membership: str | None = None,
) -> tuple[dict[str, Any], bool]:
    with transaction(database) as db:
        try:
            address, email_key = normalized_email(email)
        except ValueError as exc:
            raise Conflict() from exc
        ctx = manager(
            db, raw, now, recipient_key=email_key, expected_membership=expected_membership
        )
        if role not in {Role.MEMBER, Role.EXPERT, Role.COMPANY_ADMIN}:
            raise Forbidden()
        if not re.fullmatch(r"[A-Za-z0-9._:-]{8,200}", key):
            raise Conflict()
        payload = canonical_payload(
            {"email": email_key, "role": role.value, "expires_in_days": days}
        )
        actor = ctx.actor
        prior = db.get(NativeInvitationCommandRow, (actor.company_id, actor.identity_id, key))
        if prior:
            if prior.payload_digest != payload:
                raise IdempotencyConflict()
            return management_view(
                db.get_one(NativeInvitationRow, prior.invitation_id), now()
            ), False
        if mailer is None:
            raise DeliveryUnavailable()
        snapshot = current_settings(db, actor.company_id)
        stamp = now()
        proof = secrets.token_urlsafe(48)
        row = NativeInvitationRow(
            company_id=actor.company_id,
            issued_by_membership_id=actor.membership_id,
            issuer_account_id=ctx.account.id,
            issuer_epoch=ctx.account.epoch,
            delivery_key=email_key,
            delivery_address=address,
            role=role.value,
            token_digest=digest(proof),
            created_at=stamp,
            expires_at=stamp + timedelta(days=days or snapshot.settings.invitation_ttl_days),
            settings_version_id=snapshot.id,
            delivery_state="PREPARED",
            recipient_account_id=ctx.recipient.id if ctx.recipient else None,
            recipient_epoch=ctx.recipient.epoch if ctx.recipient else None,
        )
        db.add(row)
        db.flush()
        invitation_id, company_id = row.id, row.company_id
        db.add(
            NativeInvitationCommandRow(
                company_id=company_id,
                issuer_identity_id=actor.identity_id,
                command_key=key,
                payload_digest=payload,
                invitation_id=invitation_id,
            )
        )
        record(db, "ISSUED", row, ctx.account.id, actor.membership_id)
    # Exactly one dispatch, after the intent/command commit and outside every database lock.
    try:
        mailer.send(address, "invite", proof)
        delivery, event = "SUBMITTED", "SUBMISSION_ACCEPTED"
    except smtplib.SMTPResponseException:
        delivery, event = "FAILED", "SUBMISSION_FAILED"
    except (TimeoutError, smtplib.SMTPServerDisconnected, OSError):
        delivery, event = "UNCONFIRMED", "SUBMISSION_UNCONFIRMED"
    except Exception:
        delivery, event = "FAILED", "SUBMISSION_FAILED"
    with transaction(database) as db:
        db.get_one(CompanyRow, company_id, with_for_update=True)
        issued = db.get_one(NativeInvitationRow, invitation_id, with_for_update=True)
        stamp = now()
        if state(issued, stamp) == "PREPARED":
            issued.delivery_state = delivery
        record(db, event, issued)
        return management_view(issued, stamp), True


def list_invitations(
    database: Database,
    raw: str | None,
    limit: int,
    cursor: str | None,
    secret: str,
    now: Callable[[], datetime],
    expected_membership: str | None = None,
) -> dict[str, Any]:
    with transaction(database) as db:
        actor = manager(db, raw, now, expected_membership=expected_membership).actor
        binding = f"native-invitations:{actor.company_id}:{actor.membership_id}"
        query = select(NativeInvitationRow).where(
            NativeInvitationRow.company_id == actor.company_id
        )
        if cursor is not None:
            try:
                stamp, identifier = _cursor_decode(cursor, binding, secret)
            except ValueError as exc:
                raise Conflict() from exc
            query = query.where(
                tuple_(NativeInvitationRow.created_at, NativeInvitationRow.id) < (stamp, identifier)
            )
        rows = list(
            db.scalars(
                query.order_by(
                    NativeInvitationRow.created_at.desc(), NativeInvitationRow.id.desc()
                ).limit(limit + 1)
            )
        )
        page = rows[:limit]
        next_cursor = (
            _cursor_encode((page[-1].created_at, page[-1].id), binding, secret)
            if len(rows) > limit
            else None
        )
        return {
            "items": [management_view(item, now()) for item in page],
            "next_cursor": next_cursor,
        }


def revoke(
    database: Database,
    raw: str | None,
    invitation_id: UUID,
    now: Callable[[], datetime],
    expected_membership: str | None = None,
) -> dict[str, Any]:
    with transaction(database) as db:
        ctx = manager(
            db, raw, now, invitation_id=invitation_id, expected_membership=expected_membership
        )
        row = ctx.invitation
        if row is None:
            raise Unavailable()
        if row.consumed_at is not None:
            raise NativeInvitationConsumed()
        if row.revoked_at is None:
            row.revoked_at = now()
            row.revoke_reason = "MANAGER_REVOKED"
            record(db, "REVOKED", row, ctx.account.id, ctx.actor.membership_id)
        return management_view(row, now())


def receipt(row: NativeInvitationRow) -> dict[str, str]:
    assert row.target_membership_id and row.consumed_at
    return {
        "id": str(row.id),
        "invitation_id": str(row.id),
        "company_id": str(row.company_id),
        "membership_id": str(row.target_membership_id),
        "role_at_accept": row.role,
        "accepted_at": row.consumed_at.isoformat(),
    }


@dataclass
class RecipientResult:
    status: str
    body: dict[str, Any]
    workspace_token: str | None = None
    cookie_lifetime: int = 0


def recipient(
    database: Database,
    parent_token: str | None,
    workspace_token: str | None,
    proof: str,
    *,
    accept: bool,
    now: Callable[[], datetime] = utcnow,
) -> RecipientResult:
    with transaction(database) as db:
        if not parent_token or not TOKEN.fullmatch(parent_token):
            raise AuthenticationRequired()
        parent_digest = digest(parent_token)
        account_id = db.scalar(
            select(PasswordSessionRow.account_id).where(PasswordSessionRow.digest == parent_digest)
        )
        if account_id is None:
            raise AuthenticationRequired()
        candidate = db.scalar(
            select(NativeInvitationRow).where(NativeInvitationRow.token_digest == digest(proof))
        )
        accounts = lock_accounts(
            db, [account_id, candidate.issuer_account_id] if candidate else [account_id]
        )
        account = accounts.get(account_id)
        if account is None:
            raise AuthenticationRequired()
        parent = checked_parent(db, parent_digest, account, now)
        check_existing_workspace(db, parent, workspace_token)
        if candidate is None:
            raise Unavailable(account_id=account.id)
        company = db.active_company(candidate.company_id, lock=True)
        row = db.get_one(
            NativeInvitationRow, candidate.id, with_for_update=True, populate_existing=True
        )
        if company is None or row.delivery_key != account.email_key:
            raise Unavailable("REJECTED", row, account.id)
        if (
            row.recipient_account_id is not None and row.recipient_account_id != account.id
        ) or account.epoch != (row.recipient_epoch or 1):
            raise Unavailable("EPOCH_INVALID", row, account.id)
        # Lock existing principal identities in deterministic order before any membership row.
        principal_accounts = (
            [account.id] if row.consumed_at else [account.id, row.issuer_account_id]
        )
        bindings = db.execute(
            select(
                NativeAccountPrincipalRow.account_id, NativeAccountPrincipalRow.identity_id
            ).where(NativeAccountPrincipalRow.account_id.in_(principal_accounts))
        ).all()
        for identity_id in sorted({binding.identity_id for binding in bindings}):
            db.get_one(
                ExternalIdentityRow, identity_id, with_for_update=True, populate_existing=True
            )
        try:
            identity = principal(db, account)
        except AuthenticationRequired as exc:
            raise Unavailable() from exc
        member = (
            db.scalar(
                select(MembershipRow)
                .where(
                    MembershipRow.company_id == row.company_id,
                    MembershipRow.identity_id == identity.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if identity
            else None
        )
        stamp = now()
        if not live_parent(parent, account, stamp):
            raise AuthenticationRequired()
        summary = {
            "company_id": str(company.id),
            "company_name": company.name,
            "role": row.role,
            "expires_at": row.expires_at.isoformat(),
        }
        if row.consumed_at is not None:
            if (
                row.consumed_by_account_id != account.id
                or member is None
                or not member.active
                or member.id != row.target_membership_id
            ):
                raise Unavailable()
            if accept:
                record(db, "RECEIPT_REPLAYED", row, account.id, member.id)
            return RecipientResult(
                "ALREADY_ACCEPTED", {"invitation": summary, "receipt": receipt(row)}
            )
        issuer = accounts.get(row.issuer_account_id)
        try:
            issuer_identity = principal(db, issuer) if issuer and issuer.active else None
        except AuthenticationRequired as exc:
            raise Unavailable("REJECTED", row, account.id) from exc
        if not issuer or issuer.epoch != row.issuer_epoch:
            raise Unavailable("EPOCH_INVALID", row, account.id)
        issuer_actor = (
            db.active_actor(row.issued_by_membership_id, issuer_identity.id, lock=True)
            if issuer_identity
            else None
        )
        stamp = now()
        if not live_parent(parent, account, stamp):
            raise AuthenticationRequired()
        if row.expires_at <= stamp:
            raise Unavailable("EXPIRED", row, account.id)
        if (
            row.revoked_at is not None
            or row.delivery_state != "SUBMITTED"
            or not issuer_actor
            or issuer_actor.company_id != company.id
            or not issuer_actor.role.can_invite
        ):
            raise Unavailable("REJECTED", row, account.id)
        if member is not None:
            if member.active:
                raise NativeMembershipExists()
            raise NativeMembershipInactive()
        if not accept:
            return RecipientResult("AVAILABLE", {"invitation": summary})
        identity = identity or principal(db, account, create=True)
        assert identity is not None
        member = MembershipRow(
            company_id=company.id, identity_id=identity.id, role=row.role, active=True
        )
        db.add(member)
        db.flush()
        row.recipient_account_id, row.recipient_epoch = account.id, account.epoch
        row.consumed_by_account_id, row.consumed_at, row.target_membership_id = (
            account.id,
            stamp,
            member.id,
        )
        record(db, "ACCEPTED", row, account.id, member.id)
        token, _ = issue_workspace(db, parent, account, identity, member.id)
        return RecipientResult(
            "ACCEPTED",
            {
                "invitation": summary,
                "receipt": receipt(row),
                "membership": {"id": str(member.id), "role": member.role},
            },
            token,
            max(0, int((parent.expires_at - stamp).total_seconds())),
        )
