"""Import measured local observations without changing the frozen case inventory."""
import argparse
import json
from pathlib import Path
import harness


def import_observations(raw, evidence_reference):
    registry = json.loads(Path(__file__).with_name('registry.json').read_text())
    expected_ids = {c['id'] for c in registry['cases']}
    if {o['id'] for o in raw['observations']} != expected_ids or len(raw['observations']) != len(expected_ids):
        raise ValueError('Exactly one observation per frozen case required')
    if any(o['execution_id'] != raw['executionId'] for o in raw['observations']):
        raise ValueError('Observation identity mismatch')
    versions = {key: {'value': None, 'reason': 'Not invoked in deterministic local Capstone'} for key in harness.VERSIONS}
    for key, value in {'prompt': 'sales-request-v1', 'schema': 'sales-star-v1', 'source': raw['sourceRevision'],
                       'generator': 'capstone-pbip-1', 'validator': 'capstone-validator-1',
                       'compatibility': 'Source profile golden-source-1; Power BI runtime NOT_RUN'}.items():
        versions[key] = {'value': value}
    run = harness.new_run(registry, versions=versions, execution_id=raw['executionId'])
    for o in raw['observations']:
        actual = o['actual']
        retrieval = o['id'] == 'retrieval'
        run = harness.record(run, o['id'], status=o['status'], actual=json.dumps(actual, sort_keys=True),
            evaluator='APBRA-QA deterministic local adapter; Codex execution (not human)',
            evidence=[evidence_reference], latency_ms=o['latency_ms'], terminal=o['terminal'],
            rubric_evidence={'method': 'Executable assertions in execute-local.ts', 'observation': actual},
            candidate_id=actual.get('candidateSha256'), review_id=None,
            release_id=actual.get('operationId') if o['id'].endswith('release') else None,
            usage={'values': {'model_calls': 0, 'model_tokens': 0}},
            cost={'amount': None, 'unavailable_reason': 'No provider invocation; machine and engineering costs unmeasured'},
            relevant_evidence=json.loads((Path(__file__).parent.parent/'fixtures/sales-v1/design.expected.json').read_text())['required_evidence_ids'] if retrieval else None,
            retrieved_evidence=actual.get('orderedEvidenceIds') if retrieval else None,
            k=actual.get('retrievalK') if retrieval else None)
    return run


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('observations');p.add_argument('evidence_reference');p.add_argument('output')
    args=p.parse_args();run=import_observations(json.loads(Path(args.observations).read_text()),args.evidence_reference)
    harness.export(run,harness.ROOT,args.output)
    print(json.dumps(harness.summarize(run),indent=2))
