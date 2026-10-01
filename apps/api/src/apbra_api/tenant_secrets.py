"""Provider-neutral tenant credential boundary with an encrypted local adapter.

Only opaque database references leave this module. Keyring material belongs to
deployment bootstrap and must be supplied outside source control.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import ConfigurationUnavailable
from .persistence import TenantSecretRow, utcnow


class TenantCredentialStore(Protocol):
    """A deployment can replace this adapter without changing tenant policy."""

    def protect(
        self,
        db: Session,
        *,
        company_id: UUID,
        profile_id: str,
        credential: str,
        actor_membership_id: UUID | None,
    ) -> UUID: ...

    def resolve(
        self, db: Session, *, company_id: UUID, profile_id: str, reference_id: UUID
    ) -> str: ...


class _KeyringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_version: str = Field(min_length=1, max_length=80)
    keys: dict[str, str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def active_is_present(self) -> _KeyringConfig:
        if self.active_version not in self.keys:
            raise ValueError("active tenant encryption key is unavailable")
        return self


@dataclass(frozen=True)
class AesGcmTenantCredentialStore:
    """Authenticated encryption with deployment-managed, versioned 256-bit keys."""

    active_version: str
    keys: dict[str, bytes]

    @classmethod
    def from_bootstrap(cls, keyring_json: str | None) -> AesGcmTenantCredentialStore | None:
        if keyring_json is None or not keyring_json.strip():
            return None
        try:
            parsed = _KeyringConfig.model_validate_json(keyring_json)
            keys = {
                name: base64.b64decode(value, validate=True) for name, value in parsed.keys.items()
            }
            if any(len(value) != 32 for value in keys.values()):
                raise ValueError("tenant encryption keys must be 256-bit")
        except (ValidationError, ValueError, binascii.Error) as exc:
            raise ConfigurationUnavailable() from exc
        return cls(active_version=parsed.active_version, keys=keys)

    @staticmethod
    def _associated_data(company_id: UUID, profile_id: str, reference_id: UUID) -> bytes:
        return json.dumps(
            {"company": str(company_id), "profile": profile_id, "reference": str(reference_id)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def protect(
        self,
        db: Session,
        *,
        company_id: UUID,
        profile_id: str,
        credential: str,
        actor_membership_id: UUID | None,
    ) -> UUID:
        if not credential or len(credential) > 16_384 or not profile_id:
            raise ConfigurationUnavailable()
        reference_id = uuid4()
        nonce = os.urandom(12)
        ciphertext = AESGCM(self.keys[self.active_version]).encrypt(
            nonce, credential.encode(), self._associated_data(company_id, profile_id, reference_id)
        )
        db.add(
            TenantSecretRow(
                id=reference_id,
                company_id=company_id,
                profile_id=profile_id,
                key_version=self.active_version,
                nonce=nonce,
                ciphertext=ciphertext,
                created_by_membership_id=actor_membership_id,
                created_at=utcnow(),
            )
        )
        db.flush()
        return reference_id

    def resolve(self, db: Session, *, company_id: UUID, profile_id: str, reference_id: UUID) -> str:
        row = db.scalar(
            select(TenantSecretRow).where(
                TenantSecretRow.id == reference_id,
                TenantSecretRow.company_id == company_id,
                TenantSecretRow.profile_id == profile_id,
                TenantSecretRow.revoked_at.is_(None),
            )
        )
        if row is None or row.key_version not in self.keys:
            raise ConfigurationUnavailable()
        try:
            plaintext = AESGCM(self.keys[row.key_version]).decrypt(
                row.nonce,
                row.ciphertext,
                self._associated_data(company_id, profile_id, reference_id),
            )
            return plaintext.decode()
        except (InvalidTag, ValueError, UnicodeDecodeError) as exc:
            raise ConfigurationUnavailable() from exc


def credential_status(
    db: Session, *, company_id: UUID, reference_id: UUID | None
) -> dict[str, object]:
    row = (
        db.scalar(
            select(TenantSecretRow).where(
                TenantSecretRow.id == reference_id,
                TenantSecretRow.company_id == company_id,
                TenantSecretRow.revoked_at.is_(None),
            )
        )
        if reference_id is not None
        else None
    )
    return {
        "status": "CONFIGURED" if row else "NOT_CONFIGURED",
        "maskedValue": "***" if row else None,
        "updatedAt": row.created_at.isoformat() if row else None,
        "canReplace": True,
        "canRotate": bool(row),
    }
