"""Requirement-derived engineering checks; no product execution is implied."""
import copy
import importlib.util
import json
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('check_bootstrap', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.task = c.load_json(ROOT / 'tasks/APBRA-85-bootstrap.json')
        self.catalog = c.load_json(ROOT / 'agents/catalog.json')
        self.sources = c.load_json(ROOT / 'docs/source-register.json')
        self.schema = c.load_json(ROOT / 'contracts/engineering/task-contract.schema.json')
        self.card = next(x for x in self.catalog['cards'] if x['agent_id'] == 'APBRA-DEVOPS')
        self.workflow = (ROOT / '.github/workflows/bootstrap.yml').read_text()

    def test_valid_repository(self):
        errors, manifest = c.check(ROOT)
        self.assertEqual(errors, [])
        self.assertGreater(len(manifest), 20)

    def test_valid_task_schema(self):
        self.assertEqual(c.schema_errors(self.schema, self.task), [])

    def test_missing_acceptance(self):
        del self.task['acceptance_criteria']
        self.assertTrue(c.schema_errors(self.schema, self.task))

    def test_empty_verification(self):
        self.task['verification_required'] = []
        self.assertTrue(c.schema_errors(self.schema, self.task))

    def test_unknown_field(self):
        self.task['self_approved'] = True
        self.assertTrue(c.schema_errors(self.schema, self.task))

    def test_invalid_jira_key(self):
        self.task['task_id'] = 'NOT-A-TASK'
        self.assertTrue(c.schema_errors(self.schema, self.task))

    def test_invalid_commit(self):
        self.task['base_commit'] = 'latest'
        self.assertTrue(c.schema_errors(self.schema, self.task))

    def test_unknown_agent(self):
        self.task['assigned_agent'] = 'APBRA-IMAGINARY'
        self.assertIn('Unknown agent role', c.task_errors(self.task, self.catalog, self.sources))

    def test_stale_card(self):
        self.task['agent_card_version'] = 'old'
        self.assertIn('Stale agent card version', c.task_errors(self.task, self.catalog, self.sources))

    def test_unknown_source(self):
        self.task['source_ids'].append('invented')
        self.assertIn('Unknown source reference', c.task_errors(self.task, self.catalog, self.sources))

    def test_main_branch_denied(self):
        self.task['branch'] = 'main'
        self.assertTrue(c.task_errors(self.task, self.catalog, self.sources))

    def test_proposed_implementation_denied(self):
        self.task.update(task_mode='IMPLEMENTATION', readiness='READY_FOR_IMPLEMENTATION', owner_acceptance='RECORDED')
        self.assertIn('Proposed sources cannot authorize implementation', c.task_errors(self.task, self.catalog, self.sources))

    def test_missing_owner_acceptance(self):
        self.task.update(task_mode='IMPLEMENTATION', readiness='READY_FOR_IMPLEMENTATION')
        self.assertIn('Implementation acceptance is not recorded', c.task_errors(self.task, self.catalog, self.sources))

    def test_inconsistent_readiness(self):
        self.task['readiness'] = 'READY_FOR_IMPLEMENTATION'
        self.assertIn('Implementation mode/readiness mismatch', c.task_errors(self.task, self.catalog, self.sources))

    def test_duplicate_roles(self):
        self.catalog['cards'][1] = copy.deepcopy(self.catalog['cards'][0])
        self.assertTrue(c.catalog_errors(self.catalog))

    def test_excessive_autonomy(self):
        self.catalog['cards'][0]['max_autonomy'] = 'A7'
        schema = c.load_json(ROOT / 'contracts/engineering/agent-catalog.schema.json')
        self.assertTrue(c.schema_errors(schema, self.catalog))

    def test_unknown_reviewer(self):
        self.catalog['cards'][0]['required_reviews'] = ['FICTITIOUS']
        self.assertTrue(c.catalog_errors(self.catalog))

    def test_path_traversal(self):
        for p in ['../secret', '/etc/passwd', 'docs/../../x', 'C:\\x', 'docs//x', './x']:
            with self.subTest(path=p):
                self.assertFalse(c.path_allowed(p, self.task, self.card))

    def test_restricted_path_overrides_allow(self):
        self.task['allowed_paths'] = ['*']
        self.assertFalse(c.path_allowed('apps/api/main.py', self.task, self.card))

    def test_root_pattern_not_nested(self):
        self.assertFalse(c.matches('apps/api/README.md', '*.md'))
        self.assertTrue(c.matches('README.md', '*.md'))

    def test_card_scope_intersection(self):
        self.card['allowed_paths'] = ['docs/**']
        self.assertFalse(c.path_allowed('scripts/new.py', self.task, self.card))
        self.assertTrue(c.path_allowed('docs/new.md', self.task, self.card))

    def test_external_schema_ref(self):
        with self.assertRaises(ValueError):
            c.schema_errors({'$ref': 'https://invalid.example/schema'}, {})

    def test_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.json'
            p.write_text('{"status": "safe", "status": "unsafe"}')
            with self.assertRaises(ValueError):
                c.load_json(p)

    def test_workflow_good(self):
        self.assertEqual(c.workflow_errors(self.workflow), [])

    def test_workflow_write_token(self):
        self.assertTrue(c.workflow_errors(self.workflow.replace('contents: read', 'contents: write')))

    def test_workflow_privileged_trigger(self):
        self.assertTrue(c.workflow_errors(self.workflow.replace('pull_request:', 'pull_request_target:')))

    def test_workflow_unpinned_action(self):
        self.assertTrue(c.workflow_errors(self.workflow.replace(c.ACTION_PINS['actions/checkout'], 'v6')))

    def test_workflow_persisted_credentials(self):
        self.assertTrue(c.workflow_errors(self.workflow.replace('persist-credentials: false', 'persist-credentials: true')))

    def test_workflow_invalid_yaml(self):
        self.assertTrue(c.workflow_errors("jobs: ["))

    def test_product_file_is_not_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'repo'
            shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns('artifacts', '__pycache__', '.git', '.venv'))
            p = dest / 'apps/api/main.py'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('print(1)')
            errors, _ = c.check(dest)
            self.assertTrue(any('outside safe bootstrap scope' in e for e in errors))

    def test_credential_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'repo'
            shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns('artifacts', '__pycache__', '.git', '.venv'))
            (dest / 'docs/unsafe.md').write_text('ghp_' + 'x' * 36)
            errors, _ = c.check(dest)
            self.assertTrue(any('credential pattern' in e for e in errors))

    def test_broken_local_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'repo'
            shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns('artifacts', '__pycache__', '.git', '.venv'))
            (dest / 'docs/broken.md').write_text('[bad](absent.md)')
            errors, _ = c.check(dest)
            self.assertTrue(any('Broken/unsafe local link' in e for e in errors))

    def test_missing_repository_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            errors, _ = c.check(Path(tmp))
            self.assertTrue(any('Missing required file' in e for e in errors))


