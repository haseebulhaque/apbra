import hashlib
import hmac
import json
from functools import lru_cache
from typing import Literal
from urllib.parse import ParseResult, urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parsed_absolute_url(value: str, *, https_only: bool) -> ParseResult:
    parsed = urlparse(value)
    try:
        _port = parsed.port
    except ValueError as exc:
        raise ValueError("URL port is invalid") from exc
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or (https_only and parsed.scheme != "https")
        or (not https_only and parsed.scheme not in {"http", "https"})
    ):
        raise ValueError("URL must be absolute, credential-free and use an allowed scheme")
    return parsed


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APBRA_", env_file=".env", extra="ignore")

    profile: Literal["development", "test", "hosted"] = "development"
    database_url: str
    public_origin: str = "http://127.0.0.1:5173"
    api_origin: str = "http://127.0.0.1:8000"
    session_secret: str = Field(min_length=32)
    bootstrap_enabled: bool = True
    invitation_ttl_days: int = Field(default=7, ge=1, le=30)
    session_ttl_seconds: int = Field(default=43_200, ge=300, le=86_400)
    oidc_issuer: str | None = None
    oidc_audience: str = "apbra-local-client"
    oidc_jwks_json: str | None = None
    oidc_authorization_endpoint: str | None = None
    oidc_token_endpoint: str | None = None
    oidc_client_secret: str | None = None
    oidc_response_issuer_policy: Literal["required", "single_issuer_compatibility"] = "required"
    oidc_authorization_response_iss_parameter_supported: bool = True

    @model_validator(mode="after")
    def validate_origins(self) -> "Settings":
        self.public_origin = self.public_origin.rstrip("/")
        self.api_origin = self.api_origin.rstrip("/")
        for origin in (self.public_origin, self.api_origin):
            parsed = _parsed_absolute_url(origin, https_only=self.profile == "hosted")
            if parsed.path not in {"", "/"} or parsed.query:
                raise ValueError("origins must contain only scheme, host and optional port")
            if self.profile in {"development", "test"}:
                if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
                    raise ValueError("local profiles require an HTTP loopback origin")
        return self

    def validate_security_profile(self) -> None:
        if (
            self.profile in {"development", "test"}
            and self.oidc_response_issuer_policy != "required"
        ):
            raise ValueError("local profiles require the strict response-issuer policy")
        if self.profile == "hosted":
            if self.bootstrap_enabled:
                raise ValueError("development bootstrap is forbidden in hosted profile")
            if not all(
                (
                    self.oidc_issuer,
                    self.oidc_jwks_json,
                    self.oidc_authorization_endpoint,
                    self.oidc_token_endpoint,
                )
            ):
                raise ValueError("hosted profile requires external OIDC endpoints and JWKS")
            for endpoint in (
                self.oidc_issuer,
                self.oidc_authorization_endpoint,
                self.oidc_token_endpoint,
            ):
                assert endpoint is not None
                _parsed_absolute_url(endpoint, https_only=True)
            if "local" in self.session_secret.lower():
                raise ValueError("hosted profile requires a non-development session secret")

    @property
    def issuer(self) -> str:
        if self.profile in {"development", "test"}:
            return f"{self.api_origin}/dev/oidc"
        assert self.oidc_issuer
        return self.oidc_issuer.rstrip("/")

    @property
    def callback_url(self) -> str:
        return f"{self.api_origin}/api/auth/callback"

    @property
    def callback_issuer_required(self) -> bool:
        return (
            self.oidc_response_issuer_policy == "required"
            or self.oidc_authorization_response_iss_parameter_supported
        )

    @property
    def oidc_configuration_digest(self) -> str:
        """Bind an auth transaction to the exact trusted provider configuration.

        The HMAC avoids persisting configured credentials or a reusable plain
        digest of a potentially low-entropy client secret.
        """

        payload = json.dumps(
            {
                "issuer": self.issuer,
                "client_id": self.oidc_audience,
                "redirect_uri": self.callback_url,
                "authorization_endpoint": self.oidc_authorization_endpoint,
                "token_endpoint": self.oidc_token_endpoint,
                "jwks": self.oidc_jwks_json,
                "client_secret": self.oidc_client_secret,
                "response_issuer_policy": self.oidc_response_issuer_policy,
                "response_issuer_supported": (
                    self.oidc_authorization_response_iss_parameter_supported
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hmac.new(self.session_secret.encode(), payload, hashlib.sha256).hexdigest()


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_security_profile()
    return settings
