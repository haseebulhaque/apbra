"""Native receive, original inspection and explicit offline contract intake.

No format instruction, prose conversion or returned-URL fetch. The private runtime
must separately bind a fresh finite stage grant to receive. Offline intake reuses
existing semantic/confirmation/design validation; it sends no provider request.
"""

import json
from collections.abc import Callable, Iterator
from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid4

from fastapi import Cookie, Depends, FastAPI, Header, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .application import AcceptanceService
from .auth_boundary import SESSION_COOKIE
from .authorization import authorized_case_access, resolve_actor
from .content_storage import EvidenceObjectStore
from .domain import (
    Actor,
    ApplicationPersistence,
    CaseRecord,
    ConfigurationUnavailable,
    Conflict,
    Forbidden,
    ProtectedResourceNotFound,
    StaleVersion,
)
from .foundry_report_runtime import CURRENT, Reservations
from .generation import GenerationService, _provider_confirmed_requirements
from .model_provider import (
    FoundryAccess,
    FoundryAgentResponsesProvider,
    ProviderCallError,
    ProviderProfile,
    ProviderRequest,
)
from .native_case_files import NativeInputsUnavailable, prepare_case_files
from .native_contracts import SavedNativeContract, contract_failure, digest
from .native_response_archive import NativeResponseArchive, NativeResponseScope
from .native_response_index import (
    DatabaseNativeResponseIndex,
    NativeContractBindingRow,
    NativeReceiveCommandRow,
    NativeResponseReceiptRow,
)
from .native_response_probe import native_request_content, receive_native_response
from .persistence import Database
from .provider_diagnostics import safe_provider_diagnostic
from .tenant_settings import TenantSettingsSnapshot


class NativeReceiveCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_context_version: int = Field(ge=1, strict=True)
    expected_settings_id: UUID
    command_key: UUID
    task: Literal["REQUIREMENT_ANALYSIS", "REPORT_DESIGN"] = "REQUIREMENT_ANALYSIS"
    confirmed_contract_id: UUID | None = None


