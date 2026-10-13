"""Offline metadata only; no credentials, SDK sign-in or paid/provider calls."""
from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Any
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from apbra_api.foundry_agent_details import agent_details
from apbra_api.model_provider import FoundryAccess, FoundryBearer, ProviderProfile

COMPANY = UUID('00000000-0000-0000-0000-000000000001')
CANARY = 'synthetic-private-canary'


def profile(**changes: Any) -> ProviderProfile:
    data = dict(profile_id='configured-agent', protocol='FOUNDRY_AGENT_RESPONSES',
        endpoint='https://provider.invalid/api/projects/project/agents/configured/endpoint/protocols/openai/responses',
        model_or_deployment='configured-agent', api_version='v1', region='configured-region',
        prompt_version='configured-prompt', configuration_id='configured',
        capabilities={'structured_output': True, 'vision': False}, max_calls_per_operation=2,
        max_input_characters=1000, max_output_tokens=128, time_budget_seconds=10,
        request_timeout_seconds=5, retry_limit=0)
    return ProviderProfile.model_validate({**data, **changes})


class Credentials:
    def __init__(self, configured: ProviderProfile) -> None:
        self.configured = configured
        self.enabled = True
        self.access = FoundryAccess(COMPANY, configured.profile_id, configured.configuration_id,
            lambda: FoundryBearer(CANARY, time.time() + 60), 'configured-knowledge',
            'TENANT_PRIVATE', agent_version=configured.agent_version)

    def ready(self, company_id: UUID, configured: ProviderProfile) -> bool:
        return self.enabled and company_id == COMPANY and configured == self.configured

    def resolve(self, company_id: UUID, configured: ProviderProfile) -> FoundryAccess:
        assert self.ready(company_id, configured)
        return self.access


def records() -> list[dict[str, Any]]:
    return [{'object': 'agent', 'name': 'configured', 'agent_endpoint': {
        'version_selector': {'version_selection_rules': [{'agent_version': CANARY + '\n'}]}}},
        {'object': 'agent.version', 'name': 'configured', 'version': 'configured-version',
         'definition': {'model': 'configured-model', 'instructions': CANARY,
            'tools': [{'type': 'mcp', 'server_url': 'https://' + CANARY + '.invalid'}]}}]


def test_saved_profile_owns_targets_and_optional_selector_never_reroutes(capsys: Any) -> None:
    configured = profile(agent_version='configured-version')
    seen: list[str] = []
    responses = records()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert request.method == 'GET' and request.headers['authorization'] == 'Bearer ' + CANARY
        return httpx.Response(200, json=responses[len(seen) - 1])

    result = agent_details(COMPANY, configured, Credentials(configured),
                           transport=httpx.MockTransport(handler))
    assert seen == ['https://provider.invalid/api/projects/project/agents/configured?api-version=v1',
        'https://provider.invalid/api/projects/project/agents/configured/versions/configured-version?api-version=v1']
    assert result['status'] == 'METADATA_OBSERVED_ONLY'
    assert result['modelDeployment'] == 'configured-model'
    assert result['storedInstructionUtf8Bytes'] == len(CANARY)
    assert result['warnings'] == ['ENDPOINT_SELECTOR_UNKNOWN']
    assert CANARY not in json.dumps(result)
    assert capsys.readouterr().out == ''


def test_missing_version_is_unknown_and_never_fetches_historical_or_latest() -> None:
    configured = profile()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=records()[0])

    result = agent_details(COMPANY, configured, Credentials(configured),
                           transport=httpx.MockTransport(handler))
    assert len(seen) == 1 and '/versions/' not in seen[0]
    assert result['configuredVersion'] is None and result['modelDeployment'] is None
    assert 'AGENT_VERSION_NOT_CONFIGURED' in result['warnings']
    assert 'agent_version' not in configured.model_dump(mode='json')
    assert ProviderProfile.model_validate_json(configured.model_dump_json()) == configured


@pytest.mark.parametrize('mutation', ['identity', 'version', 'redirect', 'oversize',
    'malformed', 'private-error', 'capability-change', 'foreign-access', 'calls'])
