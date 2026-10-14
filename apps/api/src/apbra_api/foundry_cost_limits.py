"""Conservative reservation estimates; no tool policy, credentials or defaults."""
from __future__ import annotations

import hashlib
import json
from decimal import ROUND_CEILING, Decimal, localcontext

from pydantic import BaseModel, ConfigDict, Field


class AttemptEstimate(BaseModel):
    """Trusted host facts, never a client/model authorization or invoice promise.

    Rates are AUD per token with provenance. Turn counts and other billable
    work are explicit conservative assumptions, not enforced MCP bounds.
    The resulting reservation cannot guarantee an Azure invoice or override
    the monthly ceiling. Unknown exposure remains a disclosed risk.
    """
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    model_input_token_ceiling: int = Field(gt=0)
    model_output_token_ceiling: int = Field(gt=0)
    assumed_model_turns: int = Field(gt=0)
    input_aud_per_token: str
    output_aud_per_token: str
    other_billable_work_aud: str
    rate_provenance: str = Field(min_length=1)
    estimate_assumptions: str = Field(min_length=1)

    def reserve(self) -> tuple[str, str]:
        from .foundry_report_runtime import money, require

        with localcontext() as context:
            context.rounding = ROUND_CEILING
            input_rate = money(self.input_aud_per_token)
            output_rate = money(self.output_aud_per_token)
            require(input_rate > 0 and output_rate > 0)
            amount = (self.assumed_model_turns * (
                self.model_input_token_ceiling * input_rate
                + self.model_output_token_ceiling * output_rate
            ) + money(self.other_billable_work_aud)).quantize(Decimal("0.01"))
            require(amount > 0)
        digest = hashlib.sha256(json.dumps(
            self.model_dump(), sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()
        return str(amount), digest
