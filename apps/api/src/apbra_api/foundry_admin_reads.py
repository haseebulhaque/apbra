"""Read-only Foundry observations with explicit per-caller resource authority.

No production issuer is configured here. Existing metadata/report credentials do
not implement this protocol and must never be adapted by assuming a user's rights.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import httpx

from .foundry_agent_details import _json_object
from .foundry_owner_metadata import _quiet_call
from .model_provider import FoundryBearer, ProviderProfile

Operation = Literal["LIST_AGENTS", "LIST_AGENT_FILES"]


def _id(value: object) -> str | None:
    return (
        value
        if type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}", value)
        else None
    )


def _name(value: object) -> str | None:
    return (
        value
        if type(value) is str
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", value)
        else None
    )


@dataclass(frozen=True)
class ReadRequest:
    company_id: UUID
    identity_id: UUID
    membership_id: UUID
    settings_id: UUID
    profile_id: str
    configuration_id: str
    endpoint: str = field(repr=False)
    agent_version: str | None
    operation: Operation
    vector_store_id: str | None
    limit: int
    after: str | None


@dataclass(frozen=True)
class ReadAccess:
    """Trusted host-issued authority for this exact request, not a UI claim.

    LIST_AGENTS explicitly grants project-directory metadata enumeration to this
    caller. LIST_AGENT_FILES grants reading the configured agent definition AND
    this exact attached store's file/status metadata. Neither grants invocation,
    file content, ingestion, resource mutation or rights to other stores/users.
    The issuer must prove delegation/resource grants; APBRA roles are insufficient.
    """

    request: ReadRequest
    expires_at: float
    credential: Callable[[], FoundryBearer] = field(repr=False)


class AdminReadCredentials(Protocol):
    """Host-local, noninteractive issuer; no IO, sign-in, grants or token fallback.

    A production implementation needs separate qualification of actual delegated
    principal/resource rights, expiry/revocation and repeated-read constraints.
    """

    def resolve(self, request: ReadRequest) -> ReadAccess | None: ...
    def ready(self, request: ReadRequest, access: ReadAccess) -> bool: ...


def knowledge_references(definition: object) -> dict[str, Any]:
    """Configuration references only. No remote files/history/access inference."""
    if type(definition) is not dict or type(definition.get("tools")) is not list:
        return {"status": "UNKNOWN", "vector_store_ids": [], "warnings": ["TOOLS_UNKNOWN"]}
    stores: set[str] = set()
    warnings: list[str] = []
    for tool in definition["tools"]:
        if (
            type(tool) is not dict
            or type(tool.get("type")) is not str
            or re.fullmatch(r"[a-z][a-z0-9_]{0,127}", tool["type"]) is None
        ):
            warnings.append("TOOL_UNKNOWN")
        elif tool.get("type") == "file_search":
            ids = tool.get("vector_store_ids")
            if type(ids) is not list or not ids or any(_id(v) is None for v in ids):
                warnings.append("FILE_SEARCH_CONFIGURATION_UNKNOWN")
            else:
                stores.update(ids)
    return {
        "status": ("PARTIAL_CONFIGURATION_OBSERVED" if stores else "UNKNOWN")
        if warnings
        else "CONFIGURATION_OBSERVED",
        "vector_store_ids": sorted(stores),
        "warnings": sorted(set(warnings)),
        "file_history": "NOT_READ",
        "other_knowledge_tools": "NOT_ENUMERATED",
    }


def observe(
    request: ReadRequest,
    profile: ProviderProfile,
    credentials: AdminReadCredentials | None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """At most one directory GET or two attached-store GETs; never retry/follow links."""
    result: dict[str, Any] = {
        "status": "UNAVAILABLE",
        "reason": "READ_ACCESS_UNCONFIGURED",
        "items": [],
        "has_more": False,
        "next_cursor": None,
        "scope": "METADATA_READ_ONLY",
        "history": "CURRENT_SNAPSHOT_ONLY",
    }
    if credentials is None:
        return result
    raw = bytearray()
    try:
        parsed = urlsplit(profile.endpoint)
        match = re.fullmatch(
            r"/api/projects/([A-Za-z0-9_-]+)/agents/([A-Za-z0-9-]+)/endpoint/protocols/openai/responses",
            parsed.path,
        )
        if (
            profile.protocol != "FOUNDRY_AGENT_RESPONSES"
            or profile.api_version != "v1"
            or parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.port not in (None, 443)
            or match is None
            or _name(match[2]) is None
            or (
                request.profile_id,
                request.configuration_id,
                request.endpoint,
                request.agent_version,
            )
            != (
                profile.profile_id,
                profile.configuration_id,
                profile.endpoint,
                profile.agent_version,
            )
            or type(request.limit) is not int
            or request.limit not in (10, 25, 50, 100)
            or request.after is not None
            and _id(request.after) is None
            or request.operation not in ("LIST_AGENTS", "LIST_AGENT_FILES")
            or request.operation == "LIST_AGENTS"
            and request.vector_store_id is not None
            or request.operation == "LIST_AGENT_FILES"
            and _id(request.vector_store_id) is None
        ):
            raise ValueError("Request binding invalid")
        deadline = time.monotonic() + profile.time_budget_seconds
        access = _quiet_call(credentials.resolve, request)
        if access is None:
            result["reason"] = "CALLER_RESOURCE_ACCESS_REQUIRED"
            return result

        def guard() -> None:
            if (
                type(access) is not ReadAccess
                or access.request != request
                or type(access.expires_at) not in (int, float)
                or not math.isfinite(access.expires_at)
                or access.expires_at <= time.time()
                or time.monotonic() >= deadline
                or _quiet_call(credentials.ready, request, access) is not True
            ):
                raise ValueError("Read authority unavailable")

        guard()
        root = f"{parsed.scheme}://{parsed.netloc}/api/projects/{match[1]}"
        query = {"limit": str(request.limit), "order": "desc"}
        if request.after is not None:
            query["after"] = request.after

        def get(url: str) -> dict[str, Any]:
            guard()
            bearer = _quiet_call(access.credential)
            guard()
            if (
                type(bearer) is not FoundryBearer
                or type(bearer.token) is not str
                or not bearer.token
                or bearer.audience != "https://ai.azure.com"
                or type(bearer.expires_at) not in (int, float)
                or not math.isfinite(bearer.expires_at)
                or bearer.expires_at <= time.time()
            ):
                raise ValueError("Bearer unavailable")
            timeout = min(
                profile.request_timeout_seconds,
                deadline - time.monotonic(),
                access.expires_at - time.time(),
                bearer.expires_at - time.time(),
            )
            if timeout <= 0:
                raise ValueError("Read expired")
            raw.clear()
            try:
                with httpx.Client(
                    transport=transport, trust_env=False, follow_redirects=False, timeout=timeout
                ) as client:
                    with client.stream(
                        "GET",
                        url,
                        headers={
                            "Authorization": "Bearer " + bearer.token,
                            "Accept": "application/json",
                            "Accept-Encoding": "identity",
                        },
                    ) as response:
                        if response.status_code in (401, 403):
                            raise PermissionError("Provider denied metadata read")
                        if (
                            response.status_code != 200
                            or response.headers.get("content-type", "").split(";")[0]
                            != "application/json"
                        ):
                            raise ValueError("Read unavailable")
                        if (
                            response.headers.get("content-encoding", "identity").strip().lower()
                            != "identity"
                        ):
                            raise ValueError("Unexpected response compression")
                        for chunk in response.iter_bytes():
                            guard()
                            if (
                                bearer.expires_at <= time.time()
                                or len(raw) + len(chunk) > profile.max_input_characters
                            ):
                                raise ValueError("Read bound exceeded")
                            raw.extend(chunk)
                value = json.loads(
                    raw,
                    object_pairs_hook=_json_object,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")),
                )
                guard()
                if bearer.expires_at <= time.time() or type(value) is not dict:
                    raise ValueError("Invalid response")
                return value
            finally:
                raw.clear()

        if request.operation == "LIST_AGENTS":
            document = _quiet_call(
                get, root + "/agents?" + urlencode({"api-version": "v1", **query})
            )
        else:
            if profile.agent_version is None:
                result["reason"] = "EXPLICIT_AGENT_VERSION_REQUIRED"
                return result
            definition = _quiet_call(
                get,
                root
                + "/agents/"
                + match[2]
                + "/versions/"
                + profile.agent_version
                + "?api-version=v1",
            )
            if (definition.get("object"), definition.get("name"), definition.get("version")) != (
                "agent.version",
                match[2],
                profile.agent_version,
            ):
                raise ValueError("Agent identity differs")
            refs = knowledge_references(definition.get("definition"))
            if request.vector_store_id not in refs["vector_store_ids"]:
                result["reason"] = "STORE_NOT_REFERENCED_BY_CONFIGURED_AGENT_VERSION"
                return result
            document = _quiet_call(
                get,
                root
                + "/openai/v1/vector_stores/"
                + str(request.vector_store_id)
                + "/files?"
                + urlencode(query),
            )
        items = document.get("data")
        more = document.get("has_more")
        if type(items) is not list or len(items) > request.limit or type(more) is not bool:
            raise ValueError("Invalid page")
        projected = []
        seen = set()
        for item in items:
            if (
                type(item) is not dict
                or (identifier := _id(item.get("id"))) is None
                or identifier in seen
            ):
                raise ValueError("Invalid resource identity")
            seen.add(identifier)
            if request.operation == "LIST_AGENTS":
                if item.get("object") != "agent" or (name := _name(item.get("name"))) is None:
                    raise ValueError("Invalid agent record")
                projected.append(
                    {
                        "id": identifier,
                        "name": name,
                        "state": item.get("state")
                        if item.get("state") in ("enabled", "disabled")
                        else "unknown",
                        "configured": name == match[2],
                        "invocation_access": "NOT_VERIFIED",
                    }
                )
            else:
                if (
                    item.get("object") != "vector_store.file"
                    or item.get("vector_store_id") != request.vector_store_id
                ):
                    raise ValueError("Store identity differs")
                created = item.get("created_at")
                projected.append(
                    {
                        "id": identifier,
                        "vector_store_id": request.vector_store_id,
                        "status": item.get("status")
                        if item.get("status") in ("in_progress", "completed", "failed", "cancelled")
                        else "unknown",
                        "created_at": created if type(created) is int and created >= 0 else None,
                    }
                )
        cursor = document.get("last_id")
        if more and (
            not projected
            or cursor == request.after
            or cursor != projected[-1]["id"]
            or _id(cursor) is None
        ):
            raise ValueError("Invalid cursor")
        guard()
        return {
            **result,
            "status": "OBSERVED",
            "reason": None,
            "items": projected,
            "has_more": more,
            "next_cursor": cursor if more else None,
        }
    except PermissionError:
        return {**result, "status": "DENIED", "reason": "PROVIDER_ACCESS_DENIED"}
    except Exception:
        # No raw response, identity claims, credentials, URLs or error body escape.
        return {**result, "reason": "READ_UNAVAILABLE"}
    finally:
        raw.clear()
