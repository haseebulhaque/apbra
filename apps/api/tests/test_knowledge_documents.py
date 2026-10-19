"""Synthetic local originals, authorization, replay and transaction invariants."""

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from apbra_api.api import create_app
from apbra_api.config import Settings
from apbra_api.knowledge_documents import KnowledgeDocumentsError, canonical_uuid, parse_payload
from apbra_api.persistence import (
    ApplicationSession,
    CompanyRow,
    Database,
    ExternalIdentityRow,
    KnowledgeCommandRow,
    KnowledgeDocumentRow,
    KnowledgeRevisionRow,
    MembershipRow,
    SessionRow,
)

BASE = "/api/tenant-settings/knowledge-documents"


def headers(
    client: TestClient, session: dict[str, object], key: str | None = None
) -> dict[str, str]:
    caps = client.get(BASE + "/capabilities")
    assert caps.status_code == 200, caps.text
    return {
        **csrf(session),
        "X-Expected-Membership-Id": caps.json()["membership_id"],
        "Idempotency-Key": key or str(uuid4()),
    }


def draft(
    title: str = "Original", version: str = "version opaque", body: str = "User text"
) -> dict[str, str]:
    return {"title": title, "source_version": version, "text": body}


def created(client: TestClient, h: dict[str, str], payload: dict[str, str] | None = None) -> dict:
    result = client.post(BASE, json=payload or draft(), headers=h)
    assert result.status_code == 201, result.text
    return result.json()


def counts(database: Database) -> tuple[int, int, int]:
    with database.session() as db:
        return (
            db.scalar(select(func.count()).select_from(KnowledgeDocumentRow)),
            db.scalar(select(func.count()).select_from(KnowledgeRevisionRow)),
            db.scalar(select(func.count()).select_from(KnowledgeCommandRow)),
        )


@pytest.mark.parametrize(
    "raw",
    [
        b'{"title":"x","title":"y","source_version":"v","text":"t"}',
        b'{"title":"x","source_version":"v","text":"t","company_id":"x"}',
        b'{"title":1,"source_version":"v","text":"t"}',
        b'{"title":"x","source_version":"v","text":NaN}',
        b'{"title":"x","source_version":"v","text":"\\ud800"}',
        b"\xff",
        b"[]",
        b"{}",
        b"null",
    ],
)
def test_parser_strict_safe_plaintext_shape(raw: bytes) -> None:
    with pytest.raises(KnowledgeDocumentsError) as error:
        parse_payload(raw, "CREATE")
    assert error.value.code == "REQUEST_VALIDATION_FAILED"
    assert str(error.value) == "REQUEST_VALIDATION_FAILED"


@pytest.mark.parametrize(
    "value", ["", "\\x00", "\ufefffirst\r\nsecond", "<script>CANARY</script>", "opaque v😀"]
)
def test_parser_preserves_exact_strings(value: str) -> None:
    payload = parse_payload(json.dumps(draft(value, value, value)).encode(), "CREATE")
    assert (payload.title, payload.source_version, payload.text) == (value, value, value)


@pytest.mark.parametrize(
    "value", [None, 1, "not-uuid", "00000000000000000000000000000000", str(uuid4()).upper()]
)
def test_uuid_header_is_canonical_no_coercion(value: object) -> None:
    with pytest.raises(KnowledgeDocumentsError):
        canonical_uuid(value)


