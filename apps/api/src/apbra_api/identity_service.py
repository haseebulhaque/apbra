"""Provider-neutral APBRA identity binding and safe authentication provenance."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from .domain import (
    ApplicationPersistence,
    AuthenticationRequired,
    IdentityRecord,
    OidcClaims,
)


class IdentityService:
    """Bind only validated profile + issuer + subject, never mutable profile claims."""

    def resolve(
        self,
        db: object,
        *,
        profile_id: str,
        claims: OidcClaims,
        allow_legacy_local: bool = False,
    ) -> IdentityRecord:
        if not claims.issuer or not claims.subject or len(claims.subject) > 255:
            raise AuthenticationRequired()
        store = cast(ApplicationPersistence, db)
        identity, created = store.resolve_external_identity(
            profile_id,
            claims.issuer,
            claims.subject,
            (claims.display_name.strip() or "APBRA user")[:200],
            allow_legacy_local=allow_legacy_local,
        )
        if created:
            self.record(db, profile_id, "IDENTITY_BOUND", identity_id=identity.id)
        if not identity.active:
            raise AuthenticationRequired()
        return identity

    @staticmethod
    def record(
        db: object,
        profile_id: str,
        event_type: str,
        *,
        identity_id: UUID | None = None,
        session_id: UUID | None = None,
        reason: str | None = None,
    ) -> None:
        cast(ApplicationPersistence, db).add_auth_event(
            profile_id,
            event_type,
            identity_id=identity_id,
            session_id=session_id,
            reason=reason,
        )
