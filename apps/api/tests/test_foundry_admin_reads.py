"""Synthetic HTTP transports only. No SDK, provider sign-in or real requests."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Any
from uuid import uuid4

import httpx
import pytest

from apbra_api.foundry_admin_reads import ReadAccess, ReadRequest, knowledge_references, observe
from apbra_api.model_provider import FoundryBearer, ProviderProfile

CANARY = "synthetic-private-canary"


def profile() -> ProviderProfile:
    return ProviderProfile.model_validate(
        dict(
            profile_id="agent",
            protocol="FOUNDRY_AGENT_RESPONSES",
            endpoint="https://provider.invalid/api/projects/project/agents/configured/endpoint/protocols/openai/responses",
            agent_version="version1",
            model_or_deployment="not-an-agent",
            api_version="v1",
            region="test",
            prompt_version="test",
            configuration_id="cfg",
            capabilities={"structured_output": True, "vision": False},
            max_calls_per_operation=1,
            max_input_characters=2000,
            max_output_tokens=128,
            time_budget_seconds=5,
            request_timeout_seconds=2,
            retry_limit=0,
        )
    )


def request(**changes: Any) -> ReadRequest:
    p = profile()
    return replace(
        ReadRequest(
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
            p.profile_id,
            p.configuration_id,
            p.endpoint,
            p.agent_version,
            "LIST_AGENTS",
            None,
            10,
            None,
        ),
        **changes,
    )


class Credentials:
    def __init__(self, r: ReadRequest) -> None:
        self.active = True
        self.tokens = 0
        self.access = ReadAccess(r, time.time() + 30, self.bearer)

    def bearer(self) -> FoundryBearer:
        self.tokens += 1
        return FoundryBearer(CANARY, time.time() + 30)

    def resolve(self, r: ReadRequest) -> ReadAccess:
        return self.access

    def ready(self, r: ReadRequest, a: ReadAccess) -> bool:
        return self.active and r == self.access.request and a == self.access


def agent_page(**changes: Any) -> dict[str, Any]:
    return {
        "data": [
            {
                "object": "agent",
                "id": "agent1",
                "name": "configured",
                "state": "enabled",
                "instructions": CANARY,
                "metadata": {"secret": CANARY},
            }
        ],
        "has_more": False,
        **changes,
    }


def run(
    r: ReadRequest, cred: Credentials | None, documents: list[Any], status: int = 200
) -> tuple[dict[str, Any], list[str]]:
    seen = []

    def http(req: httpx.Request) -> httpx.Response:
        assert req.method == "GET" and req.headers["authorization"] == "Bearer " + CANARY
        seen.append(str(req.url))
        return httpx.Response(status, json=documents[min(len(seen) - 1, len(documents) - 1)])

    return observe(r, profile(), cred, transport=httpx.MockTransport(http)), seen


def test_default_is_unconfigured_and_never_reuses_legacy_credentials() -> None:
    result, seen = run(request(), None, [agent_page()])
    assert result["reason"] == "READ_ACCESS_UNCONFIGURED" and result["items"] == [] and not seen


def test_project_directory_projects_only_safe_metadata_and_does_not_invoke() -> None:
    r = request()
    c = Credentials(r)
    result, seen = run(r, c, [agent_page()])
    assert seen == [
        "https://provider.invalid/api/projects/project/agents?api-version=v1&limit=10&order=desc"
    ]
    assert result["status"] == "OBSERVED" and result["items"] == [
        {
            "id": "agent1",
            "name": "configured",
            "state": "enabled",
            "configured": True,
            "invocation_access": "NOT_VERIFIED",
        }
    ]
    assert CANARY not in json.dumps(result) and c.tokens == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("company_id", uuid4()),
        ("identity_id", uuid4()),
        ("membership_id", uuid4()),
        ("settings_id", uuid4()),
        ("configuration_id", "foreign"),
        ("profile_id", "foreign"),
        ("endpoint", "https://foreign.invalid"),
        ("agent_version", "version2"),
        ("operation", "LIST_AGENT_FILES"),
        ("limit", 25),
        ("after", "other"),
    ],
)
def test_exact_caller_settings_operation_and_resource_binding_precedes_token(
    field: str, value: Any
) -> None:
    r = request()
    c = Credentials(r)
    c.access = replace(c.access, request=replace(r, **{field: value}))
    result, seen = run(r, c, [agent_page()])
    assert result["status"] == "UNAVAILABLE" and not seen and c.tokens == 0


@pytest.mark.parametrize("expiry", [0, float("nan"), float("inf"), True])
def test_expired_or_malformed_lease_never_acquires_token(expiry: float) -> None:
    r = request()
    c = Credentials(r)
    c.access = replace(c.access, expires_at=expiry)
    result, seen = run(r, c, [agent_page()])
    assert result["status"] == "UNAVAILABLE" and not seen and c.tokens == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"limit": 11},
        {"after": "../secret"},
        {"vector_store_id": "vs1"},
        {"operation": "DELETE"},
        {"after": "x?redirect=foreign"},
    ],
)
def test_bad_selectors_never_acquire_token(changes: dict[str, Any]) -> None:
    r = request(**changes)
    c = Credentials(r)
    result, seen = run(r, c, [agent_page()])
    assert result["status"] == "UNAVAILABLE" and not seen and c.tokens == 0


@pytest.mark.parametrize("status", [301, 302, 307, 308, 429, 500])
def test_no_redirect_retry_or_error_payload_disclosure(status: int) -> None:
    r = request()
    result, seen = run(r, Credentials(r), [{"error": CANARY}], status)
    assert result["status"] == "UNAVAILABLE" and len(seen) == 1 and CANARY not in json.dumps(result)


@pytest.mark.parametrize("status", [401, 403])
def test_denied_is_not_empty_or_unconfigured(status: int) -> None:
    r = request()
    result, seen = run(r, Credentials(r), [{"error": CANARY}], status)
    assert result["status"] == "DENIED" and result["items"] == [] and len(seen) == 1


@pytest.mark.parametrize(
    "document", [{"data": [], "has_more": False}, agent_page(has_more=True, last_id="agent1")]
)
def test_empty_and_incomplete_cursor_page_are_truthful(document: dict[str, Any]) -> None:
    r = request()
    result, _ = run(r, Credentials(r), [document])
    assert result["status"] == "OBSERVED"
    assert result["has_more"] == document["has_more"] and result["next_cursor"] == (
        "agent1" if document["has_more"] else None
    )


@pytest.mark.parametrize(
    "document",
    [
        agent_page(has_more=True, last_id="foreign"),
        agent_page(has_more="true"),
        agent_page(data=[{"object": "agent", "id": "agent1", "name": "../../foreign"}]),
        agent_page(data=[{"id": "x"}]),
        agent_page(data=[], has_more=True, last_id="x"),
    ],
)
def test_malformed_provider_pages_do_not_become_success(document: dict[str, Any]) -> None:
    r = request()
    result, _ = run(r, Credentials(r), [document])
    assert result["status"] == "UNAVAILABLE"


def version() -> dict[str, Any]:
    return {
        "object": "agent.version",
        "name": "configured",
        "version": "version1",
        "definition": {
            "instructions": CANARY,
            "tools": [{"type": "file_search", "vector_store_ids": ["vs1"]}],
        },
    }


def test_files_require_separate_explicit_store_authority_and_attached_version() -> None:
    r = request(operation="LIST_AGENT_FILES", vector_store_id="vs1")
    c = Credentials(r)
    files = {
        "data": [
            {
                "object": "vector_store.file",
                "id": "file-1",
                "vector_store_id": "vs1",
                "status": "completed",
                "created_at": 123,
                "last_error": {"message": CANARY},
                "content": CANARY,
            }
        ],
        "has_more": False,
    }
    result, seen = run(r, c, [version(), files])
    assert result["status"] == "OBSERVED" and len(seen) == 2
    assert (
        seen[1]
        == "https://provider.invalid/api/projects/project/openai/v1/vector_stores/vs1/files?limit=10&order=desc"
    )
    assert CANARY not in json.dumps(result) and result["history"] == "CURRENT_SNAPSHOT_ONLY"
    assert result["items"][0]["created_at"] == 123


def test_reference_is_not_itself_permission_and_unattached_store_is_never_read() -> None:
    r = request(operation="LIST_AGENT_FILES", vector_store_id="foreign")
    result, seen = run(r, Credentials(r), [version()])
    assert result["reason"] == "STORE_NOT_REFERENCED_BY_CONFIGURED_AGENT_VERSION" and len(seen) == 1
    r = request(operation="LIST_AGENT_FILES", vector_store_id="vs1")
    c = Credentials(r)
    c.access = replace(c.access, request=replace(r, vector_store_id="other"))
    result, seen = run(r, c, [version()])
    assert not seen and c.tokens == 0


def test_revocation_after_response_prevents_disclosure_and_no_store_fetch() -> None:
    r = request(operation="LIST_AGENT_FILES", vector_store_id="vs1")
    c = Credentials(r)
    seen = []

    def http(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        c.active = False
        return httpx.Response(200, json=version())

    result = observe(r, profile(), c, transport=httpx.MockTransport(http))
    assert result["status"] == "UNAVAILABLE" and result["items"] == [] and len(seen) == 1


def test_oversized_and_duplicate_key_response_fail_closed() -> None:
    r = request()
    c = Credentials(r)
    for raw in [b'{"data":[],"has_more":false,"has_more":true}', b" " * 2001]:
        result = observe(
            r,
            profile(),
            c,
            transport=httpx.MockTransport(
                lambda req, raw=raw: httpx.Response(
                    200, content=raw, headers={"content-type": "application/json"}
                )
            ),
        )
        assert result["status"] == "UNAVAILABLE"


def test_unknown_knowledge_optional_configuration_never_fabricates_files() -> None:
    assert knowledge_references(None)["status"] == "UNKNOWN"
    refs = knowledge_references(
        {
            "tools": [
                {"type": "file_search", "vector_store_ids": ["vs1"]},
                {"type": "mcp", "server_url": CANARY},
            ]
        }
    )
    assert (
        refs["vector_store_ids"] == ["vs1"]
        and refs["file_history"] == "NOT_READ"
        and CANARY not in json.dumps(refs)
    )
    refs = knowledge_references(
        {"tools": [{"type": "file_search", "vector_store_ids": ["../foreign"]}]}
    )
    assert refs["vector_store_ids"] == [] and refs["warnings"] == [
        "FILE_SEARCH_CONFIGURATION_UNKNOWN"
    ]


@pytest.mark.parametrize("path", ["/agents", "/agent-files?vector_store_id=vs1"])
def test_api_requires_admin_expected_membership_and_settings_before_io(
    client: Any, monkeypatch: Any, path: str
) -> None:
    from conftest import sign_in

    import apbra_api.api as api_module

    owner = sign_in(client, "owner")
    saved = client.get("/api/tenant-settings").json()

    def forbidden(*args: Any) -> Any:
        pytest.fail("Unauthorized or unconfigured callers must not reach provider IO")

    monkeypatch.setattr(api_module, "observe", forbidden)
    url = "/api/tenant-settings" + path
    assert client.get(url).status_code == 503
    headers = {
        "X-Expected-Membership-Id": owner["actor"]["membership_id"],
        "X-Expected-Settings-Id": saved["id"],
    }
    result = client.get(url, headers=headers)
    assert result.status_code == 200 and result.json()["reason"] == "AGENT_NOT_CONFIGURED"
    assert result.headers["cache-control"] == "no-store"
    sign_in(client, "member")
    assert client.get(url, headers=headers).status_code == 403


@pytest.mark.parametrize(
    "query",
    [
        "?endpoint=https://foreign.invalid",
        "?limit=9",
        "?limit=10&limit=25",
        "?after=../secret",
        "?after=",
        "?vector_store_id=foreign",
    ],
)
def test_api_rejects_unsupported_query_before_io(client: Any, monkeypatch: Any, query: str) -> None:
    from conftest import sign_in

    import apbra_api.api as api_module

    owner = sign_in(client, "owner")
    saved = client.get("/api/tenant-settings").json()
    headers = {
        "X-Expected-Membership-Id": owner["actor"]["membership_id"],
        "X-Expected-Settings-Id": saved["id"],
    }
    monkeypatch.setattr(api_module, "observe", lambda *args: pytest.fail("No provider IO"))
    assert client.get("/api/tenant-settings/agents" + query, headers=headers).status_code == 422


def test_api_binds_real_actor_and_suppresses_read_after_revoked_membership(
    client: Any, database: Any, monkeypatch: Any
) -> None:
    from uuid import UUID

    from conftest import sign_in

    import apbra_api.api as api_module
    from apbra_api.persistence import MembershipRow

    owner = sign_in(client, "owner")
    saved = client.get("/api/tenant-settings").json()
    real = api_module.admin_settings

    def configured(db: Any, actor: Any) -> Any:
        snap = real(db, actor)
        return replace(
            snap, settings=snap.settings.model_copy(update={"provider_profile": profile()})
        )

    monkeypatch.setattr(api_module, "admin_settings", configured)
    calls = []

    def revoke(bound: ReadRequest, p: ProviderProfile, creds: Any) -> dict[str, Any]:
        calls.append(bound)
        assert str(bound.company_id) == owner["actor"]["company_id"]
        assert str(bound.identity_id) == owner["actor"]["identity_id"]
        assert str(bound.membership_id) == owner["actor"]["membership_id"]
        assert str(bound.settings_id) == saved["id"] and p == profile() and creds is None
        with database.session() as db:
            row = db.get(MembershipRow, UUID(owner["actor"]["membership_id"]))
            row.role = "MEMBER"
            db.commit()
        return {"status": "OBSERVED", "items": [{"id": "private-resource"}]}

    monkeypatch.setattr(api_module, "observe", revoke)
    headers = {
        "X-Expected-Membership-Id": owner["actor"]["membership_id"],
        "X-Expected-Settings-Id": saved["id"],
    }
    response = client.get("/api/tenant-settings/agents", headers=headers)
    assert (
        response.status_code == 403 and "private-resource" not in response.text and len(calls) == 1
    )


def test_credential_acquisition_revocation_stops_before_http_and_output_is_quiet(
    capsys: Any,
) -> None:
    import sys

    r = request()
    c = Credentials(r)

    def noisy_bearer() -> FoundryBearer:
        print(CANARY)
        print(CANARY, file=sys.stderr)
        c.active = False
        return FoundryBearer(CANARY, time.time() + 30)

    c.access = replace(c.access, credential=noisy_bearer)
    result, seen = run(r, c, [agent_page()])
    assert result["status"] == "UNAVAILABLE" and not seen and CANARY not in json.dumps(result)
    captured = capsys.readouterr()
    assert CANARY not in captured.out + captured.err


def test_repeated_cursor_is_not_followed_or_presented_as_a_complete_page() -> None:
    r = request(after="agent1")
    result, seen = run(r, Credentials(r), [agent_page(has_more=True, last_id="agent1")])
    assert result["status"] == "UNAVAILABLE" and len(seen) == 1


def test_legacy_metadata_lease_is_not_an_admin_read_capability() -> None:
    from apbra_api.foundry_agent_details import AgentMetadataAccess

    r = request()
    c = Credentials(r)
    c.access = AgentMetadataAccess(
        r.company_id, r.profile_id, r.configuration_id, c.bearer, r.agent_version
    )  # type: ignore[assignment]
    result, seen = run(r, c, [agent_page()])
    assert result["status"] == "UNAVAILABLE" and c.tokens == 0 and not seen


def test_malformed_and_mixed_knowledge_references_are_not_observed_empty_sources() -> None:
    unknown = knowledge_references(
        {"tools": [{"type": "file_search", "vector_store_ids": ["../foreign"]}]}
    )
    assert unknown["status"] == "UNKNOWN" and unknown["vector_store_ids"] == []
    partial = knowledge_references(
        {"tools": [{"type": "file_search", "vector_store_ids": ["vs1"]}, {"type": "file_search"}]}
    )
    assert partial["status"] == "PARTIAL_CONFIGURATION_OBSERVED" and partial[
        "vector_store_ids"
    ] == ["vs1"]
    assert partial["warnings"] == ["FILE_SEARCH_CONFIGURATION_UNKNOWN"]


@pytest.mark.parametrize(
    "tool", [{}, {"type": 123}, {"type": None}, {"type": ""}, {"type": "../invalid"}]
)
def test_missing_or_invalid_tool_type_is_unknown_not_observed_empty(tool: Any) -> None:
    result = knowledge_references({"tools": [tool]})
    assert result["status"] == "UNKNOWN" and result["vector_store_ids"] == []
    assert result["warnings"] == ["TOOL_UNKNOWN"]


@pytest.mark.parametrize("encoding", ["gzip", "br", "deflate", "custom", "gzip, br"])
def test_unexpected_compression_is_rejected_before_decoding_or_consuming_body(
    encoding: str,
) -> None:
    class MustNotConsume(httpx.SyncByteStream):
        def __iter__(self) -> Any:
            pytest.fail("Unexpected compressed response body must not be consumed")

    r = request()
    c = Credentials(r)

    def http(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "content-encoding": encoding},
            stream=MustNotConsume(),
        )

    result = observe(r, profile(), c, transport=httpx.MockTransport(http))
    assert result["status"] == "UNAVAILABLE" and result["items"] == []


@pytest.mark.parametrize("encoding", ["identity", " IDENTITY "])
def test_identity_encoding_can_be_read_with_existing_body_bounds(encoding: str) -> None:
    r = request()
    c = Credentials(r)
    body = json.dumps(agent_page()).encode()

    def http(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "content-encoding": encoding},
            stream=httpx.ByteStream(body),
        )

    result = observe(r, profile(), c, transport=httpx.MockTransport(http))
    assert result["status"] == "OBSERVED" and len(result["items"]) == 1
