"""Provider-neutral, bounded server-side structured model calls.

The browser never receives this configuration or its credential.  Callers
must still validate every returned object against APBRA's deterministic
contracts; a successful provider response is only untrusted candidate data.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

COMPILER_MAX_VISUALS_PER_PAGE = 6
COMPILER_SUPPORTED_TREND_GRAINS = ("DAY", "MONTH", "QUARTER", "YEAR")


def _validated_schema_capabilities(
    supported_trend_grains: Sequence[str],
    *,
    max_visuals_per_page: int | None = None,
) -> list[str]:
    grains = list(supported_trend_grains)
    if (
        not grains
        or len(set(grains)) != len(grains)
        or any(item not in COMPILER_SUPPORTED_TREND_GRAINS for item in grains)
        or (
            max_visuals_per_page is not None
            and not 1 <= max_visuals_per_page <= COMPILER_MAX_VISUALS_PER_PAGE
        )
    ):
        raise ValueError("provider schema capabilities exceed the active compiler")
    return grains


def _string_array(description: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if description is not None:
        value["description"] = description
    return value


def _validate_strict_wire_schema(schema: dict[str, Any]) -> None:
    """Fail before transport when a schema exceeds the qualified strict subset.

    This checks the exact provider-facing schema. APBRA's semantic validators
    still own numeric bounds, coverage and report-design correctness.
    """

    allowed = {
        "type", "description", "enum", "properties", "required", "additionalProperties", "items",
    }
    property_count = 0

    def inspect(node: object, object_depth: int) -> None:
        nonlocal property_count
        if not isinstance(node, dict) or set(node) - allowed:
            raise ProviderCallError("MODEL_SCHEMA_UNSUPPORTED")
        kind = node.get("type")
        if not isinstance(kind, str):
            raise ProviderCallError("MODEL_SCHEMA_UNSUPPORTED")
        if kind == "object":
            if object_depth > 5:
                raise ProviderCallError("MODEL_SCHEMA_UNSUPPORTED")
            properties = node.get("properties")
            required = node.get("required")
            if (
                not isinstance(properties, dict)
                or not all(isinstance(name, str) and isinstance(child, dict)
                           for name, child in properties.items())
                or not isinstance(required, list)
                or not all(isinstance(name, str) for name in required)
                or len(required) != len(properties)
                or set(required) != set(properties)
                or node.get("additionalProperties") is not False
                or "items" in node
            ):
                raise ProviderCallError("MODEL_SCHEMA_UNSUPPORTED")
            property_count += len(properties)
            if property_count > 100:
                raise ProviderCallError("MODEL_SCHEMA_UNSUPPORTED")
            for child in properties.values():
                inspect(child, object_depth + 1)
        elif kind == "array":
            if "items" not in node or any(
                key in node for key in ("properties", "required", "additionalProperties")
            ):
                raise ProviderCallError("MODEL_SCHEMA_UNSUPPORTED")
            inspect(node["items"], object_depth)
        elif kind in {"string", "integer", "number", "boolean"}:
            if any(
                key in node for key in ("properties", "required", "additionalProperties", "items")
            ):
                raise ProviderCallError("MODEL_SCHEMA_UNSUPPORTED")
        else:
            raise ProviderCallError("MODEL_SCHEMA_UNSUPPORTED")

    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ProviderCallError("MODEL_SCHEMA_UNSUPPORTED")
    inspect(schema, 1)


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


def requirement_analysis_schema(supported_trend_grains: Sequence[str]) -> dict[str, Any]:
    """Strict provider schema mirroring the canonical TypeScript contract."""

    grains = _validated_schema_capabilities(supported_trend_grains)
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
        "pageNames": _string_array("Only exact names already declared in interpretation.pages."),
        "required": {
            "type": "boolean",
            "description": "Whether confirmation requires this obligation downstream.",
        },
        "minimumRepresentations": {
            "type": "integer",
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
            "enum": ["NONE", *grains],
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
    clarification_category = {
        "type": "string",
        "enum": [
            "METRIC_DEFINITION", "TIME_COMPARISON", "SECURITY", "AUDIENCE",
            "PAGE_SCOPE", "FILTER_SCOPE", "OTHER",
        ],
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
        "requestedScope": _string_array(
            "The user's requested scope, including portions not deliverable now."
        ),
        "deliverableScope": _string_array(
            "Only the meaningful supported scope represented in typed obligations."
        ),
        "unsupportedScope": _string_array(
            "Requested features or semantics unsupported by the active target capability."
        ),
        "omittedScope": _string_array(
            "Requested portions omitted because data, meaning or permission is unavailable."
        ),
        "limitations": _string_array("Disclosed caveats and constraints of the deliverable scope."),
        "suggestedAlternatives": _string_array(
            "Alternatives offered for user consideration, not silently selected."
        ),
        "ambiguities": _string_array(),
        "clarifications": {
            "type": "array",
            "description": (
                "Legacy field: return an empty array. Material clarification questions "
                "belong only in the top-level questions array."
            ),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [],
                "properties": {},
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
        "category": clarification_category,
        "question": {"type": "string"},
        "reason": {"type": "string"},
        "required": {
            "type": "boolean",
            "enum": [False],
            "description": "Clarification is optional and never gates acceptance.",
        },
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


def report_design_schema(
    *, max_visuals_per_page: int, supported_trend_grains: Sequence[str]
) -> dict[str, Any]:
    """Strict provider schema mirroring the canonical ReportDesign contract."""

    grains = _validated_schema_capabilities(
        supported_trend_grains, max_visuals_per_page=max_visuals_per_page
    )
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
            "enum": ["NONE", *grains],
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
            "description": (
                f"Compiler-ordered visual list. The validated runtime permits at most "
                f"{max_visuals_per_page} visuals on this page. The active compiler has four "
                "non-card slots and two additional card-only slots; every visual must fit "
                "one of those physical slots without changing its business bindings."
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


@dataclass(frozen=True)
class ProviderExecutionObservation:
    """Safe observed execution metadata, never raw provider or candidate content."""

    usage: dict[str, int | None]
    latency_ms: int
    call_count: int
    profile_id: str
    model_or_deployment: str
    prompt_version: str
    configuration_id: str
    capability_profile: dict[str, bool]
    candidate_digest: str | None = None


class ProviderCallError(RuntimeError):
    """A safe provider failure which may carry observed execution provenance."""

    def __init__(
        self, code: str, *, observation: ProviderExecutionObservation | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.observation = observation


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
    validator: Callable[[dict[str, Any]], None] | None = field(default=None, repr=False)
    retry_instruction: Callable[[Exception], str] | None = field(default=None, repr=False)


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
    candidate_digest: str | None = None

    @property
    def observation(self) -> ProviderExecutionObservation:
        return ProviderExecutionObservation(
            usage=self.usage,
            latency_ms=self.latency_ms,
            call_count=self.call_count,
            profile_id=self.profile_id,
            model_or_deployment=self.model_or_deployment,
            prompt_version=self.prompt_version,
            configuration_id=self.configuration_id,
            capability_profile=self.capability_profile,
            candidate_digest=self.candidate_digest,
        )


class ModelProvider(Protocol):
    profile: ProviderProfile

    def structured(self, request: ProviderRequest) -> ProviderResult: ...


def _candidate_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


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
        _validate_strict_wire_schema(request.output_schema)
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
        started = time.monotonic()
        calls = 0
        last_code = "MODEL_PROVIDER_FAILED"
        candidate_digest: str | None = None
        usage_totals: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        usage_seen: set[str] = set()

        def observation() -> ProviderExecutionObservation:
            return ProviderExecutionObservation(
                usage={
                    name: amount if name in usage_seen else None
                    for name, amount in usage_totals.items()
                },
                latency_ms=int((time.monotonic() - started) * 1_000),
                call_count=calls,
                profile_id=self.profile.profile_id,
                model_or_deployment=self.profile.model_or_deployment,
                prompt_version=self.profile.prompt_version,
                configuration_id=self.profile.configuration_id,
                capability_profile=self.profile.capabilities.model_dump(),
                candidate_digest=candidate_digest,
            )

        try:
            body = self._request_body(request)
        except ProviderCallError as exc:
            raise ProviderCallError(exc.code, observation=observation()) from exc
        headers = {"Content-Type": "application/json"}
        params: dict[str, str] = {}
        if self.profile.protocol == "AZURE_OPENAI_CHAT_COMPATIBLE":
            headers["api-key"] = self._credential
            params["api-version"] = self.profile.api_version
        else:
            headers["Authorization"] = f"Bearer {self._credential}"
            headers["OpenAI-Version"] = self.profile.api_version
        while calls < min(self.profile.max_calls_per_operation, self.profile.retry_limit + 1):
            if time.monotonic() - started >= self.profile.time_budget_seconds:
                raise ProviderCallError("MODEL_TIME_BUDGET_EXCEEDED", observation=observation())
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
                    raise ProviderCallError("MODEL_PROVIDER_REJECTED", observation=observation())
                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
                value = json.loads(content) if isinstance(content, str) else content
                if not isinstance(value, dict):
                    raise ProviderCallError("MODEL_OUTPUT_INVALID", observation=observation())
                candidate_digest = _candidate_digest(value)
                usage = payload.get("usage") if isinstance(payload, dict) else None
                if not isinstance(usage, dict):
                    usage = {}
                for name in usage_totals:
                    amount = _integer_or_none(usage.get(name))
                    if amount is not None:
                        usage_totals[name] += amount
                        usage_seen.add(name)
                if request.validator is not None:
                    try:
                        request.validator(value)
                    except Exception as exc:
                        if calls >= min(
                            self.profile.max_calls_per_operation,
                            self.profile.retry_limit + 1,
                        ):
                            raise ProviderCallError(
                                "MODEL_CANDIDATE_REJECTED", observation=observation()
                            ) from exc
                        instruction = (
                            request.retry_instruction(exc)
                            if request.retry_instruction is not None
                            else (
                                "The prior structured candidate was rejected by deterministic "
                                "contract validation. Return one complete corrected candidate "
                                "without inventing business meaning, fields, requirements, or "
                                "evidence."
                            )
                        )
                        if not isinstance(instruction, str) or not instruction.strip():
                            raise ProviderCallError("MODEL_RETRY_INSTRUCTION_INVALID") from exc
                        assistant_content = (
                            content
                            if isinstance(content, str)
                            else json.dumps(content, sort_keys=True, separators=(",", ":"))
                        )
                        retry_messages = [
                            *body["messages"],
                            {"role": "assistant", "content": assistant_content},
                            {"role": "user", "content": instruction[:20_000]},
                        ]
                        if (
                            sum(len(str(message["content"])) for message in retry_messages)
                            > self.profile.max_input_characters
                        ):
                            raise ProviderCallError(
                                "MODEL_INPUT_BUDGET_EXCEEDED", observation=observation()
                            ) from exc
                        body["messages"] = retry_messages
                        continue
                return ProviderResult(
                    value=value,
                    usage={
                        name: amount if name in usage_seen else None
                        for name, amount in usage_totals.items()
                    },
                    latency_ms=int((time.monotonic() - started) * 1_000),
                    call_count=calls,
                    profile_id=self.profile.profile_id,
                    model_or_deployment=self.profile.model_or_deployment,
                    prompt_version=self.profile.prompt_version,
                    configuration_id=self.profile.configuration_id,
                    capability_profile=self.profile.capabilities.model_dump(),
                    candidate_digest=candidate_digest,
                )
            except ProviderCallError:
                raise
            except (httpx.TimeoutException, httpx.TransportError):
                last_code = "MODEL_PROVIDER_TIMEOUT"
                continue
            except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise ProviderCallError("MODEL_OUTPUT_INVALID", observation=observation()) from exc
        raise ProviderCallError(last_code, observation=observation())


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
        calls = 0
        candidate_digest: str | None = None
        limit = min(self.profile.max_calls_per_operation, self.profile.retry_limit + 1)

        def observation() -> ProviderExecutionObservation:
            return ProviderExecutionObservation(
                usage={
                    "prompt_tokens": 10 * calls if calls else None,
                    "completion_tokens": 20 * calls if calls else None,
                    "total_tokens": 30 * calls if calls else None,
                },
                latency_ms=calls,
                call_count=calls,
                profile_id=self.profile.profile_id,
                model_or_deployment=self.profile.model_or_deployment,
                prompt_version=self.profile.prompt_version,
                configuration_id=self.profile.configuration_id,
                capability_profile=self.profile.capabilities.model_dump(),
                candidate_digest=candidate_digest,
            )

        while calls < limit:
            if not self._responses:
                raise ProviderCallError("FAKE_PROVIDER_EXHAUSTED", observation=observation())
            calls += 1
            value = self._responses.pop(0)
            candidate_digest = _candidate_digest(value)
            if request.validator is not None:
                try:
                    request.validator(value)
                except Exception as exc:
                    if calls >= limit:
                        raise ProviderCallError(
                            "MODEL_CANDIDATE_REJECTED", observation=observation()
                        ) from exc
                    continue
            return ProviderResult(
                value=value,
                usage={
                    "prompt_tokens": 10 * calls,
                    "completion_tokens": 20 * calls,
                    "total_tokens": 30 * calls,
                },
                latency_ms=calls,
                call_count=calls,
                profile_id=self.profile.profile_id,
                model_or_deployment=self.profile.model_or_deployment,
                prompt_version=self.profile.prompt_version,
                configuration_id=self.profile.configuration_id,
                capability_profile=self.profile.capabilities.model_dump(),
                candidate_digest=candidate_digest,
            )
        raise ProviderCallError("FAKE_PROVIDER_EXHAUSTED", observation=observation())
