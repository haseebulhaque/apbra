"""Provider-neutral, bounded server-side structured model calls.

The browser never receives this configuration or its credential.  Callers
must still validate every returned object against APBRA's deterministic
contracts; a successful provider response is only untrusted candidate data.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ProviderConfigurationError(ValueError):
    """The explicitly configured profile is absent, malformed or unsupported."""


class ProviderCallError(RuntimeError):
    """A safe provider failure which may be persisted without response content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ProviderCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structured_output: bool
    vision: bool


class ProviderProfile(BaseModel):
    """All runtime choices and operating limits are explicit configuration."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=120)
    protocol: Literal["OPENAI_CHAT_COMPATIBLE", "AZURE_OPENAI_CHAT_COMPATIBLE"]
    endpoint: str = Field(min_length=1, max_length=2_000)
    model_or_deployment: str = Field(min_length=1, max_length=255)
    api_version: str = Field(min_length=1, max_length=80)
    region: str = Field(min_length=1, max_length=120)
    prompt_version: str = Field(min_length=1, max_length=120)
    configuration_id: str = Field(min_length=1, max_length=120)
    capabilities: ProviderCapabilities
    max_calls_per_operation: int = Field(ge=1, le=20)
    max_input_characters: int = Field(ge=1_000, le=2_000_000)
    max_output_tokens: int = Field(ge=128, le=100_000)
    time_budget_seconds: float = Field(gt=0, le=600)
    request_timeout_seconds: float = Field(gt=0, le=300)
    retry_limit: int = Field(ge=0, le=5)

    @model_validator(mode="after")
    def validate_endpoint(self) -> ProviderProfile:
        parsed = urlparse(self.endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("provider endpoint must be an absolute credential-free HTTPS URL")
        if self.retry_limit + 1 > self.max_calls_per_operation:
            raise ValueError("retry policy exceeds the configured call budget")
        return self

    @classmethod
    def parse(cls, value: str | None) -> ProviderProfile:
        if value is None or not value.strip():
            raise ProviderConfigurationError("MODEL_PROFILE_MISSING")
        try:
            decoded = json.loads(value)
            return cls.model_validate(decoded)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ProviderConfigurationError("MODEL_PROFILE_INVALID") from exc


@dataclass(frozen=True)
class ProviderRequest:
    task: Literal["REQUIREMENT_ANALYSIS", "REPORT_DESIGN"]
    system_prompt: str
    context: dict[str, Any]
    output_schema: dict[str, Any]
    requires_vision: bool = False


@dataclass(frozen=True)
class ProviderResult:
    value: dict[str, Any]
    usage: dict[str, int | None]
    latency_ms: int
    call_count: int
    profile_id: str
    model_or_deployment: str
    prompt_version: str
    configuration_id: str
    capability_profile: dict[str, bool]


class ModelProvider(Protocol):
    profile: ProviderProfile

    def structured(self, request: ProviderRequest) -> ProviderResult: ...


class OpenAICompatibleProvider:
    """Exact-endpoint adapter; it never selects or falls back to another runtime."""

    def __init__(
        self,
        profile: ProviderProfile,
        credential: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not credential:
            raise ProviderConfigurationError("MODEL_CREDENTIAL_MISSING")
        if not profile.capabilities.structured_output:
            raise ProviderConfigurationError("STRUCTURED_OUTPUT_UNSUPPORTED")
        self.profile = profile
        self._credential = credential
        self._transport = transport

    def _request_body(self, request: ProviderRequest) -> dict[str, Any]:
        if request.requires_vision and not self.profile.capabilities.vision:
            raise ProviderConfigurationError("VISION_UNSUPPORTED")
        user_content = json.dumps(request.context, sort_keys=True, separators=(",", ":"))
        if len(request.system_prompt) + len(user_content) > self.profile.max_input_characters:
            raise ProviderCallError("MODEL_INPUT_BUDGET_EXCEEDED")
        return {
            "model": self.profile.model_or_deployment,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.task.lower(),
                    "strict": True,
                    "schema": request.output_schema,
                },
            },
            "max_tokens": self.profile.max_output_tokens,
        }

    def structured(self, request: ProviderRequest) -> ProviderResult:
        body = self._request_body(request)
        headers = {"Content-Type": "application/json"}
        params: dict[str, str] = {}
        if self.profile.protocol == "AZURE_OPENAI_CHAT_COMPATIBLE":
            headers["api-key"] = self._credential
            params["api-version"] = self.profile.api_version
        else:
            headers["Authorization"] = f"Bearer {self._credential}"
            headers["OpenAI-Version"] = self.profile.api_version
        started = time.monotonic()
        calls = 0
        last_code = "MODEL_PROVIDER_FAILED"
        while calls < min(
            self.profile.max_calls_per_operation, self.profile.retry_limit + 1
        ):
            if time.monotonic() - started >= self.profile.time_budget_seconds:
                raise ProviderCallError("MODEL_TIME_BUDGET_EXCEEDED")
            calls += 1
            try:
                with httpx.Client(
                    timeout=self.profile.request_timeout_seconds,
                    transport=self._transport,
                    follow_redirects=False,
                ) as client:
                    response = client.post(
                        self.profile.endpoint, headers=headers, params=params, json=body
                    )
                if response.status_code in {408, 429, 500, 502, 503, 504}:
                    last_code = "MODEL_PROVIDER_TRANSIENT_FAILURE"
                    continue
                if response.status_code < 200 or response.status_code >= 300:
                    raise ProviderCallError("MODEL_PROVIDER_REJECTED")
                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
                value = json.loads(content) if isinstance(content, str) else content
                if not isinstance(value, dict):
                    raise ProviderCallError("MODEL_OUTPUT_INVALID")
                usage = payload.get("usage") if isinstance(payload, dict) else None
                if not isinstance(usage, dict):
                    usage = {}
                return ProviderResult(
                    value=value,
                    usage={
                        "prompt_tokens": _integer_or_none(usage.get("prompt_tokens")),
                        "completion_tokens": _integer_or_none(
                            usage.get("completion_tokens")
                        ),
                        "total_tokens": _integer_or_none(usage.get("total_tokens")),
                    },
                    latency_ms=int((time.monotonic() - started) * 1_000),
                    call_count=calls,
                    profile_id=self.profile.profile_id,
                    model_or_deployment=self.profile.model_or_deployment,
                    prompt_version=self.profile.prompt_version,
                    configuration_id=self.profile.configuration_id,
                    capability_profile=self.profile.capabilities.model_dump(),
                )
            except ProviderCallError:
                raise
            except (httpx.TimeoutException, httpx.TransportError):
                last_code = "MODEL_PROVIDER_TIMEOUT"
                continue
            except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise ProviderCallError("MODEL_OUTPUT_INVALID") from exc
        raise ProviderCallError(last_code)


def _integer_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


class DeterministicFakeProvider:
    """Injected test double.  It is never constructed by production configuration."""

    def __init__(self, profile: ProviderProfile, responses: list[dict[str, Any]]) -> None:
        self.profile = profile
        self._responses = list(responses)
        self.requests: list[ProviderRequest] = []

    def structured(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        if not self._responses:
            raise ProviderCallError("FAKE_PROVIDER_EXHAUSTED")
        value = self._responses.pop(0)
        return ProviderResult(
            value=value,
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            latency_ms=1,
            call_count=1,
            profile_id=self.profile.profile_id,
            model_or_deployment=self.profile.model_or_deployment,
            prompt_version=self.profile.prompt_version,
            configuration_id=self.profile.configuration_id,
            capability_profile=self.profile.capabilities.model_dump(),
        )
