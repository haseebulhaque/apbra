"""Bounded admin metadata reads; saved tenant profile owns every GET target."""
from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from .foundry_owner_metadata import _quiet_call
from .model_provider import FoundryBearer, FoundryCredentialProvider, ProviderProfile


def _redacted_error_details(
    error: BaseException, operation: str, *, redactions: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Original error meaning without credentials, payloads, paths or locals.

    For private owner/admin error boundaries. Known sensitive values are removed
    before structural redaction. Trace coordinates include basename/function/line
    only, never source text or locals. This does not qualify any connection.
    """
    try:
        message = str(error)
    except BaseException:
        message = "Exception message could not be rendered"
    for value in sorted((v for v in redactions if type(v) is str and v),
                        key=len, reverse=True):
        message = message.replace(value, "<redacted>")
    codes = sorted(set(re.findall(
        r"\b(?:AADSTS[0-9]{3,12}|invalid_client|invalid_grant|interaction_required|"
        r"consent_required|authorization_declined|temporarily_unavailable|"
        r"server_error|invalid_scope|unauthorized_client|access_denied)\b", message)))
    message = re.sub(r"\{.*\}|\[.*\]", "[REDACTED_PAYLOAD]", message, flags=re.S)
    message = re.sub(r"(?i)\b(?:https?|postgres(?:ql)?(?:\+\w+)?|file)://\S+",
                     "[REDACTED_URL]", message)
    message = re.sub(r"(?i)\b(authorization|bearer|token|password|secret|api[_-]?key|"
                     r"client_secret|access_token|refresh_token)\b(\s*[:=]\s*)\S+",
                     r"\1\2[REDACTED]", message)
    message = re.sub(r"(?i)\bBearer\s+\S+", "Bearer <redacted>", message)
    message = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[REDACTED_ACCOUNT]", message)
    message = re.sub(r"(?i)\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b",
                     "[REDACTED_ID]", message)
    message = re.sub(r"(['\"])[^'\"\n]*\1", "[REDACTED_VALUE]", message)
    message = re.sub(r"(?:/[A-Za-z0-9_.%+~-]+){2,}", "[REDACTED_PATH]", message)
    message = re.sub(r"\b[A-Za-z0-9_./+=:-]{20,}\b",
                     lambda match: match[0] if match[0] in {
                         "FOUNDRY_QUALIFICATION_UNAVAILABLE", "FOUNDRY_MEMORY_HANDOFF_UNAVAILABLE"
                     } else "[REDACTED_OPAQUE]", message)
    message = "".join(c if c.isprintable() or c in "\n\t" else "?" for c in message)
    result: dict[str, Any] = {
        "operation": operation,
        "exception_type": type(error).__module__ + "." + type(error).__qualname__,
        "message": message[:4096], "message_truncated": len(message) > 4096, "frames": [],
    }
    if codes:
        result["provider_error_codes"] = codes
    tb = BaseException.__getattribute__(error, "__traceback__")
    while tb is not None:
        code = tb.tb_frame.f_code
        result["frames"].append({"file": Path(code.co_filename).name,
                                 "function": code.co_name, "line": tb.tb_lineno})
        tb = tb.tb_next
    result["frames_truncated"] = len(result["frames"]) > 16
    result["frames"] = result["frames"][-16:]
    return result

@dataclass(frozen=True)
class AgentMetadataAccess:
    """Read-only metadata lease; no knowledge or report qualification claim."""

    company_id: UUID
    profile_id: str
    configuration_id: str
    credential: Callable[[], FoundryBearer] = field(repr=False)
    agent_version: str | None


class AgentMetadataCredentialProvider(Protocol):
    def ready(self, company_id: UUID, profile: ProviderProfile) -> bool: ...
    def resolve(self, company_id: UUID, profile: ProviderProfile) -> AgentMetadataAccess: ...


def _identifier(value: object) -> str | None:
    if type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,254}", value):
        return value
    return None


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key")
        result[key] = value
    return result


def agent_details(
    company_id: UUID,
    profile: ProviderProfile | None,
    credentials: FoundryCredentialProvider | AgentMetadataCredentialProvider | None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Read only configured agent metadata. No retries, discovery or paid calls."""
    result: dict[str, Any] = {
        "status": "METADATA_UNAVAILABLE", "agent": None, "configuredVersion": None,
        "observedVersion": None, "metadataSource": None,
        "modelDeployment": None, "storedInstructionUtf8Bytes": None,
        "toolTypes": [], "warnings": [],
    }
    if profile is None or profile.protocol != "FOUNDRY_AGENT_RESPONSES":
        result["warnings"] = ["AGENT_NOT_CONFIGURED"]
        return result
    parsed = urlsplit(profile.endpoint)
    suffix = "/endpoint/protocols/openai/responses"
    base = profile.endpoint[:-len(suffix)]
    agent = parsed.path[:-len(suffix)].rsplit("/", 1)[-1]
    result.update(agent=_identifier(agent), configuredVersion=profile.agent_version)
    if credentials is None:
        result["warnings"] = ["ENTRA_AUTHENTICATION_UNAVAILABLE"]
        return result
    deadline = time.monotonic() + profile.time_budget_seconds
    operation = "METADATA_CREDENTIAL_READINESS"
    private_values: list[str] = [profile.endpoint]
    try:
        if credentials.ready(company_id, profile) is not True:
            raise ValueError("Capability unavailable")
        operation = "METADATA_CREDENTIAL_RESOLVE"
        access = credentials.resolve(company_id, profile)
        operation = "METADATA_ACCESS_BINDING_VALIDATE"
        if (access.company_id != company_id or access.profile_id != profile.profile_id
                or access.configuration_id != profile.configuration_id
                or (profile.agent_version is not None
                    and access.agent_version != profile.agent_version)):
            raise ValueError("Capability binding differs")
        urls = [base + "?api-version=" + profile.api_version]
        if profile.agent_version is not None:
            urls.append(base + "/versions/" + profile.agent_version
                        + "?api-version=" + profile.api_version)
        # These one or two approved read-only metadata GETs are separate from
        # paid model dispatch slots. Time, identity and response bounds remain.

        def read(url: str) -> dict[str, Any]:
            nonlocal operation
            operation = ("AGENT_VERSION_METADATA_GET" if "/versions/" in url
                         else "AGENT_METADATA_GET")
            private_values.append(url)
            remaining = deadline - time.monotonic()
            if remaining <= 0 or credentials.ready(company_id, profile) is not True:
                raise ValueError("Expired capability")
            operation += "_TOKEN_ACQUISITION"
            bearer = _quiet_call(access.credential)
            private_values.append(bearer.token)
            operation = ("AGENT_VERSION_METADATA_GET" if "/versions/" in url
                         else "AGENT_METADATA_GET")
            if credentials.ready(company_id, profile) is not True:
                raise ValueError("Capability changed during acquisition")
            remaining = deadline - time.monotonic()
            if (remaining <= 0 or type(bearer) is not FoundryBearer
                    or type(bearer.token) is not str or not bearer.token
                    or type(bearer.audience) is not str
                    or bearer.audience != "https://ai.azure.com"
                    or type(bearer.expires_at) not in {int, float}
                    or not math.isfinite(bearer.expires_at)
                    or bearer.expires_at <= time.time() + remaining):
                raise ValueError("Expired bearer")
            raw = bytearray()
            try:
                with httpx.Client(transport=transport, trust_env=False, follow_redirects=False,
                                  timeout=min(
                                      profile.request_timeout_seconds, remaining)) as client:
                    with client.stream("GET", url, headers={
                        "Authorization": "Bearer " + bearer.token,
                        "Accept": "application/json", "Accept-Encoding": "identity",
                    }) as response:
                        if response.status_code != 200:
                            raise ValueError(f"Agent metadata HTTP status {response.status_code}")
                        if (response.headers.get("content-type", "").split(";", 1)[0]
                                != "application/json"):
                            raise ValueError("Agent metadata response content type is not JSON")
                        for chunk in response.iter_bytes():
                            if (time.monotonic() >= deadline
                                    or len(raw) + len(chunk) > profile.max_input_characters):
                                raise ValueError("Metadata bound exceeded")
                            raw.extend(chunk)
                operation += "_RESPONSE_JSON_DECODE"
                document = json.loads(raw, object_pairs_hook=_json_object)
                if bearer.expires_at <= time.time():
                    raise ValueError("Bearer expired during metadata read")
                if type(document) is not dict:
                    raise ValueError("Invalid record")
                return document
            finally:
                raw.clear()

        records = [_quiet_call(read, url) for url in urls]
        operation = "AGENT_METADATA_IDENTITY_AND_PROJECTION"
        properties = records[0]
        if properties.get("object") != "agent" or properties.get("name") != agent:
            raise ValueError("Agent identity differs")
        warnings: list[str] = []
        # Selector values never select a request target or qualify a connection.
        endpoint = properties.get("agent_endpoint")
        selector = endpoint.get("version_selector") if type(endpoint) is dict else None
        rules = selector.get("version_selection_rules") if type(selector) is dict else None
        if type(rules) is not list or not rules:
            warnings.append("ENDPOINT_SELECTOR_UNKNOWN")
        elif any(type(rule) is not dict or _identifier(rule.get("agent_version")) is None
                 for rule in rules):
            warnings.append("ENDPOINT_SELECTOR_UNKNOWN")
        version = None
        if len(records) == 2:
            version = records[1]
            if (version.get("object") != "agent.version" or version.get("name") != agent
                    or version.get("version") != profile.agent_version):
                raise ValueError("Version identity differs")
            result.update(observedVersion=profile.agent_version,
                          metadataSource="CONFIGURED_VERSION")
        else:
            warnings.append("AGENT_VERSION_NOT_CONFIGURED")
            versions = properties.get("versions")
            latest = versions.get("latest") if type(versions) is dict else None
            # Azure includes the latest definition in this same saved-agent GET.
            # Observe it only; never choose a URL, pin or invocation target from it.
            if (type(latest) is dict and latest.get("object") == "agent.version"
                    and latest.get("name") == agent):
                version = latest
                result.update(observedVersion=_identifier(latest.get("version")),
                              metadataSource="AZURE_LATEST")
            elif latest is not None:
                warnings.append("LATEST_METADATA_UNKNOWN")
        if version is not None:
            definition = version.get("definition")
            if type(definition) is dict:
                result["modelDeployment"] = _identifier(definition.get("model"))
                instructions = definition.get("instructions")
                if type(instructions) is str:
                    try:
                        result["storedInstructionUtf8Bytes"] = len(instructions.encode("utf-8"))
                    except UnicodeError:
                        pass  # Optional malformed text stays unknown, never echoed.
                tools = definition.get("tools")
                if type(tools) is list:
                    result["toolTypes"] = sorted({kind for tool in tools if type(tool) is dict
                                                  if (kind := _identifier(tool.get("type")))})
            if type(definition) is not dict or type(definition.get("tools")) is not list:
                warnings.append("TOOL_METADATA_UNKNOWN")
            elif any(type(tool) is not dict or _identifier(tool.get("type")) is None
                     for tool in definition["tools"]):
                warnings.append("TOOL_METADATA_UNKNOWN")
            if result["modelDeployment"] is None:
                warnings.append("MODEL_METADATA_UNKNOWN")
            if result["storedInstructionUtf8Bytes"] is None:
                warnings.append("INSTRUCTION_METADATA_UNKNOWN")
        if time.monotonic() >= deadline or credentials.ready(company_id, profile) is not True:
            raise ValueError("Capability changed")
        result.update(status="METADATA_OBSERVED_ONLY", warnings=warnings)
        return result
    except Exception as error:
        # Retain operation/type/redacted original message/trace, never raw responses.
        result["diagnostic"] = _redacted_error_details(
            error, operation, redactions=tuple(private_values))
        result.update(observedVersion=None, metadataSource=None,
                      modelDeployment=None, storedInstructionUtf8Bytes=None, toolTypes=[],
                      warnings=["METADATA_READ_UNAVAILABLE"])
        return result
