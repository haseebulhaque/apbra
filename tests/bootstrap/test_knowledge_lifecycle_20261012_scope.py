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
import historical_fixture_staging as fixture_names

ROOT = Path(__file__).resolve().parents[2]
TASK = 'tasks/APBRA-160-knowledge-lifecycle-20261012.json'
spec = importlib.util.spec_from_file_location('knowledge_lifecycle_bootstrap', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
h = c.k['bind'].__globals__


def restore_h9_fixture_selection(tree):
    """Reverse only the exact new import and one copy-loop iterable."""
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
               and node.module == 'historical_fixture_staging'
               and [(item.name, item.asname) for item in node.names] == [('knowledge_registration_names', None)]]
    if len(imports) != 1:
        raise AssertionError('Exact fixture import missing or duplicated')
    tree.body.remove(imports[0])
    method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'copy')
    loops = [node for node in method.body if isinstance(node, ast.For)]
    if len(loops) != 1 or ast.dump(loops[0].iter) != ast.dump(ast.parse("knowledge_registration_names(ROOT, h['G'])", mode='eval').body):
        raise AssertionError('Exact fixture selector differs')
    loops[0].iter = ast.parse("{p.relative_to(ROOT).as_posix() for p in c.repo_files(ROOT)} | h['G']", mode='eval').body
    return tree


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

    def test_exact_two_product_five_governance_paths_and_withdrawal(self):
        task = json.loads((ROOT / TASK).read_text())
        self.assertEqual(len(h['P']), 2)
        self.assertEqual(len(h['G']), 7)
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


    def test_historical_snapshot_plumbing_preserves_every_original_ast_node(self):
        name = 'tests/bootstrap/test_historical_fixture_staging_20261012_scope.py'
        old = ast.parse(subprocess.check_output(['git', 'show', h['BASE'] + ':' + name], cwd=ROOT, text=True))
        new = restore_h9_fixture_selection(ast.parse((ROOT / name).read_text()))
        names = {'HISTORICAL_CHECKER_COMMIT', 'HISTORICAL_CHECKER_TREE', 'HISTORICAL_CHECKER_DIGEST'}
        removed = []
        for node in new.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in names:
                removed.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name == 'historical_checker_snapshot':
                removed.append(node)
        self.assertEqual(len(removed), 4)
        new.body = [node for node in new.body if node not in removed]
        old_method = next(node for node in ast.walk(old) if isinstance(node, ast.FunctionDef) and node.name == 'test_whole_old_checker_ast_restored_after_exact_seven_hooks')
        old_read = next(node.value for node in old_method.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'current')
        replacements = 0
        for node in ast.walk(new):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'historical_checker_snapshot':
                self.assertEqual(node.targets[0].id, 'current')
                self.assertEqual(node.value.args, [])
                self.assertEqual(node.value.keywords, [])
                node.value = old_read
                replacements += 1
        self.assertEqual(replacements, 1)
        self.assertEqual(ast.dump(old), ast.dump(new))

    def test_pinned_historical_snapshot_good_missing_bad_tree_and_changed_bytes(self):
        path = ROOT / 'tests/bootstrap/test_historical_fixture_staging_20261012_scope.py'
        spec = importlib.util.spec_from_file_location('snapshot_negative_probe', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        raw = subprocess.check_output(['git', 'show', module.HISTORICAL_CHECKER_COMMIT + ':scripts/check_bootstrap.py'], cwd=ROOT)
        self.assertEqual(module.historical_checker_snapshot(), raw.decode('utf-8'))
        tree = module.HISTORICAL_CHECKER_TREE.encode() + b'\n'
        failures = [
            subprocess.CalledProcessError(128, ['git'], stderr=b'synthetic-private-error'),
            OSError('synthetic-private-error'),
            [b'0' * 40 + b'\n'],
            [b'\xff'],
            [tree, raw + b'\n'],
            [tree, bytes([raw[0] ^ 1]) + raw[1:]],
        ]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__), patch.object(module.subprocess, 'check_output', side_effect=failure):
                with self.assertRaisesRegex(ValueError, '^Historical checker snapshot unavailable$'):
                    module.historical_checker_snapshot()
        with patch.object(module.subprocess, 'check_output', side_effect=[tree, raw]) as get:
            self.assertEqual(module.historical_checker_snapshot(), raw.decode('utf-8'))
            self.assertEqual(get.call_count, 2)
            for call in get.call_args_list:
                self.assertEqual(call.kwargs['timeout'], 10)
                self.assertIs(call.kwargs['stderr'], subprocess.PIPE)



    def test_three_historical_copy_changes_restore_whole_h9_ast_and_old_h3_utility(self):
        base = fixture_names.KNOWLEDGE_REGISTRATION_BASE
        for name in ['test_ai_authored_layout_raw_ingress_20261012_scope.py',
                     'test_foundry_owner_metadata_20261012_scope.py',
                     'test_historical_fixture_staging_20261012_scope.py']:
            with self.subTest(name=name):
                path = 'tests/bootstrap/' + name
                old = ast.parse(subprocess.check_output(['git', 'show', base + ':' + path], cwd=ROOT))
                new = restore_h9_fixture_selection(ast.parse((ROOT / path).read_text()))
                self.assertEqual(ast.dump(old), ast.dump(new))
        path = 'tests/bootstrap/historical_fixture_staging.py'
        old_bytes = subprocess.check_output(['git', 'show', base + ':' + path], cwd=ROOT)
        current = (ROOT / path).read_bytes()
        self.assertTrue(current.startswith(old_bytes))
        old, new = ast.parse(old_bytes), ast.parse(current)
        additions = {'KNOWLEDGE_REGISTRATION_BASE', 'KNOWLEDGE_REGISTRATION_TREE',
                     'KNOWLEDGE_REGISTRATION_UNIVERSE_SHA'}
        kept = []
        removed = 0
        for node in new.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1 and
                    isinstance(node.targets[0], ast.Name) and node.targets[0].id in additions):
                removed += 1
            elif isinstance(node, ast.FunctionDef) and node.name == 'knowledge_registration_names':
                removed += 1
            else:
                kept.append(node)
        self.assertEqual(removed, 4)
        new.body = kept
        self.assertEqual(ast.dump(old), ast.dump(new))
        self.assertEqual((ROOT / 'scripts/check_bootstrap.py').read_bytes(),
                         subprocess.check_output(['git', 'show', base + ':scripts/check_bootstrap.py'], cwd=ROOT))
        self.assertEqual(len((ROOT / 'scripts/check_bootstrap.py').read_bytes()), 262076)

    def test_h9_universe_exact_pins_shape_and_git_failures_are_closed(self):
        self.assertEqual(fixture_names.KNOWLEDGE_REGISTRATION_BASE, '287ceac2c67979d60f45d44d0d0da21798f96dcd')
        self.assertEqual(fixture_names.KNOWLEDGE_REGISTRATION_TREE, '76903c07688d79c1b9ca4fdfd98965b23433d54d')
        self.assertEqual(fixture_names.KNOWLEDGE_REGISTRATION_UNIVERSE_SHA, '3dad0a31dd8add81398efcfa0edaa37e92f662662c838ab652441210c97c49b8')
        names = fixture_names.knowledge_registration_names(ROOT)
        self.assertEqual(len(names), 334)
        self.assertFalse(names & h['P'])
        self.assertEqual(fixture_names.knowledge_registration_names(ROOT, h['G']), names | h['G'])
        raw = subprocess.check_output(['git', 'ls-tree', '-rz', '--name-only', fixture_names.KNOWLEDGE_REGISTRATION_BASE], cwd=ROOT)
        tree = fixture_names.KNOWLEDGE_REGISTRATION_TREE.encode() + b'\n'
        for error in [OSError('synthetic-private-error'), subprocess.CalledProcessError(128, ['git'], stderr=b'synthetic-private-error'), [b'0' * 40 + b'\n'], [b'\xff'], [tree, raw + b'\0']]:
            with self.subTest(error=type(error).__name__), patch.object(fixture_names.subprocess, 'check_output', side_effect=error):
                with self.assertRaisesRegex(ValueError, '^Knowledge historical fixture snapshot unavailable$'):
                    fixture_names.knowledge_registration_names(ROOT)
        for raw_bad in [b'', b'a', b'\0', b'a\0a\0', b'../private\0', b'/absolute\0', b'a\\b\0', b'.git/config\0', b'\xff\0']:
            with self.subTest(shape=hashlib.sha256(raw_bad).hexdigest()), patch.object(fixture_names, 'KNOWLEDGE_REGISTRATION_UNIVERSE_SHA', hashlib.sha256(raw_bad).hexdigest()), patch.object(fixture_names.subprocess, 'check_output', side_effect=[tree, raw_bad]):
                with self.assertRaisesRegex(ValueError, '^Knowledge historical fixture snapshot unavailable$'):
                    fixture_names.knowledge_registration_names(ROOT)
        for bad in ['', '../private', '/absolute', 'a\\b', '.git/config', 'a\0b', None]:
            with self.subTest(addition=type(bad).__name__):
                with self.assertRaisesRegex(ValueError, '^Knowledge historical fixture snapshot unavailable$'):
                    fixture_names.knowledge_registration_names(ROOT, [bad])

    def test_three_historical_fixtures_exclude_future_p2_but_current_withdrawal_rejects_them(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source'
            subprocess.run(['git', 'clone', '--no-hardlinks', '--quiet', str(ROOT), str(source)], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.copy(source)
            for name in h['P']:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('# Synthetic future P2 fixture witness, never executable product.\n')
            subprocess.run(['git', '-C', str(source), 'add', '--', *sorted(h['P'])], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for index, (filename, classname) in enumerate([
                ('test_ai_authored_layout_raw_ingress_20261012_scope.py', 'AILayoutRawIngressScopeTests'),
                ('test_foundry_owner_metadata_20261012_scope.py', 'FoundryOwnerMetadataScopeTests'),
                ('test_historical_fixture_staging_20261012_scope.py', 'HistoricalFixtureStagingScopeTests'),
            ]):
                with self.subTest(module=filename):
                    spec = importlib.util.spec_from_file_location('fixture_probe_' + str(index), ROOT / 'tests/bootstrap' / filename)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    case = getattr(module, classname)()
                    selected = Path(directory) / ('selected-' + str(index))
                    with patch.object(module, 'ROOT', source):
                        case.copy(selected)
                    self.assertTrue(all(not (selected / name).exists() for name in h['P']))
                    with case.prospective(selected):
                        self.assertEqual(case.check(selected), [])
                        self.assertEqual(case.check(selected, module.h['P'], module.h['B']), [])
                    complete = Path(directory) / ('complete-' + str(index))
                    with patch.dict(globals(), {'ROOT': source}):
                        self.copy(complete)
                    self.assertTrue(all((complete / name).is_file() for name in h['P']))
                    self.assertEqual(self.check(complete, h['P'], h['B']), [])
                    with case.prospective(complete):
                        errors = case.check(complete)
                        self.assertEqual(set(errors), {'File outside safe bootstrap scope: ' + name for name in h['P']})
                    self.assertEqual(self.check(complete, h['P'], h['B']), [])


if __name__ == '__main__':
    unittest.main()
