import json
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Cookie, Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .application import (
    AcceptanceService,
    AnalysisAttemptFailed,
    CaseService,
    CompanyService,
    ConversationService,
    EvidenceService,
    InvitationService,
    MembershipService,
    ProfileService,
)
from .artifacts import LocalArtifactStore
from .auth_boundary import (
    AUTH_BINDING_COOKIE,
    SESSION_COOKIE,
    AuthStart,
    cookie_secure,
    csrf_matches,
    csrf_token,
    digest,
    pkce_challenge,
    random_token,
)
from .authorization import resolve_actor, resolve_session
from .bootstrap import BOOTSTRAP_IDENTITIES
from .config import ClarificationPolicy, Settings, UploadPolicy, get_settings
from .content_storage import (
    ArtifactObjectStore,
    EvidenceObjectStore,
)
from .domain import (
    AccessLevel,
    Actor,
    ApplicationError,
    AuthenticationRequired,
    ConfigurationUnavailable,
    Conflict,
    EvidenceInvalid,
    Role,
)
from .evidence import LocalEvidenceStore
from .generation import GenerationBridge, GenerationService
from .identity_service import IdentityService
from .model_provider import (
    ModelProvider,
    OpenAICompatibleProvider,
    ProviderConfigurationError,
)
from .oidc_adapter import OidcAdapter
from .persistence import (
    ApplicationSession,
    AuditEventRow,
    AuthorizationCodeRow,
    AuthTransactionRow,
    CompanyRow,
    Database,
    MembershipRow,
    SessionRow,
    TenantSecretRow,
)
from .reference_material import ReferenceMaterialService
from .semantic_bridge import SemanticBridge
from .tenant_secrets import AesGcmTenantCredentialStore, credential_status
from .tenant_settings import (
    TenantSettings,
    TenantSettingsSnapshot,
    admin_settings,
    current_settings,
    restore_settings,
    settings_history,
    update_settings,
    validate_qualified_profile,
)

logger = logging.getLogger("apbra_api")


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_text: str = Field(min_length=1, max_length=20_000)


class CaseUpdate(CaseCreate):
    expected_version: int = Field(ge=1)


class CaseAccessGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    membership_id: UUID
    access_level: AccessLevel


class InvitationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=1, max_length=255)
    role: Role
    expires_in_days: int | None = Field(default=None, ge=1, le=30)


class InvitationToken(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=40, max_length=200)


class ConversationEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(min_length=1, max_length=40)
    payload: dict[str, Any]
    expected_context_version: int = Field(ge=1)
    command_key: str = Field(min_length=8, max_length=200)


class InterpretationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_context_version: int = Field(ge=1)


class InterpretationConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interpretation_id: UUID
    expected_context_version: int = Field(ge=1)


class ClarificationCycleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_context_version: int = Field(ge=1)
    command_key: str = Field(min_length=8, max_length=200)
    enhancement: str = Field(default="", max_length=20_000)


class GenerationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed_contract_id: UUID
    command_key: str = Field(min_length=8, max_length=200)
    mode: str = Field(default="BUILD", pattern="^(BUILD|RETRY|REGENERATE)$")
    source_attempt_id: UUID | None = None
    reviewed_design_id: UUID | None = None


class ReviewedDesignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed_contract_id: UUID
    report_design: dict[str, Any]


class AutomaticDesignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed_contract_id: UUID
    command_key: str = Field(min_length=8, max_length=200)


class TenantSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    settings: TenantSettings
    reason: str | None = Field(default=None, max_length=500)


class TenantSettingsRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_version: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)
    confirm_consequences: bool


class TenantCredentialReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    new_credential: SecretStr = Field(min_length=1, max_length=16_384)
    confirm_disruption: bool


class CompanySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    membership_id: UUID


class CompanyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str


class MembershipRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal[Role.MEMBER, Role.COMPANY_ADMIN]


def error_response(exc: ApplicationError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.public_message}},
    )


