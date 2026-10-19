"""Only four already-authorized current sources supersede historical current pins."""
import ast,contextlib,copy,hashlib,json,os,runpy,shutil,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
H=runpy.run_path(str(ROOT/'scripts/check_nv.py'))
D=H['dispatch']();C=H['checker']();TASK=Path('tasks')/H['FILENAME']
class NativeOutputVerificationScope(unittest.TestCase):
 def check(self,root,paths=None,branch=None):return C['check'](root,active_task_id='APBRA-160',active_branch=branch or H['B'],changed_paths=H['P'] if paths is None else paths)[0]
 @contextlib.contextmanager
 def fixture(self,candidate=False):
  with tempfile.TemporaryDirectory(prefix='apbra-native-verification-') as t:
   root=Path(t)/'repo';env=dict(os.environ,GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1')
   subprocess.run(['git','clone','--no-hardlinks','--no-checkout',str(ROOT),str(root)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
   subprocess.run(['git','-C',str(root),'checkout','--detach',H['CANDIDATE'] if candidate else H['BASE']],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
   subprocess.run(['git','-C',str(root),'update-ref','refs/remotes/origin/main',H['BASE']],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
   for name in H['P']:
    source=ROOT/name;target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
   yield root
 def prospective(self,root,**changes):
  checker=dict(C);checker['delivery_context']=lambda r:('APBRA-160',D['B'],D['P'].copy());checker.update(changes)
  with patch.dict(H['qualified_current_paths'].__globals__,{'checker':lambda:checker}):return H['qualified_current_paths'](root)
 def test_literal_scope_source_and_history(self):
  self.assertEqual(len(H['P']),9);self.assertEqual(len(H['OVERLAP']),4);self.assertFalse(H['P'] & D['P']);self.assertEqual(len(D['P']),62)
  self.assertEqual(set(json.loads((ROOT/TASK).read_text())['allowed_paths']),H['P']);self.assertEqual(self.check(ROOT),[])
  for name,expected in {**D['HISTORY'],'tasks/'+D['FILENAME']:H['DISPATCH_RAW_SHA']}.items():
   self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),expected)
   self.assertEqual((ROOT/name).read_bytes(),subprocess.check_output(['git','show',H['BASE']+':'+name],cwd=ROOT))
 def test_complete_previous_ast_and_hook_inverses(self):
  source=(ROOT/'scripts/check_bootstrap.py').read_text();self.assertLessEqual(len(source.encode()),262076)
  for name,inverse in [('scripts/check_bootstrap.py','strip_hooks'),('scripts/check_sp.py','strip_sp_changes'),('scripts/check_uf.py','strip_uf_changes'),('scripts/check_gp.py','strip_gp_changes'),('scripts/check_dispatch_audit_20261019.py','strip_dispatch_changes'),('tests/bootstrap/test_dispatch_audit_20261019_scope.py','strip_dispatch_test_changes')]:
   current=(ROOT/name).read_text();previous=subprocess.check_output(['git','show',H['BASE']+':'+name],cwd=ROOT,text=True)
   self.assertEqual(ast.dump(ast.parse(H[inverse](current))),ast.dump(ast.parse(previous)))
  for count,hook in H['HOOKS']:
   for changed in (source.replace(hook,'',1),source+hook):
    with self.assertRaises(ValueError):H['strip_hooks'](changed)
 def test_governance_scope_cannot_admit_product_or_foreign_files(self):
  for name in H['P']:self.assertTrue(self.check(ROOT,H['P']-{name}))
  for paths in (H['P']|{next(iter(D['P']))},H['P']|{'compose.yaml'},D['P'],set()):self.assertTrue(H['errors'](json.loads((ROOT/TASK).read_text()),H['B'],paths))
  self.assertTrue(self.check(ROOT,H['P'],'agent/APBRA-DEVOPS/APBRA-160-foreign'))
 def test_prospective_witness_is_four_only_and_requires_actual_full_check(self):
  with self.fixture(candidate=True) as root:
   calls=[];actual=C['check']
   def check(*args,**kwargs):calls.append(kwargs);return actual(*args,**kwargs)
   self.assertEqual(self.prospective(root,check=check),set(H['OVERLAP']));self.assertEqual(len(calls),1)
   self.assertEqual(self.prospective(root,check=lambda *a,**k:(['Rejected'],{})),set())
   for context in [('APBRA-27',D['B'],D['P']),('APBRA-160',D['R'],D['G']),('APBRA-160',D['B'],set()),('APBRA-160',D['B'],D['P']|{'compose.yaml'}),('APBRA-160','agent/APBRA-DEVOPS/APBRA-160-foreign',D['P'])]:
    self.assertEqual(self.prospective(root,delivery_context=lambda r:context),set())
 def test_missing_or_mutated_task_history_and_source_fail_closed(self):
  with self.fixture(candidate=True) as root:
   for name in (TASK,Path('tasks')/D['FILENAME'],Path(next(iter(D['HISTORY']))),Path('docs/source-register.json'),Path('agents/catalog.json')):
    p=root/name;before=p.read_bytes();p.unlink();self.assertEqual(self.prospective(root),set());p.write_bytes(before)
   p=root/TASK;before=p.read_bytes();p.unlink();p.symlink_to(ROOT/TASK);self.assertEqual(self.prospective(root),set());p.unlink();p.write_bytes(before)
   original=json.loads(before)
   for field in ('requirements','allowed_paths','base_commit','owner_acceptance','branch','actual_authenticated_actor'):
    changed=copy.deepcopy(original);changed[field]=[] if isinstance(changed[field],list) else 'Changed';p.write_text(json.dumps(changed));self.assertEqual(self.prospective(root),set())
   p.write_bytes(before)
 def test_candidate_is_not_released_until_actual_main_contains_it(self):
  with self.fixture(candidate=True) as root:
   self.assertEqual(H['qualified_current_paths'](root),set())
   subprocess.run(['git','-C',str(root),'update-ref','refs/remotes/origin/main',H['CANDIDATE']],check=True)
   self.assertEqual(H['qualified_current_paths'](root),set(H['OVERLAP']))
   subprocess.run(['git','-C',str(root),'checkout','--detach',H['BASE']],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   self.assertEqual(H['qualified_current_paths'](root),set())
 def test_released_consumption_requires_each_exact_current_and_candidate_blob(self):
  with self.fixture(candidate=True) as root:
   subprocess.run(['git','-C',str(root),'update-ref','refs/remotes/origin/main',H['CANDIDATE']],check=True)
   self.assertEqual(H['qualified_current_paths'](root),set(H['OVERLAP']))
   for name in H['OVERLAP']:
    p=root/name;before=p.read_bytes();p.write_bytes(before+b'\n# Changed source\n');self.assertEqual(H['qualified_current_paths'](root),set());p.unlink();p.symlink_to(ROOT/name);self.assertEqual(H['qualified_current_paths'](root),set());p.unlink();p.write_bytes(before)
   with patch.dict(H['qualified_current_paths'].__globals__,{'git':lambda *a:b'Wrong candidate blob'}):self.assertEqual(H['qualified_current_paths'](root),set())

 def test_prior_settings_release_guard_still_bounds_actual_prospective_chain(self):
  with tempfile.TemporaryDirectory(prefix='apbra-native-sp-guard-') as t:
   root=Path(t)/'repo';env=dict(os.environ,GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1')
   def git(*args):return subprocess.run(['git','-C',str(root),*args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
   subprocess.run(['git','clone','--no-hardlinks',str(ROOT),str(root)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
   governance=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
   git('checkout','-B',D['B'],H['CANDIDATE'])
   git('-c','user.name=APBRA synthetic fixture','-c','user.email=apbra-fixture@example.invalid','merge','--no-ff',governance,'-m','Synthetic prospective composition only')
   git('update-ref','refs/remotes/origin/main',governance)
   checker=runpy.run_path(str(root/'scripts/check_bootstrap.py'));sp=runpy.run_path(str(root/'scripts/check_sp.py'));uf=runpy.run_path(str(root/'scripts/check_uf.py'));gp=runpy.run_path(str(root/'scripts/check_gp.py'))
   actual_run=subprocess.run
   def without_prior(command,*args,**kwargs):
    if command==['git','merge-base','--is-ancestor',sp['CANDIDATE'],'HEAD']:return subprocess.CompletedProcess(command,1)
    return actual_run(command,*args,**kwargs)
   with patch.dict(os.environ,{'GITHUB_HEAD_REF':D['B'],'GITHUB_BASE_REF':'main'}):
    identity,branch,paths=checker['delivery_context'](root)
    self.assertEqual((identity,branch,paths),('APBRA-160',D['B'],D['P']))
    self.assertEqual(checker['check'](root,active_task_id=identity,active_branch=branch,changed_paths=paths)[0],[])
    self.assertEqual(sp['released_product_paths'](root),set())
    self.assertEqual(uf['qualified_consumption'](root,checker),{uf['CONFIG']})
    self.assertEqual(gp['qualified_product_paths'](root,checker),{uf['CONFIG']}|set(H['OVERLAP']))
    wrong={**checker,'delivery_context':lambda root:('APBRA-160',D['B'],{'compose.yaml'})}
    helper=runpy.run_path(str(root/'scripts/check_nv.py'));self.assertEqual(helper['qualified_for_checker'](root,wrong),set())
    with patch('subprocess.run',side_effect=without_prior):
     self.assertEqual(sp['released_product_paths'](root),set())
     self.assertEqual(uf['qualified_consumption'](root,checker),{uf['CONFIG']})
     self.assertEqual(gp['qualified_product_paths'](root,checker),{uf['CONFIG']}|set(H['OVERLAP']))
