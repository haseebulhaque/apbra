import hashlib
import hmac
import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import ParseResult, urlparse
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from .model_provider import (
    COMPILER_MAX_VISUALS_PER_PAGE,
    ProviderConfigurationError,
    ProviderProfile,
)


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


class UploadPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_extensions: list[str] = Field(min_length=1, max_length=20)
    reference_extensions: list[str] = Field(min_length=1, max_length=20)
    max_file_bytes: int = Field(ge=1, le=100_000_000)
    max_files_per_selection: int = Field(ge=1, le=50)
    max_data_items_per_report: int = Field(ge=1, le=100)
    max_reference_items_per_report: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def validate_extensions(self) -> "UploadPolicy":
        allowed = {"CSV", "XLSX", "PNG", "JPG", "JPEG"}
        data = [item.upper().lstrip(".") for item in self.data_extensions]
        references = [item.upper().lstrip(".") for item in self.reference_extensions]
        if (
            len(set(data)) != len(data)
            or len(set(references)) != len(references)
            or not set(data).issubset({"CSV", "XLSX"})
            or not set(references).issubset({"PNG", "JPG", "JPEG"})
            or set(data) & set(references)
            or not set(data + references).issubset(allowed)
            or self.max_file_bytes > 5_000_000
        ):
            raise ValueError("upload extensions are duplicated or unsupported")
        self.data_extensions = data
        self.reference_extensions = references
        return self


class OrganisationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1, max_length=200)
    display_name: str = Field(alias="displayName", min_length=1, max_length=200)
    locale: str = Field(min_length=2, max_length=35)
    timezone: str = Field(min_length=1, max_length=120)


class BrandingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    primary: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    accent: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    report_naming: str = Field(alias="reportNaming", min_length=1, max_length=500)
    page_naming: str = Field(alias="pageNaming", min_length=1, max_length=500)
    executive_convention: str = Field(alias="executiveConvention", min_length=1, max_length=500)
    theme_name: str = Field(alias="themeName", min_length=1, max_length=200)


class GenerationCapabilityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    enabled: bool
    supported_capabilities: list[str] = Field(
        alias="supportedCapabilities", min_length=1, max_length=100
    )
    supported_trend_grains: list[Literal["DAY", "MONTH", "QUARTER", "YEAR"]] = Field(
        alias="supportedTrendGrains", min_length=1, max_length=4
    )
    validation_required: bool = Field(alias="validationRequired")
    policy: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_unique_values(self) -> "GenerationCapabilityPolicy":
        if len(set(self.supported_capabilities)) != len(self.supported_capabilities) or len(
            set(self.supported_trend_grains)
        ) != len(self.supported_trend_grains):
            raise ValueError("generation capabilities and trend grains must be unique")
        return self


class GovernancePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    require_knowledge: bool = Field(alias="requireKnowledge")
    require_accessibility: bool = Field(alias="requireAccessibility")
    require_validation: bool = Field(alias="requireValidation")
    max_visuals_per_page: int = Field(
        alias="maxVisualsPerPage", ge=1, le=COMPILER_MAX_VISUALS_PER_PAGE
    )
    max_pages: int = Field(alias="maxPages", ge=1, le=100)
    human_review_at_visuals: int = Field(alias="humanReviewAtVisuals", ge=1, le=500)


