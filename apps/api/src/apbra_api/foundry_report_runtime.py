"""Finite saved-case report authority; private approval only, no import-time credentials."""

from __future__ import annotations

import contextvars
import dataclasses
import re
import secrets
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, DecimalException, localcontext
from typing import Any, Literal
from uuid import UUID

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from apbra_api.config import FoundryHostBinding, Settings
from apbra_api.model_provider import (
    FoundryAccess,
    FoundryBearer,
    FoundryCredentialProvider,
    ProviderConfigurationError,
    ProviderProfile,
)

ERROR = "FOUNDRY_REPORT_AUTHORIZATION_UNAVAILABLE"
CAP = Decimal("10.00")
PERIOD = "2026-10"
BUDGET_END = datetime(2026, 11, 1, tzinfo=UTC).timestamp()
Stage = Literal["REQUIREMENT_ANALYSIS", "REPORT_DESIGN"]


def require(value: Any) -> None:
    if value is not True:
        raise ProviderConfigurationError(ERROR)


def money(value: str) -> Decimal:
    require(type(value) is str and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) is not None)
    amount = Decimal(value)
    require(amount.is_finite() and amount >= 0)
    return amount


class Slot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    stage: Stage
    attempts: int = Field(ge=1, le=20)
    all_in_attempt_aud: str = Field(repr=False)
    bound_evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$", repr=False)


