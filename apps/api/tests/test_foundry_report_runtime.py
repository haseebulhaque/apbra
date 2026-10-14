"""Synthetic runtime tests with disposable PostgreSQL and mocked provider/browser peers."""

import concurrent.futures
import contextlib
import dataclasses
import hashlib
import io
import json
import secrets
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from conftest import csrf, sign_in
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, update
from test_foundry_browser_handoff import Browser, Peer
from test_foundry_browser_metadata import setup, terminal
from test_foundry_memory_handoff import NONCE, Pipe

from apbra_api import foundry_browser_handoff as browser
from apbra_api import foundry_memory_handoff as receiver
from apbra_api import foundry_report_runtime as m
from apbra_api import foundry_report_runtime as report
from apbra_api.api import create_app
from apbra_api.application import AcceptanceService
from apbra_api.config import FoundryHostBinding
from apbra_api.evidence import LocalEvidenceStore
from apbra_api.foundry_memory_handoff import HandoffPlan
from apbra_api.model_provider import FoundryAccess, ProviderConfigurationError, ProviderProfile
from apbra_api.persistence import (
    ApplicationSession,
    CaseRow,
    InterpretationRow,
    TenantSettingsCurrentRow,
    TenantSettingsVersionRow,
    canonical_payload,
)
from apbra_api.semantic_bridge import SemanticBridge
from apbra_api.tenant_settings import _encoded, current_settings


@pytest.fixture(autouse=True)
def october_authorization_clock(monkeypatch):
    """Exercise the approved October ledger after calendar rollover too."""
    wall_time = time.time
    utc_time = time.gmtime
    offset = 1791936000.0 - wall_time()  # 2026-10-14 00:00 UTC, advancing normally.
    monkeypatch.setattr(time, "time", lambda: wall_time() + offset)
    monkeypatch.setattr(
        time, "gmtime", lambda stamp=None: utc_time(time.time() if stamp is None else stamp)
    )


def approval(attempts=1, stages=("REPORT_DESIGN",)):
    p = ProviderProfile(
        profile_id="synthetic",
        protocol="FOUNDRY_AGENT_RESPONSES",
        endpoint="https://synthetic.services.ai.azure.com/api/projects/synthetic/agents/synthetic/endpoint/protocols/openai/responses",
        model_or_deployment="synthetic",
        api_version="v1",
        region="synthetic",
        prompt_version="synthetic",
        configuration_id="synthetic",
        capabilities={"structured_output": True, "vision": False},
        max_calls_per_operation=attempts,
        max_input_characters=1000,
        max_output_tokens=128,
        time_budget_seconds=5,
        request_timeout_seconds=5,
        retry_limit=attempts - 1,
    )
    b = FoundryHostBinding(
        company_id=uuid4(),
        tenant_id=uuid4(),
        client_id=uuid4(),
        home_account_id="synthetic.account",
        provider_profile=p,
        knowledge_binding="synthetic-knowledge",
        knowledge_scope="TENANT_PRIVATE",
        agent_version="synthetic-version",
        qualification="LIVE_METADATA_VERIFIED",
        manual_authentication_approved=True,
        authorization_deadline=time.time() + 300,
    )
    return m.ReportApproval(
        binding=b,
        case_id=uuid4(),
        settings_id=uuid4(),
        settings_digest="a" * 64,
        authorization_id="b" * 64,
        request_version_id=uuid4(),
        semantic_context_version=1,
        input_digest="e" * 64,
        confirmed_contract_id=(uuid4() if stages == ("REPORT_DESIGN",) else None),
        confirmed_contract_digest=("1" * 64 if stages == ("REPORT_DESIGN",) else None),
        expected_interpretation_id=(uuid4() if stages == ("REPORT_DESIGN",) else None),
        expected_interpretation_digest=("f" * 64 if stages == ("REPORT_DESIGN",) else None),
        confirmation_mode=("CONFIRMED" if stages == ("REPORT_DESIGN",) else "AFTER_ANALYSIS"),
        approval="ONE_EXISTING_CASE_REPORT",
        ledger_period=time.strftime("%Y-%m", time.gmtime()),
        ledger_evidence_digest="c" * 64,
        posted_aud="1.00",
        unposted_exposure_aud="0.50",
        outstanding_reserves_aud="0.50",
        chain_reserve_aud="1.00",
        slots=tuple(
            m.Slot(
                stage=s,
                attempts=attempts,
                all_in_attempt_aud="0.10",
                bound_evidence_digest="d" * 64,
            )
            for s in stages
        ),
    )


class Credentials:
    def __init__(self, a):
        self.a = a
        self.calls = 0

    def ready(self, company, profile):
        return company == self.a.binding.company_id and profile == self.a.binding.provider_profile

    def resolve(self, company, profile):
        return FoundryAccess(
            company_id=company,
            profile_id=profile.profile_id,
            configuration_id=profile.configuration_id,
            credential=self.bearer,
            knowledge_binding="synthetic-knowledge",
            knowledge_scope="TENANT_PRIVATE",
            agent_version="synthetic-version",
        )

    def bearer(self):
        self.calls += 1
        return "synthetic-bearer-no-authority"


