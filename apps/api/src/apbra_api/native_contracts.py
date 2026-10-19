"""Offline intake of original, stage-bound native objects. Never sends a request."""

import hashlib
import json
import re
from typing import Any
from uuid import UUID

from .model_provider import (
    ProviderCallError,
    ProviderContractError,
    ProviderProfile,
    ProviderRequest,
    ProviderResult,
    decode_foundry_contract,
)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_NATIVE_OBJECT_KEY")
        result[key] = value
    return result


def native_json(value: str | bytes, path: str) -> Any:
    try:
        return json.loads(value, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError, RecursionError):
        # Parser exception messages and keys can contain private model content.
        raise ProviderContractError(
            "NATIVE_OUTPUT_JSON_INVALID", path=path, reason="UNAMBIGUOUS_JSON_REQUIRED",
        ) from None


def contract_failure(error: Exception) -> dict[str, Any]:
    """Closed diagnostic vocabulary; never reflect an exception message/value."""
    codes = {
        "MODEL_RESPONSE_NOT_COMPLETED", "MODEL_OUTPUT_INVALID", "MODEL_TOOL_FAILED",
        "MODEL_TOOL_ACTION_UNSUPPORTED", "MODEL_RESPONSE_REFUSED", "MODEL_GROUNDING_INVALID",
        "MODEL_GROUNDING_UNSUPPORTED", "MODEL_GROUNDING_UNSAFE",
        "REPORT_DESIGN_GEOMETRY_UNREPRESENTABLE", "NATIVE_CONTRACT_UNRECOGNIZED",
        "NATIVE_OUTPUT_JSON_INVALID",
    }
    result: dict[str, Any] = {
        "code": error.code if isinstance(error, ProviderCallError) and error.code in codes
        else "NATIVE_CONTRACT_DECODE_FAILED",
        "phase": "NATIVE_CONTRACT", "findings": [],
    }
    if isinstance(error, ProviderContractError):
        finding = error.contract_finding
        path, reason = finding.get("path"), finding.get("reason")
        if (isinstance(path, str) and re.fullmatch(
            r"/(?:standardsApplied/[0-9]{1,7}(?:/citation)?|artifact_kind|schema_version|"
            r"output/[0-9]{1,7}/content/[0-9]{1,7}/text)?", path,
        ) and isinstance(reason, str) and reason in {
            "STANDARD_OBJECT_REQUIRED", "CITATION_STRING_REQUIRED", "CITATION_NOT_OBSERVED",
            "UNBOUND_VERIFIED_REFERENCE",
            "UNAMBIGUOUS_JSON_REQUIRED", "REPORT_DESIGN_REQUIRED", "SCHEMA_VERSION_2_REQUIRED",
        }):
            result["findings"] = [{"path": path, "reason": reason}]
    return result


class SavedNativeContract:
    """ModelProvider port backed only by an integrity-checked archived receipt.

    The structured port does not imply a structured wire request: this adapter
    performs no transport, repair, inference or retries. Existing application
    validators and explicit human confirmation retain their authority.
    """

    def __init__(
        self, raw: bytes, *, profile: ProviderProfile, task: str,
        receipt_id: UUID, metadata: dict[str, Any],
    ) -> None:
        self.profile = profile
        self.task = task
        self.receipt_id = receipt_id
        body = native_json(raw, "/")
        # Check the native JSON text itself before a general parser could
        # resolve ambiguous duplicate keys. Do not repair or wrap prose.
        output = body.get("output") if isinstance(body, dict) else None
        if not isinstance(output, list):
            raise ProviderCallError("MODEL_OUTPUT_INVALID")
        for output_index, item in enumerate(output):
            if not isinstance(item, dict):
                raise ProviderCallError("MODEL_OUTPUT_INVALID")
            if item.get("role") == "assistant":
                content = item.get("content")
                if not isinstance(content, list):
                    raise ProviderCallError("MODEL_OUTPUT_INVALID")
                for part_index, part in enumerate(content):
                    if not isinstance(part, dict):
                        raise ProviderCallError("MODEL_OUTPUT_INVALID")
                    if part.get("type") == "output_text":
                        text = part.get("text")
                        if not isinstance(text, str):
                            raise ProviderCallError("MODEL_OUTPUT_INVALID")
                        native_json(text, f"/output/{output_index}/content/{part_index}/text")
        self.value, self.grounding = decode_foundry_contract(
            body, profile=profile, knowledge_binding=metadata["knowledge_binding"],
            knowledge_scope=metadata["knowledge_scope"], agent_version=metadata["agent_version"],
            qualification=metadata["qualification"],
        )
        if task == "REQUIREMENT_ANALYSIS":
            if self.value.get("state") not in ("READY_FOR_CONFIRMATION", "NEEDS_CLARIFICATION"):
                raise ProviderCallError("NATIVE_CONTRACT_UNRECOGNIZED")
        elif task != "REPORT_DESIGN" or self.value.get("artifact_kind") != "ReportDesign":
            raise ProviderContractError(
                "NATIVE_CONTRACT_UNRECOGNIZED", path="/artifact_kind",
                reason="REPORT_DESIGN_REQUIRED",
            )
        elif type(self.value.get("schema_version")) is not int or self.value["schema_version"] != 2:
            raise ProviderContractError(
                "NATIVE_CONTRACT_UNRECOGNIZED", path="/schema_version",
                reason="SCHEMA_VERSION_2_REQUIRED",
            )
        usage = body.get("usage") if isinstance(body, dict) else None
        self.usage = {
            key: usage.get(key) if isinstance(usage, dict)
            and type(usage.get(key)) is int and usage[key] >= 0 else None
            for key in ("input_tokens", "output_tokens", "total_tokens")
        }

    def structured(self, request: ProviderRequest) -> ProviderResult:
        if request.task != self.task:
            raise ProviderCallError("NATIVE_CONTRACT_STAGE_MISMATCH")
        if request.grounding_validator is not None:
            request.grounding_validator(self.value, self.grounding)
        elif request.validator is not None:
            request.validator(self.value)
        return ProviderResult(
            value=self.value, usage=self.usage, latency_ms=None,
            # One historical native POST; the intake itself sends zero requests.
            call_count=1, profile_id=self.profile.profile_id,
            model_or_deployment=self.profile.model_or_deployment,
            prompt_version=self.profile.prompt_version,
            configuration_id=self.profile.configuration_id,
            capability_profile=self.profile.capabilities.model_dump(),
            candidate_digest=digest(self.value), grounding=self.grounding,
            source_receipt_id=str(self.receipt_id),
        )