class NativeContractIntake(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_context_version: int = Field(ge=1, strict=True)
    expected_settings_id: UUID


def register_native_response_routes(
    app: FastAPI,
    database: Database,
    *,
    require_csrf: Callable[[str | None, str | None], None],
    snapshot_for: Callable[[Session, Actor], TenantSettingsSnapshot],
    service_for: Callable[..., AcceptanceService],
    generation_for: Callable[..., GenerationService],
    access_for: Callable[[Session, TenantSettingsSnapshot], tuple[ProviderProfile, FoundryAccess]],
    objects: EvidenceObjectStore,
    reservations: Reservations | None,
    receive_enabled: bool = False,
) -> None:
    index = DatabaseNativeResponseIndex(database)
    # Public correlation only; never an approval or credential.
    connection_id = str(uuid4())

    def sessions() -> Iterator[Session]:
        with database.session() as db:
            yield db

    def authorize(db: Session, token: str | None, case_id: UUID) -> Actor:
        actor = resolve_actor(db, token)
        if not actor.role.can_invite:
            raise Forbidden()
        # Company administration alone does not grant private case access.
        authorized_case_access(db, actor, case_id, require_edit=True)
        return actor

    def summary(db: Session, command: NativeReceiveCommandRow) -> dict[str, Any]:
        receipt = db.scalar(
            select(NativeResponseReceiptRow).where(
                NativeResponseReceiptRow.operation_id == command.id,
                NativeResponseReceiptRow.company_id == command.company_id,
                NativeResponseReceiptRow.case_id == command.case_id,
            )
        )
        return {
            "http_status": command.http_status,
            "provider_status": command.provider_status,
            "diagnostic": safe_provider_diagnostic(
                json.loads(command.diagnostic_json) if command.diagnostic_json else {}
            ),
            "operation_id": str(command.id),
            "state": command.state,
            "context_version": command.context_version,
            "receipt_id": str(receipt.id) if receipt else None,
            "bytes": receipt.size if receipt else None,
            "sha256": receipt.digest if receipt else None,
        }

    def prepare_request(
        db: Session, actor: Actor, case: CaseRecord, snapshot: TenantSettingsSnapshot,
        task: str = "REQUIREMENT_ANALYSIS", contract_id: UUID | None = None,
    ) -> tuple[ProviderRequest | None, dict[str, Any], list[dict[str, str]]]:
        store = cast(ApplicationPersistence, db)
        service = service_for(db, snapshot, include_provider=False)
        bundle = prepare_case_files(
            store, case, objects, service.reference_objects,
            max_file_bytes=snapshot.settings.upload_policy.max_file_bytes,
            vision_enabled=bool(snapshot.settings.provider_profile
                                and snapshot.settings.provider_profile.capabilities.vision),
        )
        availability = {
            "files": bundle.manifest,
            "ready": bundle.ready,
            "scope": "CURRENT_REQUEST_VERSION",
            "request_version_id": str(case.current_request_version_id),
            "context_version": case.semantic_context_version,
            "settings_id": str(snapshot.id),
            "reason": None if bundle.ready else "COMPLETE_FILE_HANDOFF_UNAVAILABLE",
            "input_characters": None,
            "input_limit": (snapshot.settings.provider_profile.max_input_characters
                            if snapshot.settings.provider_profile else None),
        }
        if not bundle.ready:
            return None, availability, []
        schema, context_binding, _ = service._current_context(store, case, include_history=True)
        policy = service.clarification_policy
        if policy is None or service.generation_policy is None:
            raise ConfigurationUnavailable()
        request = ProviderRequest(
            task="REQUIREMENT_ANALYSIS", system_prompt="", output_schema={},
            requires_vision=bool(bundle.image_parts),
            context={
                "materialContext": json.loads(context_binding),
                "clarificationState": service.clarification_state(store, case.id),
                "dataStructure": schema,
                "caseFiles": bundle.sources,
                "fileDelivery": {"transport": ("INLINE_SOURCE_AND_IMAGES" if bundle.image_parts
                                               else "INLINE_UTF8_SOURCE"), "sampled": False,
                                 "serviceFileUploaded": False, "processingVerified": False},
                "clarificationPolicy": {
                    "maxRounds": policy.max_rounds,
                    "maxQuestionsPerRound": policy.max_questions_per_round,
                    "maxAnswerCharacters": policy.max_answer_characters,
                },
                "generationPolicy": service.generation_policy,
            },
        )
        if task == "REPORT_DESIGN":
            if contract_id is None:
                raise Conflict()
            generation = generation_for(db, snapshot, require_bridge=True, resolve_provider=False)
            payload, _, _, _, _ = generation._current_payload(
                store, actor, case.id, contract_id, lock_access=True
            )
            assert generation.bridge is not None
            design_context = generation.bridge.design_context(
                {**payload, "knowledgeMode": "PROVIDER_MANAGED"}
            )
            request = ProviderRequest(
                task="REPORT_DESIGN", system_prompt="", output_schema={},
                requires_vision=bool(bundle.image_parts),
                context={
                    "confirmedRequirements": _provider_confirmed_requirements(payload["contract"]),
                    "dataStructure": payload["dataStructure"],
                    "referenceMaterial": payload["binding"]["referenceMaterial"],
                    "rendererCapabilities": design_context["rendererCapabilities"],
                    "generationPolicy": service.generation_policy,
                    "caseFiles": bundle.sources,
                    "fileDelivery": {"sampled": False, "serviceFileUploaded": False,
                                     "processingVerified": False},
                },
            )
        elif contract_id is not None:
            raise Conflict()
        profile = snapshot.settings.provider_profile
        if profile is None or profile.protocol != "FOUNDRY_AGENT_RESPONSES":
            availability.update(ready=False, reason="QUALIFIED_AGENT_ROUTE_REQUIRED")
            return None, availability, []
        try:
            content = native_request_content(profile, request, bundle.image_parts)
        except ProviderCallError:
            availability.update(ready=False, reason="MODEL_INPUT_BUDGET_EXCEEDED")
            return None, availability, []
        availability["input_characters"] = len(content) + sum(
            len(json.dumps(part, separators=(",", ":"))) for part in bundle.image_parts
        )
        return request, availability, bundle.image_parts

    @app.get("/api/cases/{case_id}/native-response-input")
    def inspect_input(
        case_id: UUID,
        response: Response,
        db: Annotated[Session, Depends(sessions)],
        task: Literal["REQUIREMENT_ANALYSIS", "REPORT_DESIGN"] = "REQUIREMENT_ANALYSIS",
        confirmed_contract_id: UUID | None = None,
        token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, Any]:
        actor = authorize(db, token, case_id)
        case, _ = authorized_case_access(db, actor, case_id, require_edit=True)
        if case is None:
            raise ProtectedResourceNotFound()
        response.headers["Cache-Control"] = "no-store"
        snapshot = snapshot_for(db, actor)
        _, availability, _ = prepare_request(db, actor, case, snapshot, task, confirmed_contract_id)
        can_receive = False
        if receive_enabled and reservations is not None:
            approval = reservations.approval
            can_receive = (
                availability["ready"] is True
                and len(approval.slots) == 1
                and approval.slots[0].stage == task
                and approval.slots[0].attempts == 1
                and approval.binding.company_id == actor.company_id
                and approval.confirmed_contract_id == confirmed_contract_id
                and approval.case_id == case.id
                and approval.settings_id == snapshot.id
                and approval.request_version_id == case.current_request_version_id
                and approval.semantic_context_version == case.semantic_context_version
                and reservations.ready()
            )
        availability.update(
            receive_available=can_receive,
            receive_reason=("AUTHORIZED_SINGLE_RESPONSE_READY" if can_receive
                            else "PRIVATE_AUTHORIZATION_UNAVAILABLE"),
            connection_id=connection_id if can_receive else None,
        )
        return availability

    @app.get("/api/cases/{case_id}/native-response-receipts")
    def list_receipts(
        case_id: UUID,
        response: Response,
        db: Annotated[Session, Depends(sessions)],
        token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, Any]:
        actor = authorize(db, token, case_id)
        response.headers["Cache-Control"] = "no-store"
        commands = db.scalars(select(NativeReceiveCommandRow).where(
            NativeReceiveCommandRow.company_id == actor.company_id,
            NativeReceiveCommandRow.case_id == case_id,
        ).order_by(NativeReceiveCommandRow.created_at.desc(), NativeReceiveCommandRow.id.desc()))
        return {"items": [summary(db, command) for command in commands]}

    @app.post("/api/cases/{case_id}/native-response-checks")
    def receive(
        case_id: UUID,
        payload: NativeReceiveCreate,
        db: Annotated[Session, Depends(sessions)],
        token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
        csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> dict[str, Any]:
        if not receive_enabled:
            raise ConfigurationUnavailable()
        require_csrf(token, csrf)
        actor = authorize(db, token, case_id)
        store = cast(ApplicationPersistence, db)
        case = store.locked_case(case_id)
        if case is None:
            raise ProtectedResourceNotFound()
        previous = db.scalar(
            select(NativeReceiveCommandRow).where(
                NativeReceiveCommandRow.company_id == actor.company_id,
                NativeReceiveCommandRow.case_id == case_id,
                NativeReceiveCommandRow.command_key == payload.command_key,
            )
        )
        if previous is not None:
            bound = db.get(NativeContractBindingRow, previous.id)
            if (
                previous.context_version != payload.expected_context_version
                or (bound is not None and (bound.task != payload.task
                    or bound.contract_id != payload.confirmed_contract_id))
                or (bound is None and (payload.task != "REQUIREMENT_ANALYSIS"
                    or payload.confirmed_contract_id is not None))
                or previous.settings_id != payload.expected_settings_id
            ):
                raise StaleVersion()
            # Includes ADMITTED/UNCERTAIN: never redispatch after an interrupted request.
            return {"native_response": summary(db, previous)}
        # Passive registration permits authenticated inspection, never paid
        # dispatch. Require the exact finite factory's private operation context
        # and its wrapped credential reservation before preparing a new command.
        operation = CURRENT.get()
        if reservations is None or operation is None:
            raise ConfigurationUnavailable()
        approval = reservations.approval
        if (
            len(approval.slots) != 1
            or approval.slots[0].stage != payload.task
            or approval.slots[0].attempts != 1
            or approval.confirmed_contract_id != payload.confirmed_contract_id
            or approval.case_id != case_id
            or approval.binding.company_id != actor.company_id
            or operation.case_id != case_id
            or operation.stage != payload.task
            or operation.completed
            or reservations.ready() is not True
        ):
            raise ConfigurationUnavailable()
        snapshot = snapshot_for(db, actor)
        if (
            case.semantic_context_version != payload.expected_context_version
            or snapshot.id != payload.expected_settings_id
        ):
            raise StaleVersion()
        native_request, availability, image_parts = prepare_request(
            db, actor, case, snapshot, payload.task, payload.confirmed_contract_id
        )
        if native_request is None or not availability["ready"]:
            raise NativeInputsUnavailable()
        profile, access = access_for(db, snapshot)
        # Constructor qualifies the existing tenant endpoint; it does not acquire
        # a token or consume a paid slot. Input limits are checked by the probe.
        FoundryAgentResponsesProvider(profile, access, company_id=actor.company_id)
        command = NativeReceiveCommandRow(
            id=uuid4(),
            company_id=actor.company_id,
            case_id=case_id,
            actor_membership_id=actor.membership_id,
            context_version=case.semantic_context_version,
            settings_id=snapshot.id,
            command_key=payload.command_key,
            state="ADMITTED",
        )
        db.add(command)
        db.flush()
        db.add(NativeContractBindingRow(
            operation_id=command.id, company_id=actor.company_id, case_id=case_id,
            context_version=case.semantic_context_version, task=payload.task,
            contract_id=payload.confirmed_contract_id,
            input_digest=digest({"task": native_request.task, "context": native_request.context,
                                 "images": image_parts}),
            profile_digest=digest(profile.model_dump()),
            metadata_json=json.dumps({
                "knowledge_binding": access.knowledge_binding,
                "knowledge_scope": access.knowledge_scope,
                "agent_version": access.agent_version,
                "qualification": access.qualification,
            }, sort_keys=True, separators=(",", ":")),
        ))
        db.commit()  # Durable one-command admission before any bearer/POST.
        scope = NativeResponseScope(actor.company_id, case_id, command.context_version, command.id)
        archive = NativeResponseArchive(scope, objects, index)
        try:
            result = receive_native_response(
                profile,
                access,
                native_request,
                company_id=actor.company_id,
                case_id=case_id,
                context_version=command.context_version,
                archive=archive, image_parts=image_parts,
            )
            command.state = result.status
            command.http_status = result.http_status
            command.provider_status = result.provider_status
            diagnostic = result.diagnostic
        except ProviderCallError as exc:
            # No credential, transport exception or raw response reaches logs.
            # An uncertain operation remains consumed; a refresh cannot retry it.
            command.state = "UNCERTAIN"
            diagnostic = exc.diagnostic
        safe = safe_provider_diagnostic(diagnostic)
        command.http_status = safe.get("http_status", command.http_status)
        encoded = json.dumps(safe, sort_keys=True, separators=(",", ":"))
        command.diagnostic_json = encoded if len(encoded.encode("utf-8")) <= 4096 else "{}"
        db.commit()
        # Recheck current membership and private case access after the network wait.
        authorize(db, token, case_id)
        return {"native_response": summary(db, command)}

    def archived_contract(
        db: Session, actor: Actor, case_id: UUID, reference: UUID,
        snapshot: TenantSettingsSnapshot,
    ) -> tuple[
        NativeReceiveCommandRow, NativeContractBindingRow | None, SavedNativeContract | None,
        dict[str, Any] | None,
    ]:
        row = db.scalar(select(NativeResponseReceiptRow).where(
            NativeResponseReceiptRow.id == reference,
            NativeResponseReceiptRow.company_id == actor.company_id,
            NativeResponseReceiptRow.case_id == case_id,
        ))
        if row is None:
            raise ProtectedResourceNotFound()
        command = db.get(NativeReceiveCommandRow, row.operation_id)
        assert command is not None
        binding = db.get(NativeContractBindingRow, row.operation_id)
        profile = snapshot.settings.provider_profile
        unavailable = (
            "NATIVE_BINDING_MISSING" if binding is None else
            "MODEL_PROFILE_MISSING" if profile is None else
            "MODEL_RESPONSE_NOT_COMPLETED" if command.state != "RECEIVED"
            or command.http_status != 200 or command.provider_status != "completed" else
            "NATIVE_SETTINGS_CHANGED" if command.settings_id != snapshot.id else
            "NATIVE_PROFILE_CHANGED"
            if binding.profile_digest != digest(profile.model_dump()) else None
        )
        if unavailable:
            return command, binding, None, {
                "code": unavailable, "phase": "NATIVE_BINDING", "findings": [],
            }
        assert binding is not None and profile is not None
        scope = NativeResponseScope(
            actor.company_id, case_id, row.context_version, row.operation_id
        )
        raw = NativeResponseArchive(scope, objects, index).read(reference)
        try:
            candidate = SavedNativeContract(
                raw, profile=profile, task=binding.task, receipt_id=reference,
                metadata=json.loads(binding.metadata_json),
            )
        except (ValueError, KeyError, RecursionError, ProviderCallError) as error:
            return command, binding, None, contract_failure(error)
        return command, binding, candidate, None

    @app.get("/api/cases/{case_id}/native-response-receipts/{reference}/contract")
    def inspect_contract(
        case_id: UUID, reference: UUID, response: Response,
        db: Annotated[Session, Depends(sessions)],
        token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, Any]:
        actor = authorize(db, token, case_id)
        snapshot = snapshot_for(db, actor)
        command, binding, candidate, diagnostic = archived_contract(
            db, actor, case_id, reference, snapshot,
        )
        case, _ = authorized_case_access(db, actor, case_id, require_edit=True)
        response.headers["Cache-Control"] = "no-store"
        return {"recognized": candidate is not None,
                "current": (case is not None
                            and case.semantic_context_version == command.context_version),
                "task": binding.task if binding else None,
                "context_version": command.context_version, "settings_id": str(command.settings_id),
                "reason": None if candidate else "INFORMATIONAL_ANSWER_ONLY",
                "receipt_id": str(reference), "diagnostic": diagnostic,
                "warnings": ([{"path": f"/standardsApplied/{index}/citation",
                               "reason": "CITATION_NOT_OBSERVED"}
                              for index in candidate.grounding.get("unverifiedStandardIndexes", [])]
                             if candidate is not None else [])}

    @app.post("/api/cases/{case_id}/native-response-receipts/{reference}/contract")
    def intake_contract(
        case_id: UUID, reference: UUID, payload: NativeContractIntake,
        db: Annotated[Session, Depends(sessions)],
        token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
        csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> dict[str, Any]:
        require_csrf(token, csrf)
        actor = authorize(db, token, case_id)
        store = cast(ApplicationPersistence, db)
        active = store.active_actor(actor.membership_id, actor.identity_id, lock=True)
        if active is None or active.company_id != actor.company_id or not active.role.can_invite:
            raise ProtectedResourceNotFound()
        actor = active
        authorized_case_access(store, actor, case_id, require_edit=True, lock=True)
        case = store.locked_case(case_id)
        snapshot = snapshot_for(db, actor)
        if (case is None or case.semantic_context_version != payload.expected_context_version
                or snapshot.id != payload.expected_settings_id):
            raise StaleVersion()
        command, binding, candidate, diagnostic = archived_contract(
            db, actor, case_id, reference, snapshot,
        )
        if (command.context_version != case.semantic_context_version
                or command.settings_id != snapshot.id):
            raise StaleVersion()
        if candidate is None or binding is None:
            return {"accepted": False, "reason": "INFORMATIONAL_ANSWER_ONLY",
                    "diagnostic": diagnostic}
        acceptance = service_for(db, snapshot, include_provider=False)
        if binding.task == "REQUIREMENT_ANALYSIS":
            existing = store.interpretation_for_context(case_id, case.semantic_context_version)
            if existing is not None:
                session = json.loads(existing.session_json)
                if session.get("providerProvenance", {}).get("sourceReceiptId") != str(reference):
                    raise Conflict()
                acceptance._validated_interpretation_context(store, case, existing)
                return {"accepted": True, "task": binding.task,
                        "interpretation": acceptance.state(db, actor, case_id)["interpretation"]}
        request, availability, images = prepare_request(
            db, actor, case, snapshot, binding.task, binding.contract_id,
        )
        if (request is None or not availability["ready"] or binding.input_digest != digest({
                "task": request.task, "context": request.context, "images": images})):
            raise StaleVersion()
        if binding.task == "REQUIREMENT_ANALYSIS":
            acceptance.model_provider = candidate
            result = acceptance.create_interpretation(
                db, actor, case_id, expected_context_version=case.semantic_context_version,
            )
            store.add_audit(actor, "NATIVE_ANALYSIS_INTAKE", "NATIVE_RESPONSE_RECEIPT", reference)
            db.commit()
            return {"accepted": True, "task": binding.task, "interpretation": result}
        assert binding.contract_id is not None
        generation = generation_for(db, snapshot, require_bridge=True, resolve_provider=False)
        generation.model_provider = candidate
        design, _ = generation.propose_automatic_design(
            db, actor, case_id, contract_id=binding.contract_id,
            command_key="native:" + str(reference),
        )
        return {"accepted": True, "task": binding.task, "design": design}

    @app.get("/api/cases/{case_id}/native-response-checks/{operation_id}")
    def inspect_status(
        case_id: UUID,
        operation_id: UUID,
        db: Annotated[Session, Depends(sessions)],
        token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, Any]:
        actor = authorize(db, token, case_id)
        command = db.scalar(
            select(NativeReceiveCommandRow).where(
                NativeReceiveCommandRow.id == operation_id,
                NativeReceiveCommandRow.company_id == actor.company_id,
                NativeReceiveCommandRow.case_id == case_id,
            )
        )
        if command is None:
            raise ProtectedResourceNotFound()
        return {"native_response": summary(db, command)}

    @app.get("/api/cases/{case_id}/native-response-receipts/{reference}/view")
    def view_answer(
        case_id: UUID,
        response: Response,
        reference: UUID,
        db: Annotated[Session, Depends(sessions)],
        token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, Any]:
        actor = authorize(db, token, case_id)
        row = db.scalar(select(NativeResponseReceiptRow).where(
            NativeResponseReceiptRow.id == reference,
            NativeResponseReceiptRow.company_id == actor.company_id,
            NativeResponseReceiptRow.case_id == case_id,
        ))
        if row is None:
            raise ProtectedResourceNotFound()
        scope = NativeResponseScope(
            actor.company_id, case_id, row.context_version, row.operation_id
        )
        raw = NativeResponseArchive(scope, objects, index).read(reference)
        response.headers["Cache-Control"] = "no-store"
        texts: list[str] = []
        try:
            body = json.loads(raw)
            if type(body) is dict and type(body.get("output")) is list:
                for output in body["output"]:
                    if (type(output) is dict and output.get("type") == "message"
                            and output.get("role") == "assistant"
                            and type(output.get("content")) is list):
                        texts.extend(part["text"] for part in output["content"]
                                     if type(part) is dict and part.get("type") == "output_text"
                                     and type(part.get("text")) is str)
        except (ValueError, UnicodeError, RecursionError):
            pass
        return {"receipt_id": str(row.id), "context_version": row.context_version,
                "texts": texts, "bytes": row.size, "sha256": row.digest}

    @app.get("/api/cases/{case_id}/native-response-receipts/{reference}")
    def download(
        case_id: UUID,
        reference: UUID,
        db: Annotated[Session, Depends(sessions)],
        token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> Response:
        actor = authorize(db, token, case_id)
        row = db.scalar(
            select(NativeResponseReceiptRow).where(
                NativeResponseReceiptRow.id == reference,
                NativeResponseReceiptRow.company_id == actor.company_id,
                NativeResponseReceiptRow.case_id == case_id,
            )
        )
        if row is None:
            raise ProtectedResourceNotFound()
        scope = NativeResponseScope(
            actor.company_id, case_id, row.context_version, row.operation_id
        )
        raw = NativeResponseArchive(scope, objects, index).read(reference)
        return Response(
            raw,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="native-response-{reference}.bin"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox; default-src 'none'",
            },
        )
