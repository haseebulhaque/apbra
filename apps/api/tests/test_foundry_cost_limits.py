"""Explicit estimate arithmetic; no paid calls, default prices or hard-cap claim."""
import pytest
from pydantic import ValidationError

from apbra_api.foundry_cost_limits import AttemptEstimate


def estimate(**changes):
    return AttemptEstimate(**{
        "model_input_token_ceiling": 1000, "model_output_token_ceiling": 128,
        "assumed_model_turns": 2, "input_aud_per_token": "0.0001",
        "output_aud_per_token": "0.0002", "other_billable_work_aud": "0.10",
        "rate_provenance": "synthetic-qualified-rates",
        "estimate_assumptions": "synthetic-two-turn-estimate-with-retrieval-allowance", **changes,
    })


def test_conservative_rounding_and_provenance_change_reservation_binding():
    amount, digest = estimate().reserve()
    assert amount == "0.36"
    assert estimate(rate_provenance="synthetic-next-revision").reserve()[1] != digest
    with pytest.raises(ValidationError):
        estimate(other_billable_work_aud=None)
