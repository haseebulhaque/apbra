"""Opt-in first-screen accounts. These sessions never grant APBRA tenant access.

No raw password/proof is persisted, returned, logged or put in a query string.
Mail is a single attempt after request acceptance; failed deliveries are audited,
invalidated and never automatically retried. Test mail is prohibited outside test.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import smtplib
import ssl
import threading
import unicodedata
from collections.abc import Callable
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from email_validator import EmailNotValidError, validate_email
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, inspect, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .persistence import Base, Database, utcnow


class PasswordAuthSettings(BaseSettings):
    """Feature-owned opt-in configuration; never supplies tenant/session authority."""

    model_config = SettingsConfigDict(
        env_prefix="APBRA_", env_file=".env", extra="ignore", frozen=True
    )
    password_auth_enabled: bool = False
    password_smtp_host: str | None = None
    password_smtp_port: int = Field(default=587, ge=1, le=65535)
    password_smtp_username: str | None = Field(default=None, repr=False)
    password_smtp_password: SecretStr | None = Field(default=None, repr=False)
    password_mail_from: str | None = None


COOKIE = "apbra_password_session"
PRE_COOKIE = "apbra_password_pre"
PATH = "/api/password"
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
HASH_PREFIX = "$argon2id$v=19$m=19456,t=2,p=1$"
HASH_SLOTS = threading.BoundedSemaphore(2)
MAIL_LOG = logging.getLogger("apbra.password_email")
# Conservative local baseline of commonly breached/expected passphrases. No
# password or password-derived digest is sent to an external breach service.
COMMON = frozenset(
    {
        "passwordpassword",
        "passwordpasswordpassword",
        "123456789012345",
        "1234567890123456",
        "qwertyuiopasdfgh",
        "letmeinletmeinletmein",
        "correct horse battery staple",
        "apbraapbraapbra",
    }
)

# Common-password baseline: SecLists10k, pinned 48c951a3c3afba4e647bfe6944a1fbd2fdbf2ca7
# SourceSHA256 68782d6a4a19a4768d5f15dd66bd534e7a33055cc755411e33f16d18c50fdcce
# Entries shorter than15 are already rejected by the minimum length.
# These public-list lookup digests are NOT credential hashes. No password-derived
# data is transmitted to this list provider. This is not an exhaustive breach check.
# MIT License
#
# Copyright (c) 2018 Daniel Miessler
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
COMMON_DIGESTS = frozenset(
    {
        "373d338065c3e6bce7f76c177341dee0ec4cff8af28bf595af377aa50fba2e1a",
    }
)


class PasswordAccountRow(Base):
    __tablename__ = "password_accounts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email_key: Mapped[str] = mapped_column(String(320), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str] = mapped_column(String(512))
    epoch: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PasswordProofRow(Base):
    __tablename__ = "password_proofs"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(16))
    email_key: Mapped[str] = mapped_column(String(320))
    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    account_id: Mapped[UUID | None] = mapped_column(ForeignKey("password_accounts.id"))
    epoch: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PasswordSessionRow(Base):
    __tablename__ = "password_sessions"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("password_accounts.id"))
    epoch: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    touched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PasswordThrottleRow(Base):
    __tablename__ = "password_throttles"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)


class PasswordAuditRow(Base):
    __tablename__ = "password_audit"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event: Mapped[str] = mapped_column(String(40))
    account_id: Mapped[UUID | None] = mapped_column(ForeignKey("password_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Mailer(Protocol):
    test_only: bool

    def send(self, recipient: str, purpose: str, proof: str) -> None: ...


class CaptureMailer:
    """Disposable test fixture only; never a production delivery substitute."""

    test_only = True

    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    def send(self, recipient: str, purpose: str, proof: str) -> None:
        self.messages.append((recipient, purpose, proof))

    def __repr__(self) -> str:
        return "CaptureMailer(<private test messages>)"


class SmtpMailer:
    test_only = False

    def __init__(self, settings: PasswordAuthSettings, public_origin: str) -> None:
        if not settings.password_smtp_host or not settings.password_mail_from:
            raise ValueError("PASSWORD_MAIL_NOT_CONFIGURED")
        if settings.password_smtp_port not in {465, 587}:
            raise ValueError("PASSWORD_MAIL_REQUIRES_TLS")
        if settings.password_smtp_username and not settings.password_smtp_password:
            raise ValueError("PASSWORD_MAIL_CREDENTIAL_INCOMPLETE")
        self.settings = settings
        self.public_origin = public_origin
        self.sender = normalized_email(settings.password_mail_from)[0]

    def send(self, recipient: str, purpose: str, proof: str) -> None:
        settings = self.settings
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = recipient
        message["Subject"] = (
            "Verify your APBRA account" if purpose == "verify" else "Reset your APBRA password"
        )
        # Fragments are not transmitted in HTTP requests/referrers. The UI scrubs
        # the fragment before requesting options and submits it only in a POST.
        link = f"{self.public_origin}/account#account_action={purpose}&proof={proof}"
        message.set_content(
            f"Open this link in APBRA to {purpose} your account:\n{link}\n"
            "If you did not request this, ignore this email. No existing workspace access changes."
        )
        context = ssl.create_default_context()
        host = settings.password_smtp_host
        assert host is not None
        if settings.password_smtp_port == 465:
            client: smtplib.SMTP = smtplib.SMTP_SSL(host, 465, timeout=10, context=context)
        else:
            client = smtplib.SMTP(host, 587, timeout=10)
        with client:
            if settings.password_smtp_port == 587:
                client.ehlo()
                client.starttls(context=context)
                client.ehlo()
            if settings.password_smtp_username:
                assert settings.password_smtp_password is not None
                client.login(
                    settings.password_smtp_username,
                    settings.password_smtp_password.get_secret_value(),
                )
            client.send_message(message)


def normalized_email(raw: str) -> tuple[str, str]:
    if len(raw) > 320:
        raise ValueError("EMAIL_INVALID")
    try:
        result = validate_email(raw, check_deliverability=False, allow_smtputf8=False)
    except EmailNotValidError:
        raise ValueError("EMAIL_INVALID") from None
    # Deliberate case-insensitive account key; never strip dots/plus or use it to
    # merge a provider identity. Retain the normalized delivery spelling separately.
    return result.normalized, result.normalized.casefold()


def password_value(raw: str, *, new: bool) -> str:
    value = unicodedata.normalize("NFC", raw)
    if not value or len(value) > 1024 or len(value.encode("utf-8")) > 4096:
        raise ValueError("PASSWORD_INVALID")
    if new and (
        len(value) < 15 or value.casefold() in COMMON or digest(value.casefold()) in COMMON_DIGESTS
    ):
        raise ValueError("PASSWORD_POLICY")
    return value


def password_hash(value: str) -> str:
    if not HASH_SLOTS.acquire(blocking=False):
        raise ValueError("AUTH_BUSY")
    try:
        return Argon2id(
            salt=secrets.token_bytes(16), length=32, iterations=2, lanes=1, memory_cost=19456
        ).derive_phc_encoded(value.encode("utf-8"))
    finally:
        HASH_SLOTS.release()


def password_matches(encoded: str, value: str) -> bool:
    if not encoded.startswith(HASH_PREFIX) or len(encoded) > 512:
        return False
    if not HASH_SLOTS.acquire(blocking=False):
        raise ValueError("AUTH_BUSY")
    try:
        Argon2id.verify_phc_encoded(value.encode("utf-8"), encoded)
        return True
    except (InvalidKey, ValueError):
        return False
    finally:
        HASH_SLOTS.release()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def register_password_routes(
    app: FastAPI,
    database: Database,
    settings: Settings,
    mailer: Mailer | None = None,
    clock: Callable[[], datetime] = utcnow,
    *,
    password_settings: PasswordAuthSettings | None = None,
) -> None:
    feature = password_settings if password_settings is not None else PasswordAuthSettings()
    if mailer is not None and (not mailer.test_only or settings.profile != "test"):
        raise ValueError("PASSWORD_MAIL_INJECTION_TEST_ONLY")
    if mailer is None and feature.password_auth_enabled and feature.password_smtp_host:
        mailer = SmtpMailer(feature, settings.public_origin)
    if feature.password_auth_enabled and not all(
        inspect(database.engine).has_table(name)
        for name in (
            "password_accounts",
            "password_proofs",
            "password_sessions",
            "password_throttles",
            "password_audit",
        )
    ):
        raise ValueError("PASSWORD_SCHEMA_NOT_READY")
    secure = settings.public_origin.startswith("https://")
    secret = settings.session_secret.encode()
    dummy = password_hash(secrets.token_urlsafe(32)) if feature.password_auth_enabled else ""

    def answer(code: str, status: int = 200, **extra: Any) -> JSONResponse:
        return JSONResponse(
            {"status": code, **extra},
            status_code=status,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    def audit(db: Any, event: str, account_id: UUID | None = None) -> None:
        db.add(PasswordAuditRow(event=event, account_id=account_id))

    def csrf(nonce: str) -> str:
        return hmac.new(secret, ("password-csrf:" + nonce).encode(), hashlib.sha256).hexdigest()

    def take_rate(db: Any, key: str, limit: int, now: datetime) -> bool:
        hashed = hmac.new(secret, key.encode(), hashlib.sha256).hexdigest()
        bucket = int(now.timestamp()) // 900
        count = db.execute(
            insert(PasswordThrottleRow)
            .values(key=hashed, bucket=bucket, count=1)
            .on_conflict_do_update(
                index_elements=["key", "bucket"], set_={"count": PasswordThrottleRow.count + 1}
            )
            .returning(PasswordThrottleRow.count)
        ).scalar_one()
        return bool(count <= limit)

    async def payload(request: Request) -> dict[str, str] | JSONResponse:
        if not feature.password_auth_enabled:
            return answer("PASSWORD_ACCESS_UNAVAILABLE", 503)
        if request.headers.get("origin") != settings.public_origin:
            return answer("REQUEST_NOT_VERIFIED", 403)
        nonce = request.cookies.get(PRE_COOKIE, "")
        supplied = request.headers.get("x-password-csrf", "")
        if not re.fullmatch(r"[0-9]{1,12}\.[A-Za-z0-9_-]{43}", nonce) or not re.fullmatch(
            r"[0-9a-f]{64}", supplied
        ):
            return answer("REQUEST_NOT_VERIFIED", 403)
        issued = int(nonce.split(".", 1)[0])
        age = int(clock().timestamp()) - issued
        if not 0 <= age <= 1800 or not hmac.compare_digest(csrf(nonce), supplied):
            return answer("REQUEST_NOT_VERIFIED", 403)
        if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
            return answer("REQUEST_INVALID", 400)
        raw = bytearray()
        async for part in request.stream():
            if len(part) > 8192 - len(raw):
                return answer("REQUEST_TOO_LARGE", 413)
            raw.extend(part)
        try:

            def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                result: dict[str, Any] = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("DUPLICATE_KEY")
                    result[key] = value
                return result

            data = json.loads(raw, object_pairs_hook=unique_pairs)
        except (ValueError, UnicodeError, RecursionError):
            return answer("REQUEST_INVALID", 400)
        if not isinstance(data, dict) or any(not isinstance(v, str) for v in data.values()):
            return answer("REQUEST_INVALID", 400)
        if set(data) - {"email", "password", "proof"}:
            return answer("REQUEST_INVALID", 400)
        peer = request.client.host if request.client else "unknown"
        with database.session() as db:
            allowed = take_rate(db, "peer:" + peer, 60, clock())
        if not allowed:
            return answer("TRY_LATER", 429)
        return cast(dict[str, str], data)

    def active(db: Any, raw: str | None, *, lock: bool = False) -> tuple[Any, Any] | None:
        if not raw or not TOKEN.fullmatch(raw):
            return None
        query = (
            select(PasswordSessionRow, PasswordAccountRow)
            .join(PasswordAccountRow)
            .where(PasswordSessionRow.digest == digest(raw))
        )
        if lock:
            query = query.with_for_update(of=PasswordSessionRow)
        row = db.execute(query).one_or_none()
        now = clock()
        if row is None:
            return None
        session, account = row
        if (
            not account.active
            or session.epoch != account.epoch
            or session.revoked_at
            or session.expires_at <= now
            or session.touched_at + timedelta(minutes=30) <= now
        ):
            return None
        return session, account

    def deliver(recipient: str, purpose: str, proof: str, reference: str) -> None:
        assert mailer is not None
        outcome = "SUBMITTED_NOT_DELIVERY_CONFIRMED"
        try:
            mailer.send(recipient, purpose, proof)
            event = "MAIL_SUBMITTED"  # SMTP acceptance is not inbox delivery proof.
        except smtplib.SMTPResponseException:
            event = "MAIL_FAILED"
            outcome = "SUBMISSION_REJECTED"
        except (TimeoutError, smtplib.SMTPServerDisconnected, OSError):
            # The provider may have accepted a message before the connection failed.
            # Invalidate the proof conservatively; never retry an uncertain send.
            event = "MAIL_FAILED"
            outcome = "SUBMISSION_UNCONFIRMED"
        except Exception:
            event = "MAIL_FAILED"
            outcome = "SUBMISSION_FAILED"
        with database.session() as db:
            if event == "MAIL_FAILED":
                db.execute(
                    update(PasswordProofRow)
                    .where(PasswordProofRow.digest == digest(proof))
                    .values(consumed_at=clock())
                )
            audit(db, event)
        # Operator-only diagnostics: no address, proof, password, server detail or
        # exception text. There is deliberately no public reference lookup route.
        MAIL_LOG.log(
            logging.INFO if event == "MAIL_SUBMITTED" else logging.WARNING,
            "Account email request %s: %s", reference, outcome,
        )

    @app.get(PATH + "/options")
    def options() -> JSONResponse:
        result = answer(
            "AVAILABLE" if feature.password_auth_enabled else "PASSWORD_ACCESS_UNAVAILABLE",
            enabled=feature.password_auth_enabled,
            registration=bool(feature.password_auth_enabled and mailer),
            recovery=bool(feature.password_auth_enabled and mailer),
            delivery=(
                "TEST_CAPTURE_ONLY"
                if mailer and mailer.test_only
                else "SMTP_CONFIGURED_NOT_DELIVERY_VERIFIED"
                if mailer
                else "UNCONFIGURED"
            ),
        )
        if feature.password_auth_enabled:
            nonce = f"{int(clock().timestamp())}.{secrets.token_urlsafe(32)}"
            result.set_cookie(
                PRE_COOKIE,
                nonce,
                httponly=True,
                secure=secure,
                samesite="lax",
                path=PATH,
                max_age=1800,
            )
            # The nonce itself stays HttpOnly; only its purpose-bound MAC is readable.
            result.body = json.dumps(
                {**json.loads(bytes(result.body)), "csrf": csrf(nonce)}
            ).encode()
            result.headers["content-length"] = str(len(result.body))
        return result

    @app.get(PATH + "/session")
    def session(request: Request) -> JSONResponse:
        if not feature.password_auth_enabled:
            return answer("PASSWORD_ACCESS_UNAVAILABLE", 503)
        with database.session() as db:
            found = active(db, request.cookies.get(COOKIE), lock=True)
            if found is None:
                return answer("SIGNED_OUT", authenticated=False)
            row, account = found
            row.touched_at = clock()
            return answer(
                "SIGNED_IN",
                authenticated=True,
                account={"id": str(account.id), "email": account.email},
                workspace_access=False,
                next_step="ORGANISATION_SETUP_NOT_IMPLEMENTED",
            )

    def execute(
        action: str, data: dict[str, str], request: Request, background: BackgroundTasks
    ) -> JSONResponse:
        now = clock()
        try:
            if action == "signout":
                with database.session() as db:
                    found = active(db, request.cookies.get(COOKIE), lock=True)
                    if found:
                        found[0].revoked_at = now
                        audit(db, "SIGNED_OUT", found[1].id)
                result = answer("SIGNED_OUT")
                result.delete_cookie(
                    COOKIE, path=PATH, secure=secure, httponly=True, samesite="lax"
                )
                return result
            if action in {"signup", "signin", "recover"}:
                email, key = normalized_email(data.get("email", ""))
                with database.session() as db:
                    allowed = take_rate(db, f"account:{action}:{key}", 5, now)
                if not allowed:
                    return answer("TRY_LATER", 429)
                value = (
                    password_value(data.get("password", ""), new=action == "signup")
                    if action != "recover"
                    else ""
                )
                if action in {"signup", "recover"} and mailer is None:
                    reference = str(uuid4())
                    MAIL_LOG.warning("Account email request %s: UNCONFIGURED", reference)
                    return answer("EMAIL_DELIVERY_UNAVAILABLE", 503, support_reference=reference)
                encoded = password_hash(value) if action == "signup" else None
                with database.session() as db:
                    account_query = select(PasswordAccountRow).where(
                        PasswordAccountRow.email_key == key
                    )
                    if action == "signin":
                        account_query = account_query.with_for_update()
                    account = db.scalar(account_query)
                    if action == "signin":
                        matches = password_matches(
                            account.password_hash if account else dummy, value
                        )
                        if not account or not account.active or not matches:
                            audit(db, "SIGNIN_FAILED")
                            return answer("SIGNIN_FAILED", 401)
                        # Rotate only this native browser session; legacy cookies never enter here.
                        previous = active(db, request.cookies.get(COOKIE), lock=True)
                        if previous:
                            previous[0].revoked_at = now
                        now = clock()
                        token = secrets.token_urlsafe(32)
                        db.add(
                            PasswordSessionRow(
                                digest=digest(token),
                                account_id=account.id,
                                epoch=account.epoch,
                                expires_at=now + timedelta(hours=8),
                                touched_at=now,
                            )
                        )
                        audit(db, "SIGNED_IN", account.id)
                        result = answer(
                            "SIGNED_IN",
                            workspace_access=False,
                            next_step="ORGANISATION_SETUP_NOT_IMPLEMENTED",
                        )
                        result.set_cookie(
                            COOKIE,
                            token,
                            httponly=True,
                            secure=secure,
                            samesite="lax",
                            path=PATH,
                            max_age=28800,
                        )
                        return result
                    # Independent random reference for EVERY accepted request,
                    # including ineligible addresses. Never an account/proof ID.
                    reference = str(uuid4())
                    MAIL_LOG.info("Account email request %s: REQUEST_ACCEPTED", reference)
                    eligible = (
                        account is None
                        if action == "signup"
                        else account is not None and account.active
                    )
                    if eligible:
                        now = clock()
                        recipient = account.email if action == "recover" and account else email
                        proof = secrets.token_urlsafe(32)
                        purpose = "verify" if action == "signup" else "reset"
                        db.add(
                            PasswordProofRow(
                                digest=digest(proof),
                                purpose=purpose,
                                email_key=key,
                                email=recipient,
                                password_hash=encoded,
                                account_id=account.id if account else None,
                                epoch=account.epoch if account else None,
                                expires_at=now
                                + timedelta(minutes=30 if purpose == "verify" else 15),
                            )
                        )
                        audit(
                            db,
                            "VERIFICATION_REQUESTED"
                            if action == "signup"
                            else "RECOVERY_REQUESTED",
                        )
                        db.commit()  # Proof exists before the single after-response mail attempt.
                        background.add_task(deliver, recipient, purpose, proof, reference)
                    return answer("REQUEST_ACCEPTED", 202, support_reference=reference)
            proof = data.get("proof", "")
            if not TOKEN.fullmatch(proof):
                return answer("PROOF_INVALID", 400)
            value = password_value(data.get("password", ""), new=action == "reset")
            with database.session() as db:
                allowed = take_rate(db, "proof:" + digest(proof), 5, now)
            if not allowed:
                return answer("TRY_LATER", 429)
            with database.session() as db:
                row = db.scalar(
                    select(PasswordProofRow)
                    .where(PasswordProofRow.digest == digest(proof))
                    .with_for_update()
                )
                now = clock()  # Recheck after waiting for the proof lock.
                purpose = "verify" if action == "verify" else "reset"
                if not row or row.purpose != purpose or row.consumed_at or row.expires_at <= now:
                    return answer("PROOF_INVALID", 400)
                if action == "verify":
                    if not password_matches(row.password_hash or "", value):
                        return answer("PROOF_INVALID", 400)
                    now = clock()
                    if row.expires_at <= now:
                        return answer("PROOF_INVALID", 400)
                    account_id = uuid4()
                    created = db.execute(
                        insert(PasswordAccountRow)
                        .values(
                            id=account_id,
                            email_key=row.email_key,
                            email=row.email,
                            password_hash=row.password_hash,
                            epoch=1,
                            active=True,
                            created_at=now,
                        )
                        .on_conflict_do_nothing(index_elements=["email_key"])
                        .returning(PasswordAccountRow.id)
                    ).scalar_one_or_none()
                    now = clock()
                    if row.expires_at <= now:
                        db.rollback()  # A unique-key wait must not permit expired creation.
                        return answer("PROOF_INVALID", 400)
                    row.consumed_at = now
                    if created is None:
                        return answer("PROOF_INVALID", 400)
                    audit(db, "EMAIL_VERIFIED", account_id)
                    return answer("EMAIL_VERIFIED_SIGN_IN_REQUIRED")
                account = db.scalar(
                    select(PasswordAccountRow)
                    .where(PasswordAccountRow.id == row.account_id)
                    .with_for_update()
                )
                now = clock()  # Account-lock waits must not extend the proof lifetime.
                if (
                    not account
                    or not account.active
                    or account.epoch != row.epoch
                    or row.expires_at <= now
                ):
                    return answer("PROOF_INVALID", 400)
                new_hash = password_hash(value)
                now = clock()
                if row.expires_at <= now:
                    return answer("PROOF_INVALID", 400)
                account.password_hash = new_hash
                account.epoch += 1
                row.consumed_at = now
                db.execute(
                    update(PasswordSessionRow)
                    .where(PasswordSessionRow.account_id == account.id)
                    .values(revoked_at=now)
                )
                audit(db, "PASSWORD_RESET", account.id)
                return answer("PASSWORD_RESET_SIGN_IN_REQUIRED")
        except ValueError as error:
            code = str(error)
            if code not in {"EMAIL_INVALID", "PASSWORD_INVALID", "PASSWORD_POLICY", "AUTH_BUSY"}:
                code = "REQUEST_INVALID"
            return answer(code, 503 if code == "AUTH_BUSY" else 400)

    @app.post(PATH + "/{action}")
    async def command(action: str, request: Request, background: BackgroundTasks) -> JSONResponse:
        if action not in {"signup", "verify", "signin", "recover", "reset", "signout"}:
            return answer("REQUEST_INVALID", 404)
        data = await payload(request)
        if isinstance(data, JSONResponse):
            return data
        return await run_in_threadpool(execute, action, data, request, background)
