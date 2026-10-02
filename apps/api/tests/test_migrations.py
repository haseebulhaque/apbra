import hashlib
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from conftest import csrf, disposable_alembic_config, sign_in, validate_disposable_database_url
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_generation import confirmed_case

from alembic import command
from apbra_api.bootstrap import bootstrap
from apbra_api.config import Settings
from apbra_api.persistence import CaseAccessRow, CaseRow, Database, ExternalIdentityRow


def test_clean_upgrade_head_and_recovery(settings: Settings, database: Database) -> None:
    inspector = inspect(database.engine)
    assert {
        "companies",
        "memberships",
        "reporting_cases",
        "case_request_versions",
        "generation_attempts",
        "generated_artifacts",
        "reviewed_report_designs",
        "case_reference_materials",
        "automatic_design_attempts",
        "tenant_settings_versions",
        "tenant_settings_current",
        "tenant_secret_records",
        "case_clarification_cycles",
        "authentication_events",
    }.issubset(set(inspector.get_table_names()))
    assert "uq_generation_case_active" in {
        index["name"] for index in inspector.get_indexes("generation_attempts")
    }
    config = disposable_alembic_config(settings.database_url)
    command.current(config, check_heads=True)
    with database.session() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "20261002_07"


def test_provider_binding_migration_preserves_legacy_identity_and_round_trips(
    settings: Settings, database: Database
) -> None:
    with database.session() as db:
        legacy = db.scalar(text("SELECT id FROM external_identities WHERE subject='dev-owner'"))
        assert legacy is not None
        profile = db.scalar(
            text("SELECT provider_profile_id FROM external_identities WHERE id=:id"),
            {"id": legacy},
        )
        assert profile == "legacy-unqualified"
        membership_count = db.scalar(
            text("SELECT count(*) FROM memberships WHERE identity_id=:id"), {"id": legacy}
        )
        assert membership_count == 1
    inspector = inspect(database.engine)
    assert "provider_profile_id" in {
        column["name"] for column in inspector.get_columns("external_identities")
    }
    assert "uq_identity_profile_issuer_subject" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("external_identities")
    }
    config = disposable_alembic_config(settings.database_url)
    command.downgrade(config, "20261001_06")
    assert "authentication_events" not in inspect(database.engine).get_table_names()
    command.upgrade(config, "head")
    with database.session() as db:
        assert (
            db.scalar(
                text("SELECT count(*) FROM memberships WHERE identity_id=:id"), {"id": legacy}
            )
            == 1
        )
        assert (
            db.scalar(
                text("SELECT provider_profile_id FROM external_identities WHERE id=:id"),
                {"id": legacy},
            )
            == "legacy-unqualified"
        )


def test_provider_binding_downgrade_refuses_legacy_key_collision(
    settings: Settings, database: Database
) -> None:
    with database.session() as db:
        db.add_all(
            [
                ExternalIdentityRow(
                    provider_profile_id=profile,
                    issuer="https://issuer.example/tenant",
                    subject="same-subject",
                    display_name="Synthetic",
                )
                for profile in ("entra-a", "entra-b")
            ]
        )
    config = disposable_alembic_config(settings.database_url)
    with pytest.raises(RuntimeError, match="legacy issuer/subject key collides"):
        command.downgrade(config, "20261001_06")
    with database.session() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "20261002_07"


def _assert_qualified_downgrade_preserves_state(
    settings: Settings, database: Database, table: str, row_id: object
) -> None:
    profile_state = sa.table(table, sa.column("id", sa.Uuid()), sa.column("provider_profile_id"))
    config = disposable_alembic_config(settings.database_url)
    with pytest.raises(RuntimeError, match=f"provider-qualified security state in {table}"):
        command.downgrade(config, "20261001_06")
    with database.session() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "20261002_07"
        assert (
            db.scalar(
                sa.select(profile_state.c.provider_profile_id).where(
                    profile_state.c.id == UUID(str(row_id))
                )
            )
            == "qualified-entra"
        )
    assert "provider_profile_id" in {
        column["name"] for column in inspect(database.engine).get_columns(table)
    }
    assert "authentication_events" in inspect(database.engine).get_table_names()


def test_provider_binding_downgrade_refuses_single_qualified_identity(
    settings: Settings, database: Database
) -> None:
    with database.session() as db:
        identity_id = db.scalar(
            text("SELECT id FROM external_identities WHERE subject='dev-owner'")
        )
        assert identity_id is not None
        db.execute(
            text("UPDATE external_identities SET provider_profile_id=:profile WHERE id=:id"),
            {"profile": "qualified-entra", "id": identity_id},
        )
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM external_identities "
                    "WHERE issuer=(SELECT issuer FROM external_identities WHERE id=:id) "
                    "AND subject=(SELECT subject FROM external_identities WHERE id=:id)"
                ),
                {"id": identity_id},
            )
            == 1
        )
    _assert_qualified_downgrade_preserves_state(
        settings, database, "external_identities", identity_id
    )
    with database.session() as db:
        assert (
            db.scalar(
                text("SELECT count(*) FROM memberships WHERE identity_id=:id"), {"id": identity_id}
            )
            == 1
        )


