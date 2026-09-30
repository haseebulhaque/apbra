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


def _string_array(description: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if description is not None:
        value["description"] = description
    return value


def _measure_schema() -> dict[str, Any]:
    fields = {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "businessDefinition": {"type": "string"},
        "aggregation": {
            "type": "string",
            "description": (
                "Use FILTERED_COUNT for a counted subset. DIFFERENCE and RATIO require "
                "exact operand measure IDs."
            ),
            "enum": [
                "SUM",
                "DISTINCTCOUNT",
                "COUNT",
                "AVERAGE",
                "FILTERED_COUNT",
                "DIFFERENCE",
                "RATIO",
                "PERCENTAGE_OF_TOTAL",
            ],
        },
        "field": {"type": "string"},
        "numeratorMeasureId": {"type": "string"},
        "denominatorMeasureId": {"type": "string"},
        "format": {
            "type": "string",
            "enum": ["currency", "integer", "decimal", "percentage"],
        },
        "filterField": {"type": "string"},
        "filterValue": {"type": "string"},
        "contextField": {"type": "string"},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(fields),
        "properties": fields,
    }


def requirement_analysis_schema() -> dict[str, Any]:
    """Strict provider schema mirroring the canonical TypeScript contract."""

    measure = _measure_schema()
    coverage_fields = {
        "id": {"type": "string"},
        "kind": {
            "type": "string",
            "enum": ["KPI", "FILTER", "BREAKDOWN", "TREND", "LIFECYCLE"],
        },
        "measureNames": _string_array(
            "Exact names of measures completely defined in this obligation."
        ),
        "fields": _string_array(
            "Exact Table.Column bindings. KPI uses none; FILTER and BREAKDOWN use one "
            "or more; TREND uses exactly one date or datetime field."
        ),
        "pageNames": _string_array(
            "Only exact names already declared in interpretation.pages."
        ),
        "required": {
            "type": "boolean",
            "description": "Whether confirmation requires this obligation downstream.",
        },
        "minimumRepresentations": {
            "type": "integer",
            "minimum": 0,
            "description": "Required obligations use at least 1; optional ones use 0.",
        },
        "measures": {
            "type": "array",
            "description": (
                "Complete definitions for every measureName in this obligation. When a "
                "measure is reused, repeat the exact same full JSON measure object without "
                "changing its ID, name, definition, format, fields, or operands."
            ),
            "items": measure,
        },
        "timeGrain": {
            "type": "string",
            "description": "TREND uses a non-NONE grain; every other kind uses NONE.",
            "enum": ["NONE", "DAY", "WEEK", "MONTH", "QUARTER", "YEAR"],
        },
        "lifecycleValues": _string_array(
            "Non-empty only for LIFECYCLE and empty for every other kind."
        ),
    }
    coverage = {
        "type": "object",
        "description": (
            "Typed semantic obligation. KPI uses measures and no fields; FILTER uses fields "
            "and no measures; BREAKDOWN uses measures and fields; TREND uses measures, "
            "exactly one date/datetime field, and a non-NONE time grain."
        ),
        "additionalProperties": False,
        "required": list(coverage_fields),
        "properties": coverage_fields,
    }
    option_fields = {
        "id": {"type": "string"},
        "label": {"type": "string"},
        "coverageOverrides": {"type": "array", "items": coverage},
        "pageScope": _string_array(),
        "audience": {"type": "string"},
    }
    clarification_fields = {
        "id": {"type": "string"},
        "category": {
            "type": "string",
            "enum": [
                "METRIC_DEFINITION",
                "TIME_COMPARISON",
                "SECURITY",
                "AUDIENCE",
                "PAGE_SCOPE",
                "FILTER_SCOPE",
                "OTHER",
            ],
        },
        "question": {"type": "string"},
        "reason": {"type": "string"},
        "required": {"type": "boolean"},
        "coverageRequirementIds": _string_array(),
        "selection": {"type": "string", "enum": ["SINGLE"]},
        "options": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(option_fields),
                "properties": option_fields,
            },
        },
    }
    interpretation_fields = {
        "request_kind": {
            "type": "string",
            "enum": ["POWER_BI_REPORT", "OUT_OF_SCOPE"],
        },
        "objective": {"type": "string"},
        "businessQuestions": _string_array(),
        "kpis": _string_array(),
        "dimensions": _string_array(),
        "filters": _string_array(
            "Exact confirmed Table.Column report filters. A declared report filter satisfies "
            "its FILTER obligation without requiring a duplicate slicer."
        ),
        "audience": {"type": "string"},
        "pages": _string_array(),
        "assumptions": _string_array(),
        "ambiguities": _string_array(),
        "clarifications": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(clarification_fields),
                "properties": clarification_fields,
            },
        },
        "coverageRequirements": {"type": "array", "items": coverage},
        "businessQuestionCoverage": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["question", "coverageRequirementIds"],
                "properties": {
                    "question": {"type": "string"},
                    "coverageRequirementIds": _string_array(),
                },
            },
        },
    }
    question_fields = {
        "id": {"type": "string"},
        "category": clarification_fields["category"],
        "question": {"type": "string"},
        "reason": {"type": "string"},
        "required": {"type": "boolean"},
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "label"],
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                },
            },
        },
        "allowFreeText": {"type": "boolean"},
    }
    summary_fields = {
        "objective": {"type": "string"},
        "businessQuestions": _string_array(),
        "kpiDefinitions": _string_array(),
        "scopeAndTime": _string_array(),
        "dimensionsAndFilters": _string_array(),
        "lifecycleDefinitions": _string_array(),
        "materialPolicyDecisions": _string_array(),
    }
    properties = {
        "state": {
            "type": "string",
            "enum": [
                "NEEDS_CLARIFICATION",
                "READY_FOR_CONFIRMATION",
                "HUMAN_REVIEW_REQUIRED",
                "UNSUPPORTED",
                "OUT_OF_SCOPE",
            ],
        },
        "interpretation": {
            "type": "object",
            "additionalProperties": False,
            "required": list(interpretation_fields),
            "properties": interpretation_fields,
        },
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(question_fields),
                "properties": question_fields,
            },
        },
        "unresolvedAmbiguities": _string_array(),
        "confirmationSummary": {
            "type": "object",
            "additionalProperties": False,
            "required": list(summary_fields),
            "properties": summary_fields,
        },
        "conflictReasons": _string_array(),
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


