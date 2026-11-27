"""Native receive, original inspection and explicit offline contract intake.

No format instruction, prose conversion or returned-URL fetch. The private runtime
must separately bind a fresh finite stage grant to receive. Offline intake reuses
existing semantic/confirmation/design validation; it sends no provider request.
"""

import json
from collections.abc import Callable, Iterator
from typing import Annotated, Any, Final, Literal, cast
from uuid import UUID, uuid4

from fastapi import Cookie, Depends, FastAPI, Header, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import select

from .application import AcceptanceService
from .auth_boundary import SESSION_COOKIE
from .authorization import authorized_case_access, resolve_actor, resolve_session
from .content_storage import EvidenceObjectStore
from .domain import (
    Actor,
    ApplicationError,
    ApplicationPersistence,
    CaseRecord,
    ConfigurationUnavailable,
    Conflict,
    Forbidden,
    ProtectedResourceNotFound,
    SemanticValidationFailed,
    StaleVersion,
)
from .foundry_report_runtime import CURRENT, Reservations
from .foundry_v10_demo_receiver import V10DemoReceiver
from .foundry_v10_report_transport import V10Operation
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
from .native_goal_context import (
    analysis_display as _analysis_display,
)
from .native_goal_context import (
    assistant_texts,
    goal_analysis_request,
    goal_only_context,
    prior_analysis_receipts,
)
from .native_response_archive import NativeResponseArchive, NativeResponseScope
from .native_response_index import (
    DatabaseNativeResponseIndex,
    NativeContractBindingRow,
    NativeReceiveCommandRow,
    NativeResponseReceiptRow,
)
from .native_response_probe import (
    native_input_characters,
    native_request_content,
    receive_native_response,
)
from .persistence import ApplicationSession as Session
from .persistence import Database
from .provider_diagnostics import safe_provider_diagnostic
from .request_outputs import (
    OutputInputError,
    V10ReportSave,
    has_v10_history,
    v10_binding_metadata,
    v10_command_key,
    v10_output_for_receipt,
)
from .tenant_settings import TenantSettingsSnapshot

FULL_REPORT: Final = "FULL_REPORT_ARTIFACT"
ANALYSIS: Final = "REQUIREMENT_ANALYSIS"
NativePurpose = Literal["REQUIREMENT_ANALYSIS", "REPORT_DESIGN", "FULL_REPORT_ARTIFACT"]
DemoPurpose = Literal["REQUIREMENT_ANALYSIS", "FULL_REPORT_ARTIFACT"]


class NativeReceiveCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_context_version: int = Field(ge=1, strict=True)
    expected_settings_id: UUID
    command_key: UUID
    task: NativePurpose = ANALYSIS
    confirmed_contract_id: UUID | None = None
    explicit_demo_action: StrictBool | None = None


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
    v10_receiver: V10DemoReceiver | None = None,
    save_v10_report: V10ReportSave | None = None,
    require_qualified_profile: Callable[[ProviderProfile], None],
) -> None:
    index = DatabaseNativeResponseIndex(database)
    # Public correlation only; never an approval or credential.
    connection_id = str(uuid4())

    def sessions() -> Iterator[Session]:
        with database.session() as db:
            yield cast(Session, db)

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
        binding = db.get(NativeContractBindingRow, command.id)
        demo = v10_binding_metadata(binding)
        result = {
            "task": demo["purpose"] if demo else binding.task if binding is not None else None,
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
        if demo and demo["purpose"] == FULL_REPORT:
            result["report_output"] = v10_output_for_receipt(db, receipt) if receipt else None
        return result

    def prepare_request(
        db: Session, actor: Actor, case: CaseRecord, snapshot: TenantSettingsSnapshot,
        task: str = "REQUIREMENT_ANALYSIS", contract_id: UUID | None = None,
    ) -> tuple[ProviderRequest | None, dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
        store = cast(ApplicationPersistence, db)
        service = service_for(db, snapshot, include_provider=False)
        bundle = prepare_case_files(
            store, case, objects, service.reference_objects,
            max_file_bytes=snapshot.settings.upload_policy.max_file_bytes,
            vision_enabled=bool(snapshot.settings.provider_profile
                                and snapshot.settings.provider_profile.capabilities.vision),
        )
        goal_only = not bundle.manifest
        availability = {
            "files": bundle.manifest,
            "ready": bundle.ready or goal_only,
            "scope": "CURRENT_REQUEST_VERSION",
            "request_version_id": str(case.current_request_version_id),
            "context_version": case.semantic_context_version,
            "settings_id": str(snapshot.id),
            "reason": None if bundle.ready or goal_only else "COMPLETE_FILE_HANDOFF_UNAVAILABLE",
            "input_characters": None,
            "input_limit": (snapshot.settings.provider_profile.max_input_characters
                            if snapshot.settings.provider_profile else None),
        }
        if not availability["ready"]:
            return None, availability, [], []
        if goal_only:
            request = goal_analysis_request(db, case, objects, service)
        else:
            schema, context_binding, _ = service._current_context(store, case, include_history=True)
            # Carry prior AI questions forward with the user's durable answers.
            # Only assistant text is projected; raw provider/tool/diagnostic bodies
            # remain private. Full context still passes the configured input bound.
            prior_answers = []
            if task == "REQUIREMENT_ANALYSIS":
                prior_receipts = prior_analysis_receipts(
                    db, actor.company_id, case.id, case.semantic_context_version,
                )
                for prior in prior_receipts:
                    raw = NativeResponseArchive(NativeResponseScope(
                        actor.company_id, case.id, prior.context_version, prior.operation_id,
                    ), objects, index).read(prior.id)
                    prior_answers.append({"receiptId": str(prior.id),
                                          "contextVersion": prior.context_version,
                                          "assistantTexts": assistant_texts(raw)})
            policy = service.clarification_policy
            if policy is None or service.generation_policy is None:
                raise ConfigurationUnavailable()
            request = ProviderRequest(
                task="REQUIREMENT_ANALYSIS", system_prompt="", output_schema={},
                requires_vision=bool(bundle.image_parts),
                context={
                    "materialContext": json.loads(context_binding),
                    "priorAgentAnswers": prior_answers,
                    "clarificationState": service.clarification_state(store, case.id),
                    "dataStructure": schema,
                    "caseFiles": bundle.sources,
                    "fileDelivery": {"transport": ("NO_ATTACHED_FILES" if goal_only else
                                                   "INLINE_ORIGINAL_FILES" if bundle.file_parts else
                                                   "INLINE_SOURCE_AND_IMAGES" if bundle.image_parts
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
        if task == "REPORT_DESIGN" and goal_only:
            if contract_id is None:
                raise Conflict()
            _, session, confirmed = service.native_goal_confirmed(store, case, contract_id)
            request = ProviderRequest(task="REPORT_DESIGN", system_prompt="", output_schema={},
                requires_vision=False, context={
                    "confirmedRequirements": confirmed,
                    "materialContext": goal_only_context(store, case),
                    "dataStructure": None, "caseFiles": [],
                    "fileDelivery": {"transport": "NO_ATTACHED_FILES", "sampled": False,
                                     "serviceFileUploaded": False, "processingVerified": False},
                    "generationPolicy": service.generation_policy,
                })
        elif task == FULL_REPORT:
            if contract_id is None or goal_only:
                raise Conflict()
            # This purpose uses the existing confirmed-contract validation, but
            # leaves design and compilation to the selected Foundry agent.
            contract = store.confirmed_contract_for_case(case.id, contract_id)
            latest = store.latest_interpretation(case.id)
            if (contract is None or latest is None or contract.interpretation_id != latest.id
                    or latest.context_version != case.semantic_context_version
                    or latest.request_version_id != case.current_request_version_id
                    or contract.settings_version_id != snapshot.id):
                raise StaleVersion()
            source_receipt = db.scalar(
                select(NativeResponseReceiptRow).join(
                    NativeReceiveCommandRow,
                    NativeReceiveCommandRow.id == NativeResponseReceiptRow.operation_id,
                ).where(
                    NativeResponseReceiptRow.company_id == actor.company_id,
                    NativeResponseReceiptRow.case_id == case.id,
                    NativeReceiveCommandRow.actor_membership_id == actor.membership_id,
                    NativeReceiveCommandRow.command_key == v10_command_key(
                        actor.company_id, case.id, ANALYSIS),
                    NativeReceiveCommandRow.context_version == case.semantic_context_version,
                    NativeReceiveCommandRow.settings_id == snapshot.id,
                    NativeReceiveCommandRow.state == "RECEIVED",
                    NativeReceiveCommandRow.provider_status == "completed",
                )
            )
            provenance = json.loads(latest.session_json).get("providerProvenance", {})
            source_binding = (db.get(NativeContractBindingRow, source_receipt.operation_id)
                              if source_receipt is not None else None)
            demo_analysis = v10_binding_metadata(source_binding)
            if (source_receipt is None or source_binding is None or v10_receiver is None
                    or not demo_analysis or demo_analysis["purpose"] != ANALYSIS
                    or provenance.get("sourceReceiptId") != str(source_receipt.id)
                    or demo_analysis["grant_sha256"] != v10_receiver.grant_sha256
                    or json.loads(source_binding.metadata_json).get("qualification")
                    != v10_receiver.qualification):
                raise Conflict()
            request = ProviderRequest(task="REPORT_DESIGN", system_prompt="", output_schema={},
                requires_vision=False, context={
                    "confirmedRequirements": _provider_confirmed_requirements(
                        json.loads(contract.contract_json)),
                    "dataStructure": request.context["dataStructure"],
                    "generationPolicy": service.generation_policy,
                    "caseFiles": bundle.sources,
                    "fileDelivery": request.context["fileDelivery"],
                })
        elif task == "REPORT_DESIGN":
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
            return None, availability, [], []
        try:
            content = native_request_content(
                profile, request, bundle.image_parts, bundle.file_parts,
            )
        except ProviderCallError:
            availability.update(ready=False, reason="MODEL_INPUT_BUDGET_EXCEEDED")
            return None, availability, [], []
        availability["input_characters"] = native_input_characters(
            content, bundle.image_parts, bundle.file_parts,
        )
        return request, availability, bundle.image_parts, bundle.file_parts

    def nominated(actor: Actor, case_id: UUID) -> bool:
        return (v10_receiver is not None and v10_receiver.case.company_id == actor.company_id
                and v10_receiver.case.case_id == case_id)

    def v10_inputs(
        db: Session, actor: Actor, case: CaseRecord, snapshot: TenantSettingsSnapshot,
        purpose: DemoPurpose,
        contract_id: UUID | None, operation_id: UUID, request: ProviderRequest,
    ) -> tuple[V10Operation, ProviderProfile]:
        assert v10_receiver is not None
        profile = snapshot.settings.provider_profile
        version = cast(ApplicationPersistence, db).request_version(case.current_request_version_id)
        sources = request.context.get("caseFiles", [])
        if (not snapshot.settings.automatic_generation_enabled or profile is None
                or profile.protocol != "FOUNDRY_AGENT_RESPONSES"
                or snapshot.secret_reference_id is not None or version is None
                or request.requires_vision or len(sources) != 1
                or sources[0].get("transport") != "INLINE_UTF8_SOURCE"):
            raise NativeInputsUnavailable()
        source = sources[0]
        if purpose == FULL_REPORT and contract_id is None:
            raise Conflict()
        require_qualified_profile(profile)
        config = v10_receiver.case
        return V10Operation(
            scope=NativeResponseScope(actor.company_id, case.id, case.semantic_context_version,
                                      operation_id),
            purpose=purpose, project_url=config.project_url, agent_name=config.agent_name,
            knowledge_binding=config.knowledge_binding, knowledge_scope=config.knowledge_scope,
            profile_sha256=digest(profile.model_dump(mode="json")),
            context_sha256=digest(request.context),
            source_id=UUID(source["id"]), request_version_id=version.id,
            source_digest=source["contentDigest"], goal=version.request_text,
        ), profile

    def v10_command(db: Session, actor: Actor, case_id: UUID, purpose: str
                    ) -> NativeReceiveCommandRow | None:
        key = v10_command_key(actor.company_id, case_id, purpose)
        return db.scalar(select(NativeReceiveCommandRow).where(
            NativeReceiveCommandRow.company_id == actor.company_id,
            NativeReceiveCommandRow.case_id == case_id,
            NativeReceiveCommandRow.command_key == key,
        ))

    def receive_v10(
        db: Session, actor: Actor, case_id: UUID, payload: NativeReceiveCreate,
        token: str | None,
    ) -> dict[str, Any]:
        if (v10_receiver is None or payload.explicit_demo_action is not True
                or payload.task not in (ANALYSIS, FULL_REPORT)):
            raise ConfigurationUnavailable()
        purpose = cast(DemoPurpose, payload.task)
        session, _ = resolve_session(db, token)
        active = cast(ApplicationPersistence, db).active_actor(
            actor.membership_id, actor.identity_id, lock=True
        )
        if active != actor or not actor.role.can_invite:
            raise ProtectedResourceNotFound()
        authorized_case_access(db, actor, case_id, require_edit=True, lock=True)
        case = cast(ApplicationPersistence, db).locked_case(case_id)
        if case is None:
            raise ProtectedResourceNotFound()
        snapshot = snapshot_for(db, actor)
        if (case.semantic_context_version != payload.expected_context_version
                or snapshot.id != payload.expected_settings_id):
            raise StaleVersion()
        previous = v10_command(db, actor, case.id, purpose)
        if previous is not None:
            binding = db.get(NativeContractBindingRow, previous.id)
            demo = v10_binding_metadata(binding)
            if (not demo or binding is None or previous.actor_membership_id != actor.membership_id
                    or demo["session_id"] != str(session.id) or demo["purpose"] != purpose
                    or demo["grant_sha256"] != v10_receiver.grant_sha256
                    or previous.settings_id != snapshot.id
                    or previous.context_version != case.semantic_context_version
                    or binding.contract_id != payload.confirmed_contract_id):
                raise Conflict()
            return {"native_response": summary(db, previous)}
        if purpose == FULL_REPORT:
            analysis = v10_command(db, actor, case_id, ANALYSIS)
            admission = (db.get(NativeContractBindingRow, analysis.id)
                         if analysis is not None else None)
            if v10_binding_metadata(admission).get("session_id") != str(session.id):
                raise Conflict()
        request, availability, images, files = prepare_request(
            db, actor, case, snapshot, purpose, payload.confirmed_contract_id
        )
        if request is None or not availability["ready"] or images or files:
            raise NativeInputsUnavailable()
        operation, profile = v10_inputs(db, actor, case, snapshot, purpose,
                                       payload.confirmed_contract_id, uuid4(), request)
        claimed = False

        def verify(check_db: Session) -> bool:
            check_db.expire_all()
            actual = authorize(check_db, token, case_id)
            active_session, _ = resolve_session(check_db, token)
            if actual != actor or active_session.id != session.id:
                return False
            current_case, _ = authorized_case_access(check_db, actual, case_id, require_edit=True)
            current = snapshot_for(check_db, actual)
            if (current_case.current_request_version_id != operation.request_version_id
                    or current_case.semantic_context_version != operation.scope.context_version
                    or current.id != snapshot.id or current.digest != snapshot.digest):
                return False
            candidate, readiness, pictures, attachments = prepare_request(
                check_db, actual, current_case, current, purpose, payload.confirmed_contract_id
            )
            if candidate is None or not readiness["ready"] or pictures or attachments:
                return False
            fresh, _ = v10_inputs(
                check_db, actual, current_case, current, purpose, payload.confirmed_contract_id,
                operation.scope.operation_id, candidate,
            )
            return fresh == operation

        def current() -> bool:
            with database.session() as fresh_db:
                return verify(cast(Session, fresh_db))

        def claim() -> bool:
            # Only this handler can dispatch the admission it successfully
            # committed. Concurrent callers and restarts return the saved row.
            nonlocal claimed
            if claimed:
                return False
            with database.session() as fresh_db:
                db_session = cast(Session, fresh_db)
                admitted = v10_command(db_session, actor, case_id, purpose)
                if (admitted is None or admitted.id != operation.scope.operation_id
                        or admitted.state != "ADMITTED" or not verify(db_session)):
                    return False
                claimed = True
                return True

        try:
            exchange = v10_receiver.open(
                operation, actor_id=actor.identity_id, membership_id=actor.membership_id,
                session_id=session.id, settings_id=snapshot.id, settings_digest=snapshot.digest,
                current=current, claim=claim,
            )
        except ProviderCallError:
            raise ConfigurationUnavailable() from None
        command = NativeReceiveCommandRow(
            id=operation.scope.operation_id, company_id=actor.company_id, case_id=case_id,
            actor_membership_id=actor.membership_id,
            context_version=operation.scope.context_version,
            settings_id=snapshot.id,
            command_key=v10_command_key(actor.company_id, case_id, purpose),
            state="ADMITTED",
        )
        db.add(command)
        db.flush()
        db.add(NativeContractBindingRow(
            operation_id=command.id, company_id=actor.company_id, case_id=case_id,
            context_version=command.context_version, task=request.task,
            contract_id=payload.confirmed_contract_id,
            input_digest=digest({"task": request.task, "context": request.context, "images": []}),
            profile_digest=digest(profile.model_dump()),
            metadata_json=json.dumps({
                "v10_demo": {"purpose": purpose, "session_id": str(session.id),
                             "request_version_id": str(operation.request_version_id),
                             "source_sha256": operation.source_digest,
                             "context_sha256": operation.context_sha256,
                             "grant_sha256": v10_receiver.grant_sha256},
                "knowledge_binding": operation.knowledge_binding,
                "knowledge_scope": operation.knowledge_scope,
                "agent_version": "10",
                "qualification": v10_receiver.qualification,
            }, sort_keys=True, separators=(",", ":")),
        ))
        cast(ApplicationPersistence, db).add_audit(
            actor, "NATIVE_V10_STAGE_ADMITTED", "NATIVE_RECEIVE_COMMAND", command.id,
            json.dumps({
                "purpose": purpose, "request_version_id": str(operation.request_version_id),
            }),
        )
        db.commit()

        archive = NativeResponseArchive(operation.scope, objects, index)
        original = None
        try:
            result = exchange.send(profile, request, archive=archive)
            command.state = result.status
            command.http_status = result.http_status
            command.provider_status = result.provider_status
            diagnostic = result.diagnostic
            if (purpose == FULL_REPORT and result.provider_status == "completed"
                    and result.receipt is not None and save_v10_report is not None):
                try:
                    original = exchange.read_report(
                        profile, archive=archive, receipt_id=result.receipt.id,
                    )
                except ProviderCallError as exc:
                    diagnostic = exc.diagnostic
        except ProviderCallError as exc:
            command.state = "UNCERTAIN"
            diagnostic = exc.diagnostic
        safe = safe_provider_diagnostic(diagnostic)
        encoded = json.dumps(safe, sort_keys=True, separators=(",", ":"))
        command.diagnostic_json = encoded if len(encoded.encode("utf-8")) <= 4096 else "{}"
        db.commit()
        # Save the exact file already read for this operation. A failed
        # storage/ACL check cannot cause another provider call.
        if original is not None and save_v10_report is not None:
            def guard(save_db: Session) -> None:
                # Native session validation touches the password session row.
                # Reuse the save transaction to avoid waiting on its own lock.
                if not verify(save_db) or not exchange.report_save_lease_current():
                    raise StaleVersion()

            try:
                save_v10_report(db, token, case_id, command.context_version, original, guard)
            except OutputInputError:
                # The response receipt remains available even when an unsafe
                # file cannot enter the case's downloadable output history.
                pass
        authorize(db, token, case_id)
        return {"native_response": summary(db, command)}

    @app.get("/api/cases/{case_id}/native-response-input")
    def inspect_input(
        case_id: UUID,
        response: Response,
        db: Annotated[Session, Depends(sessions)],
        task: NativePurpose = ANALYSIS,
        confirmed_contract_id: UUID | None = None,
        token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, Any]:
        actor = authorize(db, token, case_id)
        case, _ = authorized_case_access(db, actor, case_id, require_edit=True)
        if case is None:
            raise ProtectedResourceNotFound()
        response.headers["Cache-Control"] = "no-store"
        snapshot = snapshot_for(db, actor)
        demo = nominated(actor, case_id) or has_v10_history(db, actor.company_id, case_id)
        if task == FULL_REPORT and not demo:
            raise ConfigurationUnavailable()
        request, availability, images, files = prepare_request(
            db, actor, case, snapshot, task, confirmed_contract_id,
        )
        can_receive = False
        selected_connection = None
        if demo:
            availability["demo_mode"] = "FOUNDRY_V10"
            if (v10_receiver is not None and task in (ANALYSIS, FULL_REPORT)
                    and request is not None and availability["ready"]
                    and not images and not files and not v10_command(db, actor, case_id, task)):
                try:
                    purpose = cast(DemoPurpose, task)
                    operation, _ = v10_inputs(
                        db, actor, case, snapshot, purpose, confirmed_contract_id, uuid4(), request,
                    )
                    session, _ = resolve_session(db, token)
                    can_receive = v10_receiver.permits(
                        operation, actor_id=actor.identity_id, membership_id=actor.membership_id,
                        session_id=session.id, settings_id=snapshot.id,
                        settings_digest=snapshot.digest,
                    )
                    if can_receive:
                        selected_connection = v10_receiver.connection_id(purpose)
                except (ApplicationError, ProviderCallError):
                    pass
        elif receive_enabled and reservations is not None:
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
            selected_connection = connection_id if can_receive else None
        availability.update(
            receive_available=can_receive,
            receive_reason=("AUTHORIZED_SINGLE_RESPONSE_READY" if can_receive
                            else "PRIVATE_AUTHORIZATION_UNAVAILABLE"),
            connection_id=selected_connection,
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
        if not receive_enabled and v10_receiver is None:
            raise ConfigurationUnavailable()
        require_csrf(token, csrf)
        actor = authorize(db, token, case_id)
        if nominated(actor, case_id):
            return receive_v10(db, actor, case_id, payload, token)
        if has_v10_history(db, actor.company_id, case_id):
            raise ConfigurationUnavailable()
        store = cast(ApplicationPersistence, db)
        case = store.locked_case(case_id)
        if case is None:
            raise ProtectedResourceNotFound()
        if payload.task == FULL_REPORT or payload.explicit_demo_action is not None:
            raise ConfigurationUnavailable()
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
        native_request, availability, image_parts, file_parts = prepare_request(
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
                                 "images": image_parts,
                                 **({"files": file_parts} if file_parts else {})}),
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
                archive=archive, image_parts=image_parts, file_parts=file_parts,
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
        demo = v10_binding_metadata(binding)
        if demo and demo["purpose"] == FULL_REPORT:
            return command, binding, None, {
                "code": "NATIVE_OUTPUT_ARTIFACT_ONLY", "phase": "NATIVE_BINDING", "findings": [],
            }
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
        preview = None
        if (candidate is not None and binding is not None and case is not None
                and binding.task == "REQUIREMENT_ANALYSIS"
                and case.semantic_context_version == command.context_version):
            store = cast(ApplicationPersistence, db)
            rows = [*store.evidence_items(case.id), *store.reference_materials(case.id)]
            if any(getattr(row, "company_id", None) != actor.company_id
                   or getattr(row, "case_id", None) != case.id for row in rows):
                raise SemanticValidationFailed()
            if not any(getattr(row, "request_version_id", None) == case.current_request_version_id
                       for row in rows):
                request, availability, images, files = prepare_request(
                    db, actor, case, snapshot, binding.task, binding.contract_id,
                )
                if (request is not None and availability["ready"]
                        and binding.input_digest == digest({
                        "task": request.task, "context": request.context, "images": images,
                        **({"files": files} if files else {})})):
                    preview = _analysis_display(candidate.value, reference, command.context_version)
        return {"analysis_preview": preview, "recognized": candidate is not None,
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
        demo = v10_binding_metadata(binding)
        if demo:
            session, _ = resolve_session(db, token)
            if (command.actor_membership_id != actor.membership_id
                    or demo["session_id"] != str(session.id)
                    or demo["request_version_id"] != str(case.current_request_version_id)):
                raise ProtectedResourceNotFound()
        acceptance = service_for(db, snapshot, include_provider=False)
        if binding.task == "REQUIREMENT_ANALYSIS":
            existing = store.interpretation_for_context(case_id, case.semantic_context_version)
            if existing is not None:
                session = json.loads(existing.session_json)
                if session.get("providerProvenance", {}).get("sourceReceiptId") != str(reference):
                    raise Conflict()
                from .native_goal_context import GOAL_INTERPRETATION
                if session.get("kind") == GOAL_INTERPRETATION:
                    acceptance._validated_native_goal_context(store, case, existing)
                else:
                    acceptance._validated_interpretation_context(store, case, existing)
                return {"accepted": True, "task": binding.task,
                        "interpretation": acceptance.state(db, actor, case_id)["interpretation"]}
        request, availability, images, files = prepare_request(
            db, actor, case, snapshot, binding.task, binding.contract_id,
        )
        if (request is None or not availability["ready"] or binding.input_digest != digest({
                "task": request.task, "context": request.context, "images": images,
                **({"files": files} if files else {})})):
            raise StaleVersion()
        if binding.task == "REQUIREMENT_ANALYSIS":
            current_files = [*store.evidence_items(case.id), *store.reference_materials(case.id)]
            if not any(getattr(row, "request_version_id", None)
                       == case.current_request_version_id for row in current_files):
                result = acceptance.admit_native_goal_analysis(
                    db, actor, case_id, reference,
                    expected_context_version=case.semantic_context_version,
                )
            else:
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