def invitation_json(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "company_id": str(row.company_id),
        "subject": row.invited_subject,
        "role": row.role,
        "expires_at": row.expires_at.isoformat(),
    }


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    oidc: OidcAdapter | None = None,
    model_provider: ModelProvider | None = None,
    evidence_objects: EvidenceObjectStore | None = None,
    reference_objects: EvidenceObjectStore | None = None,
    artifact_objects: ArtifactObjectStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_security_profile()
    qualified_profiles = settings.qualified_provider_profiles()
    database = database or Database(settings.database_url)
    oidc = oidc or OidcAdapter(settings)
    case_service = CaseService()
    company_service = CompanyService()
    profile_service = ProfileService()
    credential_store = AesGcmTenantCredentialStore.from_bootstrap(
        settings.tenant_secret_keyring_json.get_secret_value()
        if settings.tenant_secret_keyring_json
        else None
    )
    artifact_store: ArtifactObjectStore | None = artifact_objects
    evidence_store: EvidenceObjectStore | None = evidence_objects
    reference_store: EvidenceObjectStore | None = reference_objects
    if settings.profile in {"development", "test"}:
        if artifact_store is None:
            artifact_store = LocalArtifactStore(settings.artifact_root, settings.profile)
        if evidence_store is None:
            evidence_store = LocalEvidenceStore(settings.evidence_root, settings.profile)
        if reference_store is None and settings.reference_root is not None:
            reference_store = LocalEvidenceStore(settings.reference_root, settings.profile)
    invitation_service = InvitationService()
    identity_service = IdentityService()
    membership_service = MembershipService()
    app = FastAPI(title="APBRA API", version="0.1.0")

    def db_session() -> Iterator[Session]:
        with database.session() as db:
            yield db

    DB = Annotated[Session, Depends(db_session)]
    SessionCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]

    def require_csrf(session_token: str | None, supplied: str | None) -> None:
        if not session_token or not csrf_matches(session_token, supplied, settings.session_secret):
            exc = AuthenticationRequired()
            exc.code = "CSRF_INVALID"
            exc.public_message = "The request could not be verified. Refresh and try again."
            raise exc

    def tenant_snapshot(db: Session, actor: Actor) -> TenantSettingsSnapshot:
        return current_settings(db, actor.company_id)

    def tenant_model_provider(
        db: Session, snapshot: TenantSettingsSnapshot
    ) -> ModelProvider | None:
        policy = snapshot.settings
        if (
            settings.profile == "test"
            and settings.test_semantic_simulator_enabled
            and model_provider is not None
        ):
            # Explicit dependency injection exercises deterministic model
            # contracts without changing persisted tenant policy or making calls.
            return model_provider
        if not policy.automatic_generation_enabled:
            return None
        profile = policy.provider_profile
        if profile is None or snapshot.secret_reference_id is None:
            raise ConfigurationUnavailable()
        validate_qualified_profile(profile, qualified_profiles)
        if credential_store is None:
            raise ConfigurationUnavailable()
        credential = credential_store.resolve(
            db,
            company_id=snapshot.company_id,
            profile_id=profile.profile_id,
            reference_id=snapshot.secret_reference_id,
        )
        return OpenAICompatibleProvider(profile, credential)

    def local_evidence_service(snapshot: TenantSettingsSnapshot) -> EvidenceService:
        if evidence_store is None:
            raise ConfigurationUnavailable()
        return EvidenceService(
            evidence_store,
            snapshot.settings.upload_policy,
        )

    def local_upload_policy(snapshot: TenantSettingsSnapshot) -> UploadPolicy:
        return snapshot.settings.upload_policy

    def local_acceptance_service(
        db: Session, snapshot: TenantSettingsSnapshot
    ) -> AcceptanceService:
        if settings.semantic_timeout_seconds is None:
            raise ConfigurationUnavailable()
        objects = local_evidence_service(snapshot).objects
        reference_service = local_reference_service(snapshot)
        clarification_policy = ClarificationPolicy(
            max_rounds=snapshot.settings.max_clarification_rounds_per_cycle,
            max_questions_per_round=snapshot.settings.clarification_policy.max_questions_per_round,
            max_answer_characters=snapshot.settings.clarification_policy.max_answer_characters,
        )
        return AcceptanceService(
            SemanticBridge(
                settings.semantic_bridge_path,
                node_executable=settings.semantic_node_path,
                timeout_seconds=settings.semantic_timeout_seconds,
            ),
            objects,
            reference_objects=(reference_service.objects if reference_service else None),
            model_provider=tenant_model_provider(db, snapshot),
            clarification_policy=clarification_policy,
            generation_policy=snapshot.settings.generation_policy.model_dump(by_alias=True),
            tenant_settings=snapshot,
            allow_test_simulator=(
                settings.profile == "test" and settings.test_semantic_simulator_enabled
            ),
        )

    def local_reference_service(snapshot: TenantSettingsSnapshot) -> ReferenceMaterialService:
        if reference_store is None:
            raise ConfigurationUnavailable()
        return ReferenceMaterialService(
            reference_store,
            snapshot.settings.upload_policy,
        )

    def local_generation_service(
        db: Session, snapshot: TenantSettingsSnapshot, *, require_bridge: bool = False
    ) -> GenerationService:
        if artifact_store is None:
            raise EvidenceInvalid()
        bridge = None
        if require_bridge:
            try:
                if settings.generation_timeout_seconds is None:
                    raise ProviderConfigurationError("GENERATION_TIMEOUT_MISSING")
                bridge = GenerationBridge(
                    settings.generation_bridge_path,
                    node_executable=settings.semantic_node_path,
                    timeout_seconds=settings.generation_timeout_seconds,
                )
            except ValueError as exc:
                raise ConfigurationUnavailable() from exc
        reference_service = local_reference_service(snapshot)
        return GenerationService(
            bridge,
            local_evidence_service(snapshot).objects,
            artifact_store,
            reference_objects=(reference_service.objects if reference_service else None),
            model_provider=tenant_model_provider(db, snapshot),
            generation_policy=snapshot.settings.generation_policy.model_dump(by_alias=True),
            tenant_settings=snapshot,
        )

    def callback_failure_redirect(reason: str) -> RedirectResponse:
        response = RedirectResponse(
            f"{settings.public_origin}/?auth_error={reason}", status_code=302
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.delete_cookie(AUTH_BINDING_COOKIE, path="/api/auth/callback")
        return response

    @app.exception_handler(ApplicationError)
    async def handle_application_error(request: Request, exc: ApplicationError) -> Response:
        if request.url.path == "/api/auth/callback" and "text/html" in request.headers.get(
            "accept", ""
        ):
            return callback_failure_redirect(
                "unavailable" if exc.code == "PROVIDER_UNAVAILABLE" else "invalid"
            )
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, _exc: RequestValidationError) -> Response:
        if request.url.path == "/api/auth/callback" and "text/html" in request.headers.get(
            "accept", ""
        ):
            return callback_failure_redirect("invalid")
        # Validation details can contain bearer credentials (for example an
        # invalid invitation token). Never echo rejected request input.
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "REQUEST_VALIDATION_FAILED",
                    "message": "The request format is invalid.",
                }
            },
        )

    @app.get("/api/health")
    def health(db: DB) -> dict[str, str]:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}

    @app.get("/api/cases/capabilities/uploads")
    def upload_capabilities(db: DB, session_token: SessionCookie = None) -> dict[str, Any]:
        actor = resolve_actor(db, session_token)
        snapshot = tenant_snapshot(db, actor)
        policy = local_upload_policy(snapshot)
        return {
            "data_extensions": policy.data_extensions,
            "reference_extensions": policy.reference_extensions,
            "max_file_bytes": policy.max_file_bytes,
            "max_files_per_selection": policy.max_files_per_selection,
            "max_answer_characters": snapshot.settings.clarification_policy.max_answer_characters,
        }

    def settings_response(db: Session, snapshot: TenantSettingsSnapshot) -> dict[str, Any]:
        return {
            "id": str(snapshot.id),
            "version": snapshot.version,
            "digest": snapshot.digest,
            "validation_status": snapshot.validation_status,
            "applicability": "COMPANY_NEW_OR_REVALIDATED_OPERATIONS",
            "settings": snapshot.settings.model_dump(mode="json", by_alias=True),
            "credential": credential_status(
                db,
                company_id=snapshot.company_id,
                reference_id=snapshot.secret_reference_id,
            ),
        }

    @app.get("/api/tenant-settings")
    def get_tenant_settings(db: DB, session_token: SessionCookie = None) -> dict[str, Any]:
        actor = resolve_actor(db, session_token)
        return settings_response(db, admin_settings(db, actor))

    @app.get("/api/tenant-settings/history")
    def get_tenant_settings_history(db: DB, session_token: SessionCookie = None) -> dict[str, Any]:
        return {"items": settings_history(db, resolve_actor(db, session_token))}

    @app.get("/api/tenant-settings/qualified-profiles")
    def get_qualified_profiles(db: DB, session_token: SessionCookie = None) -> dict[str, Any]:
        admin_settings(db, resolve_actor(db, session_token))
        return {"items": [profile.model_dump(mode="json") for profile in qualified_profiles]}

    @app.put("/api/tenant-settings")
    def put_tenant_settings(
        payload: TenantSettingsUpdate,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, csrf)
        actor = resolve_actor(db, session_token)
        snapshot = update_settings(
            db,
            actor,
            payload.settings,
            expected_version=payload.expected_version,
            reason=payload.reason,
            credential_store=credential_store,
            qualified_profiles=qualified_profiles,
        )
        assert isinstance(db, ApplicationSession)
        db.add_audit(actor, "TENANT_SETTINGS_UPDATED", "TENANT_SETTINGS_VERSION", snapshot.id)
        db.commit()
        return settings_response(db, snapshot)

    @app.post("/api/tenant-settings/restore")
    def post_tenant_settings_restore(
        payload: TenantSettingsRestore,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, csrf)
        if not payload.confirm_consequences:
            raise Conflict()
        actor = resolve_actor(db, session_token)
        snapshot = restore_settings(
            db,
            actor,
            source_version=payload.source_version,
            expected_version=payload.expected_version,
            reason=payload.reason,
            credential_store=credential_store,
            qualified_profiles=qualified_profiles,
        )
        assert isinstance(db, ApplicationSession)
        db.add_audit(actor, "TENANT_SETTINGS_RESTORED", "TENANT_SETTINGS_VERSION", snapshot.id)
        db.commit()
        return settings_response(db, snapshot)

    @app.post("/api/tenant-settings/credential")
    def post_tenant_credential(
        payload: TenantCredentialReplace,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, csrf)
        if not payload.confirm_disruption or credential_store is None:
            raise ConfigurationUnavailable()
        actor = resolve_actor(db, session_token)
        current = admin_settings(db, actor)
        if current.version != payload.expected_version or current.settings.provider_profile is None:
            raise Conflict()
        reference = credential_store.protect(
            db,
            company_id=actor.company_id,
            profile_id=current.settings.provider_profile.profile_id,
            credential=payload.new_credential.get_secret_value(),
            actor_membership_id=actor.membership_id,
        )
        snapshot = update_settings(
            db,
            actor,
            current.settings,
            expected_version=payload.expected_version,
            reason="Credential replaced",
            secret_reference_id=reference,
            credential_store=credential_store,
            qualified_profiles=qualified_profiles,
        )
        if current.secret_reference_id is not None:
            previous = db.scalar(
                select(TenantSecretRow).where(
                    TenantSecretRow.id == current.secret_reference_id,
                    TenantSecretRow.company_id == actor.company_id,
                )
            )
            if previous is not None:
                previous.revoked_at = datetime.now(UTC)
        assert isinstance(db, ApplicationSession)
        db.add_audit(actor, "TENANT_CREDENTIAL_REPLACED", "TENANT_SETTINGS_VERSION", snapshot.id)
        db.commit()
        return settings_response(db, snapshot)

    @app.get("/api/auth/providers")
    def auth_providers() -> dict[str, Any]:
        return {
            "items": oidc.public_providers(),
            "development_identities": (
                [item.selector for item in BOOTSTRAP_IDENTITIES]
                if settings.profile in {"development", "test"}
                else []
            ),
        }

    @app.get("/api/auth/login")
    def login(
        db: DB,
        identity: str | None = Query(default=None),
        profile_id: str | None = Query(default=None),
        return_to: str = Query(default="/"),
    ) -> Response:
        profile = oidc.profile(profile_id)
        selected_profile_id = oidc.profile_id(profile)
        if settings.profile in {"development", "test"}:
            allowed = {item.selector for item in BOOTSTRAP_IDENTITIES}
            identity = identity or "owner"
            if identity not in allowed:
                raise AuthenticationRequired()
        elif identity is not None:
            raise AuthenticationRequired()
        start = AuthStart.create(return_to)
        authorization_url = oidc.authorization_url(
            state=start.state,
            nonce=start.nonce,
            code_challenge=pkce_challenge(start.verifier),
            identity_selector=identity,
            profile=profile,
        )
        db.add(
            AuthTransactionRow(
                state_digest=digest(start.state),
                browser_binding_digest=digest(start.browser_binding),
                provider_profile_id=selected_profile_id,
                expected_issuer=settings.issuer if profile is None else profile.issuer,
                client_id=settings.oidc_audience if profile is None else profile.client_id,
                redirect_uri=settings.callback_url,
                provider_configuration_digest=settings.identity_profile_digest(profile),
                response_issuer_required=settings.callback_issuer_required,
                nonce=start.nonce,
                code_verifier=start.verifier,
                return_to=start.return_to,
                expires_at=start.expires_at,
            )
        )
        identity_service.record(db, selected_profile_id, "AUTH_LOGIN_STARTED")
        # The browser follows the redirect immediately. Make the one-time
        # transaction visible before returning rather than relying on
        # dependency cleanup after the response has started.
        db.commit()
        response = RedirectResponse(authorization_url, status_code=302)
        response.set_cookie(
            AUTH_BINDING_COOKIE,
            start.browser_binding,
            httponly=True,
            secure=cookie_secure(settings),
            samesite="lax",
            max_age=300,
            path="/api/auth/callback",
        )
        return response

    @app.get("/dev/oidc/authorize")
    def local_authorize(
        db: DB,
        client_id: str,
        redirect_uri: str,
        response_type: str,
        state: str,
        nonce: str,
        code_challenge: str,
        code_challenge_method: str,
        identity: str,
        scope: str = "openid",
    ) -> Response:
        del scope
        if settings.profile not in {"development", "test"}:
            raise AuthenticationRequired()
        identities = {item.selector: item for item in BOOTSTRAP_IDENTITIES}
        if (
            client_id != settings.oidc_audience
            or redirect_uri != settings.callback_url
            or response_type != "code"
            or code_challenge_method != "S256"
            or identity not in identities
            or not state
            or not nonce
            or not code_challenge
        ):
            raise AuthenticationRequired()
        code = random_token(48)
        db.add(
            AuthorizationCodeRow(
                code_digest=digest(code),
                subject=identities[identity].subject,
                display_name=identities[identity].display_name,
                nonce=nonce,
                code_challenge=code_challenge,
                redirect_uri=redirect_uri,
                expires_at=datetime.now(UTC) + timedelta(minutes=2),
            )
        )
        # The callback can arrive before request dependency cleanup; persist
        # the single-use code before sending the redirect that carries it.
        db.commit()
        from urllib.parse import urlencode

        return RedirectResponse(
            f"{redirect_uri}?{urlencode({'code': code, 'state': state, 'iss': settings.issuer})}",
            status_code=302,
        )

    @app.get("/api/auth/callback")
    def callback(
        request: Request,
        db: DB,
        state: str = Query(min_length=1, max_length=500),
        code: str | None = Query(default=None, min_length=1, max_length=2_000),
        error: str | None = Query(default=None, min_length=1, max_length=100),
        iss: str | None = Query(default=None, max_length=1_000),
        auth_binding: Annotated[str | None, Cookie(alias=AUTH_BINDING_COOKIE)] = None,
        prior_session_token: SessionCookie = None,
    ) -> Response:
        state_values = request.query_params.getlist("state")
        code_values = request.query_params.getlist("code")
        error_values = request.query_params.getlist("error")
        issuer_values = request.query_params.getlist("iss")
        if (
            len(state_values) != 1
            or not (
                (len(code_values) == 1 and not error_values)
                or (len(error_values) == 1 and not code_values)
            )
            or len(issuer_values) > 1
            or any(
                not value for value in (*state_values, *code_values, *error_values, *issuer_values)
            )
        ):
            logger.warning("OIDC callback rejected: malformed_response_parameters")
            raise AuthenticationRequired()
        now = datetime.now(UTC)
        transaction = db.scalar(
            select(AuthTransactionRow)
            .where(AuthTransactionRow.state_digest == digest(state))
            .with_for_update()
        )
        profile_valid = transaction is not None
        try:
            profile = (
                oidc.profile(transaction.provider_profile_id) if transaction is not None else None
            )
        except AuthenticationRequired:
            profile = None
            profile_valid = False
        expected_issuer = (
            transaction.expected_issuer
            if transaction is not None and not profile_valid
            else settings.issuer
            if profile is None and transaction is not None
            else profile.issuer
            if profile is not None
            else ""
        )
        expected_client = settings.oidc_audience if profile is None else profile.client_id
        try:
            current_profile_digest = (
                settings.identity_profile_digest(profile)
                if transaction is not None and profile_valid
                else ""
            )
        except ValueError:
            profile_valid = False
            current_profile_digest = ""
        rejection = (
            "state_not_found"
            if transaction is None
            else "binding_missing"
            if auth_binding is None
            else "binding_mismatch"
            if transaction.browser_binding_digest != digest(auth_binding)
            else "state_consumed"
            if transaction.consumed_at is not None
            else "state_expired"
            if transaction.expires_at <= now
            else "provider_configuration_changed"
            if (
                not profile_valid
                or transaction.expected_issuer != expected_issuer
                or transaction.client_id != expected_client
                or transaction.redirect_uri != settings.callback_url
                or transaction.provider_configuration_digest != current_profile_digest
                or transaction.response_issuer_required != settings.callback_issuer_required
            )
            else "response_issuer_missing"
            if transaction.response_issuer_required and iss is None
            else "response_issuer_mismatch"
            if iss is not None and iss != transaction.expected_issuer
            else None
        )
        if rejection is not None:
            logger.warning("OIDC callback rejected: %s", rejection)
            if transaction is not None:
                transaction.consumed_at = now
                identity_service.record(
                    db, transaction.provider_profile_id, "AUTH_LOGIN_FAILED", reason=rejection
                )
            db.commit()
            raise AuthenticationRequired()
        assert transaction is not None
        transaction.consumed_at = now
        if error is not None:
            identity_service.record(
                db,
                transaction.provider_profile_id,
                "AUTH_LOGIN_FAILED",
                reason="PROVIDER_CANCELLED"
                if error == "access_denied"
                else "PROVIDER_RESPONSE_ERROR",
            )
            db.commit()
            response = RedirectResponse(
                f"{settings.public_origin}{transaction.return_to}?auth_error="
                f"{'cancelled' if error == 'access_denied' else 'invalid'}",
                status_code=302,
            )
            response.delete_cookie(AUTH_BINDING_COOKIE, path="/api/auth/callback")
            return response
        # Burn the browser-bound state before provider exchange. A malformed
        # or rejected provider response must not make the callback replayable.
        db.commit()
        assert code is not None
        try:
            claims = oidc.exchange_code(
                db,
                code=code,
                verifier=transaction.code_verifier,
                redirect_uri=transaction.redirect_uri,
                expected_nonce=transaction.nonce,
                profile=profile,
            )
            identity = identity_service.resolve(
                db,
                profile_id=transaction.provider_profile_id,
                claims=claims,
                allow_legacy_local=profile is None,
            )
        except ApplicationError as exc:
            identity_service.record(
                db, transaction.provider_profile_id, "AUTH_LOGIN_FAILED", reason=exc.code
            )
            db.commit()
            raise
        memberships = db.scalars(
            select(MembershipRow)
            .join(CompanyRow, CompanyRow.id == MembershipRow.company_id)
            .where(
                MembershipRow.identity_id == identity.id,
                MembershipRow.active.is_(True),
                CompanyRow.active.is_(True),
            )
        ).all()
        if prior_session_token:
            prior = db.scalar(
                select(SessionRow).where(SessionRow.token_digest == digest(prior_session_token))
            )
            if prior is not None and prior.revoked_at is None:
                prior.revoked_at = now
                identity_service.record(
                    db,
                    prior.provider_profile_id,
                    "AUTH_SESSION_REVOKED",
                    identity_id=prior.identity_id,
                    session_id=prior.id,
                    reason="ROTATED_ON_SIGN_IN",
                )
        session_token = random_token(48)
        session_row = SessionRow(
            token_digest=digest(session_token),
            provider_profile_id=transaction.provider_profile_id,
            identity_id=identity.id,
            membership_id=memberships[0].id if len(memberships) == 1 else None,
            expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
        )
        db.add(session_row)
        db.flush()
        identity_service.record(
            db, transaction.provider_profile_id, "AUTH_LOGIN_SUCCEEDED", identity_id=identity.id
        )
        identity_service.record(
            db,
            transaction.provider_profile_id,
            "AUTH_SESSION_CREATED",
            identity_id=identity.id,
            session_id=session_row.id,
        )
        # The frontend can request its session as soon as it follows this
        # redirect, so persist identity/session state before returning.
        db.commit()
        response = RedirectResponse(
            f"{settings.public_origin}{transaction.return_to}", status_code=302
        )
        response.delete_cookie(AUTH_BINDING_COOKIE, path="/api/auth/callback")
        response.set_cookie(
            SESSION_COOKIE,
            session_token,
            httponly=True,
            secure=cookie_secure(settings),
            samesite="lax",
            max_age=settings.session_ttl_seconds,
            path="/",
        )
        return response

    @app.get("/api/auth/session")
    def auth_session(db: DB, session_token: SessionCookie = None) -> dict[str, Any]:
        assert isinstance(db, ApplicationSession)
        try:
            row, identity = resolve_session(db, session_token)
        except AuthenticationRequired:
            return {"authenticated": False}
        result: dict[str, Any] = {
            "authenticated": True,
            "identity": {
                "id": str(identity.id),
                "display_name": identity.display_name,
            },
            "csrf_token": csrf_token(session_token or "", settings.session_secret),
        }
        actor = db.active_actor(row.membership_id, identity.id) if row.membership_id else None
        if actor is not None:
            result["membership_state"] = "ACTIVE"
            result["actor"] = {
                "identity_id": str(actor.identity_id),
                "membership_id": str(actor.membership_id),
                "company_id": str(actor.company_id),
                "display_name": actor.display_name,
                "role": actor.role.value,
            }
        else:
            memberships = db.execute(
                select(MembershipRow, CompanyRow)
                .join(CompanyRow, CompanyRow.id == MembershipRow.company_id)
                .where(
                    MembershipRow.identity_id == identity.id,
                    MembershipRow.active.is_(True),
                    CompanyRow.active.is_(True),
                )
                .order_by(MembershipRow.created_at, MembershipRow.id)
            ).all()
            if memberships:
                result["membership_state"] = "COMPANY_SELECTION_REQUIRED"
                result["available_companies"] = [
                    {
                        "membership_id": str(membership.id),
                        "company_id": str(company.id),
                        "name": company.name,
                    }
                    for membership, company in memberships
                ]
            elif db.eligible_invitation_for_identity(identity, datetime.now(UTC)):
                result["membership_state"] = "INVITATION_AVAILABLE"
            else:
                result["membership_state"] = "COMPANY_CREATION_AVAILABLE"
        return result

    @app.post("/api/companies")
    def create_company(
        payload: CompanyCreate,
        response: Response,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
        command_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, Any]:
        assert isinstance(db, ApplicationSession)
        require_csrf(session_token, csrf)
        if command_key is None or re.fullmatch(r"[A-Za-z0-9._:-]{8,200}", command_key) is None:
            raise Conflict()
        session_row, identity = resolve_session(db, session_token)
        result, created = company_service.create(
            db, session_row, identity, payload.name, command_key
        )
        db.commit()
        response.status_code = 201 if created else 200
        return result

    @app.get("/api/profile")
    def get_profile(db: DB, session_token: SessionCookie = None) -> dict[str, Any]:
        _session, identity = resolve_session(db, session_token)
        return {"profile": {"display_name": identity.display_name}}

    @app.patch("/api/profile")
    def update_profile(
        payload: ProfileUpdate,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        assert isinstance(db, ApplicationSession)
        require_csrf(session_token, csrf)
        session_row, identity = resolve_session(db, session_token)
        updated = profile_service.update(db, identity, payload.display_name)
        identity_service.record(
            db,
            session_row.provider_profile_id,
            "PROFILE_UPDATED",
            identity_id=updated.id,
            session_id=session_row.id,
        )
        db.commit()
        return {"profile": {"display_name": updated.display_name}}

    @app.post("/api/auth/select-company")
    def select_company(
        payload: CompanySelection,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        assert isinstance(db, ApplicationSession)
        require_csrf(session_token, csrf)
        session_row, identity = resolve_session(db, session_token)
        actor = db.active_actor(payload.membership_id, identity.id)
        if actor is None:
            raise AuthenticationRequired()
        session_row.membership_id = actor.membership_id
        identity_service.record(
            db,
            session_row.provider_profile_id,
            "MEMBERSHIP_RESOLVED",
            identity_id=identity.id,
            session_id=session_row.id,
        )
        db.commit()
        return {"selected": True}

    @app.post("/api/auth/logout")
    def logout(
        db: DB,
        response: Response,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        require_csrf(session_token, csrf)
        try:
            row, identity = resolve_session(db, session_token)
        except AuthenticationRequired:
            row = None
        if row is not None:
            row.revoked_at = datetime.now(UTC)
            identity_service.record(
                db,
                row.provider_profile_id,
                "AUTH_LOGOUT",
                identity_id=identity.id,
                session_id=row.id,
            )
            db.commit()
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"signed_out": True}

    @app.get("/api/cases")
    def list_cases(db: DB, session_token: SessionCookie = None) -> dict[str, Any]:
        return {"items": case_service.list_cases(db, resolve_actor(db, session_token))}

    @app.post("/api/cases")
    def create_case(
        payload: CaseCreate,
        response: Response,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
        command_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, csrf)
        if command_key is None or not (8 <= len(command_key) <= 200):
            raise Conflict()
        result, created = case_service.create(
            db, resolve_actor(db, session_token), payload.request_text, command_key
        )
        db.commit()
        response.status_code = 201 if created else 200
        return {"case": result}

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: UUID, db: DB, session_token: SessionCookie = None) -> dict[str, Any]:
        return {"case": case_service.get(db, resolve_actor(db, session_token), case_id)}

    @app.get("/api/cases/{case_id}/versions")
    def case_versions(case_id: UUID, db: DB, session_token: SessionCookie = None) -> dict[str, Any]:
        return {"items": case_service.versions(db, resolve_actor(db, session_token), case_id)}

    @app.get("/api/cases/{case_id}/conversation")
    def list_conversation(
        case_id: UUID, db: DB, session_token: SessionCookie = None
    ) -> dict[str, Any]:
        actor = resolve_actor(db, session_token)
        return {"items": ConversationService().list_events(db, actor, case_id)}

    @app.post("/api/cases/{case_id}/conversation")
    def append_conversation(
        case_id: UUID,
        payload: ConversationEventCreate,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, csrf)
        actor = resolve_actor(db, session_token)
        snapshot = tenant_snapshot(db, actor)
        clarification_policy = ClarificationPolicy(
            max_rounds=snapshot.settings.max_clarification_rounds_per_cycle,
            max_questions_per_round=snapshot.settings.clarification_policy.max_questions_per_round,
            max_answer_characters=snapshot.settings.clarification_policy.max_answer_characters,
        )
        event = ConversationService(clarification_policy).append_event(
            db,
            actor,
            case_id,
            kind=payload.kind,
            payload=payload.payload,
            expected_context_version=payload.expected_context_version,
            command_key=payload.command_key,
        )
        db.commit()
        return {"event": event}

    @app.get("/api/cases/{case_id}/evidence")
    def list_evidence(case_id: UUID, db: DB, session_token: SessionCookie = None) -> dict[str, Any]:
        actor = resolve_actor(db, session_token)
        return {
            "items": local_evidence_service(tenant_snapshot(db, actor)).list(db, actor, case_id)
        }

    @app.post("/api/cases/{case_id}/evidence")
    async def add_evidence(
        case_id: UUID,
        request: Request,
        db: DB,
        filename: str = Query(min_length=1, max_length=255),
        expected_context_version: int = Query(ge=1),
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, csrf)
        actor = resolve_actor(db, session_token)
        snapshot = tenant_snapshot(db, actor)
        policy = local_upload_policy(snapshot)
        content_length = request.headers.get("content-length")
        if (
            content_length is None
            or not content_length.isdigit()
            or int(content_length) > policy.max_file_bytes
        ):
            raise EvidenceInvalid()
        content_buffer = bytearray()
        async for chunk in request.stream():
            if len(content_buffer) + len(chunk) > policy.max_file_bytes:
                raise EvidenceInvalid()
            content_buffer.extend(chunk)
        content = bytes(content_buffer)
        objects = local_evidence_service(snapshot)
        result, _storage_key = objects.add(
            db,
            actor,
            case_id,
            filename=filename,
            content=content,
            expected_context_version=expected_context_version,
        )
        # A commit may have succeeded before its acknowledgement was lost. The
        # service cleans known pre-commit failures; an uncertain commit must
        # retain bytes until authoritative reconciliation can prove orphanhood.
        db.commit()
        return {"evidence": result}

    @app.get("/api/cases/{case_id}/reference-material")
    def list_reference_material(
        case_id: UUID, db: DB, session_token: SessionCookie = None
    ) -> dict[str, Any]:
        actor = resolve_actor(db, session_token)
        return {
            "items": local_reference_service(tenant_snapshot(db, actor)).list(db, actor, case_id)
        }

    @app.post("/api/cases/{case_id}/reference-material")
    async def add_reference_material(
        case_id: UUID,
        request: Request,
        db: DB,
        filename: str = Query(min_length=1, max_length=255),
        expected_context_version: int = Query(ge=1),
        session_token: SessionCookie = None,
        supplied_csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, supplied_csrf)
        actor = resolve_actor(db, session_token)
        snapshot = tenant_snapshot(db, actor)
        policy = local_upload_policy(snapshot)
        content_length = request.headers.get("content-length")
        if (
            content_length is None
            or not content_length.isdigit()
            or int(content_length) > policy.max_file_bytes
        ):
            raise EvidenceInvalid()
        content_buffer = bytearray()
        async for chunk in request.stream():
            if len(content_buffer) + len(chunk) > policy.max_file_bytes:
                raise EvidenceInvalid()
            content_buffer.extend(chunk)
        service = local_reference_service(snapshot)
        result, _storage_key = service.add(
            db,
            actor,
            case_id,
            filename=filename,
            content=bytes(content_buffer),
            expected_context_version=expected_context_version,
        )
        db.commit()
        return {"reference_material": result}

    @app.post("/api/cases/{case_id}/interpretations")
    def create_interpretation(
        case_id: UUID,
        payload: InterpretationCreate,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, csrf)
        actor = resolve_actor(db, session_token)
        try:
            result = local_acceptance_service(db, tenant_snapshot(db, actor)).create_interpretation(
                db,
                actor,
                case_id,
                expected_context_version=payload.expected_context_version,
            )
        except AnalysisAttemptFailed as exc:
            # The provider call is outside PostgreSQL. Roll back all attempted
            # interpretation changes before committing only curated audit data.
            db.rollback()
            current_actor = resolve_actor(db, session_token)
            case_service.get(db, current_actor, case_id)
            db.add(
                AuditEventRow(
                    company_id=current_actor.company_id,
                    actor_membership_id=current_actor.membership_id,
                    event_type="INTERPRETATION_ATTEMPT_FAILED",
                    resource_type="REPORTING_CASE",
                    resource_id=case_id,
                    details_json=json.dumps(
                        exc.audit_details, sort_keys=True, separators=(",", ":")
                    ),
                )
            )
            db.commit()
            raise
        db.commit()
        return {"interpretation": result}

    @app.post("/api/cases/{case_id}/clarification-cycles")
    def create_clarification_cycle(
        case_id: UUID,
        payload: ClarificationCycleCreate,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, csrf)
        actor = resolve_actor(db, session_token)
        result = local_acceptance_service(db, tenant_snapshot(db, actor)).start_refinement_cycle(
            db,
            actor,
            case_id,
            expected_context_version=payload.expected_context_version,
            command_key=payload.command_key,
            enhancement=payload.enhancement,
        )
        db.commit()
        return result

    @app.get("/api/cases/{case_id}/acceptance")
    def acceptance_state(
        case_id: UUID,
        db: DB,
        session_token: SessionCookie = None,
    ) -> dict[str, Any]:
        actor = resolve_actor(db, session_token)
        return local_acceptance_service(db, tenant_snapshot(db, actor)).state(db, actor, case_id)

    @app.post("/api/cases/{case_id}/confirm")
    def confirm_interpretation(
        case_id: UUID,
        payload: InterpretationConfirm,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, csrf)
        actor = resolve_actor(db, session_token)
        result = local_acceptance_service(db, tenant_snapshot(db, actor)).confirm(
            db,
            actor,
            case_id,
            interpretation_id=payload.interpretation_id,
            expected_context_version=payload.expected_context_version,
        )
        db.commit()
        return {"confirmed_contract": result}

    @app.put("/api/cases/{case_id}")
    def update_case(
        case_id: UUID,
        payload: CaseUpdate,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, csrf)
        result = {
            "case": case_service.update(
                db,
                resolve_actor(db, session_token),
                case_id,
                payload.request_text,
                payload.expected_version,
            )
        }
        db.commit()
        return result

    @app.get("/api/cases/{case_id}/generation")
    def generation_history(
        case_id: UUID, db: DB, session_token: SessionCookie = None
    ) -> dict[str, Any]:
        actor = resolve_actor(db, session_token)
        return {
            "items": local_generation_service(db, tenant_snapshot(db, actor)).history(
                db, actor, case_id
            )
        }

    @app.get("/api/cases/{case_id}/reviewed-designs")
    def reviewed_designs(
        case_id: UUID,
        confirmed_contract_id: UUID,
        db: DB,
        session_token: SessionCookie = None,
    ) -> dict[str, Any]:
        actor = resolve_actor(db, session_token)
        return local_generation_service(db, tenant_snapshot(db, actor)).list_reviewed_designs(
            db, actor, case_id, confirmed_contract_id
        )

    @app.post("/api/cases/{case_id}/reviewed-designs")
    def intake_reviewed_design(
        case_id: UUID,
        payload: ReviewedDesignCreate,
        response: Response,
        db: DB,
        session_token: SessionCookie = None,
        supplied_csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, supplied_csrf)
        actor = resolve_actor(db, session_token)
        reviewed = local_generation_service(db, tenant_snapshot(db, actor)).intake_reviewed_design(
            db,
            actor,
            case_id,
            contract_id=payload.confirmed_contract_id,
            report_design=payload.report_design,
        )
        db.commit()
        response.status_code = 201
        return {"reviewed_design": reviewed}

    @app.get("/api/cases/{case_id}/automatic-designs")
    def automatic_design_history(
        case_id: UUID,
        confirmed_contract_id: UUID,
        db: DB,
        session_token: SessionCookie = None,
    ) -> dict[str, Any]:
        actor = resolve_actor(db, session_token)
        return {
            "items": local_generation_service(
                db, tenant_snapshot(db, actor)
            ).automatic_design_history(
                db,
                actor,
                case_id,
                confirmed_contract_id,
            )
        }

    @app.post("/api/cases/{case_id}/automatic-designs")
    def propose_automatic_design(
        case_id: UUID,
        payload: AutomaticDesignCreate,
        response: Response,
        db: DB,
        session_token: SessionCookie = None,
        supplied_csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, supplied_csrf)
        actor = resolve_actor(db, session_token)
        result, created = local_generation_service(
            db, tenant_snapshot(db, actor), require_bridge=True
        ).propose_automatic_design(
            db,
            actor,
            case_id,
            contract_id=payload.confirmed_contract_id,
            command_key=payload.command_key,
        )
        response.status_code = 201 if created else 200
        return result

    @app.post("/api/cases/{case_id}/generation")
    def start_generation(
        case_id: UUID,
        payload: GenerationCreate,
        response: Response,
        db: DB,
        session_token: SessionCookie = None,
        supplied_csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, supplied_csrf)
        actor = resolve_actor(db, session_token)
        result, created = local_generation_service(
            db, tenant_snapshot(db, actor), require_bridge=True
        ).start(
            db,
            actor,
            case_id,
            contract_id=payload.confirmed_contract_id,
            command_key=payload.command_key,
            mode=payload.mode,
            source_attempt_id=payload.source_attempt_id,
            reviewed_design_id=payload.reviewed_design_id,
        )
        response.status_code = 201 if created else 200
        return {"attempt": result}

    @app.get("/api/cases/{case_id}/generation/{attempt_id}")
    def generation_status(
        case_id: UUID,
        attempt_id: UUID,
        db: DB,
        session_token: SessionCookie = None,
    ) -> dict[str, Any]:
        actor = resolve_actor(db, session_token)
        return {
            "attempt": local_generation_service(db, tenant_snapshot(db, actor)).get(
                db, actor, case_id, attempt_id
            )
        }

    @app.post("/api/cases/{case_id}/generation/{attempt_id}/cancel")
    def cancel_generation(
        case_id: UUID,
        attempt_id: UUID,
        db: DB,
        session_token: SessionCookie = None,
        supplied_csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, supplied_csrf)
        actor = resolve_actor(db, session_token)
        return {
            "attempt": local_generation_service(db, tenant_snapshot(db, actor)).cancel(
                db, actor, case_id, attempt_id
            )
        }

    @app.get("/api/cases/{case_id}/generation/{attempt_id}/artifact")
    def download_generation_artifact(
        case_id: UUID,
        attempt_id: UUID,
        db: DB,
        session_token: SessionCookie = None,
    ) -> Response:
        actor = resolve_actor(db, session_token)
        content, filename, digest_value = local_generation_service(
            db, tenant_snapshot(db, actor)
        ).artifact(db, actor, case_id, attempt_id)
        safe_filename = "".join(
            character for character in filename if character.isalnum() or character in "._-"
        )
        safe_filename = safe_filename or "apbra-report-candidate.zip"
        return Response(
            content=content,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}"',
                "X-Content-SHA256": digest_value,
                "Cache-Control": "private, no-store",
            },
        )

    @app.get("/api/cases/{case_id}/access")
    def list_case_access(
        case_id: UUID, db: DB, session_token: SessionCookie = None
    ) -> dict[str, Any]:
        return {"items": case_service.list_access(db, resolve_actor(db, session_token), case_id)}

    @app.post("/api/cases/{case_id}/access")
    def grant_case_access(
        case_id: UUID,
        payload: CaseAccessGrant,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        require_csrf(session_token, csrf)
        case_service.grant_access(
            db,
            resolve_actor(db, session_token),
            case_id,
            payload.membership_id,
            payload.access_level,
        )
        db.commit()
        return {"granted": True}

    @app.post("/api/cases/{case_id}/access/{membership_id}/revoke")
    def revoke_case_access(
        case_id: UUID,
        membership_id: UUID,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        require_csrf(session_token, csrf)
        case_service.revoke_access(db, resolve_actor(db, session_token), case_id, membership_id)
        db.commit()
        return {"revoked": True}

    @app.post("/api/invitations")
    def issue_invitation(
        payload: InvitationIssue,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, csrf)
        actor = resolve_actor(db, session_token)
        snapshot = tenant_snapshot(db, actor)
        row, raw_token = invitation_service.issue(
            db,
            actor,
            payload.subject,
            payload.role,
            payload.expires_in_days or snapshot.settings.invitation_ttl_days,
        )
        db.commit()
        return {"invitation": invitation_json(row), "token": raw_token}

    @app.post("/api/invitations/inspect")
    def inspect_invitation(payload: InvitationToken, db: DB) -> dict[str, Any]:
        return {"invitation": invitation_json(invitation_service.inspect(db, payload.token))}

    @app.post("/api/invitations/accept")
    def accept_invitation(
        payload: InvitationToken,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, csrf)
        session_row, identity = resolve_session(db, session_token)
        membership = invitation_service.accept(db, identity, payload.token)
        session_row.membership_id = membership.id
        db.commit()
        return {"membership": {"id": str(membership.id), "role": membership.role}}

    @app.post("/api/invitations/{invitation_id}/revoke")
    def revoke_invitation(
        invitation_id: UUID,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        require_csrf(session_token, csrf)
        invitation_service.revoke(db, resolve_actor(db, session_token), invitation_id)
        db.commit()
        return {"revoked": True}

    @app.get("/api/memberships")
    def list_memberships(db: DB, session_token: SessionCookie = None) -> dict[str, Any]:
        return {"items": membership_service.list(db, resolve_actor(db, session_token))}

    @app.post("/api/memberships/{membership_id}/deactivate")
    def deactivate_membership(
        membership_id: UUID,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        require_csrf(session_token, csrf)
        membership_service.deactivate(db, resolve_actor(db, session_token), membership_id)
        db.commit()
        return {"deactivated": True}

    @app.post("/api/memberships/{membership_id}/role")
    def change_membership_role(
        membership_id: UUID,
        payload: MembershipRoleUpdate,
        db: DB,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        require_csrf(session_token, csrf)
        row = membership_service.change_role(
            db, resolve_actor(db, session_token), membership_id, Role(payload.role)
        )
        db.commit()
        return {"membership": {"id": str(row.id), "role": row.role, "active": row.active}}

    app.state.settings = settings
    app.state.database = database
    app.state.oidc = oidc
    return app