class TestReservations(unittest.TestCase):
    def gate(self, a, valid=lambda: True, state_loader=None):
        return m.Reservations(a, valid, state_loader or (lambda: self.state(a)))

    def test_readiness_and_resolve_consume_nothing(self):
        a = approval()
        g = self.gate(a, lambda: True)
        raw = Credentials(a)
        c = m.ReservedCredentials(raw, g)
        for _i in range(5):
            self.assertTrue(c.ready(a.binding.company_id, a.binding.provider_profile))
            c.resolve(a.binding.company_id, a.binding.provider_profile)
        self.assertEqual(g.receipt()["attempts_consumed"], 0)
        self.assertEqual(raw.calls, 0)

    def test_only_explicit_attempts_then_no_repeated_request(self):
        a = approval(2)
        g = self.gate(a, lambda: True)
        raw = Credentials(a)
        c = m.ReservedCredentials(raw, g)
        with g.operation(a.case_id, "REPORT_DESIGN"):
            access = c.resolve(a.binding.company_id, a.binding.provider_profile)
            access.credential()
            access.credential()
            with self.assertRaises(ProviderConfigurationError):
                access.credential()
        self.assertEqual(raw.calls, 2)
        with g.operation(a.case_id, "REPORT_DESIGN"), self.assertRaises(ProviderConfigurationError):
            c.resolve(a.binding.company_id, a.binding.provider_profile).credential()

    def test_unauthorized_candidate_context_spends_nothing(self):
        a = approval()
        g = self.gate(a, lambda: True)
        with g.operation(a.case_id, "REPORT_DESIGN"):
            pass
        self.assertEqual(g.receipt()["attempts_consumed"], 0)
        with g.operation(a.case_id, "REPORT_DESIGN"):
            g.claim(a.binding.company_id, a.binding.provider_profile)
        self.assertEqual(g.receipt()["attempts_consumed"], 1)

    def test_concurrent_requests_only_one_claims(self):
        a = approval()
        g = self.gate(a, lambda: True)
        barrier = threading.Barrier(2)

        def call():
            with g.operation(a.case_id, "REPORT_DESIGN"):
                barrier.wait()
                try:
                    g.claim(a.binding.company_id, a.binding.provider_profile)
                    time.sleep(0.03)
                    return True
                except ProviderConfigurationError:
                    return False

        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: call(), range(2)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(g.receipt()["attempts_consumed"], 1)

    def test_wrong_case_company_stage_profile_and_missing_context_deny(self):
        a = approval()
        g = self.gate(a, lambda: True)
        with self.assertRaises(ProviderConfigurationError):
            g.claim(a.binding.company_id, a.binding.provider_profile)
        for case, stage, company, profile in [
            (uuid4(), "REPORT_DESIGN", a.binding.company_id, a.binding.provider_profile),
            (a.case_id, "REQUIREMENT_ANALYSIS", a.binding.company_id, a.binding.provider_profile),
            (a.case_id, "REPORT_DESIGN", uuid4(), a.binding.provider_profile),
            (
                a.case_id,
                "REPORT_DESIGN",
                a.binding.company_id,
                a.binding.provider_profile.model_copy(update={"configuration_id": "wrong"}),
            ),
        ]:
            with g.operation(case, stage), self.assertRaises(ProviderConfigurationError):
                g.claim(company, profile)
        self.assertEqual(g.receipt()["attempts_consumed"], 0)

    def test_failure_consumes_no_automatic_refund_and_context_clears(self):
        a = approval()
        g = self.gate(a, lambda: True)
        with self.assertRaises(RuntimeError), g.operation(a.case_id, "REPORT_DESIGN"):
            g.claim(a.binding.company_id, a.binding.provider_profile)
            raise RuntimeError("synthetic timeout")
        self.assertIsNone(m.CURRENT.get())
        self.assertEqual(g.receipt()["operations_consumed"], 1)
        self.assertFalse(g.ready())

    def test_expiry_drift_close_deny_without_dispatch(self):
        for fault in ["drift", "close", "expiry"]:
            a = approval()
            valid = [True]
            g = self.gate(a, lambda valid=valid: valid[0])
            if fault == "drift":
                valid[0] = False
            elif fault == "close":
                g.close()
            else:
                g.approval.binding.__dict__["authorization_deadline"] = time.time() - 1
            with (
                g.operation(a.case_id, "REPORT_DESIGN"),
                self.assertRaises(ProviderConfigurationError),
            ):
                g.claim(a.binding.company_id, a.binding.provider_profile)
            self.assertEqual(g.receipt()["attempts_consumed"], 0)

    def test_explicit_stage_order(self):
        a = approval(stages=("REQUIREMENT_ANALYSIS", "REPORT_DESIGN"))
        state = [self.state(a)]
        g = self.gate(a, lambda: True, lambda: state[0])
        with g.operation(a.case_id, "REPORT_DESIGN"), self.assertRaises(ProviderConfigurationError):
            g.claim(a.binding.company_id, a.binding.provider_profile)
        with g.operation(a.case_id, "REQUIREMENT_ANALYSIS"):
            g.claim(a.binding.company_id, a.binding.provider_profile)
            state[0] = dataclasses.replace(
                state[0], interpretation_id=uuid4(), interpretation_digest="f" * 64
            )
        with g.operation(a.case_id, "REPORT_DESIGN"), self.assertRaises(ProviderConfigurationError):
            g.claim(a.binding.company_id, a.binding.provider_profile)
        state[0] = dataclasses.replace(
            state[0],
            confirmed_contract_id=uuid4(),
            confirmed_interpretation_id=state[0].interpretation_id,
            confirmed_digest="f" * 64,
            confirmed_contract_digest="1" * 64,
        )
        with g.operation(a.case_id, "REPORT_DESIGN"):
            g.claim(a.binding.company_id, a.binding.provider_profile)
        self.assertEqual(g.receipt()["operations_consumed"], 2)

    def test_cost_unknown_excess_subprecision_and_missing_bound_refuse(self):
        a = approval()
        for updates in [
            {"chain_reserve_aud": "unknown"},
            {"chain_reserve_aud": "9.01"},
            {
                "posted_aud": "10",
                "unposted_exposure_aud": "0",
                "outstanding_reserves_aud": "0",
                "chain_reserve_aud": "0.0000000000000000000000000000000000000001",
            },
            {"ledger_period": "2000-01"},
            {"ledger_evidence_digest": "unknown"},
        ]:
            data = a.model_dump()
            data.update(updates)
            with self.assertRaises(ValidationError):
                m.ReportApproval.model_validate(data)

    def test_october_grant_does_not_renew_into_november(self):
        a = approval()
        data = a.model_dump()
        data["binding"]["authorization_deadline"] = m.BUDGET_END + 1
        with self.assertRaises(ValidationError):
            m.ReportApproval.model_validate(data)
        g = self.gate(a, lambda: True)
        with patch.object(m.time, "strftime", return_value="2026-11"):
            self.assertFalse(g.ready())
            with (
                g.operation(a.case_id, "REPORT_DESIGN"),
                self.assertRaises(ProviderConfigurationError),
            ):
                g.claim(a.binding.company_id, a.binding.provider_profile)

    def state(self, a):
        return m.ReportState(
            a.settings_id,
            a.settings_digest,
            a.binding.company_id,
            a.binding.provider_profile,
            None,
            a.case_id,
            a.request_version_id,
            a.semantic_context_version,
            a.input_digest,
            a.expected_interpretation_id,
            a.expected_interpretation_digest,
            a.confirmed_contract_id,
            a.expected_interpretation_id,
            a.expected_interpretation_digest,
            a.confirmed_contract_digest,
        )

    def test_saved_input_and_confirmation_drift_never_dispatch(self):
        a = approval()
        state = [self.state(a)]
        g = self.gate(a, lambda: True, lambda: state[0])
        for change in [
            {"request_version_id": uuid4()},
            {"semantic_context_version": 2},
            {"input_digest": "0" * 64},
            {"confirmed_contract_id": uuid4()},
            {"confirmed_interpretation_id": uuid4()},
        ]:
            state[0] = dataclasses.replace(self.state(a), **change)
            with (
                g.operation(a.case_id, "REPORT_DESIGN"),
                self.assertRaises(ProviderConfigurationError),
            ):
                g.claim(a.binding.company_id, a.binding.provider_profile)
        self.assertEqual(g.receipt()["attempts_consumed"], 0)

    def test_bootstrap_private_failure_sanitizes_output_and_closes_channel(self):
        a = approval()
        plan = SimpleNamespace(
            company_id=a.binding.company_id,
            tenant_id=a.binding.tenant_id,
            client_id=a.binding.client_id,
            authorization_deadline=a.binding.authorization_deadline,
        )
        closed = []
        channel = SimpleNamespace(close=lambda: closed.append(True))

        def bad():
            print("synthetic-private-canary")
            raise RuntimeError("synthetic-private-canary")

        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
            self.assertRaises(ProviderConfigurationError) as error,
        ):
            m.run_report_receiver(
                plan, channel, a, settings=None, snapshot_loader=bad, state_loader=bad
            )
        self.assertNotIn("canary", str(error.exception) + output.getvalue())
        self.assertTrue(closed)

    def test_single_combined_state_disallows_mixed_settings_pair(self):
        a = approval()
        good = self.state(a)
        state = iter(
            [
                dataclasses.replace(good, settings_digest="0" * 64),
                dataclasses.replace(good, settings_id=uuid4()),
            ]
        )
        g = self.gate(a, lambda: m.same_input(a, next(state)))
        self.assertFalse(g.ready())
        self.assertFalse(g.ready())

    def test_private_invalid_approval_does_not_echo_raw_input(self):
        with self.assertRaises(ProviderConfigurationError) as error:
            m.decode_private_approval(b'{"private":"synthetic-private-canary"}')
        self.assertNotIn("canary", str(error.exception))

    def test_cached_unconfirmed_owner_confirm_then_design_only(self):
        a = approval()
        data = a.model_dump()
        data.update(
            confirmed_contract_id=None,
            confirmed_contract_digest=None,
            confirmation_mode="OWNER_CONFIRM_PENDING",
        )
        a = m.ReportApproval.model_validate(data)
        state = [
            dataclasses.replace(
                self.state(a),
                confirmed_contract_id=None,
                confirmed_interpretation_id=None,
                confirmed_digest=None,
            )
        ]
        g = self.gate(a, lambda: True, lambda: state[0])
        self.assertTrue(g.ready())
        with g.operation(a.case_id, "REPORT_DESIGN"), self.assertRaises(ProviderConfigurationError):
            g.claim(a.binding.company_id, a.binding.provider_profile)
        self.assertEqual(g.receipt()["attempts_consumed"], 0)
        state[0] = dataclasses.replace(
            state[0],
            confirmed_contract_id=uuid4(),
            confirmed_interpretation_id=a.expected_interpretation_id,
            confirmed_digest=a.expected_interpretation_digest,
            confirmed_contract_digest="1" * 64,
        )
        with g.operation(a.case_id, "REPORT_DESIGN"):
            g.claim(a.binding.company_id, a.binding.provider_profile)
        self.assertEqual(g.receipt()["attempts_consumed"], 1)

    def test_fastapi_sync_context_and_auth_before_claim(self):
        a = approval()
        g = self.gate(a, lambda: True)
        raw = Credentials(a)
        wrapper = None

        def create(**kw):
            nonlocal wrapper
            wrapper = kw["foundry_credentials"]
            app = FastAPI()

            @app.post("/api/cases/{case}/automatic-designs")
            def route(case: str, request: Request):
                if request.headers.get("x-synthetic-auth") != "authorized":
                    raise HTTPException(403)
                return {
                    "value": wrapper.resolve(
                        a.binding.company_id, a.binding.provider_profile
                    ).credential()
                }

            return app

        app = m.application_factory(a, g, create)(foundry_credentials=raw)
        with TestClient(app) as client:
            url = f"/api/cases/{a.case_id}/automatic-designs"
            self.assertEqual(client.post(url).status_code, 403)
            self.assertEqual(g.receipt()["attempts_consumed"], 0)
            self.assertEqual(
                client.post(url, headers={"x-synthetic-auth": "authorized"}).status_code, 200
            )
        self.assertIsNone(m.CURRENT.get())
        self.assertEqual(raw.calls, 1)


