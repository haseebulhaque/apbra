"""Offline private receipt, spend and host/receiver boundary checks. No real SDK or provider."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier, Thread
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from cryptography.exceptions import InvalidSignature
from test_foundry_memory_handoff import NONCE, Pipe, account_frame, frame
from test_foundry_v10_report_transport import FILE, REPORT_BYTES, Scenario

from apbra_api import foundry_memory_handoff as memory
from apbra_api.foundry_browser_handoff import run_handoff
from apbra_api.foundry_v10_demo_receiver import (
    V10DemoCase,
    V10DemoGrant,
    V10DemoHost,
    V10DemoReceiver,
    V10PrivatePeer,
)
from apbra_api.model_provider import ProviderCallError


def grant_for(case, *, deadline=None, tenant=None, client=None):
    return V10DemoGrant(
        case=case,
        tenant_id=tenant or uuid4(),
        client_id=client or uuid4(),
        home_account_id="synthetic.account",
        period=datetime.now(UTC).strftime("%Y-%m"),
        expires=deadline or time.time() + 120,
        posted_aud="0.12",
        unposted_aud="0.03",
        outstanding_aud="0.04",
        ceiling_aud="2",
        analysis_reserve_aud="0.10",
        report_reserve_aud="0.5",
        runtime_evidence_sha256="1" * 64,
        rights_evidence_sha256="2" * 64,
        analysis_bound_sha256="3" * 64,
        report_bound_sha256="4" * 64,
    )


def bind(scenario):
    op = scenario.operation
    case = V10DemoCase(
        company_id=op.scope.company_id,
        case_id=op.scope.case_id,
        actor_id=uuid4(),
        membership_id=uuid4(),
        session_id=uuid4(),
        settings_id=uuid4(),
        settings_digest="a" * 64,
        source_id=op.source_id,
        request_version_id=op.request_version_id,
        source_digest=op.source_digest,
        profile_sha256=op.profile_sha256,
        project_url=op.project_url,
        agent_name=op.agent_name,
        goal=op.goal,
        knowledge_binding=op.knowledge_binding,
        knowledge_scope=op.knowledge_scope,
    )
    identity = {
        k: getattr(case, k)
        for k in ("actor_id", "session_id", "membership_id", "settings_id", "settings_digest")
    }
    return grant_for(case), identity


def receiver(s, grant, **kwargs):
    defaults = dict(
        host_current=lambda: True,
        authorize_stage=lambda op: True,
        exclusive_writer=lambda op, rid, ref: True,
        transport=s.service,
    )
    return V10DemoReceiver(grant, s.send_access, s.read_access, **(defaults | kwargs))


@pytest.mark.parametrize("purpose", ["REQUIREMENT_ANALYSIS", "FULL_REPORT_ARTIFACT"])
def test_explicit_receiver_uses_real_transport_and_distinct_private_stages(tmp_path, purpose):
    s = Scenario(tmp_path, purpose)
    grant, identity = bind(s)
    stage = Mock(return_value=True)
    origin = Mock(return_value=True)
    r = receiver(s, grant, authorize_stage=stage, exclusive_writer=origin)
    assert r.connection_id("FULL_REPORT_ARTIFACT") != r.connection_id("REQUIREMENT_ANALYSIS")
    assert r.qualification == "OFFLINE_FIXTURE"
    assert r.permits(s.operation, **identity)
    claimed = Mock(return_value=True)
    ex = r.open(s.operation, **identity, current=lambda: True, claim=claimed)
    assert not stage.called and not claimed.called and not s.requests
    result = ex.send(s.profile, s.request, archive=s.archive)
    assert result.provider_status == "completed"
    assert not r.permits(s.operation, **identity)
    stage.assert_called_once_with(s.operation)
    claimed.assert_called_once()
    if purpose == "FULL_REPORT_ARTIFACT":
        original = ex.read_report(s.profile, archive=s.archive, receipt_id=result.receipt.id)
        assert original.content == REPORT_BYTES and original.reference == FILE
        assert original.response_id == "resp_demo" and original.receipt_id == result.receipt.id
        assert all(call.args == (s.operation, "resp_demo", FILE) for call in origin.call_args_list)
        assert origin.called
    else:
        with pytest.raises(ProviderCallError):
            ex.read_report(s.profile, archive=s.archive, receipt_id=result.receipt.id)
        assert not origin.called
    r.close()
    assert not ex.current()
    with pytest.raises(ProviderCallError):
        ex.read_report(s.profile, archive=s.archive, receipt_id=result.receipt.id)


def test_exact_case_identity_and_lease_readiness_precede_dispatch(tmp_path):
    s = Scenario(tmp_path)
    grant, identity = bind(s)
    r = receiver(s, grant)
    assert r.allowed_in("test") and not r.allowed_in("development")
    for field in identity:
        wrong = identity | {field: "b" * 64 if field.endswith("digest") else uuid4()}
        assert not r.permits(s.operation, **wrong)
    for wrong in (
        replace(s.operation, source_digest="b" * 64),
        replace(s.operation, request_version_id=uuid4()),
        replace(s.operation, source_id=uuid4()),
        replace(s.operation, goal="other"),
        replace(s.operation, scope=replace(s.scope, case_id=uuid4())),
        replace(s.operation, scope=replace(s.scope, company_id=uuid4())),
        replace(s.operation, knowledge_binding="other"),
        replace(s.operation, agent_name="v7"),
    ):
        with pytest.raises(ProviderCallError):
            r.open(wrong, **identity, current=lambda: True, claim=lambda: True)
    for invalid in (
        {"period": "1999-12"},
        {"expires": time.time() - 1},
        {"ceiling_aud": "0.18"},
        {"expires": time.time() + 86400 * 32},
        {"analysis_reserve_aud": "0"},
        {"report_reserve_aud": "0"},
        {"report_reserve_aud": "NaN"},
    ):
        with pytest.raises((ProviderCallError, ValueError)):
            receiver(s, grant.model_copy(update=invalid))
    with pytest.raises(ProviderCallError):
        receiver(s, grant, transport=None)
    with pytest.raises(ProviderCallError):
        receiver(s, grant, transport=httpx.HTTPTransport())
    foreign = grant.model_copy(
        update={"case": grant.case.model_copy(update={"source_digest": "f" * 64})}
    )
    with pytest.raises(ProviderCallError):
        V10DemoReceiver(
            foreign,
            replace(s.send_access, qualification="LIVE_METADATA_VERIFIED"),
            replace(s.read_access, qualification="LIVE_METADATA_VERIFIED"),
            host_current=lambda: True,
            authorize_stage=lambda op: True,
            exclusive_writer=lambda op, rid, ref: True,
        )
    with pytest.raises(memory.HandoffError):
        V10DemoHost(Mock(), Mock(), Mock()).send_grant(Pipe(b""), NONCE, foreign)
    assert not s.requests and not s.send_bearer.called


def test_parallel_exchanges_can_only_spend_one_slot_and_uncertain_claim_sticks(tmp_path):
    s = Scenario(tmp_path)
    grant, identity = bind(s)
    authorize = Mock(return_value=False)
    r = receiver(s, grant, authorize_stage=authorize)
    db_claim = Mock(return_value=True)
    start = Barrier(2)
    exchanges = [
        r.open(s.operation, **identity, current=lambda: True, claim=db_claim) for _ in range(2)
    ]
    failures = []

    def worker(ex):
        start.wait()
        try:
            ex.send(s.profile, s.request, archive=s.archive)
        except ProviderCallError as error:
            failures.append(error.code)

    threads = [Thread(target=worker, args=(exchange,)) for exchange in exchanges]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert failures == ["V10_DISPATCH_CONSUMED"] * 2
    assert not s.requests and db_claim.call_count == authorize.call_count == 1
    # A new process also consults the already committed durable case/stage record.
    new = receiver(s, grant)
    ex = new.open(s.operation, **identity, current=lambda: True, claim=lambda: False)
    with pytest.raises(ProviderCallError):
        ex.send(s.profile, s.request, archive=s.archive)
    assert not s.requests


def test_independent_origin_and_revocation_precede_all_file_access(tmp_path):
    s = Scenario(tmp_path)
    grant, identity = bind(s)
    current = Mock(return_value=True)
    origin = Mock(return_value=False)
    r = receiver(s, grant, host_current=current, exclusive_writer=origin)
    ex = r.open(s.operation, **identity, current=lambda: True, claim=lambda: True)
    received = ex.send(s.profile, s.request, archive=s.archive)
    for receipt in (uuid4(), received.receipt.id):
        with pytest.raises(ProviderCallError):
            ex.read_report(s.profile, archive=s.archive, receipt_id=receipt)
    origin.assert_called_once_with(s.operation, "resp_demo", FILE)
    origin.return_value = True
    current.return_value = False
    with pytest.raises(ProviderCallError):
        ex.read_report(s.profile, archive=s.archive, receipt_id=received.receipt.id)
    assert len(s.requests) == 1 and not s.read_bearer.called


def test_signed_grant_is_nonce_account_and_exact_owned_key_bound(tmp_path):
    s = Scenario(tmp_path)
    grant, _ = bind(s)
    host = V10DemoHost(lambda: None, lambda account, sdk: grant, lambda g, q: None)
    plan = memory.HandoffPlan(
        grant.case.company_id, grant.tenant_id, grant.client_id, grant.expires
    )
    sent = Pipe(b"")
    host.send_grant(sent, NONCE, grant)
    wire = bytes(sent.output)
    peer = V10PrivatePeer(Pipe(wire), host.verification_key, plan)
    assert peer.receive_grant(NONCE) == grant
    with pytest.raises(memory.HandoffError):
        peer.receive_grant(NONCE)
    with pytest.raises(memory.HandoffError):
        V10PrivatePeer(Pipe(wire), host.verification_key, plan).receive_grant("9" * 64)
    with pytest.raises(InvalidSignature):
        other = V10DemoHost(host.preflight, host.qualify, host.attest)
        V10PrivatePeer(Pipe(wire), other.verification_key, plan).receive_grant(NONCE)
    envelope = json.loads(wire[4:])
    envelope["payload"]["grant"]["case"]["actor_id"] = str(uuid4())
    raw = json.dumps(envelope).encode()
    with pytest.raises(InvalidSignature):
        V10PrivatePeer(
            Pipe(len(raw).to_bytes(4, "big") + raw), host.verification_key, plan
        ).receive_grant(NONCE)
    # A peer without the selected holder of the private key cannot issue unsigned authority.
    with pytest.raises(memory.HandoffError):
        raw = json.dumps(envelope["payload"]).encode()
        V10PrivatePeer(
            Pipe(len(raw).to_bytes(4, "big") + raw), host.verification_key, plan
        ).receive_grant(NONCE)


def test_handoff_rejects_mixed_or_unmatched_peer_before_authentication(tmp_path):
    s = Scenario(tmp_path)
    grant, _ = bind(s)
    plan = memory.HandoffPlan(
        grant.case.company_id, grant.tenant_id, grant.client_id, grant.expires
    )
    host = V10DemoHost(Mock(), Mock(), Mock())
    fake = Mock(runtime=False, v10_public_verifier="0" * 64)
    constructor = Mock()
    with pytest.raises(memory.HandoffError):
        run_handoff(plan, fake, credential_factory=constructor, v10_host=host)
    assert not host.preflight.called and not constructor.called


def test_owned_browser_and_pid1_compose_only_case_bound_capabilities(tmp_path, monkeypatch):
    from test_foundry_browser_handoff import Browser
    from test_foundry_browser_metadata import CLIENT, TENANT, setup, terminal

    s = Scenario(tmp_path)
    base, identity = bind(s)
    grant = grant_for(base.case, tenant=TENANT, client=CLIENT)
    plan = memory.HandoffPlan(grant.case.company_id, TENANT, CLIENT, grant.expires)
    # The host approves from the exact authenticated SDK record. The in-memory
    # wire below is the normal private protocol, with a synthetic browser account.
    sdk = Browser()
    qualify = Mock(return_value=grant)
    host = V10DemoHost(Mock(), qualify, Mock())
    challenge = dict(memory.handoff_challenge(NONCE), v10_public_verifier=host.verification_key)
    peer = Pipe(
        json.dumps(challenge).encode()
        + b"\nV10_DEMO_GRANT_ACCEPTED\nACCOUNT_ACCEPTED\n"
        + b"HANDOFF_READY_INVOCATION_GATED\n"
    )
    peer.v10_public_verifier = host.verification_key
    peer.runtime = False
    peer.attach = Mock()
    peer.check = Mock()
    monkeypatch.setattr(V10DemoHost, "serve_proofs", lambda *_: None)
    consent = Mock()
    run_handoff(
        plan,
        peer,
        v10_host=host,
        credential_factory=lambda **kw: sdk,
        terminal_factory=terminal,
        confirm=consent,
    )
    qualify.assert_called_once_with(sdk.record, sdk)
    assert sdk.closed and sdk.calls == ["authenticate", "get_token", "close"]
    assert any(call.args[-1] == "CONFIRM TWO CASE OPPORTUNITIES" for call in consent.call_args_list)
    c = setup(monkeypatch)
    config = c.settings.model_copy(
        update={
            "automatic_generation_enabled": False,
            "bootstrap_enabled": False,
            "qualified_provider_profiles_json": json.dumps([s.profile.model_dump(mode="json")]),
        }
    )
    policy = c.snapshot.settings.model_copy(update={"provider_profile": s.profile})
    snapshot = replace(
        c.snapshot,
        company_id=grant.case.company_id,
        id=grant.case.settings_id,
        digest=grant.case.settings_digest,
        settings=policy,
    )
    captured = []
    monkeypatch.setattr(memory, "create_app", lambda **kw: kw)

    def inspect_app(app, settings, stopped):
        assert not stopped.is_set()
        assert app["foundry_credentials"] is app["foundry_metadata_credentials"] is None
        private = app["v10_demo_receiver"]
        assert private.qualification == "LIVE_METADATA_VERIFIED" and private.allowed_in(
            "development"
        )
        assert not private.allowed_in("staging") and private.permits(s.operation, **identity)
        captured.append(private)

    transcript = bytes(peer.output)
    channel = Pipe(transcript)
    memory.run_receiver(
        plan,
        channel,
        settings=config,
        snapshot_loader=lambda: snapshot,
        serve=inspect_app,
        nonce_factory=lambda: NONCE,
        v10_public_verifier=host.verification_key,
    )
    assert channel.closed and b"V10_DEMO_GRANT_ACCEPTED\n" in channel.output
    assert captured and not captured[0].permits(s.operation, **identity)
    for altered in (
        transcript.replace(b"synthetic.account", b"synthetic.changed", 1),
        memory.HELLO + account_frame(plan) + frame(plan),
    ):
        with pytest.raises(memory.HandoffError):
            memory.run_receiver(
                plan,
                Pipe(altered),
                settings=config,
                snapshot_loader=lambda: snapshot,
                serve=lambda *_: pytest.fail("invalid grant started app"),
                nonce_factory=lambda: NONCE,
                v10_public_verifier=host.verification_key,
            )


def test_live_grant_needs_fresh_signed_independent_evidence_each_time(tmp_path):
    import io

    from apbra_api.foundry_v10_demo_receiver import V10DemoQuestion

    s = Scenario(tmp_path)
    grant, _ = bind(s)
    plan = memory.HandoffPlan(
        grant.case.company_id, grant.tenant_id, grant.client_id, grant.expires
    )
    host = V10DemoHost(lambda: None, lambda account, sdk: grant, lambda g, q: "f" * 64)
    outgoing = Pipe(b"")
    lease = host.send_grant(outgoing, NONCE, grant)

    class Loop(Pipe):
        previous = None
        replay = False
        questions = []

        def write(self, raw):
            question = V10DemoQuestion.model_validate_json(raw[4:])
            self.questions.append(question)
            if self.replay:
                self.value = io.BytesIO(self.previous)
                return
            signed = host._sign(
                {"question": question.model_dump(mode="json"), "evidence_sha256": "c" * 64}
            )
            reply = json.dumps(signed).encode()
            self.previous = len(reply).to_bytes(4, "big") + reply
            self.value = io.BytesIO(self.previous)

    channel = Loop(bytes(outgoing.output))
    peer = V10PrivatePeer(channel, host.verification_key, plan)
    peer.receive_grant(NONCE)
    assert peer.authorize_stage(s.operation)
    assert peer.exclusive_writer(s.operation, "resp_demo", FILE)
    assert channel.questions[0].nonce != channel.questions[1].nonce
    assert channel.questions[1].lease == lease and channel.questions[1].file_id == FILE.file_id
    channel.replay = True
    assert not peer.exclusive_writer(s.operation, "resp_demo", FILE)

    class EndOfTest(Exception):
        pass

    class HostRequests(Pipe):
        def connected(self, timeout):
            if self.value.tell() == len(self.value.getvalue()):
                raise EndOfTest
            return False

    def frames(questions):
        result = []
        for q in questions:
            raw = q.model_dump_json().encode()
            result.append(len(raw).to_bytes(4, "big") + raw)
        return b"".join(result)

    stage, writer = channel.questions[:2]
    incoming = HostRequests(frames([stage, writer]))
    with pytest.raises(EndOfTest):
        host.serve_proofs(incoming, grant, lease)
    assert bytes(incoming.output).count(b'"signature"') == 2
    for pair in (
        [writer],
        [stage, stage],
        [stage, writer.model_copy(update={"operation_id": uuid4()})],
    ):
        with pytest.raises(memory.HandoffError):
            host.serve_proofs(HostRequests(frames(pair)), grant, lease)