class ReportApproval(BaseModel):
    """Trusted owner-private attestation, not HTTP/model/token-frame claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    binding: FoundryHostBinding = Field(repr=False)
    case_id: UUID = Field(repr=False)
    settings_id: UUID = Field(repr=False)
    settings_digest: str = Field(pattern=r"^[a-f0-9]{64}$", repr=False)
    request_version_id: UUID = Field(repr=False)
    semantic_context_version: int = Field(ge=1, repr=False)
    input_digest: str = Field(pattern=r"^[a-f0-9]{64}$", repr=False)
    confirmed_contract_id: UUID | None = Field(default=None, repr=False)
    confirmed_contract_digest: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$", repr=False
    )
    expected_interpretation_id: UUID | None = Field(default=None, repr=False)
    expected_interpretation_digest: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$", repr=False
    )
    confirmation_mode: Literal["CONFIRMED", "OWNER_CONFIRM_PENDING", "AFTER_ANALYSIS"]
    authorization_id: str = Field(pattern=r"^[a-f0-9]{64}$", repr=False)
    approval: Literal["ONE_EXISTING_CASE_REPORT"]
    ledger_period: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    ledger_evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$", repr=False)
    posted_aud: str = Field(repr=False)
    unposted_exposure_aud: str = Field(repr=False)
    outstanding_reserves_aud: str = Field(repr=False)
    chain_reserve_aud: str = Field(repr=False)
    slots: tuple[Slot, ...] = Field(min_length=1, max_length=2)

    def __repr__(self) -> str:
        return "ReportApproval(<private attestation>)"

    @model_validator(mode="after")
    def finite(self) -> ReportApproval:
        try:
            require(self.binding.manual_authentication_approved)
            require(self.binding.authorization_deadline > time.time())
            require(self.ledger_period == PERIOD == time.strftime("%Y-%m", time.gmtime()))
            require(self.binding.authorization_deadline <= BUDGET_END)
            sequence = tuple(s.stage for s in self.slots)
            require(sequence in (
                ("REQUIREMENT_ANALYSIS",), ("REPORT_DESIGN",),
                ("REQUIREMENT_ANALYSIS", "REPORT_DESIGN"),
            ))
            if sequence == ("REPORT_DESIGN",):
                require(
                    self.expected_interpretation_id is not None
                    and self.expected_interpretation_digest is not None
                )
                require(
                    (
                        self.confirmation_mode == "CONFIRMED"
                        and self.confirmed_contract_id is not None
                        and self.confirmed_contract_digest is not None
                    )
                    or (
                        self.confirmation_mode == "OWNER_CONFIRM_PENDING"
                        and self.confirmed_contract_id is None
                        and self.confirmed_contract_digest is None
                    )
                )
            else:
                require(
                    self.confirmation_mode == "AFTER_ANALYSIS"
                    and self.confirmed_contract_id is None
                    and self.confirmed_contract_digest is None
                    and self.expected_interpretation_id is None
                    and self.expected_interpretation_digest is None
                )
            maximum = min(
                self.binding.provider_profile.max_calls_per_operation,
                self.binding.provider_profile.retry_limit + 1,
            )
            with localcontext() as context:
                context.rounding = ROUND_CEILING
                planned = Decimal(0)
                for slot in self.slots:
                    require(slot.attempts <= maximum)
                    bound = money(slot.all_in_attempt_aud)
                    require(bound > 0)
                    planned += bound * slot.attempts
                reserve = money(self.chain_reserve_aud)
                require(reserve >= planned and reserve > 0)
                total = sum(
                    (
                        money(self.posted_aud),
                        money(self.unposted_exposure_aud),
                        money(self.outstanding_reserves_aud),
                        reserve,
                    ),
                    Decimal(0),
                )
                require(total <= CAP)
        except (DecimalException, ValueError, ProviderConfigurationError):
            raise ValueError(ERROR) from None
        return self


@dataclasses.dataclass(frozen=True, repr=False)
class ReportState:
    """One consistent authoritative state.

    interpretation_digest is the stored readiness_binding_digest.
    confirmed_digest is that referenced interpretation's readiness binding,
    only after existing domain confirmation validity has been verified.
    confirmed_contract_digest is a separate canonical contract digest; it is
    never compared to the interpretation/session JSON hash.
    """

    settings_id: UUID
    settings_digest: str
    company_id: UUID
    profile: ProviderProfile
    secret_reference_id: UUID | None
    case_id: UUID
    request_version_id: UUID
    semantic_context_version: int
    input_digest: str
    interpretation_id: UUID | None = None
    interpretation_digest: str | None = None
    confirmed_contract_id: UUID | None = None
    confirmed_interpretation_id: UUID | None = None
    confirmed_digest: str | None = None
    confirmed_contract_digest: str | None = None


def load_report_state(
    database: Any,
    company_id: UUID,
    case_id: UUID,
    acceptance_factory: Callable[[Any], Any],
    *,
    query_timeout_seconds: float,
) -> ReportState:
    """One read-only PostgreSQL snapshot; existing domain context/file validation.

    The trusted bootstrap supplies the existing configured AcceptanceService,
    with its original evidence/reference stores. This reader never invokes its
    model/bridge, confirms requirements, modifies data or opens credentials.
    It does not replace request-level actor/tenant authorization.
    """
    import json
    import math
    from contextlib import redirect_stderr, redirect_stdout

    from sqlalchemy import select, text

    from apbra_api.application import AcceptanceService
    from apbra_api.foundry_owner_metadata import _Discard, _private_sdk_logging
    from apbra_api.persistence import CaseRow, canonical_payload, sha256_text
    from apbra_api.tenant_settings import current_settings

    state = None
    failed = False
    with _private_sdk_logging(), redirect_stdout(_Discard()), redirect_stderr(_Discard()):
        try:
            require(database.engine.dialect.name == "postgresql")
            require(
                type(query_timeout_seconds) in (int, float)
                and math.isfinite(query_timeout_seconds)
                and query_timeout_seconds > 0
            )
            timeout_ms = int(query_timeout_seconds * 1000)
            require(timeout_ms > 0)
            with database.session() as db:
                # Set isolation before the first query. No SELECT FOR UPDATE:
                # this snapshot neither locks the case nor races a confirmation
                # by combining values from successive READ COMMITTED snapshots.
                db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
                db.execute(text("SET TRANSACTION READ ONLY"))
                db.execute(text(f"SET LOCAL statement_timeout = '{timeout_ms}ms'"))
                case = db.scalar(
                    select(CaseRow).where(CaseRow.id == case_id, CaseRow.company_id == company_id)
                )
                require(case is not None)
                snapshot = current_settings(db, company_id)
                profile = snapshot.settings.provider_profile
                require(
                    snapshot.company_id == company_id
                    and profile is not None
                    and snapshot.secret_reference_id is None
                )
                assert profile is not None
                require(query_timeout_seconds == profile.request_timeout_seconds)
                service = acceptance_factory(snapshot)
                require(
                    isinstance(service, AcceptanceService) and service.tenant_settings == snapshot
                )
                interpretation = db.interpretation_for_context(
                    case_id, case.semantic_context_version
                )
                _, context_binding, _ = service._current_context(
                    db,
                    case,
                    include_history=(
                        interpretation is None or interpretation.settings_version_id is not None
                    ),
                )
                values: dict[str, Any] = {}
                if interpretation is not None:
                    latest = db.latest_interpretation(case_id)
                    require(
                        latest is not None
                        and latest.id == interpretation.id
                        and interpretation.company_id == company_id
                        and interpretation.case_id == case_id
                        and interpretation.request_version_id == case.current_request_version_id
                        and service._settings_still_materially_current(
                            db, interpretation, company_id
                        )
                    )
                    service._validated_interpretation_context(db, case, interpretation)
                    values.update(
                        interpretation_id=interpretation.id,
                        interpretation_digest=interpretation.readiness_binding_digest,
                    )
                    contract = db.confirmed_contract(interpretation.id)
                    if contract is not None:
                        # Same existing confirmation lifecycle checks, without
                        # re-confirming or asking the bridge to regenerate it.
                        require(
                            interpretation.state == "READY_FOR_CONFIRMATION"
                            and interpretation.evidence_id is not None
                            and contract.company_id == company_id
                            and contract.case_id == case_id
                            and contract.interpretation_id == interpretation.id
                            and contract.schema_version == 2
                        )
                        contract_value = json.loads(contract.contract_json)
                        require(type(contract_value) is dict)
                        values.update(
                            confirmed_contract_id=contract.id,
                            confirmed_interpretation_id=interpretation.id,
                            confirmed_digest=interpretation.readiness_binding_digest,
                            confirmed_contract_digest=canonical_payload(contract_value),
                        )
                state = ReportState(
                    settings_id=snapshot.id,
                    settings_digest=snapshot.digest,
                    company_id=company_id,
                    profile=profile,
                    secret_reference_id=None,
                    case_id=case.id,
                    request_version_id=case.current_request_version_id,
                    semantic_context_version=case.semantic_context_version,
                    input_digest=sha256_text(context_binding),
                    **values,
                )
        except BaseException:
            failed = True
    if failed or state is None:
        raise ProviderConfigurationError(ERROR) from None
    return state


def same_input(approval: ReportApproval, state: ReportState) -> bool:
    return (
        state.settings_id == approval.settings_id
        and state.settings_digest == approval.settings_digest
        and state.company_id == approval.binding.company_id
        and state.profile == approval.binding.provider_profile
        and state.secret_reference_id is None
        and state.case_id == approval.case_id
        and state.request_version_id == approval.request_version_id
        and state.semantic_context_version == approval.semantic_context_version
        and state.input_digest == approval.input_digest
    )


@dataclasses.dataclass
class Operation:
    case_id: UUID
    stage: Stage
    nonce: str = dataclasses.field(default_factory=lambda: secrets.token_hex(32))
    completed: bool = False


CURRENT: contextvars.ContextVar[Operation | None] = contextvars.ContextVar(
    "report_operation", default=None
)


class Reservations:
    """A single one-shot receiver's atomic approval budget; no readiness spending."""

    def __init__(
        self,
        approval: ReportApproval,
        valid: Callable[[], bool],
        state_loader: Callable[[], ReportState],
    ) -> None:
        # Revalidate even typed copied instances: model_copy(update=...) bypasses
        # Pydantic validation and must never bypass the explicit cost ceiling.
        try:
            self.approval = ReportApproval.model_validate(approval.model_dump()).model_copy(
                deep=True
            )
        except BaseException:
            raise ProviderConfigurationError(ERROR) from None
        self.valid = valid
        self.state_loader = state_loader
        self.expected_interpretation = self.approval.expected_interpretation_id
        self.expected_digest = self.approval.expected_interpretation_digest
        self.lock = threading.Lock()
        self.closed = False
        self.cursor = 0
        self.owner: str | None = None
        self.attempts = [0 for _ in approval.slots]
        self.finished: set[str] = set()

    def _current_state(self) -> bool:
        return (
            not self.closed
            and time.strftime("%Y-%m", time.gmtime()) == PERIOD
            and time.time() < self.approval.binding.authorization_deadline
            and self.valid() is True
            and same_input(self.approval, self.state_loader())
        )

    def connected(self) -> bool:
        """Valid lease/context for reads and compilation, never dispatch authority."""
        try:
            with self.lock:
                return self._current_state()
        except Exception:
            return False

    def ready(self) -> bool:
        try:
            with self.lock:
                return self.cursor < len(self.approval.slots) and self._current_state()
        except Exception:
            return False

    def claim(self, company: UUID, profile: ProviderProfile) -> None:
        # Called only at the existing authorized provider's bearer boundary.
        operation = CURRENT.get()
        require(operation is not None)
        assert operation is not None
        with self.lock:
            require(
                not self.closed
                and self.valid() is True
                and time.strftime("%Y-%m", time.gmtime()) == PERIOD
                and time.time() < self.approval.binding.authorization_deadline
                and company == self.approval.binding.company_id
                and profile == self.approval.binding.provider_profile
                and operation.case_id == self.approval.case_id
                and operation.completed is False
                and operation.nonce not in self.finished
                and self.cursor < len(self.approval.slots)
            )
            slot = self.approval.slots[self.cursor]
            require(operation.stage == slot.stage)
            state = self.state_loader()
            require(same_input(self.approval, state))
            if slot.stage == "REQUIREMENT_ANALYSIS":
                require(state.interpretation_id is None)
            else:
                require(
                    self.expected_interpretation is not None
                    and self.expected_digest is not None
                    and state.interpretation_id == self.expected_interpretation
                    and state.interpretation_digest == self.expected_digest
                    and state.confirmed_interpretation_id == self.expected_interpretation
                    and state.confirmed_digest == self.expected_digest
                    and state.confirmed_contract_id is not None
                    and state.confirmed_contract_digest is not None
                    and (
                        self.approval.confirmed_contract_id is None
                        or (
                            state.confirmed_contract_id == self.approval.confirmed_contract_id
                            and state.confirmed_contract_digest
                            == self.approval.confirmed_contract_digest
                        )
                    )
                )
            require(self.owner is None or self.owner == operation.nonce)
            require(self.attempts[self.cursor] < slot.attempts)
            self.owner = operation.nonce
            # Before possible dispatch; no refund for credential/HTTP/validation faults.
            self.attempts[self.cursor] += 1

    def finish(self, operation: Operation) -> None:
        with self.lock:
            # Threadpool workers share this operation object through ContextVar.
            # Retire it even if cancellation/authorization failure preceded a
            # bearer claim; a late worker must not dispatch after request exit.
            operation.completed = True
            if self.owner == operation.nonce:
                if operation.stage == "REQUIREMENT_ANALYSIS":
                    try:
                        state = self.state_loader()
                        if same_input(self.approval, state):
                            self.expected_interpretation = state.interpretation_id
                            self.expected_digest = state.interpretation_digest
                    except BaseException:
                        self.closed = True
                self.finished.add(operation.nonce)
                self.owner = None
                self.cursor += 1

    @contextmanager
    def operation(self, case_id: UUID, stage: Stage) -> Iterator[None]:
        # Candidate context only. Unauthorized requests never claim a slot.
        require(CURRENT.get() is None)
        operation = Operation(case_id, stage)
        token = CURRENT.set(operation)
        try:
            yield
        finally:
            self.finish(operation)
            CURRENT.reset(token)

    def close(self) -> None:
        with self.lock:
            self.closed = True

    def receipt(self) -> dict[str, Any]:
        with self.lock:
            return {
                "status": "REPORT_RESERVATION_CLOSED"
                if self.closed
                else "REPORT_RESERVATION_GATED",
                "attempts_consumed": sum(self.attempts),
                "operations_consumed": self.cursor,
                "automatic_refund": False,
            }


