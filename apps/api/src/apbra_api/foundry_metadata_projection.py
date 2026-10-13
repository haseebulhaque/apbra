"""Pure bounded metadata projection; no configuration, app or authentication startup."""

from __future__ import annotations

import json
import math
import re
from typing import Any, Protocol, cast
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


_PROJECTION_REASONS = frozenset(
    {
        "UNKNOWN",
        "METADATA_SHAPE",
        "IDENTITY",
        "ENDPOINT_SHAPE",
        "SELECTOR_SHAPE",
        "SELECTOR_RULES",
        "SELECTOR_RULE_KIND",
        "SELECTOR_PERCENTAGE",
        "SELECTOR_VERSION",
        "SELECTOR_TOTAL",
        "DEFINITION_KIND",
        "MODEL_IDENTIFIER",
        "TOOLS_BINDING",
        "TOOL_TYPE",
        "MCP_LOCATION",
        "MCP_LABEL",
        "MCP_FILTER_READ_ONLY",
        "MCP_ALLOWED_TOOLS",
        "MCP_SOURCE_COUNT",
        "INSTRUCTIONS_SHAPE",
        "RESPONSE_CONFIGURATION",
        "POST_PROJECTION_GUARD",
    }
)


def _projection_reason(value: object) -> str:
    if type(value) is str and value in _PROJECTION_REASONS:
        return value
    return "UNKNOWN"


class ProjectionError(ProviderConfigurationError):
    """Local closed check label; never serialize opaque metadata or exception text."""

    def __init__(self, reason: object) -> None:
        super().__init__("FOUNDRY_QUALIFICATION_UNAVAILABLE")
        self.reason = _projection_reason(reason)


def _projection_identifier(
    value: object, binding: MetadataProjectionBinding, reason: str
) -> str:
    if type(value) is not str:
        raise ProjectionError(reason)
    try:
        return _public_identifier(value, binding)
    except ProviderConfigurationError:
        raise ProjectionError(reason) from None


def _projection_json_shape(value: object) -> bool:
    """JSON-native metadata only; never trigger opaque type/string hooks."""
    stack: list[tuple[object, bool]] = [(value, False)]
    active: set[int] = set()
    while stack:
        item, leaving = stack.pop()
        kind = type(item)
        if leaving:
            active.remove(id(item))
        elif (
            item is None or kind is str or kind is bool or kind is int or kind is float
        ):
            continue
        elif kind is dict or kind is list:
            if id(item) in active:
                return False
            active.add(id(item))
            stack.append((item, True))
            if kind is dict:
                values = cast(dict[object, object], item)
                if any(type(key) is not str for key in values):
                    return False
                stack.extend((child, False) for child in values.values())
            else:
                stack.extend((child, False) for child in cast(list[object], item))
        else:
            return False
    return True