@pytest.mark.parametrize("original", ["", "\x00\ufeff\r\n😀", "<script>never execute</script>"])
def test_immutable_original_revision_archive_restart_and_latest_replay(
    client: TestClient,
    database: Database,
    settings: Settings,
    original: str,
) -> None:
    session = sign_in(client)
    h = headers(client, session)
    before = client.get("/api/tenant-settings").json()
    first = created(client, h, draft(original, original, original))
    doc = first["document"]["document_id"]
    revision = first["command"]["target_revision_id"]
    original_url = f"{BASE}/{doc}/revisions/{revision}/original"
    result = client.get(original_url, headers=h)
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert [result.json()[k] for k in ("title", "source_version", "text")] == [original] * 3
    assert result.json()["text_sha256"] == hashlib.sha256(original.encode()).hexdigest()
    assert result.json()["text_byte_count"] == len(original.encode())
    with database.session() as db:
        row = db.get(KnowledgeRevisionRow, UUID(revision))
        assert row is not None
        assert (row.title_original, row.source_version_original, row.text_original) == (
            original.encode(),
        ) * 3
    second = client.post(
        f"{BASE}/{doc}/revisions",
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={
            **draft("Second", "earlier-looking-version", "second"),
            "expected_current_revision_id": revision,
        },
    )
    assert second.status_code == 201, second.text
    newer = second.json()["command"]["target_revision_id"]
    # Lost acknowledgement: exact old CREATE replay retains IDs, returns NEW current context.
    replay = client.post(BASE, headers=h, json=draft(original, original, original))
    assert replay.status_code == 200
    assert replay.json()["command"] == first["command"]
    assert replay.json()["document"]["current_revision_id"] == newer
    restarted = TestClient(create_app(settings=settings, database=Database(settings.database_url)))
    restarted.cookies.update(client.cookies)
    reconcile = restarted.get(BASE + "/commands/" + h["Idempotency-Key"], headers=h)
    assert reconcile.status_code == 200 and reconcile.json()["reconciliation"] == "COMMITTED"
    assert reconcile.json()["command"] == first["command"]
    assert reconcile.json()["document"]["current_revision_id"] == newer
    archived = restarted.post(
        f"{BASE}/{doc}/archive",
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={"expected_current_revision_id": newer},
    )
    assert archived.status_code == 201, archived.text
    assert archived.json()["document"]["local_state"] == "LOCAL_ARCHIVAL_REQUESTED"
    history = restarted.get(f"{BASE}/{doc}/history", headers=h).json()
    assert len(history["revisions"]) == 2 and len(history["operations"]) == 3
    assert counts(database) == (1, 2, 3)
    assert restarted.get(original_url, headers=h).json()["text"] == original
    assert all(o["provider_write_outcome"] == "NOT_SENT" for o in history["operations"])
    assert client.get("/api/tenant-settings").json() == before


def test_stale_revision_and_full_intent_key_conflicts(
    client: TestClient, database: Database
) -> None:
    session = sign_in(client)
    h = headers(client, session)
    first = created(client, h)
    doc = first["document"]["document_id"]
    revision = first["command"]["target_revision_id"]
    for change in (draft("different"), draft(version="different"), draft(body="different")):
        r = client.post(BASE, headers=h, json=change)
        assert r.status_code == 409 and r.json()["error"]["code"] == "KNOWLEDGE_COMMAND_CONFLICT"
    for suffix, payload in (
        ("/archive", {"expected_current_revision_id": revision}),
        ("/revisions", {**draft(), "expected_current_revision_id": revision}),
    ):
        assert client.post(BASE + "/" + doc + suffix, json=payload, headers=h).status_code == 409
    change = {**draft(), "expected_current_revision_id": revision}
    assert (
        client.post(
            f"{BASE}/{doc}/revisions", json=change, headers={**h, "Idempotency-Key": str(uuid4())}
        ).status_code
        == 201
    )
    stale = client.post(
        f"{BASE}/{doc}/revisions", json=change, headers={**h, "Idempotency-Key": str(uuid4())}
    )
    assert (
        stale.status_code == 409 and stale.json()["error"]["code"] == "KNOWLEDGE_REVISION_CONFLICT"
    )
    assert counts(database) == (1, 2, 2)


@pytest.mark.parametrize("role", ["MEMBER", "EXPERT", "COMPANY_ADMIN"])
def test_fresh_admin_role_gates_every_operation(
    client: TestClient, database: Database, role: str
) -> None:
    owner = sign_in(client)
    h = headers(client, owner)
    first = created(client, h)
    doc = first["document"]["document_id"]
    rev = first["command"]["target_revision_id"]
    member = sign_in(client, "member")
    with database.session() as db:
        row = db.get(MembershipRow, UUID(member["actor"]["membership_id"]))
        row.role = role
    hm = {
        **csrf(member),
        "X-Expected-Membership-Id": member["actor"]["membership_id"],
        "Idempotency-Key": str(uuid4()),
    }
    expected = 200 if role == "COMPANY_ADMIN" else 403
    for path in (
        "/capabilities",
        "",
        "/" + doc,
        f"/{doc}/history",
        f"/{doc}/revisions/{rev}/original",
    ):
        assert client.get(BASE + path, headers=hm).status_code == expected
    # Another identity's command is not accessible, even to a current administrator.
    command = client.get(BASE + "/commands/" + h["Idempotency-Key"], headers=hm)
    assert command.status_code == (404 if role == "COMPANY_ADMIN" else 403)
    assert client.post(BASE, json=draft(), headers=hm).status_code == (
        201 if role == "COMPANY_ADMIN" else 403
    )