class GenerationPolicy(BaseModel):
    """Exact canonical compiler capability/branding policy supplied by configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    organisation: OrganisationPolicy
    branding: BrandingPolicy
    generation: GenerationCapabilityPolicy
    governance: GovernancePolicy


class ClarificationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_rounds: int = Field(ge=1, le=20)
    max_questions_per_round: int = Field(ge=1, le=20)
    max_answer_characters: int = Field(ge=100, le=20_000)


class QualifiedIdentityProvider(BaseModel):
    """Deployment-owned OIDC trust. No company or browser may create this profile."""

    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    display_label: str = Field(min_length=1, max_length=100)
    provider_kind: Literal["ENTRA_EXTERNAL_ID"]
    issuer: str
    discovery_url: str
    client_id: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=lambda: ["openid", "profile"])
    enabled: bool = True
    credential_env: str | None = Field(default=None, pattern=r"^APBRA_OIDC_CREDENTIAL_[A-Z0-9_]+$")
    allowed_endpoint_origins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_trust(self) -> "QualifiedIdentityProvider":
        issuer = _parsed_absolute_url(self.issuer, https_only=True)
        discovery = _parsed_absolute_url(self.discovery_url, https_only=True)
        if issuer.query or issuer.fragment:
            raise ValueError("qualified issuer must be an exact HTTPS authority")
        origins = [f"{issuer.scheme}://{issuer.netloc}"]
        for value in self.allowed_endpoint_origins:
            parsed = _parsed_absolute_url(value, https_only=True)
            if parsed.path not in {"", "/"} or parsed.query:
                raise ValueError("allowed endpoint origins must be HTTPS origins")
            origins.append(f"{parsed.scheme}://{parsed.netloc}")
        if len(set(origins)) != len(origins):
            raise ValueError("duplicate trusted endpoint origin")
        if f"{discovery.scheme}://{discovery.netloc}" not in origins:
            raise ValueError("discovery origin must be qualified")
        if "openid" not in self.scopes or len(set(self.scopes)) != len(self.scopes):
            raise ValueError("OIDC scopes must include openid and be unique")
        if not set(self.scopes).issubset({"openid", "profile", "email"}):
            raise ValueError("basic APBRA sign-in cannot request integration scopes")
        self.allowed_endpoint_origins = origins[1:]
        return self

    def permits_endpoint(self, value: str) -> bool:
        parsed = _parsed_absolute_url(value, https_only=True)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        trusted = {f"{urlparse(self.issuer).scheme}://{urlparse(self.issuer).netloc}"}
        trusted.update(self.allowed_endpoint_origins)
        return origin in trusted and not parsed.fragment

    def credential(self) -> str | None:
        if self.credential_env is None:
            return None
        value = os.environ.get(self.credential_env)
        if not value:
            raise ValueError("qualified OIDC credential reference is unavailable")
        return value


class FoundryHostBinding(BaseModel):
    """Private deployment attestation, never browser or model authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    company_id: UUID
    tenant_id: UUID
    client_id: UUID
    home_account_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,255}$")
    provider_profile: ProviderProfile
    knowledge_binding: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,120}$")
    knowledge_scope: Literal["SHARED_STANDARDS", "TENANT_PRIVATE"]
    agent_version: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,80}$")
    qualification: Literal["LIVE_METADATA_VERIFIED"]
    manual_authentication_approved: bool
    authorization_deadline: float = Field(gt=0, allow_inf_nan=False)

    def binding_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def __repr__(self) -> str:
        return "FoundryHostBinding(<private attestation>)"

    def __str__(self) -> str:
        return "<private Foundry host attestation>"


