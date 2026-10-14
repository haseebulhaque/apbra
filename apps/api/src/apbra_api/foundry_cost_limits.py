"""Explicit technical limits and conservative estimates; no credentials or defaults."""
from __future__ import annotations

import hashlib
import json
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FoundryCostLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    max_builtin_tool_calls: int | None = Field(default=None, gt=0)
    max_mcp_calls: int | None = Field(default=None, gt=0)
    max_provider_requests: int | None = Field(default=None, gt=0)
    max_retrieval_output_tokens: int | None = Field(default=None, gt=0)


def limit_readiness(limits: FoundryCostLimits | None) -> dict[str, Any]:
    """Configuration is informational; it never certifies remote enforcement."""
    warnings = []
    if limits is not None:
        if limits.max_mcp_calls is not None:
            warnings.append("MCP_PRE_EXECUTION_APPROVAL_QUALIFICATION_REQUIRED")
        if limits.max_retrieval_output_tokens is not None:
            warnings.append("EXACT_MCP_RETRIEVAL_ARGUMENT_QUALIFICATION_REQUIRED")
    return {"configured": None if limits is None else limits.model_dump(),
            "warnings": warnings, "qualifiesInvocation": False}


class AttemptEstimate(BaseModel):
    """Trusted host facts, never a client/model authorization or invoice promise.

    Rates are AUD per token and include explicit provenance. Retrieval and
    other billable work must have a separately qualified finite AUD allowance.
    Missing observations cannot be replaced by zero or inferred from a timer.
    """
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    model_input_token_ceiling: int = Field(gt=0)
    model_output_token_ceiling: int = Field(gt=0)
    model_turn_ceiling: int = Field(gt=0)
    input_aud_per_token: str
    output_aud_per_token: str
    other_billable_work_aud: str
    rate_provenance: str = Field(min_length=1)
    enforcement_provenance: str = Field(min_length=1)

    def reserve(self) -> tuple[str, str]:
        from .foundry_report_runtime import money, require

        with localcontext() as context:
            context.rounding = ROUND_CEILING
            input_rate = money(self.input_aud_per_token)
            output_rate = money(self.output_aud_per_token)
            require(input_rate > 0 and output_rate > 0)
            amount = (self.model_turn_ceiling * (
                self.model_input_token_ceiling * input_rate
                + self.model_output_token_ceiling * output_rate
            ) + money(self.other_billable_work_aud)).quantize(Decimal("0.01"))
            require(amount > 0)
        digest = hashlib.sha256(json.dumps(
            self.model_dump(), sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()
        return str(amount), digest
