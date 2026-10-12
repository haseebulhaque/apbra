"""Finite historical fixture staging authority; current full-tree gates stay exhaustive."""
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
from historical_fixture_staging import knowledge_registration_names

ROOT = Path(__file__).resolve().parents[2]
TASK = 'tasks/APBRA-160-historical-fixture-staging-20261012.json'
spec = importlib.util.spec_from_file_location('fixture_staging_bootstrap', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
h = c.f['bind'].__globals__


HOOK_ADDITIONS = ['f=runpy.run_path(str(Path(__file__).with_name("check_historical_fixture_staging_20261012.py")))\n', "        fixture_staging, e = f['bind'](root, catalog, sources, bound_provider_registration)\n        errors += e\n", "            (fixture_staging, f['P']),\n", "                else fixture_staging if active_branch in {f['B'], f['R']}\n", "                    not f['stage'](active_task_id, active_branch, changed_paths) and\n", "            errors += f['errors'](active_task_id, active_branch, changed_paths)\n", " or\n                    (active_task is not None and f['stage'](active_task_id, active_branch, changed_paths)\n                     and name in f['G'] and path_allowed(name, task, card))"]
FIXTURE_MODULES = ['test_foundry_qualification_scope.py', 'test_foundry_qualification_renewal_scope.py', 'test_foundry_qualification_renewal_20261011_scope.py', 'test_generation_scope.py']


HISTORICAL_CHECKER_COMMIT = '480df505985b888989c6c7785cbb14a8f68094a8'
HISTORICAL_CHECKER_TREE = '5781a3a45d192a1812959735348ca82fd6a702f9'
HISTORICAL_CHECKER_DIGEST = '1ed71b26bf5fb4b6064c415f807313082c47812d0b2a52046648acdff2a26938'


def historical_checker_snapshot(root=ROOT):
    """Read the actual released H4 checker, never filter the current checker."""
    try:
        tree = subprocess.check_output(
            ['git', '-C', str(root), 'rev-parse', HISTORICAL_CHECKER_COMMIT + '^{tree}'],
            timeout=10, stderr=subprocess.PIPE,
        ).decode('ascii').strip()
        if tree != HISTORICAL_CHECKER_TREE:
            raise ValueError('Historical checker snapshot unavailable')
        raw = subprocess.check_output(
            ['git', '-C', str(root), 'show', HISTORICAL_CHECKER_COMMIT + ':scripts/check_bootstrap.py'],
            timeout=10, stderr=subprocess.PIPE,
        )
        if len(raw) != 262070 or hashlib.sha256(raw).hexdigest() != HISTORICAL_CHECKER_DIGEST:
            raise ValueError('Historical checker snapshot unavailable')
        return raw.decode('utf-8')
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        raise ValueError('Historical checker snapshot unavailable') from None

class HistoricalFixtureStagingScopeTests(unittest.TestCase):
    def copy(self, root):
        for name in knowledge_registration_names(ROOT, h['G']):
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

    def test_exact_nine_governance_five_fixture_paths_and_release_binding(self):
        task = json.loads((ROOT / TASK).read_text())
        self.assertEqual(len(h['P']), 5)
        self.assertEqual(len(h['G']), 9)
        self.assertEqual(set(task['allowed_paths']), h['P'])
        self.assertEqual(len(task['allowed_paths']), 5)
        self.assertEqual(h['digest'](task), h['TASK_SHA'])
        self.assertEqual(len(h['HISTORY']), 52)
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
                    if path not in h['P']:
                        self.assertTrue(self.check(root, h['P'] | {path}, h['B']))
                for path in h['P'] | {'apps/api/src/apbra_api/main.py', '.env', 'docs/extra.md'}:
                    if path not in h['G']:
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

    def test_fixture_staging_assertion_fulltree_and_release_guards_are_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            with self.prospective(root) as original:
                for index, replacement in [(1, 'Globally filter repo_files or ad hoc file exclusions'),
                                           (2, 'Stage all current tests rather than selected methods'),
                                           (3, 'Change old assertions and checker selection'),
                                           (4, 'Permit missing authority on current full tree'),
                                           (5, 'Ignore unavailable Git data and explicit negatives'),
                                           (6, 'Raise cap or change historical helper/checker/task pins'),
                                           (7, 'Permit real auth/provider/runtime/paid calls')]:
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
                helper = root / 'scripts/check_historical_fixture_staging_20261012.py'
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
            (root / 'scripts/check_historical_fixture_staging_20261012.py').write_text('raise RuntimeError("synthetic helper crash")\n')
            result = subprocess.run([__import__('sys').executable, str(root / 'scripts/check_bootstrap.py')], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

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
        for name in ['check_ai_authored_layout_20261012.py', 'check_renderer_geometry_20261011.py', 'check_foundry_qualification_renewal.py', 'check_foundry_owner_metadata_20261012.py', 'check_ai_authored_layout_raw_ingress_20261012.py']:
            self.assertEqual((ROOT / 'scripts' / name).read_bytes(), subprocess.check_output(['git', 'show', h['BASE'] + ':scripts/' + name], cwd=ROOT))
        self.assertLessEqual(checker.stat().st_size, 262076)


    def test_whole_old_checker_ast_restored_after_exact_seven_hooks(self):
        old = subprocess.check_output(['git', 'show', h['BASE'] + ':scripts/check_bootstrap.py'], cwd=ROOT, text=True)
        current = historical_checker_snapshot()
        for addition in HOOK_ADDITIONS:
            self.assertEqual(current.count(addition), 1)
            current = current.replace(addition, '')
        self.assertEqual(ast.dump(ast.parse(current)), ast.dump(ast.parse(old)))

    def test_historical_modules_restore_after_fixture_only_plumbing(self):
        for name in FIXTURE_MODULES:
            old = ast.parse(subprocess.check_output(['git', 'show', h['BASE'] + ':tests/bootstrap/' + name], cwd=ROOT))
            new = ast.parse((ROOT / 'tests/bootstrap' / name).read_text())
            old_generation_names = next(n.value for n in ast.walk(old) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'names' for t in n.targets)) if name == 'test_generation_scope.py' else None
            new.body = [n for n in new.body if not (isinstance(n, ast.ImportFrom) and n.module == 'historical_fixture_staging')]
            for n in ast.walk(new):
                if isinstance(n, ast.FunctionDef) and n.name in ('copy', 'copy_repository'):
                    self.assertEqual([x.arg for x in n.args.kwonlyargs], ['historical'])
                    self.assertEqual(ast.dump(n.args.kw_defaults[0]), ast.dump(ast.Constant(False)))
                    n.args.kwonlyargs = []; n.args.kw_defaults = []
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'names' for t in n.targets):
                    if isinstance(n.value, ast.IfExp):
                        self.assertEqual(ast.dump(n.value.test), ast.dump(ast.Name('historical', ast.Load())))
                        n.value = n.value.orelse
                    elif old_generation_names is not None:
                        self.assertEqual(ast.dump(n.value), ast.dump(ast.parse('historical_names(ROOT)', mode='eval').body))
                        n.value = copy.deepcopy(old_generation_names)
                if isinstance(n, ast.For) and isinstance(n.iter, ast.IfExp):
                    self.assertEqual(ast.dump(n.iter.test), ast.dump(ast.Name('historical', ast.Load())))
                    n.iter = n.iter.orelse
                if isinstance(n, ast.Call):
                    kws = [k for k in n.keywords if k.arg == 'historical']
                    if kws:
                        self.assertEqual(ast.dump(kws[0].value), ast.dump(ast.Constant(True)))
                        self.assertIsInstance(n.func, ast.Attribute)
                        self.assertIn(n.func.attr, ('copy', 'copy_repository'))
                        n.keywords = [k for k in n.keywords if k.arg != 'historical']
            self.assertEqual(ast.dump(new), ast.dump(old), name)

    def test_frozen_universe_and_explicit_unknown_additions(self):
        import historical_fixture_staging as staging
        actual = set(subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', staging.BASE], cwd=ROOT, text=True).splitlines())
        self.assertEqual(staging.historical_names(ROOT), actual)
        self.assertEqual(staging.historical_names(ROOT, {'apps/api/src/apbra_api/unregistered.py'}), actual | {'apps/api/src/apbra_api/unregistered.py'})
        for path in ('../outside', '/absolute', '.git/config', 'a//b'):
            with self.assertRaises(ValueError):
                staging.historical_names(ROOT, {path})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(subprocess.CalledProcessError):
                staging.historical_names(Path(directory))
        with patch.object(staging.subprocess, 'check_output', return_value=b'wrong-tree'):
            with self.assertRaises(ValueError):
                staging.historical_names(ROOT)
        with patch.object(staging.subprocess, 'check_output', side_effect=[(staging.TREE + '\n').encode(), b'bad-data']):
            with self.assertRaises(ValueError):
                staging.historical_names(ROOT)

    def test_current_bytes_and_explicit_negatives_are_not_suppressed(self):
        import historical_fixture_staging as staging
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            path = root / 'apps/api/src/apbra_api/main.py'
            path.write_text('gh' + 'p_' + 'x' * 36)
            errors = c.check(root)[0]
            self.assertTrue(any('credential pattern' in e for e in errors))
            path.write_text('synthetic fixture')
            unknown = root / 'apps/api/src/apbra_api/unregistered.py'
            unknown.write_text('synthetic unknown fixture')
            self.assertTrue(any('File outside safe bootstrap scope: apps/api/src/apbra_api/unregistered.py' in e for e in c.check(root)[0]))
            path.unlink(); path.symlink_to(root / 'README.md')
            self.assertTrue(any('File outside safe bootstrap scope: apps/api/src/apbra_api/main.py' in e for e in c.check(root)[0]))
            # Source's frozen names are selected only by explicit staging calls.
            self.assertIn(unknown, c.repo_files(root))

    def test_current_p4_p31_admission_requires_actual_new_authority_and_old_history(self):
        cases = [
            ('tasks/APBRA-160-foundry-owner-metadata-20261012.json', ['apps/api/src/apbra_api/foundry_metadata_projection.py', 'apps/api/src/apbra_api/foundry_owner_metadata.py', 'apps/api/tests/test_foundry_owner_metadata.py']),
            ('tasks/APBRA-160-ai-authored-layout-20261012.json', ['apps/api/tests/test_config.py', 'apps/web/knowledge/report-design-format-contract-v2.md', 'apps/web/src/aiGeometry.ts', 'apps/web/src/aiGeometry.test.ts']),
        ]
        for taskname, paths in cases:
            with self.subTest(task=taskname), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy(root)
                for name in paths:
                    path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('synthetic current registered file')
                self.assertEqual(c.check(root)[0], [])
                task = root / taskname; original = task.read_bytes()
                for mutation in ('missing', 'malformed', 'changed'):
                    if mutation == 'missing': task.unlink()
                    elif mutation == 'malformed': task.write_text('{malformed')
                    else:
                        changed = json.loads(original); changed['actual_authenticated_actor'] = 'Invented actor'; task.write_text(json.dumps(changed))
                    self.assertTrue(c.check(root)[0], mutation)
                    task.write_bytes(original)
                old = root / 'tasks/APBRA-160-foundry-qualification.json'; raw = old.read_bytes()
                old.write_bytes(raw + b'\n')
                errors = c.check(root)[0]
                self.assertTrue(any('File outside safe bootstrap scope: ' + name in errors for name in paths))
                old.unlink()
                self.assertTrue(c.check(root)[0])
                old.write_bytes(raw)
                self.assertEqual(c.check(root)[0], [])
                unknown = root / 'apps/api/src/apbra_api/new_unknown.py'; unknown.write_text('synthetic unknown')
                self.assertTrue(any('File outside safe bootstrap scope: apps/api/src/apbra_api/new_unknown.py' in e for e in c.check(root)[0]))

if __name__ == '__main__':
    unittest.main()
