"""Exact immutable released-source consumption and five-file governance phase."""
import ast,copy,hashlib,json,runpy,shutil,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
H=runpy.run_path(str(ROOT/'scripts/check_uf.py'))
C=runpy.run_path(str(ROOT/'scripts/check_bootstrap.py'))
NAME='tasks/APBRA-160-released-runtime-fixtures-20261014.json'

class ReleasedRuntimeFixtureScope(unittest.TestCase):
 def test_exact_five_file_registration_and_known_consumer_authority(self):
  task=json.loads((ROOT/NAME).read_text())
  self.assertEqual(set(task['allowed_paths']),H['P']);self.assertEqual(len(H['P']),5)
  errors,_=C['check'](ROOT,active_task_id='APBRA-160',active_branch=H['B'],changed_paths=H['P'])
  self.assertEqual(errors,[])
  # This registered UX authority remains distinct; no API edit admission.
  errors,_=C['check'](ROOT,active_task_id='APBRA-160',active_branch=C['DEMO_UX_BRANCH'],changed_paths={'apps/web/src/durableGeneration.tsx'})
  self.assertEqual(errors,[])
  errors,_=C['check'](ROOT,active_task_id='APBRA-160',active_branch=C['DEMO_UX_BRANCH'],changed_paths={H['CONFIG']})
  self.assertTrue(errors)
 def test_partial_mixed_foreign_and_product_scope_never_qualifies(self):
  for paths in [H['P']-{'scripts/check_uf.py'},H['P']|{'apps/web/src/durableGeneration.tsx'},{H['CONFIG']},{'compose.yaml'}]:
   with self.subTest(paths=paths):
    self.assertFalse(H['ok']({},H['B'],paths));self.assertTrue(H['phase_errors']({},H['B'],paths))
  self.assertFalse(H['ok']({},'agent/APBRA-DEVOPS/APBRA-160-unregistered',H['P']))
 def test_whole_task_and_all_protected_sections_are_bound(self):
  task=json.loads((ROOT/NAME).read_text());digest=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  self.assertEqual(digest(task),H['TASK_SHA'])
  for key,expected in H['GATES'].items():self.assertEqual(digest(task[key]),expected)
  for key in task:
   mutation=copy.deepcopy(task);mutation[key]=None;self.assertNotEqual(digest(mutation),H['TASK_SHA'])
 def test_whole_previous_checker_and_guided_helper_ast_preserved_by_exact_inverses(self):
  previous=lambda path:subprocess.check_output(['git','show',H['BASE']+':'+path],cwd=ROOT,text=True)
  current=(ROOT/'scripts/check_bootstrap.py').read_text()
  self.assertEqual(ast.dump(ast.parse(H['strip_hooks'](current))),ast.dump(ast.parse(previous('scripts/check_bootstrap.py'))))
  self.assertLessEqual(len(current.encode()),262076)
  guided=(ROOT/'scripts/check_gp.py').read_text()
  self.assertEqual(ast.dump(ast.parse(H['strip_gp_changes'](guided))),ast.dump(ast.parse(previous('scripts/check_gp.py'))))
  for count,hook in H['HOOKS']:
   for mutation in [current.replace(hook,'',1),current+hook]:
    with self.assertRaises(ValueError):H['strip_hooks'](mutation)
  for before,after in H['GP_EDITS']:
   for mutation in [guided.replace(after,'',1),guided+after]:
    with self.assertRaises(ValueError):H['strip_gp_changes'](mutation)
 def test_only_exact_published_configuration_is_consumed_on_other_branches(self):
  self.assertEqual(H['qualified_consumption'](ROOT,C),{H['CONFIG']})
  gp=runpy.run_path(str(ROOT/'scripts/check_gp.py'))
  for branch in ['main',C['DEMO_UX_BRANCH'],'agent/APBRA-DEVOPS/APBRA-160-unknown']:
   checker={**C,'delivery_context':lambda root,b=branch:('APBRA-160',b,{'apps/web/src/durableGeneration.tsx'})}
   self.assertEqual(gp['qualified_product_paths'](ROOT,checker),set())
 def test_missing_or_noncallable_callbacks_and_rejected_actual_context_fail_closed(self):
  for checker in [{},{'delivery_context':C['delivery_context']},{**C,'bound_provider_registration':None},{**C,'delivery_context':None}]:
   with self.subTest(keys=tuple(checker)):self.assertEqual(H['qualified_consumption'](ROOT,checker),set())
  actual={**C,'check':lambda *a,**kw:(['SYNTHETIC_REJECTED'],{})}
  original=runpy.run_path
  def load(path,*a,**kw):
   return actual if Path(path).name=='check_bootstrap.py' else original(path,*a,**kw)
  with patch('runpy.run_path',side_effect=load):self.assertEqual(H['qualified_consumption'](ROOT,C),set())
 def test_invalid_task_or_source_binding_cannot_consume_published_paths(self):
  checker={**C,'bound_provider_registration':lambda *a,**k:(None,['SYNTHETIC_INVALID_BINDING'])}
  self.assertEqual(H['qualified_consumption'](ROOT,checker),set())
  catalog=json.loads((ROOT/'agents/catalog.json').read_text());sources=json.loads((ROOT/'docs/source-register.json').read_text())
  sources['sources'][0]['version']=999999
  task,errors=H['bind'](ROOT,catalog,sources,C['bound_provider_registration']);self.assertIsNone(task);self.assertTrue(errors)
 def test_modified_missing_or_symlink_current_config_never_qualifies(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);target=root/H['CONFIG'];target.parent.mkdir(parents=True)
   self.assertEqual(H['released_runtime_paths'](root),set())
   target.write_bytes((ROOT/H['CONFIG']).read_bytes()+b'\n# changed\n')
   self.assertEqual(H['released_runtime_paths'](root),set())
   target.unlink();target.symlink_to(ROOT/H['CONFIG'])
   self.assertEqual(H['released_runtime_paths'](root),set())
 def test_hash_alone_without_exact_release_ancestor_is_not_qualified(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);target=root/H['CONFIG'];target.parent.mkdir(parents=True);target.write_bytes((ROOT/H['CONFIG']).read_bytes())
   self.assertEqual(H['released_runtime_paths'](root),set())
   with patch('subprocess.run',return_value=subprocess.CompletedProcess([],1)):
    self.assertEqual(H['released_runtime_paths'](root),set())
 def test_release_blob_lookup_failure_and_changed_release_bytes_fail_closed(self):
  with patch('subprocess.check_output',side_effect=subprocess.CalledProcessError(128,['git'])):
   self.assertEqual(H['released_runtime_paths'](ROOT),set())
  with patch('subprocess.check_output',return_value=b'SYNTHETIC_WRONG_RELEASE_BLOB'):
   self.assertEqual(H['released_runtime_paths'](ROOT),set())
 def test_prior_runtime_and_all_old_source_task_bytes_are_unchanged(self):
  paths=subprocess.check_output(['git','ls-tree','-r','--name-only',H['BASE']],cwd=ROOT,text=True).splitlines()
  for name in paths:
   if name not in H['P']:
    with self.subTest(name=name):self.assertEqual((ROOT/name).read_bytes(),subprocess.check_output(['git','show',H['BASE']+':'+name],cwd=ROOT))

if __name__=='__main__':unittest.main()
