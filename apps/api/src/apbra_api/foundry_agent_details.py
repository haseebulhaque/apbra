"""Bounded admin metadata reads; saved tenant profile owns every GET target."""
from __future__ import annotations

import json
import math
import re
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from .foundry_owner_metadata import _quiet_call
from .model_provider import FoundryBearer, FoundryCredentialProvider, ProviderProfile


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
    credentials: FoundryCredentialProvider | None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Read only configured agent metadata. No retries, discovery or paid calls."""
    result: dict[str, Any] = {
        "status": "METADATA_UNAVAILABLE", "agent": None, "configuredVersion": None,
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
    try:
        if credentials.ready(company_id, profile) is not True:
            raise ValueError("Capability unavailable")
        access = credentials.resolve(company_id, profile)
        if (access.company_id != company_id or access.profile_id != profile.profile_id
                or access.configuration_id != profile.configuration_id
                or (profile.agent_version is not None
                    and access.agent_version != profile.agent_version)):
            raise ValueError("Capability binding differs")
        urls = [base + "?api-version=" + profile.api_version]
        if profile.agent_version is not None:
            urls.append(base + "/versions/" + profile.agent_version
                        + "?api-version=" + profile.api_version)
        if len(urls) > profile.max_calls_per_operation:
            result["warnings"] = ["METADATA_CALL_BUDGET_UNAVAILABLE"]
            return result

        def read(url: str) -> dict[str, Any]:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or credentials.ready(company_id, profile) is not True:
                raise ValueError("Expired capability")
            bearer = _quiet_call(access.credential)
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
                        if (response.status_code != 200
                                or response.headers.get("content-type", "").split(";", 1)[0]
                                != "application/json"):
                            raise ValueError("Metadata unavailable")
                        for chunk in response.iter_bytes():
                            if (time.monotonic() >= deadline
                                    or len(raw) + len(chunk) > profile.max_input_characters):
                                raise ValueError("Metadata bound exceeded")
                            raw.extend(chunk)
                document = json.loads(raw, object_pairs_hook=_json_object)
                if bearer.expires_at <= time.time():
                    raise ValueError("Bearer expired during metadata read")
                if type(document) is not dict:
                    raise ValueError("Invalid record")
                return document
            finally:
                raw.clear()

        records = [_quiet_call(read, url) for url in urls]
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
        if len(records) == 2:
            version = records[1]
            if (version.get("object") != "agent.version" or version.get("name") != agent
                    or version.get("version") != profile.agent_version):
                raise ValueError("Version identity differs")
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
        else:
            warnings.append("AGENT_VERSION_NOT_CONFIGURED")
        if time.monotonic() >= deadline or credentials.ready(company_id, profile) is not True:
            raise ValueError("Capability changed")
        result.update(status="METADATA_OBSERVED_ONLY", warnings=warnings)
        return result
    except Exception:
        # Do not expose response bodies, URLs, identities, bearer or exception text.
        result.update(modelDeployment=None, storedInstructionUtf8Bytes=None, toolTypes=[],
                      warnings=["METADATA_READ_UNAVAILABLE"])
        return result
