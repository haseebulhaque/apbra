"""Sanitized observed-shape regressions; no live answer, URL, credential or transport."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
from test_model_provider import foundry_profile

from apbra_api.model_provider import ProviderCallError, ProviderContractError
from apbra_api.native_contracts import SavedNativeContract, contract_failure

FIXTURE = Path(__file__).parent / 'fixtures/saved_design_unobserved_citations.json'
META = {'knowledge_binding': 'synthetic-kb', 'knowledge_scope': 'SHARED_STANDARDS',
        'agent_version': None, 'qualification': 'OFFLINE_FIXTURE'}


def decode(body):
    return SavedNativeContract(json.dumps(body).encode(), profile=foundry_profile(),
                               task='REPORT_DESIGN', receipt_id=uuid4(), metadata=META)


def test_saved_actual_design_structure_preserves_unverified_claims_without_fabricating_evidence():
    body = json.loads(FIXTURE.read_text())
    original = json.dumps(body)
    candidate = decode(body)
    assert candidate.grounding['references'] == []
    assert candidate.grounding['unverifiedStandardIndexes'] == [0, 1]
    assert candidate.grounding['retrievalEvidence'] == 'NO_OBSERVED_RETRIEVAL'
    assert candidate.value['standardsApplied'] == json.loads(
        body['output'][1]['content'][0]['text']
    )['standardsApplied']
    assert json.dumps(body) == original


def test_grounded_v2_remains_recognizable_without_fabricated_source_evidence():
    body = json.loads(FIXTURE.read_text())
    body['output'][1]['content'][0]['annotations'] = [
        {'type': 'file_citation', 'file_id': 'synthetic-unobserved-standard-a'},
        {'type': 'file_citation', 'file_id': 'synthetic-unobserved-standard-b'},
    ]
    candidate = decode(body)
    assert len(candidate.grounding['references']) == 2
    assert candidate.grounding['observedToolCount'] == 0
    assert candidate.grounding['retrievalEvidence'] == 'ANNOTATIONS_ONLY'
    assert candidate.value['artifact_kind'] == 'ReportDesign'


@pytest.mark.parametrize('version', [1, True, '2', None])
def test_unsupported_schema_version_keeps_exact_failure_without_echoing_value(version):
    body = json.loads(FIXTURE.read_text())
    value = {'artifact_kind': 'ReportDesign', 'schema_version': version, 'standardsApplied': []}
    body['output'][1]['content'][0]['text'] = json.dumps(value)
    with pytest.raises(ProviderCallError) as caught:
        decode(body)
    assert contract_failure(caught.value)['findings'] == [
        {'path': '/schema_version', 'reason': 'SCHEMA_VERSION_2_REQUIRED'},
    ]


@pytest.mark.parametrize('text', ['not json PRIVATE_CANARY', '{"secret-key":1,"secret-key":2}'])
def test_json_failure_keeps_output_path_without_model_text_or_duplicate_key(text):
    body = json.loads(FIXTURE.read_text())
    body['output'][1]['content'][0]['text'] = text
    with pytest.raises(ProviderCallError) as caught:
        decode(body)
    diagnostic = contract_failure(caught.value)
    assert diagnostic == {
        'code': 'NATIVE_OUTPUT_JSON_INVALID', 'phase': 'NATIVE_CONTRACT',
        'findings': [{'path': '/output/1/content/0/text', 'reason': 'UNAMBIGUOUS_JSON_REQUIRED'}],
    }
    assert 'PRIVATE_CANARY' not in json.dumps(diagnostic)
    assert 'secret-key' not in json.dumps(diagnostic)


def test_unknown_or_forged_diagnostics_cannot_reflect_private_exception_values():
    assert contract_failure(ValueError('PRIVATE_CANARY')) == {
        'code': 'NATIVE_CONTRACT_DECODE_FAILED', 'phase': 'NATIVE_CONTRACT', 'findings': [],
    }
    error = ProviderContractError('PRIVATE_CANARY', path='/PRIVATE_CANARY', reason='PRIVATE_CANARY')
    assert 'PRIVATE_CANARY' not in json.dumps(contract_failure(error))