def new_settings(db, company, updates, *, invalid_digest=False):
    snapshot = current_settings(db, company)
    policy = snapshot.settings.model_copy(update=updates)
    old = db.get(TenantSettingsVersionRow, snapshot.id)
    row = TenantSettingsVersionRow(
        id=uuid4(),
        company_id=company,
        version=snapshot.version + 1,
        settings_json=_encoded(policy),
        settings_digest=(
            "0" * 64
            if invalid_digest
            else canonical_payload(policy.model_dump(mode="json", by_alias=True))
        ),
        created_by_membership_id=old.created_by_membership_id,
        changed_keys_json="[]",
        safe_changes_json="[]",
        validation_status="PASS",
    )
    db.add(row)
    db.flush()
    pointer = db.get(TenantSettingsCurrentRow, company)
    pointer.version_id = row.id
    pointer.version = row.version
    db.flush()


@pytest.fixture
def saved(settings, database, client):
    session = sign_in(client, "owner")
    company = UUID(session["actor"]["company_id"])
    # Synthetic settings only; preserve authoritative serialization and digest.
    p = approval().binding.provider_profile
    with database.session() as db:
        new_settings(db, company, {"provider_profile": p})
    settings.qualified_provider_profiles_json = json.dumps([p.model_dump()])
    case = client.post(
        "/api/cases",
        json={"request_text": "Create a report of total amount by division."},
        headers={**csrf(session), "Idempotency-Key": str(uuid4())},
    ).json()["case"]
    upload = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "synthetic.csv", "expected_context_version": 1},
        content=b"Amount,Division\n12,North\n9,South\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]

    def service(snapshot):
        return AcceptanceService(
            SemanticBridge(
                settings.semantic_bridge_path,
                node_executable=settings.semantic_node_path,
                timeout_seconds=settings.semantic_timeout_seconds,
            ),
            LocalEvidenceStore(settings.evidence_root, settings.profile),
            reference_objects=LocalEvidenceStore(settings.reference_root, settings.profile),
            tenant_settings=snapshot,
        )

    def load():
        return m.load_report_state(
            database,
            company,
            UUID(case["id"]),
            service,
            query_timeout_seconds=p.request_timeout_seconds,
        )

    return SimpleNamespace(
        settings=settings,
        database=database,
        client=client,
        session=session,
        company=company,
        case=case,
        upload=upload,
        service=service,
        load=load,
        profile=p,
    )


def interpret(s):
    r = s.client.post(
        f"/api/cases/{s.case['id']}/interpretations",
        json={"expected_context_version": s.upload["semantic_context_version"]},
        headers=csrf(s.session),
    )
    assert r.status_code == 200, r.text
    return r.json()["interpretation"]


def confirm(s, interpretation):
    r = s.client.post(
        f"/api/cases/{s.case['id']}/confirm",
        json={
            "interpretation_id": interpretation["id"],
            "expected_context_version": s.upload["semantic_context_version"],
        },
        headers=csrf(s.session),
    )
    assert r.status_code == 200, r.text
    return r.json()["confirmed_contract"]


