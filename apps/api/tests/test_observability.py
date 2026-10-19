"""Offline structural tests are explicit; PostgreSQL integration tests need its fixture."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from apbra_api.domain import Actor, Forbidden, ProtectedResourceNotFound, Role
from apbra_api.model_provider import ProviderCallError
from apbra_api.observability import (
    CURRENT_CORRELATION,
    HistoryFilters,
    HistoryQueryInvalid,
    _audit_details,
    _cursor_decode,
    _cursor_encode,
    _safe_diagnostic,
    audit_detail,
    diagnostic_json,
    error_detail,
    list_audit,
    list_errors,
    record_system_error,
)
from apbra_api.persistence import (
    ApplicationSession,
    AuditEventRow,
    Base,
    Database,
    SystemErrorDiagnosticRow,
    SystemErrorRow,
)


@pytest.fixture
def offline_actor() -> Actor:
    return Actor(
        uuid4(),
        uuid4(),
        uuid4(),
        "synthetic",
        "synthetic",
        "Synthetic owner",
        Role.COMPANY_OWNER,
        "synthetic",
    )


@pytest.fixture
def offline_db(offline_actor: Actor, monkeypatch: pytest.MonkeyPatch) -> Any:
    # Query/transaction unit harness only. This does not prove PostgreSQL FKs or triggers.
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def functions(connection: Any, _: Any) -> None:
        connection.create_function("octet_length", 1, lambda value: len(value.encode()))

    Base.metadata.create_all(
        engine,
        tables=[
            SystemErrorRow.__table__,
            SystemErrorDiagnosticRow.__table__,
            AuditEventRow.__table__,
        ],
    )
    with ApplicationSession(engine, expire_on_commit=False) as db:
        monkeypatch.setattr(db, "active_actor", lambda *args: offline_actor)
        monkeypatch.setattr(db, "case_access", lambda *args: None)
        yield db
    engine.dispose()


@pytest.mark.parametrize("limit", [0, 101, True, -1])
def test_offline_filter_limit_validation(limit: int) -> None:
    with pytest.raises(ValueError):
        HistoryFilters(limit=limit)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"from_time": datetime(2026, 1, 1)},
        {"module": "secret"},
        {"operation": "raw/path"},
        {"outcome": "bogus"},
        {"cursor": "x" * 2049},
        {
            "from_time": datetime(2026, 2, 1, tzinfo=UTC),
            "to_time": datetime(2026, 1, 1, tzinfo=UTC),
        },
    ],
)
def test_offline_filter_rejects_invalid_values(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        HistoryFilters(**kwargs)


def test_offline_cursor_signature_and_scope() -> None:
    timestamp, identifier = datetime.now(UTC), uuid4()
    cursor = _cursor_encode((timestamp, identifier), "scope-a", "synthetic-session-secret")
    assert _cursor_decode(cursor, "scope-a", "synthetic-session-secret") == (timestamp, identifier)
    for value, scope, secret in [
        (cursor, "scope-b", "synthetic-session-secret"),
        (cursor, "scope-a", "different-session-secret"),
        (cursor[:-1] + "!", "scope-a", "synthetic-session-secret"),
        ("not-base64", "scope-a", "synthetic-session-secret"),
    ]:
        with pytest.raises(ValueError, match="cursor"):
            _cursor_decode(value, scope, secret)


def test_offline_redaction_never_formats_error_values() -> None:
    class HostileError(RuntimeError):
        def __str__(self) -> str:
            raise AssertionError("must not format exception")

    try:
        raise HostileError("private-document-content-and-secret")
    except HostileError as error:
        encoded, truncated = diagnostic_json(error)
    assert "private-document" not in encoded
    assert not truncated
    assert len(encoded.encode()) <= 4096
    assert set(json.loads(encoded)) == {"exception_type", "frames"}
    assert set(json.loads(encoded)["frames"][0]) == {"module", "function", "line"}


def test_offline_diagnostic_frame_limit() -> None:
    def recurse(depth: int) -> None:
        if depth:
            recurse(depth - 1)
        else:
            raise ValueError("withheld")

    try:
        recurse(20)
    except ValueError as error:
        encoded, truncated = diagnostic_json(error)
    assert truncated
    assert len(json.loads(encoded)["frames"]) == 8


def test_offline_legacy_audit_details_allowlist() -> None:
    identifier = str(uuid4())
    details = _audit_details(
        json.dumps(
            {
                "artifact_id": identifier,
                "digest": "a" * 64,
                "role": "COMPANY_ADMIN",
                "version": 3,
                "prompt": "private",
                "api_key": "private",
                "message": "private",
                "count": 7,
            }
        )
    )
    assert details == {
        "artifact_id": identifier,
        "digest": "a" * 64,
        "role": "COMPANY_ADMIN",
        "version": 3,
    }
    assert _audit_details("not-json") == {}
    assert _audit_details("[]") == {}
    assert _audit_details(json.dumps({"role": {}, "outcome": []})) == {}
    assert _audit_details(json.dumps({"message": "x" * 5000})) == {}


def test_offline_untrusted_technical_payload_is_structurally_projected() -> None:
    assert _safe_diagnostic(
        '{"exception_type":"ValueError","frames":[],"secret":"private"}', False
    ) == {
        "diagnostic": {"exception_type": "ValueError", "frames": []},
        "truncated": False,
    }
    assert _safe_diagnostic('{"exception_type":"private/path","frames":[]}', False) is None
    assert _safe_diagnostic("invalid", False) is None


def test_offline_error_transaction_and_projection(
    offline_db: ApplicationSession,
    offline_actor: Actor,
) -> None:
    correlation = uuid4()
    token = CURRENT_CORRELATION.set(correlation)
    source = uuid4()
    try:
        reference = record_system_error(
            offline_db,
            offline_actor,
            None,
            "GENERATION_FAILED",
            ProviderCallError("private-instance-code-and-prompt"),
            source_kind="GENERATION",
            source_id=source,
        )
    finally:
        CURRENT_CORRELATION.reset(token)
    assert offline_db.in_transaction()
    assert offline_db.error_reference(offline_actor.company_id, "GENERATION", source) == reference
    assert (
        record_system_error(
            offline_db,
            offline_actor,
            None,
            "GENERATION_FAILED",
            ValueError("private"),
            source_kind="GENERATION",
            source_id=source,
        )
        == reference
    )
    result = error_detail(offline_db, offline_actor, reference, technical=True)
    assert result["safe_code"] == "PROVIDER_OPERATION_FAILED"
    assert result["correlation_id"] == str(correlation)
    assert "private" not in json.dumps(result)
    assert result["technical"]["diagnostic"]["exception_type"] == "ProviderCallError"
    offline_db.rollback()
    assert offline_db.scalar(select(SystemErrorRow)) is None
    assert offline_db.scalar(select(SystemErrorDiagnosticRow)) is None


def test_offline_error_commit_survives_new_session(
    offline_db: ApplicationSession,
    offline_actor: Actor,
) -> None:
    reference = record_system_error(offline_db, offline_actor, None, "REQUEST_FAILED", ValueError())
    offline_db.commit()
    with ApplicationSession(offline_db.bind) as fresh:
        assert fresh.scalar(select(SystemErrorRow.id)) == reference
        assert fresh.scalar(select(SystemErrorDiagnosticRow.error_id)) == reference


def test_offline_error_tenant_cursor_and_keyset_boundaries(
    offline_db: ApplicationSession,
    offline_actor: Actor,
) -> None:
    time = datetime.now(UTC)
    ids = []
    retained_rows = []  # SQLite drops timezone on reload; PG timestamptz is separately tested.
    for index in range(5):
        ref = record_system_error(offline_db, offline_actor, None, "REQUEST_FAILED", ValueError())
        row = offline_db.get(SystemErrorRow, ref)
        assert row is not None
        row.occurred_at = time + timedelta(seconds=index)
        ids.append(str(ref))
        retained_rows.append(row)
    foreign = replace(offline_actor, company_id=uuid4())
    foreign_ref = record_system_error(offline_db, foreign, None, "REQUEST_FAILED", ValueError())
    offline_db.flush()
    filters = HistoryFilters(limit=2)
    first = list_errors(
        offline_db, offline_actor, filters, cursor_secret=offline_actor.identity_id.hex
    )
    assert [r["id"] for r in first["items"]] == ids[::-1][:2]
    second = list_errors(
        offline_db,
        offline_actor,
        replace(filters, cursor=first["next_cursor"]),
        cursor_secret=offline_actor.identity_id.hex,
    )
    third = list_errors(
        offline_db,
        offline_actor,
        replace(filters, cursor=second["next_cursor"]),
        cursor_secret=offline_actor.identity_id.hex,
    )
    assert [r["id"] for r in second["items"] + third["items"]] == ids[::-1][2:]
    assert third["next_cursor"] is None
    with pytest.raises(ProtectedResourceNotFound):
        error_detail(offline_db, offline_actor, foreign_ref)
    with pytest.raises(HistoryQueryInvalid):
        list_errors(
            offline_db,
            offline_actor,
            replace(filters, cursor=first["next_cursor"], operation="OTHER"),
            cursor_secret=offline_actor.identity_id.hex,
        )


def test_offline_permissions_and_case_scope(
    offline_db: ApplicationSession,
    offline_actor: Actor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    member = replace(offline_actor, role=Role.MEMBER)
    monkeypatch.setattr(offline_db, "active_actor", lambda *args: member)
    case_id = uuid4()
    reference = record_system_error(offline_db, member, case_id, "REQUEST_FAILED", ValueError())
    with pytest.raises(Forbidden):
        list_errors(
            offline_db, member, HistoryFilters(), cursor_secret=offline_actor.identity_id.hex
        )
    with pytest.raises(ProtectedResourceNotFound):
        error_detail(offline_db, member, reference, case_id)
    monkeypatch.setattr(offline_db, "case_access", lambda *args: (object(), object()))
    assert error_detail(offline_db, member, reference, case_id)["id"] == str(reference)
    with pytest.raises(Forbidden):
        error_detail(offline_db, member, reference, case_id, technical=True)
    with pytest.raises(ProtectedResourceNotFound):
        error_detail(offline_db, member, reference, uuid4())
    monkeypatch.setattr(offline_db, "active_actor", lambda *args: None)
    with pytest.raises(Forbidden):
        error_detail(offline_db, member, reference, case_id)


def test_offline_audit_filters_sparse_page_and_tenant_isolation(
    offline_db: ApplicationSession,
    offline_actor: Actor,
) -> None:
    ids = []
    for index in range(3):
        row = AuditEventRow(
            id=uuid4(),
            company_id=offline_actor.company_id,
            actor_membership_id=offline_actor.membership_id,
            event_type="GENERATION_STARTED",
            resource_type="GENERATION_ATTEMPT",
            resource_id=uuid4(),
            created_at=datetime.now(UTC) + timedelta(seconds=index),
            details_json=json.dumps({"digest": "b" * 64, "private": "secret"}),
        )
        offline_db.add(row)
        ids.append(row.id)
    foreign = AuditEventRow(
        id=uuid4(),
        company_id=uuid4(),
        actor_membership_id=uuid4(),
        event_type="CASE_CREATED",
        resource_type="REPORTING_CASE",
        resource_id=uuid4(),
        details_json="{}",
    )
    offline_db.add(foreign)
    offline_db.flush()
    first = list_audit(
        offline_db,
        offline_actor,
        HistoryFilters(module="Reports", outcome="FAILED", limit=1),
        cursor_secret=offline_actor.identity_id.hex,
    )
    assert first["items"] == [] and first["next_cursor"]
    items = list_audit(
        offline_db,
        offline_actor,
        HistoryFilters(module="Reports"),
        cursor_secret=offline_actor.identity_id.hex,
    )["items"]
    assert [r["id"] for r in items] == [str(i) for i in ids[::-1]]
    assert all(r["outcome"] == "UNSPECIFIED" for r in items)
    assert "private" not in json.dumps(items)
    with pytest.raises(ProtectedResourceNotFound):
        audit_detail(offline_db, offline_actor, foreign.id)


def test_offline_postgresql_schema_constraints_compile() -> None:
    error_ddl = str(CreateTable(SystemErrorRow.__table__).compile(dialect=postgresql.dialect()))
    diagnostic_ddl = str(
        CreateTable(SystemErrorDiagnosticRow.__table__).compile(dialect=postgresql.dialect())
    )
    assert "FOREIGN KEY(actor_membership_id, company_id)" in error_ddl
    assert "FOREIGN KEY(case_id, company_id)" in error_ddl
    assert "uq_system_error_source" in error_ddl
    assert "octet_length(technical_json) <= 4096" in diagnostic_ddl
    assert "FOREIGN KEY(error_id, company_id)" in diagnostic_ddl


def test_postgresql_error_history_is_durable_and_immutable(database: Database) -> None:
    from sqlalchemy.exc import DBAPIError

    from apbra_api.persistence import MembershipRow

    with database.session() as db:
        membership = db.scalar(select(MembershipRow).where(MembershipRow.active.is_(True)))
        assert membership is not None
        actor = db.active_actor(membership.id, membership.identity_id)
        assert actor is not None
        reference = db.record_system_error(actor, None, "REQUEST_FAILED", RuntimeError("private"))
        db.commit()
    with database.session() as db:
        assert db.get(SystemErrorRow, reference) is not None
        assert db.get(SystemErrorDiagnosticRow, reference) is not None
        from sqlalchemy import delete, update

        for model, column in (
            (SystemErrorRow, SystemErrorRow.id),
            (SystemErrorDiagnosticRow, SystemErrorDiagnosticRow.error_id),
        ):
            for verb in ("UPDATE", "DELETE"):
                with pytest.raises(DBAPIError, match="immutable"):
                    if verb == "UPDATE":
                        db.execute(
                            update(model)
                            .where(column == reference)
                            .values(company_id=model.company_id)
                        )
                    else:
                        db.execute(delete(model).where(column == reference))
                db.rollback()


def test_postgresql_error_company_bindings_and_bounds(database: Database) -> None:
    from sqlalchemy.exc import IntegrityError

    from apbra_api.persistence import MembershipRow

    with database.session() as db:
        members = list(db.scalars(select(MembershipRow)))
        first = members[0]
        other = next(member for member in members if member.company_id != first.company_id)
        actor = db.active_actor(first.id, first.identity_id)
        assert actor is not None
        reference = db.record_system_error(actor, None, "REQUEST_FAILED", RuntimeError("private"))
        db.commit()
        source = db.get(SystemErrorRow, reference)
        assert source is not None
        values = {
            column.name: getattr(source, column.name) for column in SystemErrorRow.__table__.columns
        }
        values.update(id=uuid4(), actor_membership_id=other.id)
        db.add(SystemErrorRow(**values))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
        db.add(
            SystemErrorDiagnosticRow(
                error_id=uuid4(), company_id=actor.company_id, technical_json="{}", truncated=False
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_offline_critical_error_write_failure_propagates(
    offline_db: ApplicationSession,
    offline_actor: Actor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flush = offline_db.flush
    calls = 0

    def fail_diagnostic_flush(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic write failure")
        flush(*args, **kwargs)

    monkeypatch.setattr(offline_db, "flush", fail_diagnostic_flush)
    with pytest.raises(RuntimeError, match="synthetic write failure"):
        record_system_error(offline_db, offline_actor, None, "REQUEST_FAILED", ValueError())
    offline_db.rollback()
    assert offline_db.scalar(select(SystemErrorRow)) is None
    assert offline_db.scalar(select(SystemErrorDiagnosticRow)) is None


def test_offline_report_failure_projection_uses_persisted_reference() -> None:
    from types import SimpleNamespace

    from apbra_api.generation import attempt_json, design_attempt_json

    reference = uuid4()
    calls = []

    class Store:
        def error_reference(self, company: UUID, kind: str, source: UUID) -> UUID:
            calls.append((company, kind, source))
            return reference

    store = Store()
    row = SimpleNamespace(
        id=uuid4(),
        company_id=uuid4(),
        case_id=uuid4(),
        confirmed_contract_id=uuid4(),
        reviewed_design_id=None,
        interpretation_id=uuid4(),
        request_version_id=uuid4(),
        status="FAILED",
        attempt_number=1,
        retry_of_attempt_id=None,
        supersedes_attempt_id=None,
        artifact_id=None,
        provenance_json="{}",
        validation_json=None,
        failure_code="GENERATION_FAILED",
        failure_reason="Safe failure",
        created_at=datetime.now(UTC),
        started_at=None,
        completed_at=None,
        cancelled_at=None,
    )
    assert attempt_json(store, row)["failure"]["support_reference"] == str(reference)
    assert calls[-1] == (row.company_id, "GENERATION", row.id)
    design = SimpleNamespace(
        id=uuid4(),
        company_id=row.company_id,
        confirmed_contract_id=row.confirmed_contract_id,
        usage_json="{}",
        safe_failure_code="MODEL_INPUT_BUDGET_EXCEEDED",
        status="FAILED",
        provider_profile_id="synthetic",
        model_or_deployment="synthetic",
        prompt_version="v1",
        configuration_id="synthetic",
        capability_profile_json="{}",
        validation_json=None,
        created_at=datetime.now(UTC),
        completed_at=None,
    )
    assert design_attempt_json(design, store)["failure"]["support_reference"] == str(reference)
    assert calls[-1] == (row.company_id, "AUTOMATIC_DESIGN", design.id)
    assert design_attempt_json(design)["failure"]["support_reference"] is None


def test_offline_migration_upgrade_sql_has_all_guards() -> None:
    import importlib.util
    from io import StringIO
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[1] / "alembic/versions/20261015_11_audit_errors.py"
    spec = importlib.util.spec_from_file_location("audit_error_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(context):
        migration.upgrade()
    sql = output.getvalue()
    assert "CREATE TABLE system_errors" in sql
    assert "CREATE TABLE system_error_diagnostics" in sql
    assert "CREATE INDEX ix_audit_company_time" in sql
    assert sql.count("BEFORE UPDATE OR DELETE") == 2
    assert "FOREIGN KEY(case_id, company_id)" in sql
    assert "octet_length(technical_json) <= 4096" in sql
    assert "source_kind IS NOT NULL" in sql


def test_postgresql_history_api_admin_tenant_and_selection_boundaries(
    client: Any,
    database: Database,
) -> None:
    from conftest import sign_in

    owner = sign_in(client, "owner")
    headers = {"X-Expected-Membership-Id": owner["actor"]["membership_id"]}
    with database.session() as db:
        actor = db.active_actor(
            UUID(owner["actor"]["membership_id"]), UUID(owner["actor"]["identity_id"])
        )
        assert actor is not None
        reference = db.record_system_error(
            actor, None, "REQUEST_FAILED", ProviderCallError("synthetic-private-token")
        )
        db.commit()
    assert client.get("/api/tenant-settings/errors").status_code == 409
    response = client.get("/api/tenant-settings/errors", headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert any(item["support_reference"] == str(reference) for item in response.json()["items"])
    detail = client.get(f"/api/tenant-settings/errors/{reference}", headers=headers)
    assert detail.status_code == 200 and detail.json()["technical"]
    assert "synthetic-private-token" not in detail.text
    audit = client.get("/api/tenant-settings/audit-events", headers=headers)
    assert audit.status_code == 200
    assert any(item["operation"] == "ERROR_HISTORY_VIEWED" for item in audit.json()["items"])
    for query in (
        "limit=101",
        "from=2026-01-01",
        "module=wrong",
        "actor_id=wrong",
        "limit=1&limit=2",
        "extra=private",
        "from=0001-01-01T00:00:00%2B14:00",
        "to=9999-12-31T23:59:59-12:00",
    ):
        assert (
            client.get("/api/tenant-settings/errors?" + query, headers=headers).status_code == 422
        )
    foreign = sign_in(client, "foreign")
    foreign_headers = {"X-Expected-Membership-Id": foreign["actor"]["membership_id"]}
    assert (
        client.get(f"/api/tenant-settings/errors/{reference}", headers=foreign_headers).status_code
        == 404
    )
    member = sign_in(client, "member")
    member_headers = {"X-Expected-Membership-Id": member["actor"]["membership_id"]}
    for path in ("errors", f"errors/{reference}", "audit-events"):
        assert client.get("/api/tenant-settings/" + path, headers=member_headers).status_code == 403


def test_postgresql_report_error_api_respects_current_private_grants(
    client: Any,
    database: Database,
) -> None:
    from conftest import sign_in
    from test_cases import create_case

    from apbra_api.persistence import CaseAccessRow

    member = sign_in(client, "member")
    case = create_case(client, "Synthetic safe operational-history report")
    case_id = UUID(case["id"])
    with database.session() as db:
        actor = db.active_actor(
            UUID(member["actor"]["membership_id"]), UUID(member["actor"]["identity_id"])
        )
        assert actor is not None
        reference = db.record_system_error(
            actor,
            case_id,
            "GENERATION_FAILED",
            RuntimeError("private-prompt"),
            source_kind="GENERATION",
            source_id=uuid4(),
        )
        db.commit()
    response = client.get(f"/api/cases/{case_id}/errors")
    assert response.status_code == 200
    assert any(item["id"] == str(reference) for item in response.json()["items"])
    detail = client.get(f"/api/cases/{case_id}/errors/{reference}")
    assert detail.status_code == 200
    assert "technical" not in detail.json()
    assert "private-prompt" not in detail.text
    assert client.get(f"/api/cases/{uuid4()}/errors/{reference}").status_code == 404
    with database.session() as db:
        grant = db.scalar(
            select(CaseAccessRow).where(
                CaseAccessRow.case_id == case_id,
                CaseAccessRow.membership_id == UUID(member["actor"]["membership_id"]),
            )
        )
        assert grant is not None
        grant.active = False
        db.commit()
    assert client.get(f"/api/cases/{case_id}/errors/{reference}").status_code == 404
    sign_in(client, "owner")
    assert client.get(f"/api/cases/{case_id}/errors").status_code == 404


def test_postgresql_history_api_rechecks_membership_and_cursor_scope(
    client: Any,
    database: Database,
) -> None:
    from conftest import sign_in

    from apbra_api.persistence import MembershipRow

    owner = sign_in(client, "owner")
    membership_id = UUID(owner["actor"]["membership_id"])
    headers = {"X-Expected-Membership-Id": str(membership_id)}
    with database.session() as db:
        actor = db.active_actor(membership_id, UUID(owner["actor"]["identity_id"]))
        assert actor is not None
        for _ in range(3):
            db.record_system_error(actor, None, "REQUEST_FAILED", RuntimeError("synthetic"))
        db.commit()
    response = client.get("/api/tenant-settings/errors?limit=1", headers=headers)
    assert response.status_code == 200
    cursor = response.json()["next_cursor"]
    assert cursor is not None
    rejected = client.get(
        "/api/tenant-settings/errors",
        headers=headers,
        params={"limit": 1, "cursor": cursor, "module": "API"},
    )
    assert rejected.status_code == 422
    with database.session() as db:
        membership = db.get(MembershipRow, membership_id)
        assert membership is not None
        membership.role = "MEMBER"
        db.commit()
    assert client.get("/api/tenant-settings/errors", headers=headers).status_code == 403
    with database.session() as db:
        membership = db.get(MembershipRow, membership_id)
        assert membership is not None
        membership.active = False
        db.commit()
    assert client.get("/api/tenant-settings/errors", headers=headers).status_code in {401, 403}


def test_postgresql_validation_failure_has_safe_durable_support_reference(
    client: Any, database: Database,
) -> None:
    from conftest import sign_in

    owner = sign_in(client, "owner")
    response = client.get(
        "/api/tenant-settings/errors?limit=private-rejected-input",
        headers={"X-Expected-Membership-Id": owner["actor"]["membership_id"]},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["recorded"] is True
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-apbra-request-id"] == error["correlation_id"]
    assert "private-rejected-input" not in response.text
    with database.session() as db:
        row = db.get(SystemErrorRow, UUID(error["support_reference"]))
        assert row is not None
        assert row.company_id == UUID(owner["actor"]["company_id"])
        assert row.category == "VALIDATION" and row.outcome == "REJECTED"
        assert row.operation == "TENANT_ERRORS"
        diagnostic = db.get(SystemErrorDiagnosticRow, row.id)
        assert diagnostic is not None
        assert "private-rejected-input" not in diagnostic.technical_json


def test_postgresql_recording_failure_does_not_claim_durable_history(
    client: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conftest import sign_in

    import apbra_api.api as api_module

    owner = sign_in(client, "owner")

    def unavailable(*args: Any, **kwargs: Any) -> UUID:
        raise RuntimeError("synthetic-private-connection-string")

    monkeypatch.setattr(api_module, "record_system_error", unavailable)
    response = client.get(
        "/api/tenant-settings/errors?limit=invalid",
        headers={"X-Expected-Membership-Id": owner["actor"]["membership_id"]},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["recorded"] is False
    assert UUID(error["support_reference"])
    assert "synthetic-private-connection-string" not in response.text

def test_offline_native_output_operations_use_exact_reports_mapping_before_limit(
    offline_db: ApplicationSession, offline_actor: Actor,
) -> None:
    operations = ["NATIVE_ANALYSIS_INTAKE", "REQUEST_OUTPUT_SAVED",
                  "NATIVE_ANALYSIS_INTAKE_PRIVATE", "REQUEST_OUTPUT_PRIVATE"]
    for index, operation in enumerate(operations):
        offline_db.add(AuditEventRow(
            id=uuid4(), company_id=offline_actor.company_id,
            actor_membership_id=offline_actor.membership_id, event_type=operation,
            resource_type="REQUEST_OUTPUT", resource_id=uuid4(),
            created_at=datetime.now(UTC) + timedelta(seconds=index),
            details_json=json.dumps({"sha256": "a" * 64, "byte_size": 42,
                                     "outcome": "SUCCEEDED", "filename": "PRIVATE-CANARY"}),
        ))
    offline_db.flush()
    result = list_audit(offline_db, offline_actor,
                        HistoryFilters(module="Reports", limit=1),
                        cursor_secret=offline_actor.identity_id.hex)
    item = result["items"][0]
    assert item["operation"] == "REQUEST_OUTPUT_SAVED"
    assert item["module"] == "Reports" and item["outcome"] == "SUCCEEDED"
    assert item["details"] == {"sha256": "a" * 64, "byte_size": 42, "outcome": "SUCCEEDED"}
    assert result["next_cursor"]
    second = list_audit(offline_db, offline_actor,
                        HistoryFilters(module="Reports", limit=1, cursor=result["next_cursor"]),
                        cursor_secret=offline_actor.identity_id.hex)
    assert [row["operation"] for row in second["items"]] == ["NATIVE_ANALYSIS_INTAKE"]
    other = list_audit(offline_db, offline_actor, HistoryFilters(module="Other"),
                       cursor_secret=offline_actor.identity_id.hex)
    assert {row["operation"] for row in other["items"]} == set(operations[2:])
    assert "PRIVATE-CANARY" not in json.dumps([result, second, other])


def test_output_storage_audit_appears_in_protected_reports_history(client: Any) -> None:
    from conftest import csrf, sign_in

    session = sign_in(client)
    created = client.post("/api/cases", json={"request_text": "Synthetic opaque history"},
                          headers={**csrf(session), "Idempotency-Key": str(uuid4())})
    assert created.status_code == 201
    case = created.json()["case"]
    saved = client.post(f"/api/cases/{case['id']}/outputs", content=b"Opaque original content",
                        params={"filename": "PRIVATE-FILENAME-CANARY.zip",
                                "expected_context_version": 1, "command_key": str(uuid4())},
                        headers={**csrf(session), "Content-Type": "application/octet-stream"})
    assert saved.status_code == 200
    output = saved.json()["output"]
    assert output["content_verification"] == "NOT_RUN"
    history = client.get("/api/tenant-settings/audit-events",
                         params={"module": "Reports", "operation": "REQUEST_OUTPUT_SAVED"},
                         headers={"X-Expected-Membership-Id": session["actor"]["membership_id"]})
    assert history.status_code == 200
    row = history.json()["items"][0]
    assert row["target_id"] == output["id"] and row["outcome"] == "SUCCEEDED"
    assert row["details"] == {"sha256": output["sha256"], "byte_size": output["bytes"],
                              "outcome": "SUCCEEDED"}
    assert "PRIVATE-FILENAME-CANARY" not in history.text