class ReservedCredentials:
    def __init__(self, credentials: FoundryCredentialProvider, reservations: Reservations) -> None:
        self.credentials, self.reservations = credentials, reservations

    def ready(self, company_id: UUID, profile: ProviderProfile) -> bool:
        return (
            self.reservations.connected()
            and company_id == self.reservations.approval.binding.company_id
            and profile == self.reservations.approval.binding.provider_profile
            and self.credentials.ready(company_id, profile) is True
        )

    def resolve_readonly(self, company_id: UUID, profile: ProviderProfile,
                         *, case_id: UUID) -> FoundryAccess:
        """Existing connected identity for fixed project file GETs, never dispatch authority.

        Only the artifact retriever receives this capability. Paid provider resolution
        below remains reservation-claiming; reads cannot refund or create stage slots.
        """
        require(case_id == self.reservations.approval.case_id)
        require(self.ready(company_id, profile))
        access = self.credentials.resolve(company_id, profile)

        def bearer() -> FoundryBearer:
            require(case_id == self.reservations.approval.case_id)
            require(self.ready(company_id, profile))
            result = access.credential()
            require(self.ready(company_id, profile))
            return result

        return dataclasses.replace(access, credential=bearer)

    def resolve(self, company_id: UUID, profile: ProviderProfile) -> FoundryAccess:
        require(self.ready(company_id, profile))
        access = self.credentials.resolve(company_id, profile)

        def bearer() -> FoundryBearer:
            require(self.ready(company_id, profile))
            self.reservations.claim(company_id, profile)
            return access.credential()

        return dataclasses.replace(access, credential=bearer)


