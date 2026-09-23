from uuid import uuid4

import pytest
from conftest import csrf, disposable_alembic_config, sign_in, validate_disposable_database_url
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from alembic import command
from apbra_api.config import Settings
from apbra_api.persistence import CaseAccessRow, CaseRow, Database


def test_clean_upgrade_head_and_recovery(settings: Settings, database: Database) -> None:
    inspector = inspect(database.engine)
    assert {"companies", "memberships", "reporting_cases", "case_request_versions"}.issubset(
        set(inspector.get_table_names())
    )
    config = disposable_alembic_config(settings.database_url)
    command.current(config, check_heads=True)


def test_first_migration_downgrades_and_reapplies_explicit_schema(
    settings: Settings, database: Database
) -> None:
    config = disposable_alembic_config(settings.database_url)
    command.downgrade(config, "base")
    assert "reporting_cases" not in inspect(database.engine).get_table_names()
    command.upgrade(config, "head")
    assert "reporting_cases" in inspect(database.engine).get_table_names()


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "postgresql+psycopg://apbra:unused@127.0.0.1:54321/apbra",
        "postgresql+psycopg://apbra:unused@database.internal:5432/apbra_test",
        "postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_test?host=preview",
        "postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_test?service=preview",
        "postgresql+psycopg://apbra:unused@127.0.0.1/apbra_test",
        "postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_test?host=one&host=two",
        "sqlite:///apbra_test",
    ],
)
def test_backend_reset_target_rejected_before_alembic_config(unsafe_url: str) -> None:
    with pytest.raises(pytest.UsageError):
        disposable_alembic_config(unsafe_url)


def test_backend_reset_target_rejects_inherited_libpq_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PGSERVICE", "preview")
    with pytest.raises(pytest.UsageError, match="PGSERVICE"):
        validate_disposable_database_url(
            "postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_test"
        )


def test_explicit_disposable_target_wins_over_application_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_url = "postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_test"
    monkeypatch.setenv(
        "APBRA_DATABASE_URL",
        "postgresql+psycopg://apbra:unused@127.0.0.1:54321/apbra",
    )
    config = disposable_alembic_config(test_url)
    assert config.get_main_option("sqlalchemy.url") == test_url


@pytest.mark.parametrize(
    "application_url, expected",
    [
        (
            "postgresql://apbra:unused@127.0.0.1:54322/apbra_test",
            "must be distinct",
        ),
        (
            "postgresql://apbra:unused@database.internal:6432/apbra_test",
            "must be distinct",
        ),
        (
            "postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra"
            "?dbname=apbra_test",
            "must expose an unambiguous",
        ),
    ],
)
def test_backend_reset_rejects_ambiguous_or_equivalent_application_targets(
    monkeypatch: pytest.MonkeyPatch, application_url: str, expected: str
) -> None:
    monkeypatch.setenv("APBRA_DATABASE_URL", application_url)
    with pytest.raises(pytest.UsageError, match=expected):
        validate_disposable_database_url(
            "postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_test"
        )


def test_locked_psycopg_dialect_receives_only_the_validated_target() -> None:
    test_url = validate_disposable_database_url(
        "postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_test"
    )
    args, kwargs = postgresql.psycopg.dialect().create_connect_args(make_url(test_url))
    assert args == []
    assert kwargs == {
        "dbname": "apbra_test",
        "user": "apbra",
        "password": "unused",
        "host": "127.0.0.1",
        "port": 54322,
    }


def test_request_versions_are_database_immutable(client: TestClient, database: Database) -> None:
    session = sign_in(client, "owner")
    created = client.post(
        "/api/cases",
        json={"request_text": "Preserve this original business request."},
        headers={**csrf(session), "Idempotency-Key": str(uuid4())},
    )
    assert created.status_code == 201
    with database.session() as db:
        row = db.execute(text("SELECT id FROM case_request_versions LIMIT 1")).first()
        assert row is not None
        with pytest.raises(DBAPIError):
            db.execute(
                text("UPDATE case_request_versions SET request_text='tampered' WHERE id=:id"),
                {"id": row.id},
            )


def test_composite_foreign_key_rejects_cross_company_private_access(
    client: TestClient, database: Database
) -> None:
    session = sign_in(client, "owner")
    created = client.post(
        "/api/cases",
        json={"request_text": "Company-consistent private access."},
        headers={**csrf(session), "Idempotency-Key": str(uuid4())},
    )
    assert created.status_code == 201
    case_id = created.json()["case"]["id"]
    with database.session() as db:
        case = db.get(CaseRow, case_id)
        foreign_membership = db.execute(
            text(
                """
                SELECT memberships.id
                FROM memberships
                JOIN companies ON companies.id=memberships.company_id
                WHERE companies.name='Beta Synthetic'
                """
            )
        ).first()
        assert case is not None and foreign_membership is not None
        db.add(
            CaseAccessRow(
                case_id=case.id,
                company_id=case.company_id,
                membership_id=foreign_membership.id,
                access_level="VIEWER",
            )
        )
        foreign_membership_id = foreign_membership.id
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    with database.session() as db:
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM case_access "
                    "WHERE case_id=:case_id AND membership_id=:membership_id"
                ),
                {"case_id": case_id, "membership_id": foreign_membership_id},
            )
            == 0
        )
