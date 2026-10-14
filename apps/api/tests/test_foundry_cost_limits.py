"""Synthetic limits: no network, pricing lookup or credentials."""

import json

import httpx
import pytest
from pydantic import ValidationError
from test_model_provider import foundry_adapter, foundry_profile, request, responses_payload

from apbra_api.foundry_cost_limits import (
    AttemptEstimate,
    FoundryCostLimits,
    QualifiedMcpControls,
    limit_readiness,
    provider_identity_digest,
)
from apbra_api.model_provider import ProviderCallError


@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "1"])
def test_limits_are_explicit_positive_integers(value):
    with pytest.raises(ValidationError):
        FoundryCostLimits(max_mcp_calls=value)


def test_absent_limits_preserve_historical_profile_encoding():
    assert "foundry_cost_limits" not in foundry_profile().model_dump(mode="json")
    assert limit_readiness(None) == {
        "configured": None,
        "warnings": [],
        "qualifiesInvocation": False,
    }


def test_wire_builtin_limit_is_distinct_from_mcp_and_no_tool_override():
    wires = []
    adapter = foundry_adapter(
        lambda wire: wires.append(json.loads(wire.content))
        or httpx.Response(200, json=responses_payload()),
        profile_overrides={"foundry_cost_limits": {"max_builtin_tool_calls": 1}},
    )
    adapter.structured(request())
    assert wires[0]["max_tool_calls"] == 1
    assert not {"tools", "model", "instructions"} & wires[0].keys()
    assert wires[0]["store"] is False


@pytest.mark.parametrize("key", ["max_mcp_calls", "max_retrieval_output_tokens"])
def test_unqualified_remote_cap_stops_before_credential_and_dispatch(key):
    acquired, wires = [], []
    adapter = foundry_adapter(
        lambda wire: wires.append(wire) or httpx.Response(200),
        credential=lambda: acquired.append(True),
        profile_overrides={"foundry_cost_limits": {key: 1}},
    )
    with pytest.raises(ProviderCallError, match="MODEL_MCP_COST_CONTROL_UNQUALIFIED") as caught:
        adapter.structured(request())
    assert caught.value.observation.call_count == 0
    assert acquired == wires == []
    assert limit_readiness(adapter.profile.foundry_cost_limits)["qualifiesInvocation"] is False


def test_provider_request_limit_caps_transient_retry_exposure():
    wires = []
    adapter = foundry_adapter(
        lambda wire: wires.append(wire) or httpx.Response(503),
        profile_overrides={
            "retry_limit": 1,
            "max_calls_per_operation": 2,
            "foundry_cost_limits": {"max_provider_requests": 1},
        },
    )
    with pytest.raises(ProviderCallError) as caught:
        adapter.structured(request())
    assert len(wires) == caught.value.observation.call_count == 1


def estimate(**changes):
    return AttemptEstimate(
        **{
            "model_input_token_ceiling": 1000,
            "model_output_token_ceiling": 128,
            "model_turn_ceiling": 2,
            "input_aud_per_token": "0.0001",
            "output_aud_per_token": "0.0002",
            "other_billable_work_aud": "0.10",
            "rate_provenance": "synthetic-qualified-rates",
            "enforcement_provenance": "synthetic-service-and-retrieval-bounds",
            **changes,
        }
    )


def test_conservative_rounding_and_provenance_change_reservation_binding():
    amount, digest = estimate().reserve()
    assert amount == "0.36"
    assert estimate(rate_provenance="synthetic-next-revision").reserve()[1] != digest
    with pytest.raises(ValidationError):
        estimate(other_billable_work_aud=None)


def qualified_mcp(**changes):
    return QualifiedMcpControls(
        **{
            "configuration_id": foundry_profile().configuration_id,
            "provider_identity_digest": provider_identity_digest(foundry_profile()),
            "agent_version": "6",
            "knowledge_binding": "synthetic-shared-standards",
            "server_label": "synthetic-kb",
            "tool_name": "knowledge_base_retrieve",
            "approval_policy": "always",
            "stateless_continuation_qualified": True,
            "enforcement_provenance": "synthetic-selected-agent-schema",
            **changes,
        }
    )


def approval(identity="approval-1", **changes):
    return {
        "type": "mcp_approval_request",
        "id": identity,
        "server_label": "synthetic-kb",
        "name": "knowledge_base_retrieve",
        "arguments": '{"maxOutputSize":32}',
        **changes,
    }