def application_factory(
    approval: ReportApproval, reservations: Reservations, create: Callable[..., FastAPI]
) -> Callable[..., FastAPI]:
    def factory(**kwargs: Any) -> FastAPI:
        credentials = kwargs.get("foundry_credentials")
        require(credentials is not None)
        assert credentials is not None
        kwargs["foundry_credentials"] = ReservedCredentials(credentials, reservations)
        app = create(**kwargs)
        # Exact trusted route mapping to immutable saved case. No client headers.
        paths: dict[str, Stage] = {
            f"/api/cases/{approval.case_id}/interpretations": "REQUIREMENT_ANALYSIS",
            f"/api/cases/{approval.case_id}/automatic-designs": "REPORT_DESIGN",
        }

        @app.middleware("http")
        async def context(
            request: Request, call_next: Callable[[Request], Awaitable[Response]]
        ) -> Response:
            stage = paths.get(request.url.path) if request.method == "POST" else None
            if stage is None:
                return await call_next(request)
            with reservations.operation(approval.case_id, stage):
                return await call_next(request)

        return app

    return factory


def run_report_receiver(
    plan: Any,
    channel: Any,
    approval: ReportApproval,
    *,
    settings: Settings,
    snapshot_loader: Callable[[], Any],
    state_loader: Callable[[], ReportState],
    serve: Callable[..., None] | None = None,
    listener: tuple[str, int] | None = None,
    published_port: int | None = None,
    nonce_factory: Callable[[], str] | None = None,
    native_receive_only: bool = False,
) -> dict[str, Any]:
    """Trusted bootstrap only; all private construction/errors/cleanup stay quiet."""
    from contextlib import redirect_stderr, redirect_stdout

    from apbra_api.foundry_owner_metadata import _Discard, _private_sdk_logging

    reservations = private = None
    failed = False
    with _private_sdk_logging(), redirect_stdout(_Discard()), redirect_stderr(_Discard()):
        try:
            from apbra_api.api import create_app
            from apbra_api.foundry_memory_handoff import run_receiver

            binding = approval.binding
            require(
                (
                    binding.company_id,
                    binding.tenant_id,
                    binding.client_id,
                    binding.authorization_deadline,
                )
                == (plan.company_id, plan.tenant_id, plan.client_id, plan.authorization_deadline)
            )
            initial = state_loader()
            require(same_input(approval, initial))
            if approval.slots[0].stage == "REQUIREMENT_ANALYSIS":
                # Cache hits must use existing owner Confirm/design-only, not a paid reanalysis.
                require(initial.interpretation_id is None)
            else:
                require(
                    initial.interpretation_id == approval.expected_interpretation_id
                    and initial.interpretation_digest == approval.expected_interpretation_digest
                )
                if approval.confirmation_mode == "CONFIRMED":
                    require(
                        initial.confirmed_contract_id == approval.confirmed_contract_id
                        and initial.confirmed_contract_digest == approval.confirmed_contract_digest
                        and initial.confirmed_interpretation_id
                        == approval.expected_interpretation_id
                    )
                else:
                    require(initial.confirmed_contract_id is None)
            private = settings.model_copy(
                update={
                    "foundry_host_enabled": True,
                    "foundry_host_binding_json": SecretStr(binding.model_dump_json()),
                }
            )

            def valid() -> bool:
                # One authoritative combined state, not two ID/digest reads.
                return same_input(approval, state_loader())

            reservations = Reservations(approval, valid, state_loader)
            if native_receive_only:
                from apbra_api.native_response_runtime import native_application_factory

                selected_factory = native_application_factory(approval, reservations, create_app)
            else:
                selected_factory = application_factory(approval, reservations, create_app)
            run_receiver(
                plan,
                channel,
                settings=private,
                snapshot_loader=snapshot_loader,
                serve=serve,
                runtime=True,
                invocation_gate=reservations.connected,
                application_factory=selected_factory,
                listener=listener,
                published_port=published_port,
                nonce_factory=nonce_factory,
            )
        except BaseException:
            failed = True
        finally:
            if reservations is not None:
                reservations.close()
            try:
                channel.close()
            except BaseException:
                failed = True
            private = None
    if failed:
        raise ProviderConfigurationError(ERROR) from None
    require(reservations is not None)
    assert reservations is not None
    return reservations.receipt()


