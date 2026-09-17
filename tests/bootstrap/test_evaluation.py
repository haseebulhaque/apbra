"""Synthetic harness tests; none are measurements of the APBRA application."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).parent / 'evaluation' / 'harness.py'
spec = importlib.util.spec_from_file_location('evaluation_harness', MODULE)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads(MODULE.with_name('registry.json').read_text())
        self.run = h.new_run(self.registry, execution_id='synthetic-self-test')

    def add(self, run=None, case='requirements', status='PASSED', **changes):
        run = run or self.run
        definition = next(c for c in run['registry']['cases'] if c['id'] == case)
        args = dict(status=status, actual='Synthetic observation for harness self-test only',
                    evaluator='unittest synthetic adapter', evidence=['artifacts/synthetic/result.json'],
                    latency_ms=10, terminal=definition['expected_terminal'],
                    rubric_evidence='Synthetic deterministic assertion', assessment_method='deterministic')
        if status not in h.EXECUTED:
            args['latency_ms'] = None
        args.update(changes)
        return h.record(run, case, **args)

    def test_unexecuted_is_not_run_tbd(self):
        summary = h.summarize(self.run)
        self.assertEqual(summary['status'], 'NOT_RUN')
        self.assertEqual(summary['quality'], 'TBD')
        self.assertIsNone(summary['executed_pass_rate']['value'])
        self.assertIsNone(summary['observed_failures'])
        self.assertFalse(summary['mandatory_gate'])
        self.assertEqual(summary['not_run'], len(self.registry['cases']))

    def test_skipped_mandatory_prevents_gate(self):
        run = self.run
        for case in self.registry['cases'][1:]:
            kwargs = dict(relevant_evidence=['rule'], retrieved_evidence=['rule'], k=1) if case['metric'] == 'retrieval' else {}
            run = self.add(run, case['id'], **kwargs)
        self.assertFalse(h.summarize(run)['mandatory_gate'])
        self.assertEqual(h.summarize(run)['unresolved_mandatory'], ['requirements'])

    def test_complete_synthetic_gate_requires_every_mandatory(self):
        run = self.run
        for case in self.registry['cases']:
            kwargs = dict(relevant_evidence=['rule'], retrieved_evidence=['rule'], k=1) if case['metric'] == 'retrieval' else {}
            run = self.add(run, case['id'], **kwargs)
        self.assertTrue(h.summarize(run)['mandatory_gate'])
        self.assertEqual(h.summarize(run)['status'], 'COMPLETE_PASS')

    def test_failed_and_provider_error_stay_in_denominator(self):
        run = self.add()
        run = self.add(run, 'design', 'FAILED')
        run = self.add(run, 'generation', 'ERRORED', actual='Provider timeout')
        summary = h.summarize(run)
        self.assertEqual(summary['executed_pass_rate'], h.ratio(1, 3))
        self.assertEqual(summary['execution_coverage'], h.ratio(3, 24))
        self.assertEqual(summary['observed_failures'], 2)

    def test_counts_reconcile_with_raw_cases(self):
        run = self.add(status='FAILED')
        run = self.add(run, 'design', 'ERRORED')
        run = self.add(run, 'generation', 'BLOCKED')
        run = self.add(run, 'unsupported', 'UNSUPPORTED')
        result = h.summarize(run)
        self.assertEqual(result['applicable'], sum(result[k.lower()] for k in h.STATUSES))
        self.assertEqual(result['planned'], result['applicable'] + result['excluded'])
        self.assertEqual(result['executed'], 3)

    def test_retry_preserves_failure_first_and_eventual_success(self):
        failed = self.add(case='validation', status='FAILED')
        passed = self.add(failed, 'validation')
        self.assertEqual(len(failed['attempts']), 1)
        self.assertEqual(len(passed['attempts']), 2)
        result = h.summarize(passed)
        self.assertEqual(result['attempt_counts'], {'FAILED': 1, 'PASSED': 1})
        self.assertEqual(result['first_attempt_pass_rate'], h.ratio(0, 1))
        self.assertEqual(result['executed_pass_rate'], h.ratio(1, 1))
        self.assertEqual(result['metrics']['first_pass_validation']['executed_pass_rate'], h.ratio(0, 1))

    def test_rerun_records_link_without_replacing_old(self):
        first = self.add()
        second = h.new_run(self.registry, previous_run_id=first['run_id'])
        self.assertNotEqual(first['run_id'], second['run_id'])
        self.assertEqual(second['previous_run_id'], first['run_id'])
        self.assertTrue(second['repeated_run'])
        self.assertEqual(second['attempts'], [])
        self.assertEqual(len(first['attempts']), 1)

    def test_safe_refusal_not_generation_or_release(self):
        result = h.summarize(self.add(case='unsupported'))
        self.assertEqual(result['passed'], 1)
        self.assertEqual(result['successful_releases'], 0)
        self.assertIsNone(result['metrics']['generation']['executed_pass_rate']['value'])

    def test_unexpected_unsupported_must_be_failure(self):
        with self.assertRaises(ValueError):
            self.add(case='generation', status='UNSUPPORTED')
        self.assertEqual(h.summarize(self.add(case='generation', status='FAILED'))['failed'], 1)

    def test_unknown_case_and_status_rejected(self):
        with self.assertRaises(ValueError):
            h.record(self.run, 'not-declared', status='PASSED', actual='x', evaluator='x')
        with self.assertRaises(ValueError):
            self.add(status='SKIPPED_AS_PASS')

    def test_pass_requires_expected_terminal_and_rubric(self):
        with self.assertRaises(ValueError):
            self.add(terminal='SAFE_REFUSAL')
        with self.assertRaises(ValueError):
            self.add(rubric_evidence=None)

    def test_inventory_cannot_change_after_measurement(self):
        run = self.add()
        run['registry']['cases'][1]['mandatory'] = False
        with self.assertRaises(ValueError):
            h.summarize(run)

    def test_registry_duplicate_missing_and_invalid_cases_rejected(self):
        for mutation in ('duplicate', 'missing', 'partition'):
            registry = copy.deepcopy(self.registry)
            if mutation == 'duplicate':
                registry['cases'].append(registry['cases'][0])
            elif mutation == 'missing':
                del registry['cases'][0]['rubric']
            else:
                registry['cases'][0]['partition'] = 'unlabelled'
            with self.assertRaises(ValueError):
                h.new_run(registry)

    def test_applicability_exclusion_requires_reason(self):
        registry = copy.deepcopy(self.registry)
        registry['cases'][0]['applicable'] = False
        with self.assertRaises(ValueError):
            h.new_run(registry)
        registry['cases'][0]['applicability_reason'] = 'Explicit synthetic test exclusion'
        run = h.new_run(registry)
        self.assertEqual(h.summarize(run)['excluded'], 1)
        with self.assertRaises(ValueError):
            self.add(run)

    def test_mandatory_governance_positive_negative_routes_present(self):
        for case_id in ('business-route', 'business-unauthorized', 'business-stale',
                        'trusted-route', 'trusted-forged', 'trusted-invalid', 'revoked-reviewer'):
            case = next(c for c in self.registry['cases'] if c['id'] == case_id)
            self.assertTrue(case['mandatory'])
            self.assertTrue(case['applicable'])

    def test_fixtures_exist_and_partitions_distinct(self):
        paths = {'development': set(), 'held_out': set()}
        for case in self.registry['cases']:
            for path in case['fixtures']:
                self.assertTrue((h.ROOT / path).is_file())
                paths[case['partition']].add(path)
        self.assertFalse(paths['development'] & paths['held_out'])

    def test_all_required_versions_explicitly_unknown(self):
        self.assertEqual(set(self.run['versions']), set(h.VERSIONS))
        self.assertTrue(all(v['value'] is None and v['reason'] for v in self.run['versions'].values()))
        with self.assertRaises(ValueError):
            h.new_run(self.registry, versions={'model': 'invented'})

    def test_latency_and_cost_keep_failed_attempts_and_variability(self):
        cost = dict(amount=0.2, currency='AUD', rate_version='synthetic-v1', basis='per_call', kind='estimate')
        run = self.add(case='business-release', status='ERRORED', latency_ms=5, cost=cost)
        run = self.add(run, 'business-release', latency_ms=15, cost=cost)
        result = h.summarize(run)
        self.assertEqual(result['latency']['n'], 2)
        self.assertEqual(result['latency']['mean_ms'], 10)
        self.assertEqual(result['latency']['stdev_ms'], 5)
        self.assertEqual(result['cost_totals'][0]['amount'], '0.4')
        self.assertEqual(result['cost_totals'][0]['per_successful_release'], '0.4')
        self.assertFalse(result['cost_is_invoice'])

    def test_unknown_cost_not_zero_and_mixed_currency_separate(self):
        result = h.summarize(self.add())
        self.assertEqual(result['unknown_cost_attempts'], 1)
        self.assertEqual(result['cost_totals'], [])
        run = self.add(cost=dict(amount=1, currency='AUD', rate_version='v1', basis='call', kind='estimate'))
        run = self.add(run, 'design', cost=dict(amount=1, currency='USD', rate_version='v1', basis='call', kind='estimate'))
        self.assertEqual(len(h.summarize(run)['cost_totals']), 2)

    def test_invalid_measurements_rejected(self):
        for value in (-1, float('inf'), float('nan'), True):
            with self.assertRaises(ValueError):
                self.add(latency_ms=value)
        with self.assertRaises(ValueError):
            self.add(cost={'amount': 1})
        with self.assertRaises(ValueError):
            self.add(usage={'values': {'tokens': -1}})

    def test_recall_at_k_no_duplicate_inflation(self):
        run = self.add(case='retrieval', relevant_evidence=['a', 'b'], retrieved_evidence=['a', 'a', 'b'], k=2)
        self.assertEqual(h.summarize(run)['recall_at_k_all_attempts'], h.ratio(1, 2))
        with self.assertRaises(ValueError):
            self.add(case='retrieval')

    def test_llm_only_security_arithmetic_and_validity_cannot_pass(self):
        for case in ('numeric-runtime', 'trusted-forged', 'validation'):
            with self.assertRaises(ValueError):
                self.add(case=case, assessment_method='llm_only')

    def test_evidence_paths_reject_absolute_traversal_and_signed_urls(self):
        for path in ('https://example.invalid/?token=fake', '/tmp/out', 'artifacts/../x', 'tests//x', 'secrets/x'):
            with self.assertRaises(ValueError):
                self.add(evidence=[path])

    def test_export_retains_raw_and_derived_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            h.export(self.run, root, 'artifacts/evaluation/run.json')
            data = json.loads((root / 'artifacts/evaluation/run.json').read_text())
            self.assertEqual(data['run'], self.run)
            self.assertEqual(data['summary'], h.summarize(self.run))
            with self.assertRaises(ValueError):
                h.export(self.run, root, 'artifacts/evaluation/run.json')

    def test_export_symlinks_and_traversal_no_external_side_effects(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as external:
            root = Path(folder)
            (root / 'artifacts').symlink_to(external)
            with self.assertRaises(ValueError):
                h.export(self.run, root, 'artifacts/new/result.json')
            self.assertEqual(list(Path(external).iterdir()), [])
            with self.assertRaises(ValueError):
                h.export(self.run, root, 'artifacts/../escape.json')

    def test_altered_attempt_sequence_rejected(self):
        run = self.add()
        run['attempts'][0]['attempt'] = 2
        with self.assertRaises(ValueError):
            h.summarize(run)


if __name__ == '__main__':
    unittest.main()
