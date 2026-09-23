from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from .config import Settings, get_settings
from .persistence import CompanyRow, Database, ExternalIdentityRow, MembershipRow


@dataclass(frozen=True)
class BootstrapIdentity:
    selector: str
    subject: str
    display_name: str
    company: str | None
    role: str | None


BOOTSTRAP_IDENTITIES = (
    BootstrapIdentity("owner", "dev-owner", "Avery Owner", "Acme Synthetic", "COMPANY_OWNER"),
    BootstrapIdentity("member", "dev-member", "Morgan Member", "Acme Synthetic", "MEMBER"),
    BootstrapIdentity("uninvited", "dev-uninvited", "Uma Uninvited", None, None),
    BootstrapIdentity("foreign", "dev-foreign", "Fran Foreign", "Beta Synthetic", "COMPANY_OWNER"),
)


def bootstrap(settings: Settings, database: Database) -> None:
    if not settings.bootstrap_enabled:
        return
    if settings.profile not in {"development", "test"}:
        raise RuntimeError("bootstrap is restricted to development and test profiles")
    with database.session() as db:
        companies: dict[str, CompanyRow] = {}
        for item in BOOTSTRAP_IDENTITIES:
            if item.company and item.company not in companies:
                company = db.scalar(select(CompanyRow).where(CompanyRow.name == item.company))
                if company is None:
                    company = CompanyRow(name=item.company)
                    db.add(company)
                    db.flush()
                companies[item.company] = company
            identity = db.scalar(
                select(ExternalIdentityRow).where(
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
            if item.company and item.role:
                company = companies[item.company]
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


def main() -> None:
    settings = get_settings()
    settings.validate_security_profile()
    bootstrap(settings, Database(settings.database_url))


if __name__ == "__main__":
    main()
