"""Literal candidate/blob consumption cannot grant product edit authority."""
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
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
H=runpy.run_path(str(ROOT/'scripts/check_sp.py'))
C=runpy.run_path(str(ROOT/'scripts/check_bootstrap.py'))
NAME='tasks/APBRA-160-settings-release-proof-20261015.json'
APP=H['PIN_PATHS'][0]
digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class SettingsReleaseProofScope(unittest.TestCase):
    def test_exact_six_governance_paths_no_product_or_foreign_authority(self):
        task=json.loads((ROOT/NAME).read_text());self.assertEqual(set(task['allowed_paths']),H['P']);self.assertEqual(len(H['P']),6)
        errors,_=C['check'](ROOT,active_task_id='APBRA-160',active_branch=H['B'],changed_paths=H['P']);self.assertEqual(errors,[])
        for paths in [H['P']-{'scripts/check_sp.py'},H['P']|{APP},{APP},{'compose.yaml'},{'.github/workflows/bootstrap.yml'}]:
            self.assertFalse(H['ok'](task,H['B'],paths))
            errors,_=C['check'](ROOT,active_task_id='APBRA-160',active_branch=H['B'],changed_paths=paths);self.assertTrue(errors)
        self.assertFalse(H['ok'](task,'main',H['P']))
    def test_whole_task_and_every_gate_are_bound(self):
        task=json.loads((ROOT/NAME).read_text());self.assertEqual(digest(task),H['TASK_SHA'])
        for key,expected in H['GATES'].items():self.assertEqual(digest(task[key]),expected)
        for key in task:
            value=copy.deepcopy(task);value[key]=None;self.assertNotEqual(digest(value),H['TASK_SHA'])
        catalog=json.loads((ROOT/'agents/catalog.json').read_text());sources=json.loads((ROOT/'docs/source-register.json').read_text());sources['sources'][0]['version']=999999
        bound,errors=H['bind'](ROOT,catalog,sources,C['bound_provider_registration']);self.assertIsNone(bound);self.assertTrue(errors)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tasks').mkdir();(root/NAME).symlink_to(ROOT/NAME)
            bound,errors=H['bind'](root,catalog,sources,lambda *a,**k:self.fail('Symlink must not be read'));self.assertIsNone(bound);self.assertTrue(errors)
    def test_exact_inverses_preserve_previous_whole_checker_helpers_and_negative_hooks(self):
        for path,strip in [('scripts/check_bootstrap.py',H['strip_hooks']),('scripts/check_uf.py',H['strip_uf_changes']),('scripts/check_sc.py',H['strip_sc_changes'])]:
            previous=subprocess.check_output(['git','show',H['BASE']+':'+path],cwd=ROOT,text=True)
            actual=(ROOT/path).read_text();self.assertEqual(ast.dump(ast.parse(strip(actual))),ast.dump(ast.parse(previous)))
        current=(ROOT/'scripts/check_bootstrap.py').read_text();self.assertLessEqual(len(current.encode()),262076)
        for count,hook in H['HOOKS']:
            for mutation in [current.replace(hook,'',1),current+hook]:
                with self.assertRaises(ValueError):H['strip_hooks'](mutation)
        for path,key,strip in [('check_uf.py','UF_EDITS',H['strip_uf_changes']),('check_sc.py','SC_EDITS',H['strip_sc_changes'])]:
            source=(ROOT/'scripts'/path).read_text()
            for before,after in H[key]:
                for mutation in [source.replace(after,'',1),source+after]:
                    with self.assertRaises(ValueError):strip(mutation)
    def test_registration_does_not_consume_unreleased_candidate_or_allow_edit(self):
        # Missing ancestry is an explicit negative fixture, independent of
        # whether the actual checkout is before or after the product release.
        actual_run=subprocess.run
        def without_candidate(command,*args,**kwargs):
            if command==['git','merge-base','--is-ancestor',H['CANDIDATE'],'HEAD']:
                return subprocess.CompletedProcess(command,1)
            return actual_run(command,*args,**kwargs)
        with patch('subprocess.run',side_effect=without_candidate):
            self.assertEqual(H['released_product_paths'](ROOT),set())
            uf=runpy.run_path(str(ROOT/'scripts/check_uf.py'))
            self.assertEqual(uf['qualified_consumption'](ROOT,C),{'apps/api/src/apbra_api/config.py'})
    def fixture(self,folder):
        root=Path(folder)
        for name in [NAME,'agents/catalog.json','docs/source-register.json','contracts/engineering/task-contract.schema.json']:
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
        raw=subprocess.check_output(['git','show',H['CANDIDATE']+':'+APP],cwd=ROOT)
        target=root/APP;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        return root,target,raw
    def test_exact_candidate_ancestor_git_blob_current_blob_and_task_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root,target,raw=self.fixture(folder)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),H['PIN_HASHES'][0])
            with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0)) as ancestry,patch('subprocess.check_output',return_value=raw) as blob:
                self.assertEqual(H['released_product_paths'](root),{APP})
                self.assertEqual(ancestry.call_args.args[0],['git','merge-base','--is-ancestor',H['CANDIDATE'],'HEAD'])
                self.assertEqual(blob.call_args.args[0],['git','show',H['CANDIDATE']+':'+APP])
            with patch('subprocess.run',return_value=subprocess.CompletedProcess([],1)),patch('subprocess.check_output',side_effect=AssertionError('No blob after failed ancestry')):
                self.assertEqual(H['released_product_paths'](root),set())
            with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0)),patch('subprocess.check_output',return_value=b'WRONG_LITERAL_BLOB'):
                self.assertEqual(H['released_product_paths'](root),set())
            with patch('subprocess.run',side_effect=subprocess.TimeoutExpired(['git'],10)):
                self.assertEqual(H['released_product_paths'](root),set())
    def test_changed_missing_symlink_current_source_and_missing_or_mutated_binding_reject(self):
        with tempfile.TemporaryDirectory() as folder:
            root,target,raw=self.fixture(folder)
            with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0)),patch('subprocess.check_output',return_value=raw):
                target.write_bytes(raw+b'\n# unapproved\n');self.assertEqual(H['released_product_paths'](root),set())
                target.unlink();self.assertEqual(H['released_product_paths'](root),set())
                target.symlink_to(ROOT/APP);self.assertEqual(H['released_product_paths'](root),set())
                target.unlink();target.write_bytes(raw)
                task=json.loads((root/NAME).read_text());task['requirements']=[];(root/NAME).write_text(json.dumps(task));self.assertEqual(H['released_product_paths'](root),set())
                (root/NAME).unlink();self.assertEqual(H['released_product_paths'](root),set())
    def test_all_prior_product_and_task_bytes_preserved_in_governance_phase(self):
        _,branch,paths=C['delivery_context'](ROOT)
        if branch!=H['B'] or paths!=H['P']:return
        names=subprocess.check_output(['git','ls-tree','-r','--name-only',H['BASE']],cwd=ROOT,text=True).splitlines()
        for name in names:
            if name not in H['P']:
                with self.subTest(name=name):self.assertEqual((ROOT/name).read_bytes(),subprocess.check_output(['git','show',H['BASE']+':'+name],cwd=ROOT))

if __name__=='__main__':unittest.main()
