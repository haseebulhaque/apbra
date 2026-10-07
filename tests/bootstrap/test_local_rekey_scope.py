"""Finite local rekey registration; no live secret access."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('bootstrap_rekey', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
TASK = 'tasks/APBRA-160-local-rekey.json'
PRODUCT = {'apps/api/src/apbra_api/tenant_secrets.py', 'apps/api/src/apbra_api/rekey_tenant_secrets.py', 'apps/api/tests/test_rekey_tenant_secrets.py'}
REGISTRATION = {'scripts/check_bootstrap.py', TASK, 'tests/bootstrap/test_local_rekey_scope.py'}

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

class LocalRekeyScopeTests(unittest.TestCase):
    def check(self, paths, branch=None):
        return c.check(ROOT, active_task_id='APBRA-160', active_branch=branch or c.LOCAL_RECOVERY_BRANCH, changed_paths=set(paths))[0]

    def test_exact_scope_and_historical_preservation(self):
        task = c.load_json(ROOT / TASK)
        self.assertEqual(set(task['allowed_paths']), PRODUCT)
        self.assertEqual(len(task['allowed_paths']), 3)
        self.assertEqual(c.LOCAL_RECOVERY_PATHS, PRODUCT)
        self.assertEqual(c.LOCAL_RECOVERY_REGISTRATION_PATHS, REGISTRATION)
        self.assertEqual(digest(task), c.LOCAL_RECOVERY_TASK_SHA256)
        self.assertEqual(digest(c.load_json(ROOT / 'docs/source-register.json')), c.LOCAL_RECOVERY_ALL_SOURCES_SHA256)
        self.assertEqual(digest(c.load_json(ROOT / 'tasks/APBRA-160-foundry-structured-output.json')), c.FOUNDRY_SCHEMA_TASK_SHA256)
        self.assertEqual(len(c.FOUNDRY_SCHEMA_PATHS), 26)
        self.assertEqual(task['base_commit'], '356041b4464a500a2ca126bd1d95298405ffe934')
        self.assertEqual(len(c.load_json(ROOT / 'docs/source-register.json')['sources']), 84)

    def test_separate_registration_and_implementation(self):
        self.assertEqual(self.check(REGISTRATION, c.LOCAL_RECOVERY_REGISTRATION_BRANCH), [])
        self.assertEqual(self.check(PRODUCT), [])
        for omitted in REGISTRATION:
            self.assertTrue(self.check(REGISTRATION - {omitted}, c.LOCAL_RECOVERY_REGISTRATION_BRANCH))
        for extra in PRODUCT | {'docs/source-register.json', '.github/workflows/bootstrap.yml'}:
            self.assertTrue(self.check(REGISTRATION | {extra}, c.LOCAL_RECOVERY_REGISTRATION_BRANCH))
        for extra in REGISTRATION | {'apps/api/src/apbra_api/api.py', 'compose.yaml', 'apps/api/alembic/versions/rekey.py'}:
            self.assertTrue(self.check(PRODUCT | {extra}))
        self.assertTrue(self.check(PRODUCT, c.FOUNDRY_SCHEMA_BRANCH))
        self.assertTrue(self.check(PRODUCT, 'agent/APBRA-DEVOPS/APBRA-160-unregistered'))

    def test_scope_mutations_fail_even_with_recomputed_digest(self):
        original = c.load_json(ROOT / TASK)
        variants = []
        for omitted in PRODUCT:
            value = copy.deepcopy(original)
            value['allowed_paths'].remove(omitted)
            variants.append(value)
        for extra in ['apps/api/**', '*', 'compose.yaml', 'apps/api/src/apbra_api/api.py']:
            value = copy.deepcopy(original)
            value['allowed_paths'].append(extra)
            variants.append(value)
        value = copy.deepcopy(original)
        value['allowed_paths'].append(value['allowed_paths'][0])
        variants.append(value)
        loader = c.load_json
        for value in variants:
            with self.subTest(paths=value['allowed_paths']):
                def altered(path):
                    return value if path == ROOT / TASK else loader(path)
                with patch.object(c, 'load_json', side_effect=altered), patch.object(c, 'LOCAL_RECOVERY_TASK_SHA256', digest(value)):
                    self.assertTrue(self.check(PRODUCT))

    def test_weakened_protected_gates_fail_with_recomputed_task_digest(self):
        loader = c.load_json
        for field in c.LOCAL_RECOVERY_GATE_SHA256:
            task = copy.deepcopy(loader(ROOT / TASK))
            task[field] = ['Agents may decrypt real credentials; no review or CI'] if isinstance(task[field], list) else 'Live agent execution allowed'
            with self.subTest(field=field):
                with patch.object(c, 'load_json', side_effect=lambda path: task if path == ROOT / TASK else loader(path)), patch.object(c, 'LOCAL_RECOVERY_TASK_SHA256', digest(task)):
                    self.assertTrue(self.check(PRODUCT))

if __name__ == '__main__':
    unittest.main()
