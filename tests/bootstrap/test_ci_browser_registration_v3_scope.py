"""Current v3 graph, source-state and immutable historical-boundary controls."""
import copy
from contextlib import contextmanager
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

def registration_fixture_blob(name):
    """Resolve the hash-frozen Reg7 phase without an unpublished commit identity."""
    expected=H['manifest'](ROOT)['registration_fixture_files'][name]
    current=(ROOT/name).read_bytes()
    if hashlib.sha256(current).hexdigest()==expected:return current
    commits=subprocess.check_output(['git','log','--format=%H','HEAD','--',name],cwd=ROOT,text=True).splitlines()
    for commit in commits:
        raw=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
        if hashlib.sha256(raw).hexdigest()==expected:return raw
    raise AssertionError('Exact Reg7 historical fixture is unavailable: '+name)


@contextmanager
def frozen_release_model(main_stage, current_stage):
    """Synthetic bytes/ref view only; never updates Git refs or claims real release."""
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        for name in H['G']|{'agents/catalog.json','docs/source-register.json','contracts/engineering/task-contract.schema.json'}:
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
            if name in H['REG_FIXTURES']:target.write_bytes(registration_fixture_blob(name))
            else:shutil.copyfile(ROOT/name,target)
        legacy=runpy.run_path(ROOT/'scripts/check_nv.py');candidate=legacy['CANDIDATE'];overlap=legacy['OVERLAP']
        candidate_blobs={name:subprocess.check_output(['git','show',candidate+':'+name],cwd=ROOT) for name in overlap}
        for name,expected in overlap.items():
            assert hashlib.sha256(candidate_blobs[name]).hexdigest()==expected
            if name not in H['Q']|H['N']:
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(candidate_blobs[name])
        account={name:('synthetic-account-fixture:'+name).encode() for name in H['Q']}
        native={name:('synthetic-native-fixture:'+name).encode() for name in H['N']}
        model=copy.deepcopy(H['manifest'](ROOT));model.update(product_status='FROZEN',account_files={name:hashlib.sha256(raw).hexdigest() for name,raw in account.items()},native_files={name:hashlib.sha256(raw).hexdigest() for name,raw in native.items()},account_observed_source='2'*40,native_observed_source='3'*40)
        (root/H['MANIFEST']).write_text(json.dumps(model,sort_keys=True))
        task_pins={}
        for name,key in [(H['QT'],'QT_SHA'),(H['NT'],'NT_SHA')]:
            task=json.loads((root/name).read_text());task.update(task_mode='IMPLEMENTATION',readiness='READY_FOR_IMPLEMENTATION')
            (root/name).write_text(json.dumps(task));task_pins[key]=H['digest'](task)
        registration={name:(root/name).read_bytes() for name in H['G']}
        main={} if main_stage=='missing' else dict(registration)
        if main_stage in ('account','native'):main.update(account)
        if main_stage=='native':main.update(native)
        if main_stage=='partial':main.update({name:account[name] for name in H['REG_FIXTURES']})
        if main_stage=='bad-governance':main[H['RT']]+=b'\n'
        if main_stage=='bad-fixture':main['apps/api/tests/test_native_case_files.py']+=b'\n'
        for files in ([account] if current_stage=='account' else [account,native] if current_stage=='native' else []):
            for name,raw in files.items():
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        state={'root':root,'model':model,'main':main,'candidate':candidate,'overlap':overlap,'candidate_blobs':candidate_blobs,'branch':H['QB'] if current_stage=='account' else H['NB'] if current_stage=='native' else H['R'],'identity':'APBRA-160' if current_stage=='account' else 'APBRA-183','paths':H['Q'] if current_stage=='account' else H['N'] if current_stage=='native' else H['G'],'bad_candidate':False,'bad_ancestry':False,'canonical_errors':[],'checks':0}
        def git(_root,*args):
            if args[0]!='show':raise AssertionError(args)
            ref,name=args[1].split(':',1)
            if ref==candidate:
                return candidate_blobs[name]+(b'changed' if state['bad_candidate'] else b'')
            if ref=='origin/main' and name in main:return main[name]
            raise subprocess.CalledProcessError(1,['git',*args])
        def ancestor(_root,sha,ref):
            return main_stage!='missing' and not (state['bad_ancestry'] and sha==candidate)
        def check(*args,**kwargs):
            state['checks']+=1
            return state['canonical_errors'],{}
        state['checker']={'delivery_context':lambda _root:(state['identity'],state['branch'],state['paths']),'schema_errors':C['schema_errors'],'task_errors':C['task_errors'],'check':check}
        def qualified():
            return H['qualified_paths'](root,state['checker'],state['identity'],state['branch'],state['paths'],overlap,candidate)
        state['qualified']=qualified
        with patch.dict(H['qualified_paths'].__globals__,dict(task_pins,manifest=lambda _root:model,git=git,ancestor=ancestor)):
            yield state


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
        self.assertEqual((len(H['G']), len(H['Q']), len(H['N']), len(H['REG_FIXTURES'])), (40, 80, 17, 7))
        self.assertEqual(H['G'] & H['Q'], H['REG_FIXTURES'])
        self.assertFalse(H['G'] & H['N'])
        self.assertFalse(any(name.startswith(('apps/api/src/', 'apps/web/')) for name in H['G']))
        frozen=H['manifest'](ROOT);current={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in H['REG_FIXTURES']}
        registration=frozen['registration_fixture_files'];product={name:frozen['account_files'][name] for name in H['REG_FIXTURES']} if frozen['product_status']=='FROZEN' else None
        self.assertTrue(current==registration or current==product)
        faults=C['check'](ROOT,active_task_id='APBRA-183',active_branch=H['R'],changed_paths=H['G'])[0]
        if current==registration:self.assertEqual(faults,[])
        else:self.assertIn('V3 registration test-fixture phase differs',faults)
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
        unfrozen=copy.deepcopy(H['manifest'](ROOT));unfrozen.update(product_status='NOT_FROZEN',account_files={},native_files={},account_observed_source=None,native_observed_source=None)
        # The veto is an isolated state model, independent of the working candidate's later freeze.
        with patch.dict(P['V3']['bind'].__globals__,{'manifest':lambda root:unfrozen}):
            parent,native,registration,faults=P['bind'](ROOT,catalog,sources,C['schema_errors'],C['task_errors'])
            self.assertFalse(faults);self.assertIsNone(parent);self.assertIsNone(native);self.assertIsNotNone(registration)
            for branch,paths in [(H['QB'],H['Q']),(H['NB'],H['N'])]:
                self.assertIn('NOT_FROZEN',P['errors'](ROOT,{}, {},{},branch,paths)[0])
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
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
                if name in H['REG_FIXTURES']:target.write_bytes(registration_fixture_blob(name))
                else:shutil.copyfile(ROOT/name,target)
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
                unfrozen=copy.deepcopy(H['manifest'](root));unfrozen.update(product_status='NOT_FROZEN',account_files={},native_files={},account_observed_source=None,native_observed_source=None)
                with patch.dict(H['bind'].__globals__, {key:H['digest'](task),'manifest':lambda root:unfrozen}):
                    result = H['bind'](root, catalog, sources, C['schema_errors'], C['task_errors'])
                    self.assertIsNone(result[0]); self.assertIsNone(result[1])
                path.write_bytes(raw)
            path = root / H['MANIFEST']; original = path.read_bytes(); value = json.loads(original)
            value.update(product_status='NOT_FROZEN',account_files=[],native_files=[],account_observed_source=None,native_observed_source=None)
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


    def test_frozen_release_chain_is_lawful_only_with_actual_registration_and_parent_states(self):
        # These are isolated synthetic source/ref views, never real release assertions.
        for main,current,expected in [('missing','account',False),('registration','account',True),('account','account',True),('registration','native',False),('account','native',True),('native','native',True),('partial','account',False),('bad-governance','account',False),('bad-fixture','account',False),('account','registration',False),('account','account-native-cross',False)]:
            phase='native' if current=='account-native-cross' else current
            with self.subTest(main=main,current=current),frozen_release_model(main,phase) as state:
                if current=='account-native-cross':state.update(branch=H['QB'],identity='APBRA-160',paths=H['Q'])
                result=state['qualified']()
                self.assertEqual(result,set(state['overlap']) if expected else set())
                if expected:self.assertEqual(state['checks'],1)
                if current=='native' and main in ('account','native'):
                    self.assertTrue(H['parent_released'](state['root']))
                    self.assertEqual(H['errors'](state['root'],{}, {},{},H['NB'],H['N']),[])

    def test_frozen_historical_supersession_requires_complete_released_current_source(self):
        for main,current,expected in [('registration','account',False),('account','account',True),('native','native',True),('partial','account',False)]:
            with self.subTest(main=main,current=current),frozen_release_model(main,current) as state:
                state.update(identity='APBRA-160',branch='agent/APBRA-DEVOPS/APBRA-160-historical-source-check',paths={'apps/api/src/apbra_api/config.py'})
                self.assertEqual(state['qualified'](),set(state['overlap']) if expected else set())

    def test_frozen_qualification_preserves_original_candidate_pins_context_and_all_checks(self):
        for defect in ('candidate-blob','candidate-ancestry','canonical-failure','current-source','current-protected','mismatched-context','unfrozen'):
            with self.subTest(defect=defect),frozen_release_model('account','native') as state:
                if defect=='candidate-blob':state['bad_candidate']=True
                elif defect=='candidate-ancestry':state['bad_ancestry']=True
                elif defect=='canonical-failure':state['canonical_errors']=['Rejected actual canonical check']
                elif defect=='current-source':
                    path=state['root']/'apps/web/src/style.css';path.write_bytes(path.read_bytes()+b'changed')
                elif defect=='current-protected':
                    path=state['root']/'apps/api/src/apbra_api/model_provider.py';path.write_bytes(path.read_bytes()+b'changed')
                elif defect=='mismatched-context':state['checker']['delivery_context']=lambda _root:('APBRA-183',H['NB'],set())
                elif defect=='unfrozen':state['model']['product_status']='NOT_FROZEN'
                self.assertEqual(state['qualified'](),set())

    def test_registration_phase_proof_transitions_only_after_whole_product_release(self):
        for main,expected in [('missing',False),('registration',True),('account',True),('native',True),('partial',False),('bad-governance',False),('bad-fixture',False)]:
            with self.subTest(main=main),frozen_release_model(main,'native') as state:
                self.assertEqual(H['registration_published'](state['root']),expected)

    def test_exact_historical_adapters_restore_647_bytes_and_reject_missing_duplicate_or_inexact(self):
        for name in H['HISTORICAL_COPY_MODULES']:
            current=(ROOT/'tests/bootstrap'/name).read_text()
            restored=H['strip_historical_copy_adapter'](name,current)
            self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),H['HISTORICAL_TEST_PREIMAGES'][name])
            for bad in (current.replace(H['HISTORICAL_COPY_ADAPTER'],'',1),current+H['HISTORICAL_COPY_ADAPTER'],current.replace("c.pn['workflow_projection']","c.pn['not_projection']",1)):
                with self.assertRaises(ValueError):H['strip_historical_copy_adapter'](name,bad)
        current=(ROOT/'tests/bootstrap/test_guided_preparation_scope.py').read_text();before,after=H['HISTORICAL_GUIDED_ADAPTER']
        restored=H['strip_historical_guided_adapter'](current)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),H['HISTORICAL_TEST_PREIMAGES']['test_guided_preparation_scope.py'])
        for bad in (current.replace(after,'',1),current+after,current.replace("C['pn']['workflow_projection']","C['pn']['not_projection']",1)):
            with self.assertRaises(ValueError):H['strip_historical_guided_adapter'](bad)

        current=(ROOT/'tests/bootstrap/test_historical_fixture_staging_20261012_scope.py').read_text();before,after=H['HISTORICAL_STAGING_AST_ADAPTER']
        restored=H['strip_historical_staging_adapter'](current)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),H['HISTORICAL_TEST_PREIMAGES']['test_historical_fixture_staging_20261012_scope.py'])
        for bad in (current.replace(after,'',1),current+after,current.replace("c.pn['V3']['strip_historical_copy_adapter']","c.pn['V3']['bad_inverse']",1)):
            with self.assertRaises(ValueError):H['strip_historical_staging_adapter'](bad)


    def test_composed_historical_fixtures_preserve_all_original_assertions_and_reject_corruption(self):
        cases=[('test_bootstrap.py','strip_historical_bootstrap_adapter',[H['HISTORICAL_BOOTSTRAP_ADAPTER']]),
               ('test_knowledge_lifecycle_20261012_scope.py','strip_historical_knowledge_adapter',H['HISTORICAL_KNOWLEDGE_ADAPTERS']),
               ('test_tenant_document_drafts_20261013_scope.py','strip_historical_tenant_adapter',[H['HISTORICAL_TENANT_ADAPTER']])]
        for name,function,pairs in cases:
            current=(ROOT/'tests/bootstrap'/name).read_text();restored=H[function](current)
            self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),H['HISTORICAL_TEST_PREIMAGES'][name])
            for original,added in pairs:
                self.assertEqual(current.count(added),1)
                for changed in (current.replace(added,'',1),current+added,current.replace(added,added+'# inexact adapter\n',1),current+'\n'):
                    with self.subTest(name=name),self.assertRaises(ValueError):H[function](changed)
        original=H['strip_historical_bootstrap_adapter']((ROOT/'tests/bootstrap/test_bootstrap.py').read_text())
        self.assertEqual(original,subprocess.check_output(['git','show',H['BASE']+':tests/bootstrap/test_bootstrap.py'],cwd=ROOT,text=True))
        current=(ROOT/'scripts/check_ci_policy.py').read_bytes();restored=H['historical_policy_source']('check_ci_policy.py',current)
        self.assertEqual(hashlib.sha256(restored).hexdigest(),H['HISTORICAL_POLICY_SHA'])
        self.assertEqual(restored,subprocess.check_output(['git','show',H['BASE']+':scripts/check_ci_policy.py'],cwd=ROOT))
        self.assertEqual(H['historical_policy_source']('other-helper.py',b'unmodified'),b'unmodified')
        wrapper=H['HISTORICAL_POLICY_APPEND']
        for changed in (current.replace(wrapper,b'',1),current+wrapper,current.replace(wrapper,wrapper.replace(b'validate_legacy',b'wrong_legacy'),1),current+b'\n'):
            with self.assertRaises(ValueError):H['historical_policy_source']('check_ci_policy.py',changed)
        current=(ROOT/'tests/bootstrap/test_tenant_document_drafts_20261013_scope.py').read_text()
        self.assertEqual(P['historical_fixture_source']('tests/bootstrap/test_tenant_document_drafts_20261013_scope.py',current),subprocess.check_output(['git','show',H['BASE']+':tests/bootstrap/test_tenant_document_drafts_20261013_scope.py'],cwd=ROOT,text=True))


if __name__ == '__main__':
    unittest.main()