def test_security_transport_and_tenant_bounds_fail_without_raw_output(mutation: str) -> None:
    configured = profile(agent_version='configured-version',
                         **({'max_calls_per_operation': 1} if mutation == 'calls' else {}))
    credential = Credentials(configured)
    responses = records()
    seen: list[str] = []
    if mutation == 'foreign-access':
        credential.access = replace(credential.access,
            company_id=UUID('00000000-0000-0000-0000-000000000002'))
    if mutation == 'identity':
        responses[0]['name'] = CANARY
    if mutation == 'version':
        responses[1]['version'] = CANARY

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if mutation == 'redirect':
            return httpx.Response(302, headers={'location': 'https://' + CANARY + '.invalid'})
        if mutation == 'oversize':
            return httpx.Response(200, content=b'x' * 1001,
                                  headers={'content-type': 'application/json'})
        if mutation == 'malformed':
            return httpx.Response(200, content=b'{', headers={'content-type': 'application/json'})
        if mutation == 'private-error':
            raise RuntimeError(CANARY)
        if mutation == 'capability-change':
            credential.enabled = False
        return httpx.Response(200, json=responses[min(len(seen)-1, 1)])

    result = agent_details(COMPANY, configured, credential, transport=httpx.MockTransport(handler))
    assert result['status'] == 'METADATA_UNAVAILABLE'
    assert CANARY not in json.dumps(result)
    assert len(seen) <= 2
    if mutation in {'foreign-access', 'calls'}:
        assert seen == []


def test_version_cannot_be_attached_to_model_api_profile() -> None:
    with pytest.raises(ValidationError):
        profile(protocol='OPENAI_CHAT_COMPATIBLE', agent_version='configured-version')


@pytest.mark.parametrize("definition", [None, {}, {"model": True, "instructions": 7},
    {"model": "unknown model format", "instructions": "\ud800", "tools": {"raw": CANARY}}])
def test_optional_definition_metadata_stays_unknown_without_rejecting(definition: Any) -> None:
    configured = profile(agent_version="configured-version")
    response_records = records()
    response_records[1]["definition"] = definition
    index = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal index
        body = json.dumps(response_records[index]).encode()
        index += 1
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    result = agent_details(COMPANY, configured, Credentials(configured),
                           transport=httpx.MockTransport(handler))
    assert result["status"] == "METADATA_OBSERVED_ONLY"
    assert result["modelDeployment"] is None and result["storedInstructionUtf8Bytes"] is None
    assert CANARY not in json.dumps(result)


@pytest.mark.parametrize("version", [".", ".."])
def test_configured_version_cannot_be_a_dot_segment(version: str) -> None:
    with pytest.raises(ValidationError):
        profile(agent_version=version)


@pytest.mark.parametrize("audience,lifetime", [("https://search.azure.com", 60),
    ("https://ai.azure.com", 1)])
def test_wrong_audience_or_insufficient_token_lifetime_stops_before_get(
    audience: str, lifetime: int,
) -> None:
    configured = profile(agent_version="configured-version")
    credential = Credentials(configured)
    credential.access = replace(credential.access,
        credential=lambda: FoundryBearer(CANARY, time.time() + lifetime, audience=audience))

    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("Unqualified bearer must never reach HTTP")

    result = agent_details(COMPANY, configured, credential,
                           transport=httpx.MockTransport(forbidden))
    assert result["status"] == "METADATA_UNAVAILABLE"
    assert CANARY not in json.dumps(result)


@pytest.mark.parametrize("changed", ["deadline", "capability"])
def test_credential_acquisition_cannot_outlive_metadata_authority(
    monkeypatch: pytest.MonkeyPatch, changed: str,
) -> None:
    import apbra_api.foundry_agent_details as module

    configured = profile(agent_version="configured-version")
    credential = Credentials(configured)
    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])

    def acquire() -> FoundryBearer:
        if changed == "deadline":
            clock[0] = 11.0
        else:
            credential.enabled = False
        return FoundryBearer(CANARY, time.time() + 60)

    credential.access = replace(credential.access, credential=acquire)

    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("Expired authority must never reach HTTP")

    result = agent_details(COMPANY, configured, credential,
                           transport=httpx.MockTransport(forbidden))
    assert result["status"] == "METADATA_UNAVAILABLE"


@pytest.mark.parametrize("tools", [None, "unknown", 42, {}, [None], [{}],
                                 [{"type": CANARY + "\n"}]])
def test_unknown_tool_metadata_warns_and_uses_only_saved_settings(tools: Any) -> None:
    configured=profile(agent_version="configured-version")
    responses=records()
    responses[1]["definition"]["tools"]=tools
    seen: list[str]=[]
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200,json=responses[len(seen)-1])
    result=agent_details(COMPANY,configured,Credentials(configured),
                         transport=httpx.MockTransport(handler))
    assert result["status"] == "METADATA_OBSERVED_ONLY"
    assert result["toolTypes"] == []
    assert "TOOL_METADATA_UNKNOWN" in result["warnings"]
    assert CANARY not in json.dumps(result)
    assert len(seen)==2
