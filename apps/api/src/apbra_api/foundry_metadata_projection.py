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
        "KNOWLEDGE_MODELS",
        "KNOWLEDGE_OUTPUT_MODE",
        "KNOWLEDGE_REASONING",
        "KNOWLEDGE_SOURCES",
        "KNOWLEDGE_SOURCE_CAP",
        "KNOWLEDGE_DEFAULTS",
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
) -> tuple[dict[str, Any], str | None]:
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
    metadata_warnings: list[str] = []
    try:
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
    except ProjectionError as error:
        # Endpoint selection is an observation, never a GET target or authority.
        # Discard partial/unsafe values; emit only the finite local reason.
        observed_rules = None
        metadata_warnings.append(_projection_reason(error.reason))
    definition = version.get("definition")
    if type(definition) is not dict or definition.get("kind") != "prompt":
        metadata_warnings.append("DEFINITION_KIND")
        definition = {}

    def optional_identifier(value: object, reason: str) -> str | None:
        try:
            return _projection_identifier(value, binding, reason)
        except ProjectionError:
            metadata_warnings.append(reason)
            return None

    model = optional_identifier(definition.get("model"), "MODEL_IDENTIFIER")
    tools = definition.get("tools")
    safe_tools: list[dict[str, Any]] | None = None
    search_origins: list[str] = []
    invalid_search_location = False
    if type(tools) is not list or len(tools) > binding.max_projection_items:
        metadata_warnings.append("TOOLS_BINDING")
    else:
        safe_tools = []
        for tool in tools:
            if type(tool) is not dict:
                metadata_warnings.append("TOOL_TYPE")
                safe_tools.append({"type": None})
                continue
            kind = optional_identifier(tool.get("type"), "TOOL_TYPE")
            safe: dict[str, Any] = {"type": kind}
            if kind == "mcp":
                # This location alone can authorize the separately confirmed
                # read. Optional labels/filters never qualify tool execution.
                origin = _owner_search_origin(tool.get("server_url"), binding)
                if origin is None:
                    invalid_search_location = True
                    metadata_warnings.append("MCP_LOCATION")
                else:
                    search_origins.append(origin)
                safe["serverLabel"] = optional_identifier(
                    tool.get("server_label"), "MCP_LABEL"
                )
                allowed = tool.get("allowed_tools")
                names = allowed
                if type(allowed) is dict:
                    read_only = allowed.get("read_only")
                    safe["readOnly"] = read_only if type(read_only) is bool else None
                    if read_only is not None and type(read_only) is not bool:
                        metadata_warnings.append("MCP_FILTER_READ_ONLY")
                    names = allowed.get("tool_names")
                if names is None:
                    safe["allowedTools"] = None
                elif (type(names) is list and len(names) <= binding.max_projection_items
                      and all(type(value) is str and value == "knowledge_base_retrieve"
                              for value in names) and len(set(names)) == len(names)):
                    safe["allowedTools"] = names[:]
                else:
                    safe["allowedTools"] = None
                    metadata_warnings.append("MCP_ALLOWED_TOOLS")
            safe_tools.append(safe)
    search_origin = (
        search_origins[0]
        if len(search_origins) == 1 and not invalid_search_location
        else None
    )
    if search_origin is None:
        metadata_warnings.append("MCP_SOURCE_COUNT")
    instructions = definition.get("instructions")
    instruction_bytes: int | None = None
    try:
        if instructions is not None and type(instructions) is not str:
            raise ValueError
        instruction_bytes = _instruction_bytes(instructions)
    except (ValueError, UnicodeError):
        metadata_warnings.append("INSTRUCTIONS_SHAPE")
    response_bytes: dict[str, int | None] = {}
    for key in ("response_format", "text"):
        response_bytes[key] = None
        if key in definition and definition[key] is not None:
            try:
                response_bytes[key] = len(json.dumps(
                    definition[key], ensure_ascii=False, allow_nan=False
                ).encode("utf-8"))
            except (ValueError, TypeError, UnicodeError):
                metadata_warnings.append("RESPONSE_CONFIGURATION")
    return {
        "agent": binding.agent_name,
        "observedVersion": binding.agent_version,
        "modelDeployment": model,
        "storedInstructionUtf8Bytes": instruction_bytes,
        "responseConfigurationUtf8Bytes": response_bytes,
        "observedEndpointSelector": observed_rules,
        **({"metadataWarnings": sorted(set(metadata_warnings))} if metadata_warnings else {}),
        "tools": safe_tools,
        "searchOrigin": search_origin,
    }, search_origin


def _owner_search_origin(value: object, binding: MetadataProjectionBinding) -> str | None:
    """Safe destination for one fixed KB read, never generic MCP execution."""
    if type(value) is not str or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        return None
    try:
        parsed = urlparse(value)
        if (parsed.scheme != "https" or parsed.hostname is None
                or not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.search\.windows\.net", parsed.hostname)
                or parsed.port not in {None, 443} or parsed.username is not None
                or parsed.password is not None or parsed.fragment
                or parsed.path not in {
                    f"/knowledgebases/{binding.knowledge_base}/mcp",
                    f"/knowledgebases('{binding.knowledge_base}')/mcp",
                }
                or (parsed.query and re.fullmatch(r"api-version=[A-Za-z0-9-]+", parsed.query)
                    is None)):
            return None
        return "https://" + parsed.hostname
    except ValueError:
        return None


