"""Outcome-bounded AI layout registration; synthetic governance failures only."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
TASK = 'tasks/APBRA-160-ai-authored-layout-20261012.json'
SPEC = importlib.util.spec_from_file_location('ai_layout_bootstrap', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
h = c.a['bind'].__globals__


class AIAuthoredLayoutScopeTests(unittest.TestCase):
    def copy(self, root):
        for name in {p.relative_to(ROOT).as_posix() for p in c.repo_files(ROOT)} | h['G']:
            path = ROOT / name
            if path.is_file():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)

    def check(self, root, paths=None, branch=None):
        return c.check(root, active_task_id='APBRA-160', active_branch=branch or h['R'],
                       changed_paths=h['G'] if paths is None else paths)[0]

    def test_exact_registration_and_28_product_paths(self):
        task = json.loads((ROOT / TASK).read_text())
        self.assertEqual(len(h['G']), 4)
        self.assertEqual(len(h['P']), 28)
        self.assertEqual(len(task['allowed_paths']), 28)
        self.assertEqual(set(task['allowed_paths']), h['P'])
        self.assertEqual(task['base_commit'], h['BASE'])
        self.assertEqual(h['digest'](task), h['TASK_SHA'])
        self.assertEqual(self.check(ROOT), [])
        self.assertEqual(self.check(ROOT, h['P'], h['B']), [])
        self.assertNotIn('CUTOFF', h)
        self.assertEqual(task['requirements'][0], h['AUTHORITY'])

    def test_each_registration_omission_and_stage_mix_fail_closed(self):
        for path in h['G']:
            with self.subTest(omitted=path):
                self.assertTrue(self.check(ROOT, h['G'] - {path}))
        for path in h['P'] | {'.env', '.github/workflows/bootstrap.yml', 'apps/api/uv.lock'}:
            with self.subTest(extra=path):
                self.assertTrue(self.check(ROOT, h['G'] | {path}))
        for path in h['G']:
            with self.subTest(product_mix=path):
                self.assertTrue(self.check(ROOT, h['P'] | {path}, h['B']))
        self.assertTrue(self.check(ROOT, h['G'], h['B']))
        self.assertTrue(self.check(ROOT, h['P'], h['R']))
        self.assertTrue(h['errors']('APBRA-160', h['B'], set()))
        self.assertTrue(self.check(ROOT, h['P'], 'agent/APBRA-DEVOPS/APBRA-160-unknown'))

    def test_protected_sections_survive_recomputed_outer_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            original = json.loads((root / TASK).read_text())
            for field in h['GATES']:
                changed = copy.deepcopy(original)
                value = changed[field]
                changed[field] = value + ['Broader authority'] if isinstance(value, list) else 'PENDING'
                (root / TASK).write_text(json.dumps(changed))
                with self.subTest(field=field), patch.dict(h, {'TASK_SHA': h['digest'](changed)}):
                    self.assertTrue(self.check(root))

    def test_owner_outcome_authority_survives_recomputed_task_and_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            task = json.loads((root / TASK).read_text())
            for text in ['Owner authority pending', h['AUTHORITY'] + ' New future cutoff2026-10-13.',
                         h['AUTHORITY'].replace('23:12:19Z', '23:12:20Z')]:
                changed = copy.deepcopy(task)
                changed['requirements'][0] = text
                (root / TASK).write_text(json.dumps(changed))
                gates = {**h['GATES'], 'requirements': h['digest'](changed['requirements'])}
                with self.subTest(text=text), patch.dict(h, {'TASK_SHA': h['digest'](changed), 'GATES': gates}):
                    self.assertTrue(self.check(root))

    def test_identity_card_base_branch_literal_scope_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            original = json.loads((root / TASK).read_text())
            mutations = {'base_commit': 'a' * 40, 'branch': h['R'], 'assigned_agent': 'APBRA-DEV-FE',
                         'actual_authenticated_actor': 'Invented actor', 'human_initiator': 'Other owner',
                         'human_owner': 'Other owner', 'agent_card_version': '9.9', 'task_id': 'APBRA-154'}
            for field, value in mutations.items():
                changed = {**original, field: value}
                (root / TASK).write_text(json.dumps(changed))
                with self.subTest(field=field), patch.dict(h, {'TASK_SHA': h['digest'](changed)}):
                    self.assertTrue(self.check(root))
            for value in [original['allowed_paths'][:-1], original['allowed_paths'] + ['apps/api/**'],
                          original['allowed_paths'] + [original['allowed_paths'][0]],
                          original['allowed_paths'] + ['apps/api/src/apbra_api/api.py']]:
                changed = {**original, 'allowed_paths': value}
                (root / TASK).write_text(json.dumps(changed))
                with self.subTest(paths=value), patch.dict(h, {'TASK_SHA': h['digest'](changed)}):
                    self.assertTrue(self.check(root))

    def test_accepted_source_row_missing_duplicate_and_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            sourcepath = root / 'docs/source-register.json'
            original = json.loads(sourcepath.read_text())
            for operation in ['mutation', 'duplicate', 'missing']:
                sources = copy.deepcopy(original)
                index = next(i for i, row in enumerate(sources['sources']) if row['id'] == h['SOURCES'][0][0])
                if operation == 'mutation':
                    sources['sources'][index]['version'] += 1
                elif operation == 'duplicate':
                    sources['sources'].append(copy.deepcopy(sources['sources'][index]))
                else:
                    sources['sources'].pop(index)
                sourcepath.write_text(json.dumps(sources))
                with self.subTest(operation=operation), patch.dict(h, {'SOURCES_SHA': h['digest'](sources)}):
                    self.assertTrue(self.check(root))

    def test_all_49_historical_tasks_and_84_source_rows_byte_exact(self):
        self.assertEqual(len(h['HISTORY']), 49)
        self.assertEqual(len(json.loads((ROOT / 'docs/source-register.json').read_text())['sources']), 84)
        for name in h['HISTORY']:
            expected = subprocess.check_output(['git', 'show', h['BASE'] + ':tasks/' + name], cwd=ROOT)
            self.assertEqual((ROOT / 'tasks' / name).read_bytes(), expected, name)
        expected = subprocess.check_output(['git', 'show', h['BASE'] + ':docs/source-register.json'], cwd=ROOT)
        self.assertEqual((ROOT / 'docs/source-register.json').read_bytes(), expected)
        self.assertEqual(hashlib.sha256(expected).hexdigest(), h['SOURCE_FILE_SHA'])
        self.assertEqual(c.g['CUTOFF'], '2026-10-11T20:19:10Z')

    def test_historical_task_whitespace_missing_and_source_whitespace_withdraw_new_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            history = root / 'tasks/APBRA-160-renderer-geometry-20261011.json'
            original = history.read_bytes()
            history.write_bytes(original + b'\n')
            self.assertTrue(self.check(root))
            history.unlink()
            self.assertTrue(self.check(root))
            history.write_bytes(original)
            sourcepath = root / 'docs/source-register.json'
            sourcepath.write_bytes(sourcepath.read_bytes() + b'\n')
            self.assertTrue(self.check(root))

    def test_missing_malformed_task_and_missing_or_broken_helper_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            path = root / TASK
            original = path.read_text()
            path.unlink()
            self.assertTrue(self.check(root))
            for value in ['{}', '{malformed']:
                path.write_text(value)
                self.assertTrue(self.check(root))
            path.write_text(original)
            helper = root / 'scripts/check_ai_authored_layout_20261012.py'
            helper.unlink()
            self.assertTrue(self.check(root))
            helper.write_text('raise RuntimeError("synthetic broken fixed helper")\n')
            result = subprocess.run([sys.executable, str(root / 'scripts/check_bootstrap.py')],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_old_declarations_functions_helpers_and_size_unchanged(self):
        old = ast.parse(subprocess.check_output(['git', 'show', h['BASE'] + ':scripts/check_bootstrap.py'], cwd=ROOT))
        checker = ROOT / 'scripts/check_bootstrap.py'
        new = ast.parse(checker.read_text())
        declarations = {node.targets[0].id: node for node in new.body
                        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
        functions = {node.name: node for node in new.body if isinstance(node, ast.FunctionDef)}
        for node in old.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                self.assertEqual(ast.dump(node), ast.dump(declarations[node.targets[0].id]))
            elif isinstance(node, ast.FunctionDef) and node.name != 'check':
                self.assertEqual(ast.dump(node), ast.dump(functions[node.name]))
        for name in ['scripts/check_renderer_geometry_20261011.py', 'scripts/check_foundry_qualification_renewal.py']:
            expected = subprocess.check_output(['git', 'show', h['BASE'] + ':' + name], cwd=ROOT)
            self.assertEqual((ROOT / name).read_bytes(), expected)
        self.assertLessEqual(checker.stat().st_size, 262144)

    def test_unrelated_historical_branches_and_restricted_paths_gain_no_scope(self):
        for name in ['apps/api/src/apbra_api/api.py', 'apps/api/uv.lock', '.github/workflows/bootstrap.yml',
                     'docs/source-register.json', 'apps/api/alembic/env.py', 'compose.yaml', '.env']:
            with self.subTest(path=name):
                self.assertTrue(self.check(ROOT, {name}, h['B']))
        self.assertTrue(self.check(ROOT, h['P'], c.g['B']))
        self.assertTrue(self.check(ROOT, h['G'], c.g['R']))

    def test_geometry_contract_is_only_documented_representation_not_business_heuristics(self):
        task = json.loads((ROOT / TASK).read_text())
        self.assertIn('z/tabOrder/angle', task['requirements'][1])
        self.assertIn('optional JSONnumbers', task['requirements'][1])
        self.assertIn('No APBRA completeness requirement', task['requirements'][1])
        self.assertIn('fractional/negative/off-canvas/overlapping', task['verification_required'][1])
        self.assertIn('Desktop behavior remains UNTESTED', task['acceptance_criteria'][1])
        self.assertIn('apps/web/src/aiGeometry.ts', h['P'])
        self.assertIn('apps/web/knowledge/report-design-format-contract-v2.md', h['P'])


class PureSchemaErrorMemoTests(unittest.TestCase):
    def setUp(self):
        self.original = c.schema_errors.__wrapped__
        self.memo = c.a['ContentMemo'](self.original)

    def parity(self, schema, value, **kwargs):
        def outcome(fn):
            try:
                return ('result', fn(schema, value, **kwargs))
            except Exception as exc:
                return ('exception', type(exc), str(exc))
        expected = outcome(self.original)
        self.assertEqual(outcome(self.memo), expected)
        self.assertEqual(outcome(self.memo), expected)
        return expected

    def test_01_valid_plain_json_cache_hit(self):
        self.parity({'type': 'integer'}, 1)
        self.assertEqual(self.memo.original_calls, 1)
        self.assertEqual(self.memo.hits, 1)

    def test_02_invalid_plain_json_errors_cache_hit(self):
        self.parity({'type': 'integer'}, 'wrong')
        self.assertEqual(self.memo.original_calls, 1)
        self.assertEqual(self.memo.hits, 1)

    def test_03_same_object_value_mutation_changes_full_key(self):
        schema = {'type': 'object', 'required': ['count']}
        value = {'count': 1}
        self.parity(schema, value)
        del value['count']
        self.assertTrue(self.parity(schema, value)[1])
        self.assertEqual(self.memo.misses, 2)

    def test_04_same_schema_object_mutation_changes_full_key(self):
        schema = {'type': 'number', 'minimum': 1}
        self.assertTrue(self.parity(schema, 0)[1])
        schema['minimum'] = 0
        self.assertEqual(self.parity(schema, 0), ('result', []))
        self.assertEqual(self.memo.misses, 2)

    def test_05_returned_error_list_is_caller_owned(self):
        expected = self.original({'type': 'integer'}, 'wrong')
        errors = self.memo({'type': 'integer'}, 'wrong')
        errors.clear()
        self.assertEqual(self.memo({'type': 'integer'}, 'wrong'), expected)
        errors = self.memo({'type': 'integer'}, 'wrong')
        errors.append('caller tamper')
        self.assertEqual(self.memo({'type': 'integer'}, 'wrong'), expected)

    def test_06_invalid_schema_exception_not_cached(self):
        self.assertEqual(self.parity({'type': 'unsupported-type'}, 1)[0], 'exception')
        self.assertEqual(self.memo.original_calls, 2)
        self.assertEqual(len(self.memo.cache), 0)

    def test_07_external_reference_exception_not_cached(self):
        result = self.parity({'$ref': 'https://invalid.example/schema'}, 1)
        self.assertEqual(result[0], 'exception')
        self.assertEqual(result[1], ValueError)
        self.assertEqual(self.memo.original_calls, 2)
        self.assertEqual(len(self.memo.cache), 0)

    def test_08_error_order_and_full_dict_representation_preserved(self):
        self.parity({'required': ['second', 'first']}, {})
        schema = {'enum': [None]}
        self.parity(schema, {'b': 2, 'a': 1})
        self.parity(schema, {'a': 1, 'b': 2})
        self.assertEqual(self.memo.misses, 3)

    def test_09_keyword_schema_and_value_unchanged(self):
        schema = {'type': 'integer'}
        expected = self.original(schema=schema, value='wrong')
        self.assertEqual(self.memo(schema=schema, value='wrong'), expected)
        self.assertEqual(self.memo(schema, 'wrong'), expected)
        self.assertEqual(self.memo.hits, 1)

    def test_10_unsupported_path_kwargs_fall_back_unchanged(self):
        self.assertEqual(self.parity({}, 1, path='synthetic')[0], 'exception')
        self.assertEqual(self.memo.fallbacks, 2)
        self.assertEqual(len(self.memo.cache), 0)

    def test_11_nan_falls_back_without_caching(self):
        self.parity({'type': 'number'}, float('nan'))
        self.assertEqual(self.memo.fallbacks, 2)
        self.assertEqual(len(self.memo.cache), 0)

    def test_12_positive_and_negative_infinity_fall_back(self):
        for value in [float('inf'), float('-inf')]:
            self.parity({'type': 'number'}, value)
        self.assertEqual(self.memo.fallbacks, 4)
        self.assertEqual(len(self.memo.cache), 0)

    def test_13_non_json_tuple_and_set_fall_back(self):
        for value in [(1, 2), {1, 2}]:
            self.parity({'type': 'array'}, value)
        self.assertEqual(self.memo.fallbacks, 4)
        self.assertEqual(len(self.memo.cache), 0)

    def test_14_custom_object_and_container_subclass_fall_back(self):
        class CustomDict(dict):
            pass
        for value in [object(), CustomDict({'count': 1})]:
            self.parity({}, value)
        self.assertEqual(self.memo.fallbacks, 4)
        self.assertEqual(len(self.memo.cache), 0)

    def test_15_non_string_dictionary_key_falls_back(self):
        self.parity({}, {1: 'synthetic'})
        self.assertEqual(self.memo.fallbacks, 2)
        self.assertEqual(len(self.memo.cache), 0)

    def test_16_cyclic_and_deep_value_fall_back_original_behavior(self):
        cyclic = []
        cyclic.append(cyclic)
        self.parity({}, cyclic)
        deep = 1
        for _ in range(1200):
            deep = [deep]
        self.parity({}, deep)
        self.assertEqual(self.memo.fallbacks, 4)
        self.assertEqual(len(self.memo.cache), 0)

    def test_17_entry_bound_and_eviction_preserve_errors(self):
        memo = c.a['ContentMemo'](self.original, max_entries=2)
        for value in ['first', 'second', 'third', 'first']:
            self.assertEqual(memo({'type': 'integer'}, value), self.original({'type': 'integer'}, value))
        self.assertEqual(len(memo.cache), 2)
        self.assertEqual(memo.evictions, 2)

    def test_18_large_key_falls_back_without_validation_limit(self):
        memo = c.a['ContentMemo'](self.original, max_key_bytes=32)
        value = 'synthetic' * 50
        self.assertEqual(memo({}, value), self.original({}, value))
        self.assertEqual(memo.fallbacks, 1)
        self.assertEqual(len(memo.cache), 0)

    def test_19_large_error_result_is_returned_without_caching(self):
        memo = c.a['ContentMemo'](self.original, max_result_bytes=1)
        expected = self.original({'type': 'integer'}, 'wrong')
        self.assertEqual(memo({'type': 'integer'}, 'wrong'), expected)
        self.assertEqual(memo({'type': 'integer'}, 'wrong'), expected)
        self.assertEqual(memo.original_calls, 2)
        self.assertEqual(len(memo.cache), 0)

    def test_20_supplied_documents_not_mutated(self):
        schema = {'type': 'object', 'properties': {'count': {'type': 'integer'}}, 'required': ['count']}
        value = {'count': 'wrong'}
        before = copy.deepcopy((schema, value))
        self.parity(schema, value)
        self.assertEqual((schema, value), before)

    def compare_check(self, root, branch, paths):
        with patch.object(c, 'schema_errors', self.original):
            expected = c.check(root, active_task_id='APBRA-160', active_branch=branch, changed_paths=paths)[0]
        with patch.object(c, 'schema_errors', self.memo):
            actual = c.check(root, active_task_id='APBRA-160', active_branch=branch, changed_paths=paths)[0]
        self.assertEqual(actual, expected)
        return actual

    def test_21_old_and_new_branch_admission_errors_match_without_memo(self):
        for branch, paths in [(c.g['R'], c.g['G']), (c.g['B'], c.g['P']),
                              (h['R'], h['G']), (h['B'], h['P']),
                              (c.g['B'], h['P']), (h['R'], h['G'] | {'.env'})]:
            with self.subTest(branch=branch, paths=paths):
                self.compare_check(ROOT, branch, paths)

    def test_22_reloaded_copied_root_and_task_mutations_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            AIAuthoredLayoutScopeTests().copy(root)
            self.assertEqual(self.compare_check(root, h['R'], h['G']), [])
            path = root / TASK
            task = json.loads(path.read_text())
            for field, value in [('allowed_paths', task['allowed_paths'] + ['apps/api/**']),
                                 ('actual_authenticated_actor', 'Invented actor')]:
                path.write_text(json.dumps({**task, field: value}))
                self.assertTrue(self.compare_check(root, h['R'], h['G']))

    def test_23_raw_history_and_source_byte_changes_remain_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            AIAuthoredLayoutScopeTests().copy(root)
            self.assertEqual(self.compare_check(root, h['R'], h['G']), [])
            for name in ['tasks/APBRA-160-renderer-geometry-20261011.json', 'docs/source-register.json']:
                path = root / name
                original = path.read_bytes()
                hits = self.memo.hits
                path.write_bytes(original + b'\n')
                self.assertTrue(self.compare_check(root, h['R'], h['G']))
                self.assertGreater(self.memo.hits, hits)
                path.write_bytes(original)
                self.assertEqual(self.compare_check(root, h['R'], h['G']), [])


if __name__ == '__main__':
    unittest.main()
