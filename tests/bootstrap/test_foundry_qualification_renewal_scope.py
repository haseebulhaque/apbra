"""Additive finite renewal, exact stages and preserved historical checker behavior."""
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
TASK = 'tasks/APBRA-160-foundry-qualification-renewal.json'
ORIGINAL = 'tasks/APBRA-160-foundry-qualification.json'
BASE = 'b3f177a89f8831b8a4f8857198728878fa0722f6'
SPEC = importlib.util.spec_from_file_location('bootstrap_renewal', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
h = c.r['bind'].__globals__


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class FoundryQualificationRenewalScopeTests(unittest.TestCase):
    def setUp(self):
        self.task = json.loads((ROOT / TASK).read_text())

    def copy_repository(self, root):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)} | h['G']
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if (ROOT / name).is_file():
                shutil.copyfile(ROOT / name, target)

    def check(self, root, paths, branch=None):
        return c.check(root, active_task_id='APBRA-160', active_branch=branch or h['B'],
                       changed_paths=set(paths))[0]

    def test_new_pins_exact_cutoff_and_separate_scopes(self):
        self.assertEqual(h['CEILING'], '2026-10-10T02:09:00Z')
        self.assertEqual(h['P'], {'apps/api/src/apbra_api/config.py', 'apps/api/tests/test_model_provider.py'})
        self.assertEqual(h['G'], {TASK, 'scripts/check_bootstrap.py',
                                 'scripts/check_foundry_qualification_renewal.py',
                                 'tests/bootstrap/test_foundry_qualification_renewal_scope.py'})
        self.assertEqual(set(self.task['allowed_paths']), h['P'])
        self.assertEqual(len(self.task['allowed_paths']), 2)
        self.assertEqual(self.task['base_commit'], h['BASE'])
        self.assertEqual(self.task['branch'], h['B'])
        self.assertEqual(digest(self.task), h['TASK_SHA'])
        for section, expected in h['GATES'].items():
            self.assertEqual(digest(self.task[section]), expected)
        self.assertEqual(digest(json.loads((ROOT / ORIGINAL).read_text())), h['ORIGINAL_TASK_SHA'])

    def test_exact_governance_stage_and_product_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, h['G'], h['R']), [])
            self.assertEqual(self.check(root, h['P']), [])
            for omitted in h['G']:
                self.assertTrue(self.check(root, h['G'] - {omitted}, h['R']))
            for omitted in h['P']:
                self.assertTrue(self.check(root, h['P'] - {omitted}))
            for extra in ('apps/api/src/apbra_api/main.py', 'apps/api/src/apbra_api/model_provider.py',
                          'apps/api/uv.lock', '.env', '.github/workflows/bootstrap.yml'):
                self.assertTrue(self.check(root, h['G'] | {extra}, h['R']))
                self.assertTrue(self.check(root, h['P'] | {extra}))
            self.assertTrue(self.check(root, h['P'], 'agent/APBRA-DEVOPS/APBRA-160-unregistered-renewal'))
            self.assertTrue(self.check(root, h['G']))

    def test_scope_cannot_be_broadened_even_with_recomputed_whole_task_pin(self):
        original = self.task['allowed_paths']
        mutations = [original[:1], original + [original[0]], original + ['apps/api/src/**'],
                     original + ['apps/api/src/apbra_api/main.py'],
                     original + ['apps/api/src/apbra_api/model_provider.py']]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for paths in mutations:
                changed = copy.deepcopy(self.task)
                changed['allowed_paths'] = paths
                (root / TASK).write_text(json.dumps(changed))
                with patch.dict(h, {'TASK_SHA': digest(changed)}):
                    self.assertTrue(self.check(root, h['G'], h['R']))

    def test_each_operation_release_and_privacy_gate_is_independently_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for section in h['GATES']:
                with self.subTest(section=section):
                    changed = copy.deepcopy(self.task)
                    value = changed[section]
                    changed[section] = value + ['Broader authority'] if isinstance(value, list) else 'PENDING'
                    (root / TASK).write_text(json.dumps(changed))
                    with patch.dict(h, {'TASK_SHA': digest(changed)}):
                        self.assertTrue(self.check(root, h['G'], h['R']))

    def test_expiry_is_not_missing_shifted_or_the_obsolete_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for ceiling in ('2026-10-09T22:35:00Z', '2026-10-10T02:10:00Z', ''):
                changed = copy.deepcopy(self.task)
                changed['requirements'][0] = changed['requirements'][0].replace(h['CEILING'], ceiling)
                (root / TASK).write_text(json.dumps(changed))
                gates = {**h['GATES'], 'requirements': digest(changed['requirements'])}
                with patch.dict(h, {'TASK_SHA': digest(changed), 'GATES': gates}):
                    errors = self.check(root, h['G'], h['R'])
                    self.assertTrue(any('renewal ceiling differs' in error for error in errors))

    def test_historical_task_cannot_be_rewritten_by_renewal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            original = json.loads((root / ORIGINAL).read_text())
            original['objective'] += ' rewritten historical authority'
            (root / ORIGINAL).write_text(json.dumps(original))
            with patch.object(c, 'FOUNDRY_QUALIFICATION_TASK_SHA256', digest(original)):
                errors = self.check(root, h['G'], h['R'])
                self.assertTrue(any('renewal historical task differs' in error for error in errors))

    def test_identity_base_and_source_history_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for field, value in (('base_commit', '0' * 40), ('task_id', 'APBRA-173'),
                                 ('assigned_agent', 'APBRA-DEV-BE'), ('branch', h['R'])):
                changed = copy.deepcopy(self.task)
                changed[field] = value
                (root / TASK).write_text(json.dumps(changed))
                with patch.dict(h, {'TASK_SHA': digest(changed)}):
                    self.assertTrue(self.check(root, h['G'], h['R']))
            (root / TASK).write_text(json.dumps(self.task))
            sources = json.loads((root / 'docs/source-register.json').read_text())
            sources['sources'][0]['title'] = 'rewritten historical source'
            (root / 'docs/source-register.json').write_text(json.dumps(sources))
            self.assertTrue(self.check(root, h['G'], h['R']))

    def test_missing_or_malformed_registration_never_grants_product_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            (root / TASK).unlink()
            self.assertTrue(self.check(root, h['P']))
            (root / TASK).write_text(json.dumps(self.task))
            original = (root / ORIGINAL).read_bytes()
            (root / ORIGINAL).unlink()
            self.assertTrue(self.check(root, h['P']))
            self.assertTrue(self.check(root, h['G'], h['R']))
            (root / ORIGINAL).write_bytes(original)
            (root / TASK).write_text('{')
            self.assertTrue(self.check(root, h['P']))
            (root / TASK).write_text(json.dumps(self.task))
            (root / 'scripts/check_foundry_qualification_renewal.py').unlink()
            self.assertTrue(self.check(root, h['P']))

    def test_missing_or_invalid_helper_import_stops_checker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            helper = root / 'scripts/check_foundry_qualification_renewal.py'
            for contents in (None, 'def malformed('):
                if contents is None:
                    helper.unlink()
                else:
                    helper.write_text(contents)
                result = subprocess.run([sys.executable, str(root / 'scripts/check_bootstrap.py')],
                                        capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('check_foundry_qualification_renewal.py', result.stderr)

    def test_original_constants_and_unaffected_functions_are_ast_identical(self):
        baseline = subprocess.check_output(['git', 'show', BASE + ':scripts/check_bootstrap.py'],
                                           cwd=ROOT, text=True, timeout=10)
        old = ast.parse(baseline)
        new = ast.parse((ROOT / 'scripts/check_bootstrap.py').read_text())
        declarations = {node.targets[0].id: node for node in new.body
                        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
        functions = {node.name: node for node in new.body if isinstance(node, ast.FunctionDef)}
        for node in old.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                self.assertEqual(ast.dump(node), ast.dump(declarations[node.targets[0].id]))
            elif isinstance(node, ast.FunctionDef) and node.name != 'check':
                self.assertEqual(ast.dump(node), ast.dump(functions[node.name]))
        self.assertLessEqual((ROOT / 'scripts/check_bootstrap.py').stat().st_size, 262144)
        self.assertEqual((ROOT / ORIGINAL).read_bytes(), subprocess.check_output(
            ['git', 'show', BASE + ':' + ORIGINAL], cwd=ROOT, timeout=10))
        self.assertEqual((ROOT / 'docs/source-register.json').read_bytes(), subprocess.check_output(
            ['git', 'show', BASE + ':docs/source-register.json'], cwd=ROOT, timeout=10))

    def test_old_registration_errors_are_preserved_on_actual_baseline_checker(self):
        baseline = subprocess.check_output(['git', 'show', BASE + ':scripts/check_bootstrap.py'],
                                           cwd=ROOT, text=True, timeout=10)
        with tempfile.TemporaryDirectory() as directory:
            outer = Path(directory)
            baseline_path = outer / 'baseline_checker.py'
            baseline_path.write_text(baseline)
            spec = importlib.util.spec_from_file_location('renewal_old_checker', baseline_path)
            original = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(original)
            roots = [outer / 'old', outer / 'new']
            for root in roots:
                root.mkdir()
                self.copy_repository(root)
                for name in h['G'] - {'scripts/check_bootstrap.py'}:
                    (root / name).unlink()
            (roots[0] / 'scripts/check_bootstrap.py').write_text(baseline)
            cases = ((ORIGINAL, c.FOUNDRY_QUALIFICATION_BRANCH, c.FOUNDRY_QUALIFICATION_PATHS),
                     ('tasks/APBRA-160-foundry-host.json', c.FOUNDRY_HOST_BRANCH, c.FOUNDRY_HOST_PATHS),
                     ('tasks/APBRA-160-provider-retrieval.json', c.PROVIDER_RETRIEVAL_BRANCH, c.PROVIDER_RETRIEVAL_PATHS))
            for filename, branch, paths in cases:
                accepted = json.loads((ROOT / filename).read_text())
                for mutation in (None, 'scope', 'identity', 'gate', 'sources'):
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
                    old_errors = original.check(roots[0], active_task_id='APBRA-160',
                                                active_branch=branch, changed_paths=set(paths))[0]
                    new_errors = c.check(roots[1], active_task_id='APBRA-160',
                                         active_branch=branch, changed_paths=set(paths))[0]
                    self.assertEqual(new_errors, old_errors)
                    self.assertEqual(bool(old_errors), mutation is not None)
                for root in roots:
                    (root / filename).write_text(json.dumps(accepted))


if __name__ == '__main__':
    unittest.main()
