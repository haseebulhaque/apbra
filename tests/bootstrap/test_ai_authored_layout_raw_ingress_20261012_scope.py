"""Additive AI raw-ingress integrity authority; no historical scope expansion."""
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
from contextlib import contextmanager
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
TASK = 'tasks/APBRA-160-ai-authored-layout-raw-ingress-20261012.json'
spec = importlib.util.spec_from_file_location('raw_ingress_bootstrap', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
h = c.u['bind'].__globals__


class AILayoutRawIngressScopeTests(unittest.TestCase):
    def copy(self, root):
        for name in {p.relative_to(ROOT).as_posix() for p in c.repo_files(ROOT)} | h['G']:
            path = ROOT / name
            if path.is_file():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)

    def check(self, root, paths=None, branch=None, identity='APBRA-160'):
        return c.check(root, active_task_id=identity, active_branch=branch or h['R'],
                       changed_paths=h['G'] if paths is None else set(paths))[0]

    @contextmanager
    def prospective(self, root):
        # Synthetic readiness for scope tests is not release provenance.
        path = root / TASK
        original = path.read_bytes()
        task = json.loads(original)
        task.update(task_mode='IMPLEMENTATION', readiness='READY_FOR_IMPLEMENTATION')
        path.write_text(json.dumps(task))
        gates = {**h['GATES'], 'task_mode': h['digest'](task['task_mode']),
                 'readiness': h['digest'](task['readiness'])}
        with patch.dict(h, {'RELEASE_BOUND': True, 'TASK_SHA': h['digest'](task), 'GATES': gates}):
            try:
                yield task
            finally:
                path.write_bytes(original)

    def test_exact_p31_union_and_release_binding(self):
        task = json.loads((ROOT / TASK).read_text())
        self.assertEqual(len(h['P']), 31)
        self.assertEqual(len(h['G']), 4)
        self.assertEqual(set(task['allowed_paths']), h['P'])
        self.assertEqual(len(task['allowed_paths']), 31)
        self.assertEqual(h['digest'](task), h['TASK_SHA'])
        self.assertEqual(h['P'], c.a['P'] | {'apps/web/src/durableGeneration.tsx', 'apps/web/src/api.ts', 'apps/api/src/apbra_api/api.py'})
        self.assertEqual(len(h['HISTORY']), 51)
        self.assertNotIn('CUTOFF', h)
        self.assertEqual(task['requirements'][0], h['AUTHORITY'])
        if not h['RELEASE_BOUND']:
            self.assertEqual(task['readiness'], 'BLOCKED_EXTERNAL')
            self.assertTrue(self.check(ROOT))
            self.assertTrue(self.check(ROOT, h['P'], h['B']))
        else:
            self.assertEqual(task['readiness'], 'READY_FOR_IMPLEMENTATION')
            self.assertEqual(self.check(ROOT), [])

    def test_prospective_stage_separation_omissions_unknown_and_mixed_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            with self.prospective(root):
                self.assertEqual(self.check(root), [])
                self.assertEqual(self.check(root, h['P'], h['B']), [])
                for path in h['G']:
                    self.assertTrue(self.check(root, h['G'] - {path}))
                    self.assertTrue(self.check(root, h['P'] | {path}, h['B']))
                for path in h['P'] | {'apps/api/src/apbra_api/main.py', '.env', 'docs/extra.md'}:
                    self.assertTrue(self.check(root, h['G'] | {path}))
                self.assertTrue(self.check(root, h['G'], h['B']))
                self.assertTrue(self.check(root, h['P'], h['R']))
                self.assertTrue(self.check(root, h['P'], c.a['B']))
                self.assertTrue(self.check(root, h['P'], h['B'], 'APBRA-85'))
                self.assertTrue(h['errors']('APBRA-160', h['B'], set()))

    def test_independent_sections_reject_recomputed_task_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            with self.prospective(root) as original:
                for field in h['GATES']:
                    changed = copy.deepcopy(original)
                    value = changed[field]
                    changed[field] = value + ['Broader permission'] if isinstance(value, list) else 'PENDING'
                    (root / TASK).write_text(json.dumps(changed))
                    with self.subTest(field=field), patch.dict(h, {'TASK_SHA': h['digest'](changed)}):
                        self.assertTrue(self.check(root))

    def test_owner_actor_base_card_and_literal_scope_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            with self.prospective(root) as original:
                mutations = [('actual_authenticated_actor', 'Invented actor'), ('human_owner', 'Other owner'),
                             ('human_initiator', 'Other owner'), ('base_commit', '0' * 40), ('branch', h['R']),
                             ('agent_card_version', '9.9'), ('assigned_agent', 'APBRA-DEV-FE'),
                             ('allowed_paths', original['allowed_paths'][:-1]),
                             ('allowed_paths', original['allowed_paths'] + [original['allowed_paths'][0]]),
                             ('allowed_paths', original['allowed_paths'] + ['apps/api/**'])]
                for field, value in mutations:
                    changed = {**original, field: value}
                    (root / TASK).write_text(json.dumps(changed))
                    with self.subTest(field=field), patch.dict(h, {'TASK_SHA': h['digest'](changed)}):
                        self.assertTrue(self.check(root))
                changed = copy.deepcopy(original)
                changed.pop('actual_authenticated_actor')
                (root / TASK).write_text(json.dumps(changed))
                with patch.dict(h, {'TASK_SHA': h['digest'](changed)}):
                    self.assertTrue(self.check(root))

    def test_expired_or_invented_authority_rejected_after_both_pin_recomputations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            with self.prospective(root) as original:
                for authority in ['Old approval19:10UTC2026-10-09', h['AUTHORITY'] + ' New sessionTTL3600/deadline2026-10-14.']:
                    changed = copy.deepcopy(original)
                    changed['requirements'][0] = authority
                    (root / TASK).write_text(json.dumps(changed))
                    gates = {**h['GATES'], 'requirements': h['digest'](changed['requirements'])}
                    with patch.dict(h, {'TASK_SHA': h['digest'](changed), 'GATES': gates}):
                        self.assertTrue(self.check(root))

    def test_raw_integrity_permission_priority_and_release_guards_are_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            with self.prospective(root) as original:
                for index, replacement in [(6, 'Round or normalize all raw source and discard original'),
                                           (7, 'Use SafeInteger cap and global JSON monkeypatch'),
                                           (8, 'Validate raw body before auth/CSRF/ACL and write first'),
                                           (9, 'Reuse prior P28 scope without new release gates')]:
                    changed = copy.deepcopy(original)
                    changed['requirements'][index] = replacement
                    (root / TASK).write_text(json.dumps(changed))
                    with self.subTest(index=index), patch.dict(h, {'TASK_SHA': h['digest'](changed)}):
                        self.assertTrue(self.check(root))

    def test_sources_and_history_raw_bytes_are_preserved_and_required(self):
        for name in h['HISTORY']:
            expected = subprocess.check_output(['git', 'show', h['BASE'] + ':tasks/' + name], cwd=ROOT)
            self.assertEqual((ROOT / 'tasks' / name).read_bytes(), expected)
        expected = subprocess.check_output(['git', 'show', h['BASE'] + ':docs/source-register.json'], cwd=ROOT)
        self.assertEqual((ROOT / 'docs/source-register.json').read_bytes(), expected)
        self.assertEqual(len(json.loads(expected)['sources']), 84)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            with self.prospective(root):
                path = root / 'docs/source-register.json'
                raw = path.read_bytes()
                path.write_bytes(raw + b'\n')
                self.assertTrue(self.check(root))
                path.write_bytes(raw)
                rows = json.loads(raw)
                row = next(v for v in rows['sources'] if v['id'] == h['SOURCES'][0][0])
                row['version'] += 1
                path.write_text(json.dumps(rows))
                with patch.dict(h, {'SOURCES_SHA': h['digest'](rows)}):
                    self.assertTrue(self.check(root))
                path.write_bytes(raw)
                history = root / 'tasks/APBRA-160-foundry-qualification.json'
                raw = history.read_bytes()
                history.write_bytes(raw + b'\n')
                self.assertTrue(self.check(root))
                history.unlink()
                self.assertTrue(self.check(root))

    def test_missing_malformed_task_and_helper_do_not_admit_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            with self.prospective(root) as original:
                path = root / TASK
                for value in ['{}', '{malformed']:
                    path.write_text(value)
                    self.assertTrue(self.check(root))
                path.write_text(json.dumps(original))
                helper = root / 'scripts/check_ai_authored_layout_raw_ingress_20261012.py'
                helper.unlink()
                self.assertTrue(self.check(root))

    def test_release_binding_withdrawal_rejects_both_stages(self):
        # Actual released prerequisite never substitutes for this helper binding.
        with patch.dict(h, {'RELEASE_BOUND': False}):
            self.assertTrue(self.check(ROOT))
            self.assertTrue(self.check(ROOT, h['P'], h['B']))

    def test_source_missing_duplicate_and_helper_crash_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            path = root / 'docs/source-register.json'
            original = json.loads(path.read_text())
            for missing in (True, False):
                rows = copy.deepcopy(original)
                index = next(i for i, v in enumerate(rows['sources']) if v['id'] == h['SOURCES'][0][0])
                if missing:
                    rows['sources'].pop(index)
                else:
                    rows['sources'].append(copy.deepcopy(rows['sources'][index]))
                path.write_text(json.dumps(rows))
                with patch.dict(h, {'SOURCES_SHA': h['digest'](rows)}):
                    self.assertTrue(self.check(root))
            path.write_text(json.dumps(original))
            (root / 'scripts/check_ai_authored_layout_raw_ingress_20261012.py').write_text('raise RuntimeError("synthetic helper crash")\n')
            result = subprocess.run([__import__('sys').executable, str(root / 'scripts/check_bootstrap.py')], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_raw_bounds_have_no_business_magnitude_or_new_confirmation_gate(self):
        task = json.loads((ROOT / TASK).read_text())
        self.assertIn('Accept large exactly representable2**60', task['requirements'][7])
        self.assertIn('No Number.isSafeInteger magnitude cap', task['requirements'][7])
        self.assertIn('authentication, CSRF and resource ACL error priority', task['requirements'][8])
        self.assertIn('Request/SDK/transport objects stay outside domain logic', task['requirements'][8])
        self.assertTrue(self.check(ROOT, h['P'], c.o['B']))
        self.assertTrue(self.check(ROOT, h['P'], 'agent/APBRA-DEVOPS/APBRA-160-unknown'))

    def test_old_ast_helpers_task_bytes_and_checker_cap_preserved(self):
        old = ast.parse(subprocess.check_output(['git', 'show', h['BASE'] + ':scripts/check_bootstrap.py'], cwd=ROOT))
        checker = ROOT / 'scripts/check_bootstrap.py'
        new = ast.parse(checker.read_text())
        declarations = {n.targets[0].id: n for n in new.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
        functions = {n.name: n for n in new.body if isinstance(n, ast.FunctionDef)}
        for node in old.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                self.assertEqual(ast.dump(node), ast.dump(declarations[node.targets[0].id]))
            elif isinstance(node, ast.FunctionDef) and node.name != 'check':
                self.assertEqual(ast.dump(node), ast.dump(functions[node.name]))
        for name in ['check_ai_authored_layout_20261012.py', 'check_renderer_geometry_20261011.py', 'check_foundry_qualification_renewal.py', 'check_foundry_owner_metadata_20261012.py']:
            self.assertEqual((ROOT / 'scripts' / name).read_bytes(), subprocess.check_output(['git', 'show', h['BASE'] + ':scripts/' + name], cwd=ROOT))
        self.assertLessEqual(checker.stat().st_size, 262144)


if __name__ == '__main__':
    unittest.main()