def bound_approval(s, state, mode="CONFIRMED"):
    a = approval()
    data = a.model_dump()
    data["binding"].update(company_id=s.company, provider_profile=s.profile)
    data.update(
        case_id=state.case_id,
        settings_id=state.settings_id,
        settings_digest=state.settings_digest,
        request_version_id=state.request_version_id,
        semantic_context_version=state.semantic_context_version,
        input_digest=state.input_digest,
        expected_interpretation_id=state.interpretation_id,
        expected_interpretation_digest=state.interpretation_digest,
        confirmed_contract_id=state.confirmed_contract_id,
        confirmed_contract_digest=state.confirmed_contract_digest,
        confirmation_mode=mode,
    )
    return m.ReportApproval.model_validate(data)


def test_reader_real_snapshot_context_and_confirmation_are_read_only(saved):
    s = saved
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(s.database.engine, "before_cursor_execute", capture)
    try:
        before = s.load()
        assert before.interpretation_id is None and before.profile == s.profile
        assert any(x == "SET TRANSACTION READ ONLY" for x in statements)
        assert any(x.startswith("SET LOCAL statement_timeout") for x in statements)
        assert not any(
            x.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"} for x in statements
        )
    finally:
        event.remove(s.database.engine, "before_cursor_execute", capture)
    interpretation = interpret(s)
    unconfirmed = s.load()
    assert unconfirmed.interpretation_id == UUID(interpretation["id"])
    assert unconfirmed.confirmed_contract_id is None
    contract = confirm(s, interpretation)
    confirmed = s.load()
    assert confirmed.confirmed_contract_id == UUID(contract["id"])
    assert confirmed.confirmed_contract_digest == canonical_payload(contract["contract"])
    assert confirmed.confirmed_digest == confirmed.interpretation_digest
    assert before.input_digest == unconfirmed.input_digest == confirmed.input_digest
    with s.database.session() as db:
        row = db.get(InterpretationRow, confirmed.interpretation_id)
        assert confirmed.interpretation_digest == row.readiness_binding_digest


@pytest.mark.parametrize(
    "fault",
    [
        "foreign_company",
        "foreign_case",
        "timeout_unknown",
        "timeout_drift",
        "evidence_tamper",
        "interpretation_context_tamper",
        "settings_tamper",
    ],
)
def test_reader_rejects_wrong_or_changed_authority_quietly(saved, fault, capsys, monkeypatch):
    s = saved
    company = s.company
    case = UUID(s.case["id"])
    timeout = s.profile.request_timeout_seconds
    if fault == "foreign_company":
        company = uuid4()
    elif fault == "foreign_case":
        case = uuid4()
    elif fault == "timeout_unknown":
        timeout = float("nan")
    elif fault == "timeout_drift":
        timeout += 1
    elif fault == "evidence_tamper":
        with s.database.session() as db:
            row = db.evidence_items(case)[0]
        (s.settings.evidence_root / row.storage_key).write_bytes(b"synthetic-modified-bytes")
    elif fault == "interpretation_context_tamper":
        interpret(s)
        original = ApplicationSession.interpretation_for_context

        def corrupted(db, case_id, version):
            row = original(db, case_id, version)
            value = json.loads(row.session_json)
            value["contextBinding"] = "synthetic-private-canary"
            return dataclasses.replace(row, session_json=json.dumps(value))

        # Immutable rows cannot be updated: inject a corrupt projection instead,
        # retaining PostgreSQL immutability controls in this real-domain test.
        monkeypatch.setattr(ApplicationSession, "interpretation_for_context", corrupted)
    elif fault == "settings_tamper":
        with s.database.session() as db:
            new_settings(db, s.company, {}, invalid_digest=True)
    with pytest.raises(ProviderConfigurationError, match=m.ERROR) as error:
        m.load_report_state(s.database, company, case, s.service, query_timeout_seconds=timeout)
    output = capsys.readouterr()
    assert "synthetic-private-canary" not in str(error.value) + output.out + output.err


def test_reader_transaction_really_rejects_writes(saved):
    s = saved
    denials = []

    def reject_write(conn, cursor, statement, parameters, context, executemany):
        if statement == "SET TRANSACTION READ ONLY":
            try:
                conn.execute(
                    update(CaseRow).values(
                        semantic_context_version=CaseRow.semantic_context_version
                    )
                )
            except Exception as error:
                denials.append(getattr(getattr(error, "orig", None), "sqlstate", None))
                raise

    event.listen(s.database.engine, "after_cursor_execute", reject_write)
    try:
        with pytest.raises(ProviderConfigurationError, match=m.ERROR):
            s.load()
    finally:
        event.remove(s.database.engine, "after_cursor_execute", reject_write)
    assert denials == ["25006"]  # read_only_sql_transaction, not a missing table


def test_reader_snapshot_does_not_mix_concurrent_settings_commit(saved):
    s = saved
    before = s.load()
    changed = []

    def concurrent(conn, cursor, statement, parameters, context, executemany):
        if (
            not changed
            and statement.lstrip().startswith("SELECT")
            and f"FROM {CaseRow.__tablename__}" in statement
        ):
            changed.append(True)
            with s.database.session() as db:
                new_settings(db, s.company, {"automatic_generation_enabled": True})

    event.listen(s.database.engine, "after_cursor_execute", concurrent)
    try:
        state = s.load()
    finally:
        event.remove(s.database.engine, "after_cursor_execute", concurrent)
    assert (
        changed
        and state.settings_id == before.settings_id
        and state.settings_digest == before.settings_digest
    )
    fresh = s.load()
    assert (
        fresh.settings_id != before.settings_id and fresh.settings_digest != before.settings_digest
    )


def test_factory_real_api_cached_confirm_auth_and_private_case_before_dispatch(saved, monkeypatch):
    import apbra_api.api as api
    from apbra_api.model_provider import ProviderCallError

    s = saved
    interpretation = interpret(s)
    with s.database.session() as db:
        new_settings(db, s.company, {"automatic_generation_enabled": True})
    state = s.load()
    a = bound_approval(s, state, "OWNER_CONFIRM_PENDING")
    gate = m.Reservations(a, lambda: True, s.load)
    raw = Credentials(a)

    # Exercise the real API's provider construction, private access, CSRF,
    # Confirm and dispatch. Synthetic timeout occurs after the reserved bearer.
    class TimeoutProvider:
        def __init__(self, profile, access, **kwargs):
            self.access = access
            self.profile = profile

        def structured(self, request):
            self.access.credential()
            raise ProviderCallError("MODEL_PROVIDER_TIMEOUT")

    monkeypatch.setattr(api, "FoundryAgentResponsesProvider", TimeoutProvider)
    app = m.application_factory(a, gate, create_app)(
        settings=s.settings, database=s.database, foundry_credentials=raw
    )
    url = f"/api/cases/{s.case['id']}/automatic-designs"
    with TestClient(app) as c:
        c.cookies.update(s.client.cookies)
        cached = c.post(
            f"/api/cases/{s.case['id']}/interpretations",
            json={"expected_context_version": s.upload["semantic_context_version"]},
            headers=csrf(s.session),
        )
        assert cached.status_code == 200 and raw.calls == 0
        contract = c.post(
            f"/api/cases/{s.case['id']}/confirm",
            json={
                "interpretation_id": interpretation["id"],
                "expected_context_version": s.upload["semantic_context_version"],
            },
            headers=csrf(s.session),
        )
        assert contract.status_code == 200 and raw.calls == 0
        payload = {
            "confirmed_contract_id": contract.json()["confirmed_contract"]["id"],
            "command_key": str(uuid4()),
        }
        assert c.post(url, json=payload).status_code == 401
        assert raw.calls == 0
        member = TestClient(app, raise_server_exceptions=False)
        other = sign_in(member, "member")
        assert member.post(url, json=payload, headers=csrf(other)).status_code in (403, 404)
        member.close()
        assert raw.calls == 0
        response = c.post(url, json=payload, headers=csrf(s.session))
        assert response.status_code >= 400 and raw.calls == 1
        assert (
            gate.receipt()["attempts_consumed"] == 1 and gate.receipt()["operations_consumed"] == 1
        )
        c.post(url, json={**payload, "command_key": str(uuid4())}, headers=csrf(s.session))
        assert raw.calls == 1
        # Spent dispatch authority must not block existing read/compile services
        # whose constructors resolve an available provider but never call it.
        assert c.get(f"/api/cases/{s.case['id']}/acceptance").status_code == 200
        assert (
            c.get(
                url, params={"confirmed_contract_id": payload["confirmed_contract_id"]}
            ).status_code
            == 200
        )
        assert raw.calls == 1
    assert m.CURRENT.get() is None


