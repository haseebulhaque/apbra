from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread

import pytest
from sqlalchemy import select

from apbra_api.domain import AuthenticationRequired, OidcClaims
from apbra_api.identity_service import IdentityService
from apbra_api.persistence import AuthenticationEventRow, Database, ExternalIdentityRow


def claims(issuer: str, subject: str, name: str = "Same display name") -> OidcClaims:
    return OidcClaims(
        issuer=issuer,
        subject=subject,
        audience="qualified-client",
        nonce="validated-nonce",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        display_name=name,
    )


def test_identity_binding_is_profile_issuer_subject_not_mutable_display_data(
    database: Database,
) -> None:
    service = IdentityService()
    with database.session() as db:
        first = service.resolve(
            db, profile_id="entra-a", claims=claims("https://issuer.example/a", "subject-1")
        )
        first_id = first.id
        returning = service.resolve(
            db,
            profile_id="entra-a",
            claims=claims("https://issuer.example/a", "subject-1", "Changed email/name"),
        )
        assert returning.id == first_id
        different_subject = service.resolve(
            db,
            profile_id="entra-a",
            claims=claims("https://issuer.example/a", "subject-2"),
        )
        different_issuer = service.resolve(
            db,
            profile_id="entra-a",
            claims=claims("https://issuer.example/b", "subject-1"),
        )
        different_profile = service.resolve(
            db,
            profile_id="entra-b",
            claims=claims("https://issuer.example/a", "subject-1"),
        )
        assert len({first_id, different_subject.id, different_issuer.id, different_profile.id}) == 4
        assert (
            db.scalar(
                select(AuthenticationEventRow).where(
                    AuthenticationEventRow.identity_id == first_id,
                    AuthenticationEventRow.event_type == "IDENTITY_BOUND",
                )
            )
            is not None
        )


def test_missing_email_is_not_required_and_disabled_binding_fails_closed(
    database: Database,
) -> None:
    service = IdentityService()
    with database.session() as db:
        identity = service.resolve(
            db, profile_id="entra-a", claims=claims("https://issuer.example/a", "no-email", "")
        )
        assert identity.display_name == "APBRA user"
        identity.active = False
    with database.session() as db:
        with pytest.raises(AuthenticationRequired):
            service.resolve(
                db,
                profile_id="entra-a",
                claims=claims("https://issuer.example/a", "no-email"),
            )


def test_legacy_identity_is_reused_only_for_exact_local_binding(database: Database) -> None:
    service = IdentityService()
    with database.session() as db:
        legacy = db.scalar(
            select(ExternalIdentityRow).where(ExternalIdentityRow.subject == "dev-owner")
        )
        assert legacy is not None
        same = service.resolve(
            db,
            profile_id="local-test",
            claims=claims(legacy.issuer, legacy.subject),
            allow_legacy_local=True,
        )
        assert same.id == legacy.id
        distinct = service.resolve(
            db,
            profile_id="entra-qualified",
            claims=claims(legacy.issuer, legacy.subject),
            allow_legacy_local=False,
        )
        assert distinct.id != legacy.id


def test_concurrent_first_binding_returns_one_identity(database: Database) -> None:
    service = IdentityService()
    barrier = Barrier(2)
    ids: list[object] = []
    failures: list[Exception] = []

    def resolve() -> None:
        try:
            barrier.wait()
            with database.session() as db:
                identity = service.resolve(
                    db,
                    profile_id="entra-a",
                    claims=claims("https://issuer.example/a", "racing-subject"),
                )
                ids.append(identity.id)
        except Exception as exc:
            failures.append(exc)

    first, second = Thread(target=resolve), Thread(target=resolve)
    first.start()
    second.start()
    first.join()
    second.join()
    assert not failures
    assert len(ids) == 2 and ids[0] == ids[1]
