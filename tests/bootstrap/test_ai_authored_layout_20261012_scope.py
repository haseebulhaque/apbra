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


if __name__ == '__main__':
    unittest.main()
