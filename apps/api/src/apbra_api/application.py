from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from .authorization import authorized_case_access
from .domain import (
    AccessLevel,
    Actor,
    ApplicationPersistence,
    CaseRecord,
    Conflict,
    Forbidden,
    IdempotencyConflict,
    IdentityRecord,
    InvitationInvalid,
    InvitationRecord,
    MembershipRecord,
    RequestVersionRecord,
    Role,
    StaleVersion,
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def request_version_json(row: RequestVersionRecord) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "sequence": row.sequence,
        "request_text": row.request_text,
        "created_at": row.created_at.isoformat(),
    }


def case_json(db: ApplicationPersistence, row: CaseRecord) -> dict[str, Any]:
    current = db.request_version(row.current_request_version_id)
    assert current is not None
    return {
        "id": str(row.id),
        "company_id": str(row.company_id),
        "creator_membership_id": str(row.creator_membership_id),
        "current_request_version_id": str(row.current_request_version_id),
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "current_request": request_version_json(current),
    }


class CaseService:
    def create(
        self, db: object, actor: Actor, request_text: str, command_key: str
    ) -> tuple[dict[str, Any], bool]:
        store = cast(ApplicationPersistence, db)
        text = request_text.strip()
        if not text:
            raise Conflict()
        payload_digest = canonical_payload({"request_text": text})
        store.lock_create_case(actor, command_key)
        existing = store.idempotency_record(actor, "CREATE_CASE", command_key)
        if existing:
            if not hmac.compare_digest(existing.payload_digest, payload_digest):
                raise IdempotencyConflict()
            case, _ = authorized_case_access(store, actor, existing.resource_id)
            return case_json(store, case), False

        case = store.create_case(actor, text, command_key, payload_digest)
        return case_json(store, case), True

    def list_cases(self, db: object, actor: Actor) -> list[dict[str, Any]]:
        store = cast(ApplicationPersistence, db)
        return [case_json(store, row) for row in store.accessible_cases(actor)]

    def get(self, db: object, actor: Actor, case_id: UUID) -> dict[str, Any]:
        store = cast(ApplicationPersistence, db)
        row, _ = authorized_case_access(db, actor, case_id)
        return case_json(store, row)

    def versions(self, db: object, actor: Actor, case_id: UUID) -> list[dict[str, Any]]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(db, actor, case_id)
        return [request_version_json(row) for row in store.case_versions(case_id)]

    def update(
        self, db: object, actor: Actor, case_id: UUID, request_text: str, expected_version: int
    ) -> dict[str, Any]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(db, actor, case_id, require_edit=True)
        row = store.locked_case(case_id)
        assert row is not None
        if row.version != expected_version:
            raise StaleVersion()
        text = request_text.strip()
        if not text:
            raise Conflict()
        return case_json(store, store.update_case_request(row, actor, text))

    def list_access(self, db: object, actor: Actor, case_id: UUID) -> list[dict[str, Any]]:
        store = cast(ApplicationPersistence, db)
        _, actor_access = authorized_case_access(store, actor, case_id)
        if actor_access.access_level != AccessLevel.OWNER:
            raise Forbidden()
        return [
            {
                "membership_id": str(membership.id),
                "display_name": identity.display_name,
                "subject": identity.subject,
                "access_level": access.access_level,
                "active": access.active,
            }
            for access, membership, identity in store.case_access_entries(case_id)
        ]

    def grant_access(
        self,
        db: object,
        actor: Actor,
        case_id: UUID,
        membership_id: UUID,
        access_level: AccessLevel,
    ) -> None:
        store = cast(ApplicationPersistence, db)
        _, actor_access = authorized_case_access(store, actor, case_id)
        if actor_access.access_level != AccessLevel.OWNER or access_level == AccessLevel.OWNER:
            raise Forbidden()
        membership = store.lock_company_membership(actor.company_id, membership_id)
        if membership is None or not membership.active:
            raise Forbidden()
        store.grant_case_access(actor, case_id, membership, access_level)

    def revoke_access(
        self, db: object, actor: Actor, case_id: UUID, membership_id: UUID
    ) -> None:
        store = cast(ApplicationPersistence, db)
        _, actor_access = authorized_case_access(store, actor, case_id)
        if actor_access.access_level != AccessLevel.OWNER or membership_id == actor.membership_id:
            raise Forbidden()
        access = store.lock_case_access(case_id, membership_id)
        if access is None or access.company_id != actor.company_id:
            raise Forbidden()
        if access.active:
            access.active = False
            access.revoked_at = datetime.now(UTC)
            store.add_audit(
                actor,
                "CASE_ACCESS_REVOKED",
                "REPORTING_CASE",
                case_id,
                json.dumps(
                    {"membership_id": str(membership_id)},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )


class InvitationService:
    def issue(
        self,
        db: object,
        actor: Actor,
        invited_subject: str,
        role: Role,
        expires_in_days: int,
    ) -> tuple[InvitationRecord, str]:
        if not actor.role.can_invite:
            raise Forbidden()
        if role == Role.COMPANY_OWNER:
            raise Forbidden()
        subject = invited_subject.strip()
        if not subject:
            raise Conflict()
        raw_token = secrets.token_urlsafe(48)
        row = cast(ApplicationPersistence, db).create_invitation(
            actor,
            subject,
            role,
            sha256_text(raw_token),
            datetime.now(UTC) + timedelta(days=expires_in_days),
        )
        return row, raw_token

    def inspect(self, db: object, raw_token: str) -> InvitationRecord:
        row = cast(ApplicationPersistence, db).invitation(sha256_text(raw_token))
        if (
            row is None
            or row.revoked_at is not None
            or row.consumed_at is not None
            or row.expires_at <= datetime.now(UTC)
        ):
            raise InvitationInvalid()
        return row

    def accept(
        self, db: object, identity: IdentityRecord, raw_token: str
    ) -> MembershipRecord:
        store = cast(ApplicationPersistence, db)
        digest = sha256_text(raw_token)
        row = store.invitation(digest, lock=True)
        if row is None or not hmac.compare_digest(row.token_digest, digest):
            raise InvitationInvalid()
        if row.consumed_at is not None:
            existing = store.membership(row.company_id, identity.id)
            if row.consumed_by_identity_id == identity.id and existing is not None:
                return existing
            raise InvitationInvalid()
        if row.revoked_at is not None or row.expires_at <= datetime.now(UTC):
            raise InvitationInvalid()
        if row.invited_subject != identity.subject or row.invited_issuer != identity.issuer:
            raise InvitationInvalid()
        store.lock_identity_for_membership(identity.id)
        active_membership = store.active_identity_membership(identity.id)
        if active_membership is not None and active_membership.company_id != row.company_id:
            raise Conflict()
        existing = store.membership(row.company_id, identity.id)
        if existing is not None:
            raise Conflict()
        return store.accept_invitation(row, identity)

    def revoke(self, db: object, actor: Actor, invitation_id: UUID) -> None:
        if not actor.role.can_invite:
            raise Forbidden()
        store = cast(ApplicationPersistence, db)
        row = store.lock_company_invitation(actor.company_id, invitation_id)
        if row is None or row.consumed_at is not None:
            raise InvitationInvalid()
        row.revoked_at = datetime.now(UTC)
        store.add_audit(actor, "INVITATION_REVOKED", "INVITATION", row.id)


class MembershipService:
    def list(self, db: object, actor: Actor) -> list[dict[str, Any]]:
        if not actor.role.can_invite:
            raise Forbidden()
        rows = cast(ApplicationPersistence, db).company_memberships(actor.company_id)
        return [
            {
                "id": str(membership.id),
                "display_name": identity.display_name,
                "subject": identity.subject,
                "role": membership.role,
                "active": membership.active,
            }
            for membership, identity in rows
        ]

    def deactivate(self, db: object, actor: Actor, membership_id: UUID) -> None:
        if not actor.role.can_invite or membership_id == actor.membership_id:
            raise Forbidden()
        store = cast(ApplicationPersistence, db)
        membership = store.lock_company_membership(actor.company_id, membership_id)
        if membership is None:
            raise Forbidden()
        if membership.active:
            membership.active = False
            store.add_audit(actor, "MEMBERSHIP_DEACTIVATED", "MEMBERSHIP", membership.id)