@pytest.mark.parametrize("inactive", ["session", "expiry", "membership", "identity", "company"])
def test_reads_and_replays_recheck_revocation(
    client: TestClient, database: Database, inactive: str
) -> None:
    session = sign_in(client)
    h = headers(client, session)
    first = created(client, h)
    with database.session() as db:
        member = db.get(MembershipRow, UUID(session["actor"]["membership_id"]))
        if inactive == "membership":
            member.active = False
        elif inactive == "identity":
            db.get(ExternalIdentityRow, member.identity_id).active = False
        elif inactive == "company":
            db.get(CompanyRow, member.company_id).active = False
        else:
            row = db.scalar(select(SessionRow).where(SessionRow.identity_id == member.identity_id))
            if inactive == "session":
                row.revoked_at = datetime.now(UTC)
            else:
                row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    for path in (
        "/capabilities",
        "",
        "/" + first["document"]["document_id"],
        "/commands/" + h["Idempotency-Key"],
    ):
        assert client.get(BASE + path, headers=h).status_code == 401
    assert client.post(BASE, headers=h, json=draft()).status_code == 401
    assert counts(database) == (1, 1, 1)


@pytest.mark.parametrize("echo", [None, "bad", str(uuid4())])
def test_expected_membership_never_selects_authority(
    client: TestClient, database: Database, echo: str | None
) -> None:
    session = sign_in(client)
    h = headers(client, session)
    if echo is None:
        h.pop("X-Expected-Membership-Id")
    else:
        h["X-Expected-Membership-Id"] = echo
    expected = 409 if echo and echo != "bad" else 422
    assert client.get(BASE, headers=h).status_code == expected
    assert (
        client.post(BASE, headers=h, content=b"untrusted-canary-malformed").status_code == expected
    )
    assert counts(database) == (0, 0, 0)


def other_membership(database: Database, session: dict) -> str:
    with database.session() as db:
        identity = db.get(MembershipRow, UUID(session["actor"]["membership_id"])).identity_id
        company = CompanyRow(id=uuid4(), name="Other synthetic company")
        db.add(company)
        db.flush()
        member = MembershipRow(
            id=uuid4(),
            company_id=company.id,
            identity_id=identity,
            role="COMPANY_OWNER",
            active=True,
        )
        db.add(member)
        return str(member.id)


def test_company_switch_before_request_rejects_old_create_without_reading_body(
    client: TestClient, database: Database
) -> None:
    session = sign_in(client)
    h = headers(client, session)
    membership = other_membership(database, session)
    assert (
        client.post(
            "/api/auth/select-company", json={"membership_id": membership}, headers=csrf(session)
        ).status_code
        == 200
    )
    r = client.post(BASE, headers=h, content=b"PRIVATE_INVALID_BODY")
    assert r.status_code == 409 and r.json()["error"]["code"] == "KNOWLEDGE_CONTEXT_CHANGED"
    assert counts(database) == (0, 0, 0)


@pytest.mark.parametrize("change", ["switch", "expiry", "revoke"])
def test_locked_wait_rechecks_session_without_unlocked_company_write(
    client: TestClient,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    session = sign_in(client)
    h = headers(client, session)
    member_id = other_membership(database, session)
    reached = threading.Event()
    original = ApplicationSession.lock_company_for_membership_management

    def observed(db, company):
        reached.set()
        return original(db, company)

    monkeypatch.setattr(ApplicationSession, "lock_company_for_membership_management", observed)
    with database.engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            text("SELECT id FROM companies WHERE id=:id FOR UPDATE"),
            {"id": session["actor"]["company_id"]},
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.post, BASE, headers=h, json=draft())
            assert reached.wait(5)
            with database.session() as db:
                row = db.scalar(
                    select(SessionRow).where(
                        SessionRow.identity_id == UUID(session["actor"]["identity_id"])
                    )
                )
                if change == "switch":
                    row.membership_id = UUID(member_id)
                elif change == "expiry":
                    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                else:
                    row.revoked_at = datetime.now(UTC)
            transaction.commit()
            response = pending.result(timeout=10)
    assert response.status_code == (409 if change == "switch" else 401), response.text
    assert counts(database) == (0, 0, 0)


def test_same_key_two_instance_race_and_recovery(
    client: TestClient, database: Database, settings: Settings
) -> None:
    session = sign_in(client)
    h = headers(client, session)
    second_db = Database(settings.database_url)
    second = TestClient(create_app(settings=settings, database=second_db))
    second.cookies.update(client.cookies)
    barrier = threading.Barrier(2)

    def send(c):
        barrier.wait(timeout=5)
        return c.post(BASE, headers=h, json=draft())

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(send, client)
            b = pool.submit(send, second)
            results = [a.result(10), b.result(10)]
        assert sorted(r.status_code for r in results) == [200, 201]
        assert results[0].json()["command"] == results[1].json()["command"]
        assert counts(database) == (1, 1, 1)
    finally:
        second_db.engine.dispose()


