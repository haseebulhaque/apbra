"""Provider-neutral tenant credential boundary with an encrypted local adapter.

Only opaque database references leave this module. Keyring material belongs to
deployment bootstrap and must be supplied outside source control.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select, text
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


def _unique_keyring_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate keyring field")
        result[name] = value
    return result


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
            parsed = _KeyringConfig.model_validate(
                json.loads(keyring_json, object_pairs_hook=_unique_keyring_fields)
            )
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


@dataclass(frozen=True)
class RekeyResult:
    row_count: int
    snapshot_digest: str
    dry_run: bool


def _immutable_credential_metadata(row: TenantSecretRow) -> tuple[object, ...]:
    return (
        row.id,
        row.company_id,
        row.profile_id,
        row.created_by_membership_id,
        row.created_at,
        row.revoked_at,
    )


def _credential_snapshot(rows: list[TenantSecretRow]) -> str:
    manifest = [
        [
            str(row.id),
            str(row.company_id),
            row.profile_id,
            row.key_version,
            row.nonce.hex(),
            row.ciphertext.hex(),
            str(row.created_by_membership_id),
            row.created_at.isoformat(),
            str(row.revoked_at),
        ]
        for row in rows
    ]
    return hashlib.sha256(json.dumps(manifest, separators=(",", ":")).encode()).hexdigest()


def rekey_tenant_credentials(
    db: Session,
    source: AesGcmTenantCredentialStore,
    replacement: AesGcmTenantCredentialStore,
    *,
    dry_run: bool = True,
    expected_snapshot_digest: str | None = None,
) -> RekeyResult:
    """Owner maintenance only: one PostgreSQL transaction, with stable references.

    Dry-run exercises writes and database readback, then rolls back. Commit must
    match the preceding dry-run snapshot. Old key mappings must be retained for
    existing backups; this operation never changes credentials or settings rows.
    """
    if (
        db.in_transaction()
        or db.get_bind().dialect.name != "postgresql"
        or not source.keys
        or source.active_version not in source.keys
        or replacement.active_version not in replacement.keys
        or replacement.active_version in source.keys
        or any(replacement.keys.get(version) != key for version, key in source.keys.items())
        or replacement.keys[replacement.active_version] in source.keys.values()
        or any(len(key) != 32 for key in (*source.keys.values(), *replacement.keys.values()))
        or (not dry_run and expected_snapshot_digest is None)
    ):
        raise ConfigurationUnavailable()
    with db.begin() as transaction:
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("SET LOCAL statement_timeout = '30s'"))
        # Blocks credential writes, including inserts, throughout preparation and
        # readback. Ordinary reads remain possible; API must be stopped by owner.
        db.execute(text("LOCK TABLE tenant_secret_records IN SHARE ROW EXCLUSIVE MODE"))
        rows = list(db.scalars(select(TenantSecretRow).order_by(TenantSecretRow.id)))
        if not rows:
            raise ConfigurationUnavailable()
        snapshot = _credential_snapshot(rows)
        if expected_snapshot_digest is not None and not hmac.compare_digest(
            snapshot, expected_snapshot_digest
        ):
            raise ConfigurationUnavailable()
        prepared: list[tuple[TenantSecretRow, bytes, bytes, bytes, tuple[object, ...]]] = []
        try:
            for row in rows:
                if row.key_version not in source.keys:
                    raise ConfigurationUnavailable()
                aad = source._associated_data(row.company_id, row.profile_id, row.id)
                plaintext = AESGCM(source.keys[row.key_version]).decrypt(
                    row.nonce, row.ciphertext, aad
                )
                decoded = plaintext.decode()
                if not decoded or len(decoded) > 16_384:
                    raise ConfigurationUnavailable()
                nonce = os.urandom(12)
                ciphertext = AESGCM(replacement.keys[replacement.active_version]).encrypt(
                    nonce, plaintext, aad
                )
                if not hmac.compare_digest(
                    AESGCM(replacement.keys[replacement.active_version]).decrypt(
                        nonce, ciphertext, aad
                    ),
                    plaintext,
                ):
                    raise ConfigurationUnavailable()
                prepared.append(
                    (row, nonce, ciphertext, plaintext, _immutable_credential_metadata(row))
                )
            # Nothing is updated until all original envelopes authenticate.
            for row, nonce, ciphertext, _, _metadata in prepared:
                row.key_version = replacement.active_version
                row.nonce = nonce
                row.ciphertext = ciphertext
            db.flush()
            for row, nonce, ciphertext, plaintext, metadata in prepared:
                db.refresh(row)
                if (
                    row.key_version != replacement.active_version
                    or _immutable_credential_metadata(row) != metadata
                    or row.nonce != nonce
                    or row.ciphertext != ciphertext
                ):
                    raise ConfigurationUnavailable()
                aad = replacement._associated_data(row.company_id, row.profile_id, row.id)
                if not hmac.compare_digest(
                    AESGCM(replacement.keys[row.key_version]).decrypt(
                        row.nonce, row.ciphertext, aad
                    ),
                    plaintext,
                ):
                    raise ConfigurationUnavailable()
        except (InvalidTag, ValueError, UnicodeDecodeError) as error:
            raise ConfigurationUnavailable() from error
        result = RekeyResult(len(rows), snapshot, dry_run)
        if dry_run:
            transaction.rollback()
    return result


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