def _owner_agent_observation(
    properties: dict[str, Any],
    version: dict[str, Any],
    binding: MetadataProjectionBinding,
) -> tuple[dict[str, Any], str]:
    if not _projection_json_shape(properties) or not _projection_json_shape(version):
        raise ProjectionError("METADATA_SHAPE")
    if (
        type(properties) is not dict
        or type(version) is not dict
        or type(properties.get("name")) is not str
        or properties.get("name") != binding.agent_name
        or type(version.get("name")) is not str
        or version.get("name") != binding.agent_name
        or type(version.get("version")) is not str
        or version.get("version") != binding.agent_version
        or type(properties.get("object")) is not str
        or properties.get("object") != "agent"
        or type(version.get("object")) is not str
        or version.get("object") != "agent.version"
    ):
        raise ProjectionError("IDENTITY")
    # Optional schema objects are unknown when omitted, never assumed latest/pinned.
    observed_rules: list[dict[str, Any]] | None = None
    if "agent_endpoint" in properties:
        endpoint = properties["agent_endpoint"]
        if type(endpoint) is not dict:
            raise ProjectionError("ENDPOINT_SHAPE")
        if "version_selector" in endpoint:
            selector = endpoint["version_selector"]
            if type(selector) is not dict:
                raise ProjectionError("SELECTOR_SHAPE")
            rules = selector.get("version_selection_rules")
            if (
                type(rules) is not list
                or not 1 <= len(rules) <= binding.max_projection_items
            ):
                raise ProjectionError("SELECTOR_RULES")
            observed_rules = []
            for rule in rules:
                if (
                    type(rule) is not dict
                    or type(rule.get("type")) is not str
                    or rule.get("type") != "FixedRatio"
                ):
                    raise ProjectionError("SELECTOR_RULE_KIND")
                percentage = rule.get("traffic_percentage")
                if type(percentage) is not int or not 0 <= percentage <= 100:
                    raise ProjectionError("SELECTOR_PERCENTAGE")
                observed_rules.append(
                    {
                        "type": "FixedRatio",
                        "version": _projection_identifier(
                            rule.get("agent_version"), binding, "SELECTOR_VERSION"
                        ),
                        "trafficPercentage": percentage,
                    }
                )
            if sum(rule["trafficPercentage"] for rule in observed_rules) != 100:
                raise ProjectionError("SELECTOR_TOTAL")
    definition = version.get("definition")
    if (
        type(definition) is not dict
        or type(definition.get("kind")) is not str
        or definition.get("kind") != "prompt"
    ):
        raise ProjectionError("DEFINITION_KIND")
    model = _projection_identifier(definition.get("model"), binding, "MODEL_IDENTIFIER")
    tools = definition.get("tools")
    if type(tools) is not list or not 1 <= len(tools) <= binding.max_projection_items:
        raise ProjectionError("TOOLS_BINDING")
    safe_tools: list[dict[str, Any]] = []
    search_origins: list[str] = []
    for tool in tools:
        if type(tool) is not dict:
            raise ProjectionError("TOOL_TYPE")
        kind = _projection_identifier(tool.get("type"), binding, "TOOL_TYPE")
        safe: dict[str, Any] = {"type": kind}
        if kind == "mcp":
            server = tool.get("server_url")
            if type(server) is not str:
                raise ProjectionError("MCP_LOCATION")
            try:
                parsed = urlparse(server)
                invalid = (
                    parsed.scheme != "https"
                    or parsed.hostname is None
                    or not re.fullmatch(
                        r"[a-z0-9][a-z0-9-]*\.search\.windows\.net", parsed.hostname
                    )
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
                        and re.fullmatch(r"api-version=[A-Za-z0-9-]+", parsed.query)
                        is None
                    )
                )
            except ValueError:
                raise ProjectionError("MCP_LOCATION") from None
            if invalid:
                raise ProjectionError("MCP_LOCATION")
            origin = "https://" + cast(str, parsed.hostname)
            search_origins.append(origin)
            safe["serverLabel"] = _projection_identifier(
                tool.get("server_label"), binding, "MCP_LABEL"
            )
            allowed = tool.get("allowed_tools")
            if type(allowed) is dict:
                if "read_only" in allowed:
                    if type(allowed["read_only"]) is not bool:
                        raise ProjectionError("MCP_FILTER_READ_ONLY")
                    safe["readOnly"] = allowed["read_only"]
                else:
                    safe["readOnly"] = None
                allowed = allowed.get("tool_names")
            if (
                type(allowed) is not list
                or not 1 <= len(allowed) <= binding.max_projection_items
                or any(
                    type(value) is not str or value != "knowledge_base_retrieve"
                    for value in allowed
                )
                or len(set(allowed)) != len(allowed)
            ):
                raise ProjectionError("MCP_ALLOWED_TOOLS")
            safe["allowedTools"] = ["knowledge_base_retrieve"]
        safe_tools.append(safe)
    if len(search_origins) != 1:
        raise ProjectionError("MCP_SOURCE_COUNT")
    instructions = definition.get("instructions")
    if instructions is not None and type(instructions) is not str:
        raise ProjectionError("INSTRUCTIONS_SHAPE")
    try:
        instruction_bytes = _instruction_bytes(instructions)
    except UnicodeError:
        raise ProjectionError("INSTRUCTIONS_SHAPE") from None
    if any(
        key in definition and not _projection_json_shape(definition[key])
        for key in ("response_format", "text")
    ):
        raise ProjectionError("RESPONSE_CONFIGURATION")
    try:
        response_bytes = {
            key: len(
                json.dumps(definition[key], ensure_ascii=False, allow_nan=False).encode(
                    "utf-8"
                )
            )
            if key in definition
            else None
            for key in ("response_format", "text")
        }
    except (ValueError, TypeError, UnicodeError):
        raise ProjectionError("RESPONSE_CONFIGURATION") from None
    return {
        "agent": binding.agent_name,
        "observedVersion": binding.agent_version,
        "modelDeployment": model,
        "storedInstructionUtf8Bytes": instruction_bytes,
        "responseConfigurationUtf8Bytes": response_bytes,
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