@pytest.mark.parametrize("table", ["tenant_knowledge_revisions", "tenant_knowledge_commands"])
@pytest.mark.parametrize("mutation", ["UPDATE", "DELETE"])
def test_database_rejects_history_mutation(
    client: TestClient, database: Database, table: str, mutation: str
) -> None:
    session = sign_in(client)
    created(client, headers(client, session))
    with pytest.raises(DBAPIError, match="knowledge originals and commands are immutable"):
        with database.session() as db:
            sql = {
                (
                    "tenant_knowledge_revisions",
                    "UPDATE",
                ): "UPDATE tenant_knowledge_revisions SET id=id",
                ("tenant_knowledge_revisions", "DELETE"): "DELETE FROM tenant_knowledge_revisions",
                (
                    "tenant_knowledge_commands",
                    "UPDATE",
                ): "UPDATE tenant_knowledge_commands SET id=id",
                ("tenant_knowledge_commands", "DELETE"): "DELETE FROM tenant_knowledge_commands",
            }[(table, mutation)]
            db.execute(text(sql))
    assert counts(database) == (1, 1, 1)


def test_compound_scope_and_actor_guards_reject_insert(
    client: TestClient, database: Database
) -> None:
    session = sign_in(client)
    first = created(client, headers(client, session))
    other = other_membership(database, session)
    with database.session() as db:
        member = db.get(MembershipRow, UUID(other))
        other_company = member.company_id
        alien_identity = db.scalar(
            select(ExternalIdentityRow.id).where(ExternalIdentityRow.id != member.identity_id)
        )
    for altered in ("document", "company", "identity"):
        with pytest.raises(DBAPIError):
            with database.session() as db:
                source = db.get(KnowledgeRevisionRow, UUID(first["command"]["target_revision_id"]))
                db.add(
                    KnowledgeRevisionRow(
                        id=uuid4(),
                        document_id=uuid4() if altered == "document" else source.document_id,
                        company_id=other_company if altered == "company" else source.company_id,
                        predecessor_revision_id=source.id,
                        creator_membership_id=source.creator_membership_id,
                        creator_identity_id=alien_identity
                        if altered == "identity"
                        else source.creator_identity_id,
                        title_original=b"x",
                        source_version_original=b"v",
                        text_original=b"x",
                        text_sha256=hashlib.sha256(b"x").hexdigest(),
                        text_byte_count=1,
                        created_at=datetime.now(UTC),
                    )
                )
    assert counts(database) == (1, 1, 1)


def test_oversize_actual_stream_without_length_trust_and_safe_errors(
    client: TestClient, database: Database, caplog: pytest.LogCaptureFixture
) -> None:
    session = sign_in(client)
    h = headers(client, session)
    policy = client.get("/api/tenant-settings").json()
    policy["settings"]["upload_policy"]["max_file_bytes"] = 100
    updated = client.put(
        "/api/tenant-settings",
        json={"expected_version": policy["version"], "settings": policy["settings"]},
        headers=csrf(session),
    )
    assert updated.status_code == 200, updated.text
    assert client.get(BASE + "/capabilities").json()["maximum_request_bytes"] == 100
    sentinel = "PRIVATE_DOCUMENT_CANARY"
    raw = json.dumps(draft(body=sentinel * 30)).encode()
    response = client.post(
        BASE,
        headers={**h, "Content-Type": "application/json", "Content-Length": "1"},
        content=iter([raw[:80], raw[80:]]),
    )
    assert response.status_code == 413
    assert sentinel not in response.text and sentinel not in caplog.text
    assert counts(database) == (0, 0, 0)


def test_csrf_and_auth_precede_private_body_validation(
    client: TestClient, database: Database
) -> None:
    response = client.post(BASE, content=b"PRIVATE_BODY")
    assert response.status_code == 401 and response.json()["error"]["code"] == "CSRF_INVALID"
    session = sign_in(client)
    h = headers(client, session)
    for content in (
        b'{"title":"x","text":"x","source_version":"v","role":"COMPANY_OWNER"}',
        b"\xff",
    ):
        result = client.post(
            BASE, content=content, headers={**h, "Content-Type": "application/json"}
        )
        assert result.status_code == 422
        assert counts(database) == (0, 0, 0)
    assert client.get(BASE + "?company_id=" + str(uuid4()), headers=h).status_code == 422


