"""Tenant date-display preference, separate from immutable report-generation policy."""

from __future__ import annotations

from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import Actor, ConfigurationUnavailable, Conflict, Forbidden, Role
from .persistence import (
    CompanyRow,
    TenantDateDisplayCurrentRow,
    TenantDateDisplayVersionRow,
)


class DateDisplayUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=0)
    time_zone: str | None = Field(max_length=255)

    @field_validator("time_zone")
    @classmethod
    def valid_zone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # Membership in the actual installed IANA database also rejects offset strings,
        # absolute paths, whitespace and user-defined TZ files.
        if value in {"Factory", "localtime", "posixrules"} or value not in available_timezones():
            raise ValueError("Select an installed IANA time zone")
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Select an installed IANA time zone") from None
        return value


def require_admin(actor: Actor) -> None:
    if actor.role not in {Role.COMPANY_OWNER, Role.COMPANY_ADMIN}:
        raise Forbidden()


def current(db: Session, company_id: UUID) -> dict[str, object]:
    pointer = db.get(TenantDateDisplayCurrentRow, company_id)
    if pointer is None:
        # Read-only implicit default: each viewer's browser local zone. No backfill.
        return {"company_id": str(company_id), "version": 0, "time_zone": None}
    row = db.scalar(
        select(TenantDateDisplayVersionRow).where(
            TenantDateDisplayVersionRow.id == pointer.version_id,
            TenantDateDisplayVersionRow.company_id == company_id,
            TenantDateDisplayVersionRow.version == pointer.version,
        )
    )
    if row is None:
        raise ConfigurationUnavailable()
    return {"company_id": str(company_id), "version": row.version, "time_zone": row.time_zone}


def update(db: Session, actor: Actor, payload: DateDisplayUpdate) -> dict[str, object]:
    require_admin(actor)
    # Lock the stable tenant row, including the first save (no pointer exists yet).
    # This serializes simultaneous expected-version-zero requests without upserts
    # that could silently overwrite a concurrent administrator's selection.
    company = db.scalar(
        select(CompanyRow)
        .where(
            CompanyRow.id == actor.company_id,
            CompanyRow.active.is_(True),
        )
        .with_for_update()
    )
    if company is None:
        raise Forbidden()
    before = current(db, actor.company_id)
    if payload.expected_version != before["version"]:
        raise Conflict()
    row = TenantDateDisplayVersionRow(
        company_id=actor.company_id,
        version=payload.expected_version + 1,
        time_zone=payload.time_zone,
        created_by_membership_id=actor.membership_id,
    )
    db.add(row)
    db.flush()
    pointer = db.get(TenantDateDisplayCurrentRow, actor.company_id)
    if pointer is None:
        db.add(
            TenantDateDisplayCurrentRow(
                company_id=actor.company_id,
                version_id=row.id,
                version=row.version,
            )
        )
    else:
        pointer.version_id, pointer.version = row.id, row.version
    db.flush()
    return current(db, actor.company_id)


def history(db: Session, actor: Actor) -> list[dict[str, object]]:
    require_admin(actor)
    return [
        {
            "version": row.version,
            "time_zone": row.time_zone,
            "created_at": row.created_at.isoformat(),
        }
        for row in db.scalars(
            select(TenantDateDisplayVersionRow)
            .where(
                TenantDateDisplayVersionRow.company_id == actor.company_id,
            )
            .order_by(TenantDateDisplayVersionRow.version.desc())
        )
    ]
