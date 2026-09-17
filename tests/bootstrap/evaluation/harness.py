"""APBRA-91 offline evidence accounting; never invokes a model or the product."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import statistics
import uuid

ROOT = Path(__file__).resolve().parents[3]
STATUSES = {'PASSED', 'FAILED', 'ERRORED', 'NOT_RUN', 'BLOCKED', 'UNSUPPORTED'}
EXECUTED = {'PASSED', 'FAILED', 'ERRORED', 'UNSUPPORTED'}
VERSIONS = ('model', 'deployment', 'profile', 'prompt', 'schema', 'embedding',
            'index', 'source', 'generator', 'validator', 'compatibility')
METRICS = ('structured_output', 'clarification', 'retrieval', 'citation_integrity',
           'precedence', 'first_pass_validation', 'repair', 'generation',
           'governance', 'end_to_end', 'business_runtime', 'authorization', 'human_quality')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def finite_nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def safe_reference(value):
    """Only repository-relative evidence paths, never signed/credential URLs."""
    return (isinstance(value, str) and bool(value) and ':' not in value
            and '\\' not in value and not value.startswith('/')
            and all(p not in ('', '.', '..') for p in value.split('/'))
            and PurePosixPath(value).parts[0] in ('artifacts', 'tests'))


def validate_registry(registry):
    if registry.get('version') != 1 or registry.get('synthetic') is not True:
        raise ValueError('Versioned synthetic registry required')
    cases = registry.get('cases', [])
    if not cases or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Nonempty unique case IDs required')
    for case in cases:
        for field in ('id', 'requirements', 'capability', 'expected', 'rubric', 'fixtures'):
            if not case.get(field):
                raise ValueError(f'Missing {field}')
        if type(case.get('mandatory')) is not bool or type(case.get('applicable')) is not bool:
            raise ValueError('Explicit mandatory/applicable flags required')
        if not case['applicable'] and not case.get('applicability_reason'):
            raise ValueError('Non-applicability requires a declared reason')
        if case.get('partition') not in ('development', 'held_out'):
            raise ValueError('Declare development or held_out partition')
        if case.get('metric') in ('generation', 'end_to_end') and case.get('expected_terminal') != 'SUCCESS':
            raise ValueError('Generation/release metrics require successful generation, not safe refusal')
        if case.get('metric') not in METRICS or case.get('expected_terminal') not in (
                'SUCCESS', 'SAFE_REFUSAL', 'BLOCK', 'FAILURE_DETECTED'):
            raise ValueError('Unknown metric or terminal outcome')
        if not all(safe_reference(p) for p in case['fixtures']):
            raise ValueError('Unsafe fixture reference')
    return registry


def new_run(registry, *, versions=None, execution_id=None, previous_run_id=None):
    """Freeze inventory before measurements; new run never overwrites old results."""
    registry = deepcopy(validate_registry(registry))
    version_info = {key: {'value': None, 'reason': 'Component/provider not available'}
                    for key in VERSIONS}
    if versions is not None:
        if set(versions) != set(VERSIONS):
            raise ValueError('Record every required version or explicit unavailable reason')
        for info in versions.values():
            if not isinstance(info, dict) or not (info.get('value') or info.get('reason')):
                raise ValueError('Unavailable version requires reason')
        version_info = deepcopy(versions)
    return {'format_version': 1, 'run_id': execution_id or str(uuid.uuid4()),
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'previous_run_id': previous_run_id, 'repeated_run': previous_run_id is not None,
            'registry': registry, 'registry_sha256': digest(registry),
            'versions': version_info, 'attempts': []}


def validate_attempt(case, attempt):
    status = attempt.get('status')
    if status not in STATUSES:
        raise ValueError('Unknown status')
    if not case['applicable']:
        raise ValueError('Cannot execute excluded case without a new declared inventory')
    if not attempt.get('actual') or not attempt.get('evaluator'):
        raise ValueError('Actual outcome and evaluator identity required')
    if status in EXECUTED:
        if not attempt.get('evidence') or not all(safe_reference(p) for p in attempt['evidence']):
            raise ValueError('Executed outcome requires safe evidence references')
        if not finite_nonnegative(attempt.get('latency_ms')):
            raise ValueError('Executed outcome requires measured nonnegative latency')
    elif attempt.get('latency_ms') is not None:
        raise ValueError('Unexecuted outcome cannot have measured latency')
    if status == 'PASSED' and attempt.get('terminal') != case['expected_terminal']:
        raise ValueError('Passing terminal must match declared expectation')
    if status == 'PASSED' and not attempt.get('rubric_evidence'):
        raise ValueError('Pass requires rubric assessment, not status alone')
    if case['metric'] in ('business_runtime', 'authorization', 'first_pass_validation') and (
            status == 'PASSED' and attempt.get('assessment_method') == 'llm_only'):
        raise ValueError('LLM-only arithmetic/security/file validity judgment forbidden')
    if status == 'UNSUPPORTED' and case['expected_terminal'] != 'SAFE_REFUSAL':
        raise ValueError('Unsupported on supported request must be FAILED')
    cost = attempt.get('cost', {})
    amount = cost.get('amount')
    if amount is None:
        if not cost.get('unavailable_reason'):
            raise ValueError('Missing cost requires explicit unavailable reason')
    elif (not finite_nonnegative(amount) or not all(cost.get(k) for k in (
            'currency', 'rate_version', 'basis')) or cost.get('kind') not in ('estimate', 'measured')):
        raise ValueError('Cost requires finite amount, currency/rate/basis and kind')
    usage = attempt.get('usage', {})
    if not usage or (usage.get('values') is None and not usage.get('unavailable_reason')):
        raise ValueError('Record usage or unavailable reason')
    if usage.get('values') is not None and not all(
            finite_nonnegative(v) for v in usage['values'].values()):
        raise ValueError('Invalid usage measurement')
    relevant, retrieved = attempt.get('relevant_evidence'), attempt.get('retrieved_evidence')
    if case['metric'] == 'retrieval' and status in EXECUTED:
        if not isinstance(relevant, list) or not relevant or not isinstance(retrieved, list):
            raise ValueError('Recall requires expected/retrieved evidence IDs')
        if type(attempt.get('k')) is not int or attempt['k'] <= 0:
            raise ValueError('Recall requires positive K')
    for field in ('execution_id', 'candidate_id', 'review_id', 'release_id'):
        if field not in attempt:
            raise ValueError('Record lineage identifiers, null when unavailable')


def record(run, case_id, *, status, actual, evaluator, evidence=(), latency_ms=None,
           terminal=None, rubric_evidence=None, assessment_method='deterministic',
           usage=None, cost=None, relevant_evidence=None, retrieved_evidence=None,
           k=None, candidate_id=None, review_id=None, release_id=None):
    """Return a new run value. Retrying appends; earlier failures remain present."""
    validate_run(run)
    case = next((c for c in run['registry']['cases'] if c['id'] == case_id), None)
    if case is None:
        raise ValueError('Case was not predeclared')
    attempt = {'case_id': case_id, 'attempt': 1 + sum(a['case_id'] == case_id for a in run['attempts']),
               'status': status, 'actual': actual, 'evaluator': evaluator, 'terminal': terminal,
               'rubric_evidence': rubric_evidence, 'assessment_method': assessment_method,
               'evidence': list(evidence), 'latency_ms': latency_ms,
               'usage': usage or {'values': None, 'unavailable_reason': 'Not supplied'},
               'cost': cost or {'amount': None, 'unavailable_reason': 'Not supplied'},
               'relevant_evidence': relevant_evidence, 'retrieved_evidence': retrieved_evidence, 'k': k,
               'execution_id': run['run_id'], 'candidate_id': candidate_id,
               'review_id': review_id, 'release_id': release_id}
    validate_attempt(case, attempt)
    result = deepcopy(run)
    result['attempts'].append(attempt)
    return result


def validate_run(run):
    registry = validate_registry(run['registry'])
    if digest(registry) != run['registry_sha256']:
        raise ValueError('Declared inventory changed after run creation')
    cases = {c['id']: c for c in registry['cases']}
    counts = Counter()
    for attempt in run['attempts']:
        if attempt['case_id'] not in cases:
            raise ValueError('Undeclared case')
        counts[attempt['case_id']] += 1
        if attempt['attempt'] != counts[attempt['case_id']]:
            raise ValueError('Attempt history is not sequential')
        validate_attempt(cases[attempt['case_id']], attempt)
    return run


def ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}


def summarize(run):
    validate_run(run)
    cases = [c for c in run['registry']['cases'] if c['applicable']]
    attempts = run['attempts']
    latest = {a['case_id']: a for a in attempts}
    first = {}
    for a in attempts:
        first.setdefault(a['case_id'], a)
    counts = Counter(latest.get(c['id'], {}).get('status', 'NOT_RUN') for c in cases)
    executed = sum(counts[s] for s in EXECUTED)
    passed = counts['PASSED']
    metrics = {}
    for metric in METRICS:
        subset = [c for c in cases if c['metric'] == metric]
        observations = [(first if metric == 'first_pass_validation' else latest).get(c['id'], {})
                        for c in subset]
        metrics[metric] = {'applicable': len(subset),
                           'executed_pass_rate': ratio(sum(a.get('status') == 'PASSED' for a in observations),
                                                      sum(a.get('status') in EXECUTED for a in observations)),
                           'coverage': ratio(sum(a.get('status') in EXECUTED for a in observations), len(subset))}
    required = [c for c in cases if c['mandatory']]
    unresolved = [c['id'] for c in required if latest.get(c['id'], {}).get('status') != 'PASSED']
    latencies = [a['latency_ms'] for a in attempts if a['status'] in EXECUTED]
    latency = {'n': len(latencies), 'min_ms': min(latencies) if latencies else None,
               'max_ms': max(latencies) if latencies else None,
               'mean_ms': statistics.mean(latencies) if latencies else None,
               'stdev_ms': statistics.pstdev(latencies) if latencies else None,
               'p95_ms': sorted(latencies)[math.ceil(len(latencies) * .95) - 1] if latencies else None,
               'percentile_method': 'nearest_rank', 'includes_retries_and_failures': True}
    costs = {}
    for a in attempts:
        cost = a['cost']
        if a['status'] in EXECUTED and cost.get('amount') is not None:
            key = (cost['currency'], cost['rate_version'], cost['kind'], cost['basis'])
            costs[key] = costs.get(key, Decimal(0)) + Decimal(str(cost['amount']))
    releases = sum(a['status'] == 'PASSED' and a['terminal'] == 'SUCCESS'
                   and next(c for c in cases if c['id'] == a['case_id'])['metric'] == 'end_to_end'
                   for a in latest.values())
    recall_attempts = [a for a in attempts if a.get('relevant_evidence') and a['status'] in EXECUTED]
    recall = ratio(sum(len(set(a['relevant_evidence']) & set(a['retrieved_evidence'][:a['k']]))
                       for a in recall_attempts), sum(len(set(a['relevant_evidence'])) for a in recall_attempts))
    partitions = {}
    for partition in ('development', 'held_out'):
        subset = [c for c in cases if c['partition'] == partition]
        observations = [latest.get(c['id'], {}) for c in subset]
        n = sum(a.get('status') in EXECUTED for a in observations)
        partitions[partition] = {'case_ids': [c['id'] for c in subset],
                                 'execution_coverage': ratio(n, len(subset)),
                                 'executed_pass_rate': ratio(sum(a.get('status') == 'PASSED' for a in observations), n)}
    return {'status': 'NOT_RUN' if not executed else ('COMPLETE_PASS' if required and not unresolved else 'INCOMPLETE'),
            'planned': len(run['registry']['cases']), 'applicable': len(cases),
            'excluded': len(run['registry']['cases']) - len(cases),
            **{s.lower(): counts[s] for s in sorted(STATUSES)}, 'executed': executed,
            'observed_failures': counts['FAILED'] + counts['ERRORED'] if executed else None,
            'quality': 'TBD' if not executed else 'OBSERVED_SAMPLE_ONLY',
            'execution_coverage': ratio(executed, len(cases)),
            'executed_pass_rate': ratio(passed, executed),
            'mandatory_gate': bool(required) and not unresolved,
            'unresolved_mandatory': unresolved, 'metrics': metrics,
            'attempt_counts': dict(Counter(a['status'] for a in attempts)),
            'first_attempt_pass_rate': ratio(sum(a['status'] == 'PASSED' for a in first.values()),
                                             sum(a['status'] in EXECUTED for a in first.values())),
            'recall_at_k_all_attempts': recall, 'latency': latency,
            'cost_totals': [{'currency': k[0], 'rate_version': k[1], 'kind': k[2], 'basis': k[3],
                             'amount': str(v), 'per_successful_release': str(v / releases) if releases else None}
                            for k, v in costs.items()],
            'unknown_cost_attempts': sum(a['status'] in EXECUTED and a['cost'].get('amount') is None for a in attempts),
            'successful_releases': releases, 'cost_is_invoice': False,
            'partitions': partitions,
            'limitations': 'Synthetic small sample; no production accuracy/cost extrapolation. Reference existence and runtime claims require independent review.'}


def export(run, root, relative_path):
    """Reuse bootstrap exclusive no-follow artifact writer; never overwrite history."""
    spec = importlib.util.spec_from_file_location('bootstrap_writer', ROOT / 'scripts/check_bootstrap.py')
    writer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(writer)
    writer.write_report(Path(root), relative_path, {'run': run, 'summary': summarize(run)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, help='New artifacts/... JSON filename')
    args = parser.parse_args()
    registry = json.loads(Path(__file__).with_name('registry.json').read_text())
    run = new_run(registry)
    export(run, ROOT, args.report)
    print(json.dumps(summarize(run), indent=2))


if __name__ == '__main__':
    main()
