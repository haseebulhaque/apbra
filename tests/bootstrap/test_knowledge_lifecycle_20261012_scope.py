"""Pure knowledge lifecycle finite registration; no provider or runtime authority."""
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
TASK = 'tasks/APBRA-160-knowledge-lifecycle-20261012.json'
spec = importlib.util.spec_from_file_location('knowledge_lifecycle_bootstrap', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
h = c.k['bind'].__globals__


class KnowledgeLifecycleScopeTests(unittest.TestCase):
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

    def test_exact_two_product_four_governance_paths_and_withdrawal(self):
        task = json.loads((ROOT / TASK).read_text())
        self.assertEqual(len(h['P']), 2)
        self.assertEqual(len(h['G']), 4)
        self.assertEqual(set(task['allowed_paths']), h['P'])
        self.assertEqual(len(task['allowed_paths']), 2)
        self.assertEqual(h['digest'](task), h['TASK_SHA'])
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
                for path in h['P'] | {'apps/api/src/apbra_api/config.py', '.env', 'docs/extra.md'}:
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

    def test_every_technical_lifecycle_privacy_and_noeffects_requirement_is_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            with self.prospective(root) as original:
                for index in range(1, len(original['requirements'])):
                    changed = copy.deepcopy(original)
                    changed['requirements'][index] = 'Broader provider dispatch, mutable identity and private output'
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
                helper = root / 'scripts/check_knowledge_lifecycle_20261012.py'
                helper.unlink()
                self.assertTrue(self.check(root))

    def test_release_binding_withdrawal_rejects_both_stages(self):
        # Actual released prerequisite never substitutes for this helper binding.
        with patch.dict(h, {'RELEASE_BOUND': False}):
            self.assertTrue(self.check(ROOT))
            self.assertTrue(self.check(ROOT, h['P'], h['B']))

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
        for name in subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', h['BASE'], 'scripts/'], cwd=ROOT, text=True).splitlines():
            if name == 'scripts/check_bootstrap.py':
                continue
            name = name.removeprefix('scripts/')
            self.assertEqual((ROOT / 'scripts' / name).read_bytes(), subprocess.check_output(['git', 'show', h['BASE'] + ':scripts/' + name], cwd=ROOT))
        self.assertLessEqual(checker.stat().st_size, 262076)


    def test_frozen_contract_semantics_and_outer_security_boundaries_are_explicit(self):
        task = json.loads((ROOT / TASK).read_text())
        text = '\n'.join(task['requirements'])
        for marker in ['PLAN10795', '22ad544614284295b4c2da2f8b024fdc4a5441d4c2cc8764bd7319017e7ea4b5',
                       'actor.identity_id AND membership_id', 'no cross-kind uniqueness restriction',
                       'fresh membership/session/CSRF', 'UNKNOWN', 'HISTORICAL_ONLY',
                       'No actual auth/owner/SDK']:
            self.assertIn(marker, text)
        self.assertEqual(set(task['allowed_paths']), h['P'])
        self.assertNotIn('isolation_verified', ''.join(task['allowed_paths']))


    def test_whole_original_checker_ast_matches_after_only_seven_additive_hooks(self):
        original = subprocess.check_output(['git', 'show', h['BASE'] + ':scripts/check_bootstrap.py'], cwd=ROOT, text=True)
        current = (ROOT / 'scripts/check_bootstrap.py').read_text()
        hooks = [
            'k=runpy.run_path(str(Path(__file__).with_name("check_knowledge_lifecycle_20261012.py")))\n',
            "        knowledge_lifecycle, e = k['bind'](root, catalog, sources, bound_provider_registration)\n        errors += e\n",
            "            (knowledge_lifecycle, k['P']),\n",
            "                else knowledge_lifecycle if active_branch in {k['B'], k['R']}\n",
            "                    not k['stage'](active_task_id, active_branch, changed_paths) and\n",
            "            errors += k['errors'](active_task_id, active_branch, changed_paths)\n",
            "                    (active_task is not None and k['stage'](active_task_id, active_branch, changed_paths)\n                     and name in k['G'] and path_allowed(name, task, card)) or\n",
        ]
        for hook in hooks:
            self.assertEqual(current.count(hook), 1)
            current = current.replace(hook, '', 1)
        self.assertEqual(ast.dump(ast.parse(original)), ast.dump(ast.parse(current)))
        old_lines, new_lines = original.splitlines(keepends=True), current.splitlines(keepends=True)
        self.assertEqual(len(old_lines), len(new_lines))
        first_function = next(i for i, line in enumerate(old_lines) if line.startswith('def '))
        for index, (before, after) in enumerate(zip(old_lines, new_lines)):
            if before != after:
                self.assertLess(index, first_function)
                self.assertTrue(before.startswith('    '))
                self.assertEqual(before.lstrip(), after.lstrip())
                self.assertGreater(len(before), len(after))
        self.assertEqual(len(original.encode()) - len(current.encode()), 670)


if __name__ == '__main__':
    unittest.main()