def test_foreign_resources_cannot_be_read_or_mutated(
    client: TestClient, database: Database
) -> None:
    owner = sign_in(client)
    h = headers(client, owner)
    first = created(client, h)
    doc = first["document"]["document_id"]
    rev = first["command"]["target_revision_id"]
    foreign = sign_in(client, "foreign")
    hf = headers(client, foreign)
    for path in (f"/{doc}", f"/{doc}/history", f"/{doc}/revisions/{rev}/original"):
        assert client.get(BASE + path, headers=hf).status_code == 404
    assert client.get(BASE, headers=hf).json()["items"] == []
    assert (
        client.post(
            f"{BASE}/{doc}/archive", headers=hf, json={"expected_current_revision_id": rev}
        ).status_code
        == 404
    )
    assert counts(database) == (1, 1, 1)


@pytest.mark.parametrize("committed", [False, True])
def test_commit_uncertainty_no_orphans_and_same_key_reconciliation(
    client: TestClient,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    committed: bool,
) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    session = sign_in(client)
    h = headers(client, session)
    original = ApplicationSession.commit
    emitted = False

    def uncertain(db):
        nonlocal emitted
        has_command = db.scalar(select(KnowledgeCommandRow.id)) is not None
        if has_command and not emitted:
            emitted = True
            if committed:
                original(db)
            raise SQLAlchemyError("PRIVATE_SQL_INPUT_CANARY")
        return original(db)

    monkeypatch.setattr(ApplicationSession, "commit", uncertain)
    result = client.post(BASE, headers=h, json=draft())
    assert (
        result.status_code == 503
        and result.json()["error"]["code"] == "KNOWLEDGE_DOCUMENTS_UNAVAILABLE"
    )
    assert "PRIVATE_SQL_INPUT_CANARY" not in result.text + caplog.text
    reconciliation = client.get(BASE + "/commands/" + h["Idempotency-Key"], headers=h)
    assert reconciliation.status_code == 200
    assert reconciliation.json()["reconciliation"] == ("COMMITTED" if committed else "NOT_OBSERVED")
    assert counts(database) == ((1, 1, 1) if committed else (0, 0, 0))
    retry = client.post(BASE, headers=h, json=draft())
    assert retry.status_code == (200 if committed else 201)
    assert counts(database) == (1, 1, 1)
    if committed:
        assert retry.json()["command"] == reconciliation.json()["command"]


