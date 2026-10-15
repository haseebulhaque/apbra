"""Exact finite registration and preservation of prior authority."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
H=runpy.run_path(str(ROOT/'scripts/check_sc.py'))
C=runpy.run_path(str(ROOT/'scripts/check_bootstrap.py'))
NAME='tasks/APBRA-160-settings-context-20261015.json'
digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class SettingsContextScope(unittest.TestCase):
    def test_exact_finite_phases_and_prior_protected_files(self):
        task=json.loads((ROOT/NAME).read_text())
        self.assertEqual(set(task['allowed_paths']),H['P'])
        self.assertEqual((len(H['GOV']),len(H['PRODUCT']),len(H['P'])),(7,9,16))
        for paths in [H['GOV'],{'apps/api/src/apbra_api/application.py'},H['PRODUCT']]:
            errors,_=C['check'](ROOT,active_task_id='APBRA-160',active_branch=H['B'],changed_paths=paths)
            self.assertEqual(errors,[])
        for paths in [H['GOV']-{'scripts/check_sc.py'},H['P'],H['PRODUCT']|{'apps/api/src/apbra_api/persistence.py'},{'.github/workflows/bootstrap.yml'},{'apps/api/src/apbra_api/auth_boundary.py'}]:
            self.assertFalse(H['ok'](task,H['B'],paths))
            errors,_=C['check'](ROOT,active_task_id='APBRA-160',active_branch=H['B'],changed_paths=paths)
            self.assertTrue(errors)
        self.assertFalse(H['ok'](task,'agent/APBRA-DEVOPS/APBRA-160-foreign',H['PRODUCT']))
    def test_whole_task_sections_and_sources_are_bound(self):
        task=json.loads((ROOT/NAME).read_text())
        self.assertEqual(digest(task),H['TASK_SHA'])
        for key,expected in H['GATES'].items():self.assertEqual(digest(task[key]),expected)
        catalog=json.loads((ROOT/'agents/catalog.json').read_text());sources=json.loads((ROOT/'docs/source-register.json').read_text())
        for key in task:
            mutation=copy.deepcopy(task);mutation[key]=None
            self.assertNotEqual(digest(mutation),H['TASK_SHA'])
        changed=copy.deepcopy(sources);changed['sources'][0]['version']=999999
        bound,errors=H['bind'](ROOT,catalog,changed,C['bound_provider_registration'])
        self.assertIsNone(bound);self.assertTrue(errors)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'tasks').mkdir();(root/NAME).symlink_to(ROOT/NAME)
            bound,errors=H['bind'](root,catalog,sources,lambda *a,**k:self.fail('Symlink was read'))
            self.assertIsNone(bound);self.assertTrue(errors)
    def test_exact_inverses_preserve_previous_whole_checker_ast(self):
        for name,strip in [('scripts/check_bootstrap.py',H['strip_hooks']),('scripts/check_gp.py',H['strip_gp_changes']),('scripts/check_uf.py',H['strip_uf_changes'])]:
            actual=(ROOT/name).read_text();previous=subprocess.check_output(['git','show',H['BASE']+':'+name],cwd=ROOT,text=True)
            self.assertEqual(ast.dump(ast.parse(strip(actual))),ast.dump(ast.parse(previous)))
        current=(ROOT/'scripts/check_bootstrap.py').read_text()
        self.assertLessEqual(len(current.encode()),262076)
        for count,hook in H['HOOKS']:
            for mutation in [current.replace(hook,'',1),current+hook]:
                with self.assertRaises(ValueError):H['strip_hooks'](mutation)
        for name,key,strip in [('check_gp.py','GP_EDITS',H['strip_gp_changes']),('check_uf.py','UF_EDITS',H['strip_uf_changes'])]:
            current=(ROOT/'scripts'/name).read_text()
            for before,after in H[key]:
                for mutation in [current.replace(after,'',1),current+after]:
                    with self.assertRaises(ValueError):strip(mutation)
    def test_qualified_product_requires_exact_authority_and_full_check(self):
        checker={**C,'delivery_context':lambda root:('APBRA-160',H['B'],{'apps/api/src/apbra_api/application.py'})}
        self.assertEqual(H['qualified_product_paths'](ROOT,checker),H['PRODUCT'])
        self.assertFalse(H['qualified_product_paths'](ROOT,checker)&H['GOV'])
        for task,branch,paths in [('APBRA-27',H['B'],H['PRODUCT']),('APBRA-160','main',H['PRODUCT']),('APBRA-160',H['B'],H['GOV']),('APBRA-160',H['B'],set()),('APBRA-160',H['B'],H['P'])]:
            self.assertEqual(H['qualified_product_paths'](ROOT,{**C,'delivery_context':lambda root:(task,branch,paths)}),set())
        self.assertEqual(H['qualified_product_paths'](ROOT,{**checker,'check':lambda *a,**k:(['REJECTED'],{})}),set())
        self.assertEqual(H['qualified_product_paths'](ROOT,{}),set())
        with patch.dict(H['qualified_product_paths'].__globals__,{'bind':lambda *a:(None,['WITHDRAWN'])}):
            self.assertEqual(H['qualified_product_paths'](ROOT,checker),set())
    def test_registration_preserves_every_existing_non_governance_blob(self):
        _,branch,paths=C['delivery_context'](ROOT)
        # Audit the registration candidate itself; future product phase is separate.
        if branch!=H['B'] or paths!=H['GOV']:return
        names=subprocess.check_output(['git','ls-tree','-r','--name-only',H['BASE']],cwd=ROOT,text=True).splitlines()
        for name in names:
            if name not in H['GOV']:
                with self.subTest(name=name):
                    self.assertEqual((ROOT/name).read_bytes(),subprocess.check_output(['git','show',H['BASE']+':'+name],cwd=ROOT))

if __name__=='__main__':unittest.main()
