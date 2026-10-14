"""Private derivation with synthetic saved state and browser SDK only."""
import dataclasses
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_foundry_browser_handoff import Browser
from test_foundry_browser_metadata import setup, terminal
from test_foundry_cost_limits import estimate
from test_foundry_report_runtime import ReportPeer, grant

from apbra_api.foundry_browser_handoff import run_handoff
from apbra_api.foundry_memory_handoff import HandoffError
from apbra_api.foundry_private_preparation import Preparation, QualifiedAgentFacts, derive_approval
from apbra_api.foundry_report_runtime import ReportState
from apbra_api.model_provider import ProviderConfigurationError


def state_for(a):
    return ReportState(
        settings_id=a.settings_id, settings_digest=a.settings_digest,
        company_id=a.binding.company_id, profile=a.binding.provider_profile,
        secret_reference_id=None, case_id=a.case_id,
        request_version_id=a.request_version_id,
        semantic_context_version=a.semantic_context_version, input_digest=a.input_digest,
        interpretation_id=a.expected_interpretation_id,
        interpretation_digest=a.expected_interpretation_digest,
        confirmed_contract_id=a.confirmed_contract_id,
        confirmed_interpretation_id=a.expected_interpretation_id,
        confirmed_digest=a.expected_interpretation_digest,
        confirmed_contract_digest=a.confirmed_contract_digest,
    )


def prepare(a, **changes):
    record = SimpleNamespace(tenant_id=str(a.binding.tenant_id),
                             client_id=str(a.binding.client_id),
                             home_account_id=a.binding.home_account_id)
    return derive_approval(**{
        "state": state_for(a), "record": record, "qualified_agent": QualifiedAgentFacts(**{
            field.name: getattr(a.binding, field.name)
            for field in dataclasses.fields(QualifiedAgentFacts)
        }),
        "choices": (("REPORT_DESIGN", 1),), "estimates": (estimate(),),
        "posted_aud": "1.25", "unposted_exposure_aud": "0.50",
        "outstanding_reserves_aud": "0.25", "ledger_period": a.ledger_period, **changes,
    })


def test_saved_context_and_confirmation_derive_without_owner_hashes():
    a = grant()
    result = prepare(a)
    assert result.case_id == a.case_id
    assert result.settings_id == a.settings_id
    assert result.input_digest == a.input_digest
    assert result.confirmed_contract_digest == a.confirmed_contract_digest
    assert result.confirmation_mode == "CONFIRMED"
    assert result.chain_reserve_aud == "0.36"
    assert result.authorization_id != a.authorization_id


@pytest.mark.parametrize("field", ["company_id", "secret_reference_id"])
def test_foreign_tenant_or_key_bound_state_cannot_be_reinterpreted(field):
    a = grant()
    with pytest.raises(ProviderConfigurationError):
        prepare(a, state=dataclasses.replace(state_for(a), **{field: uuid4()}))


def test_foreign_sdk_account_and_existing_confirmation_drift_stop():
    a = grant()
    record = SimpleNamespace(tenant_id=str(a.binding.tenant_id),
                             client_id=str(uuid4()), home_account_id="foreign.account")
    with pytest.raises(ProviderConfigurationError):
        prepare(a, record=record)
    with pytest.raises(ProviderConfigurationError):
        prepare(a, state=dataclasses.replace(state_for(a), confirmed_digest="9" * 64))


def test_no_authentication_when_nonpaid_readiness_fails(monkeypatch):
    c = setup(monkeypatch)
    peer = ReportPeer()
    created = []
    def stop():
        raise ValueError("synthetic-private-detail")
    with pytest.raises(HandoffError):
        run_handoff(c.plan, peer, preparation=Preparation(stop, lambda *_: None),
                    credential_factory=lambda **_: created.append(True), terminal_factory=terminal)
    assert created == [] and peer.closed


def test_derived_grant_follows_account_confirmation_before_token(monkeypatch, capsys):
    c = setup(monkeypatch)
    sdk, peer = Browser(), ReportPeer()
    events = []
    def qualify(record, credential):
        assert credential is sdk and sdk.calls == ["authenticate"]
        assert len(peer.frames) == 0 and events[-1] == "YES"
        events.append("qualified")
        return prepare(grant(c), record=record)
    run_handoff(c.plan, peer, preparation=Preparation(lambda: events.append("preflight"), qualify),
                credential_factory=lambda **_: sdk, terminal_factory=terminal,
                confirm=lambda *args: events.append(args[-1]), hold=lambda: None)
    assert events == ["preflight", "YES", "YES", "YES", "qualified", "YES"]
    assert len(peer.frames) == 3 and sdk.closed and peer.closed
    assert peer.frames[0]["approval"]["binding"]["home_account_id"] == sdk.record.home_account_id
    assert capsys.readouterr().out == ""



def test_absent_optional_agent_version_is_not_replaced_with_historical_default():
    a=grant()
    binding=a.binding.model_copy(update={"agent_version":None})
    a=a.model_copy(update={"binding":binding})
    result=prepare(a)
    assert result.binding.agent_version is None
    assert result.binding.provider_profile == a.binding.provider_profile


def test_preparation_prompt_states_saved_retry_allowance_without_changing_policy(monkeypatch):
    c = setup(monkeypatch)
    sdk = Browser()
    peer = ReportPeer()
    messages=[]
    run_handoff(c.plan,peer,
        preparation=Preparation(
            lambda: None, lambda record, credential: prepare(grant(c), record=record)
        ),
        credential_factory=lambda **_:sdk,terminal_factory=terminal,
        confirm=lambda terminal,plan,message,phrase:messages.append(message),hold=lambda:None)
    assert any("Saved retry allowance: 0" in message for message in messages)
    assert any("not an Azure hard cap" in message for message in messages)
    assert not any("no automatic retry" in message for message in messages)