def test_provider_binding_downgrade_refuses_active_qualified_invitation(
    settings: Settings, database: Database, client: TestClient
) -> None:
    owner_session = sign_in(client, "owner")
    issued = client.post(
        "/api/invitations",
        json={"subject": "dev-uninvited", "role": "MEMBER"},
        headers=csrf(owner_session),
    )
    assert issued.status_code == 200, issued.text
    invitation_id = issued.json()["invitation"]["id"]
    with database.session() as db:
        db.execute(
            text("UPDATE invitations SET provider_profile_id=:profile WHERE id=:id"),
            {"profile": "qualified-entra", "id": invitation_id},
        )
        assert db.execute(
            text("SELECT consumed_at, revoked_at FROM invitations WHERE id=:id"),
            {"id": invitation_id},
        ).one() == (None, None)
    _assert_qualified_downgrade_preserves_state(settings, database, "invitations", invitation_id)
    with database.session() as db:
        assert (
            db.scalar(
                text("SELECT token_digest FROM invitations WHERE id=:id"), {"id": invitation_id}
            )
            is not None
        )


@pytest.mark.parametrize(
    "table", ("auth_transactions", "application_sessions", "authentication_events")
)
def test_provider_binding_downgrade_refuses_qualified_auth_provenance(
    settings: Settings, database: Database, client: TestClient, table: str
) -> None:
    sign_in(client, "owner")
    profile_state = sa.table(table, sa.column("id", sa.Uuid()), sa.column("provider_profile_id"))
    with database.session() as db:
        # Isolate each guard: local sign-in also creates profile-qualified rows
        # in the other two tables, which would mask a missing check here.
        for other in ("auth_transactions", "application_sessions", "authentication_events"):
            if other != table:
                legacy_state = sa.table(other, sa.column("provider_profile_id"))
                db.execute(sa.update(legacy_state).values(provider_profile_id="legacy-unqualified"))
        row_id = db.scalar(sa.select(profile_state.c.id).limit(1))
        assert row_id is not None
        db.execute(
            sa.update(profile_state)
            .where(profile_state.c.id == row_id)
            .values(provider_profile_id="qualified-entra")
        )
    _assert_qualified_downgrade_preserves_state(settings, database, table, row_id)


def test_package_c_to_reviewed_design_upgrade_is_isolated(
    settings: Settings, database: Database, client: TestClient
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Compare completed cases by team.",
        "cases.csv",
        b"Team,Completed\nA,4\nB,7\n",
    )
    generated = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": str(uuid4()),
        },
        headers=csrf(session),
    )
    assert generated.status_code == 201, generated.text
    original = generated.json()["attempt"]
    assert original["status"] == "SUCCEEDED"
    original_bytes = client.get(
        f"/api/cases/{case['id']}/generation/{original['id']}/artifact"
    ).content
    # This test exercises the older generation migration. Its disposable
    # local-test authentication state has no pre-172 profile representation.
    with database.session() as db:
        db.execute(text("DELETE FROM authentication_events"))
        db.execute(text("DELETE FROM application_sessions"))
        db.execute(text("DELETE FROM auth_transactions"))
    config = disposable_alembic_config(settings.database_url)
    command.downgrade(config, "20260924_03")
    inspector = inspect(database.engine)
    assert "reviewed_report_designs" not in inspector.get_table_names()
    assert "reviewed_design_id" not in {
        column["name"] for column in inspector.get_columns("generation_attempts")
    }
    with database.session() as db:
        historical = db.execute(
            text("SELECT status, artifact_id FROM generation_attempts WHERE id=:id"),
            {"id": original["id"]},
        ).one()
        assert historical.status == "SUCCEEDED"
        assert str(historical.artifact_id) == original["artifact"]["id"]
    command.upgrade(config, "20260929_04")
    inspector = inspect(database.engine)
    assert "reviewed_report_designs" in inspector.get_table_names()
    assert "reviewed_design_id" in {
        column["name"] for column in inspector.get_columns("generation_attempts")
    }
    with database.session() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "20260929_04"
        historical = db.execute(
            text(
                "SELECT status, artifact_id, reviewed_design_id "
                "FROM generation_attempts WHERE id=:id"
            ),
            {"id": original["id"]},
        ).one()
        assert historical.status == "SUCCEEDED"
        assert str(historical.artifact_id) == original["artifact"]["id"]
        assert historical.reviewed_design_id is None
    command.upgrade(config, "head")
    with database.session() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "20261002_07"
    # The deliberate downgrade removed the new tenant-settings tables. Re-seed
    # only this disposable test tenant before exercising the restored API.
    bootstrap(settings, database)
    sign_in(client, "member")
    restored = client.get(f"/api/cases/{case['id']}/generation/{original['id']}/artifact")
    assert restored.status_code == 200
    assert restored.content == original_bytes
    assert hashlib.sha256(restored.content).hexdigest() == original["artifact"]["content_digest"]


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
            "postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra?dbname=apbra_test",
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
