"""Provider-neutral, bounded server-side structured model calls.

The browser never receives this configuration or its credential.  Callers
must still validate every returned object against APBRA's deterministic
contracts; a successful provider response is only untrusted candidate data.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from urllib.parse import urlparse
from uuid import UUID

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
    still own numeric bounds, typed references and executable output integrity.
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
                "Use a compiler-supported grain for a trend visual and NONE for "
                "every non-trend visual."
            ),
            "enum": ["NONE", *grains],
        },
        "measureIds": _string_array("Exact IDs declared in ReportDesign.measures."),
        "fields": _string_array(
            "Exact Table.Column bindings. A slicer uses exactly one fields entry and an "
            "empty categoryField and measureIds."
        ),
        "altText": {"type": "string"},
    }
    page_fields = {
        "id": {"type": "string"},
        "name": {
            "type": "string",
            "description": (
                "Name of a draft page chosen by the model using the full confirmed context."
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
                "Draft measures chosen by the model using the full confirmed context. "
                "Use unique IDs, supported operations, exact source fields, and valid operands."
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
            "Exact Table.Column report filters chosen by the model for this editable draft."
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
    grounding: dict[str, Any] | None = None


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
    protocol: Literal[
        "OPENAI_CHAT_COMPATIBLE", "AZURE_OPENAI_CHAT_COMPATIBLE", "FOUNDRY_AGENT_RESPONSES"
    ]
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
        if self.protocol == "FOUNDRY_AGENT_RESPONSES" and (
            self.api_version != "v1"
            or parsed.query
            or not re.fullmatch(
                r"/api/projects/[^/]+/agents/[^/]+/endpoint/protocols/openai/responses",
                parsed.path,
            )
        ):
            raise ValueError("Foundry requires an explicit stable agent Responses v1 endpoint")
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
    grounding_validator: Callable[[dict[str, Any], dict[str, Any]], None] | None = field(
        default=None, repr=False
    )


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
    grounding: dict[str, Any] | None = None

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
            grounding=self.grounding,
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
        if profile.protocol == "FOUNDRY_AGENT_RESPONSES":
            raise ProviderConfigurationError("MODEL_PROTOCOL_UNSUPPORTED")
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
                # A provider may report billable usage even when the candidate
                # body is malformed. Capture only validated counters first so
                # the failure observation does not silently lose known usage.
                usage = payload.get("usage") if isinstance(payload, dict) else None
                if not isinstance(usage, dict):
                    usage = {}
                for name in usage_totals:
                    amount = _integer_or_none(usage.get(name))
                    if amount is not None:
                        usage_totals[name] += amount
                        usage_seen.add(name)
                content = payload["choices"][0]["message"]["content"]
                value = json.loads(content) if isinstance(content, str) else content
                if not isinstance(value, dict):
                    raise ProviderCallError("MODEL_OUTPUT_INVALID", observation=observation())
                candidate_digest = _candidate_digest(value)
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
    return value if type(value) is int and value >= 0 else None


@dataclass(frozen=True)
class FoundryBearer:
    """Explicit short-lived capability supplied by an authorized host integration."""

    token: str = field(repr=False)
    expires_at: float
    audience: str = "https://ai.azure.com"


@dataclass(frozen=True)
class FoundryAccess:
    """Trusted server qualification, never populated from client/model claims.

    The host owns qualification of routing, version and knowledge isolation.
    Neither this record nor mocked tests qualify a live Foundry resource.
    """

    company_id: UUID
    profile_id: str
    configuration_id: str
    credential: Callable[[], FoundryBearer] = field(repr=False)
    knowledge_binding: str
    knowledge_scope: Literal["SHARED_STANDARDS", "TENANT_PRIVATE"]
    agent_version: str | None = None
    qualification: Literal["OFFLINE_FIXTURE", "LIVE_METADATA_VERIFIED"] = "OFFLINE_FIXTURE"


class FoundryCredentialProvider(Protocol):
    """Injected host boundary; no discovery, login, CLI or persistent credentials."""

    def ready(self, company_id: UUID, profile: ProviderProfile) -> bool: ...

    def resolve(self, company_id: UUID, profile: ProviderProfile) -> FoundryAccess: ...


class FoundryAccessToken(Protocol):
    @property
    def token(self) -> str: ...

    @property
    def expires_on(self) -> int: ...


class FoundryTokenCredential(Protocol):
    """Structural Azure TokenCredential boundary; no SDK dependency or login."""

    def get_token(self, *scopes: str) -> FoundryAccessToken: ...


class FoundryTokenCredentialProvider:
    """Bind an explicitly enabled host credential to one qualified tenant/profile.

    The host must complete separately authorized authentication and metadata
    qualification before enabling this capability. Construction, ready and
    resolve do not acquire tokens. No credential discovery, interactive login,
    SDK construction or persistent cache is provided here.
    """

    def __init__(
        self,
        *,
        company_id: UUID,
        profile: ProviderProfile,
        token_credential: FoundryTokenCredential,
        enabled: Callable[[], bool],
        knowledge_binding: str,
        knowledge_scope: Literal["SHARED_STANDARDS", "TENANT_PRIVATE"],
        agent_version: str | None,
        qualification: Literal["OFFLINE_FIXTURE", "LIVE_METADATA_VERIFIED"],
    ) -> None:
        self._company_id = company_id
        self._profile = profile.model_copy(deep=True)
        self._token_credential = token_credential
        self._enabled = enabled
        self._access = FoundryAccess(
            company_id=company_id, profile_id=profile.profile_id,
            configuration_id=profile.configuration_id,
            credential=self._bearer, knowledge_binding=knowledge_binding,
            knowledge_scope=knowledge_scope, agent_version=agent_version,
            qualification=qualification,
        )
        _validate_foundry_access(self._profile, self._access, company_id)

    def ready(self, company_id: UUID, profile: ProviderProfile) -> bool:
        try:
            if (
                company_id != self._company_id
                or profile.model_dump(mode="json") != self._profile.model_dump(mode="json")
            ):
                return False
            return self._enabled() is True
        except Exception:
            return False

    def resolve(self, company_id: UUID, profile: ProviderProfile) -> FoundryAccess:
        if not self.ready(company_id, profile):
            raise ProviderConfigurationError("FOUNDRY_RUNTIME_IDENTITY_UNAVAILABLE")
        return self._access

    def _bearer(self) -> FoundryBearer:
        if not self.ready(self._company_id, self._profile):
            raise ProviderConfigurationError("FOUNDRY_RUNTIME_IDENTITY_UNAVAILABLE")
        try:
            acquired = self._token_credential.get_token("https://ai.azure.com/.default")
            token, expiry = acquired.token, acquired.expires_on
            if (
                not isinstance(token, str) or not token
                or type(expiry) not in {int, float}
                or not math.isfinite(expiry) or expiry <= time.time()
            ):
                raise ValueError("Invalid host capability")
            return FoundryBearer(token=token, expires_at=float(expiry))
        except Exception:
            # SDK messages may contain private identity or authentication details.
            raise ProviderConfigurationError("FOUNDRY_CREDENTIAL_UNAVAILABLE") from None


def _validate_foundry_access(
    profile: ProviderProfile, access: FoundryAccess, company_id: UUID,
) -> None:
    if (
        profile.protocol != "FOUNDRY_AGENT_RESPONSES"
        or not profile.capabilities.structured_output
        or access.company_id != company_id
        or access.profile_id != profile.profile_id
        or access.configuration_id != profile.configuration_id
        or access.knowledge_scope not in {"SHARED_STANDARDS", "TENANT_PRIVATE"}
        or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", access.knowledge_binding)
        or access.qualification not in {"OFFLINE_FIXTURE", "LIVE_METADATA_VERIFIED"}
        or (access.agent_version is not None
            and not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", access.agent_version))
    ):
        raise ProviderConfigurationError("FOUNDRY_QUALIFICATION_INVALID")


class FoundryAgentResponsesProvider:
    """Invoke the configured agent, preserving its stored instructions and tools."""

    def __init__(
        self,
        profile: ProviderProfile,
        access: FoundryAccess,
        *,
        company_id: UUID,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        _validate_foundry_access(profile, access, company_id)
        if transport is None and access.qualification != "LIVE_METADATA_VERIFIED":
            raise ProviderConfigurationError("FOUNDRY_QUALIFICATION_INVALID")
        self.profile = profile
        self._access = access
        self._transport = transport

    def _body(self, request: ProviderRequest) -> dict[str, Any]:
        if request.requires_vision:
            # This bounded wire contract only supports authorized textual context.
            raise ProviderConfigurationError("VISION_UNSUPPORTED")
        _validate_strict_wire_schema(request.output_schema)
        content = json.dumps(
            {"task": request.task, "context": request.context},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        if len(content) > self.profile.max_input_characters:
            raise ProviderCallError("MODEL_INPUT_BUDGET_EXCEEDED")
        # No application system prompt, instructions, tools or model override.
        # No remote conversation reuse; retries carry only this operation's context.
        return {
            "input": [{"role": "user", "content": content}],
            "text": {"format": {
                "type": "json_schema", "name": request.task.lower(),
                "strict": True, "schema": request.output_schema,
            }},
            "max_output_tokens": self.profile.max_output_tokens,
            "stream": False,
            "store": False,
        }

    def _candidate(
        self, payload: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(payload, dict) or payload.get("status") != "completed":
            raise ProviderCallError("MODEL_RESPONSE_NOT_COMPLETED")
        if payload.get("error") is not None or payload.get("incomplete_details") is not None:
            raise ProviderCallError("MODEL_RESPONSE_NOT_COMPLETED")
        output = payload.get("output")
        if not isinstance(output, list) or not 1 <= len(output) <= 100:
            raise ProviderCallError("MODEL_OUTPUT_INVALID")
        texts: list[str] = []
        aliases: dict[str, str] = {}
        references: set[str] = set()
        tool_count = 0
        for item in output:
            if not isinstance(item, dict):
                raise ProviderCallError("MODEL_OUTPUT_INVALID")
            kind = item.get("type")
            if kind == "reasoning":
                continue
            if kind in {"mcp_call", "file_search_call", "mcp_list_tools"}:
                if item.get("status") not in {None, "completed"} or item.get("error"):
                    raise ProviderCallError("MODEL_TOOL_FAILED")
                if kind != "mcp_list_tools":
                    tool_count += 1
                # Raw arguments, tool output and document text are never retained.
                continue
            if kind != "message":
                raise ProviderCallError("MODEL_TOOL_ACTION_UNSUPPORTED")
            if item.get("role") != "assistant" or item.get("status") != "completed":
                raise ProviderCallError("MODEL_OUTPUT_INVALID")
            parts = item.get("content")
            if not isinstance(parts, list) or not 1 <= len(parts) <= 100:
                raise ProviderCallError("MODEL_OUTPUT_INVALID")
            for part in parts:
                if not isinstance(part, dict):
                    raise ProviderCallError("MODEL_OUTPUT_INVALID")
                if part.get("type") == "refusal":
                    raise ProviderCallError("MODEL_RESPONSE_REFUSED")
                text = part.get("text")
                annotations = part.get("annotations", [])
                if (
                    part.get("type") != "output_text" or not isinstance(text, str)
                    or len(text.encode()) > 2_000_000
                    or not isinstance(annotations, list) or len(annotations) > 100
                ):
                    raise ProviderCallError("MODEL_OUTPUT_INVALID")
                texts.append(text)
                for annotation in annotations:
                    if not isinstance(annotation, dict):
                        raise ProviderCallError("MODEL_GROUNDING_INVALID")
                    annotation_type = annotation.get("type")
                    if annotation_type == "file_citation":
                        source = annotation.get("file_id")
                    elif annotation_type == "url_citation":
                        source = annotation.get("url")
                    else:
                        # An attachment/file-path is not evidence of retrieved standards.
                        raise ProviderCallError("MODEL_GROUNDING_UNSUPPORTED")
                    if not isinstance(source, str) or not 1 <= len(source) <= 2_000:
                        raise ProviderCallError("MODEL_GROUNDING_INVALID")
                    if annotation_type == "url_citation":
                        parsed = urlparse(source)
                        if parsed.scheme != "https" or not parsed.hostname or parsed.username:
                            raise ProviderCallError("MODEL_GROUNDING_INVALID")
                    identity = json.dumps([
                        self._access.knowledge_binding, annotation_type, source,
                    ], separators=(",", ":"))
                    reference = "provider:" + hashlib.sha256(identity.encode()).hexdigest()
                    aliases[source] = reference
                    aliases[reference] = reference
                    references.add(reference)
        if len(texts) != 1 or len(references) > 100:
            raise ProviderCallError("MODEL_OUTPUT_INVALID")
        value = json.loads(texts[0])
        if not isinstance(value, dict):
            raise ProviderCallError("MODEL_OUTPUT_INVALID")
        standards = value.get("standardsApplied", [])
        if not isinstance(standards, list):
            raise ProviderCallError("MODEL_GROUNDING_INVALID")
        for standard in standards:
            if not isinstance(standard, dict) or standard.get("citation") not in aliases:
                raise ProviderCallError("MODEL_GROUNDING_INVALID")
            # Only reference normalization; the provider's business decision is retained.
            standard["citation"] = aliases[standard["citation"]]
        normalized = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if any(source in normalized for source in aliases if not source.startswith("provider:")):
            raise ProviderCallError("MODEL_GROUNDING_UNSAFE")
        grounding: dict[str, Any] = {
            "mode": "PROVIDER_MANAGED", "scope": self._access.knowledge_scope,
            "profileId": self.profile.profile_id,
            "configurationId": self.profile.configuration_id,
            "knowledgeBinding": self._access.knowledge_binding,
            "agentVersion": self._access.agent_version,
            "qualification": self._access.qualification,
            "references": sorted(references), "observedToolCount": tool_count,
            "retrievalEvidence": (
                "OBSERVED_TOOL_TRACE" if tool_count else
                "ANNOTATIONS_ONLY" if references else "NO_OBSERVED_RETRIEVAL"
            ),
        }
        return value, grounding

    def structured(self, request: ProviderRequest) -> ProviderResult:
        started = time.monotonic()
        calls = 0
        candidate_digest: str | None = None
        grounding: dict[str, Any] | None = None
        totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        reported_calls: dict[str, int] = {name: 0 for name in totals}

        def observation() -> ProviderExecutionObservation:
            usage: dict[str, int | None] = {}
            for name, amount in totals.items():
                complete = calls > 0 and reported_calls[name] == calls
                usage[name] = amount if complete else None
                if 0 < reported_calls[name] < calls:
                    # Preserve known billed observations without presenting a
                    # partial subtotal as the aggregate cost of this operation.
                    usage["observed_" + name] = amount
                    usage[name + "_reported_calls"] = reported_calls[name]
            return ProviderExecutionObservation(
                usage=usage,
                latency_ms=int((time.monotonic() - started) * 1_000), call_count=calls,
                profile_id=self.profile.profile_id,
                model_or_deployment=self.profile.model_or_deployment,
                prompt_version=self.profile.prompt_version,
                configuration_id=self.profile.configuration_id,
                capability_profile=self.profile.capabilities.model_dump(),
                candidate_digest=candidate_digest, grounding=grounding,
            )

        last_code = "MODEL_PROVIDER_FAILED"
        limit = min(self.profile.max_calls_per_operation, self.profile.retry_limit + 1)
        try:
            body = self._body(request)
            while calls < limit:
                remaining = self.profile.time_budget_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    raise ProviderCallError("MODEL_TIME_BUDGET_EXCEEDED")
                try:
                    bearer = self._access.credential()
                except Exception:
                    raise ProviderCallError("MODEL_CREDENTIAL_UNAVAILABLE") from None
                if (
                    not isinstance(bearer, FoundryBearer) or not bearer.token
                    or bearer.audience != "https://ai.azure.com"
                    or type(bearer.expires_at) not in {float, int}
                    or not math.isfinite(bearer.expires_at)
                    or bearer.expires_at <= time.time() + remaining
                ):
                    raise ProviderCallError("MODEL_CREDENTIAL_UNAVAILABLE")
                remaining = self.profile.time_budget_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    raise ProviderCallError("MODEL_TIME_BUDGET_EXCEEDED")
                calls += 1
                try:
                    with httpx.Client(
                        transport=self._transport, follow_redirects=False,
                        timeout=min(self.profile.request_timeout_seconds, remaining),
                    ) as client:
                        with client.stream(
                            "POST", self.profile.endpoint,
                            headers={"Authorization": f"Bearer {bearer.token}",
                                     "Content-Type": "application/json"},
                            params={"api-version": self.profile.api_version}, json=body,
                        ) as response:
                            chunks: list[bytes] = []
                            size = 0
                            for chunk in response.iter_bytes():
                                size += len(chunk)
                                if size > 4_000_000:
                                    raise ProviderCallError("MODEL_OUTPUT_BUDGET_EXCEEDED")
                                if time.monotonic() - started >= self.profile.time_budget_seconds:
                                    raise ProviderCallError("MODEL_TIME_BUDGET_EXCEEDED")
                                chunks.append(chunk)
                            try:
                                payload = json.loads(b"".join(chunks))
                            except ValueError:
                                payload = None
                    usage = payload.get("usage") if isinstance(payload, dict) else None
                    if isinstance(usage, dict):
                        for wire, name in (("input_tokens", "prompt_tokens"),
                                           ("output_tokens", "completion_tokens"),
                                           ("total_tokens", "total_tokens")):
                            amount = _integer_or_none(usage.get(wire))
                            if amount is not None:
                                totals[name] += amount
                                reported_calls[name] += 1
                    if time.monotonic() - started >= self.profile.time_budget_seconds:
                        raise ProviderCallError("MODEL_TIME_BUDGET_EXCEEDED")
                    if response.status_code in {408, 429, 500, 502, 503, 504}:
                        last_code = "MODEL_PROVIDER_TRANSIENT_FAILURE"
                        continue
                    if not 200 <= response.status_code < 300:
                        raise ProviderCallError("MODEL_PROVIDER_REJECTED")
                    output_usage = usage.get("output_tokens") if isinstance(usage, dict) else None
                    if type(output_usage) is int and output_usage > self.profile.max_output_tokens:
                        raise ProviderCallError("MODEL_OUTPUT_BUDGET_EXCEEDED")
                    value, grounding = self._candidate(payload)
                    candidate_digest = _candidate_digest(value)
                    try:
                        if request.grounding_validator is not None:
                            request.grounding_validator(value, grounding)
                        elif request.validator is not None:
                            request.validator(value)
                    except Exception as exc:
                        if calls >= limit:
                            raise ProviderCallError("MODEL_CANDIDATE_REJECTED") from exc
                        instruction = (
                            request.retry_instruction(exc) if request.retry_instruction else
                            "Return a corrected complete candidate for the supplied typed contract."
                        )
                        if not isinstance(instruction, str) or not instruction.strip():
                            raise ProviderCallError("MODEL_RETRY_INSTRUCTION_INVALID") from exc
                        body["input"] = [*body["input"],
                                         {"role": "assistant", "content": json.dumps(value)},
                                         {"role": "user", "content": instruction[:20_000]}]
                        if sum(len(item["content"]) for item in body["input"]) > (
                            self.profile.max_input_characters
                        ):
                            raise ProviderCallError("MODEL_INPUT_BUDGET_EXCEEDED") from exc
                        continue
                    observed = observation()
                    return ProviderResult(
                        value=value, usage=observed.usage, latency_ms=observed.latency_ms,
                        call_count=calls, profile_id=observed.profile_id,
                        model_or_deployment=observed.model_or_deployment,
                        prompt_version=observed.prompt_version,
                        configuration_id=observed.configuration_id,
                        capability_profile=observed.capability_profile,
                        candidate_digest=candidate_digest, grounding=grounding,
                    )
                except (httpx.TimeoutException, httpx.TransportError):
                    last_code = "MODEL_PROVIDER_TIMEOUT"
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    raise ProviderCallError("MODEL_OUTPUT_INVALID") from exc
            raise ProviderCallError(last_code)
        except ProviderCallError as exc:
            exc.observation = observation()
            raise


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