def decode_private_approval(raw: bytes) -> ReportApproval:
    """Private input parsing is quiet and bounded; no metadata-derived defaults."""
    import json
    from contextlib import redirect_stderr, redirect_stdout

    from apbra_api.foundry_memory_handoff import MAX_FRAME, pairs
    from apbra_api.foundry_owner_metadata import _Discard, _private_sdk_logging

    failed = False
    result = None
    with _private_sdk_logging(), redirect_stdout(_Discard()), redirect_stderr(_Discard()):
        try:
            require(type(raw) is bytes and 0 < len(raw) <= MAX_FRAME)
            value = json.loads(raw, object_pairs_hook=pairs)
            require(type(value) is dict)
            result = ReportApproval.model_validate(value)
        except BaseException:
            failed = True
        finally:
            raw = b""
    if failed:
        raise ProviderConfigurationError(ERROR) from None
    assert result is not None
    return result


def _approval_frame(plan: Any, approval: ReportApproval, nonce: str) -> bytes:
    """One owner-private frame; no token, CLI grant, persistence or inferred facts."""
    import json

    from apbra_api.foundry_memory_handoff import MAX_FRAME

    # Revalidate copied models too: model_copy/update is not attestation validation.
    approval = ReportApproval.model_validate(approval.model_dump())
    require(type(nonce) is str and re.fullmatch(r"[a-f0-9]{64}", nonce) is not None)
    require(
        (
            approval.binding.company_id,
            approval.binding.tenant_id,
            approval.binding.client_id,
            approval.binding.authorization_deadline,
        )
        == (plan.company_id, plan.tenant_id, plan.client_id, plan.authorization_deadline)
    )
    raw = json.dumps(
        {"v": 1, "nonce": nonce, "approval": approval.model_dump(mode="json")},
        separators=(",", ":"),
    ).encode()
    require(0 < len(raw) <= MAX_FRAME)
    return len(raw).to_bytes(4, "big") + raw


