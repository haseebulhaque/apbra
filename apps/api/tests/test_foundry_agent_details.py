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
    'malformed', 'private-error', 'capability-change', 'foreign-access'])
def test_security_transport_and_tenant_bounds_fail_without_raw_output(mutation: str) -> None:
    configured = profile(agent_version='configured-version')
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
    if mutation in {'foreign-access'}:
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


def test_distinct_metadata_access_has_no_report_qualification_and_uses_saved_targets() -> None:
    from apbra_api.foundry_agent_details import AgentMetadataAccess

    configured = profile(agent_version='configured-version')
    credential = Credentials(configured)
    credential.access = AgentMetadataAccess(  # type: ignore[assignment]
        COMPANY, configured.profile_id, configured.configuration_id,
        lambda: FoundryBearer(CANARY, time.time()+60), configured.agent_version)
    seen: list[str] = []
    values = records()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == 'GET'
        seen.append(str(request.url))
        return httpx.Response(200, json=values[len(seen)-1])

    result = agent_details(COMPANY, configured, credential, transport=httpx.MockTransport(handler))
    assert result['status'] == 'METADATA_OBSERVED_ONLY' and len(seen) == 2
    assert not hasattr(credential.access, 'knowledge_binding')
    assert not hasattr(credential.access, 'qualification')
    assert CANARY not in repr(credential.access)



def test_one_paid_dispatch_limit_does_not_reject_two_approved_metadata_gets():
    configured=profile(agent_version='configured-version',max_calls_per_operation=1)
    seen=[]
    values=records()
    def handler(request):
        seen.append(request)
        assert request.method=='GET'
        return httpx.Response(200,json=values[len(seen)-1])
    result=agent_details(COMPANY,configured,Credentials(configured),
        transport=httpx.MockTransport(handler))
    assert len(seen)==2
    assert result['status']=='METADATA_OBSERVED_ONLY'
    assert configured.max_calls_per_operation==1 and configured.retry_limit==0


def test_unpinned_agent_observes_inline_latest_without_any_new_get_or_routing_change() -> None:
    configured = profile()
    original = configured.model_dump_json()
    body = records()[0]
    body['versions'] = {'latest': records()[1]}
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=body)

    result = agent_details(COMPANY, configured, Credentials(configured),
                           transport=httpx.MockTransport(handler))
    assert [(r.method, str(r.url)) for r in seen] == [('GET',
        'https://provider.invalid/api/projects/project/agents/configured?api-version=v1')]
    assert result['status'] == 'METADATA_OBSERVED_ONLY'
    assert result['configuredVersion'] is None
    assert result['observedVersion'] == 'configured-version'
    assert result['metadataSource'] == 'AZURE_LATEST'
    assert result['modelDeployment'] == 'configured-model'
    assert result['storedInstructionUtf8Bytes'] == len(CANARY)
    assert result['toolTypes'] == ['mcp']
    assert result['warnings'] == ['ENDPOINT_SELECTOR_UNKNOWN', 'AGENT_VERSION_NOT_CONFIGURED']
    assert CANARY not in json.dumps(result)
    assert configured.model_dump_json() == original


@pytest.mark.parametrize('latest', [None, [], 'unknown', {},
    {'object': 'agent.version', 'name': 'another-agent', 'version': 'other',
     'definition': {'model': CANARY, 'instructions': CANARY, 'tools': [{'type': CANARY}]}},
    {'object': 'different-object', 'name': 'configured', 'version': 'other',
     'definition': {'model': CANARY}}])
def test_optional_latest_shape_or_identity_never_rejects_connection_or_leaks(latest: Any) -> None:
    configured = profile()
    body = records()[0]
    body['versions'] = {'latest': latest}
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=body)

    result = agent_details(COMPANY, configured, Credentials(configured),
                           transport=httpx.MockTransport(handler))
    assert result['status'] == 'METADATA_OBSERVED_ONLY' and len(seen) == 1
    assert result['configuredVersion'] is None and result['observedVersion'] is None
    assert result['metadataSource'] is None and result['modelDeployment'] is None
    assert result['storedInstructionUtf8Bytes'] is None and result['toolTypes'] == []
    assert CANARY not in json.dumps(result)


