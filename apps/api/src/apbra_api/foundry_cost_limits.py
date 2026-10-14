"""Explicit technical limits and conservative estimates; no credentials or defaults."""

from __future__ import annotations

import hashlib
import json
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    return {
        "configured": None if limits is None else limits.model_dump(),
        "warnings": warnings,
        "qualifiesInvocation": False,
    }


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
            amount = (
                self.model_turn_ceiling
                * (
                    self.model_input_token_ceiling * input_rate
                    + self.model_output_token_ceiling * output_rate
                )
                + money(self.other_billable_work_aud)
            ).quantize(Decimal("0.01"))
            require(amount > 0)
        digest = hashlib.sha256(
            json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return str(amount), digest


def provider_identity_digest(profile: Any) -> str:
    """Bind private enforcement proof to every qualified provider identity field."""
    identity = profile.model_dump(mode="json")
    for key in (
        "max_calls_per_operation",
        "max_input_characters",
        "max_output_tokens",
        "time_budget_seconds",
        "request_timeout_seconds",
        "retry_limit",
        "foundry_cost_limits",
    ):
        identity.pop(key, None)
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


class QualifiedMcpControls(BaseModel):
    """Private host proof for the exact stored agent; never Tenant Settings proof.

    The host must observe the stored approval policy and qualify stateless
    continuation plus the actual retrieval argument schema. These declarations
    do not change a cloud tool or establish live support by themselves.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    configuration_id: str = Field(min_length=1)
    provider_identity_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    agent_version: str = Field(min_length=1)
    knowledge_binding: str = Field(min_length=1)
    server_label: str = Field(min_length=1, max_length=120)
    tool_name: str = Field(min_length=1, max_length=120)
    approval_policy: Literal["always"]
    stateless_continuation_qualified: Literal[True]
    retrieval_argument_path: tuple[str, ...] | None = None
    enforcement_provenance: str = Field(min_length=1)

    @field_validator("retrieval_argument_path", mode="before")
    @classmethod
    def private_wire_path(cls, value: Any) -> Any:
        # The private JSON transport represents tuples as arrays; admit only
        # the identical string path, retaining strict validation everywhere else.
        if type(value) is list and all(type(key) is str for key in value):
            return tuple(value)
        return value


class McpContinuation:
    """Operation-local approval IDs and exposure; no remote storage or logging."""

    def __init__(self, controls: FoundryCostLimits, proof: QualifiedMcpControls):
        if (
            controls.max_mcp_calls is None
            or proof.approval_policy != "always"
            or proof.stateless_continuation_qualified is not True
        ):
            raise ValueError("MODEL_MCP_COST_CONTROL_UNQUALIFIED")
        if controls.max_retrieval_output_tokens is not None and (
            not proof.retrieval_argument_path or len(proof.retrieval_argument_path) > 8
        ):
            raise ValueError("MODEL_MCP_COST_CONTROL_UNQUALIFIED")
        self.controls, self.proof = controls, proof
        self.approved: set[str] = set()
        self.executed: set[str] = set()

    def next_input(self, payload: Any, prior: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        if (
            not isinstance(payload, dict)
            or payload.get("status") != "completed"
            or payload.get("error") is not None
            or payload.get("incomplete_details") is not None
        ):
            raise ValueError("MODEL_RESPONSE_NOT_COMPLETED")
        output = payload.get("output")
        if not isinstance(output, list) or not 1 <= len(output) <= 100:
            raise ValueError("MODEL_OUTPUT_INVALID")
        pending: set[str] = set()
        approvals: list[dict[str, Any]] = []
        for item in output:
            if not isinstance(item, dict):
                raise ValueError("MODEL_OUTPUT_INVALID")
            kind = item.get("type")
            if kind not in {
                "message",
                "reasoning",
                "mcp_list_tools",
                "mcp_call",
                "mcp_approval_request",
            }:
                raise ValueError("MODEL_MCP_UNQUALIFIED_TOOL")
            if kind in {"mcp_call", "mcp_approval_request", "mcp_list_tools"} and (
                item.get("server_label") != self.proof.server_label
            ):
                raise ValueError("MODEL_MCP_UNQUALIFIED_TOOL")
            if (
                kind in {"mcp_call", "mcp_approval_request"}
                and item.get("name") != self.proof.tool_name
            ):
                raise ValueError("MODEL_MCP_UNQUALIFIED_TOOL")
            if kind == "mcp_call":
                if item.get("status") not in {None, "completed"} or item.get("error"):
                    raise ValueError("MODEL_TOOL_FAILED")
                approval = item.get("approval_request_id")
                if (
                    not isinstance(approval, str)
                    or approval not in self.approved
                    or approval in self.executed
                ):
                    raise ValueError("MODEL_MCP_APPROVAL_POLICY_VIOLATION")
                self.executed.add(approval)
            if kind != "mcp_approval_request":
                continue
            identity = item.get("id")
            if (
                not isinstance(identity, str)
                or not 1 <= len(identity) <= 200
                or (identity in self.approved or identity in pending)
            ):
                raise ValueError("MODEL_MCP_APPROVAL_REPLAY")
            if self.controls.max_retrieval_output_tokens is not None:
                try:

                    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                        result: dict[str, Any] = {}
                        for key, value in pairs:
                            if key in result:
                                raise ValueError("Duplicate argument")
                            result[key] = value
                        return result

                    arguments = json.loads(item["arguments"], object_pairs_hook=unique_pairs)
                    for key in self.proof.retrieval_argument_path or ():
                        arguments = arguments[key]
                    if (
                        type(arguments) is not int
                        or not 0 < arguments <= self.controls.max_retrieval_output_tokens
                    ):
                        raise ValueError()
                except (ValueError, KeyError, TypeError):
                    raise ValueError("MODEL_MCP_RETRIEVAL_BUDGET_UNQUALIFIED") from None
            pending.add(identity)
            approvals.append(
                {"type": "mcp_approval_response", "approval_request_id": identity, "approve": True}
            )
        if not pending:
            return None
        if len(self.approved) + len(pending) > (self.controls.max_mcp_calls or 0):
            raise ValueError("MODEL_MCP_CALL_BUDGET_EXCEEDED")
        # Reserve every parallel approval before dispatch; never refund an
        # unknown/failed request. These IDs are never accepted from the UI.
        self.approved.update(pending)
        return [*prior, *output, *approvals]
