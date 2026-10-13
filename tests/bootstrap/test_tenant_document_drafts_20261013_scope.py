"""Finite LOCAL document-drafts registration; historical journal authority unchanged."""
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
TASK = 'tasks/APBRA-160-tenant-document-drafts-20261013.json'
SEMANTIC_ORIGIN_BASE = '18454c33cff6be0e42c8f412d3cdc1ec75d1c898'
spec = importlib.util.spec_from_file_location('tenant_draft_bootstrap', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
h = c.d['bind'].__globals__


HOOK_ADDITIONS = ['d=runpy.run_path(str(Path(__file__).with_name("check_tenant_document_drafts_20261013.py")))\n', "        document_drafts, e = d['bind'](root, catalog, sources, bound_provider_registration)\n        errors += e\n", "            (document_drafts, d['P']),\n", "                else document_drafts if active_branch in {d['B'], d['R']}\n", "                    not d['stage'](active_task_id, active_branch, changed_paths) and\n", "            errors += d['errors'](active_task_id, active_branch, changed_paths)\n", "                    (active_task is not None and d['stage'](active_task_id, active_branch, changed_paths)\n                     and name in d['G'] and path_allowed(name, task, card)) or\n"]

class TenantDocumentDraftScopeTests(unittest.TestCase):
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

    def test_exact_g6_p10_scope_and_release_binding(self):
        task = json.loads((ROOT / TASK).read_text())
        self.assertEqual(h['BASE'], '7c16f98cfb0d33bd8259dc6d37eb9777f421bb96')
        self.assertEqual(task['base_commit'], h['BASE'])
        self.assertNotEqual(h['BASE'], SEMANTIC_ORIGIN_BASE)
        self.assertEqual(len(h['P']), 10)
        self.assertEqual(len(h['G']), 6)
        self.assertEqual(set(task['allowed_paths']), h['P'])
        self.assertEqual(len(task['allowed_paths']), 10)
        self.assertEqual(h['digest'](task), h['TASK_SHA'])
        self.assertEqual(len(h['HISTORY']), 54)
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
                for path in h['P'] | {'apps/api/src/apbra_api/main.py', '.env', 'apps/web/src/KnowledgeDocuments.tsx', 'docs/extra.md'}:
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
                             ('human_initiator', 'Other owner'), ('base_commit', '0' * 40), ('base_commit', SEMANTIC_ORIGIN_BASE), ('branch', h['R']),
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

    def test_contract_scope_history_and_closed_effects_requirements_are_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy(root)
            with self.prospective(root) as original:
                for index, replacement in [(2, 'External unpinned CI contract dependency'),
                                           (3, 'Raise checker cap or rewrite old journal task'),
                                           (4, 'Globally filter source files and remove old assertions'),
                                           (5, 'Perform owner sign-in/provider calls before release')]:
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
                helper = root / 'scripts/check_tenant_document_drafts_20261013.py'
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
            (root / 'scripts/check_tenant_document_drafts_20261013.py').write_text('raise RuntimeError("synthetic helper crash")\n')
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
        for name in ['check_ai_authored_layout_20261012.py', 'check_renderer_geometry_20261011.py', 'check_foundry_qualification_renewal.py', 'check_foundry_owner_metadata_20261012.py', 'check_ai_authored_layout_raw_ingress_20261012.py', 'check_knowledge_lifecycle_20261012.py']:
            self.assertEqual((ROOT / 'scripts' / name).read_bytes(), subprocess.check_output(['git', 'show', h['BASE'] + ':scripts/' + name], cwd=ROOT))
        self.assertLessEqual(checker.stat().st_size, 262076)


    def test_entire_old_checker_ast_after_only_exact_seven_hooks(self):
        old = subprocess.check_output(['git', 'show', h['BASE'] + ':scripts/check_bootstrap.py'], cwd=ROOT, text=True)
        current = c.zz['strip_current_hooks']((ROOT / 'scripts/check_bootstrap.py').read_text())
        # Strip only exact current hooks; the entire historical guard still compares.
        current = c.n['strip_current_hooks'](current)
        self.assertEqual(len(HOOK_ADDITIONS), 7)
        for hook in HOOK_ADDITIONS:
            self.assertEqual(current.count(hook), 1)
            current = current.replace(hook, '', 1)
        self.assertEqual(ast.dump(ast.parse(current)), ast.dump(ast.parse(old)))

    def test_full_embedded_contract_exact_paths_and_all_semantics(self):
        task = json.loads((ROOT / TASK).read_text())
        raw = task['requirements'][1].removeprefix(h['CONTRACT_PREFIX']).encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), h['CONTRACT_SHA'])
        contract = json.loads(raw)
        self.assertEqual(set(contract['product_paths']), h['P'])
        self.assertEqual(set(contract['registration_paths']), h['G'])
        self.assertEqual(contract['product_branch'], h['B'])
        self.assertEqual(contract['registration_branch'], h['R'])
        self.assertEqual(contract['base'], SEMANTIC_ORIGIN_BASE)
        self.assertNotEqual(contract['base'], h['BASE'])
        self.assertIn('max_file_bytes', contract['intake']['request_size'])
        self.assertIn('No new number/default', contract['intake']['request_size'])
        self.assertEqual(len(contract['product_paths']), 10)
        self.assertNotIn('apps/web/src/KnowledgeDocuments.tsx', h['P'])
        for section in ['server_authority', 'durability_and_order', 'migration', 'user_interface', 'verification', 'unchanged_and_closed']:
            self.assertTrue(contract[section])
        self.assertIn('provider write outcomes remain NOT_SENT', '\n'.join(contract['server_authority']))
        self.assertIn('not physically deleted', '\n'.join(contract['durability_and_order']))
        self.assertIn('No draft content enters Understanding/generation/RAG', '\n'.join(contract['user_interface']))
        self.assertIn('UTF8 bytea', contract['intake']['original'])
        self.assertIn('X-Expected-Membership-Id', contract['intake']['credentials'])
        wire_raw = task['requirements'][6].removeprefix(h['WIRE_PREFIX']).encode()
        self.assertEqual(hashlib.sha256(wire_raw).hexdigest(), h['WIRE_SHA'])
        wire = json.loads(wire_raw)
        self.assertEqual(wire['base'], SEMANTIC_ORIGIN_BASE)
        self.assertNotEqual(wire['base'], h['BASE'])
        self.assertEqual(wire['contractSHA256'], h['CONTRACT_SHA'])
        self.assertIn('equality', wire['headers']['X-Expected-Membership-Id'])
        self.assertIn('bytea', wire['database']['originals'])
        self.assertEqual(wire['basePath'], '/api/tenant-settings/knowledge-documents')
        self.assertEqual(len(wire['routes']), 9)

    def test_contract_raw_hash_rejects_every_section_even_after_outer_and_requirements_repin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.copy(root)
            path = root / TASK; task = json.loads(path.read_text())
            contract = json.loads(task['requirements'][1][len(h['CONTRACT_PREFIX']):])
            for field in contract:
                altered = copy.deepcopy(contract); altered[field] = h['BASE'] if field == 'base' else 'Broader or weaker semantics'
                changed = copy.deepcopy(task); changed['requirements'][1] = h['CONTRACT_PREFIX'] + json.dumps(altered)
                path.write_text(json.dumps(changed))
                gates = {**h['GATES'], 'requirements': h['digest'](changed['requirements'])}
                with self.subTest(field=field), patch.dict(h, {'TASK_SHA': h['digest'](changed), 'GATES': gates}):
                    self.assertTrue(self.check(root))
            for raw in ['{}', '{malformed', task['requirements'][1] + '\n', task['requirements'][1][len(h['CONTRACT_PREFIX']):]]:
                changed = copy.deepcopy(task); changed['requirements'][1] = raw; path.write_text(json.dumps(changed))
                with patch.dict(h, {'TASK_SHA': h['digest'](changed), 'GATES': {**h['GATES'], 'requirements': h['digest'](changed['requirements'])}}):
                    self.assertTrue(self.check(root))

            wire = json.loads(task['requirements'][6][len(h['WIRE_PREFIX']):])
            for field in wire:
                altered = copy.deepcopy(wire); altered[field] = h['BASE'] if field == 'base' else 'Broader or weaker wire'
                changed = copy.deepcopy(task); changed['requirements'][6] = h['WIRE_PREFIX'] + json.dumps(altered)
                path.write_text(json.dumps(changed))
                gates = {**h['GATES'], 'requirements': h['digest'](changed['requirements'])}
                with self.subTest(wire_field=field), patch.dict(h, {'TASK_SHA': h['digest'](changed), 'GATES': gates}):
                    self.assertTrue(self.check(root))
            for raw in ['{}', '{malformed', task['requirements'][6] + '\n', task['requirements'][6][len(h['WIRE_PREFIX']):]]:
                changed = copy.deepcopy(task); changed['requirements'][6] = raw; path.write_text(json.dumps(changed))
                with patch.dict(h, {'TASK_SHA': h['digest'](changed), 'GATES': {**h['GATES'], 'requirements': h['digest'](changed['requirements'])}}):
                    self.assertTrue(self.check(root))

    def test_old_utility_prefix_and_entire_ast_remain_after_only_six_appended_nodes(self):
        path = 'tests/bootstrap/historical_fixture_staging.py'
        old = subprocess.check_output(['git', 'show', h['BASE'] + ':' + path], cwd=ROOT)
        new = (ROOT / path).read_bytes(); self.assertTrue(new.startswith(old))
        tree = ast.parse(new)
        assignments = {'TENANT_DOCUMENT_DRAFTS_HISTORICAL_BASE', 'TENANT_DOCUMENT_DRAFTS_HISTORICAL_TREE', 'TENANT_DOCUMENT_DRAFTS_HISTORICAL_UNIVERSE_SHA', 'TENANT_DOCUMENT_DRAFTS_HISTORICAL_SNAPSHOTS'}
        functions = {'document_drafts_registration_names', 'knowledge_registration_snapshot'}
        kept = []; removed = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in assignments: removed.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name in functions: removed.append(node)
            else: kept.append(node)
        self.assertEqual(len(removed), 6); tree.body = kept
        self.assertEqual(ast.dump(tree), ast.dump(ast.parse(old)))

    def test_entire_old_knowledge_scope_ast_after_only_five_exact_read_expressions(self):
        path = 'tests/bootstrap/test_knowledge_lifecycle_20261012_scope.py'
        old = subprocess.check_output(['git', 'show', h['BASE'] + ':' + path], cwd=ROOT, text=True)
        current = (ROOT / path).read_text()
        replacements = [
            ("fixture_names.document_drafts_registration_names(ROOT, h['G'])", "{p.relative_to(ROOT).as_posix() for p in c.repo_files(ROOT)} | h['G']"),
            ("fixture_names.knowledge_registration_snapshot(ROOT, 'scripts/check_bootstrap.py').decode('utf-8')", "(ROOT / 'scripts/check_bootstrap.py').read_text()"),
            ("fixture_names.knowledge_registration_snapshot(ROOT, path)", "(ROOT / path).read_bytes()"),
            ("self.assertEqual(fixture_names.knowledge_registration_snapshot(ROOT, 'scripts/check_bootstrap.py'),", "self.assertEqual((ROOT / 'scripts/check_bootstrap.py').read_bytes(),"),
            ("len(fixture_names.knowledge_registration_snapshot(ROOT, 'scripts/check_bootstrap.py'))", "len((ROOT / 'scripts/check_bootstrap.py').read_bytes())"),
        ]
        for after, before in replacements:
            self.assertEqual(current.count(after), 1); current = current.replace(after, before)
        self.assertEqual(ast.dump(ast.parse(current)), ast.dump(ast.parse(old)))

    def test_pinned_h12_names_and_snapshots_fail_closed(self):
        import historical_fixture_staging as f
        names = f.document_drafts_registration_names(ROOT)
        self.assertEqual(len(names), 336)
        self.assertEqual(names, set(subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', f.TENANT_DOCUMENT_DRAFTS_HISTORICAL_BASE], cwd=ROOT, text=True).splitlines()))
        self.assertEqual(f.document_drafts_registration_names(ROOT, {'apps/api/foreign.py'}), names | {'apps/api/foreign.py'})
        for path in f.TENANT_DOCUMENT_DRAFTS_HISTORICAL_SNAPSHOTS:
            self.assertEqual(f.knowledge_registration_snapshot(ROOT, path), subprocess.check_output(['git', 'show', f.TENANT_DOCUMENT_DRAFTS_HISTORICAL_BASE + ':' + path], cwd=ROOT))
        for bad in ('../outside', '/outside', '.git/config', 'a//b', 'a\x00b', 1):
            with self.subTest(bad=bad), self.assertRaises(ValueError): f.document_drafts_registration_names(ROOT, [bad])
        for bad in ('apps/api/src/apbra_api/main.py', '../outside', None):
            with self.assertRaises(ValueError): f.knowledge_registration_snapshot(ROOT, bad)
        for failure in (OSError('synthetic'), subprocess.CalledProcessError(1, ['git']), UnicodeError('synthetic')):
            with patch.object(f.subprocess, 'check_output', side_effect=failure):
                with self.assertRaises(ValueError): f.document_drafts_registration_names(ROOT)
                with self.assertRaises(ValueError): f.knowledge_registration_snapshot(ROOT, 'scripts/check_bootstrap.py')
        tree = (f.TENANT_DOCUMENT_DRAFTS_HISTORICAL_TREE + '\n').encode()
        for values in ([b'wrong-tree'], [tree, b'bad names']):
            with patch.object(f.subprocess, 'check_output', side_effect=values):
                with self.assertRaises(ValueError): f.document_drafts_registration_names(ROOT)
        for values in ([b'wrong-tree'], [tree, b'bad snapshot']):
            with patch.object(f.subprocess, 'check_output', side_effect=values):
                with self.assertRaises(ValueError): f.knowledge_registration_snapshot(ROOT, 'scripts/check_bootstrap.py')

    def test_complete_current_new_product_witnesses_require_authority_and_old_history(self):
        names = ['apps/api/src/apbra_api/knowledge_documents.py', 'apps/api/alembic/versions/20261013_09_tenant_knowledge_drafts.py', 'apps/api/tests/test_knowledge_documents.py']
        baseline_names = set(subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', h['BASE']], cwd=ROOT, text=True).splitlines())
        self.assertEqual(h['P'] - baseline_names, set(names))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.copy(root)
            for name in names:
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('# Synthetic future draft source, not product implementation.\n')
            self.assertEqual(c.check(root)[0], [])
            self.assertTrue(all(root / name in c.repo_files(root) for name in names))
            task = root / TASK; original = task.read_bytes()
            for mode in ('missing', 'malformed', 'changed'):
                if mode == 'missing': task.unlink()
                elif mode == 'malformed': task.write_text('{malformed')
                else:
                    changed = json.loads(original); changed['human_owner'] = 'Other owner'; task.write_text(json.dumps(changed))
                self.assertTrue(c.check(root)[0]); task.write_bytes(original)
            old = root / 'tasks/APBRA-160-knowledge-lifecycle-20261012.json'; raw = old.read_bytes()
            old.write_bytes(raw + b'\n')
            self.assertTrue(any('File outside safe bootstrap scope: ' + name in c.check(root)[0] for name in names))
            old.unlink(); self.assertTrue(c.check(root)[0]); old.write_bytes(raw)
            with patch.dict(h, {'RELEASE_BOUND': False}): self.assertTrue(c.check(root)[0])
            self.assertEqual(c.check(root)[0], [])
            unknown = root / 'apps/api/src/apbra_api/foreign_drafts.py'; unknown.write_text('# Synthetic foreign source\n')
            self.assertIn('File outside safe bootstrap scope: apps/api/src/apbra_api/foreign_drafts.py', c.check(root)[0])

    def test_historical_knowledge_prospective_fixture_excludes_new_product_but_not_current_checks(self):
        import test_knowledge_lifecycle_20261012_scope as old_scope
        names = ['apps/api/src/apbra_api/knowledge_documents.py', 'apps/api/alembic/versions/20261013_09_tenant_knowledge_drafts.py', 'apps/api/tests/test_knowledge_documents.py']
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source'; source.mkdir(); self.copy(source)
            for name in names:
                path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('# Synthetic future draft file\n')
            case = old_scope.KnowledgeLifecycleScopeTests()
            selected = Path(directory) / 'historical'; selected.mkdir()
            # Source fixture needs the real immutable Git objects only for names.
            gitdir = ROOT / '.git'
            (source / '.git').write_text('gitdir: ' + str(gitdir.resolve()) + '\n')
            with patch.object(old_scope, 'ROOT', source): case.copy(selected)
            self.assertTrue(all(not (selected / name).exists() for name in names))
            with case.prospective(selected):
                self.assertEqual(case.check(selected), [])
            complete = Path(directory) / 'complete'; complete.mkdir(); self.copy(complete)
            for name in names:
                path = complete / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('# Synthetic future draft file\n')
            with case.prospective(complete):
                errors = c.check(complete)[0]
                self.assertTrue(any('File outside safe bootstrap scope: ' + name in errors for name in names))

if __name__ == '__main__':
    unittest.main()
