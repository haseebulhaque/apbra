from __future__ import annotations

import base64
import binascii
import json
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from authlib.jose import JoseError, JsonWebKey, jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth_boundary import pkce_challenge
from .config import QualifiedIdentityProvider, Settings
from .domain import ApplicationError, AuthenticationRequired, OidcClaims
from .persistence import AuthorizationCodeRow, sha256_text

logger = logging.getLogger("apbra_api.oidc")


class OidcValidationError(AuthenticationRequired):
    code = "OIDC_RESPONSE_INVALID"
    public_message = "Sign-in could not be validated. Please try again."


class OidcProviderUnavailable(ApplicationError):
    status_code = 503
    code = "PROVIDER_UNAVAILABLE"
    public_message = "The sign-in provider is unavailable. Please try again later."


class OidcAdapter:
    """Provider boundary; APBRA authorization never consumes provider role/company claims."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._local_private_key: Any | None = None
        self._local_public_key: Any | None = None
        self._cache_lock = threading.RLock()
        self._metadata_cache: dict[str, tuple[float, dict[str, str]]] = {}
        self._jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        if settings.profile in {"development", "test"}:
            self._local_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            self._local_public_key = self._local_private_key.public_key()

    def public_providers(self) -> list[dict[str, str]]:
        if self.settings.profile in {"development", "test"}:
            return [{"profile_id": "local-test", "display_label": "Local development identity"}]
        return [
            {"profile_id": profile.profile_id, "display_label": profile.display_label}
            for profile in self.settings.identity_profiles()
            if profile.enabled
        ]

    def profile(self, profile_id: str | None) -> QualifiedIdentityProvider | None:
        if self.settings.profile in {"development", "test"}:
            if profile_id not in {None, "local-test"}:
                raise AuthenticationRequired()
            return None
        enabled = [profile for profile in self.settings.identity_profiles() if profile.enabled]
        if profile_id is None and len(enabled) == 1:
            return enabled[0]
        for profile in enabled:
            if profile.profile_id == profile_id:
                return profile
        raise AuthenticationRequired()

    @staticmethod
    def profile_id(profile: QualifiedIdentityProvider | None) -> str:
        return profile.profile_id if profile is not None else "local-test"

    def _json_get(self, url: str) -> dict[str, Any]:
        # Metadata/key GETs may be retried once. Never retry a code exchange.
        for attempt in range(2):
            try:
                response = httpx.get(url, timeout=5.0, follow_redirects=False)
                response.raise_for_status()
                break
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt == 0:
                    continue
                raise OidcProviderUnavailable() from exc
            except httpx.HTTPStatusError as exc:
                if attempt == 0 and exc.response.status_code >= 500:
                    continue
                raise OidcProviderUnavailable() from exc
            except httpx.HTTPError as exc:
                raise OidcProviderUnavailable() from exc
        if len(response.content) > 256_000:
            raise OidcValidationError()
        try:
            value = response.json()
        except ValueError as exc:
            raise OidcValidationError() from exc
        if not isinstance(value, dict):
            raise OidcValidationError()
        return value

    def _metadata(
        self, profile: QualifiedIdentityProvider, *, refresh: bool = False
    ) -> dict[str, str]:
        with self._cache_lock:
            cached = self._metadata_cache.get(profile.profile_id)
            if not refresh and cached and cached[0] > time.monotonic():
                return cached[1]
            raw = self._json_get(profile.discovery_url)
            if raw.get("issuer") != profile.issuer:
                raise OidcValidationError()
            metadata: dict[str, str] = {}
            for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
                value = raw.get(key)
                if not isinstance(value, str) or not profile.permits_endpoint(value):
                    raise OidcValidationError()
                metadata[key] = value
            supported = raw.get("id_token_signing_alg_values_supported")
            if supported is not None and (
                not isinstance(supported, list) or "RS256" not in supported
            ):
                raise OidcValidationError()
            self._metadata_cache[profile.profile_id] = (time.monotonic() + 300, metadata)
            return metadata

    def _jwks(self, profile: QualifiedIdentityProvider, *, refresh: bool = False) -> dict[str, Any]:
        with self._cache_lock:
            cached = self._jwks_cache.get(profile.profile_id)
            if not refresh and cached and cached[0] > time.monotonic():
                return cached[1]
            metadata = self._metadata(profile, refresh=refresh)
            value = self._json_get(metadata["jwks_uri"])
            keys = value.get("keys")
            if not isinstance(keys, list) or not 1 <= len(keys) <= 32:
                raise OidcValidationError()
            seen: set[str] = set()
            for key in keys:
                if (
                    not isinstance(key, dict)
                    or key.get("kty") != "RSA"
                    or not isinstance(key.get("kid"), str)
                    or not key["kid"]
                    or key["kid"] in seen
                    or key.get("use", "sig") != "sig"
                    or key.get("alg", "RS256") != "RS256"
                ):
                    raise OidcValidationError()
                seen.add(key["kid"])
            self._jwks_cache[profile.profile_id] = (time.monotonic() + 300, value)
            return value

    @staticmethod
    def _header(token: str) -> dict[str, Any]:
        if len(token) > 16_384:
            raise OidcValidationError()
        try:
            encoded = token.split(".", 2)[0]
            if len(encoded) > 2_000:
                raise OidcValidationError()
            header = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        except (ValueError, IndexError, binascii.Error) as exc:
            raise OidcValidationError() from exc
        if (
            not isinstance(header, dict)
            or header.get("alg") != "RS256"
            or str(header.get("typ", "JWT")).upper() != "JWT"
            or any(key in header for key in ("jwk", "jku", "x5u", "crit"))
        ):
            raise OidcValidationError()
        return header

    def _key(self, profile: QualifiedIdentityProvider | None, token: str) -> Any:
        header = self._header(token)
        if profile is None:
            return self._local_public_key
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise OidcValidationError()
        for refresh in (False, True):
            keys = self._jwks(profile, refresh=refresh)["keys"]
            match = next((key for key in keys if key["kid"] == kid), None)
            if match is not None:
                try:
                    return JsonWebKey.import_key(match)
                except (JoseError, ValueError) as exc:
                    raise OidcValidationError() from exc
        raise OidcValidationError()

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
        identity_selector: str | None = None,
        profile: QualifiedIdentityProvider | None = None,
    ) -> str:
        endpoint = (
            f"{self.settings.issuer}/authorize"
            if profile is None
            else self._metadata(profile)["authorization_endpoint"]
        )
        params = {
            "client_id": self.settings.oidc_audience if profile is None else profile.client_id,
            "redirect_uri": self.settings.callback_url,
            "response_type": "code",
            "scope": "openid profile" if profile is None else " ".join(profile.scopes),
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if profile is None and identity_selector:
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
        profile: QualifiedIdentityProvider | None = None,
    ) -> OidcClaims:
        """Exchange a provider code without exposing provider tokens to the browser."""
        if profile is None:
            if self.settings.profile not in {"development", "test"}:
                raise OidcValidationError()
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

        form = {
            "grant_type": "authorization_code",
            "client_id": profile.client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        }
        try:
            credential = profile.credential()
            if credential:
                form["client_secret"] = credential
            response = httpx.post(
                self._metadata(profile)["token_endpoint"],
                data=form,
                timeout=10.0,
                follow_redirects=False,
            )
            response.raise_for_status()
            if len(response.content) > 32_000:
                raise OidcValidationError()
            token = response.json().get("id_token")
            if not isinstance(token, str):
                raise OidcValidationError()
            return self.validate_id_token(token, expected_nonce, profile=profile)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                raise OidcValidationError() from exc
            raise OidcProviderUnavailable() from exc
        except httpx.HTTPError as exc:
            raise OidcProviderUnavailable() from exc
        except (ValueError, TypeError) as exc:
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

    def validate_id_token(
        self,
        token: str,
        expected_nonce: str,
        *,
        profile: QualifiedIdentityProvider | None = None,
    ) -> OidcClaims:
        if profile is None and self.settings.profile not in {"development", "test"}:
            profile = self.profile(None)
        issuer = self.settings.issuer if profile is None else profile.issuer
        audience_id = self.settings.oidc_audience if profile is None else profile.client_id
        try:
            claims = jwt.decode(
                token,
                self._key(profile, token),
                claims_options={
                    "iss": {"essential": True, "value": issuer},
                    "sub": {"essential": True},
                    "aud": {"essential": True, "value": audience_id},
                    "iat": {"essential": True},
                    "exp": {"essential": True},
                    "nbf": {"essential": True},
                    "nonce": {"essential": True, "value": expected_nonce},
                },
            )
            claims.validate(leeway=5)
            audience = claims["aud"]
            authorized_party = claims.get("azp")
            if isinstance(audience, list):
                if audience_id not in audience:
                    raise OidcValidationError()
                if len(audience) > 1 and authorized_party != audience_id:
                    raise OidcValidationError()
            elif audience != audience_id:
                raise OidcValidationError()
            if authorized_party is not None and authorized_party != audience_id:
                raise OidcValidationError()
            if not isinstance(claims["sub"], str) or not claims["sub"]:
                raise OidcValidationError()
            if not isinstance(claims["iss"], str) or claims["iss"] != issuer:
                raise OidcValidationError()
            return OidcClaims(
                issuer=claims["iss"],
                subject=str(claims["sub"]),
                audience=audience_id,
                nonce=str(claims["nonce"]),
                expires_at=datetime.fromtimestamp(int(claims["exp"]), UTC),
                display_name=str(claims.get("name") or claims["sub"]),
            )
        except (JoseError, KeyError, TypeError, ValueError) as exc:
            raise OidcValidationError() from exc
