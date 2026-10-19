"""Synthetic adapter only: durable protected local provider-operation workflow."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from conftest import disposable_alembic_config, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_knowledge_documents import BASE, created, draft, headers

from alembic import command
from apbra_api.api import create_app
from apbra_api.config import Settings
from apbra_api.knowledge_dispatch import KnowledgeDispatchService, ProviderResult, Submission
from apbra_api.knowledge_documents import authorize
from apbra_api.persistence import Database, KnowledgeDispatchCallRow, KnowledgeDispatchRow


class SyntheticProvider:
    def __init__(self) -> None:
        self.sent: list[Submission] = []
        self.observed: list[Submission] = []
        self.mode = "ACK"
        self.entered = threading.Event()
        self.release = threading.Event()
        self.hold = False

    def prepare(self, submission: Submission) -> tuple[str, ...]:
        return ("synthetic-key-one", "synthetic-key-two")

    def send(self, submission: Submission, call_id: UUID, keys: tuple[str, ...]) -> ProviderResult:
        self.sent.append(submission)
        if self.hold:
            self.entered.set()
            assert self.release.wait(10)
        return self.result(submission, call_id, keys)

    def reconcile(
        self, submission: Submission, call_id: UUID, keys: tuple[str, ...]
    ) -> ProviderResult:
        self.observed.append(submission)
        return self.result(submission, call_id, keys)

    def result(
        self, submission: Submission, call_id: UUID, keys: tuple[str, ...]
    ) -> ProviderResult:
        if self.mode == "ERROR":
            raise RuntimeError("synthetic private detail must never be returned")
        if self.mode == "FOREIGN":
            return ProviderResult(uuid4(), call_id, ((keys[0], True),))
        if self.mode == "MISSING":
            return ProviderResult(submission.operation_id, call_id, ((keys[0], True),))
        if self.mode == "DUPLICATE":
            return ProviderResult(
                submission.operation_id, call_id, ((keys[0], True), (keys[0], True))
            )
        values = tuple(
            (key, self.mode != "FAILED" and (i == 0 or self.mode != "PARTIAL"))
            for i, key in enumerate(keys)
        )
        return ProviderResult(submission.operation_id, call_id, values)


def setup(settings: Settings, database: Database, provider: SyntheticProvider | None = None):
    client = TestClient(
        create_app(settings=settings, database=database, knowledge_provider=provider)
    )
    session = sign_in(client)
    h = headers(client, session)
    saved = created(client, h)
    doc = saved["document"]
    path = BASE + "/" + doc["document_id"] + "/provider-operations"
    status = client.get(path, headers=h)
    assert status.status_code == 200, status.text
    payload = dict(
        expected_current_revision_id=doc["current_revision_id"],
        expected_current_operation_id=doc["current_operation_id"],
        expected_settings_version=status.json()["current_settings_version"],
        retry_of=None,
    )
    return client, h, doc, path, payload


def prepare(client, h, path, payload):
    result = client.post(path, headers=h, json=payload)
    assert result.status_code == 200, result.text
    return result.json()


def test_unconfigured_prepare_recovery_replay_and_no_send(settings, database):
    client, h, doc, path, payload = setup(settings, database)
    op = prepare(client, h, path, payload)
    assert op["provider_write_outcome"] == "NOT_SENT"
    assert prepare(client, h, path, payload) == op
    recovered = client.get(BASE + "/provider-commands/" + h["Idempotency-Key"], headers=h)
    assert recovered.json()["operation"] == op
    assert (
        client.post(path + "/" + op["operation_id"] + "/dispatch", headers=h, json={}).json()[
            "error"
        ]["code"]
        == "KNOWLEDGE_PROVIDER_UNCONFIGURED"
    )
    assert client.get(path, headers=h).json()["operations"][0]["calls"] == []
    changed = {**payload, "expected_settings_version": payload["expected_settings_version"] + 1}
    assert client.post(path, headers=h, json=changed).status_code == 409
    assert (
        client.post(path, headers={**h, "Idempotency-Key": str(uuid4())}, json=payload).status_code
        == 409
    )
    assert (
        client.get(BASE + "/" + doc["document_id"], headers=h).json()["provider_write_outcome"]
        == "NOT_SENT"
    )


@pytest.mark.parametrize(
    ("mode", "outcome"),
    [
        ("ACK", "ACKNOWLEDGED"),
        ("FAILED", "FAILED"),
        ("PARTIAL", "UNKNOWN"),
        ("ERROR", "UNKNOWN"),
        ("FOREIGN", "UNKNOWN"),
        ("MISSING", "UNKNOWN"),
        ("DUPLICATE", "UNKNOWN"),
    ],
)
def test_synthetic_receipts_are_not_indexing_and_dispatch_never_repeats(
    settings, database, mode, outcome
):
    provider = SyntheticProvider()
    provider.mode = mode
    client, h, doc, path, payload = setup(settings, database, provider)
    op = prepare(client, h, path, payload)
    result = client.post(path + "/" + op["operation_id"] + "/dispatch", headers=h, json={})
    assert result.status_code == 200, result.text
    value = result.json()["operations"][0]
    assert value["provider_write_outcome"] == outcome
    assert value["indexing"] == value["removal"] == value["ai_availability"] == "UNVERIFIED"
    assert "synthetic private detail" not in result.text
    assert (
        client.post(path + "/" + op["operation_id"] + "/dispatch", headers=h, json={}).status_code
        == 200
    )
    assert len(provider.sent) == 1
    assert provider.sent[0].text == "User text"
    assert "User text" not in repr(provider.sent[0])
    assert (
        client.get(BASE + "/" + doc["document_id"], headers=h).json()["provider_write_outcome"]
        == outcome
    )
    provider.mode = "ACK"
    observed = client.post(path + "/" + op["operation_id"] + "/reconcile", headers=h, json={})
    assert observed.json()["operations"][0]["provider_write_outcome"] == "ACKNOWLEDGED"
    assert len(provider.sent) == len(provider.observed) == 1


def test_interrupted_claim_survives_restart_reconciles_without_resend(settings, database):
    provider = SyntheticProvider()
    client, h, doc, path, payload = setup(settings, database, provider)
    op = prepare(client, h, path, payload)
    token = client.cookies.get("apbra_session")
    # Commit a claim, then simulate process interruption before any adapter invocation.
    with database.session() as db:
        context = authorize(db, token, h["X-Expected-Membership-Id"])
        claimed = KnowledgeDispatchService(provider).claim(
            db, context, UUID(doc["document_id"]), UUID(op["operation_id"]), False
        )
    assert claimed is not None
    client2 = TestClient(
        create_app(settings=settings, database=database, knowledge_provider=provider)
    )
    client2.cookies.update(client.cookies)
    state = client2.get(path, headers=h).json()["operations"][0]
    assert state["provider_write_outcome"] == "UNKNOWN"
    assert state["calls"][0]["reason"] == "PENDING_RECEIPT"
    assert (
        client2.post(path + "/" + op["operation_id"] + "/dispatch", headers=h, json={}).status_code
        == 200
    )
    assert provider.sent == []
    assert (
        client2.post(path + "/" + op["operation_id"] + "/reconcile", headers=h, json={}).status_code
        == 200
    )
    assert provider.sent == [] and len(provider.observed) == 1
    # An older receipt is retained without overriding the later observation.
    service = KnowledgeDispatchService(provider)
    provider.mode = "FAILED"
    late = provider.result(claimed[0], claimed[1], claimed[2])
    with database.session() as db:
        service.complete(db, claimed[1], late)
    assert (
        client.get(path, headers=h).json()["operations"][0]["provider_write_outcome"]
        == "ACKNOWLEDGED"
    )
    with database.session() as db:
        service.complete(db, claimed[1], late)  # exact replay
    with pytest.raises(Exception, match="KNOWLEDGE_RECEIPT_CONFLICT"):
        with database.session() as db:
            service.complete(
                db,
                claimed[1],
                ProviderResult(
                    claimed[0].operation_id, claimed[1], tuple((k, True) for k in claimed[2])
                ),
            )


def test_concurrent_dispatch_claim_and_late_old_revision_receipt(settings, database):
    provider = SyntheticProvider()
    provider.hold = True
    client, h, doc, path, payload = setup(settings, database, provider)
    op = prepare(client, h, path, payload)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            client.post, path + "/" + op["operation_id"] + "/dispatch", headers=h, json={}
        )
        assert provider.entered.wait(5)
        try:
            repeated = client.post(
                path + "/" + op["operation_id"] + "/dispatch", headers=h, json={}
            )
            assert repeated.json()["operations"][0]["provider_write_outcome"] == "UNKNOWN"
            revision = client.post(
                BASE + "/" + doc["document_id"] + "/revisions",
                headers={**h, "Idempotency-Key": str(uuid4())},
                json={
                    **draft(body="new original"),
                    "expected_current_revision_id": doc["current_revision_id"],
                },
            )
            assert revision.status_code == 201, revision.text
            newer = revision.json()["document"]
        finally:
            provider.release.set()
        assert future.result().status_code == 200
    assert len(provider.sent) == 1
    current = client.get(BASE + "/" + doc["document_id"], headers=h).json()
    assert current["current_revision_id"] == newer["current_revision_id"]
    assert current["provider_write_outcome"] == "NOT_SENT"
    assert (
        client.get(path, headers=h).json()["operations"][0]["provider_write_outcome"]
        == "ACKNOWLEDGED"
    )


def test_protected_reads_writes_and_tenant_isolation(settings, database):
    client, h, doc, path, payload = setup(settings, database)
    op = prepare(client, h, path, payload)
    routes = [path, BASE + "/provider-commands/" + h["Idempotency-Key"]]
    anonymous = TestClient(create_app(settings=settings, database=database))
    for route in routes:
        assert anonymous.get(route, headers=h).status_code == 401
    assert (
        client.post(
            path, headers={"X-Expected-Membership-Id": h["X-Expected-Membership-Id"]}, json=payload
        ).status_code
        == 401
    )
    assert (
        client.get(path, headers={**h, "X-Expected-Membership-Id": str(uuid4())}).status_code == 409
    )
    for selector in ["member", "foreign"]:
        other = TestClient(create_app(settings=settings, database=database))
        session = sign_in(other, selector)
        # capabilities itself is forbidden for ordinary members.
        cap = other.get(BASE + "/capabilities")
        if cap.status_code == 403:
            assert other.get(path, headers=h).status_code == 403
        else:
            oh = headers(other, session)
            assert other.get(path, headers=oh).status_code == 404
            assert (
                other.post(
                    path + "/" + op["operation_id"] + "/dispatch", headers=oh, json={}
                ).status_code
                == 404
            )
            assert other.get(routes[1], headers=oh).json()["operation"] is None


def test_append_only_history_and_populated_downgrade_refuses(settings, database):
    client, h, doc, path, payload = setup(settings, database, SyntheticProvider())
    op = prepare(client, h, path, payload)
    assert (
        client.post(path + "/" + op["operation_id"] + "/dispatch", headers=h, json={}).status_code
        == 200
    )
    for table in [
        "tenant_knowledge_dispatches",
        "tenant_knowledge_dispatch_calls",
        "tenant_knowledge_dispatch_receipts",
    ]:
        for mutation in ["DELETE FROM ", "UPDATE "]:
            with pytest.raises(DBAPIError):
                with database.session() as db:
                    statement = (
                        mutation
                        + table
                        + (" SET created_at=created_at" if mutation == "UPDATE " else "")
                    )
                    db.execute(text(statement))
    with pytest.raises(RuntimeError, match="Cannot downgrade retained knowledge dispatch history"):
        command.downgrade(disposable_alembic_config(settings.database_url), "20261013_09")
    with database.session() as db:
        assert db.scalar(select(KnowledgeDispatchRow.id)) == UUID(op["operation_id"])
        assert db.scalar(select(KnowledgeDispatchCallRow.id)) is not None


def test_acknowledged_send_cannot_be_retried_after_contradictory_observation(settings, database):
    provider = SyntheticProvider()
    client, h, doc, path, payload = setup(settings, database, provider)
    op = prepare(client, h, path, payload)
    assert (
        client.post(path + "/" + op["operation_id"] + "/dispatch", headers=h, json={}).status_code
        == 200
    )
    provider.mode = "FAILED"
    observed = client.post(path + "/" + op["operation_id"] + "/reconcile", headers=h, json={})
    value = observed.json()["operations"][0]
    assert value["provider_write_outcome"] == "UNKNOWN"
    assert value["receipt_outcome"] == "FAILED"
    assert value["write_evidence"] == "CONFLICTING"
    retry = client.post(
        path,
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={**payload, "retry_of": op["operation_id"]},
    )
    assert retry.status_code == 409
    assert len(provider.sent) == 1


def test_per_key_receipt_replay_detects_swapped_assignment_but_accepts_reordering(
    settings, database
):
    provider = SyntheticProvider()
    client, h, doc, path, payload = setup(settings, database, provider)
    op = prepare(client, h, path, payload)
    service = KnowledgeDispatchService(provider)
    with database.session() as db:
        context = authorize(db, client.cookies.get("apbra_session"), h["X-Expected-Membership-Id"])
        claimed = service.claim(
            db, context, UUID(doc["document_id"]), UUID(op["operation_id"]), False
        )
    assert claimed is not None
    submission, call_id, keys = claimed
    values = ((keys[0], True), (keys[1], False))
    with database.session() as db:
        service.complete(db, call_id, ProviderResult(submission.operation_id, call_id, values))
    with database.session() as db:
        service.complete(
            db, call_id, ProviderResult(submission.operation_id, call_id, tuple(reversed(values)))
        )
    with pytest.raises(Exception, match="KNOWLEDGE_RECEIPT_CONFLICT"):
        with database.session() as db:
            service.complete(
                db,
                call_id,
                ProviderResult(
                    submission.operation_id, call_id, ((keys[0], False), (keys[1], True))
                ),
            )


def test_prior_unknown_write_blocks_new_send_and_failed_retry_requires_explicit_intent(
    settings, database
):
    provider = SyntheticProvider()
    provider.mode = "ERROR"
    client, h, doc, path, payload = setup(settings, database, provider)
    first = prepare(client, h, path, payload)
    client.post(path + "/" + first["operation_id"] + "/dispatch", headers=h, json={})
    revised = client.post(
        BASE + "/" + doc["document_id"] + "/revisions",
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={
            **draft(body="Later original"),
            "expected_current_revision_id": doc["current_revision_id"],
        },
    ).json()["document"]
    newer = prepare(
        client,
        {**h, "Idempotency-Key": str(uuid4())},
        path,
        {
            **payload,
            "expected_current_revision_id": revised["current_revision_id"],
            "expected_current_operation_id": revised["current_operation_id"],
        },
    )
    denied = client.post(path + "/" + newer["operation_id"] + "/dispatch", headers=h, json={})
    assert (
        denied.status_code == 409
        and denied.json()["error"]["code"] == "KNOWLEDGE_PRIOR_WRITE_UNKNOWN"
    )
    provider.mode = "FAILED"
    client.post(path + "/" + first["operation_id"] + "/reconcile", headers=h, json={})
    assert (
        client.post(
            path + "/" + newer["operation_id"] + "/dispatch", headers=h, json={}
        ).status_code
        == 200
    )
    # Retry must be a new reviewed preparation bound to this exact failed operation.
    newer_payload = {
        **payload,
        "expected_current_revision_id": revised["current_revision_id"],
        "expected_current_operation_id": revised["current_operation_id"],
    }
    assert (
        client.post(
            path, headers={**h, "Idempotency-Key": str(uuid4())}, json=newer_payload
        ).status_code
        == 409
    )
    retry = prepare(
        client,
        {**h, "Idempotency-Key": str(uuid4())},
        path,
        {**newer_payload, "retry_of": newer["operation_id"]},
    )
    assert retry["provider_write_outcome"] == "NOT_SENT"
    assert len(provider.sent) == 2


def test_revocation_during_adapter_io_retains_receipt_but_denies_response(settings, database):
    from apbra_api.persistence import SessionRow

    provider = SyntheticProvider()
    provider.hold = True
    client, h, doc, path, payload = setup(settings, database, provider)
    op = prepare(client, h, path, payload)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            client.post, path + "/" + op["operation_id"] + "/dispatch", headers=h, json={}
        )
        assert provider.entered.wait(5)
        try:
            with database.session() as db:
                from datetime import UTC, datetime

                for row in db.scalars(select(SessionRow)):
                    row.revoked_at = datetime.now(UTC)
        finally:
            provider.release.set()
        assert future.result().status_code == 401
    with database.session() as db:
        from apbra_api.knowledge_dispatch import summary

        row = db.get(KnowledgeDispatchRow, UUID(op["operation_id"]))
        assert summary(db, row)["provider_write_outcome"] == "ACKNOWLEDGED"


def test_provider_injection_rejected_outside_test_profile(settings, database):
    other = settings.model_copy(
        update={"profile": "development", "test_semantic_simulator_enabled": False}
    )
    with pytest.raises(ValueError, match="requires the test profile"):
        create_app(settings=other, database=database, knowledge_provider=SyntheticProvider())


@pytest.mark.parametrize(
    "raw",
    [b"{}", b"null", b"[]", b'{"retry_of":null}', b'{"expected_settings_version":true}', b"\xff"],
)
def test_prepare_rejects_bad_shape_without_creating_operation(settings, database, raw):
    client, h, doc, path, payload = setup(settings, database)
    result = client.post(path, headers={**h, "Content-Type": "application/json"}, content=raw)
    assert result.status_code == 422
    assert client.get(path, headers=h).json()["operations"] == []


def test_changed_tenant_settings_require_explicit_unsent_replacement_and_observation_keeps_binding(
    settings, database
):
    provider = SyntheticProvider()
    client, h, doc, path, payload = setup(settings, database, provider)
    first = prepare(client, h, path, payload)

    def change_settings():
        current = client.get("/api/tenant-settings").json()
        result = client.patch(
            "/api/tenant-settings/sections/budgets_limits",
            headers=h,
            json={
                "expected_version": current["version"],
                "changes": {"invitation_ttl_days": current["settings"]["invitation_ttl_days"] - 1},
            },
        )
        assert result.status_code == 200, result.text
        return result.json()["version"]

    version = change_settings()
    denied = client.post(path + "/" + first["operation_id"] + "/dispatch", headers=h, json={})
    assert denied.status_code == 409
    assert provider.sent == []
    replacement = prepare(
        client,
        {**h, "Idempotency-Key": str(uuid4())},
        path,
        {**payload, "expected_settings_version": version, "retry_of": first["operation_id"]},
    )
    assert (
        client.post(
            path + "/" + replacement["operation_id"] + "/dispatch", headers=h, json={}
        ).status_code
        == 200
    )
    change_settings()
    assert (
        client.post(
            path + "/" + replacement["operation_id"] + "/reconcile", headers=h, json={}
        ).status_code
        == 200
    )
    assert provider.sent[0].settings_id == provider.observed[0].settings_id
    assert provider.observed[0].settings_version == version
    assert (
        client.get(path, headers=h).json()["operations"][0]["provider_write_outcome"] == "NOT_SENT"
    )


def test_prepared_retry_cannot_send_after_prior_operation_later_acknowledged(settings, database):
    provider = SyntheticProvider()
    provider.mode = "FAILED"
    client, h, doc, path, payload = setup(settings, database, provider)
    original = prepare(client, h, path, payload)
    assert (
        client.post(
            path + "/" + original["operation_id"] + "/dispatch", headers=h, json={}
        ).status_code
        == 200
    )
    retry = prepare(
        client,
        {**h, "Idempotency-Key": str(uuid4())},
        path,
        {**payload, "retry_of": original["operation_id"]},
    )
    provider.mode = "ACK"
    assert (
        client.post(
            path + "/" + original["operation_id"] + "/reconcile", headers=h, json={}
        ).status_code
        == 200
    )
    rejected = client.post(path + "/" + retry["operation_id"] + "/dispatch", headers=h, json={})
    assert (
        rejected.status_code == 409
        and rejected.json()["error"]["code"] == "KNOWLEDGE_PRIOR_WRITE_ACKNOWLEDGED"
    )
    assert len(provider.sent) == 1
    assert (
        client.get(path, headers=h).json()["operations"][-1]["provider_write_outcome"] == "NOT_SENT"
    )