@pytest.mark.parametrize('version', [None, True, ['latest'], 'unsupported version', CANARY + '\n'])
def test_optional_latest_version_format_does_not_gate_other_same_agent_observations(
    version: Any,
) -> None:
    configured = profile()
    latest = records()[1]
    latest['version'] = version
    body = records()[0]
    body['versions'] = {'latest': latest}
    result = agent_details(COMPANY, configured, Credentials(configured),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    assert result['status'] == 'METADATA_OBSERVED_ONLY'
    assert result['configuredVersion'] is None and result['observedVersion'] is None
    assert result['metadataSource'] == 'AZURE_LATEST'
    assert result['modelDeployment'] == 'configured-model'
    assert CANARY not in json.dumps(result)


def test_explicit_saved_version_observation_ignores_conflicting_inline_latest() -> None:
    configured = profile(agent_version='configured-version')
    bodies = records()
    bodies[0]['versions'] = {'latest': {'object': 'agent.version', 'name': 'configured',
        'version': 'other', 'definition': {'model': CANARY, 'instructions': CANARY}}}
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=bodies[len(seen) - 1])

    result = agent_details(COMPANY, configured, Credentials(configured),
                           transport=httpx.MockTransport(handler))
    assert len(seen) == 2 and seen[1].url.path.endswith('/versions/configured-version')
    assert result['configuredVersion'] == result['observedVersion'] == 'configured-version'
    assert result['metadataSource'] == 'CONFIGURED_VERSION'
    assert result['modelDeployment'] == 'configured-model'
    assert CANARY not in json.dumps(result)


def test_late_capability_change_clears_inline_observations() -> None:
    configured = profile()
    credential = Credentials(configured)
    body = records()[0]
    body['versions'] = {'latest': records()[1]}

    def handler(request: httpx.Request) -> httpx.Response:
        credential.enabled = False
        return httpx.Response(200, json=body)

    result = agent_details(COMPANY, configured, credential, transport=httpx.MockTransport(handler))
    assert result['status'] == 'METADATA_UNAVAILABLE'
    assert result['observedVersion'] is None and result['metadataSource'] is None
    assert result['modelDeployment'] is None and result['storedInstructionUtf8Bytes'] is None
    assert CANARY not in json.dumps(result)


@pytest.mark.parametrize('status', [401, 403, 429, 503])
def test_http_failure_preserves_exact_operation_status_type_and_trace_without_body(
    status: int,
) -> None:
    configured = profile()
    result = agent_details(COMPANY, configured, Credentials(configured),
        transport=httpx.MockTransport(lambda request: httpx.Response(status, text=CANARY)))
    details = result['diagnostic']
    assert details['operation'] == 'AGENT_METADATA_GET'
    assert details['exception_type'] == 'builtins.ValueError'
    assert details['message'] == f'Agent metadata HTTP status {status}'
    assert any(f['file'] == 'foundry_agent_details.py' and f['function'] == 'read'
               for f in details['frames'])
    assert CANARY not in json.dumps(result)


def test_json_error_keeps_original_decoder_message_and_actual_type_without_payload() -> None:
    configured = profile()
    result = agent_details(COMPANY, configured, Credentials(configured),
        transport=httpx.MockTransport(lambda request: httpx.Response(200,
            content=b'{', headers={'content-type': 'application/json'})))
    details = result['diagnostic']
    assert details['operation'] == 'AGENT_METADATA_GET_RESPONSE_JSON_DECODE'
    assert details['exception_type'] == 'json.decoder.JSONDecodeError'
    assert 'Expecting property name enclosed in double quotes' in details['message']
    assert details['frames'] and details['frames'][-1]['file'] == 'decoder.py'

def test_diagnostic_preserves_original_meaning_and_codes_while_redacting_private_values():
    from apbra_api.foundry_agent_details import _redacted_error_details
    private = 'opaque-private-authentication-value'
    try:
        raise RuntimeError('Authentication failed AADSTS700016: invalid_client; '
            'Bearer ' + private + '; account person@example.invalid; '
            'tenant 00000000-0000-0000-0000-000000000001; '
            "directory 'Private Company'; https://host.invalid/secret/path; "
            '{"error":"invalid_client","private":"raw-response-secret"}')
    except RuntimeError as error:
        details = _redacted_error_details(error, 'BROWSER_AUTHENTICATION', redactions=(private,))
    encoded = json.dumps(details)
    assert details['exception_type'] == 'builtins.RuntimeError'
    assert 'Authentication failed AADSTS700016' in details['message']
    assert details['provider_error_codes'] == ['AADSTS700016', 'invalid_client']
    assert details['frames'][-1]['function'] == \
        'test_diagnostic_preserves_original_meaning_and_codes_while_redacting_private_values'
    for value in [private, 'person@example.invalid', '00000000-0000-0000-0000-000000000001',
                  'Private Company', 'host.invalid', 'raw-response-secret']:
        assert value not in encoded
    assert 'OtherException' not in encoded


