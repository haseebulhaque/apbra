"""Pure bounded metadata projection; no configuration, app or authentication startup."""

from __future__ import annotations

import json
import math
import re
from typing import Any, Protocol
from urllib.parse import urlparse

from .model_provider import ProviderConfigurationError


class MetadataProjectionBinding(Protocol):
    @property
    def agent_name(self) -> str: ...
    @property
    def agent_version(self) -> str: ...
    @property
    def knowledge_base(self) -> str: ...
    @property
    def max_projection_items(self) -> int: ...
    @property
    def max_projection_string_characters(self) -> int: ...


def _qualification_error() -> ProviderConfigurationError:
    return ProviderConfigurationError("FOUNDRY_QUALIFICATION_UNAVAILABLE")


def _public_identifier(value: Any, binding: MetadataProjectionBinding) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= binding.max_projection_string_characters
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*", value) is None
    ):
        raise _qualification_error()
    return value


def _instruction_bytes(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _qualification_error()
    return len(value.encode("utf-8"))


def _agent_observation(
    properties: dict[str, Any],
    version: dict[str, Any],
    binding: MetadataProjectionBinding,
) -> tuple[dict[str, Any], str]:
    if (
        properties.get("name") != binding.agent_name
        or version.get("name") != binding.agent_name
        or version.get("version") != binding.agent_version
        or properties.get("object") != "agent"
        or version.get("object") != "agent.version"
    ):
        raise _qualification_error()
    endpoint = properties.get("agent_endpoint")
    selector = endpoint.get("version_selector") if isinstance(endpoint, dict) else None
    rules = selector.get("version_selection_rules") if isinstance(selector, dict) else None
    if not isinstance(rules, list) or not 1 <= len(rules) <= binding.max_projection_items:
        raise _qualification_error()
    observed_rules: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("type") != "FixedRatio":
            raise _qualification_error()
        percentage = rule.get("traffic_percentage")
        if type(percentage) is not int or not 0 <= percentage <= 100:
            raise _qualification_error()
        observed_rules.append(
            {
                "type": "FixedRatio",
                "version": _public_identifier(rule.get("agent_version"), binding),
                "trafficPercentage": percentage,
            }
        )
    if sum(rule["trafficPercentage"] for rule in observed_rules) != 100:
        raise _qualification_error()
    definition = version.get("definition")
    if not isinstance(definition, dict) or definition.get("kind") != "prompt":
        raise _qualification_error()
    model = _public_identifier(definition.get("model"), binding)
    tools = definition.get("tools")
    if not isinstance(tools, list) or not 1 <= len(tools) <= binding.max_projection_items:
        raise _qualification_error()
    safe_tools: list[dict[str, Any]] = []
    search_origins: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            raise _qualification_error()
        kind = _public_identifier(tool.get("type"), binding)
        safe: dict[str, Any] = {"type": kind}
        if kind == "mcp":
            server = tool.get("server_url")
            if not isinstance(server, str):
                raise _qualification_error()
            parsed = urlparse(server)
            if (
                parsed.scheme != "https"
                or parsed.hostname is None
                or not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.search\.windows\.net", parsed.hostname)
                or parsed.port not in {None, 443}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.fragment
                or parsed.path
                not in {
                    f"/knowledgebases/{binding.knowledge_base}/mcp",
                    f"/knowledgebases('{binding.knowledge_base}')/mcp",
                }
                or (
                    parsed.query
                    and re.fullmatch(r"api-version=[A-Za-z0-9-]+", parsed.query) is None
                )
            ):
                raise _qualification_error()
            origin = "https://" + parsed.hostname
            search_origins.append(origin)
            safe["serverLabel"] = _public_identifier(tool.get("server_label"), binding)
            allowed = tool.get("allowed_tools")
            if isinstance(allowed, dict):
                if type(allowed.get("read_only")) is not bool:
                    raise _qualification_error()
                safe["readOnly"] = allowed["read_only"]
                allowed = allowed.get("tool_names")
            if (
                not isinstance(allowed, list)
                or not 1 <= len(allowed) <= binding.max_projection_items
                or any(value != "knowledge_base_retrieve" for value in allowed)
                or len(set(allowed)) != len(allowed)
            ):
                raise _qualification_error()
            safe["allowedTools"] = ["knowledge_base_retrieve"]
        safe_tools.append(safe)
    if len(search_origins) != 1:
        raise _qualification_error()
    return {
        "agent": binding.agent_name,
        "observedVersion": binding.agent_version,
        "modelDeployment": model,
        "storedInstructionUtf8Bytes": _instruction_bytes(definition.get("instructions")),
        "responseConfigurationUtf8Bytes": {
            key: len(
                json.dumps(definition[key], ensure_ascii=False, allow_nan=False).encode("utf-8")
            )
            if key in definition
            else None
            for key in ("response_format", "text")
        },
        "observedEndpointSelector": observed_rules,
        "tools": safe_tools,
        "searchOrigin": search_origins[0],
    }, search_origins[0]


def _knowledge_observation(
    knowledge: dict[str, Any],
    binding: MetadataProjectionBinding,
) -> dict[str, Any]:
    if knowledge.get("name") != binding.knowledge_base:
        raise _qualification_error()
    output = knowledge.get("outputMode")
    if output not in {"extractiveData", "answerSynthesis"}:
        raise _qualification_error()
    models = knowledge.get("models")
    sources = knowledge.get("knowledgeSources")
    if (
        not isinstance(models, list)
        or len(models) > binding.max_projection_items
        or not isinstance(sources, list)
        or not 1 <= len(sources) <= binding.max_projection_items
    ):
        raise _qualification_error()
    observed_models: list[dict[str, str]] = []
    for model in models:
        parameters = model.get("azureOpenAIParameters") if isinstance(model, dict) else None
        if not isinstance(parameters, dict) or model.get("kind") != "azureOpenAI":
            raise _qualification_error()
        observed_models.append(
            {
                "kind": "azureOpenAI",
                "modelName": _public_identifier(parameters.get("modelName"), binding),
                "deploymentId": _public_identifier(parameters.get("deploymentId"), binding),
            }
        )
    reasoning = knowledge.get("retrievalReasoningEffort")
    effort = reasoning.get("kind") if isinstance(reasoning, dict) else None
    if effort not in {None, "minimal", "low", "medium"}:
        raise _qualification_error()
    source_caps: list[int | None] = []
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("name"), str):
            raise _qualification_error()
        cap = source.get("maxSubQueries")
        if cap is not None and (type(cap) is not int or cap < 0):
            raise _qualification_error()
        source_caps.append(cap)
    defaults = knowledge.get("retrieveDefaults")
    safe_defaults: dict[str, int | float] | None = None
    if defaults is not None:
        if not isinstance(defaults, dict):
            raise _qualification_error()
        safe_defaults = {}
        for key in ("maxRuntimeInSeconds", "maxOutputSize", "maxOutputTokens"):
            value = defaults.get(key)
            if value is not None:
                if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
                    raise _qualification_error()
                safe_defaults[key] = value
    return {
        "knowledgeBase": binding.knowledge_base,
        "retrievalInstructionUtf8Bytes": _instruction_bytes(knowledge.get("retrievalInstructions")),
        "answerInstructionUtf8Bytes": _instruction_bytes(knowledge.get("answerInstructions")),
        "outputMode": output,
        "retrievalReasoningEffort": effort,
        "models": observed_models,
        "knowledgeSourceCount": len(sources),
        "knowledgeSourceMaxSubQueries": source_caps,
        # Absence remains unknown; observed numbers never certify a spending bound.
        "retrieveDefaults": safe_defaults,
        "numericCaps": safe_defaults or None,
        "allInCostBound": "UNKNOWN",
    }