def approval_frame(plan: Any, approval: ReportApproval, nonce: str) -> bytes:
    from contextlib import redirect_stderr, redirect_stdout

    from apbra_api.foundry_owner_metadata import _Discard, _private_sdk_logging

    with _private_sdk_logging(), redirect_stdout(_Discard()), redirect_stderr(_Discard()):
        try:
            return _approval_frame(plan, approval, nonce)
        except BaseException:
            raise ProviderConfigurationError(ERROR) from None


def receive_approval(plan: Any, channel: Any, nonce: str) -> ReportApproval:
    import json

    from apbra_api.foundry_memory_handoff import MAX_FRAME, exact, pairs

    value: dict[str, Any] = {}
    raw = b""
    try:
        length = int.from_bytes(exact(channel, 4, plan.authorization_deadline), "big")
        require(0 < length <= MAX_FRAME)
        raw = exact(channel, length, plan.authorization_deadline)
        value = json.loads(raw, object_pairs_hook=pairs)
        require(
            type(value) is dict
            and set(value) == {"v", "nonce", "approval"}
            and type(value["v"]) is int
            and value["v"] == 1
            and type(value["nonce"]) is str
            and value["nonce"] == nonce
            and type(value["approval"]) is dict
        )
        approval = decode_private_approval(json.dumps(value["approval"]).encode())
        # Same identity/deadline checks as sender; the nonce belongs to this PID1 lease.
        approval_frame(plan, approval, nonce)
        return approval
    except BaseException:
        raise ProviderConfigurationError(ERROR) from None
    finally:
        raw = b""
        if isinstance(value, dict):
            value.clear()