class SchemaRetrievalTests(unittest.TestCase):
    def test_external_reference_keywords_never_retrieve(self):
        for keyword in ('$ref', '$dynamicRef'):
            for uri in ('https://example.invalid/schema', 'file:///synthetic-schema',
                        'relative-schema.json'):
                with self.subTest(keyword=keyword, uri=uri):
                    with patch('urllib.request.urlopen') as retrieve:
                        with self.assertRaises(ValueError):
                            c.schema_errors({keyword: uri}, {})
                        retrieve.assert_not_called()

    def test_nested_external_references_never_retrieve(self):
        for keyword in ('$ref', '$dynamicRef'):
            schema = {'properties': {'value': {'allOf': [
                {keyword: 'https://example.invalid/schema'}]}}}
            with self.subTest(keyword=keyword), patch('urllib.request.urlopen') as retrieve:
                with self.assertRaises(ValueError):
                    c.schema_errors(schema, {'value': 1})
                retrieve.assert_not_called()

    def test_valid_local_references(self):
        schemas = [
            {'$defs': {'number': {'type': 'integer'}}, '$ref': '#/$defs/number'},
            {'$defs': {'number': {'$dynamicAnchor': 'number', 'type': 'integer'}},
             '$dynamicRef': '#number'},
        ]
        with patch('urllib.request.urlopen') as retrieve:
            for schema in schemas:
                self.assertEqual(c.schema_errors(schema, 1), [])
                self.assertTrue(c.schema_errors(schema, 'invalid'))
            retrieve.assert_not_called()

    def test_explicit_registry_disables_unregistered_retrieval(self):
        # Exercise the configured registry independently of the keyword preflight.
        with patch.object(c, 'Registry', wraps=c.Registry) as registry:
            self.assertEqual(c.schema_errors({'type': 'integer'}, 1), [])
        registry.assert_called_once_with()
        configured = registry.call_args
        self.assertEqual(configured.args, ())
        validator = c.Draft202012Validator(
            {'$dynamicRef': 'https://example.invalid/schema'}, registry=c.Registry())
        with patch('urllib.request.urlopen') as retrieve:
            from referencing.exceptions import Unresolvable
            with self.assertRaises(Unresolvable):
                list(validator.iter_errors({}))
            retrieve.assert_not_called()


