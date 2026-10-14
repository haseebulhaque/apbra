"""Synthetic limits: no network, pricing lookup or credentials."""
import json

import httpx
import pytest
from pydantic import ValidationError
from test_model_provider import foundry_adapter, foundry_profile, request, responses_payload

from apbra_api.foundry_cost_limits import AttemptEstimate, FoundryCostLimits, limit_readiness
from apbra_api.model_provider import ProviderCallError


@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "1"])
def test_limits_are_explicit_positive_integers(value):
    with pytest.raises(ValidationError):
        FoundryCostLimits(max_mcp_calls=value)


def test_absent_limits_preserve_historical_profile_encoding():
    assert "foundry_cost_limits" not in foundry_profile().model_dump(mode="json")
    assert limit_readiness(None) == {
        "configured": None, "warnings": [], "qualifiesInvocation": False,
    }


def test_wire_builtin_limit_is_distinct_from_mcp_and_no_tool_override():
    wires = []
    adapter = foundry_adapter(
        lambda wire: wires.append(json.loads(wire.content)) or httpx.Response(
            200, json=responses_payload()
        ), profile_overrides={"foundry_cost_limits": {"max_builtin_tool_calls": 1}},
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
        profile_overrides={"retry_limit": 1, "max_calls_per_operation": 2,
                           "foundry_cost_limits": {"max_provider_requests": 1}},
    )
    with pytest.raises(ProviderCallError) as caught:
        adapter.structured(request())
    assert len(wires) == caught.value.observation.call_count == 1


def estimate(**changes):
    return AttemptEstimate(**{
        "model_input_token_ceiling": 1000, "model_output_token_ceiling": 128,
        "model_turn_ceiling": 2, "input_aud_per_token": "0.0001",
        "output_aud_per_token": "0.0002", "other_billable_work_aud": "0.10",
        "rate_provenance": "synthetic-qualified-rates",
        "enforcement_provenance": "synthetic-service-and-retrieval-bounds", **changes,
    })


def test_conservative_rounding_and_provenance_change_reservation_binding():
    amount, digest = estimate().reserve()
    assert amount == "0.36"
    assert estimate(rate_provenance="synthetic-next-revision").reserve()[1] != digest
    with pytest.raises(ValidationError):
        estimate(other_billable_work_aud=None)