@pytest.mark.parametrize('private_field', [
    "password='violet amber mist'", 'client_secret="violet amber mist"',
    'password: violet amber mist', 'Authorization: Basic dTpw',
    'Authorization: Bearer violet', 'Proxy-Authorization: Custom violet amber mist',
    'Cookie: session=violet; owner=amber', 'clientSecret=violet amber mist',
])
def test_diagnostic_redacts_complete_sensitive_fields_including_quoted_or_basic_values(
    private_field: str,
) -> None:
    from apbra_api.foundry_agent_details import _redacted_error_details
    details = _redacted_error_details(ValueError('Authentication failed: ' + private_field),
                                       'BROWSER_AUTHENTICATION')
    assert details['exception_type'] == 'builtins.ValueError'
    assert details['message'].startswith('Authentication failed: ')
    for value in ['violet', 'amber', 'mist', 'dTpw']:
        assert value not in json.dumps(details)


@pytest.mark.parametrize('payload', ['{"private":"violet', '<html>violet amber</html>',
                                    '["violet",', 'response body: violet amber mist'])
def test_diagnostic_redacts_unclosed_structured_or_text_payload(payload: str) -> None:
    from apbra_api.foundry_agent_details import _redacted_error_details
    details = _redacted_error_details(RuntimeError('Server rejected request: ' + payload), 'GET')
    assert details['message'].startswith('Server rejected request: ')
    assert 'violet' not in json.dumps(details)


def test_diagnostic_keeps_technical_codes_without_private_multiline_body() -> None:
    from apbra_api.foundry_agent_details import _redacted_error_details
    details = _redacted_error_details(RuntimeError('Authentication failed\n'
        'AADSTS700016 invalid_client\nPrivate customer data violet amber mist'), 'AUTH')
    assert details['message'] == 'Authentication failed'
    assert details['message_redacted_continuation_lines'] == 2
    assert details['provider_error_codes'] == ['AADSTS700016', 'invalid_client']
    assert 'violet' not in json.dumps(details)


@pytest.mark.parametrize('fail_rendering', [False, True])
def test_diagnostic_suppresses_side_effect_output_while_rendering_original_error(
    capsys: Any, fail_rendering: bool,
) -> None:
    import sys

    from apbra_api.foundry_agent_details import _redacted_error_details

    class LoudError(Exception):
        def __str__(self) -> str:
            print(CANARY)
            print(CANARY, file=sys.stderr)
            if fail_rendering:
                raise TypeError(CANARY)
            return 'Useful original failure reason'

    details = _redacted_error_details(LoudError(), 'SDK_CALL')
    assert details['exception_type'].endswith('.LoudError')
    if fail_rendering:
        assert details['message_rendering_error_type'] == 'builtins.TypeError'
    else:
        assert details['message'] == 'Useful original failure reason'
    assert capsys.readouterr() == ('', '')
    assert CANARY not in json.dumps(details)


@pytest.mark.parametrize('message', ['[Errno 61] Connection refused',
    '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: '
    'unable to get local issuer certificate (_ssl.c:1000)'])
def test_standard_network_error_brackets_preserve_the_original_technical_reason(
    message: str,
) -> None:
    from apbra_api.foundry_agent_details import _redacted_error_details
    details = _redacted_error_details(OSError(message), 'AGENT_METADATA_GET')
    assert details['message'] == message
    assert details['exception_type'] == 'builtins.OSError'


@pytest.mark.parametrize('code', ['QUALIFIED_PROFILES_INVALID',
    'FOUNDRY_HOST_CONFIGURATION_UNAVAILABLE', 'FOUNDRY_REPORT_AUTHORIZATION_UNAVAILABLE'])
def test_known_authored_technical_error_constants_are_preserved_exactly(code: str) -> None:
    from apbra_api.foundry_agent_details import _redacted_error_details
    details = _redacted_error_details(ValueError(code), 'PRIVATE_REPORT_QUALIFICATION')
    assert details['message'] == code
