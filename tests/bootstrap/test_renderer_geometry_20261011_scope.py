"""Finite offline geometry authority; unchanged historical scope and size guards."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
TASK = 'tasks/APBRA-160-renderer-geometry-20261011.json'
SPEC = importlib.util.spec_from_file_location('geometry_oct11_bootstrap', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
h = c.g['bind'].__globals__


class RendererGeometryOct11ScopeTests(unittest.TestCase):
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

    def test_exact_sources_paths_window_and_separate_stages(self):
        task = json.loads((ROOT / TASK).read_text())
        self.assertEqual(len(h['G']), 4)
        self.assertEqual(len(h['P']), 7)
        self.assertEqual(set(task['allowed_paths']), h['P'])
        self.assertEqual(task['base_commit'], h['BASE'])
        self.assertEqual(h['CUTOFF'], '2026-10-11T20:19:10Z')
        self.assertEqual(h['digest'](task), h['TASK_SHA'])
        self.assertEqual(self.check(ROOT), [])
        self.assertEqual(self.check(ROOT, h['P'], h['B']), [])

    def test_each_omission_and_product_governance_mix_rejected(self):
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

    def test_identity_base_branch_and_literal_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            original = json.loads((root / TASK).read_text())
            mutations = {'base_commit': 'a' * 40, 'branch': h['R'], 'assigned_agent': 'APBRA-DEV-FE',
                         'actual_authenticated_actor': 'Invented reviewer', 'human_initiator': 'Other owner',
                         'agent_card_version': '9.9', 'task_id': 'APBRA-154'}
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
                with patch.dict(h, {'TASK_SHA': h['digest'](changed)}):
                    self.assertTrue(self.check(root))

    def test_cutoff_survives_recomputed_task_and_section_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            task = json.loads((root / TASK).read_text())
            task['requirements'][0] = task['requirements'][0].replace(h['CUTOFF'], '2026-10-12T20:19:10Z')
            (root / TASK).write_text(json.dumps(task))
            gates = {**h['GATES'], 'requirements': h['digest'](task['requirements'])}
            with patch.dict(h, {'TASK_SHA': h['digest'](task), 'GATES': gates}):
                self.assertTrue(self.check(root))

    def test_source_and_historical_task_preservation(self):
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
            sourcepath.write_text(json.dumps(original))
            path = root / 'tasks/APBRA-160-demo-ux.json'
            historical = json.loads(path.read_text())
            historical['objective'] += ' broader authority'
            path.write_text(json.dumps(historical))
            self.assertTrue(self.check(root))

    def test_missing_malformed_task_and_missing_helper_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            path = root / TASK
            original = path.read_text()
            path.unlink()
            self.assertTrue(self.check(root))
            path.write_text('{}')
            self.assertTrue(self.check(root))
            path.write_text(original)
            (root / 'scripts/check_renderer_geometry_20261011.py').unlink()
            self.assertTrue(self.check(root))
            result = subprocess.run([__import__('sys').executable, str(root / 'scripts/check_bootstrap.py')],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_broken_fixed_helper_and_historical_whitespace_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            path = root / 'tasks/APBRA-160-demo-ux.json'
            path.write_text(path.read_text() + '\n')
            self.assertTrue(self.check(root))
            helper = root / 'scripts/check_renderer_geometry_20261011.py'
            helper.write_text('raise RuntimeError("synthetic broken fixed helper")\n')
            result = subprocess.run([__import__('sys').executable, str(root / 'scripts/check_bootstrap.py')],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_historical_declarations_AST_and_checker_size_unchanged(self):
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
        self.assertLessEqual(checker.stat().st_size, 262144)

    def test_unrelated_prior_branches_and_restricted_paths_do_not_gain_scope(self):
        for path in ['apps/api/src/apbra_api/config.py', 'apps/api/src/apbra_api/generation.py',
                     'apps/web/src/foundry.ts', 'docs/source-register.json', 'apps/api/alembic/env.py']:
            with self.subTest(path=path):
                self.assertTrue(self.check(ROOT, {path}, h['B']))
        self.assertTrue(self.check(ROOT, h['P'], c.DEMO_UX_BRANCH))


if __name__ == '__main__':
    unittest.main()
