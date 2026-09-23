from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from authlib.jose import JoseError, JsonWebKey, jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth_boundary import pkce_challenge
from .config import Settings
from .domain import AuthenticationRequired, OidcClaims
from .persistence import AuthorizationCodeRow, sha256_text

logger = logging.getLogger("apbra_api.oidc")


class OidcValidationError(AuthenticationRequired):
    code = "OIDC_RESPONSE_INVALID"
    public_message = "Sign-in could not be validated. Please try again."


class OidcAdapter:
    """Provider boundary; APBRA authorization never consumes provider role/company claims."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._local_private_key: Any | None = None
        self._local_public_key: Any | None = None
        if settings.profile in {"development", "test"}:
            self._local_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            self._local_public_key = self._local_private_key.public_key()

    def _key(self) -> Any:
        if self.settings.profile in {"development", "test"}:
            return self._local_public_key
        assert self.settings.oidc_jwks_json
        key_set = json.loads(self.settings.oidc_jwks_json)
        if not isinstance(key_set, dict):
            raise OidcValidationError()
        return JsonWebKey.import_key_set(key_set)

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
        identity_selector: str | None = None,
    ) -> str:
        endpoint = (
            f"{self.settings.issuer}/authorize"
            if self.settings.profile in {"development", "test"}
            else self.settings.oidc_authorization_endpoint
        )
        if not endpoint:
            raise OidcValidationError()
        params = {
            "client_id": self.settings.oidc_audience,
            "redirect_uri": self.settings.callback_url,
            "response_type": "code",
            "scope": "openid profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if self.settings.profile in {"development", "test"} and identity_selector:
            params["identity"] = identity_selector
        return f"{endpoint}?{urlencode(params)}"

    def exchange_code(
        self,
        db: Session,
        *,
        code: str,
        verifier: str,
        redirect_uri: str,
        expected_nonce: str,
    ) -> OidcClaims:
        """Exchange a provider code without exposing provider tokens to the browser."""
        if self.settings.profile in {"development", "test"}:
            row = db.scalar(
                select(AuthorizationCodeRow)
                .where(AuthorizationCodeRow.code_digest == sha256_text(code))
                .with_for_update()
            )
            now = datetime.now(UTC)
            reason = (
                "code_not_found"
                if row is None
                else "code_consumed"
                if row.consumed_at is not None
                else "code_expired"
                if row.expires_at <= now
                else "redirect_mismatch"
                if row.redirect_uri != redirect_uri
                else "nonce_mismatch"
                if row.nonce != expected_nonce
                else "pkce_mismatch"
                if row.code_challenge != pkce_challenge(verifier)
                else None
            )
            if reason is not None:
                logger.warning("Local OIDC code exchange rejected: %s", reason)
                raise OidcValidationError()
            assert row is not None
            row.consumed_at = now
            token = self.issue_local_id_token(row.subject, row.display_name, expected_nonce)
            return self.validate_id_token(token, expected_nonce)

        if not self.settings.oidc_token_endpoint:
            raise OidcValidationError()
        form = {
            "grant_type": "authorization_code",
            "client_id": self.settings.oidc_audience,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        }
        if self.settings.oidc_client_secret:
            form["client_secret"] = self.settings.oidc_client_secret
        try:
            response = httpx.post(self.settings.oidc_token_endpoint, data=form, timeout=10.0)
            response.raise_for_status()
            token = response.json().get("id_token")
            if not isinstance(token, str):
                raise OidcValidationError()
            return self.validate_id_token(token, expected_nonce)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise OidcValidationError() from exc

    def issue_local_id_token(self, subject: str, display_name: str, nonce: str) -> str:
        if self.settings.profile not in {"development", "test"}:
            raise RuntimeError("local issuer is unavailable outside development and test")
        now = datetime.now(UTC)
        payload = {
            "iss": self.settings.issuer,
            "sub": subject,
            "aud": self.settings.oidc_audience,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "nonce": nonce,
            "name": display_name,
        }
        encoded = jwt.encode(
            {"alg": "RS256", "typ": "JWT", "kid": "apbra-local-runtime"},
            payload,
            self._local_private_key,
        )
        return encoded.decode() if isinstance(encoded, bytes) else str(encoded)

    def validate_id_token(self, token: str, expected_nonce: str) -> OidcClaims:
        try:
            claims = jwt.decode(
                token,
                self._key(),
                claims_options={
                    "iss": {"essential": True, "value": self.settings.issuer},
                    "sub": {"essential": True},
                    "aud": {"essential": True, "value": self.settings.oidc_audience},
                    "iat": {"essential": True},
                    "exp": {"essential": True},
                    "nbf": {"essential": True},
                    "nonce": {"essential": True, "value": expected_nonce},
                },
            )
            claims.validate(leeway=5)
            header = claims.header
            if header.get("alg") != "RS256":
                raise OidcValidationError()
            audience = claims["aud"]
            authorized_party = claims.get("azp")
            if isinstance(audience, list):
                if self.settings.oidc_audience not in audience:
                    raise OidcValidationError()
                if len(audience) > 1 and authorized_party != self.settings.oidc_audience:
                    raise OidcValidationError()
            elif audience != self.settings.oidc_audience:
                raise OidcValidationError()
            if authorized_party is not None and authorized_party != self.settings.oidc_audience:
                raise OidcValidationError()
            if not isinstance(claims["sub"], str) or not claims["sub"]:
                raise OidcValidationError()
            return OidcClaims(
                issuer=str(claims["iss"]),
                subject=str(claims["sub"]),
                audience=self.settings.oidc_audience,
                nonce=str(claims["nonce"]),
                expires_at=datetime.fromtimestamp(int(claims["exp"]), UTC),
                display_name=str(claims.get("name") or claims["sub"]),
            )
        except (JoseError, KeyError, TypeError, ValueError) as exc:
            raise OidcValidationError() from exc
