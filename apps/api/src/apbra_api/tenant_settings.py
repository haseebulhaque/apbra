"""Validated, immutable, tenant-authoritative operating policy.

Deployment configuration is used only to create a first local development/test
version. Normal operations read the tenant's effective database version.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
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


def private_preview_onboarding_settings_v1(company_display_name: str) -> TenantSettings:
    """Haseeb-approved APBRA-151 private-preview policy (Jira comment 10406).

    This is a versioned customer-onboarding policy, independent of the local
    development/test ``seed_settings`` and deployment bootstrap configuration.
    The caller supplies only the validated APBRA company display name.
    """
    if (
        not company_display_name
        or company_display_name != company_display_name.strip()
        or any(unicodedata.category(char) == "Cc" for char in company_display_name)
    ):
        raise ValueError("company display name is not validated")
    return TenantSettings.model_validate(
        {
            "clarification_enabled": True,
            "max_clarification_rounds_per_cycle": 2,
            "max_clarification_rounds_overall": 10,
            "expert_escalation_enabled": False,
            "automatic_generation_enabled": False,
            "invitation_ttl_days": 7,
            "upload_policy": {
                "data_extensions": ["CSV", "XLSX"],
                "reference_extensions": ["PNG", "JPG", "JPEG"],
                "max_file_bytes": 5_000_000,
                "max_files_per_selection": 8,
                "max_data_items_per_report": 20,
                "max_reference_items_per_report": 20,
            },
            "clarification_policy": {
                "max_questions_per_round": 5,
                "max_answer_characters": 2_000,
            },
            "generation_policy": {
                "organisation": {
                    "name": company_display_name,
                    "displayName": company_display_name,
                    "locale": "en-AU",
                    "timezone": "Australia/Sydney",
                },
                "branding": {
                    "primary": "#17635E",
                    "accent": "#2D7D9A",
                    "reportNaming": "Concise business report titles",
                    "pageNaming": "Short page names",
                    "executiveConvention": "Accessible summaries",
                    "themeName": "APBRA Default",
                },
                "generation": {
                    "enabled": True,
                    "supportedCapabilities": [
                        "KPI cards",
                        "Bar and column charts",
                        "Line charts",
                        "Tables",
                        "Slicers",
                        "Multiple pages",
                        "Explicit measures",
                    ],
                    "supportedTrendGrains": ["DAY", "MONTH", "QUARTER", "YEAR"],
                    "validationRequired": True,
                    "policy": "Governed candidate generation",
                },
                "governance": {
                    "requireKnowledge": True,
                    "requireAccessibility": True,
                    "requireValidation": True,
                    "maxVisualsPerPage": 6,
                    "maxPages": 5,
                    "humanReviewAtVisuals": 6,
                },
            },
            "provider_profile": None,
            "delivery_guide_policy": {
                "enabled": True,
                "include_handover_instructions": True,
            },
            "conventions": {
                "report_naming": "",
                "semantic_modelling": "",
                "accessibility": "",
                "terminology": {},
            },
        }
    )


@dataclass(frozen=True)
class TenantSettingsSnapshot:
    id: UUID
    company_id: UUID
    version: int
    settings: TenantSettings
    digest: str
    secret_reference_id: UUID | None
    validation_status: Literal["PASS"]


_QUALIFIED_IDENTITY_FIELDS = (
    "profile_id",
    "protocol",
    "endpoint",
    "model_or_deployment",
    "api_version",
    "region",
    "prompt_version",
    "configuration_id",
    "capabilities",
)
_QUALIFIED_BUDGET_FIELDS = (
    "max_calls_per_operation",
    "max_input_characters",
    "max_output_tokens",
    "time_budget_seconds",
    "request_timeout_seconds",
    "retry_limit",
)


def validate_qualified_profile(
    profile: ProviderProfile | None, qualified_profiles: tuple[ProviderProfile, ...]
) -> None:
    if profile is None:
        return
    qualified = next(
        (item for item in qualified_profiles if item.profile_id == profile.profile_id), None
    )
    if (
        qualified is None
        or any(
            getattr(profile, field) != getattr(qualified, field)
            for field in _QUALIFIED_IDENTITY_FIELDS
        )
        or any(
            getattr(profile, field) > getattr(qualified, field)
            for field in _QUALIFIED_BUDGET_FIELDS
        )
    ):
        raise ConfigurationUnavailable()


def _encoded(settings: TenantSettings) -> str:
    return json.dumps(
        settings.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":")
    )


def _snapshot(row: TenantSettingsVersionRow) -> TenantSettingsSnapshot:
    if row.validation_status != "PASS":
        raise ConfigurationUnavailable()
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
        validation_status="PASS",
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
    qualified_profiles: tuple[ProviderProfile, ...],
) -> TenantSettingsSnapshot:
    validate_qualified_profile(settings.provider_profile, qualified_profiles)
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


def create_private_preview_initial_settings(
    db: Session,
    company: CompanyRow,
    creator_membership_id: UUID,
) -> TenantSettingsSnapshot:
    """Create validated v1 and its pointer inside the caller's company transaction."""
    if db.get(TenantSettingsCurrentRow, company.id) is not None:
        raise Conflict()
    return _insert_version(
        db,
        company.id,
        private_preview_onboarding_settings_v1(company.name),
        version=1,
        actor_id=creator_membership_id,
        secret_reference_id=None,
        credential_store=None,
        changed_keys=list(TenantSettings.model_fields),
        safe_changes={},
        reason="APBRA Private Preview Onboarding Tenant Settings Template v1 (Jira 10406)",
        restored_from=None,
        qualified_profiles=(),
    )


def update_settings(
    db: Session,
    actor: Actor,
    settings: TenantSettings,
    *,
    expected_version: int,
    reason: str | None = None,
    secret_reference_id: UUID | None = None,
    credential_store: TenantCredentialStore | None = None,
    qualified_profiles: tuple[ProviderProfile, ...] = (),
) -> TenantSettingsSnapshot:
    _require_admin(actor)
    current = current_settings(db, actor.company_id, lock=True)
    if current.version != expected_version:
        raise Conflict()
    reference = current.secret_reference_id if secret_reference_id is None else secret_reference_id
    # A provider-profile switch cannot silently reuse a credential bound to another profile.
    next_identity = (
        tuple(getattr(settings.provider_profile, field) for field in _QUALIFIED_IDENTITY_FIELDS)
        if settings.provider_profile
        else None
    )
    current_identity = (
        tuple(
            getattr(current.settings.provider_profile, field)
            for field in _QUALIFIED_IDENTITY_FIELDS
        )
        if current.settings.provider_profile
        else None
    )
    if next_identity != current_identity and secret_reference_id is None:
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
        qualified_profiles=qualified_profiles,
    )


def restore_settings(
    db: Session,
    actor: Actor,
    *,
    source_version: int,
    expected_version: int,
    reason: str | None,
    credential_store: TenantCredentialStore | None,
    qualified_profiles: tuple[ProviderProfile, ...] = (),
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
        qualified_profiles=qualified_profiles,
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
        qualified_profiles=bootstrap.qualified_provider_profiles(),
    )