def test_factory_hook_is_exactly_additive_and_metadata_cannot_use_it():
    current = Path(receiver.__file__).read_text()
    restored = current.replace(
        "    application_factory: Callable[..., Any] | None = None,\n", "", 1
    )
    restored = restored.replace(
        "            require(\n                application_factory is None\n"
        "                or (binding is not None and callable(application_factory))\n"
        "            )\n",
        "",
        1,
    )
    restored = restored.replace(
        "            app = (application_factory or create_app)(\n",
        "            app = create_app(\n",
        1,
    )
    route = """        if runtime:
            from .foundry_report_runtime import run_private_report_receiver

            run_private_report_receiver(
                HandoffPlan(**args), StdioChannel(), listener=listener, published_port=published
            )
            return
"""
    assert restored.count(route) == 1
    restored = restored.replace(route, "", 1)
    assert (
        hashlib.sha256(restored.encode()).hexdigest()
        == "e2e6e8debd358a3cf408d052ecb77bece022a5dbd0598d2ea6f92b7fa97d1b76"
    )
    a = approval()
    p = HandoffPlan(
        a.binding.company_id,
        a.binding.tenant_id,
        a.binding.client_id,
        a.binding.authorization_deadline,
    )
    from apbra_api.config import Settings

    channel = SimpleNamespace(close=lambda: None)
    settings = Settings(
        _env_file=None,
        profile="test",
        database_url="sqlite://",
        session_secret=secrets.token_urlsafe(32),
    )
    with pytest.raises(receiver.HandoffError):
        receiver.run_receiver(
            p,
            channel,
            settings=settings,
            runtime=False,
            application_factory=lambda **k: k,
            serve=lambda *a: None,
            snapshot_loader=lambda: pytest.fail("must fail before snapshot"),
        )


def test_real_receiver_factory_passes_live_synthetic_lease_and_closes(saved, monkeypatch, capsys):
    import apbra_api.foundry_memory_handoff as released

    s = saved
    interpretation = interpret(s)
    confirm(s, interpretation)
    state = s.load()
    a = bound_approval(s, state)
    settings = s.settings.model_copy(
        update={"profile": "development", "test_semantic_simulator_enabled": False}
    )

    # In-memory channel responds to fresh receiver nonce; no actual token or SDK.
    class Pipe:
        def __init__(self):
            self.value = io.BytesIO(receiver.HELLO)
            self.output = []
            self.closed = False

        def read(self, n, deadline):
            return self.value.read(n)

        def write(self, value):
            self.output.append(value)
            if value.startswith(b"{"):
                nonce = json.loads(value)["nonce"]
                common = dict(
                    v=1,
                    nonce=nonce,
                    company=str(a.binding.company_id),
                    tenant=str(a.binding.tenant_id),
                    client=str(a.binding.client_id),
                    deadline=a.binding.authorization_deadline,
                    account="synthetic.account",
                )

                def frame(v):
                    r = json.dumps(v).encode()
                    return len(r).to_bytes(4, "big") + r

                self.value = io.BytesIO(
                    frame(common)
                    + frame(
                        {
                            **common,
                            "token": "synthetic-memory-canary",
                            "expires": int(time.time() + 100),
                        }
                    )
                )

        def connected(self, timeout):
            time.sleep(min(timeout, 0.005))
            return not self.closed

        def close(self):
            self.closed = True

    pipe = Pipe()
    captured = []
    monkeypatch.setattr(released, "run_receiver", receiver.run_receiver)

    def serve(app, settings, stopped):
        # A dict app cannot receive middleware: use real FastAPI while retaining
        # only injected credentials; no database/app route is needed in this test.
        credentials = app.state.synthetic_credentials
        captured.append(credentials)
        assert credentials.ready(s.company, s.profile)
        with credentials.reservations.operation(state.case_id, "REPORT_DESIGN"):
            token = credentials.resolve(s.company, s.profile).credential()
            assert token.token == "synthetic-" + "memory-canary"

    from fastapi import FastAPI

    def app(**kwargs):
        value = FastAPI()
        value.state.synthetic_credentials = kwargs["foundry_credentials"]
        return value

    monkeypatch.setattr("apbra_api.api.create_app", app)

    def snapshot():
        with s.database.session() as db:
            return current_settings(db, s.company)

    receipt = m.run_report_receiver(
        HandoffPlan(
            a.binding.company_id,
            a.binding.tenant_id,
            a.binding.client_id,
            a.binding.authorization_deadline,
        ),
        pipe,
        a,
        settings=settings,
        snapshot_loader=snapshot,
        state_loader=s.load,
        serve=serve,
    )
    assert receipt["attempts_consumed"] == 1 and receipt["status"] == "REPORT_RESERVATION_CLOSED"
    assert pipe.closed and not captured[0].ready(s.company, s.profile)
    output = capsys.readouterr()
    assert "synthetic-memory-canary" not in output.out + output.err + b"".join(pipe.output).decode()