class FoundryQualificationBinding(BaseModel):
    """Finite private discovery approval; never a runtime activation attestation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    tenant_id: Literal["4825d1f6-89d8-4e38-9418-2827aa59a23c"]
    client_id: Literal["04b07795-8ddb-461a-bbee-02f9e1bf7b46"]
    project_endpoint: Literal[
        "https://s08-cloud-ai-agent-resource.services.ai.azure.com/api/projects/s08-cloud-ai-agent"
    ]
    agent_name: Literal["s08-document-grounded-agent"]
    agent_version: Literal["6"]
    knowledge_base: Literal["s08-knowledge-base"]
    agent_api_version: Literal["v1"]
    search_api_version: Literal["2025-11-01-preview"]
    manual_authentication_approved: bool
    independent_private_terminal_approved: bool
    authorization_deadline: float = Field(gt=0, allow_inf_nan=False)
    request_timeout_seconds: float = Field(gt=0, le=300, allow_inf_nan=False)
    max_metadata_response_bytes: int = Field(gt=0)
    max_projection_items: int = Field(gt=0)
    max_projection_string_characters: int = Field(gt=0)

    def __repr__(self) -> str:
        return "FoundryQualificationBinding(<private approval>)"

    def __str__(self) -> str:
        return "<private Foundry qualification approval>"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APBRA_", env_file=".env", extra="ignore")

    profile: Literal["development", "test", "hosted"] = "development"
    database_url: str = Field(repr=False)
    public_origin: str = "http://127.0.0.1:5173"
    api_origin: str = "http://127.0.0.1:8000"
    session_secret: str = Field(min_length=32, repr=False)
    bootstrap_enabled: bool = True
    invitation_ttl_days: int = Field(default=7, ge=1, le=30)
    session_ttl_seconds: int = Field(default=43_200, ge=300, le=86_400)
    evidence_root: Path = Path("/var/lib/apbra/evidence")
    artifact_root: Path = Path("/var/lib/apbra/artifacts")
    reference_root: Path | None = None
    semantic_bridge_path: Path = Path("/app/runtime/apbra-semantic-bridge.mjs")
    generation_bridge_path: Path = Path("/app/runtime/apbra-generation-bridge.mjs")
    semantic_node_path: Path = Path("/usr/local/bin/node")
    semantic_timeout_seconds: int | None = Field(default=None, ge=1, le=120)
    generation_timeout_seconds: int | None = Field(default=None, ge=1, le=120)
    upload_policy_json: str | None = None
    generation_policy_json: str | None = None
    clarification_policy_json: str | None = None
    automatic_generation_enabled: bool | None = None
    model_provider_profile_json: str | None = None
    qualified_provider_profiles_json: str | None = None
    model_provider_api_key: SecretStr | None = None
    foundry_host_enabled: bool = False
    foundry_qualification_enabled: bool = False
    foundry_qualification_binding_json: SecretStr | None = Field(default=None, repr=False)
    foundry_host_binding_json: SecretStr | None = Field(default=None, repr=False)
    tenant_secret_keyring_json: SecretStr | None = Field(default=None, repr=False)
    test_semantic_simulator_enabled: bool = False
    oidc_issuer: str | None = None
    oidc_audience: str = "apbra-local-client"
    oidc_jwks_json: str | None = None
    oidc_authorization_endpoint: str | None = None
    oidc_token_endpoint: str | None = None
    oidc_client_secret: str | None = Field(default=None, repr=False)
    oidc_profiles_json: str | None = Field(default=None, repr=False)
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
        if self.test_semantic_simulator_enabled and self.profile != "test":
            raise ValueError("the deterministic semantic simulator is test-profile only")
        if (
            self.profile in {"development", "test"}
            and self.oidc_response_issuer_policy != "required"
        ):
            raise ValueError("local profiles require the strict response-issuer policy")
        if self.profile == "hosted":
            if self.bootstrap_enabled:
                raise ValueError("development bootstrap is forbidden in hosted profile")
            profiles = self.identity_profiles()
            if not any(profile.enabled for profile in profiles):
                raise ValueError("hosted profile requires a qualified enabled identity provider")
            if (
                self.oidc_response_issuer_policy == "single_issuer_compatibility"
                and sum(profile.enabled for profile in profiles) != 1
            ):
                raise ValueError("response-issuer compatibility requires one enabled provider")
            for provider in profiles:
                if provider.enabled:
                    provider.credential()
            if "local" in self.session_secret.lower():
                raise ValueError("hosted profile requires a non-development session secret")
        # Provider/profile/credential policy belongs to the effective tenant
        # settings version. Bootstrap validates it before first activation.

    @staticmethod
    def _configured_json(value: str | None, model: type[BaseModel], code: str) -> BaseModel:
        if value is None or not value.strip():
            raise ProviderConfigurationError(f"{code}_MISSING")
        try:
            return model.model_validate_json(value)
        except ValidationError as exc:
            raise ProviderConfigurationError(f"{code}_INVALID") from exc

    def upload_policy(self) -> UploadPolicy:
        return self._configured_json(self.upload_policy_json, UploadPolicy, "UPLOAD_POLICY")  # type: ignore[return-value]

    def generation_policy(self) -> GenerationPolicy:
        return self._configured_json(
            self.generation_policy_json, GenerationPolicy, "GENERATION_POLICY"
        )  # type: ignore[return-value]

    def clarification_policy(self) -> ClarificationPolicy:
        return self._configured_json(
            self.clarification_policy_json, ClarificationPolicy, "CLARIFICATION_POLICY"
        )  # type: ignore[return-value]

    def model_profile(self) -> ProviderProfile:
        if self.automatic_generation_enabled is not True:
            raise ProviderConfigurationError("AUTOMATIC_GENERATION_DISABLED")
        return ProviderProfile.parse(self.model_provider_profile_json)

    def qualified_provider_profiles(self) -> tuple[ProviderProfile, ...]:
        """Deployment-owned qualification catalogue, not tenant self-attestation."""
        if not self.qualified_provider_profiles_json:
            return ()
        try:
            profiles = TypeAdapter(list[ProviderProfile]).validate_json(
                self.qualified_provider_profiles_json
            )
        except ValidationError as exc:
            raise ProviderConfigurationError("QUALIFIED_PROFILES_INVALID") from exc
        if len({profile.profile_id for profile in profiles}) != len(profiles):
            raise ProviderConfigurationError("QUALIFIED_PROFILES_DUPLICATED")
        return tuple(profiles)

    def foundry_qualification_binding(self) -> FoundryQualificationBinding:
        from datetime import UTC, datetime

        try:
            if (
                self.profile != "development"
                or self.foundry_qualification_enabled is not True
                or self.foundry_host_enabled is not False
                or self.foundry_qualification_binding_json is None
            ):
                raise ValueError("Disabled qualification")
            binding = FoundryQualificationBinding.model_validate_json(
                self.foundry_qualification_binding_json.get_secret_value()
            )
            if (
                binding.manual_authentication_approved is not True
                or binding.independent_private_terminal_approved is not True
                or not time.time() < binding.authorization_deadline
                or binding.authorization_deadline
                > datetime(2026, 10, 10, 2, 9, tzinfo=UTC).timestamp()
            ):
                raise ValueError("Expired qualification approval")
            return binding
        except Exception:
            raise ProviderConfigurationError("FOUNDRY_QUALIFICATION_UNAVAILABLE") from None

    def foundry_host_binding(self) -> FoundryHostBinding:
        try:
            if (
                self.foundry_host_enabled is not True
                or self.profile != "development"
                or self.foundry_host_binding_json is None
            ):
                raise ValueError("Disabled host")
            binding = FoundryHostBinding.model_validate_json(
                self.foundry_host_binding_json.get_secret_value()
            )
            if (
                binding.manual_authentication_approved is not True
                or binding.authorization_deadline <= time.time()
                or binding.provider_profile.protocol != "FOUNDRY_AGENT_RESPONSES"
                or not any(
                    profile.model_dump(mode="json")
                    == binding.provider_profile.model_dump(mode="json")
                    for profile in self.qualified_provider_profiles()
                )
            ):
                raise ValueError("Unqualified host")
            return binding
        except Exception:
            raise ProviderConfigurationError("FOUNDRY_HOST_CONFIGURATION_UNAVAILABLE") from None

    def model_credential(self) -> str:
        if self.model_provider_profile_json is not None and (
            ProviderProfile.parse(self.model_provider_profile_json).protocol
            == "FOUNDRY_AGENT_RESPONSES"
        ):
            raise ProviderConfigurationError("FOUNDRY_SERVER_IDENTITY_REQUIRED")
        if self.model_provider_api_key is None:
            raise ProviderConfigurationError("MODEL_CREDENTIAL_MISSING")
        value = self.model_provider_api_key.get_secret_value()
        if not value:
            raise ProviderConfigurationError("MODEL_CREDENTIAL_MISSING")
        return value

    def identity_profiles(self) -> tuple[QualifiedIdentityProvider, ...]:
        if not self.oidc_profiles_json:
            return ()
        try:
            profiles = TypeAdapter(list[QualifiedIdentityProvider]).validate_json(
                self.oidc_profiles_json
            )
        except ValidationError as exc:
            raise ValueError("qualified identity provider catalogue is invalid") from exc
        if len({profile.profile_id for profile in profiles}) != len(profiles):
            raise ValueError("qualified identity provider IDs are duplicated")
        return tuple(profiles)

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

    def identity_profile_digest(self, profile: QualifiedIdentityProvider | None) -> str:
        if profile is None:
            return self.oidc_configuration_digest
        payload = json.dumps(
            {
                "profile": profile.model_dump(mode="json"),
                "credential": profile.credential(),
                "redirect_uri": self.callback_url,
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
