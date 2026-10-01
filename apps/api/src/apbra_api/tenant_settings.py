"""Validated, immutable, tenant-authoritative operating policy.

Deployment configuration is used only to create a first local development/test
version. Normal operations read the tenant's effective database version.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import GenerationPolicy, Settings, UploadPolicy
from .domain import Actor, ConfigurationUnavailable, Conflict, Forbidden, Role
from .model_provider import ProviderProfile
from .persistence import (
    CompanyRow,
    TenantSecretRow,
    TenantSettingsCurrentRow,
    TenantSettingsVersionRow,
    utcnow,
)
from .tenant_secrets import TenantCredentialStore


class DeliveryGuidePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: Literal[True]
    include_handover_instructions: bool


class TenantClarificationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_questions_per_round: int = Field(ge=1, le=20)
    max_answer_characters: int = Field(ge=100, le=20_000)


class TenantConventions(BaseModel):
    """Organisation-authored conventions, not application business defaults."""

    model_config = ConfigDict(extra="forbid")

    report_naming: str = Field(max_length=2_000)
    semantic_modelling: str = Field(max_length=2_000)
    accessibility: str = Field(max_length=2_000)
    terminology: dict[str, str] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_terminology(self) -> TenantConventions:
        if any(
            not key.strip() or not value.strip() or len(key) > 100 or len(value) > 500
            for key, value in self.terminology.items()
        ):
            raise ValueError("tenant terminology must have bounded nonempty entries")
        return self


class TenantSettings(BaseModel):
    """Explicit versioned tenant settings. Credential bytes are never fields here."""

    model_config = ConfigDict(extra="forbid")

    clarification_enabled: bool
    max_clarification_rounds_per_cycle: int = Field(ge=1, le=20)
    max_clarification_rounds_overall: int = Field(ge=1, le=100)
    expert_escalation_enabled: bool
    automatic_generation_enabled: bool
    invitation_ttl_days: int = Field(ge=1, le=30)
    upload_policy: UploadPolicy
    clarification_policy: TenantClarificationPolicy
    generation_policy: GenerationPolicy
    provider_profile: ProviderProfile | None
    delivery_guide_policy: DeliveryGuidePolicy
    conventions: TenantConventions

    @model_validator(mode="after")
    def validate_capability(self) -> TenantSettings:
        if self.max_clarification_rounds_per_cycle > self.max_clarification_rounds_overall:
            raise ValueError("per-cycle clarification limit exceeds overall limit")
        if (
            not self.generation_policy.generation.validation_required
            or not self.generation_policy.governance.require_validation
        ):
            raise ValueError("deterministic generation validation is mandatory")
        if self.automatic_generation_enabled and self.provider_profile is None:
            raise ValueError("automatic generation requires an explicit qualified provider profile")
        if (
            self.provider_profile is not None
            and not self.provider_profile.capabilities.structured_output
        ):
            raise ValueError("qualified provider must support structured output")
        return self


@dataclass(frozen=True)
class TenantSettingsSnapshot:
    id: UUID
    company_id: UUID
    version: int
    settings: TenantSettings
    digest: str
    secret_reference_id: UUID | None


def _encoded(settings: TenantSettings) -> str:
    return json.dumps(
        settings.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":")
    )


def _snapshot(row: TenantSettingsVersionRow) -> TenantSettingsSnapshot:
    try:
        settings = TenantSettings.model_validate_json(row.settings_json)
    except ValidationError as exc:
        raise ConfigurationUnavailable() from exc
    encoded = _encoded(settings)
    if hashlib.sha256(encoded.encode()).hexdigest() != row.settings_digest:
        raise ConfigurationUnavailable()
    return TenantSettingsSnapshot(
        id=row.id,
        company_id=row.company_id,
        version=row.version,
        settings=settings,
        digest=row.settings_digest,
        secret_reference_id=row.secret_reference_id,
    )


def current_settings(
    db: Session, company_id: UUID, *, lock: bool = False
) -> TenantSettingsSnapshot:
    query = select(TenantSettingsCurrentRow).where(
        TenantSettingsCurrentRow.company_id == company_id
    )
    if lock:
        query = query.with_for_update()
    current = db.scalar(query)
    if current is None:
        raise ConfigurationUnavailable()
    version = db.scalar(
        select(TenantSettingsVersionRow).where(
            TenantSettingsVersionRow.id == current.version_id,
            TenantSettingsVersionRow.company_id == company_id,
        )
    )
    if version is None or version.version != current.version:
        raise ConfigurationUnavailable()
    return _snapshot(version)


def settings_version(db: object, company_id: UUID, version_id: UUID) -> TenantSettingsSnapshot:
    row = cast(Session, db).scalar(
        select(TenantSettingsVersionRow).where(
            TenantSettingsVersionRow.id == version_id,
            TenantSettingsVersionRow.company_id == company_id,
        )
    )
    if row is None:
        raise ConfigurationUnavailable()
    return _snapshot(row)


def interpretation_material_digest(settings: TenantSettings) -> str:
    """Changes to these settings can change accepted business meaning or scope."""
    material = {
        "clarification_enabled": settings.clarification_enabled,
        "clarification_policy": settings.clarification_policy.model_dump(mode="json"),
        "generation_policy": settings.generation_policy.model_dump(mode="json", by_alias=True),
        "provider_profile": settings.provider_profile.model_dump(mode="json")
        if settings.provider_profile
        else None,
        "conventions": settings.conventions.model_dump(mode="json"),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _require_admin(actor: Actor) -> None:
    if actor.role not in {Role.COMPANY_OWNER, Role.COMPANY_ADMIN}:
        raise Forbidden()


def admin_settings(db: Session, actor: Actor) -> TenantSettingsSnapshot:
    _require_admin(actor)
    return current_settings(db, actor.company_id)


def _valid_secret(
    db: Session,
    company_id: UUID,
    profile: ProviderProfile | None,
    reference_id: UUID | None,
    credential_store: TenantCredentialStore | None,
) -> bool:
    if profile is None or reference_id is None or credential_store is None:
        return False
    row = db.scalar(
        select(TenantSecretRow).where(
            TenantSecretRow.id == reference_id,
            TenantSecretRow.company_id == company_id,
            TenantSecretRow.profile_id == profile.profile_id,
            TenantSecretRow.revoked_at.is_(None),
        )
    )
    if row is None:
        return False
    try:
        credential_store.resolve(
            db, company_id=company_id, profile_id=profile.profile_id, reference_id=reference_id
        )
    except ConfigurationUnavailable:
        return False
    return True


def _safe_changes(
    previous: TenantSettings, updated: TenantSettings
) -> tuple[list[str], dict[str, Any]]:
    before = previous.model_dump(mode="json", by_alias=True)
    after = updated.model_dump(mode="json", by_alias=True)
    changed = sorted(key for key in after if before[key] != after[key])
    changes: dict[str, Any] = {}
    for key in changed:
        if key == "provider_profile":
            changes[key] = {"previous": "CHANGED_OR_UNSET", "current": "CHANGED_OR_UNSET"}
        else:
            changes[key] = {"previous": before[key], "current": after[key]}
    return changed, changes


def _insert_version(
    db: Session,
    company_id: UUID,
    settings: TenantSettings,
    *,
    version: int,
    actor_id: UUID | None,
    secret_reference_id: UUID | None,
    credential_store: TenantCredentialStore | None,
    changed_keys: list[str],
    safe_changes: dict[str, Any],
    reason: str | None,
    restored_from: UUID | None,
) -> TenantSettingsSnapshot:
    if settings.automatic_generation_enabled and not _valid_secret(
        db, company_id, settings.provider_profile, secret_reference_id, credential_store
    ):
        raise ConfigurationUnavailable()
    encoded = _encoded(settings)
    row = TenantSettingsVersionRow(
        id=uuid4(),
        company_id=company_id,
        version=version,
        settings_json=encoded,
        settings_digest=hashlib.sha256(encoded.encode()).hexdigest(),
        secret_reference_id=secret_reference_id,
        created_by_membership_id=actor_id,
        created_at=utcnow(),
        changed_keys_json=json.dumps(changed_keys),
        safe_changes_json=json.dumps(safe_changes, sort_keys=True),
        reason=reason,
        restored_from_version_id=restored_from,
        validation_status="PASS",
    )
    db.add(row)
    db.flush()
    current = db.get(TenantSettingsCurrentRow, company_id)
    if current is None:
        db.add(TenantSettingsCurrentRow(company_id=company_id, version_id=row.id, version=version))
    else:
        current.version_id = row.id
        current.version = version
        current.updated_at = utcnow()
    db.flush()
    return _snapshot(row)


def update_settings(
    db: Session,
    actor: Actor,
    settings: TenantSettings,
    *,
    expected_version: int,
    reason: str | None = None,
    secret_reference_id: UUID | None = None,
    credential_store: TenantCredentialStore | None = None,
) -> TenantSettingsSnapshot:
    _require_admin(actor)
    current = current_settings(db, actor.company_id, lock=True)
    if current.version != expected_version:
        raise Conflict()
    reference = current.secret_reference_id if secret_reference_id is None else secret_reference_id
    # A provider-profile switch cannot silently reuse a credential bound to another profile.
    if (
        settings.provider_profile != current.settings.provider_profile
        and secret_reference_id is None
    ):
        reference = None
    changed, changes = _safe_changes(current.settings, settings)
    if not changed and reference == current.secret_reference_id:
        raise Conflict()
    if reference != current.secret_reference_id:
        changed.append("credential")
        changes["credential"] = {"previous": "REDACTED", "current": "REDACTED"}
    return _insert_version(
        db,
        actor.company_id,
        settings,
        version=current.version + 1,
        actor_id=actor.membership_id,
        secret_reference_id=reference,
        credential_store=credential_store,
        changed_keys=sorted(changed),
        safe_changes=changes,
        reason=reason,
        restored_from=None,
    )


def restore_settings(
    db: Session,
    actor: Actor,
    *,
    source_version: int,
    expected_version: int,
    reason: str | None,
    credential_store: TenantCredentialStore | None,
) -> TenantSettingsSnapshot:
    _require_admin(actor)
    current = current_settings(db, actor.company_id, lock=True)
    if current.version != expected_version:
        raise Conflict()
    historical = db.scalar(
        select(TenantSettingsVersionRow).where(
            TenantSettingsVersionRow.company_id == actor.company_id,
            TenantSettingsVersionRow.version == source_version,
        )
    )
    if historical is None or historical.id == current.id:
        raise Conflict()
    source = _snapshot(historical)
    reference = (
        source.secret_reference_id
        if _valid_secret(
            db,
            actor.company_id,
            source.settings.provider_profile,
            source.secret_reference_id,
            credential_store,
        )
        else None
    )
    changed, changes = _safe_changes(current.settings, source.settings)
    if current.secret_reference_id != reference:
        changed.append("credential")
        changes["credential"] = {
            "previous": "REDACTED",
            "current": "REPLACEMENT_REQUIRED" if reference is None else "PROTECTED_REFERENCE",
        }
    return _insert_version(
        db,
        actor.company_id,
        source.settings,
        version=current.version + 1,
        actor_id=actor.membership_id,
        secret_reference_id=reference,
        credential_store=credential_store,
        changed_keys=sorted(changed),
        safe_changes=changes,
        reason=reason,
        restored_from=source.id,
    )


def settings_history(db: Session, actor: Actor) -> list[dict[str, Any]]:
    _require_admin(actor)
    current = current_settings(db, actor.company_id)
    rows = db.scalars(
        select(TenantSettingsVersionRow)
        .where(TenantSettingsVersionRow.company_id == actor.company_id)
        .order_by(TenantSettingsVersionRow.version.desc())
    ).all()
    return [
        {
            "id": str(row.id),
            "version": row.version,
            "created_at": row.created_at.isoformat(),
            "actor_membership_id": str(row.created_by_membership_id)
            if row.created_by_membership_id
            else None,
            "changed_keys": json.loads(row.changed_keys_json),
            "safe_changes": json.loads(row.safe_changes_json),
            "reason": row.reason,
            "restored_from_version_id": str(row.restored_from_version_id)
            if row.restored_from_version_id
            else None,
            "validation_status": row.validation_status,
            "current": row.id == current.id,
        }
        for row in rows
    ]


def seed_settings(
    db: Session,
    company: CompanyRow,
    bootstrap: Settings,
    credential_store: TenantCredentialStore | None,
) -> TenantSettingsSnapshot:
    """One-time explicit local seed. An existing owner version is never overwritten."""
    db.scalar(select(CompanyRow).where(CompanyRow.id == company.id).with_for_update())
    existing = db.get(TenantSettingsCurrentRow, company.id)
    if existing is not None:
        return current_settings(db, company.id)
    initial = TenantSettings(
        clarification_enabled=True,
        max_clarification_rounds_per_cycle=2,
        max_clarification_rounds_overall=10,
        expert_escalation_enabled=True,
        automatic_generation_enabled=bootstrap.automatic_generation_enabled is True,
        invitation_ttl_days=bootstrap.invitation_ttl_days,
        upload_policy=bootstrap.upload_policy(),
        clarification_policy=TenantClarificationPolicy(
            max_questions_per_round=bootstrap.clarification_policy().max_questions_per_round,
            max_answer_characters=bootstrap.clarification_policy().max_answer_characters,
        ),
        generation_policy=bootstrap.generation_policy(),
        provider_profile=(
            bootstrap.model_profile() if bootstrap.automatic_generation_enabled else None
        ),
        delivery_guide_policy=DeliveryGuidePolicy(enabled=True, include_handover_instructions=True),
        conventions=TenantConventions(
            report_naming="", semantic_modelling="", accessibility="", terminology={}
        ),
    )
    secret_reference_id = None
    if initial.automatic_generation_enabled:
        if credential_store is None or initial.provider_profile is None:
            raise ConfigurationUnavailable()
        secret_reference_id = credential_store.protect(
            db,
            company_id=company.id,
            profile_id=initial.provider_profile.profile_id,
            credential=bootstrap.model_credential(),
            actor_membership_id=None,
        )
    return _insert_version(
        db,
        company.id,
        initial,
        version=1,
        actor_id=None,
        secret_reference_id=secret_reference_id,
        credential_store=credential_store,
        changed_keys=list(TenantSettings.model_fields),
        safe_changes={},
        reason="Initial validated development/test seed",
        restored_from=None,
    )