class PurePathMemoTests(unittest.TestCase):
    def test_exact_builtin_strings_reuse_only_pure_validation(self):
        from unittest.mock import Mock
        original = lambda value: value == 'docs/example.md'
        measured = Mock(side_effect=original)
        wrapped = c._memoized_path(measured)
        self.assertTrue(wrapped('docs/example.md'))
        self.assertTrue(wrapped(''.join(['docs/', 'example.md'])))
        self.assertFalse(wrapped('../unsafe'))
        self.assertFalse(wrapped('../unsafe'))
        self.assertEqual(measured.call_count, 2)

    def test_mutable_task_and_card_decisions_are_never_cached(self):
        task = {'allowed_paths': ['docs/**'], 'restricted_paths': []}
        card = {'allowed_paths': ['*']}
        self.assertTrue(c.path_allowed('docs/example.md', task, card))
        task['restricted_paths'].append('docs/**')
        self.assertFalse(c.path_allowed('docs/example.md', task, card))
        task['restricted_paths'].clear()
        card['allowed_paths'] = ['scripts/**']
        self.assertFalse(c.path_allowed('docs/example.md', task, card))

    def test_string_subclass_behavior_is_rechecked(self):
        class MutablePath(str):
            blocked = False
            def startswith(self, prefix):
                return self.blocked or super().startswith(prefix)
        value = MutablePath('docs/example.md')
        self.assertTrue(c.valid_path(value))
        value.blocked = True
        self.assertFalse(c.valid_path(value))
        self.assertTrue(c.valid_path(str(value)))

    def test_keyword_calls_preserve_original_result_and_errors(self):
        for value, expected in [('docs/example.md', True), ('../unsafe', False)]:
            self.assertEqual(c.valid_path(path=value), expected)
        original = next(cell.cell_contents for cell in c.valid_path.__closure__
                        if getattr(cell.cell_contents, '__name__', None) == 'valid_path')
        for args, kwargs in [((), {}), (('a', 'b'), {}), ((), {'unexpected': 'a'})]:
            with self.assertRaises(TypeError) as expected:
                original(*args, **kwargs)
            with self.assertRaises(TypeError) as actual:
                c.valid_path(*args, **kwargs)
            self.assertEqual(str(actual.exception), str(expected.exception))

    def test_non_string_inputs_preserve_original_results_and_exception_details(self):
        original = next(cell.cell_contents for cell in c.valid_path.__closure__
                        if getattr(cell.cell_contents, '__name__', None) == 'valid_path')
        for value in [None, [], {}, 0, False]:
            self.assertEqual(c.valid_path(value), original(value))
        for value in [['x'], {'x': 1}, 1, True]:
            try:
                original(value)
            except Exception as expected:
                with self.assertRaises(type(expected)) as actual:
                    c.valid_path(value)
                self.assertEqual(str(actual.exception), str(expected))

    def test_matches_observes_current_dependencies_after_path_cache_warms(self):
        self.assertTrue(c.matches('docs/example.md', 'docs/**'))
        with patch.object(c, 'valid_path', return_value=False):
            self.assertFalse(c.matches('docs/example.md', 'docs/**'))
        self.assertTrue(c.matches('README.md', '*.md'))
        with patch.object(c.fnmatch, 'fnmatchcase', return_value=False):
            self.assertFalse(c.matches('README.md', '*.md'))


class ReportContainmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.outside = Path(self.temp.name) / 'outside'
        self.outside.mkdir()

    def test_valid_report_and_existing_evidence_preserved(self):
        name = 'artifacts/reviews/result.json'
        c.write_report(self.root, name, {'status': 'PASS'})
        target = self.root / name
        self.assertEqual(json.loads(target.read_text()), {'status': 'PASS'})
        with self.assertRaises(ValueError):
            c.write_report(self.root, name, {'status': 'REPLACED'})
        self.assertEqual(json.loads(target.read_text()), {'status': 'PASS'})

    def test_symlinked_artifacts_root_has_no_external_side_effects(self):
        (self.root / 'artifacts').symlink_to(self.outside, target_is_directory=True)
        sentinel = self.outside / 'report.json'
        sentinel.write_text('original evidence')
        for name in ('artifacts/report.json', 'artifacts/new/report.json'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                c.write_report(self.root, name, {})
        self.assertEqual(sentinel.read_text(), 'original evidence')
        self.assertEqual(list(self.outside.iterdir()), [sentinel])

    def test_nested_escape_creates_no_external_directory(self):
        (self.root / 'artifacts').mkdir()
        (self.root / 'artifacts/link').symlink_to(self.outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            c.write_report(self.root, 'artifacts/link/new/report.json', {})
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_output_symlink_preserves_external_file(self):
        (self.root / 'artifacts').mkdir()
        target = self.outside / 'sentinel'
        target.write_text('original')
        (self.root / 'artifacts/report.json').symlink_to(target)
        with self.assertRaises(ValueError):
            c.write_report(self.root, 'artifacts/report.json', {})
        self.assertEqual(target.read_text(), 'original')

    def test_dangling_symlink_is_rejected_without_creation(self):
        (self.root / 'artifacts').symlink_to(self.outside / 'absent')
        with self.assertRaises(ValueError):
            c.write_report(self.root, 'artifacts/new/report.json', {})
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_traversal_is_rejected_before_creating_artifacts(self):
        for name in ('artifacts/../outside/report.json', 'artifacts/./report.json',
                     'artifacts//report.json', '/artifacts/report.json'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                c.write_report(self.root, name, {})
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_symlink_replacement_after_preflight_is_not_followed(self):
        artifacts = self.root / 'artifacts'
        artifacts.mkdir()
        original_open = os.open

        def replace_then_open(path, flags, *args, **kwargs):
            if path == 'artifacts':
                artifacts.rename(self.root / 'saved-artifacts')
                artifacts.symlink_to(self.outside, target_is_directory=True)
            return original_open(path, flags, *args, **kwargs)

        with patch.object(c.os, 'open', side_effect=replace_then_open):
            with self.assertRaises(OSError):
                c.write_report(self.root, 'artifacts/new/report.json', {})
        self.assertEqual(list(self.outside.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
