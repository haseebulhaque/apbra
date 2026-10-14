"""Derive one private saved-case grant; no sign-in, paid calls or HTTP authority."""
from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Any, Literal
from uuid import UUID

from .config import FoundryHostBinding
from .foundry_cost_limits import AttemptEstimate, QualifiedMcpControls
from .foundry_report_runtime import ReportApproval, ReportState, Slot, Stage, money, require
from .model_provider import ProviderProfile


@dataclass(frozen=True, repr=False)
class Preparation:
    """Trusted private-host callbacks; cannot be supplied by an HTTP/model claim.

    Nonpaid readiness runs before SDK construction. Qualification reads only
    the already approved account's selected agent/knowledge metadata privately.
    The host must verify actual enforcement and rates before returning a grant.
    """
    preflight: Callable[[], None]
    qualify: Callable[[Any, Any], ReportApproval]


@dataclass(frozen=True, repr=False)
class QualifiedAgentFacts:
    """Already verified private-host routing/isolation facts, not metadata authority.

    There is deliberately no account-ID field. The same approved SDK account
    confirmed by the owner supplies it when deriving the grant.
    """
    company_id: UUID
    tenant_id: UUID
    client_id: UUID
    provider_profile: ProviderProfile
    knowledge_binding: str
    knowledge_scope: Literal["SHARED_STANDARDS", "TENANT_PRIVATE"]
    agent_version: str
    authorization_deadline: float
    mcp_controls: QualifiedMcpControls | None = None


def derive_approval(
    state: ReportState,
    record: Any,
    qualified_agent: QualifiedAgentFacts,
    *,
    choices: tuple[tuple[Stage, int], ...],
    estimates: tuple[AttemptEstimate, ...],
    posted_aud: str,
    unposted_exposure_aud: str,
    outstanding_reserves_aud: str,
    ledger_period: str,
) -> ReportApproval:
    """Private verified facts plus normal owner choices; no external grant JSON.

    The qualification record supplies actual routing/isolation facts. It does
    not choose a case, reinterpret requirements, confirm them or change a
    profile. The confirmed SDK record alone supplies the home account ID.
    """
    require(len(choices) == len(estimates) and 1 <= len(choices) <= 2)
    require(type(qualified_agent) is QualifiedAgentFacts)
    require((record.tenant_id, record.client_id) == (
        str(qualified_agent.tenant_id), str(qualified_agent.client_id)
    ))
    binding = FoundryHostBinding(
        company_id=qualified_agent.company_id, tenant_id=UUID(record.tenant_id),
        client_id=UUID(record.client_id), home_account_id=record.home_account_id,
        provider_profile=qualified_agent.provider_profile,
        knowledge_binding=qualified_agent.knowledge_binding,
        knowledge_scope=qualified_agent.knowledge_scope,
        agent_version=qualified_agent.agent_version,
        qualification="LIVE_METADATA_VERIFIED", manual_authentication_approved=True,
        authorization_deadline=qualified_agent.authorization_deadline,
        mcp_controls=qualified_agent.mcp_controls,
    )
    require(state.company_id == binding.company_id and state.profile == binding.provider_profile)
    require(state.secret_reference_id is None)
    require(
        (record.tenant_id, record.client_id) == (str(binding.tenant_id), str(binding.client_id))
    )
    slots = []
    with localcontext() as context:
        context.rounding = ROUND_CEILING
        reserve = Decimal(0)
        for (stage, attempts), estimate in zip(choices, estimates, strict=True):
            amount, digest = estimate.reserve()
            slots.append(Slot(stage=stage, attempts=attempts, all_in_attempt_aud=amount,
                              bound_evidence_digest=digest))
            reserve += money(amount) * attempts
    values: dict[str, Any] = {}
    if tuple(stage for stage, _ in choices) == ("REPORT_DESIGN",):
        require(state.interpretation_id is not None and state.interpretation_digest is not None)
        values.update(expected_interpretation_id=state.interpretation_id,
                      expected_interpretation_digest=state.interpretation_digest)
        if state.confirmed_contract_id is not None:
            require(state.confirmed_interpretation_id == state.interpretation_id
                    and state.confirmed_digest == state.interpretation_digest
                    and state.confirmed_contract_digest is not None)
            values.update(confirmation_mode="CONFIRMED",
                          confirmed_contract_id=state.confirmed_contract_id,
                          confirmed_contract_digest=state.confirmed_contract_digest)
        else:
            values["confirmation_mode"] = "OWNER_CONFIRM_PENDING"
    else:
        values["confirmation_mode"] = "AFTER_ANALYSIS"
    ledger = {"period": ledger_period, "posted_aud": posted_aud,
              "unposted_exposure_aud": unposted_exposure_aud,
              "outstanding_reserves_aud": outstanding_reserves_aud}
    digest = hashlib.sha256(json.dumps(ledger, sort_keys=True,
                                       separators=(",", ":")).encode()).hexdigest()
    return ReportApproval(
        binding=binding, case_id=state.case_id, settings_id=state.settings_id,
        settings_digest=state.settings_digest, request_version_id=state.request_version_id,
        semantic_context_version=state.semantic_context_version, input_digest=state.input_digest,
        authorization_id=secrets.token_hex(32), approval="ONE_EXISTING_CASE_REPORT",
        ledger_period=ledger_period, ledger_evidence_digest=digest,
        posted_aud=posted_aud, unposted_exposure_aud=unposted_exposure_aud,
        outstanding_reserves_aud=outstanding_reserves_aud, chain_reserve_aud=str(reserve),
        slots=tuple(slots), **values,
    )