class _ApprovalChannel:
    """Continue the existing receiver handshake after the private approval prelude.

    The external peer sees one fresh challenge. The original receiver still
    executes every preflight and account/token check. Its matching challenge
    acknowledges the already received approval only after those preflights.
    """

    def __init__(self, channel: Any, nonce: str) -> None:
        from apbra_api.foundry_memory_handoff import HELLO

        self.channel, self.nonce = channel, nonce
        self.hello = HELLO
        self.challenge_pending = True

    def read(self, size: int, deadline: float) -> bytes:
        if self.hello:
            result, self.hello = self.hello[:size], self.hello[size:]
            return result
        received: bytes = self.channel.read(size, deadline)
        return received

    def write(self, value: bytes) -> None:
        import json

        from apbra_api.foundry_memory_handoff import pairs

        if self.challenge_pending:
            expected = {"v": 1, "nonce": self.nonce, "pid": 1}
            parsed = json.loads(value, object_pairs_hook=pairs)
            require(
                type(parsed) is dict
                and parsed == expected
                and type(parsed["v"]) is int
                and type(parsed["pid"]) is int
            )
            self.challenge_pending = False
            self.channel.write(b"REPORT_APPROVAL_ACCEPTED\n")
        else:
            self.channel.write(value)

    def connected(self, timeout: float) -> bool:
        result: bool = self.channel.connected(timeout)
        return result

    def close(self) -> None:
        self.hello = b""
        self.channel.close()


