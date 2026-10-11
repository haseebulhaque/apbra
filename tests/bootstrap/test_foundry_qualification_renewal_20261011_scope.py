"""Exact combined Oct11 renewal and unchanged historical authority regressions."""
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
BASE = '6b8c1df8371fd836f1940cdb5a34d48933aeda93'
TASK = 'tasks/APBRA-160-foundry-qualification-renewal-20261011.json'
SPEC = importlib.util.spec_from_file_location('oct11_bootstrap', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
h = c.r['bind11'].__globals__


class FoundryQualificationOct11ScopeTests(unittest.TestCase):
    def copy(self, root):
        for name in {p.relative_to(ROOT).as_posix() for p in c.repo_files(ROOT)} | h['N_PATHS']:
            if (ROOT / name).is_file():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)

    def check(self, root, paths=None, branch=None):
        return c.check(root, active_task_id='APBRA-160', active_branch=branch or h['N_BRANCH'],
                       changed_paths=h['N_PATHS'] if paths is None else paths)[0]

    def test_exact_pinned_six_paths_and_window(self):
        task = json.loads((ROOT / TASK).read_text())
        self.assertEqual(task['base_commit'], BASE)
        self.assertEqual(task['branch'], h['N_BRANCH'])
        self.assertEqual(len(task['allowed_paths']), 6)
        self.assertEqual(set(task['allowed_paths']), h['N_PATHS'])
        self.assertEqual(h['N_CEILING'], '2026-10-11T12:24:46Z')
        self.assertEqual(h['digest'](task), h['N_TASK_SHA'])
        for section, expected in h['N_GATES'].items():
            self.assertEqual(h['digest'](task[section]), expected)
        self.assertEqual(self.check(ROOT), [])

    def test_omission_extra_duplicate_wildcard_wrong_branch_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            for path in h['N_PATHS']:
                self.assertTrue(self.check(root, h['N_PATHS'] - {path}))
            for path in ['apps/api/src/apbra_api/main.py', 'apps/api/uv.lock', '.env',
                         'apps/web/src/App.tsx', 'tasks/APBRA-160-foundry-qualification.json']:
                self.assertTrue(self.check(root, h['N_PATHS'] | {path}))
            self.assertTrue(self.check(root, branch=h['B']))
            task = json.loads((root / TASK).read_text())
            for paths in [task['allowed_paths'] + [task['allowed_paths'][0]],
                          task['allowed_paths'] + ['apps/api/**']]:
                changed = {**task, 'allowed_paths': paths}
                (root / TASK).write_text(json.dumps(changed))
                with patch.dict(h, {'N_TASK_SHA': h['digest'](changed)}):
                    self.assertTrue(self.check(root))

    def test_each_protected_section_remains_independently_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            task = json.loads((root / TASK).read_text())
            for section in h['N_GATES']:
                changed = copy.deepcopy(task)
                value = changed[section]
                changed[section] = value + ['Broader authority'] if isinstance(value, list) else 'PENDING'
                (root / TASK).write_text(json.dumps(changed))
                with patch.dict(h, {'N_TASK_SHA': h['digest'](changed)}):
                    self.assertTrue(self.check(root))

    def test_ceiling_pinned_even_when_task_and_section_hashes_are_recomputed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            task = json.loads((root / TASK).read_text())
            for ceiling in ['', '2026-10-10T02:09:00Z', '2026-10-11T12:24:47Z']:
                changed = copy.deepcopy(task)
                changed['requirements'][0] = changed['requirements'][0].replace(h['N_CEILING'], ceiling)
                (root / TASK).write_text(json.dumps(changed))
                with patch.dict(h, {'N_TASK_SHA': h['digest'](changed), 'N_GATES': {
                        **h['N_GATES'], 'requirements': h['digest'](changed['requirements'])}}):
                    self.assertTrue(any('Oct11 renewal ceiling differs' in e for e in self.check(root)))

    def test_missing_malformed_or_rewritten_history_never_grants_new_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            for name in [TASK, 'tasks/APBRA-160-foundry-qualification.json',
                         'tasks/APBRA-160-foundry-qualification-renewal.json']:
                data = (root / name).read_bytes()
                (root / name).unlink()
                self.assertTrue(self.check(root))
                (root / name).write_text('{')
                self.assertTrue(self.check(root))
                changed = json.loads(data)
                changed['objective'] += ' broadened'
                (root / name).write_text(json.dumps(changed))
                self.assertTrue(self.check(root))
                (root / name).write_bytes(data)

    def test_base_actor_source_and_identity_rejected_under_recomputed_task_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            task = json.loads((root / TASK).read_text())
            for field, value in [('base_commit', '0' * 40), ('task_id', 'APBRA-173'),
                                 ('assigned_agent', 'APBRA-DEV-BE'), ('branch', h['B'])]:
                changed = {**task, field: value}
                (root / TASK).write_text(json.dumps(changed))
                with patch.dict(h, {'N_TASK_SHA': h['digest'](changed)}):
                    self.assertTrue(self.check(root))
            (root / TASK).write_text(json.dumps(task))
            sources = json.loads((root / 'docs/source-register.json').read_text())
            sources['sources'][0]['title'] = 'rewritten'
            (root / 'docs/source-register.json').write_text(json.dumps(sources))
            self.assertTrue(self.check(root))

    def test_historical_constants_functions_and_files_preserved(self):
        for filename in ['scripts/check_bootstrap.py', 'scripts/check_foundry_qualification_renewal.py']:
            old = ast.parse(subprocess.check_output(['git', 'show', BASE + ':' + filename], cwd=ROOT))
            new = ast.parse((ROOT / filename).read_text())
            declarations = {n.targets[0].id: n for n in new.body
                            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
            functions = {n.name: n for n in new.body if isinstance(n, ast.FunctionDef)}
            for node in old.body:
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                    self.assertEqual(ast.dump(node), ast.dump(declarations[node.targets[0].id]))
                if isinstance(node, ast.FunctionDef) and node.name != 'check':
                    self.assertEqual(ast.dump(node), ast.dump(functions[node.name]))
        for filename in ['tasks/APBRA-160-foundry-qualification.json',
                         'tasks/APBRA-160-foundry-qualification-renewal.json', 'docs/source-register.json']:
            self.assertEqual((ROOT / filename).read_bytes(), subprocess.check_output(
                ['git', 'show', BASE + ':' + filename], cwd=ROOT))
        self.assertLessEqual((ROOT / 'scripts/check_bootstrap.py').stat().st_size, 262144)

    def test_old_renewal_error_parity_on_actual_base_checker(self):
        with tempfile.TemporaryDirectory() as directory:
            outer = Path(directory)
            for name in ['check_bootstrap.py', 'check_foundry_qualification_renewal.py']:
                (outer / name).write_bytes(subprocess.check_output(
                    ['git', 'show', BASE + ':scripts/' + name], cwd=ROOT))
            spec = importlib.util.spec_from_file_location('old_oct11_checker', outer / 'check_bootstrap.py')
            old = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(old)
            roots = [outer / 'old', outer / 'new']
            for root in roots:
                root.mkdir()
                self.copy(root)
            original = json.loads((ROOT / 'tasks/APBRA-160-foundry-qualification-renewal.json').read_text())
            for mutation in [None, 'paths', 'base', 'gate']:
                changed = copy.deepcopy(original)
                if mutation == 'paths':
                    changed['allowed_paths'].append('apps/api/src/apbra_api/main.py')
                elif mutation == 'base':
                    changed['base_commit'] = '0' * 40
                elif mutation == 'gate':
                    changed['effective_release'] += ' broadened'
                for root in roots:
                    (root / 'tasks/APBRA-160-foundry-qualification-renewal.json').write_text(json.dumps(changed))
                for branch, paths in [(h['B'], h['P']), (h['R'], h['G'])]:
                    kwargs = {'active_task_id': 'APBRA-160', 'active_branch': branch, 'changed_paths': paths}
                    before = old.check(roots[0], **kwargs)[0]
                    after = c.check(roots[1], **kwargs)[0]
                    self.assertEqual(after, before)
                    self.assertEqual(bool(before), mutation is not None)


    def test_original_branch_errors_preserved_with_dated_task_present(self):
        with tempfile.TemporaryDirectory() as directory:
            outer = Path(directory)
            for name in ['check_bootstrap.py', 'check_foundry_qualification_renewal.py']:
                (outer / name).write_bytes(subprocess.check_output(
                    ['git', 'show', BASE + ':scripts/' + name], cwd=ROOT))
            spec = importlib.util.spec_from_file_location('original_oct11_checker', outer / 'check_bootstrap.py')
            old = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(old)
            roots = [outer / 'old', outer / 'new']
            filename = 'tasks/APBRA-160-foundry-qualification.json'
            for root in roots:
                root.mkdir()
                self.copy(root)
                (root / 'tasks/APBRA-160-foundry-qualification-renewal.json').unlink()
            accepted = json.loads((ROOT / filename).read_text())
            for mutation in [None, 'scope', 'identity', 'gate', 'sources']:
                changed = copy.deepcopy(accepted)
                if mutation == 'scope':
                    changed['allowed_paths'].append('apps/api/src/apbra_api/unregistered.py')
                elif mutation == 'identity':
                    changed['base_commit'] = '0' * 40
                elif mutation == 'gate':
                    changed['effective_release'] += ' broader authority'
                elif mutation == 'sources':
                    changed['source_ids'] = ['apbra-160-current-six-stage-direction']
                for root in roots:
                    (root / filename).write_text(json.dumps(changed))
                kwargs = {'active_task_id': 'APBRA-160',
                          'active_branch': c.FOUNDRY_QUALIFICATION_BRANCH,
                          'changed_paths': c.FOUNDRY_QUALIFICATION_PATHS}
                before, after = old.check(roots[0], **kwargs)[0], c.check(roots[1], **kwargs)[0]
                self.assertEqual(after, before)
                self.assertEqual(bool(before), mutation is not None)

    def test_mismatched_history_blocks_new_stage_even_after_old_task_pin_recomputed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            filename = 'tasks/APBRA-160-foundry-qualification.json'
            changed = json.loads((root / filename).read_text())
            changed['objective'] += ' rewritten history'
            (root / filename).write_text(json.dumps(changed))
            with patch.object(c, 'FOUNDRY_QUALIFICATION_TASK_SHA256', h['digest'](changed)), \
                    patch.dict(h, {'ORIGINAL_TASK_SHA': h['digest'](changed)}):
                errors = self.check(root)
            self.assertIn('Unknown or invalid active task authority: APBRA-160', errors)
            self.assertIn('File outside active task scope: apps/api/src/apbra_api/config.py', errors)
            self.assertIn('File outside active task scope: apps/api/tests/test_model_provider.py', errors)


if __name__ == '__main__':
    unittest.main()
