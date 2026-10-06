"""Mutation tests for the bootstrap pipeline; not native ruleset proof."""
import importlib.util
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('ci_policy', ROOT / 'scripts/check_ci_policy.py')
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
BOOTSTRAP_SPEC = importlib.util.spec_from_file_location('bootstrap_for_ci_capacity', ROOT / 'scripts/check_bootstrap.py')
b = importlib.util.module_from_spec(BOOTSTRAP_SPEC)
BOOTSTRAP_SPEC.loader.exec_module(b)


class CiPolicyTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / '.github/workflows/bootstrap.yml').read_text()
        self.doc = yaml.load(self.text, Loader=yaml.BaseLoader)
        self.job = self.doc['jobs']['bootstrap']

    def rejected(self):
        self.assertTrue(c.validate(yaml.safe_dump(self.doc)))

    def test_current_workflow(self):
        self.assertEqual(self.job['timeout-minutes'], '45')
        self.assertEqual(c.validate(self.text), [])

    def test_step_names_are_not_authority(self):
        self.job['steps'][0]['name'] = 'A different description'
        self.assertEqual(c.validate(yaml.safe_dump(self.doc)), [])

    def test_missing_frontend_tests(self):
        self.job['steps'] = [s for s in self.job['steps'] if s.get('run', '').strip() != c.WEB_COMMAND]
        self.rejected()

    def test_semantic_bridge_must_be_built_before_backend_tests(self):
        bridge = next(s for s in self.job['steps'] if s.get('run', '').strip() == c.TYPESCRIPT_BRIDGE_BUILD)
        self.job['steps'].remove(bridge)
        api_index = next(index for index,step in enumerate(self.job['steps']) if step.get('run','').strip() == c.API_CHECK)
        self.job['steps'].insert(api_index+1,bridge)
        self.rejected()

    def test_backend_bridge_path_is_fixed(self):
        self.job['env']['APBRA_TEST_SEMANTIC_BRIDGE'] = '/tmp/other.mjs'
        self.rejected()

    def test_generation_bridge_must_be_built_and_fixed(self):
        bridge = next(
            s
            for s in self.job['steps']
            if s.get('run', '').strip() == c.TYPESCRIPT_BRIDGE_BUILD
        )
        bridge['run'] = bridge['run'].replace(
            'npm --prefix apps/web run build:generation-bridge', ''
        )
        self.rejected()
        self.setUp()
        self.job['env']['APBRA_TEST_GENERATION_BRIDGE'] = '/tmp/other.mjs'
        self.rejected()

    def test_frontend_failure_not_hidden(self):
        next(s for s in self.job['steps'] if s.get('run', '').strip() == c.WEB_COMMAND)['run'] += ' || true'
        self.rejected()

    def test_wrong_node_version(self):
        next(s for s in self.job['steps'] if s.get('uses', '').startswith('actions/setup-node@'))['with']['node-version'] = '19'
        self.rejected()

    def test_timeout_is_exact_capacity_boundary(self):
        for timeout in ('10', '19', '20', '21', '29', '30', '31', '44', '46'):
            with self.subTest(timeout=timeout):
                self.job['timeout-minutes'] = timeout
                self.rejected()

    def test_apbra160_capacity_branch_has_exact_four_file_authority(self):
        expected = {
            '.github/workflows/bootstrap.yml',
            'scripts/check_bootstrap.py',
            'scripts/check_ci_policy.py',
            'tests/bootstrap/test_ci_policy.py',
        }
        self.assertEqual(b.APBRA160_CI_CAPACITY_PATHS, expected)
        self.assertEqual(len(expected), 4)
        self.assertTrue(all('*' not in path for path in expected))
        branch = b.APBRA160_CI_CAPACITY_BRANCH
        self.assertEqual(branch, 'agent/APBRA-DEVOPS/APBRA-160-bootstrap-ci-capacity')
        self.assertEqual(b.check(ROOT, active_task_id='APBRA-160',
                                 active_branch=branch, changed_paths=expected)[0], [])
        for omitted in expected:
            with self.subTest(omitted=omitted):
                errors = b.check(ROOT, active_task_id='APBRA-160', active_branch=branch,
                                 changed_paths=expected - {omitted})[0]
                self.assertIn('APBRA-160 CI-capacity amendment must change exactly four policy files', errors)
        for extra in ('apps/api/src/apbra_api/api.py', 'docs/source-register.json'):
            with self.subTest(extra=extra):
                errors = b.check(ROOT, active_task_id='APBRA-160', active_branch=branch,
                                 changed_paths=expected | {extra})[0]
                self.assertIn('APBRA-160 CI-capacity amendment must change exactly four policy files', errors)

    def test_missing_scanner(self):
        self.job['steps'] = [s for s in self.job['steps'] if s.get('run') != c.COMMANDS[0]]
        self.rejected()

    def test_missing_tests(self):
        self.job['steps'] = [s for s in self.job['steps'] if s.get('run') != c.COMMANDS[-1]]
        self.rejected()

    def test_swallowed_exit_code(self):
        next(s for s in self.job['steps'] if s.get('run') == c.COMMANDS[-1])['run'] += ' || true'
        self.rejected()

    def test_continue_on_error(self):
        self.job['steps'][2]['continue-on-error'] = 'true'
        self.rejected()

    def test_skipped_scanner(self):
        self.job['steps'][2]['if'] = 'false'
        self.rejected()

    def test_skipped_entire_job(self):
        self.job['if'] = 'false'
        self.rejected()

    def test_job_write_permissions(self):
        self.job['permissions'] = {'contents': 'write'}
        self.rejected()

    def test_extra_command(self):
        self.job['steps'].append({'run': 'echo unrelated'})
        self.rejected()

    def test_shallow_checkout(self):
        self.job['steps'][0]['with']['fetch-depth'] = '1'
        self.rejected()

    def test_custom_checkout_token(self):
        self.job['steps'][0]['with']['token'] = '${{ github.token }}'
        self.rejected()

    def test_missing_evidence_is_error(self):
        self.job['steps'][-1]['with']['if-no-files-found'] = 'warn'
        self.rejected()

    def test_workflow_path_filter(self):
        self.doc['on']['pull_request']['paths'] = ['README.md']
        self.rejected()

    def test_environment_override(self):
        self.job['steps'][2]['env'] = {'PATH': '/other'}
        self.rejected()

    def test_duplicate_mapping_key(self):
        self.assertTrue(c.validate(self.text + '\npermissions:\n  contents: write\n'))

    def test_reordered_checks(self):
        self.job['steps'][2], self.job['steps'][3] = self.job['steps'][3], self.job['steps'][2]
        self.rejected()

    def test_malformed_job(self):
        self.doc['jobs']['bootstrap'] = ['bad']
        self.rejected()


if __name__ == '__main__':
    unittest.main()
