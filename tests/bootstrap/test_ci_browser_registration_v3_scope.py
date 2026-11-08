"""Current v3 graph, source-state and immutable historical-boundary controls."""
import copy
import hashlib
import itertools
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
H = runpy.run_path(ROOT / 'scripts/check_ci_browser_registration_v3.py')
P = runpy.run_path(ROOT / 'scripts/check_recovered_native_registration.py')
C = runpy.run_path(ROOT / 'scripts/check_bootstrap.py')
CI = runpy.run_path(ROOT / 'scripts/check_ci_policy.py')


def render(value):
    value = copy.deepcopy(value)
    value['on']['workflow_dispatch'] = None
    value['concurrency']['cancel-in-progress'] = True
    for job in value['jobs'].values():
        job['timeout-minutes'] = int(job['timeout-minutes'])
    return yaml.safe_dump(value, sort_keys=False)


class SplitCiPolicy(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / '.github/workflows/bootstrap.yml').read_text()
        self.doc = yaml.load(self.text, Loader=yaml.BaseLoader)

    def test_current_graph_has_only_existing_pins_full_checks_and_true_null_dispatch(self):
        self.assertEqual(CI['validate'](self.text), [])
        self.assertEqual(CI['validate'](render(self.doc)), [])
        self.assertEqual(set(self.doc['jobs']), {'governance', 'api', 'web', 'bootstrap'})
        self.assertEqual(self.doc['jobs']['bootstrap']['name'], 'APBRA Bootstrap Checks')
        self.assertEqual({job['timeout-minutes'] for job in self.doc['jobs'].values()}, {'45'})
        governance = self.doc['jobs']['governance']['steps']
        self.assertFalse(any(step.get('run', '').strip() == CI['API_INSTALL'] for step in governance))
        for command in CI['COMMANDS']:
            self.assertEqual(sum(step.get('run', '').strip() == command for step in governance), 1)
        self.assertEqual(self.doc['jobs']['api']['steps'][-1]['run'].strip(), CI['API_CHECK'])
        self.assertEqual(self.doc['jobs']['web']['steps'][-1]['run'].strip(), CI['WEB_COMMAND'])
        self.assertTrue(H['validate_workflow'](self.text.replace('  workflow_dispatch:\n', "  workflow_dispatch: ''\n", 1)))
        self.assertTrue(H['validate_workflow'](self.text.replace('timeout-minutes: 45', "timeout-minutes: '45'", 1)))

    def test_each_dependency_status_is_enforced_by_the_actual_aggregator_shell(self):
        job = self.doc['jobs']['bootstrap']
        self.assertEqual(job['needs'], ['governance', 'api', 'web'])
        self.assertEqual(job['if'], 'always()')
        command = job['steps'][0]['run']
        states = ['success', 'failure', 'cancelled', 'skipped', '', 'invalid']
        names = ['GOVERNANCE_RESULT', 'API_RESULT', 'WEB_RESULT']
        for values in itertools.product(states, repeat=3):
            result = subprocess.run(['/bin/bash', '-e', '-c', command], env=dict(zip(names, values)),
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertEqual(result.returncode == 0, values == ('success',) * 3, values)
        for omitted in names:
            env = {name: 'success' for name in names if name != omitted}
            self.assertNotEqual(subprocess.run(['/bin/bash', '-e', '-c', command], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode, 0)

    def test_missing_mutated_duplicated_and_reordered_jobs_or_steps_are_rejected(self):
        for key in self.doc['jobs']:
            value = copy.deepcopy(self.doc); del value['jobs'][key]
            self.assertTrue(CI['validate'](render(value)), key)
        for key in ('governance', 'api', 'web'):
            for index in range(len(self.doc['jobs'][key]['steps'])):
                value = copy.deepcopy(self.doc); del value['jobs'][key]['steps'][index]
                self.assertTrue(CI['validate'](render(value)), (key, index))
            value = copy.deepcopy(self.doc); value['jobs'][key]['steps'].reverse()
            self.assertTrue(CI['validate'](render(value)))
            value = copy.deepcopy(self.doc); value['jobs'][key]['steps'] *= 2
            self.assertTrue(CI['validate'](render(value)))
        value = copy.deepcopy(self.doc); value['jobs']['foreign'] = copy.deepcopy(value['jobs']['api'])
        self.assertTrue(CI['validate'](render(value)))

    def test_job_dependency_permissions_and_failure_suppression_mutations_fail_closed(self):
        for key in self.doc['jobs']:
            for field, mutated in [('if', 'false'), ('continue-on-error', 'true'), ('permissions', {'contents': 'write'}),
                                   ('runs-on', 'self-hosted'), ('timeout-minutes', '46'), ('strategy', {'matrix': {'x': ['only']}})]:
                value = copy.deepcopy(self.doc); value['jobs'][key][field] = mutated
                self.assertTrue(CI['validate'](render(value)), (key, field))
            for field, mutated in [('if', 'always()'), ('continue-on-error', 'true'), ('env', {'PATH': '/other'}),
                                   ('shell', 'bash'), ('timeout-minutes', '45')]:
                value = copy.deepcopy(self.doc); value['jobs'][key]['steps'][0][field] = mutated
                self.assertTrue(CI['validate'](render(value)), (key, field))
        for key in ('api', 'web'):
            value = copy.deepcopy(self.doc); value['jobs'][key]['needs'] = []
            self.assertTrue(CI['validate'](render(value)))
        for field in ('needs', 'if', 'env'):
            value = copy.deepcopy(self.doc); del value['jobs']['bootstrap'][field]
            self.assertTrue(CI['validate'](render(value)))
        value = copy.deepcopy(self.doc); value['jobs']['bootstrap']['steps'][0]['run'] += ' || true'
        self.assertTrue(CI['validate'](render(value)))
        for key in ('api', 'web'):
            value = copy.deepcopy(self.doc); value['jobs'][key]['steps'][-1]['run'] += ' || true'
            self.assertTrue(CI['validate'](render(value)))

    def test_duplicate_keys_events_secret_context_and_wrong_pins_are_rejected(self):
        self.assertTrue(CI['validate'](self.text + '\npermissions:\n  contents: write\n'))
        for key in ('governance', 'api', 'web'):
            for options in ({'fetch-depth': '1'}, {'persist-credentials': 'true'}, {'token': '${{ github.token }}'}):
                value = copy.deepcopy(self.doc); value['jobs'][key]['steps'][0]['with'].update(options)
                self.assertTrue(CI['validate'](render(value)))
            value = copy.deepcopy(self.doc); value['jobs'][key]['steps'][0]['uses'] += '-wrong'
            self.assertTrue(CI['validate'](render(value)))
        value = copy.deepcopy(self.doc); value['on']['pull_request']['paths'] = ['README.md']
        self.assertTrue(CI['validate'](render(value)))
        for secret in ('${{ secrets.TOKEN }}', "${{ secrets['TOKEN'] }}"):
            value = copy.deepcopy(self.doc); value['jobs']['governance']['steps'][3]['run'] = 'echo ' + secret
            self.assertTrue(CI['validate'](render(value)))
            self.assertIn('Privileged trigger/secret reference prohibited', C['workflow_errors'](render(value)))
        value = copy.deepcopy(self.doc); value['jobs']['bootstrap']['name'] = 'A different required context'
        self.assertTrue(CI['validate'](render(value)))
        value = copy.deepcopy(self.doc); value['jobs']['governance']['steps'][-1]['if'] = 'success()'
        self.assertTrue(CI['validate'](render(value)))

    def test_step_descriptions_do_not_change_policy_but_check_names_remain_bound(self):
        for job in self.doc['jobs'].values():
            for step in job['steps']:
                step['name'] = 'Description only'
        self.assertEqual(CI['validate'](render(self.doc)), [])


class CiBrowserRegistration(unittest.TestCase):
    def minimal_root(self, folder):
        root = Path(folder)
        names = [H['RT'], H['QT'], H['NT'], H['MANIFEST'], 'scripts/check_ci_browser_registration_v3.py',
                 'contracts/engineering/task-contract.schema.json', *H['IMMUTABLE_V2']]
        for name in names:
            target = root / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / name, target)
        return root

    def test_exact_versioned_scopes_preserve_all_v2_bytes_and_current_canonical_integration(self):
        self.assertEqual((len(H['G']), len(H['Q']), len(H['N']), len(H['REG_FIXTURES'])), (33, 80, 17, 7))
        self.assertEqual(H['G'] & H['Q'], H['REG_FIXTURES'])
        self.assertFalse(H['G'] & H['N'])
        self.assertFalse(any(name.startswith(('apps/api/src/', 'apps/web/')) for name in H['G']))
        self.assertEqual(C['check'](ROOT, active_task_id='APBRA-183', active_branch=H['R'], changed_paths=H['G'])[0], [])
        for name, expected in H['IMMUTABLE_V2'].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)
        for name in H['G']:
            self.assertTrue(H['errors'](ROOT, None, None, {}, H['R'], H['G'] - {name}), name)
        for foreign in sorted(H['Q'] - H['G'])[:2] + ['compose.yaml', 'docs/source-register.json']:
            self.assertTrue(H['errors'](ROOT, None, None, {}, H['R'], H['G'] | {foreign}), foreign)

    def test_only_exact_test_overlaps_belong_first_to_registration_while_product_is_unfrozen(self):
        self.assertEqual(P['scope'](ROOT,'Q'),H['Q']-H['REG_FIXTURES'])
        self.assertEqual(P['scope'](ROOT,'G'),H['G'])
        catalog=json.loads((ROOT/'agents/catalog.json').read_text());card=next(x for x in catalog['cards'] if x['agent_id']=='APBRA-DEVOPS')
        bootstrap=json.loads((ROOT/'tasks/APBRA-85-bootstrap.json').read_text());registration=json.loads((ROOT/H['RT']).read_text())
        test='apps/api/tests/test_report_authorization_clock.py';product=sorted(H['Q']-H['G'])[0]
        bound=((None,P['scope'](ROOT,'Q')),(None,H['N']),(registration,H['G']))
        self.assertTrue(C['whole_tree_safe'](test,bootstrap,(),bound,card))
        self.assertFalse(C['whole_tree_safe'](product,bootstrap,(),bound,card))
        self.assertFalse(C['whole_tree_safe'](test,bootstrap,(),((None,H['G']),),card))

    def test_unfrozen_products_and_missing_partial_or_mutated_helpers_never_admit_source(self):
        catalog = json.loads((ROOT / 'agents/catalog.json').read_text())
        sources = json.loads((ROOT / 'docs/source-register.json').read_text())
        parent, native, registration, faults = P['bind'](ROOT, catalog, sources, C['schema_errors'], C['task_errors'])
        self.assertFalse(faults); self.assertIsNone(parent); self.assertIsNone(native); self.assertIsNotNone(registration)
        self.assertEqual(H['manifest'](ROOT)['product_status'], 'NOT_FROZEN')
        for branch, paths in [(H['QB'], H['Q']), (H['NB'], H['N'])]:
            self.assertIn('NOT_FROZEN', P['errors'](ROOT, {}, {}, {}, branch, paths)[0])
        with tempfile.TemporaryDirectory() as folder:
            empty = Path(folder)
            for branch, paths in [(H['QB'], H['Q']), (H['NB'], H['N'])]:
                self.assertTrue(P['errors'](empty, {}, {}, {}, branch, paths))
            root = self.minimal_root(folder)
            helper = root / 'scripts/check_ci_browser_registration_v3.py'; original = helper.read_bytes()
            for mode in ('missing', 'changed', 'symlink'):
                helper.unlink()
                if mode == 'changed': helper.write_bytes(original + b'\n')
                elif mode == 'symlink': helper.symlink_to(ROOT / 'scripts/check_ci_browser_registration_v3.py')
                self.assertTrue(P['bind'](root, catalog, sources, C['schema_errors'], C['task_errors'])[3], mode)
                self.assertTrue(P['errors'](root, {}, {}, {}, H['QB'], H['Q']), mode)
                if helper.exists() or helper.is_symlink(): helper.unlink()
                helper.write_bytes(original)
            for name in (H['RT'], H['QT'], H['NT'], H['MANIFEST']):
                path = root / name; raw = path.read_bytes(); path.unlink()
                self.assertTrue(P['bind'](root, catalog, sources, C['schema_errors'], C['task_errors'])[3], name)
                path.write_bytes(raw)

    def test_all_v3_files_removed_together_and_unknown_product_branch_are_rejected(self):
        catalog=json.loads((ROOT/'agents/catalog.json').read_text());sources=json.loads((ROOT/'docs/source-register.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            root=self.minimal_root(folder)
            for name in (H['RT'],H['QT'],H['NT'],H['MANIFEST'],'scripts/check_ci_browser_registration_v3.py'):
                (root/name).unlink()
            self.assertFalse(P['v3_present'](root))
            for branch,paths in [(H['QB'],H['Q']),(H['NB'],H['N'])]:
                self.assertIn('missing',P['errors'](root,{}, {},{},branch,paths)[0])
        foreign=sorted(H['Q']-P['Q'])[0]
        faults=C['check'](ROOT,active_task_id='APBRA-160',active_branch=H['QB']+'-foreign',changed_paths={foreign})[0]
        self.assertTrue(faults)
        self.assertTrue(any('authority' in fault or 'scope' in fault for fault in faults))

    def test_registration_rejects_swapped_product_phase_metadata_and_changed_test_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.minimal_root(folder)
            for name in {'.github/workflows/bootstrap.yml'}|H['REG_FIXTURES']:
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
            with patch.dict(H['errors'].__globals__,{'ancestor':lambda *args:True}):
                self.assertEqual(H['errors'](root,None,None,{},H['R'],H['G']),[])
                name='apps/api/tests/test_native_case_files.py';path=root/name;path.write_bytes(path.read_bytes()+b'\n')
                self.assertIn('test-fixture phase differs',H['errors'](root,None,None,{},H['R'],H['G'])[0])
            path=root/H['MANIFEST'];value=json.loads(path.read_text());prior=json.loads((root/'docs/engineering/recovered-native-frozen-manifests.json').read_text())
            product=dict(prior['account_files']);value['registration_fixture_files']=[[name,product[name]] for name in sorted(H['REG_FIXTURES'])]
            raw=json.dumps(value).encode();path.write_bytes(raw)
            with patch.dict(H['manifest'].__globals__,{'MANIFEST_SHA':hashlib.sha256(raw).hexdigest()}):
                with self.assertRaisesRegex(ValueError,'immutable Reg7'):H['manifest'](root)

    def test_complete_contract_digest_status_inventory_and_immutable_bytes_are_independent_controls(self):
        catalog = json.loads((ROOT / 'agents/catalog.json').read_text()); sources = json.loads((ROOT / 'docs/source-register.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            root = self.minimal_root(folder)
            for name in (H['RT'], H['QT'], H['NT']):
                path = root / name; raw = path.read_bytes(); task = json.loads(raw)
                for field in task:
                    changed = copy.deepcopy(task); changed[field] = None
                    self.assertNotEqual(H['digest'](changed), H['digest'](task), (name, field))
                task.update(task_mode='IMPLEMENTATION', readiness='READY_FOR_IMPLEMENTATION')
                path.write_text(json.dumps(task))
                # Even a deliberately repinned ready product task cannot override NOT_FROZEN.
                key = 'QT_SHA' if name == H['QT'] else 'NT_SHA' if name == H['NT'] else 'RT_SHA'
                with patch.dict(H['bind'].__globals__, {key: H['digest'](task)}):
                    result = H['bind'](root, catalog, sources, C['schema_errors'], C['task_errors'])
                    self.assertIsNone(result[0]); self.assertIsNone(result[1])
                path.write_bytes(raw)
            path = root / H['MANIFEST']; original = path.read_bytes(); value = json.loads(original)
            for changes in ({'product_status': 'FROZEN'}, {'product_status': 'READY'}, {'account_observed_source': 'a'*40}, {'account_files': [['fake', '0'*64]]}):
                changed = copy.deepcopy(value); changed.update(changes); raw = json.dumps(changed).encode(); path.write_bytes(raw)
                with patch.dict(H['manifest'].__globals__, {'MANIFEST_SHA': hashlib.sha256(raw).hexdigest()}):
                    with self.assertRaises(ValueError): H['manifest'](root)
            path.write_bytes(original)
            name = next(iter(H['IMMUTABLE_V2'])); path = root / name; path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaises(ValueError): H['manifest'](root)

    def test_every_literal_path_obeys_card_and_restriction_precedence(self):
        catalog = json.loads((ROOT / 'agents/catalog.json').read_text()); card = next(x for x in catalog['cards'] if x['agent_id'] == 'APBRA-DEVOPS')
        for name in (H['RT'], H['QT'], H['NT']):
            task = json.loads((ROOT / name).read_text())
            for path in task['allowed_paths']:
                self.assertTrue(C['path_allowed'](path, task, card), (name, path))
        task = json.loads((ROOT / H['RT']).read_text()); task['restricted_paths'].append('.github/**')
        self.assertFalse(C['path_allowed']('.github/workflows/bootstrap.yml', task, card))

    def test_exact_inverses_ceiling_and_old_legacy_workflow_commitment_survive(self):
        for name, function in [('scripts/check_bootstrap.py', 'strip_bootstrap'), ('scripts/check_nv.py', 'strip_nv')]:
            self.assertEqual(P[function]((ROOT / name).read_text()), subprocess.check_output(['git', 'show', H['BASE']+':'+name], cwd=ROOT, text=True))
        self.assertLessEqual((ROOT / 'scripts/check_bootstrap.py').stat().st_size, 262076)
        self.assertEqual(hashlib.sha256(H['legacy_workflow']().encode()).hexdigest(), H['LEGACY_WORKFLOW_SHA'])
        self.assertEqual(CI['validate_legacy'](H['legacy_workflow']()), [])
        current = (ROOT / '.github/workflows/bootstrap.yml').read_text()
        self.assertEqual(H['workflow_projection'](ROOT, current), H['legacy_workflow']())
        self.assertEqual(H['workflow_projection'](ROOT, current+'\n'), current+'\n')


if __name__ == '__main__':
    unittest.main()
