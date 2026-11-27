"""Private, case-bound bridge to the released saved-v10 transport.

The ordinary product supplies current database authority. Only the owned host
can attest the selected runtime, finite allowance and independent file origin.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from fractions import Fraction
from threading import Event, Lock
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field

from .foundry_artifacts import GeneratedFile
from .foundry_memory_handoff import MAX_FRAME, Channel, HandoffPlan, exact, pairs, require
from .foundry_v10_report_transport import V10Operation, V10Original, V10ReportTransport
from .model_provider import FoundryAccess, ProviderCallError, ProviderProfile, ProviderRequest
from .native_contracts import digest
from .native_response_archive import NativeResponseArchive
from .native_response_probe import NativeReceiveResult

Purpose = Literal["REQUIREMENT_ANALYSIS", "FULL_REPORT_ARTIFACT"]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Amount = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]+)?$")]
# The separately authorised six-row synthetic work-order CSV, including its final newline.
DEMO_SOURCE_SHA256 = "5226ffea2c59ff6c00e7171e38787de98584775491e1f591922434714b1842f4"


class _Private(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class V10DemoCase(_Private):
    company_id: UUID
    actor_id: UUID
    membership_id: UUID
    session_id: UUID
    case_id: UUID
    settings_id: UUID
    settings_digest: Digest
    source_id: UUID
    request_version_id: UUID
    source_digest: Digest
    goal: str = Field(min_length=1, repr=False)
    project_url: str = Field(repr=False)
    agent_name: str
    knowledge_binding: str
    knowledge_scope: Literal["SHARED_STANDARDS", "TENANT_PRIVATE"]
    profile_sha256: Digest


class V10DemoGrant(_Private):
    case: V10DemoCase
    tenant_id: UUID
    client_id: UUID
    home_account_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,255}$", repr=False)
    period: str
    expires: float = Field(strict=True, allow_inf_nan=False)
    posted_aud: Amount
    unposted_aud: Amount
    outstanding_aud: Amount
    ceiling_aud: Amount
    analysis_reserve_aud: Amount
    report_reserve_aud: Amount
    # Actual host evidence covers identity/permissions, v10 default instructions,
    # knowledge and unseeded auto interpreter, and all-in metering for each action.
    runtime_evidence_sha256: Digest
    rights_evidence_sha256: Digest
    analysis_bound_sha256: Digest
    report_bound_sha256: Digest

    def current(self) -> bool:
        now = time.time()
        if self.expires <= now:
            return False
        try:
            current = datetime.fromtimestamp(now, UTC)
            next_month = datetime(
                current.year + (current.month == 12), current.month % 12 + 1, 1, tzinfo=UTC
            )
            analysis = Fraction(self.analysis_reserve_aud)
            report = Fraction(self.report_reserve_aud)
            total = sum(map(Fraction, (self.posted_aud, self.unposted_aud, self.outstanding_aud)))
            return (
                self.period == current.strftime("%Y-%m")
                and self.expires <= next_month.timestamp()
                and analysis > 0
                and report > 0
                and total + analysis + report <= Fraction(self.ceiling_aud)
            )
        except (ArithmeticError, ValueError, OverflowError):
            return False


def _denied() -> ProviderCallError:
    return ProviderCallError("V10_AUTHORITY_UNAVAILABLE")


def _ok(callback: Callable[[], bool]) -> bool:
    try:
        return callback() is True
    except Exception:
        return False


class V10DemoReceiver:
    """Typed composition capability. No credentials, JSON or URL grants it via HTTP."""

    def __init__(
        self,
        grant: V10DemoGrant,
        dispatch_access: FoundryAccess,
        read_access: FoundryAccess,
        *,
        host_current: Callable[[], bool],
        authorize_stage: Callable[[V10Operation], bool],
        exclusive_writer: Callable[[V10Operation, str, GeneratedFile], bool],
        transport: httpx.MockTransport | None = None,
    ) -> None:
        self._grant = V10DemoGrant.model_validate_json(grant.model_dump_json())
        self.case = self._grant.case
        if (
            not self._grant.current()
            or transport is None
            and self.case.source_digest != DEMO_SOURCE_SHA256
            or dispatch_access.credential == read_access.credential
            or transport is not None
            and type(transport) is not httpx.MockTransport
        ):
            raise _denied()
        mode = "LIVE_METADATA_VERIFIED" if transport is None else "OFFLINE_FIXTURE"
        for access in (dispatch_access, read_access):
            if (
                access.company_id,
                access.agent_version,
                access.knowledge_binding,
                access.knowledge_scope,
                access.qualification,
            ) != (
                self.case.company_id,
                "10",
                self.case.knowledge_binding,
                self.case.knowledge_scope,
                mode,
            ):
                raise _denied()
        self._dispatch, self._read = dispatch_access, read_access
        self._transport = transport
        self._host_current, self._authorize = host_current, authorize_stage
        self._writer = exclusive_writer
        self._connections = {
            s: str(uuid4()) for s in ("REQUIREMENT_ANALYSIS", "FULL_REPORT_ARTIFACT")
        }
        self._consumed: set[Purpose] = set()
        self._closed = Event()
        self._lock = Lock()

    def close(self) -> None:
        self._closed.set()

    def allowed_in(self, profile: str) -> bool:
        return profile == "test" or profile == "development" and self._transport is None

    @property
    def qualification(self) -> Literal["OFFLINE_FIXTURE", "LIVE_METADATA_VERIFIED"]:
        return self._dispatch.qualification

    @property
    def grant_sha256(self) -> str:
        return digest(self._grant.model_dump(mode="json"))

    def connection_id(self, purpose: Purpose) -> str:
        return self._connections[purpose]

    def _current(self) -> bool:
        return not self._closed.is_set() and self._grant.current() and _ok(self._host_current)

    def permits(
        self,
        operation: V10Operation,
        *,
        actor_id: UUID,
        session_id: UUID,
        membership_id: UUID,
        settings_id: UUID,
        settings_digest: str,
    ) -> bool:
        case = self.case
        return (
            self._current()
            and operation.purpose in self._connections
            and operation.purpose not in self._consumed
            and (actor_id, membership_id, session_id, settings_id, settings_digest)
            == (
                case.actor_id,
                case.membership_id,
                case.session_id,
                case.settings_id,
                case.settings_digest,
            )
            and (
                operation.scope.company_id,
                operation.scope.case_id,
                operation.request_version_id,
                operation.source_id,
                operation.source_digest,
                operation.goal,
                operation.profile_sha256,
                operation.project_url,
                operation.agent_name,
                operation.knowledge_binding,
                operation.knowledge_scope,
            )
            == (
                case.company_id,
                case.case_id,
                case.request_version_id,
                case.source_id,
                case.source_digest,
                case.goal,
                case.profile_sha256,
                case.project_url,
                case.agent_name,
                case.knowledge_binding,
                case.knowledge_scope,
            )
            and re.fullmatch(r"[a-f0-9]{64}", operation.context_sha256) is not None
        )

    def open(
        self,
        operation: V10Operation,
        *,
        actor_id: UUID,
        session_id: UUID,
        membership_id: UUID,
        settings_id: UUID,
        settings_digest: str,
        current: Callable[[], bool],
        claim: Callable[[], bool],
    ) -> V10DemoExchange:
        if not self.permits(
            operation,
            actor_id=actor_id,
            session_id=session_id,
            membership_id=membership_id,
            settings_id=settings_id,
            settings_digest=settings_digest,
        ):
            raise _denied()
        return V10DemoExchange(self, operation, current, claim)


class V10DemoExchange:
    def __init__(
        self,
        receiver: V10DemoReceiver,
        operation: V10Operation,
        current: Callable[[], bool],
        claim: Callable[[], bool],
    ) -> None:
        self._receiver, self._operation = receiver, operation
        self._current_case, self._claim_slot = current, claim
        self._proved_claim = False
        self._sender = V10ReportTransport(operation, self)

    def current(self, operation: V10Operation | None = None) -> bool:
        return (
            (operation is None or operation == self._operation)
            and self._receiver._current()
            and _ok(self._current_case)
        )

    def report_save_lease_current(self) -> bool:
        """Check the claimed report lease while storage rechecks the case in its transaction."""
        return (
            self._operation.purpose == "FULL_REPORT_ARTIFACT"
            and self._proved_claim
            and self._receiver._current()
        )

    def claim(self, operation: V10Operation) -> bool:
        r = self._receiver
        if not self.current(operation):
            return False
        with r._lock:
            if operation.purpose in r._consumed:
                return False
            r._consumed.add(operation.purpose)
        # A failure or disconnect after this point never replenishes this lease.
        self._proved_claim = (
            _ok(self._claim_slot)
            and self.current(operation)
            and _ok(lambda: r._authorize(operation))
            and self.current(operation)
        )
        return self._proved_claim

    def exclusive_writer(
        self, operation: V10Operation, response_id: str, ref: GeneratedFile
    ) -> bool:
        return (
            self._proved_claim
            and self.current(operation)
            and _ok(lambda: self._receiver._writer(operation, response_id, ref))
            and self.current(operation)
        )

    def send(
        self, profile: ProviderProfile, request: ProviderRequest, *, archive: NativeResponseArchive
    ) -> NativeReceiveResult:
        s = self._operation.scope
        return self._sender(
            profile,
            self._receiver._dispatch,
            request,
            company_id=s.company_id,
            case_id=s.case_id,
            context_version=s.context_version,
            archive=archive,
            transport=self._receiver._transport,
        )

    def read_report(
        self, profile: ProviderProfile, *, archive: NativeResponseArchive, receipt_id: UUID
    ) -> V10Original:
        return self._sender.read_report(
            profile,
            self._receiver._read,
            archive=archive,
            receipt_id=receipt_id,
            transport=self._receiver._transport,
        )


class V10DemoQuestion(_Private):
    nonce: Digest
    lease: Digest
    action: Literal["STAGE", "EXCLUSIVE_WRITER"]
    purpose: Purpose
    operation_id: UUID
    case_id: UUID
    context_version: int = Field(strict=True, ge=1)
    context_sha256: Digest
    operation_sha256: Digest
    response_id: str | None = None
    container_id: str | None = None
    file_id: str | None = None
    filename: str | None = None


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _send(channel: Channel, value: object) -> None:
    data = _bytes(value)
    require(0 < len(data) <= MAX_FRAME)
    channel.write(len(data).to_bytes(4, "big") + data)


def _get(channel: Channel, deadline: float) -> dict[str, Any]:
    size = int.from_bytes(exact(channel, 4, deadline), "big")
    require(0 < size <= MAX_FRAME)
    result = json.loads(exact(channel, size, deadline), object_pairs_hook=pairs)
    require(type(result) is dict)
    return dict(result)


def _verify(value: dict[str, Any], key: str) -> dict[str, Any]:
    require(set(value) == {"payload", "signature"} and type(value["payload"]) is dict)
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(key)).verify(
        bytes.fromhex(value["signature"]), _bytes(value["payload"])
    )
    return dict(value["payload"])


@dataclass(frozen=True, repr=False)
class V10DemoHost:
    """Trusted private operator composition, independent of HTTP, the agent and its output.

    qualify reads the *authenticated* SDK account, actual project and private cost ledger.
    attest checks the current operation or independent sole-writer evidence. It returns
    the digest of actual observed evidence, or None. Neither defaults to granting access.
    """

    preflight: Callable[[], None]
    qualify: Callable[[Any, Any], V10DemoGrant]
    attest: Callable[[V10DemoGrant, V10DemoQuestion], str | None]
    signer: Ed25519PrivateKey = field(default_factory=Ed25519PrivateKey.generate, repr=False)

    @property
    def verification_key(self) -> str:
        return self.signer.public_key().public_bytes_raw().hex()

    def _sign(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"payload": payload, "signature": self.signer.sign(_bytes(payload)).hex()}

    def send_grant(self, channel: Channel, nonce: str, grant: V10DemoGrant) -> str:
        require(
            grant.case.source_digest == DEMO_SOURCE_SHA256
            and grant.current()
            and re.fullmatch(r"[a-f0-9]{64}", nonce)
        )
        payload = {"mode": "SIGNED_IN_V10", "nonce": nonce, "grant": grant.model_dump(mode="json")}
        _send(channel, self._sign(payload))
        return hashlib.sha256(_bytes(payload)).hexdigest()

    def serve_proofs(self, channel: Channel, grant: V10DemoGrant, lease: str) -> None:
        seen: dict[Purpose, tuple[UUID, str]] = {}
        while grant.current() and time.time() < grant.expires:
            if channel.connected(0.25):
                continue
            q = V10DemoQuestion.model_validate(_get(channel, grant.expires))
            require(q.lease == lease and q.case_id == grant.case.case_id)
            key = (q.operation_id, q.operation_sha256)
            file = (q.response_id, q.container_id, q.file_id, q.filename)
            if q.action == "STAGE":
                require(not any(x is not None for x in file) and q.purpose not in seen)
                seen[q.purpose] = key
            else:
                require(
                    q.purpose == "FULL_REPORT_ARTIFACT"
                    and seen.get(q.purpose) == key
                    and all(isinstance(x, str) and x for x in file)
                )
            observed = self.attest(grant, q)
            verified = (
                isinstance(observed, str)
                and re.fullmatch(r"[a-f0-9]{64}", observed)
                and grant.current()
            )
            proof = {
                "question": q.model_dump(mode="json"),
                "evidence_sha256": observed if verified else None,
            }
            _send(channel, self._sign(proof))


class V10PrivatePeer:
    """A receiver trusts only the public key pinned in its owned PID1 command."""

    def __init__(self, channel: Channel, verification_key: str, plan: HandoffPlan) -> None:
        require(re.fullmatch(r"[a-f0-9]{64}", verification_key))
        self.channel, self.key, self.plan = channel, verification_key, plan
        self._lock = Lock()
        self._revoked = Event()
        self._lease: str | None = None
        self.grant: V10DemoGrant | None = None

    def receive_grant(self, nonce: str) -> V10DemoGrant:
        require(self._lease is None)
        payload = _verify(_get(self.channel, self.plan.authorization_deadline), self.key)
        require(
            set(payload) == {"mode", "nonce", "grant"}
            and payload["nonce"] == nonce
            and payload["mode"] == "SIGNED_IN_V10"
        )
        grant = V10DemoGrant.model_validate(payload["grant"])
        require(grant.case.source_digest == DEMO_SOURCE_SHA256)
        require(
            grant.current()
            and (grant.case.company_id, grant.tenant_id, grant.client_id, grant.expires)
            == (
                self.plan.company_id,
                self.plan.tenant_id,
                self.plan.client_id,
                self.plan.authorization_deadline,
            )
        )
        self._lease = hashlib.sha256(_bytes(payload)).hexdigest()
        self.grant = grant
        return grant

    def connected(self, timeout: float) -> bool:
        with self._lock:
            return not self._revoked.is_set() and self.channel.connected(timeout)

    def _attest(
        self, op: V10Operation, response_id: str | None, file: GeneratedFile | None
    ) -> bool:
        grant = self.grant
        if self._revoked.is_set() or self._lease is None or grant is None or not grant.current():
            return False
        op_digest = hashlib.sha256(
            json.dumps(
                asdict(op), sort_keys=True, separators=(",", ":"), default=str, allow_nan=False
            ).encode()
        ).hexdigest()
        question = V10DemoQuestion(
            nonce=secrets.token_hex(32),
            lease=self._lease,
            action="STAGE" if file is None else "EXCLUSIVE_WRITER",
            purpose=op.purpose,
            operation_id=op.scope.operation_id,
            case_id=op.scope.case_id,
            context_version=op.scope.context_version,
            context_sha256=op.context_sha256,
            operation_sha256=op_digest,
            response_id=response_id,
            container_id=file.container_id if file else None,
            file_id=file.file_id if file else None,
            filename=file.filename if file else None,
        )
        value = question.model_dump(mode="json")
        with self._lock:
            try:
                if self._revoked.is_set():
                    return False
                _send(self.channel, value)
                result = _verify(_get(self.channel, grant.expires), self.key)
                require(
                    set(result) == {"question", "evidence_sha256"} and result["question"] == value
                )
                evidence = result["evidence_sha256"]
                if evidence is None:
                    return False
                require(type(evidence) is str and re.fullmatch(r"[a-f0-9]{64}", evidence))
                return grant.current()
            except Exception:
                self._revoked.set()
                return False

    def authorize_stage(self, operation: V10Operation) -> bool:
        return self._attest(operation, None, None)

    def exclusive_writer(
        self, operation: V10Operation, response_id: str, file: GeneratedFile
    ) -> bool:
        return self._attest(operation, response_id, file)