def output(*items):
    return {
        "status": "completed",
        "output": list(items),
        "usage": {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
    }


def completed_retrieval(identity="approval-1"):
    return {
        "type": "mcp_call",
        "id": "call-1",
        "server_label": "synthetic-kb",
        "name": "knowledge_base_retrieve",
        "approval_request_id": identity,
        "status": "completed",
        "output": '{"content": []}',
    }


def mcp_adapter(handler, *, limits=None, proof=None, **profile):
    return foundry_adapter(
        handler,
        mcp_controls=proof or qualified_mcp(),
        profile_overrides={
            "max_calls_per_operation": 2,
            "retry_limit": 0,
            "foundry_cost_limits": limits or {"max_mcp_calls": 1},
            **profile,
        },
    )


def test_stateless_approval_continuation_is_a_reserved_call_not_a_retry():
    wires = []

    def handler(wire):
        wires.append(json.loads(wire.content))
        if len(wires) == 1:
            return httpx.Response(200, json=output(approval()))
        final = responses_payload()
        final["output"].insert(0, completed_retrieval())
        return httpx.Response(200, json=final)

    result = mcp_adapter(handler).structured(request())
    assert result.call_count == len(wires) == 2
    assert wires[1]["input"][-1] == {
        "type": "mcp_approval_response",
        "approval_request_id": "approval-1",
        "approve": True,
    }
    assert wires[1]["input"][0] == wires[0]["input"][0]
    assert all(wire["store"] is False for wire in wires)
    assert all(
        not {"tools", "model", "instructions", "previous_response_id", "conversation"} & wire.keys()
        for wire in wires
    )
    assert result.usage["prompt_tokens"] == 8


@pytest.mark.parametrize(
    "items,code",
    [
        ([approval(), approval("approval-2")], "MODEL_MCP_CALL_BUDGET_EXCEEDED"),
        ([approval(), approval()], "MODEL_MCP_APPROVAL_REPLAY"),
        ([approval(server_label="foreign")], "MODEL_MCP_UNQUALIFIED_TOOL"),
        ([approval(name="other-tool")], "MODEL_MCP_UNQUALIFIED_TOOL"),
        ([completed_retrieval()], "MODEL_MCP_APPROVAL_POLICY_VIOLATION"),
        ([{"type": "file_search_call"}], "MODEL_MCP_UNQUALIFIED_TOOL"),
    ],
)
def test_unapproved_parallel_foreign_or_replayed_calls_never_receive_approval(items, code):
    wires = []
    adapter = mcp_adapter(
        lambda wire: wires.append(wire) or httpx.Response(200, json=output(*items))
    )
    with pytest.raises(ProviderCallError, match=code) as caught:
        adapter.structured(request())
    assert caught.value.observation.call_count == len(wires) == 1


@pytest.mark.parametrize(
    "arguments", ["{}", '{"maxOutputSize":true}', '{"maxOutputSize":33}', '{"maxOutputSize":0}']
)
def test_actual_qualified_retrieval_argument_is_checked_before_approval(arguments):
    wires = []
    adapter = mcp_adapter(
        lambda wire: wires.append(wire)
        or httpx.Response(200, json=output(approval(arguments=arguments))),
        limits={"max_mcp_calls": 1, "max_retrieval_output_tokens": 32},
        proof=qualified_mcp(retrieval_argument_path=("maxOutputSize",)),
    )
    with pytest.raises(ProviderCallError, match="MODEL_MCP_RETRIEVAL_BUDGET_UNQUALIFIED"):
        adapter.structured(request())
    assert len(wires) == 1


def test_provider_dispatch_ceiling_stops_before_approval_followup():
    wires = []
    adapter = mcp_adapter(
        lambda wire: wires.append(wire) or httpx.Response(200, json=output(approval())),
        limits={"max_mcp_calls": 1, "max_provider_requests": 1},
    )
    with pytest.raises(ProviderCallError, match="MODEL_PROVIDER_REQUEST_BUDGET_EXCEEDED") as caught:
        adapter.structured(request())
    assert caught.value.observation.call_count == len(wires) == 1


@pytest.mark.parametrize("failure", [503, "timeout"])
def test_uncertain_approved_tool_dispatch_is_never_retried(failure):
    wires = []

    def handler(wire):
        wires.append(wire)
        if len(wires) == 1:
            return httpx.Response(200, json=output(approval()))
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic", request=wire)
        return httpx.Response(failure)

    adapter = mcp_adapter(handler, max_calls_per_operation=3, retry_limit=2)
    with pytest.raises(ProviderCallError) as caught:
        adapter.structured(request())
    assert caught.value.observation.call_count == len(wires) == 2
    assert caught.value.observation.usage["prompt_tokens"] is None
    assert caught.value.observation.usage["observed_prompt_tokens"] == 3


def test_foreign_qualification_fails_before_any_credential_or_dispatch():
    wires = []
    adapter = mcp_adapter(
        lambda wire: wires.append(wire) or httpx.Response(200),
        proof=qualified_mcp(agent_version="foreign"),
    )
    with pytest.raises(ProviderCallError, match="MODEL_MCP_COST_CONTROL_UNQUALIFIED") as caught:
        adapter.structured(request())
    assert caught.value.observation.call_count == 0
    assert wires == []


def test_qualified_retrieval_limit_approves_the_original_arguments_without_rewriting():
    wires = []

    def handler(wire):
        wires.append(json.loads(wire.content))
        if len(wires) == 1:
            return httpx.Response(200, json=output(approval()))
        final = responses_payload()
        final["output"].insert(0, completed_retrieval())
        return httpx.Response(200, json=final)

    mcp_adapter(
        handler,
        limits={"max_mcp_calls": 1, "max_retrieval_output_tokens": 32},
        proof=qualified_mcp(retrieval_argument_path=("maxOutputSize",)),
    ).structured(request())
    assert wires[1]["input"][1]["arguments"] == '{"maxOutputSize":32}'
    assert wires[1]["input"][-1]["approve"] is True


def test_duplicate_retrieval_cap_arguments_stop_before_approval():
    wires = []
    adapter = mcp_adapter(
        lambda wire: wires.append(wire)
        or httpx.Response(
            200, json=output(approval(arguments='{"maxOutputSize":1000,"maxOutputSize":32}'))
        ),
        limits={"max_mcp_calls": 1, "max_retrieval_output_tokens": 32},
        proof=qualified_mcp(retrieval_argument_path=("maxOutputSize",)),
    )
    with pytest.raises(ProviderCallError, match="MODEL_MCP_RETRIEVAL_BUDGET_UNQUALIFIED"):
        adapter.structured(request())
    assert len(wires) == 1


@pytest.mark.parametrize(
    "proof",
    [
        qualified_mcp(retrieval_argument_path=None),
        qualified_mcp().model_copy(update={"approval_policy": "never"}),
        qualified_mcp().model_copy(update={"stateless_continuation_qualified": False}),
    ],
)
def test_unknown_retrieval_schema_or_unqualified_policy_stops_before_paid_dispatch(proof):
    wires = []
    adapter = mcp_adapter(
        lambda wire: wires.append(wire) or httpx.Response(200),
        limits={"max_mcp_calls": 1, "max_retrieval_output_tokens": 32},
        proof=proof,
    )
    with pytest.raises(ProviderCallError, match="MODEL_MCP_COST_CONTROL_UNQUALIFIED") as caught:
        adapter.structured(request())
    assert caught.value.observation.call_count == 0
    assert wires == []


def test_same_configuration_id_cannot_reuse_proof_for_another_endpoint():
    wires = []
    adapter = mcp_adapter(lambda wire: wires.append(wire) or httpx.Response(200))
    adapter.profile = adapter.profile.model_copy(update={
        "endpoint": "https://other.invalid/api/projects/project/agents/agent/endpoint/protocols/openai/responses",
    })
    with pytest.raises(ProviderCallError, match="MODEL_MCP_COST_CONTROL_UNQUALIFIED") as caught:
        adapter.structured(request())
    assert caught.value.observation.call_count == 0
    assert wires == []


def test_private_token_host_propagates_qualification_without_acquiring_a_token():
    from test_model_provider import token_credential_host

    proof = qualified_mcp()
    host, credential, company, profile, activation = token_credential_host(mcp_controls=proof)
    activation["enabled"] = True
    assert host.resolve(company, profile).mcp_controls == proof
    assert credential.scopes == []
