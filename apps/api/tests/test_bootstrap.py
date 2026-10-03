from uuid import UUID

import pytest
from sqlalchemy import func, select

from apbra_api.bootstrap import BOOTSTRAP_IDENTITIES, BootstrapIdentity, bootstrap
from apbra_api.config import Settings
from apbra_api.persistence import (
    CompanyRow,
    Database,
    ExternalIdentityRow,
    MembershipRow,
)


def test_bootstrap_is_idempotent_and_server_controlled(database: Database) -> None:
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(CompanyRow)) == 2
        assert db.scalar(select(func.count()).select_from(ExternalIdentityRow)) == 5
        assert db.scalar(select(func.count()).select_from(MembershipRow)) == 3


def test_bootstrap_never_claims_user_company_by_display_name(
    database: Database, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A matching name alone cannot bind synthetic fixture identities."""
    fixture_id = UUID("6c66299f-d81a-4ba8-bb6e-cbc7604a2242")
    with database.session() as db:
        creator = db.scalar(
            select(ExternalIdentityRow).where(ExternalIdentityRow.subject == "dev-creator")
        )
        assert creator is not None
        creator_id = creator.id
        user_company = CompanyRow(name="Acme Synthetic")
        db.add(user_company)
        db.flush()
        user_company_id = user_company.id
        db.add(
            MembershipRow(company_id=user_company_id, identity_id=creator_id, role="COMPANY_OWNER")
        )

    monkeypatch.setattr(
        "apbra_api.bootstrap.BOOTSTRAP_IDENTITIES",
        BOOTSTRAP_IDENTITIES
        + (
            BootstrapIdentity(
                "collision-owner",
                "dev-collision-owner",
                "Synthetic Collision Owner",
                fixture_id,
                "Acme Synthetic",
                "COMPANY_OWNER",
            ),
        ),
    )
    bootstrap(settings, database)
    with database.session() as db:
        fixture_identity = db.scalar(
            select(ExternalIdentityRow).where(ExternalIdentityRow.subject == "dev-collision-owner")
        )
        assert fixture_identity is not None
        fixture_membership = db.scalar(
            select(MembershipRow).where(MembershipRow.identity_id == fixture_identity.id)
        )
        user_membership = db.scalar(
            select(MembershipRow).where(MembershipRow.identity_id == creator_id)
        )
        assert fixture_membership is not None and user_membership is not None
        assert fixture_membership.company_id == fixture_id
        assert fixture_membership.company_id != user_company_id
        assert user_membership.company_id == user_company_id


def test_bootstrap_never_binds_a_different_provider_profile(
    database: Database, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = "dev-profile-collision"
    fixture_id = UUID("343db02d-3293-44bf-aa16-60aa189eb792")
    with database.session() as db:
        qualified = ExternalIdentityRow(
            provider_profile_id="qualified-other",
            issuer=settings.issuer,
            subject=subject,
            display_name="Different Qualified Identity",
        )
        db.add(qualified)
        db.flush()
        qualified_id = qualified.id
    monkeypatch.setattr(
        "apbra_api.bootstrap.BOOTSTRAP_IDENTITIES",
        BOOTSTRAP_IDENTITIES
        + (
            BootstrapIdentity(
                "profile-collision",
                subject,
                "Synthetic Fixture Identity",
                fixture_id,
                "Profile Fixture",
                "COMPANY_OWNER",
            ),
        ),
    )
    bootstrap(settings, database)
    with database.session() as db:
        identities = db.scalars(
            select(ExternalIdentityRow).where(
                ExternalIdentityRow.issuer == settings.issuer,
                ExternalIdentityRow.subject == subject,
            )
        ).all()
        assert {identity.provider_profile_id for identity in identities} == {
            "legacy-unqualified",
            "qualified-other",
        }
        qualified_memberships = db.scalars(
            select(MembershipRow).where(MembershipRow.identity_id == qualified_id)
        ).all()
        assert not qualified_memberships
        fixture_identity = next(
            identity
            for identity in identities
            if identity.provider_profile_id == "legacy-unqualified"
        )
        fixture_membership = db.scalar(
            select(MembershipRow).where(MembershipRow.identity_id == fixture_identity.id)
        )
        assert fixture_membership is not None
        assert fixture_membership.company_id == fixture_id
