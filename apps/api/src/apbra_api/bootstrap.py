from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .persistence import (
    CompanyCreationCommandRow,
    CompanyRow,
    Database,
    ExternalIdentityRow,
    MembershipRow,
)
from .tenant_secrets import AesGcmTenantCredentialStore
from .tenant_settings import seed_settings


@dataclass(frozen=True)
class BootstrapIdentity:
    selector: str
    subject: str
    display_name: str
    company_id: UUID | None
    company: str | None
    role: str | None


_ACME_FIXTURE_ID = UUID("862f1a32-46c1-48c7-9f2f-c50b7d9e0507")
_BETA_FIXTURE_ID = UUID("655e01b9-6bc5-4315-9131-99fc8bc10d11")

BOOTSTRAP_IDENTITIES = (
    BootstrapIdentity(
        "owner", "dev-owner", "Avery Owner", _ACME_FIXTURE_ID, "Acme Synthetic", "COMPANY_OWNER"
    ),
    BootstrapIdentity(
        "member", "dev-member", "Morgan Member", _ACME_FIXTURE_ID, "Acme Synthetic", "MEMBER"
    ),
    BootstrapIdentity("uninvited", "dev-uninvited", "Uma Uninvited", None, None, None),
    BootstrapIdentity("creator", "dev-creator", "Cora Creator", None, None, None),
    BootstrapIdentity(
        "foreign",
        "dev-foreign",
        "Fran Foreign",
        _BETA_FIXTURE_ID,
        "Beta Synthetic",
        "COMPANY_OWNER",
    ),
)


def _legacy_fixture_company(db: Session, item: BootstrapIdentity, issuer: str) -> CompanyRow | None:
    """Recognize old local fixtures by exact synthetic identity and membership.

    A matching company display name alone never identifies a fixture. A
    durable APBRA-151 creation command proves that the company was created by
    a user, even if that user is also a synthetic development identity.
    """
    assert item.company is not None and item.role is not None
    identity = db.scalar(
        select(ExternalIdentityRow).where(
            ExternalIdentityRow.provider_profile_id == "legacy-unqualified",
            ExternalIdentityRow.issuer == issuer,
            ExternalIdentityRow.subject == item.subject,
        )
    )
    if identity is None:
        return None
    memberships = db.scalars(
        select(MembershipRow).where(
            MembershipRow.identity_id == identity.id,
            MembershipRow.role == item.role,
            MembershipRow.active.is_(True),
        )
    ).all()
    candidates = [
        company
        for membership in memberships
        if (company := db.get(CompanyRow, membership.company_id)) is not None
        and company.active
        and company.name == item.company
        and db.scalar(
            select(CompanyCreationCommandRow.id).where(
                CompanyCreationCommandRow.company_id == company.id
            )
        ) is None
    ]
    return candidates[0] if len(candidates) == 1 else None


def bootstrap(settings: Settings, database: Database) -> None:
    if not settings.bootstrap_enabled:
        return
    if settings.profile not in {"development", "test"}:
        raise RuntimeError("bootstrap is restricted to development and test profiles")
    credential_store = AesGcmTenantCredentialStore.from_bootstrap(
        settings.tenant_secret_keyring_json.get_secret_value()
        if settings.tenant_secret_keyring_json
        else None
    )
    with database.session() as db:
        companies: dict[UUID, CompanyRow] = {}
        for item in BOOTSTRAP_IDENTITIES:
            if item.company_id is not None and item.company_id not in companies:
                assert item.company is not None
                company = db.get(CompanyRow, item.company_id)
                if company is None:
                    company = _legacy_fixture_company(db, item, settings.issuer)
                    if company is None:
                        company = CompanyRow(id=item.company_id, name=item.company)
                        db.add(company)
                        db.flush()
                elif company.name != item.company:
                    raise RuntimeError(
                        "local fixture company identity conflicts with existing data"
                    )
                companies[item.company_id] = company
            identity = db.scalar(
                select(ExternalIdentityRow).where(
                    ExternalIdentityRow.provider_profile_id == "legacy-unqualified",
                    ExternalIdentityRow.issuer == settings.issuer,
                    ExternalIdentityRow.subject == item.subject,
                )
            )
            if identity is None:
                identity = ExternalIdentityRow(
                    issuer=settings.issuer,
                    subject=item.subject,
                    display_name=item.display_name,
                )
                db.add(identity)
                db.flush()
            if item.company_id is not None and item.role:
                company = companies[item.company_id]
                membership = db.scalar(
                    select(MembershipRow).where(
                        MembershipRow.company_id == company.id,
                        MembershipRow.identity_id == identity.id,
                    )
                )
                if membership is None:
                    db.add(
                        MembershipRow(
                            company_id=company.id,
                            identity_id=identity.id,
                            role=item.role,
                        )
                    )
        db.flush()
        for company in companies.values():
            seed_settings(db, company, settings, credential_store)


def main() -> None:
    settings = get_settings()
    settings.validate_security_profile()
    bootstrap(settings, Database(settings.database_url))


if __name__ == "__main__":
    main()
