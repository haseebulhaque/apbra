from uuid import uuid4

import pytest
from alembic.config import Config
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from alembic import command
from apbra_api.config import Settings
from apbra_api.persistence import CaseAccessRow, CaseRow, Database


def test_clean_upgrade_head_and_recovery(settings: Settings, database: Database) -> None:
    inspector = inspect(database.engine)
    assert {"companies", "memberships", "reporting_cases", "case_request_versions"}.issubset(
        set(inspector.get_table_names())
    )
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.current(config, check_heads=True)


def test_first_migration_downgrades_and_reapplies_explicit_schema(
    settings: Settings, database: Database
) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.downgrade(config, "base")
    assert "reporting_cases" not in inspect(database.engine).get_table_names()
    command.upgrade(config, "head")
    assert "reporting_cases" in inspect(database.engine).get_table_names()


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