def test_distinct_revision_race_cas_and_complete_same_time_journal(
    client: TestClient,
    database: Database,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import apbra_api.knowledge_documents as documents

    session = sign_in(client)
    h = headers(client, session)
    first = created(client, h)
    doc = first["document"]["document_id"]
    rev = first["command"]["target_revision_id"]
    fixed = datetime.now(UTC)

    class SameTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(documents, "datetime", SameTime)
    second_db = Database(settings.database_url)
    second = TestClient(create_app(settings=settings, database=second_db))
    second.cookies.update(client.cookies)
    barrier = threading.Barrier(2)

    def save(c, title):
        barrier.wait(5)
        return c.post(
            f"{BASE}/{doc}/revisions",
            headers={**h, "Idempotency-Key": str(uuid4())},
            json={**draft(title), "expected_current_revision_id": rev},
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(save, client, "A")
            b = pool.submit(save, second, "B")
            results = [a.result(10), b.result(10)]
        assert sorted(r.status_code for r in results) == [201, 409]
        winner = next(r for r in results if r.status_code == 201).json()
        again = client.post(
            f"{BASE}/{doc}/revisions",
            headers={**h, "Idempotency-Key": str(uuid4())},
            json={
                **draft("Next"),
                "expected_current_revision_id": winner["command"]["target_revision_id"],
            },
        )
        assert again.status_code == 201
        # Exact old replay validates reconstructed history even with equal actual UTC timestamps.
        replay = client.post(BASE, headers=h, json=draft())
        assert replay.status_code == 200 and replay.json()["command"] == first["command"]
        assert (
            replay.json()["document"]["current_revision_id"]
            == again.json()["command"]["target_revision_id"]
        )
        with database.session() as db:
            commands = list(
                db.scalars(select(KnowledgeCommandRow).order_by(KnowledgeCommandRow.sequence))
            )
            assert [c.sequence for c in commands] == [1, 2, 3]
            assert commands[1].created_at == commands[2].created_at
    finally:
        second_db.engine.dispose()


def test_authorization_and_current_byte_limit_rechecked_after_stream(
    client: TestClient,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import apbra_api.api as api_module

    session = sign_in(client)
    h = headers(client, session)
    original = api_module.authorize_documents
    observed = 0

    def changed_after_preflight(db, token, expected, **kwargs):
        nonlocal observed
        observed += 1
        if kwargs.get("initial") is not None:
            # A revocation wins between bounded-body preflight and write transaction.
            with database.session() as other:
                row = other.get(MembershipRow, UUID(h["X-Expected-Membership-Id"]))
                row.active = False
        return original(db, token, expected, **kwargs)

    monkeypatch.setattr(api_module, "authorize_documents", changed_after_preflight)
    result = client.post(BASE, headers=h, json=draft())
    assert result.status_code == 401 and observed == 2
    assert counts(database) == (0, 0, 0)


def test_poststream_current_limit_cannot_use_preflight_stale_settings(
    client: TestClient,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import apbra_api.api as api_module

    session = sign_in(client)
    h = headers(client, session)
    original = api_module.authorize_documents
    changed = False
    policy = client.get("/api/tenant-settings").json()

    def changed_after_preflight(db, token, expected, **kwargs):
        nonlocal changed
        if kwargs.get("initial") is not None and not changed:
            changed = True
            policy["settings"]["upload_policy"]["max_file_bytes"] = 1
            r = client.put(
                "/api/tenant-settings",
                headers=csrf(session),
                json={"expected_version": policy["version"], "settings": policy["settings"]},
            )
            assert r.status_code == 200
        return original(db, token, expected, **kwargs)

    monkeypatch.setattr(api_module, "authorize_documents", changed_after_preflight)
    result = client.post(BASE, headers=h, json=draft())
    assert result.status_code == 413
    assert counts(database) == (0, 0, 0)


def test_local_documents_never_construct_provider_or_enter_report_context(
    client: TestClient,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import apbra_api.api as api_module

    def forbidden(*args, **kwargs):
        raise AssertionError("PROVIDER_CONSTRUCTION_FORBIDDEN")

    for name in (
        "OpenAICompatibleProvider",
        "FoundryAgentResponsesProvider",
        "SemanticBridge",
        "GenerationBridge",
    ):
        monkeypatch.setattr(api_module, name, forbidden)
    session = sign_in(client)
    h = headers(client, session)
    first = created(client, h)
    assert client.get(BASE, headers=h).json()["items"][0]["used_by_ai"] is False
    assert (
        client.get(f"{BASE}/{first['document']['document_id']}/history", headers=h).status_code
        == 200
    )
    with database.session() as db:
        for query in (
            text("SELECT count(*) FROM automatic_design_attempts"),
            text("SELECT count(*) FROM case_interpretation_versions"),
            text("SELECT count(*) FROM generation_attempts"),
        ):
            assert db.scalar(query) == 0


def test_second_admin_cannot_reuse_first_initiator_create_key(
    client: TestClient, database: Database
) -> None:
    owner = sign_in(client)
    h = headers(client, owner)
    first = created(client, h)
    admin = sign_in(client, "member")
    with database.session() as db:
        row = db.get(MembershipRow, UUID(admin["actor"]["membership_id"]))
        row.role = "COMPANY_ADMIN"
    other = headers(client, admin, h["Idempotency-Key"])
    result = client.post(BASE, headers=other, json=draft())
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "KNOWLEDGE_COMMAND_CONFLICT"
    assert (
        client.get(BASE + "/commands/" + other["Idempotency-Key"], headers=other).status_code == 404
    )
    assert counts(database) == (1, 1, 1)
    owner_again = sign_in(client)
    replay_headers = headers(client, owner_again, h["Idempotency-Key"])
    replay = client.post(BASE, headers=replay_headers, json=draft())
    assert replay.status_code == 200 and replay.json()["command"] == first["command"]


@pytest.mark.parametrize("altered", ["document", "company", "identity", "membership"])
def test_command_insert_cannot_cross_compound_scope_or_actor_binding(
    client: TestClient,
    database: Database,
    altered: str,
) -> None:
    session = sign_in(client)
    first = created(client, headers(client, session))
    other_id = other_membership(database, session)
    with database.session() as db:
        source = db.scalar(select(KnowledgeCommandRow))
        values = {
            name: getattr(source, name)
            for name in (
                "company_id",
                "document_id",
                "initiator_identity_id",
                "initiator_membership_id",
                "kind",
                "target_revision_id",
                "expected_current_revision_id",
                "payload_digest",
                "created_at",
            )
        }
        other = db.get(MembershipRow, UUID(other_id))
        if altered == "document":
            values["document_id"] = uuid4()
        elif altered == "company":
            values["company_id"] = other.company_id
        elif altered == "membership":
            values["initiator_membership_id"] = other.id
        else:
            values["initiator_identity_id"] = db.scalar(
                select(ExternalIdentityRow.id).where(
                    ExternalIdentityRow.id != source.initiator_identity_id
                )
            )
    with pytest.raises(DBAPIError):
        with database.session() as db:
            db.add(KnowledgeCommandRow(id=uuid4(), command_key=uuid4(), sequence=2, **values))
    assert counts(database) == (1, 1, 1)
    assert (
        client.get(
            BASE + "/" + first["document"]["document_id"], headers=headers(client, session)
        ).status_code
        == 200
    )


def test_sql_parameter_logging_never_exposes_document_originals(
    client: TestClient,
    database: Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    session = sign_in(client)
    h = headers(client, session)
    caplog.clear()
    caplog.set_level(logging.INFO, logger="sqlalchemy.engine")
    sentinel = "SYNTHETIC_PRIVATE_SQL_ORIGINAL_CANARY"
    original = sentinel + "\x00\r\n"
    first = created(client, h, draft(original, original, original))
    doc = first["document"]["document_id"]
    rev = first["command"]["target_revision_id"]
    assert (
        client.get(f"{BASE}/{doc}/revisions/{rev}/original", headers=h).json()["text"] == original
    )
    revised = client.post(
        f"{BASE}/{doc}/revisions",
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={**draft(original, original, original), "expected_current_revision_id": rev},
    )
    assert revised.status_code == 201
    current = revised.json()["command"]["target_revision_id"]
    assert (
        client.post(
            f"{BASE}/{doc}/archive",
            headers={**h, "Idempotency-Key": str(uuid4())},
            json={"expected_current_revision_id": current},
        ).status_code
        == 201
    )
    with pytest.raises(DBAPIError) as error:
        with database.session() as db:
            db.execute(
                text("UPDATE tenant_knowledge_revisions SET text_original=:original"),
                {"original": original.encode()},
            )
    assert "knowledge originals and commands are immutable" in str(error.value)
    assert "UPDATE tenant_knowledge_revisions" in str(error.value)
    assert sentinel not in str(error.value) + caplog.text
    assert "SQL parameters hidden" in caplog.text
    assert "INSERT INTO tenant_knowledge_revisions" in caplog.text
    assert "SELECT" in caplog.text and "COMMIT" in caplog.text


def test_fresh_python_process_recovers_committed_journal_and_originals(
    client: TestClient,
    database: Database,
    database_url: str,
) -> None:
    import os
    import subprocess
    import sys
    from pathlib import Path

    from apbra_api.auth_boundary import SESSION_COOKIE

    session = sign_in(client)
    h = headers(client, session)
    original = draft("title\x00\r\n", "opaque\ufeffversion\x00", "\ufefforiginal\r\n\x00😀")
    first = created(client, h, original)
    doc = first["document"]["document_id"]
    first_revision = first["command"]["target_revision_id"]
    next_result = client.post(
        f"{BASE}/{doc}/revisions",
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={
            **draft("new title", "earlier opaque version", "next text"),
            "expected_current_revision_id": first_revision,
        },
    )
    assert next_result.status_code == 201
    current = next_result.json()["command"]["target_revision_id"]
    archived = client.post(
        f"{BASE}/{doc}/archive",
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={"expected_current_revision_id": current},
    )
    assert archived.status_code == 201
    token = client.cookies.get(SESSION_COOKIE)
    assert isinstance(token, str)
    source_root = Path(__file__).resolve().parents[1] / "src"
    fixture = {
        "database_url": database_url,
        "session_token": token,
        "membership_id": h["X-Expected-Membership-Id"],
        "command_key": h["Idempotency-Key"],
        "command": first["command"],
        "document_id": doc,
        "original_revision_id": first_revision,
        "latest_revision_id": current,
        "latest_operation_id": archived.json()["command"]["operation_id"],
        "original_hashes": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in original.items()},
    }
    # Fresh interpreter, independent pool/session and original-byte projections.
    # The synthetic session credential travels only on stdin, never CLI/env/log.
    child = r"""
import hashlib,json,sys,os
from pathlib import Path
from uuid import UUID
from sqlalchemy.engine import make_url
import apbra_api.persistence as persisted
import apbra_api.knowledge_documents as documents
import apbra_api.knowledge_lifecycle as lifecycle
from apbra_api.persistence import Database
from apbra_api.knowledge_documents import KnowledgeDocumentsService, authorize, parse_payload
try:
    fixture=json.load(sys.stdin)
    source=Path(os.environ["PYTHONPATH"]).resolve()
    assert all(Path(module.__file__).resolve().is_relative_to(source)
               for module in (persisted,documents,lifecycle))
    url=make_url(fixture["database_url"])
    assert url.drivername=="postgresql+psycopg"
    assert url.host in {"127.0.0.1","localhost"} and url.port is not None
    assert url.database=="apbra_test" and not url.query
    database=Database(fixture["database_url"])
    service=KnowledgeDocumentsService()
    with database.session() as db:
        context=authorize(db, fixture["session_token"], fixture["membership_id"])
        recovered=service.reconcile(db, context, UUID(fixture["command_key"]))
        assert recovered["reconciliation"]=="COMMITTED"
        assert recovered["command"]==fixture["command"]
        assert recovered["document"]["current_revision_id"]==fixture["latest_revision_id"]
        assert recovered["document"]["current_operation_id"]==fixture["latest_operation_id"]
        assert recovered["document"]["local_state"]=="LOCAL_ARCHIVAL_REQUESTED"
        history=service.history(db, context, UUID(fixture["document_id"]))
        assert len(history["revisions"])==2 and len(history["operations"])==3
        original=service.original(db, context, UUID(fixture["document_id"]),
                                  UUID(fixture["original_revision_id"]))
        hashes={k:hashlib.sha256(original[k].encode()).hexdigest()
                for k in ("title","source_version","text")}
        assert hashes==fixture["original_hashes"]
        assert original["text_sha256"]==hashes["text"]
        original_payload={k:original[k] for k in ("title","source_version","text")}
        payload=parse_payload(json.dumps(original_payload).encode(), "CREATE")
        replay=service.apply(db, context, "CREATE", UUID(fixture["command_key"]), None, payload)
        assert replay["disposition"]=="REPLAY" and replay["command"]==fixture["command"]
        assert replay["document"]==recovered["document"]
    database.engine.dispose()
    print(json.dumps({"status":"FRESH_PROCESS_JOURNAL_ORIGINAL_REPLAY_PASS",
                      "revisions":2,"operations":3,"provider_write_outcome":"NOT_SENT"}))
except BaseException:
    print(json.dumps({"status":"FRESH_PROCESS_ASSERTION_FAILED"}))
    sys.exit(1)
"""
    # No inherited private settings/libpq variables or token-bearing environment.
    environment = {
        "PATH": os.defpath,
        "PYTHONPATH": str(source_root),
        "PYTHONNOUSERSITE": "1",
        "APBRA_PROFILE": "test",
    }
    result = subprocess.run(  # noqa: S603 - own interpreter, fixed code, synthetic stdin only
        [sys.executable, "-B", "-c", child],
        input=json.dumps(fixture).encode(),
        env=environment,
        capture_output=True,
        timeout=30,
        check=False,
    )
    # Never expose a child stderr/traceback, fixture, or credential on failure.
    assert result.returncode == 0, "FRESH_PROCESS_DURABILITY_FAILED"
    assert result.stderr == b"", "FRESH_PROCESS_UNEXPECTED_DIAGNOSTIC"
    assert json.loads(result.stdout) == {
        "status": "FRESH_PROCESS_JOURNAL_ORIGINAL_REPLAY_PASS",
        "revisions": 2,
        "operations": 3,
        "provider_write_outcome": "NOT_SENT",
    }
    assert counts(database) == (1, 2, 3)


def test_local_draft_revision_archive_do_not_implicitly_prepare_provider(client, database):
    from apbra_api.persistence import KnowledgeDispatchRow

    session = sign_in(client)
    h = headers(client, session)
    first = created(client, h)["document"]
    path = BASE + "/" + first["document_id"]
    revised = client.post(
        path + "/revisions",
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={**draft(), "expected_current_revision_id": first["current_revision_id"]},
    )
    assert revised.status_code == 201
    archived = client.post(
        path + "/archive",
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={"expected_current_revision_id": revised.json()["document"]["current_revision_id"]},
    )
    assert archived.status_code == 201
    assert client.get(path + "/provider-operations", headers=h).json()["operations"] == []
    with database.session() as db:
        assert db.scalar(select(KnowledgeDispatchRow.id)) is None
