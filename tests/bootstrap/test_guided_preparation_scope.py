"""Finite registration, strict phases and retained runtime/privacy controls."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
H=runpy.run_path(str(ROOT/'scripts/check_gp.py'))
C=runpy.run_path(str(ROOT/'scripts/check_bootstrap.py'))
NAME='tasks/APBRA-160-guided-preparation-20261014.json'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class GuidedPreparationScope(unittest.TestCase):
    def test_exact_scope_and_governance_only_registration(self):
        task=json.loads((ROOT/NAME).read_text())
        self.assertEqual(set(task['allowed_paths']),H['P'])
        self.assertEqual((len(H['GOV']),len(H['PRODUCT']),len(H['P'])),(10,29,39))
        errors,_=C['check'](ROOT,active_task_id='APBRA-160',active_branch=H['B'],changed_paths=H['GOV'])
        self.assertEqual(errors,[])
    def test_product_only_scope_is_selected_without_cumulative_governance(self):
        errors,_=C['check'](ROOT,active_task_id='APBRA-160',active_branch=H['B'],changed_paths={'apps/api/src/apbra_api/foundry_cost_limits.py'})
        self.assertEqual(errors,[])
    def test_partial_mixed_foreign_or_empty_phase_is_rejected(self):
        for paths in [H['P'],H['GOV']-{'scripts/check_gp.py'},H['GOV']|{'compose.yaml'},
                      {'apps/api/src/apbra_api/main.py'},set()]:
            with self.subTest(paths=sorted(paths)):
                self.assertTrue(H['phase_errors']({},H['B'],paths))
                errors,_=C['check'](ROOT,active_task_id='APBRA-160',active_branch=H['B'],changed_paths=paths)
                self.assertEqual(bool(errors),bool(paths))
    def test_foreign_branch_cannot_claim_new_product_files(self):
        errors,_=C['check'](ROOT,active_task_id='APBRA-160',active_branch='agent/APBRA-DEVOPS/APBRA-160-unregistered',changed_paths={'apps/api/src/apbra_api/foundry_cost_limits.py'})
        self.assertTrue(errors)
    def test_new_scope_is_last_and_cannot_mask_or_rescue_previous_bound_scope(self):
        source=(ROOT/'scripts/check_bootstrap.py').read_text()
        self.assertLess(source.index("(rt,rr['P']),"),source.index("(gt,gp['P']),"))
        path='apps/api/src/apbra_api/foundry_report_runtime.py'
        task=json.loads((ROOT/NAME).read_text());bootstrap=json.loads((ROOT/'tasks/APBRA-85-bootstrap.json').read_text())
        catalog=json.loads((ROOT/'agents/catalog.json').read_text());card=next(c for c in catalog['cards'] if c['agent_id']=='APBRA-DEVOPS')
        self.assertFalse(C['whole_tree_safe'](path,bootstrap,(),((None,{path}),(task,H['P'])),card))
    def test_complete_task_and_every_gate_are_pinned(self):
        task=json.loads((ROOT/NAME).read_text())
        self.assertEqual(digest(task),H['TASK_SHA'])
        for key,expected in H['GATES'].items():self.assertEqual(digest(task[key]),expected)
        for key in task:
            changed=copy.deepcopy(task);changed[key]=None
            self.assertNotEqual(digest(changed),H['TASK_SHA'])
    def test_real_binding_rejects_authority_mutation_and_symlink(self):
        catalog=json.loads((ROOT/'agents/catalog.json').read_text())
        sources=json.loads((ROOT/'docs/source-register.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'tasks').mkdir();(root/'contracts/engineering').mkdir(parents=True)
            shutil.copy2(ROOT/'contracts/engineering/task-contract.schema.json',root/'contracts/engineering/task-contract.schema.json')
            task=json.loads((ROOT/NAME).read_text());path=root/NAME
            for key in ['requirements','allowed_paths','branch','base_commit','owner_acceptance','out_of_scope']:
                value=copy.deepcopy(task);value[key]=[] if isinstance(value[key],list) else 'UNQUALIFIED'
                path.write_text(json.dumps(value))
                bound,errors=H['bind'](root,catalog,sources,C['bound_provider_registration'])
                self.assertIsNone(bound);self.assertTrue(errors)
            path.unlink();path.symlink_to(ROOT/NAME)
            bound,errors=H['bind'](root,catalog,sources,lambda *args,**kwargs:self.fail('Symlink must reject before read'))
            self.assertIsNone(bound);self.assertTrue(errors)
    def test_source_register_change_is_rejected(self):
        catalog=json.loads((ROOT/'agents/catalog.json').read_text())
        sources=json.loads((ROOT/'docs/source-register.json').read_text())
        sources['sources'][0]['version']=999999
        bound,errors=H['bind'](ROOT,catalog,sources,C['bound_provider_registration'])
        self.assertIsNone(bound);self.assertTrue(errors)
    def test_whole_previous_checker_ast_and_byte_ceiling_preserved(self):
        current=(ROOT/'scripts/check_bootstrap.py').read_text()
        before=subprocess.check_output(['git','show',H['BASE']+':scripts/check_bootstrap.py'],cwd=ROOT,text=True)
        self.assertEqual(ast.dump(ast.parse(H['strip_current_hooks'](current))),ast.dump(ast.parse(before)))
        self.assertLessEqual(len(current.encode()),262076)
        for count,hook in H['HOOKS']:
            for mutation in [current.replace(hook,'',1),current+hook]:
                with self.assertRaises(ValueError):H['strip_current_hooks'](mutation)
        weakened=current.replace('return errors, manifest','return [], manifest',1)
        self.assertNotEqual(ast.dump(ast.parse(H['strip_current_hooks'](weakened))),ast.dump(ast.parse(before)))
    def test_registration_bytes_and_protected_current_sources_are_verified(self):
        _,branch,paths=C['delivery_context']()
        registration=(branch==H['B'] and paths==H['GOV'])
        allowed=H['qualified_product_paths'](ROOT,C)
        for name,expected in H['RETAINED'].items():
            with self.subTest(name=name):
                baseline=subprocess.check_output(['git','show',H['BASE']+':'+name],cwd=ROOT)
                self.assertEqual(hashlib.sha256(baseline).hexdigest(),expected)
                if registration or (name not in H['PRODUCT'] and name not in allowed):
                    self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),expected)
        if registration:
            for name in ['apps/api/src/apbra_api/foundry_private_preparation.py','apps/api/src/apbra_api/foundry_cost_limits.py']:
                self.assertFalse((ROOT/name).exists())
    def test_scope_never_grants_provider_activation_or_secret_access(self):
        task=json.loads((ROOT/NAME).read_text())
        self.assertEqual(task['restricted_paths'],json.loads((ROOT/'tasks/APBRA-160-report-runtime-20261014.json').read_text())['restricted_paths'][:4]+[
            'apps/api/alembic/**','apps/api/src/apbra_api/main.py','apps/api/src/apbra_api/application.py','apps/api/src/apbra_api/generation.py',
            'apps/api/src/apbra_api/auth_boundary.py','apps/api/src/apbra_api/authorization.py','apps/api/src/apbra_api/tenant_secrets.py','apps/api/src/apbra_api/persistence.py','infrastructure/**','local-data/**'])
        self.assertIn('built-in', ' '.join(task['requirements']).lower())
        self.assertIn('v21 generationEnabled is not active bounded runtime',' '.join(task['requirements']))

    def test_prospective_product_witness_excludes_protected_and_governance_paths(self):
        checker=dict(C)
        checker['delivery_context']=lambda root:('APBRA-160',H['B'],{'apps/api/src/apbra_api/config.py'})
        allowed=H['qualified_product_paths'](ROOT,checker)
        self.assertEqual(allowed,H['PRODUCT'])
        self.assertFalse(allowed & H['GOV'])
        self.assertFalse(allowed & (set(H['RETAINED'])-H['PRODUCT']))

    def test_current_pin_exception_rejects_invalid_actual_delivery_or_check(self):
        for task,branch,paths in [('APBRA-27',H['B'],H['PRODUCT']),
              ('APBRA-160','agent/APBRA-DEVOPS/APBRA-160-foreign',H['PRODUCT']),
              ('APBRA-160',H['B'],H['GOV']),('APBRA-160',H['B'],set()),
              ('APBRA-160',H['B'],H['PRODUCT']|{'compose.yaml'})]:
            checker={'delivery_context':lambda root:(task,branch,paths)}
            self.assertEqual(H['qualified_product_paths'](ROOT,checker),set())
        checker=dict(C)
        checker['delivery_context']=lambda root:('APBRA-160',H['B'],{'apps/api/src/apbra_api/config.py'})
        checker['check']=lambda *args,**kwargs:(['Rejected'],{})
        self.assertEqual(H['qualified_product_paths'](ROOT,checker),set())

    def test_withdrawn_binding_cannot_supersede_current_pins(self):
        from unittest.mock import patch
        checker=dict(C)
        checker['delivery_context']=lambda root:('APBRA-160',H['B'],{'apps/api/src/apbra_api/config.py'})
        witness=H['qualified_product_paths']
        with patch.dict(witness.__globals__,{'bind':lambda *args:(None,['Withdrawn'])}):
            self.assertEqual(witness(ROOT,checker),set())