def report_design_schema() -> dict[str, Any]:
    """Strict provider schema mirroring the canonical ReportDesign contract."""

    relationship_fields = {
        "fromTable": {"type": "string"},
        "fromColumn": {"type": "string"},
        "toTable": {"type": "string"},
        "toColumn": {"type": "string"},
    }
    visual_fields = {
        "id": {"type": "string"},
        "type": {
            "type": "string",
            "description": (
                "card requires exactly one measure; bar, column, and line require at least "
                "one measure and a categoryField; table requires at least one field or "
                "measure; slicer requires exactly one field binding and no measure."
            ),
            "enum": ["card", "bar", "column", "line", "table", "slicer"],
        },
        "title": {"type": "string"},
        "categoryField": {
            "type": "string",
            "description": (
                "Exact Table.Column category for bar, column, or line. For a slicer, leave "
                "this empty and put the one binding in fields."
            ),
        },
        "timeGrain": {
            "type": "string",
            "description": (
                "Use the exact confirmed supported grain for a trend visual and NONE for "
                "every non-trend visual."
            ),
            "enum": ["NONE", "DAY", "MONTH", "QUARTER", "YEAR"],
        },
        "measureIds": _string_array("Exact IDs declared in ReportDesign.measures."),
        "fields": _string_array(
            "Exact Table.Column bindings. A slicer uses exactly one fields entry and an "
            "empty categoryField and measureIds. Do not create a slicer for a field already "
            "listed in ReportDesign.filters."
        ),
        "altText": {"type": "string"},
    }
    page_fields = {
        "id": {"type": "string"},
        "name": {
            "type": "string",
            "description": (
                "Exact name of one confirmed required page; emit every confirmed page once "
                "without renaming it."
            ),
        },
        "purpose": {"type": "string"},
        "visuals": {
            "type": "array",
            "maxItems": 6,
            "description": (
                "Compiler-ordered visual list. At most six. If there are five or six, list "
                "only card visuals in positions five and six; every non-card must be in the "
                "first four positions."
            ),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(visual_fields),
                "properties": visual_fields,
            },
        },
    }
    properties = {
        "artifact_kind": {"type": "string", "enum": ["ReportDesign"]},
        "schema_version": {"type": "integer", "enum": [1]},
        "projectName": {"type": "string"},
        "overview": {"type": "string"},
        "audience": {"type": "string"},
        "dataModel": {
            "type": "object",
            "additionalProperties": False,
            "required": ["factTables", "dimensionTables", "relationships"],
            "properties": {
                "factTables": _string_array(),
                "dimensionTables": _string_array(),
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": list(relationship_fields),
                        "properties": relationship_fields,
                    },
                },
            },
        },
        "measures": {
            "type": "array",
            "description": (
                "Each canonical confirmed measure exactly once, copied without changing any "
                "identity, definition, format, source field, or operand."
            ),
            "items": _measure_schema(),
        },
        "pages": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(page_fields),
                "properties": page_fields,
            },
        },
        "filters": _string_array(
            "Exact confirmed Table.Column report filters. A declared report filter satisfies "
            "its FILTER obligation without requiring a duplicate slicer. A field listed here "
            "must not also be represented by a slicer."
        ),
        "branding": {
            "type": "object",
            "additionalProperties": False,
            "required": ["themeName", "primary", "accent"],
            "properties": {
                "themeName": {"type": "string"},
                "primary": {"type": "string"},
                "accent": {"type": "string"},
            },
        },
        "accessibility": _string_array(),
        "standardsApplied": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["citation", "decision"],
                "properties": {
                    "citation": {"type": "string"},
                    "decision": {"type": "string"},
                },
            },
        },
        "assumptions": _string_array(),
        "warnings": _string_array(),
        "generationRequirements": _string_array(),
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


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
