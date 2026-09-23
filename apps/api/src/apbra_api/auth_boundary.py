from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from .config import Settings

SESSION_COOKIE = "apbra_session"
AUTH_BINDING_COOKIE = "apbra_auth_binding"


def random_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def pkce_challenge(verifier: str) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    return encoded.rstrip(b"=").decode()


def safe_return_path(value: str) -> str:
    if not value.startswith("/") or value.startswith("//"):
        return "/"
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or "\\" in value:
        return "/"
    return parsed.path if parsed.path in {"/", "/invite"} else "/"


def csrf_token(session_token: str, secret: str) -> str:
    return hmac.new(secret.encode(), f"csrf:{session_token}".encode(), hashlib.sha256).hexdigest()


def csrf_matches(session_token: str, supplied: str | None, secret: str) -> bool:
    if supplied is None:
        return False
    return hmac.compare_digest(csrf_token(session_token, secret), supplied)


@dataclass(frozen=True)
class AuthStart:
    state: str
    nonce: str
    verifier: str
    browser_binding: str
    expires_at: datetime
    return_to: str

    @classmethod
    def create(cls, return_to: str) -> AuthStart:
        return cls(
            state=random_token(),
            nonce=random_token(),
            verifier=random_token(48),
            browser_binding=random_token(),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            return_to=safe_return_path(return_to),
        )


def cookie_secure(settings: Settings) -> bool:
    return settings.profile == "hosted"
