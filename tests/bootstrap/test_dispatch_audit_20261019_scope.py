"""Finite local scope proposal, historical inverse and withdrawal regressions."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('dispatch_audit_bootstrap', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
H = c.da['bind'].__globals__
TASK = 'tasks/' + H['FILENAME']


class DispatchAuditScopeTests(unittest.TestCase):
    def fixture(self, folder):
        root = Path(folder)
        for name in {path.relative_to(ROOT) for path in c.repo_files(ROOT)} | {Path(name) for name in H['G']}:
            path = ROOT / name
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        return root

    def check(self, root, paths=None, branch=None, identity='APBRA-160'):
        return c.check(root, active_task_id=identity, active_branch=branch or H['R'],
                       changed_paths=H['G'] if paths is None else set(paths))[0]

    def test_exact_scope_and_unchanged_history(self):
        task = json.loads((ROOT / TASK).read_text())
        self.assertEqual(len(H['P']), 57)
        self.assertEqual(len(H['G']), 6)
        self.assertFalse(H['P'] & H['G'])
        self.assertEqual(set(task['allowed_paths']), H['P'])
        self.assertEqual(H['digest'](task), H['TASK_SHA'])
        self.assertEqual(task['base_commit'], 'f7a363dc7e5a958585f65f4cfeedf69ac20890d7')
        self.assertEqual(task['requirements'][0], H['AUTHORITY'])
        self.assertEqual(self.check(ROOT), [])
        for name, expected in H['HISTORY'].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)
            self.assertEqual((ROOT / name).read_bytes(), subprocess.check_output(
                ['git', 'show', H['BASE'] + ':' + name], cwd=ROOT))
        for name in ['agents/catalog.json', 'docs/source-register.json']:
            self.assertEqual((ROOT / name).read_bytes(), subprocess.check_output(
                ['git', 'show', H['BASE'] + ':' + name], cwd=ROOT))

    def test_full_prior_ast_and_exact_hook_negatives(self):
        current = (ROOT / 'scripts/check_bootstrap.py').read_text()
        previous = subprocess.check_output(['git', 'show', H['BASE'] + ':scripts/check_bootstrap.py'],
                                           cwd=ROOT, text=True)
        self.assertLessEqual(len(current.encode()), 262076)
        self.assertEqual(ast.dump(ast.parse(H['strip_hooks'](current))), ast.dump(ast.parse(previous)))
        for _, hook in H['HOOKS']:
            for broken in [current.replace(hook, '', 1), current + hook]:
                with self.assertRaises(ValueError):
                    H['strip_hooks'](broken)
        source = (ROOT / 'scripts/check_sp.py').read_text()
        previous = subprocess.check_output(['git', 'show', H['BASE'] + ':scripts/check_sp.py'],
                                           cwd=ROOT, text=True)
        self.assertEqual(ast.dump(ast.parse(H['strip_sp_changes'](source))), ast.dump(ast.parse(previous)))
        for _, after in H['SP_EDITS']:
            for broken in [source.replace(after, '', 1), source + after]:
                with self.assertRaises(ValueError):
                    H['strip_sp_changes'](broken)

    def test_stage_omissions_and_mixed_or_foreign_paths_fail(self):
        for name in H['G']:
            self.assertTrue(self.check(ROOT, H['G'] - {name}))
            self.assertTrue(self.check(ROOT, H['P'] | {name}, H['B']))
        for foreign in ['.env', 'compose.yaml', '.github/workflows/bootstrap.yml',
                        'apps/api/src/apbra_api/auth_boundary.py', 'apps/api/src/apbra_api/main.py',
                        'apps/api/src/apbra_api/tenant_settings.py', 'apps/web/src/EnterpriseApp.tsx']:
            self.assertTrue(self.check(ROOT, H['G'] | {foreign}))
            self.assertTrue(self.check(ROOT, H['P'] | {foreign}, H['B']))
        self.assertTrue(self.check(ROOT, H['P']))
        self.assertTrue(self.check(ROOT, H['G'], H['B']))
        self.assertTrue(self.check(ROOT, H['G'], identity='APBRA-85'))
        self.assertTrue(self.check(ROOT, H['G'], 'agent/APBRA-DEVOPS/APBRA-160-unknown'))
        self.assertTrue(H['errors'](json.loads((ROOT / TASK).read_text()), H['B'], set()))

    def test_product_witnesses_require_current_task_and_every_history_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fixture(folder)
            # Synthetic syntax witnesses prove path admission only, never product behavior.
            for name in H['P']:
                target = root / name
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text('"Synthetic scope witness only."\n')
            self.assertEqual(self.check(root, H['P'], H['B']), [])
            self.assertTrue(all(root / name in c.repo_files(root) for name in H['P']))
            original = (root / TASK).read_bytes()
            (root / TASK).unlink()
            errors = self.check(root, H['P'], H['B'])
            self.assertTrue(errors)
            self.assertTrue(any('safe bootstrap scope' in error for error in errors))
            (root / TASK).write_bytes(original)
            previous = root / 'tasks/APBRA-160-tenant-document-drafts-20261013.json'
            previous.write_bytes(previous.read_bytes() + b'\n')
            self.assertTrue(self.check(root, H['P'], H['B']))

    def test_recomputed_outer_task_pin_does_not_admit_mutated_sections(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fixture(folder)
            original = json.loads((root / TASK).read_text())
            for key in H['GATES']:
                value = copy.deepcopy(original)
                current = value[key]
                value[key] = current + ['Broader scope'] if isinstance(current, list) else 'MUTATED'
                (root / TASK).write_text(json.dumps(value))
                with self.subTest(key=key), patch.dict(H, {'TASK_SHA': H['digest'](value)}):
                    self.assertTrue(self.check(root))

    def test_authority_and_literal_paths_survive_outer_and_section_repin(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fixture(folder)
            original = json.loads((root / TASK).read_text())
            changes = [('requirements', ['Invented broader approval', *original['requirements'][1:]]),
                       ('allowed_paths', original['allowed_paths'] + ['apps/api/**']),
                       ('allowed_paths', original['allowed_paths'][:-1]),
                       ('allowed_paths', original['allowed_paths'] + [original['allowed_paths'][0]]),
                       ('base_commit', '0' * 40), ('branch', H['R']),
                       ('assigned_agent', 'APBRA-DEV-BE'), ('agent_card_version', '9.9')]
            for key, changed in changes:
                value = {**original, key: changed}
                (root / TASK).write_text(json.dumps(value))
                gates = {**H['GATES'], key: H['digest'](changed)}
                with self.subTest(key=key), patch.dict(H, {'TASK_SHA': H['digest'](value), 'GATES': gates}):
                    self.assertTrue(self.check(root))

    def test_source_and_catalog_tampering_with_recomputed_source_pin_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fixture(folder)
            path = root / 'docs/source-register.json'
            original = path.read_bytes()
            changed = json.loads(original)
            changed['sources'][0]['version'] = 999999
            path.write_text(json.dumps(changed))
            with patch.dict(H, {'SOURCES_SHA': H['digest'](changed)}):
                self.assertTrue(self.check(root))
            path.write_bytes(original)
            catalog = root / 'agents/catalog.json'
            catalog.write_bytes(catalog.read_bytes() + b'\n')
            self.assertTrue(self.check(root))

    def test_missing_malformed_withdrawn_task_and_helper_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fixture(folder)
            task = root / TASK
            original = task.read_bytes()
            for broken in [b'{', json.dumps({**json.loads(original), 'owner_acceptance': 'PENDING'}).encode()]:
                task.write_bytes(broken)
                self.assertTrue(self.check(root))
            task.write_bytes(original)
            helper = root / 'scripts/check_dispatch_audit_20261019.py'
            helper.unlink()
            result = subprocess.run([__import__('sys').executable, str(root / 'scripts/check_bootstrap.py')],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_historical_fixture_adaptation_preserves_every_prior_assertion(self):
        name='tests/bootstrap/test_tenant_document_drafts_20261013_scope.py'
        current=(ROOT/name).read_text()
        previous=subprocess.check_output(['git','show',H['BASE']+':'+name],cwd=ROOT,text=True)
        before,after=H['DOCUMENT_FIXTURE_EDIT']
        self.assertEqual(current.count(after),1)
        self.assertEqual(ast.dump(ast.parse(current.replace(after,before,1))),ast.dump(ast.parse(previous)))
        names=H['historical_document_fixture_names'](ROOT,set())
        expected=set(subprocess.check_output(['git','ls-tree','-rz','--name-only',H['BASE']],cwd=ROOT).decode().split('\0')[:-1])
        self.assertEqual(names,expected|{'scripts/check_dispatch_audit_20261019.py'})
        self.assertNotIn(TASK,names)
        self.assertIn(ROOT/TASK,c.repo_files(ROOT))

    def test_historical_fixture_missing_object_or_unsafe_addition_fails_closed(self):
        for unsafe in ['../outside','/absolute','a\\b','.git/config','a//b']:
            with self.subTest(path=unsafe),self.assertRaises(ValueError):
                H['historical_document_fixture_names'](ROOT,{unsafe})
        with patch('subprocess.check_output',side_effect=OSError('Synthetic missing object')):
            with self.assertRaises(ValueError):
                H['historical_document_fixture_names'](ROOT,set())


if __name__ == '__main__':
    unittest.main()