def test_real_receiver_factory_failure_retains_exposure_and_hides_canary(
    saved, monkeypatch, capsys
):
    import apbra_api.foundry_memory_handoff as released

    s = saved
    interpretation = interpret(s)
    confirm(s, interpretation)
    state = s.load()
    a = bound_approval(s, state)
    channel = SimpleNamespace(closed=False)
    channel.close = lambda: setattr(channel, "closed", True)
    held = []

    def failed_receiver(plan, pipe, **kwargs):
        # Same trusted hook receives reserved credentials; fail after dispatch.
        wrapped = kwargs["application_factory"](foundry_credentials=Credentials(a))
        held.append(wrapped.state.synthetic_credentials)
        with held[0].reservations.operation(state.case_id, "REPORT_DESIGN"):
            held[0].resolve(s.company, s.profile).credential()
            print("synthetic-private-failure-canary")
            raise RuntimeError("synthetic-private-failure-canary")

    from fastapi import FastAPI

    def app(**kwargs):
        value = FastAPI()
        value.state.synthetic_credentials = kwargs["foundry_credentials"]
        return value

    monkeypatch.setattr("apbra_api.api.create_app", app)
    monkeypatch.setattr(released, "run_receiver", failed_receiver)
    with pytest.raises(ProviderConfigurationError, match=m.ERROR) as error:
        m.run_report_receiver(
            HandoffPlan(
                a.binding.company_id,
                a.binding.tenant_id,
                a.binding.client_id,
                a.binding.authorization_deadline,
            ),
            channel,
            a,
            settings=s.settings,
            snapshot_loader=lambda: None,
            state_loader=s.load,
            serve=lambda *args: None,
        )
    assert held[0].reservations.receipt()["attempts_consumed"] == 1
    assert (
        channel.closed and held[0].reservations.closed and not held[0].ready(s.company, s.profile)
    )
    output = capsys.readouterr()
    assert "synthetic-private-failure-canary" not in output.out + output.err + str(error.value)


def test_private_bootstrap_default_reader_and_factory_on_synthetic_postgres(
    saved, monkeypatch, capsys
):
    from apbra_api import foundry_report_runtime as runtime

    s = saved
    interpretation = interpret(s)
    confirm(s, interpretation)
    state = s.load()
    a = runtime.ReportApproval.model_validate(bound_approval(s, state).model_dump())
    p = HandoffPlan(
        a.binding.company_id,
        a.binding.tenant_id,
        a.binding.client_id,
        a.binding.authorization_deadline,
    )
    from fastapi import FastAPI

    held = []

    def create(**kwargs):
        value = FastAPI()
        value.state.credentials = kwargs["foundry_credentials"]
        return value

    monkeypatch.setattr("apbra_api.api.create_app", create)

    class Pipe:
        def __init__(self):
            self.value = io.BytesIO(b"APBRA_MEMORY_HANDOFF_1\n")
            self.output = []
            self.closed = False

        def read(self, n, deadline):
            return self.value.read(n)

        def write(self, value):
            self.output.append(value)
            if value.startswith(b"{"):
                nonce = json.loads(value)["nonce"]
                common = dict(
                    v=1,
                    nonce=nonce,
                    company=str(p.company_id),
                    tenant=str(p.tenant_id),
                    client=str(p.client_id),
                    deadline=p.authorization_deadline,
                    account="synthetic.account",
                )

                def frame(v):
                    r = json.dumps(v).encode()
                    return len(r).to_bytes(4, "big") + r

                self.value = io.BytesIO(
                    runtime.approval_frame(p, a, nonce)
                    + frame(common)
                    + frame(
                        {
                            **common,
                            "token": "synthetic-private-bootstrap-canary",
                            "expires": int(time.time() + 100),
                        }
                    )
                )

        def connected(self, timeout):
            time.sleep(min(timeout, 0.005))
            return not self.closed

        def close(self):
            self.closed = True

    channel = Pipe()

    def serve(app, settings, stopped):
        credentials = app.state.credentials
        held.append(credentials)
        with credentials.reservations.operation(a.case_id, "REPORT_DESIGN"):
            token = credentials.resolve(p.company_id, a.binding.provider_profile).credential()
            assert token.token == "synthetic-" + "private-bootstrap-canary"

    settings = s.settings.model_copy(
        update={"profile": "development", "test_semantic_simulator_enabled": False}
    )
    receipt = runtime.run_private_report_receiver(p, channel, settings=settings, serve=serve)
    assert receipt["attempts_consumed"] == 1 and channel.closed
    assert not held[0].ready(p.company_id, a.binding.provider_profile)
    output = capsys.readouterr()
    assert (
        "synthetic-private-bootstrap-canary"
        not in output.out + output.err + b"".join(channel.output).decode()
    )


def grant(c=None):
    data = approval().model_dump()
    if c is not None:
        data["binding"].update(
            company_id=c.plan.company_id,
            tenant_id=c.plan.tenant_id,
            client_id=c.plan.client_id,
            authorization_deadline=c.plan.authorization_deadline,
            provider_profile=c.profile,
            agent_version=c.profile.agent_version,
        )
    return report.ReportApproval.model_validate(data)


def plan(a):
    b = a.binding
    return receiver.HandoffPlan(b.company_id, b.tenant_id, b.client_id, b.authorization_deadline)


class ReportPeer(Peer):
    runtime = True

    def __init__(self, ack=b"REPORT_APPROVAL_ACCEPTED", **kwargs):
        super().__init__(**kwargs)
        self.stream = io.BytesIO(
            json.dumps(dict(v=1, nonce=NONCE, pid=1)).encode()
            + b"\n"
            + ack
            + b"\nACCOUNT_ACCEPTED\nHANDOFF_READY_INVOCATION_GATED\n"
        )
        self.frames = []

    def write(self, value):
        if value != receiver.HELLO:
            self.frames.append(json.loads(value[4:]))
        super().write(value)