def _owner_knowledge_observation(
    knowledge: dict[str, Any] | None, binding: MetadataProjectionBinding
) -> dict[str, Any]:
    """Display observations only; no retrieval/model or cost qualification."""
    result: dict[str, Any] = {
        "knowledgeBase": binding.knowledge_base,
        "retrievalInstructionUtf8Bytes": None, "answerInstructionUtf8Bytes": None,
        "outputMode": None, "retrievalReasoningEffort": None, "models": None,
        "knowledgeSourceCount": None, "knowledgeSourceMaxSubQueries": None,
        "retrieveDefaults": None, "numericCaps": None, "allInCostBound": "UNKNOWN",
    }
    warnings: list[str] = []
    if knowledge is None:
        result["knowledgeMetadataWarnings"] = ["KNOWLEDGE_NOT_OBSERVED"]
        return result
    if not _projection_json_shape(knowledge) or type(knowledge) is not dict:
        raise ProjectionError("METADATA_SHAPE")
    if type(knowledge.get("name")) is not str or knowledge.get("name") != binding.knowledge_base:
        raise ProjectionError("IDENTITY")
    for source, target in (("retrievalInstructions", "retrievalInstructionUtf8Bytes"),
                           ("answerInstructions", "answerInstructionUtf8Bytes")):
        try:
            result[target] = _instruction_bytes(knowledge.get(source))
        except (ProviderConfigurationError, UnicodeError):
            warnings.append("INSTRUCTIONS_SHAPE")
    output = knowledge.get("outputMode")
    if type(output) is str and output in {"extractiveData", "answerSynthesis"}:
        result["outputMode"] = output
    elif output is not None:
        warnings.append("KNOWLEDGE_OUTPUT_MODE")
    reasoning = knowledge.get("retrievalReasoningEffort")
    effort = reasoning.get("kind") if type(reasoning) is dict else None
    if type(effort) is str and effort in {"minimal", "low", "medium", "auto"}:
        result["retrievalReasoningEffort"] = effort
    elif reasoning is not None:
        warnings.append("KNOWLEDGE_REASONING")
    models = knowledge.get("models")
    if type(models) is list and len(models) <= binding.max_projection_items:
        observed_models: list[dict[str, str]] = []
        try:
            for model in models:
                parameters = model.get("azureOpenAIParameters") if type(model) is dict else None
                if type(parameters) is not dict or model.get("kind") != "azureOpenAI":
                    raise ProjectionError("KNOWLEDGE_MODELS")
                observed_models.append({
                    "kind": "azureOpenAI",
                    "modelName": _projection_identifier(parameters.get("modelName"), binding,
                                                        "KNOWLEDGE_MODELS"),
                    "deploymentId": _projection_identifier(parameters.get("deploymentId"), binding,
                                                           "KNOWLEDGE_MODELS"),
                })
            result["models"] = observed_models
        except ProjectionError:
            warnings.append("KNOWLEDGE_MODELS")
    elif models is not None:
        warnings.append("KNOWLEDGE_MODELS")
    sources = knowledge.get("knowledgeSources")
    if type(sources) is list and len(sources) <= binding.max_projection_items:
        caps: list[int | None] = []
        valid = True
        for source in sources:
            if type(source) is not dict:
                valid = False
                break
            cap = source.get("maxSubQueries")
            if cap is not None and (type(cap) is not int or cap < 0):
                warnings.append("KNOWLEDGE_SOURCE_CAP")
                cap = None
            caps.append(cap)
        if valid:
            result.update(knowledgeSourceCount=len(sources), knowledgeSourceMaxSubQueries=caps)
        else:
            warnings.append("KNOWLEDGE_SOURCES")
    elif sources is not None:
        warnings.append("KNOWLEDGE_SOURCES")
    defaults = knowledge.get("retrieveDefaults")
    if type(defaults) is dict:
        safe_defaults: dict[str, int | float] = {}
        for key in ("maxRuntimeInSeconds", "maxOutputSize", "maxOutputTokens"):
            value = defaults.get(key)
            if value is not None:
                try:
                    valid = type(value) in {int, float} and math.isfinite(value) and value > 0
                except OverflowError:
                    valid = False
                if valid:
                    safe_defaults[key] = value
                else:
                    warnings.append("KNOWLEDGE_DEFAULTS")
        result.update(retrieveDefaults=safe_defaults, numericCaps=safe_defaults or None)
    elif defaults is not None:
        warnings.append("KNOWLEDGE_DEFAULTS")
    if warnings:
        result["knowledgeMetadataWarnings"] = sorted(set(warnings))
    return result


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
