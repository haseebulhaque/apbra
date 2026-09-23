import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import Cookie, Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .application import CaseService, InvitationService, MembershipService
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
from .config import Settings, get_settings
from .domain import AccessLevel, ApplicationError, AuthenticationRequired, Conflict, Role
from .oidc_adapter import OidcAdapter
from .persistence import (
    AuthorizationCodeRow,
    AuthTransactionRow,
    Database,
    ExternalIdentityRow,
    MembershipRow,
    SessionRow,
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
) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_security_profile()
    database = database or Database(settings.database_url)
    oidc = oidc or OidcAdapter(settings)
    case_service = CaseService()
    invitation_service = InvitationService()
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

    @app.exception_handler(ApplicationError)
    async def handle_application_error(_request: Request, exc: ApplicationError) -> JSONResponse:
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
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

    @app.get("/api/auth/login")
    def login(
        db: DB,
        identity: str = Query(default="owner"),
        return_to: str = Query(default="/"),
    ) -> Response:
        if settings.profile in {"development", "test"}:
            allowed = {item.selector for item in BOOTSTRAP_IDENTITIES}
            if identity not in allowed:
                raise AuthenticationRequired()
        start = AuthStart.create(return_to)
        db.add(
            AuthTransactionRow(
                state_digest=digest(start.state),
                browser_binding_digest=digest(start.browser_binding),
                expected_issuer=settings.issuer,
                client_id=settings.oidc_audience,
                redirect_uri=settings.callback_url,
                provider_configuration_digest=settings.oidc_configuration_digest,
                response_issuer_required=settings.callback_issuer_required,
                nonce=start.nonce,
                code_verifier=start.verifier,
                return_to=start.return_to,
                expires_at=start.expires_at,
            )
        )
        # The browser follows the redirect immediately. Make the one-time
        # transaction visible before returning rather than relying on
        # dependency cleanup after the response has started.
        db.commit()
        response = RedirectResponse(
            oidc.authorization_url(
                state=start.state,
                nonce=start.nonce,
                code_challenge=pkce_challenge(start.verifier),
                identity_selector=(
                    identity if settings.profile in {"development", "test"} else None
                ),
            ),
            status_code=302,
        )
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
        code: str = Query(min_length=1, max_length=2_000),
        iss: str | None = Query(default=None, max_length=1_000),
        auth_binding: Annotated[str | None, Cookie(alias=AUTH_BINDING_COOKIE)] = None,
    ) -> Response:
        state_values = request.query_params.getlist("state")
        code_values = request.query_params.getlist("code")
        issuer_values = request.query_params.getlist("iss")
        if (
            len(state_values) != 1
            or len(code_values) != 1
            or len(issuer_values) > 1
            or any(not value for value in (*state_values, *code_values, *issuer_values))
        ):
            logger.warning("OIDC callback rejected: malformed_response_parameters")
            raise AuthenticationRequired()
        now = datetime.now(UTC)
        transaction = db.scalar(
            select(AuthTransactionRow)
            .where(AuthTransactionRow.state_digest == digest(state))
            .with_for_update()
        )
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
                transaction.expected_issuer != settings.issuer
                or transaction.client_id != settings.oidc_audience
                or transaction.redirect_uri != settings.callback_url
                or transaction.provider_configuration_digest
                != settings.oidc_configuration_digest
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
            raise AuthenticationRequired()
        assert transaction is not None
        transaction.consumed_at = now
        # Burn the browser-bound state before provider exchange. A malformed
        # or rejected provider response must not make the callback replayable.
        db.commit()
        claims = oidc.exchange_code(
            db,
            code=code,
            verifier=transaction.code_verifier,
            redirect_uri=transaction.redirect_uri,
            expected_nonce=transaction.nonce,
        )
        identity = db.scalar(
            select(ExternalIdentityRow).where(
                ExternalIdentityRow.issuer == claims.issuer,
                ExternalIdentityRow.subject == claims.subject,
            )
        )
        if identity is None:
            identity = ExternalIdentityRow(
                issuer=claims.issuer,
                subject=claims.subject,
                display_name=claims.display_name,
            )
            db.add(identity)
            db.flush()
        if not identity.active:
            raise AuthenticationRequired()
        memberships = db.scalars(
            select(MembershipRow).where(
                MembershipRow.identity_id == identity.id,
                MembershipRow.active.is_(True),
            )
        ).all()
        if len(memberships) > 1:
            raise AuthenticationRequired()
        session_token = random_token(48)
        db.add(
            SessionRow(
                token_digest=digest(session_token),
                identity_id=identity.id,
                membership_id=memberships[0].id if memberships else None,
                expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
            )
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
        try:
            row, identity = resolve_session(db, session_token)
        except AuthenticationRequired:
            return {"authenticated": False}
        result: dict[str, Any] = {
            "authenticated": True,
            "identity": {
                "id": str(identity.id),
                "display_name": identity.display_name,
                "subject": identity.subject,
            },
            "csrf_token": csrf_token(session_token or "", settings.session_secret),
        }
        if row.membership_id:
            actor = resolve_actor(db, session_token)
            result["actor"] = {
                "identity_id": str(actor.identity_id),
                "membership_id": str(actor.membership_id),
                "company_id": str(actor.company_id),
                "display_name": actor.display_name,
                "role": actor.role.value,
            }
        return result

    @app.post("/api/auth/logout")
    def logout(
        db: DB,
        response: Response,
        session_token: SessionCookie = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        require_csrf(session_token, csrf)
        row, _ = resolve_session(db, session_token)
        row.revoked_at = datetime.now(UTC)
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

    @app.get("/api/cases/{case_id}/access")
    def list_case_access(
        case_id: UUID, db: DB, session_token: SessionCookie = None
    ) -> dict[str, Any]:
        return {
            "items": case_service.list_access(
                db, resolve_actor(db, session_token), case_id
            )
        }

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
        case_service.revoke_access(
            db, resolve_actor(db, session_token), case_id, membership_id
        )
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
        row, raw_token = invitation_service.issue(
            db,
            actor,
            payload.subject,
            payload.role,
            payload.expires_in_days or settings.invitation_ttl_days,
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

    app.state.settings = settings
    app.state.database = database
    app.state.oidc = oidc
    return app