class TestPrivateApproval(unittest.TestCase):
    def test_nonce_and_plan_bound_frame_roundtrip(self):
        a = grant()
        p = plan(a)
        raw = report.approval_frame(p, a, NONCE)
        self.assertEqual(report.receive_approval(p, Pipe(raw), NONCE), a)
        self.assertNotIn("token", json.loads(raw[4:]))
        for other in ["b" * 64, "", True]:
            with self.assertRaises(ProviderConfigurationError):
                report.receive_approval(p, Pipe(raw), other)
        with self.assertRaises(ProviderConfigurationError):
            report.approval_frame(dataclasses.replace(p, company_id=uuid4()), a, NONCE)

    def test_invalid_shapes_duplicates_bounds_and_private_errors(self):
        a = grant()
        p = plan(a)
        valid = json.loads(report.approval_frame(p, a, NONCE)[4:])
        values = [
            None,
            [],
            {**valid, "v": True},
            {**valid, "extra": "synthetic-private-canary"},
            {**valid, "approval": {"private": "synthetic-private-canary"}},
            {**valid, "nonce": "b" * 64},
        ]
        raws = [json.dumps(v).encode() for v in values] + [b'{"v":1,"v":1}', b""]
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            for raw in raws:
                with self.assertRaises(ProviderConfigurationError) as error:
                    report.receive_approval(p, Pipe(len(raw).to_bytes(4, "big") + raw), NONCE)
                self.assertNotIn("canary", str(error.exception))
            with self.assertRaises(ProviderConfigurationError):
                report.receive_approval(p, Pipe((receiver.MAX_FRAME + 1).to_bytes(4, "big")), NONCE)
        self.assertEqual(output.getvalue(), "")

    def test_encoder_revalidates_model_copy_and_does_not_leak(self):
        a = grant()
        bad = a.model_copy(update={"posted_aud": "synthetic-private-canary"})
        with self.assertRaises(ProviderConfigurationError) as error:
            report.approval_frame(plan(a), bad, NONCE)
        self.assertNotIn("canary", str(error.exception))

    def test_reservation_revalidates_typed_model_copy_cost_proof(self):
        a = grant()
        for changes in [
            {"posted_aud": "100.00"},
            {"posted_aud": "synthetic-private-canary"},
            {"ledger_period": "2000-01"},
        ]:
            with self.assertRaises(ProviderConfigurationError) as error:
                report.Reservations(a.model_copy(update=changes), lambda: True, lambda: None)
            self.assertNotIn("canary", str(error.exception))

    def test_late_copied_thread_context_cannot_claim_after_request_exit(self):
        import contextvars

        a = grant()
        gate = report.Reservations(
            a,
            lambda: True,
            lambda: report.ReportState(
                a.settings_id,
                a.settings_digest,
                a.binding.company_id,
                a.binding.provider_profile,
                None,
                a.case_id,
                a.request_version_id,
                a.semantic_context_version,
                a.input_digest,
                a.expected_interpretation_id,
                a.expected_interpretation_digest,
                a.confirmed_contract_id,
                a.expected_interpretation_id,
                a.expected_interpretation_digest,
                a.confirmed_contract_digest,
            ),
        )
        with gate.operation(a.case_id, "REPORT_DESIGN"):
            late = contextvars.copy_context()
        with self.assertRaises(ProviderConfigurationError):
            late.run(gate.claim, a.binding.company_id, a.binding.provider_profile)
        self.assertEqual(gate.receipt()["attempts_consumed"], 0)
        # The unused slot remains available to a distinct active authorized request.
        with gate.operation(a.case_id, "REPORT_DESIGN"):
            gate.claim(a.binding.company_id, a.binding.provider_profile)
        self.assertEqual(gate.receipt()["attempts_consumed"], 1)

    def test_spent_slots_keep_read_resolution_but_cannot_dispatch_again(self):
        from test_runtime_draft import Tests as CoreTests

        a = grant()
        state = CoreTests().state(a)
        gate = report.Reservations(a, lambda: True, lambda: state)
        raw = Credentials(a)
        credentials = report.ReservedCredentials(raw, gate)
        with gate.operation(a.case_id, "REPORT_DESIGN"):
            credentials.resolve(a.binding.company_id, a.binding.provider_profile).credential()
        self.assertFalse(gate.ready())
        self.assertTrue(gate.connected())
        for _ in range(3):
            credentials.resolve(a.binding.company_id, a.binding.provider_profile)
        with (
            gate.operation(a.case_id, "REPORT_DESIGN"),
            self.assertRaises(ProviderConfigurationError),
        ):
            credentials.resolve(a.binding.company_id, a.binding.provider_profile).credential()
        self.assertEqual(raw.calls, 1)
        gate.close()
        self.assertFalse(gate.connected())

    def test_replayed_handshake_has_one_challenge_and_no_private_echo(self):
        raw = Pipe(b"account-bytes")
        wrapped = report._ApprovalChannel(raw, NONCE)
        self.assertEqual(
            receiver.exact(wrapped, len(receiver.HELLO), time.time() + 10), receiver.HELLO
        )
        wrapped.write(json.dumps(dict(v=1, nonce=NONCE, pid=1)).encode() + b"\n")
        self.assertEqual(raw.output, b"REPORT_APPROVAL_ACCEPTED\n")
        self.assertEqual(wrapped.read(7, time.time() + 10), b"account")
        wrapped.write(b"ACCOUNT_ACCEPTED\n")
        self.assertTrue(wrapped.connected(0.01))
        wrapped.close()
        self.assertTrue(raw.closed)
        for changed in [
            dict(v=True, nonce=NONCE, pid=1),
            dict(v=1, nonce=NONCE, pid=True),
            dict(v=1, nonce="b" * 64, pid=1),
        ]:
            with self.assertRaises(ProviderConfigurationError):
                report._ApprovalChannel(Pipe(b""), NONCE).write(json.dumps(changed).encode())

    def context(self):
        mp = pytest.MonkeyPatch()
        self.addCleanup(mp.undo)
        return setup(mp)

    def send(self, c, sdk, peer, grant_value, confirm=lambda *args: None):
        browser.run_handoff(
            c.plan,
            peer,
            credential_factory=lambda **kwargs: sdk,
            terminal_factory=terminal,
            confirm=confirm,
            hold=lambda: None,
            report_approval=grant_value,
        )

    def test_sender_approval_precedes_sdk_account_and_token(self):
        c = self.context()
        a = grant(c)
        sdk = Browser()
        peer = ReportPeer()
        phrases = []
        original = sdk.authenticate

        def authenticate(**kwargs):
            self.assertEqual(len(peer.frames), 1)
            self.assertIn("approval", peer.frames[0])
            return original(**kwargs)

        sdk.authenticate = authenticate
        self.send(c, sdk, peer, a, lambda *args: phrases.append(args[-1]))
        self.assertEqual(
            phrases,
            ["CONFIRM PRIVATE MEMORY HANDOFF", "CONFIRM ONE CASE REPORT", "CONFIRM ACCOUNT"],
        )
        self.assertEqual(len(peer.frames), 3)
        self.assertEqual([set(f) for f in peer.frames][0], {"v", "nonce", "approval"})
        self.assertTrue(sdk.closed and peer.closed)

    def test_runtime_flag_without_private_grant_cannot_authenticate(self):
        c = self.context()
        sdk = Browser()
        peer = ReportPeer()
        with self.assertRaises(receiver.HandoffError):
            self.send(c, sdk, peer, None)
        self.assertEqual(sdk.calls, [])
        self.assertEqual(peer.frames, [])
        self.assertTrue(peer.closed)

    def test_wrong_peer_or_ack_or_confirmation_fails_before_sdk(self):
        for fault in ["metadata_peer", "ack", "confirmation", "expired_model_copy"]:
            c = self.context()
            a = grant(c)
            sdk = Browser()
            peer = ReportPeer()
            if fault == "metadata_peer":
                peer.runtime = False
            elif fault == "ack":
                peer = ReportPeer(ack=b"NO")
            elif fault == "expired_model_copy":
                a = a.model_copy(
                    update={"binding": a.binding.model_copy(update={"authorization_deadline": 0})}
                )

            def confirmation(*args, fault=fault):
                if fault == "confirmation" and args[-1] == "CONFIRM ONE CASE REPORT":
                    raise RuntimeError("synthetic-private-canary")

            with self.assertRaises(receiver.HandoffError) as error:
                self.send(c, sdk, peer, a, confirmation)
            self.assertEqual(sdk.calls, [])
            self.assertTrue(peer.closed)
            self.assertNotIn("canary", str(error.exception))

    def test_different_approved_home_account_stops_before_token(self):
        c = self.context()
        a = grant(c)
        sdk = Browser()
        sdk.record.home_account_id = "different.account"
        peer = ReportPeer()
        with self.assertRaises(receiver.HandoffError):
            self.send(c, sdk, peer, a)
        self.assertEqual(sdk.calls, ["authenticate", "close"])
        self.assertEqual(len(peer.frames), 1)

    def test_bootstrap_invalid_private_frame_closes_before_data_or_serve(self):
        a = grant()
        p = plan(a)
        channel = Pipe(receiver.HELLO + b"\0\0\0\2{}")
        from apbra_api.config import Settings

        settings = Settings(
            _env_file=None,
            profile="test",
            database_url="sqlite://",
            session_secret=secrets.token_urlsafe(32),
        )

        def forbidden(*args):
            raise AssertionError("should not access stores or serve")

        with self.assertRaises(ProviderConfigurationError):
            report.run_private_report_receiver(
                p,
                channel,
                settings=settings,
                snapshot_loader=forbidden,
                state_loader_factory=forbidden,
                serve=forbidden,
            )
        self.assertTrue(channel.closed)

    def test_cleanup_disposes_database_even_when_channel_close_raises(self):
        from apbra_api import persistence

        a = grant()
        p = plan(a)
        from apbra_api.config import Settings

        settings = Settings(
            _env_file=None,
            profile="test",
            database_url="sqlite://",
            session_secret=secrets.token_urlsafe(32),
        )
        for runtime_fails in [False, True]:
            events = []

            class ClosingPipe(Pipe):
                def close(self, events=events):
                    events.append("close")
                    raise RuntimeError("synthetic-private-close-canary")

            channel = ClosingPipe(receiver.HELLO + report.approval_frame(p, a, NONCE))
            db = SimpleNamespace(
                engine=SimpleNamespace(dispose=lambda events=events: events.append("dispose"))
            )

            def runtime(*args, runtime_fails=runtime_fails, **kwargs):
                if runtime_fails:
                    raise RuntimeError("synthetic-private-runtime-canary")
                return {"status": "synthetic-receipt"}

            with (
                patch.object(report.secrets, "token_hex", return_value=NONCE),
                patch.object(persistence, "Database", return_value=db),
                patch.object(report, "run_report_receiver", runtime),
            ):
                with self.assertRaises(ProviderConfigurationError) as failure:
                    report.run_private_report_receiver(
                        p, channel, settings=settings, state_loader_factory=lambda _: lambda: None
                    )
            self.assertEqual(events, ["close", "dispose"])
            self.assertNotIn("canary", str(failure.exception))

    def test_plain_private_dictionary_frame_without_api_dependencies(self):
        a = grant()
        p = plan(a)
        value = a.model_dump(mode="json")
        raw, account = browser._private_report_frame(p, value, NONCE)
        self.assertEqual(account, a.binding.home_account_id)
        self.assertEqual(report.receive_approval(p, Pipe(raw), NONCE), a)
        # Framing conveys facts; the receiver is the budget authority.
        value["posted_aud"] = "99"
        raw, _ = browser._private_report_frame(p, value, NONCE)
        with self.assertRaises(ProviderConfigurationError):
            report.receive_approval(p, Pipe(raw), NONCE)

    def test_cli_runtime_routes_to_private_protocol_not_a_boolean_grant(self):
        a = grant()
        p = plan(a)
        captured = []
        argv = [
            "receiver",
            "--company-id",
            str(p.company_id),
            "--tenant-id",
            str(p.tenant_id),
            "--client-id",
            str(p.client_id),
            "--authorization-deadline",
            str(p.authorization_deadline),
            "--listen-host",
            receiver.CONTAINER_LISTEN,
            "--listen-port",
            "8000",
            "--published-port",
            "8001",
            "--runtime",
        ]
        with (
            patch.object(receiver.sys, "argv", argv),
            patch.object(receiver, "StdioChannel", lambda: object()),
            patch.object(
                receiver,
                "run_receiver",
                side_effect=AssertionError("must not use default boolean path"),
            ),
            patch.object(
                report,
                "run_private_report_receiver",
                lambda *args, **kwargs: captured.append((args, kwargs)),
            ),
        ):
            receiver.main()
        self.assertEqual(len(captured), 1)

    def test_parent_frames_run_the_private_receiver_and_reserved_lease(self):
        c = self.context()
        a = grant(c)
        sdk = Browser()
        peer = ReportPeer()
        self.send(c, sdk, peer, a)

        def encode(frame):
            raw = json.dumps(frame).encode()
            return len(raw).to_bytes(4, "big") + raw

        channel = Pipe(receiver.HELLO + b"".join(encode(f) for f in peer.frames))
        state = report.ReportState(
            a.settings_id,
            a.settings_digest,
            a.binding.company_id,
            a.binding.provider_profile,
            None,
            a.case_id,
            a.request_version_id,
            a.semantic_context_version,
            a.input_digest,
            a.expected_interpretation_id,
            a.expected_interpretation_digest,
            a.confirmed_contract_id,
            a.expected_interpretation_id,
            a.expected_interpretation_digest,
            a.confirmed_contract_digest,
        )
        from fastapi import FastAPI

        import apbra_api.api as api

        def app(**kwargs):
            value = FastAPI()
            value.state.credentials = kwargs["foundry_credentials"]
            return value

        held = []

        def serve(value, settings, stopped):
            self.assertTrue(sdk.closed)
            credentials = value.state.credentials
            held.append(credentials)
            self.assertTrue(credentials.ready(c.plan.company_id, c.profile))
            with credentials.reservations.operation(a.case_id, "REPORT_DESIGN"):
                token = credentials.resolve(c.plan.company_id, c.profile).credential()
                self.assertEqual(token.token, peer.frames[-1]["token"])

        def load_factory(parsed):
            self.assertEqual(parsed, a)
            return lambda: state

        settings = c.settings.model_copy(update={"profile": "development"})
        with (
            patch.object(report.secrets, "token_hex", return_value=NONCE),
            patch.object(api, "create_app", app),
        ):
            receipt = report.run_private_report_receiver(
                plan(a),
                channel,
                settings=settings,
                snapshot_loader=lambda: c.snapshot,
                state_loader_factory=load_factory,
                serve=serve,
            )
        self.assertEqual(receipt["attempts_consumed"], 1)
        self.assertTrue(channel.closed)
        self.assertFalse(held[0].ready(c.plan.company_id, c.profile))
        self.assertEqual(channel.output.count(b'"nonce"'), 1)
        self.assertEqual(channel.output.count(b"REPORT_APPROVAL_ACCEPTED"), 1)
        self.assertEqual(channel.output.count(b"ACCOUNT_ACCEPTED"), 1)
        self.assertNotIn(peer.frames[-1]["token"].encode(), channel.output)