def run_private_report_receiver(
    plan: Any,
    channel: Any,
    *,
    settings: Settings | None = None,
    snapshot_loader: Callable[[], Any] | None = None,
    state_loader_factory: Callable[[ReportApproval], Callable[[], ReportState]] | None = None,
    serve: Callable[..., None] | None = None,
    listener: tuple[str, int] | None = None,
    published_port: int | None = None,
    native_receive_only: bool = False,
) -> dict[str, Any]:
    """PID1 owner's optional runtime mode: authority comes only from private frame."""
    import json
    from contextlib import redirect_stderr, redirect_stdout

    from apbra_api.foundry_owner_metadata import _Discard, _private_sdk_logging

    database = None
    failed = False
    receipt = None
    with _private_sdk_logging(), redirect_stdout(_Discard()), redirect_stderr(_Discard()):
        try:
            from apbra_api.config import get_settings
            from apbra_api.foundry_memory_handoff import HELLO, exact

            plan.validate()
            settings = settings or get_settings()
            settings.validate_security_profile()
            # No inherited host attestation or secret-reference fallback grants reports.
            require(
                settings.foundry_host_enabled is False
                and settings.foundry_host_binding_json is None
            )
            require(exact(channel, len(HELLO), plan.authorization_deadline) == HELLO)
            nonce = secrets.token_hex(32)
            channel.write(
                json.dumps({"v": 1, "nonce": nonce, "pid": 1}, separators=(",", ":")).encode()
                + b"\n"
            )
            approval = receive_approval(plan, channel, nonce)
            if snapshot_loader is None or state_loader_factory is None:
                from apbra_api.persistence import Database

                database = Database(settings.database_url)
            if snapshot_loader is None:
                from apbra_api.tenant_settings import current_settings

                assert database is not None

                def snapshot_loader() -> Any:
                    assert database is not None
                    with database.session() as db:
                        return current_settings(db, plan.company_id)

            if state_loader_factory is None:
                from apbra_api.application import AcceptanceService
                from apbra_api.evidence import LocalEvidenceStore
                from apbra_api.semantic_bridge import SemanticBridge

                require(settings.evidence_root.is_dir() and not settings.evidence_root.is_symlink())
                objects = LocalEvidenceStore(settings.evidence_root, settings.profile)
                references = None
                if settings.reference_root is not None:
                    require(
                        settings.reference_root.is_dir()
                        and not settings.reference_root.is_symlink()
                    )
                    references = LocalEvidenceStore(settings.reference_root, settings.profile)
                require(settings.semantic_timeout_seconds is not None)
                assert settings.semantic_timeout_seconds is not None
                bridge = SemanticBridge(
                    settings.semantic_bridge_path,
                    node_executable=settings.semantic_node_path,
                    timeout_seconds=settings.semantic_timeout_seconds,
                )

                def acceptance(snapshot: Any) -> Any:
                    return AcceptanceService(
                        bridge, objects, reference_objects=references, tenant_settings=snapshot
                    )

                def load() -> ReportState:
                    return load_report_state(
                        database,
                        plan.company_id,
                        approval.case_id,
                        acceptance,
                        query_timeout_seconds=approval.binding.provider_profile.request_timeout_seconds,
                    )
            else:
                load = state_loader_factory(approval)
            receipt = run_report_receiver(
                plan,
                _ApprovalChannel(channel, nonce),
                approval,
                settings=settings,
                snapshot_loader=snapshot_loader,
                state_loader=load,
                serve=serve,
                listener=listener,
                published_port=published_port,
                nonce_factory=lambda: nonce,
                native_receive_only=native_receive_only,
            )
        except BaseException:
            failed = True
        finally:
            for closer in (
                channel.close,
                *((database.engine.dispose,) if database is not None else ()),
            ):
                try:
                    closer()
                except BaseException:
                    failed = True
    if failed or receipt is None:
        raise ProviderConfigurationError(ERROR) from None
    return receipt
