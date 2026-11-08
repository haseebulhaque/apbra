"""Public canonical phases preserve historical intent without private ancestry."""
import ast,copy,hashlib,json,re,runpy,shutil,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
H=runpy.run_path(ROOT/'scripts/check_recovered_native_registration.py')
C=runpy.run_path(ROOT/'scripts/check_bootstrap.py')
class RecoveredNativePublicRegistration(unittest.TestCase):
    def test_current_canonical_governance_only_phase_and_literal_scope(self):
        self.assertEqual((len(H['G']),len(H['Q']),len(H['N'])),(21,75,17))
        self.assertEqual(H['G']&H['Q'],H['REG_FIXTURES'])
        self.assertEqual(len(H['REG_FIXTURES']),7)
        self.assertTrue(all(name.startswith('apps/api/tests/') for name in H['REG_FIXTURES']))
        self.assertFalse(H['G']&H['N'])
        self.assertTrue(all(not name.startswith('apps/api/src/') for name in H['G']))
        self.assertTrue(all('*' not in n and '..' not in n.split('/') for n in H['G']|H['Q']|H['N']))
        frozen=H['manifest'](ROOT);registration=frozen['registration_fixture_files']
        product={name:frozen['account_files'][name] for name in H['REG_FIXTURES']}
        current={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in H['REG_FIXTURES']}
        self.assertIn(current,[registration,product])
        faults=C['check'](ROOT,active_task_id='APBRA-183',active_branch=H['R'],changed_paths=H['G'])[0]
        if H['v3_present'](ROOT):
            self.assertIn('V3 registration requires exact finite G40 CI/governance scope',faults)
            current_faults=C['check'](ROOT,active_task_id='APBRA-183',active_branch=H['R'],changed_paths=H['scope'](ROOT,'G'))[0]
            if current==registration:self.assertEqual(current_faults,[])
            else:self.assertIn('V3 registration test-fixture phase differs',current_faults)
        elif current==registration:self.assertEqual(faults,[])
        else:self.assertIn('Public registration test fixtures differ from their frozen phase',faults)
    def test_every_registration_omission_foreign_product_and_branch_is_rejected(self):
        for name in H['G']:
            self.assertTrue(H['errors'](ROOT,{}, {},{},H['R'],H['G']-{name}),name)
        for paths in [H['G']|{sorted(H['Q']-H['G'])[0]},H['G']|{'compose.yaml'},set()]:self.assertTrue(H['errors'](ROOT,{}, {},{},H['R'],paths))
        self.assertTrue(C['check'](ROOT,active_task_id='APBRA-183',active_branch=H['R']+'-foreign',changed_paths=H['G'])[0])
    def test_products_are_not_released_by_observed_hashes_or_registration(self):
        # Isolate the unmerged state; real main may legitimately advance later.
        with patch.dict(H['errors'].__globals__,{'registration_published':lambda root:False}):
            for branch,paths in [(H['QB'],H['Q']),(H['NB'],H['N'])]:
                self.assertEqual(H['errors'](ROOT,{}, {},{},branch,paths),['Public product registration is not effective on actual main'])
                self.assertTrue(H['errors'](ROOT,{}, {},{},branch,paths|{'compose.yaml'}))
            self.assertTrue(H['errors'](ROOT,None,{}, {},H['QB'],H['Q']))
        # An effective registration admits only complete matching account source.
        with patch.dict(H['errors'].__globals__,{'registration_published':lambda root:True,'files_match':lambda *a,**k:True}):
            self.assertEqual(H['errors'](ROOT,{}, {},{},H['QB'],H['Q']),[])
        with patch.dict(H['errors'].__globals__,{'registration_published':lambda root:True,'files_match':lambda *a,**k:False}):
            self.assertIn('differs from frozen',H['errors'](ROOT,{}, {},{},H['QB'],H['Q'])[0])
        with patch.dict(H['errors'].__globals__,{'registration_published':lambda root:True,'parent_released':lambda root:False}):
            self.assertIn('actually released',H['errors'](ROOT,{}, {},{},H['NB'],H['N'])[0])
    def test_task_bindings_cover_all_fields_and_historical_source_register(self):
        catalog=json.loads((ROOT/'agents/catalog.json').read_text());sources=json.loads((ROOT/'docs/source-register.json').read_text())
        self.assertFalse(H['bind'](ROOT,catalog,sources,C['schema_errors'],C['task_errors'])[3])
        for name,key in [(H['QT'],'QT_SHA'),(H['NT'],'NT_SHA'),(H['RT'],'RT_SHA')]:
            value=json.loads((ROOT/name).read_text());self.assertEqual(H['digest'](value),H[key])
            for field in value:
                changed=copy.deepcopy(value);changed[field]=None
                self.assertNotEqual(H['digest'](changed),H[key],field)
        changed=copy.deepcopy(sources);changed['sources'][0]['version']='CHANGED'
        self.assertTrue(H['bind'](ROOT,catalog,changed,C['schema_errors'],C['task_errors'])[3])
    def test_all_literal_product_paths_obey_canonical_card_and_restriction_precedence(self):
        catalog=json.loads((ROOT/'agents/catalog.json').read_text());card=next(row for row in catalog['cards'] if row['agent_id']=='APBRA-DEVOPS')
        for name in (H['QT'],H['NT'],H['RT']):
            task=json.loads((ROOT/name).read_text())
            for path in task['allowed_paths']:self.assertTrue(C['path_allowed'](path,task,card),(name,path))
        task=json.loads((ROOT/H['QT']).read_text());task['restricted_paths'].append('apps/api/pyproject.toml')
        self.assertFalse(C['path_allowed']('apps/api/pyproject.toml',task,card))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in (H['QT'],H['NT'],H['RT'],H['MANIFEST'],'contracts/engineering/task-contract.schema.json'):
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
            (root/H['QT']).write_text(json.dumps(task))
            sources=json.loads((ROOT/'docs/source-register.json').read_text())
            # Even a newly recomputed task hash cannot waive canonical restrictions.
            with patch.dict(H['bind'].__globals__,{'QT_SHA':H['digest'](task)}):
                faults=H['bind'](root,catalog,sources,C['schema_errors'],C['task_errors'])[3]
            self.assertIn('Public v2 allowed/restricted scope conflict',faults)
    def test_missing_symlink_and_unaccepted_tasks_never_grant_authority(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tasks').mkdir()
            self.assertEqual(H['bind'](root,{}, {},C['schema_errors'],C['task_errors'])[:3],(None,None,None))
            (root/H['RT']).symlink_to(ROOT/H['RT'])
            self.assertTrue(H['bind'](root,{}, {},C['schema_errors'],C['task_errors'])[3])
        self.assertFalse(H['ready']({'task_mode':'SPECIFICATION','readiness':'NEEDS_OWNER_ACCEPTANCE','owner_acceptance':'PENDING'}))
    def test_public_base_and_frozen_source_provenance_have_no_private_ancestry(self):
        self.assertEqual(H['BASE'],'444f4828c87a3a158fc102efae37196540cbbafa')
        for sha in ['36db1e8196499a8af0501d3ee1d46d690dfa5e7f','0751e1812b7fe5d844095f9d7dd1472ba00ea91e','b4f7bbe923187fee1b659a21a4093322e00337d9']:
            self.assertFalse(H['ancestor'](ROOT,sha,'HEAD'))
        value=H['manifest'](ROOT)
        self.assertEqual(set(value['account_files']),H['Q']);self.assertEqual(set(value['native_files']),H['N'])
        for expected in [*value['account_files'].values(),*value['native_files'].values(),*value['privacy_originals_sha256'].values()]:self.assertRegex(expected,r'^[0-9a-f]{64}$')
        self.assertFalse(any('business-journey-20261104' in n for n in H['G']))
    def test_typed_checksum_arrays_preserve_the_exact_logical_source_inventory(self):
        raw=json.loads((ROOT/H['MANIFEST']).read_text());self.assertEqual(raw['schema_version'],2)
        self.assertEqual(raw['hash_inventory_format'],'path-sha256-pairs-v1')
        for name in ['account_files','native_files','privacy_originals_sha256','registration_fixture_files']:
            self.assertIs(type(raw[name]),list)
            self.assertTrue(all(type(row) is list and len(row)==2 for row in raw[name]))
        logical=H['manifest'](ROOT)
        self.assertEqual(H['digest']({name:logical[name] for name in ['account_files','native_files','privacy_originals_sha256','registration_fixture_files']}),H['LOGICAL_INVENTORY_SHA'])
    def test_inventory_parser_rejects_ambiguous_duplicate_and_untyped_rows(self):
        sha='a'*64;valid=[['p',sha]]
        self.assertEqual(H['parse_inventory'](valid,{'p'}),{'p':sha})
        cases=[{'p':sha},[['p']],[['p',sha,'extra']],[['p',None]],[[None,sha]],[['p','G'*64]],[['p',sha],['p',sha]],[['other',sha]],[],['p',sha]]
        for value in cases:
            with self.subTest(value_type=type(value).__name__),self.assertRaises(ValueError):H['parse_inventory'](value,{'p'})
    def test_whole_previous_checker_and_native_helper_bytes_are_restored_exactly(self):
        for name,key in [('scripts/check_bootstrap.py','strip_bootstrap'),('scripts/check_nv.py','strip_nv')]:
            previous=subprocess.check_output(['git','show',H['BASE']+':'+name],cwd=ROOT,text=True)
            self.assertEqual(H[key]((ROOT/name).read_text()),previous)
        self.assertLessEqual((ROOT/'scripts/check_bootstrap.py').stat().st_size,262076)
        nv=runpy.run_path(ROOT/'scripts/check_nv.py');self.assertEqual(nv['PUBLIC_BOOT_EDITS'],H['BOOT_EDITS'])
        tree=ast.parse((ROOT/'scripts/check_bootstrap.py').read_text())
        appends=[n for n in ast.walk(tree) if isinstance(n,ast.AugAssign) and isinstance(n.target,ast.Name) and n.target.id=='bound_authorities']
        self.assertEqual(len(appends),1)
        self.assertEqual([n.elts[0].id for n in appends[0].value.elts],['pa','na','pg'])
    def test_every_new_hook_and_whitespace_inverse_rejects_missing_or_duplicate(self):
        for name,key,strip in [('scripts/check_bootstrap.py','BOOT_EDITS','strip_bootstrap'),('scripts/check_nv.py','NV_EDITS','strip_nv')]:
            source=(ROOT/name).read_text()
            for before,after in H[key]:
                for bad in [source.replace(after,'',1),source+after]:
                    with self.assertRaises(ValueError):H[strip](bad)
    def test_exact_test_only_c92_fixture_preserves_original_pin_and_production_checks(self):
        sp=runpy.run_path(ROOT/'scripts/check_sp.py')
        fixture=ROOT/'tests/bootstrap/fixtures/settings-release-proof-c92d488-application.txt'
        self.assertEqual(len(fixture.read_bytes()),67024)
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(),sp['PIN_HASHES'][0])
        self.assertIn("['git','merge-base','--is-ancestor',CANDIDATE,'HEAD']",(ROOT/'scripts/check_sp.py').read_text())
        self.assertIn("['git','show',CANDIDATE+':'+name]",(ROOT/'scripts/check_sp.py').read_text())
    def test_historical_git_producer_inverse_is_exact_and_cannot_erase_other_assertions(self):
        name='tests/bootstrap/test_tenant_document_drafts_20261013_scope.py';current=(ROOT/name).read_text()
        self.assertEqual(H['historical_fixture_source'](name,current),subprocess.check_output(['git','show',H['BASE']+':'+name],cwd=ROOT,text=True))
        for bad in [current.replace(H['FIXTURE_AFTER'],'',1),current+H['FIXTURE_AFTER'],current.replace("'--absolute-git-dir'","'--git-dir'",1)]:
            with self.assertRaises(ValueError):H['historical_fixture_source'](name,bad)
    def test_original_native_fixture_selector_and_all_nine_readbacks_are_frozen(self):
        public=runpy.run_path(ROOT/'scripts/check_nv.py')
        governance=subprocess.check_output(['git','log','-1','--no-merges','--format=%H',H['BASE'],'--','scripts/check_nv.py'],cwd=ROOT,text=True).strip()
        self.assertEqual(governance,'fed5c942cdafe057118ffc9b51dc114752ee52d7')
        for name in public['P']:
            self.assertEqual(H['historical_native_source'](ROOT,name),subprocess.check_output(['git','show',governance+':'+name],cwd=ROOT))
        name='tests/bootstrap/test_native_output_verification_20261019_scope.py';source=(ROOT/name).read_text()
        for before,after in H['PUBLIC_NATIVE_TEST_EDITS']:
            for bad in [source.replace(after,'',1),source+after]:
                with self.assertRaises(ValueError):H['inverse'](bad,H['PUBLIC_NATIVE_TEST_EDITS'])
    def test_shared_test_fixture_transition_needs_a_complete_released_product(self):
        frozen=H['manifest'](ROOT);G=H['G'];overlap=H['REG_FIXTURES']
        proof=H['_v2_registration_published'] if H['v3_present'](ROOT) else H['registration_published']
        # A synthetic main supplies exact G non-overlap bytes, never real refs.
        def blob(root,*args):
            prefix='origin/main:'
            self.assertEqual(args[0],'show');name=args[1][len(prefix):]
            self.assertIn(name,G-overlap)
            return (ROOT/name).read_bytes()
        for released in [False,True]:
            calls=[]
            def match(root,files,ref=None):
                calls.append(set(files))
                if set(files)==overlap:
                    expected={name:frozen['account_files'][name] for name in overlap} if released else frozen['registration_fixture_files']
                    self.assertEqual(files,expected);return True
                return released
            with patch.dict(proof.__globals__,{'ancestor':lambda *a:True,'git':blob,'files_match':match}):self.assertTrue(proof(ROOT))
        with patch.dict(proof.__globals__,{'ancestor':lambda *a:True,'git':blob,'files_match':lambda *a,**k:False}):self.assertFalse(proof(ROOT))
    def test_source_or_release_blob_errors_do_not_create_runtime_witness(self):
        nv=runpy.run_path(ROOT/'scripts/check_nv.py');args=(nv['OVERLAP'],nv['CANDIDATE'])
        # Missing immutable ancestry denies witnesses in every current branch phase.
        with patch.dict(H['qualified_paths'].__globals__,{'ancestor':lambda *a:False}):
            for identity,branch,paths in [('APBRA-183',H['R'],H['G']),('APBRA-160',H['QB'],H['Q']),('APBRA-183',H['NB'],H['N'])]:
                self.assertEqual(H['qualified_paths'](ROOT,C,identity,branch,paths,*args),set())
        with patch.dict(H['registration_published'].__globals__,{'git':lambda *args:(_ for _ in ()).throw(subprocess.CalledProcessError(1,['git']))}):
            self.assertFalse(H['registration_published'](ROOT))
    def test_additional_approval_consumers_only_opt_into_the_existing_clock(self):
        case='apps/api/tests/test_native_case_files.py';response='apps/api/tests/test_native_response_integration.py'
        marker='@pytest.mark.usefixtures("approved_report_authorization_clock")\n'
        module='\npytestmark = pytest.mark.usefixtures("approved_report_authorization_clock")\n'
        for name,added in [(case,marker),(response,module)]:
            frozen=H['manifest'](ROOT);current=(ROOT/name).read_bytes();expected=frozen['registration_fixture_files'][name]
            self.assertIn(hashlib.sha256(current).hexdigest(),{expected,frozen['account_files'][name]})
            commits=subprocess.check_output(['git','log','--format=%H','HEAD','--',name],cwd=ROOT,text=True).splitlines()
            snapshots=[subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT) for commit in commits]
            snapshots=[raw for raw in snapshots if hashlib.sha256(raw).hexdigest()==expected]
            self.assertTrue(snapshots,'Exact frozen Reg7 historical fixture snapshot is unavailable: '+name)
            registration=snapshots[0].decode();self.assertEqual(registration.count(added),1)
            before=subprocess.check_output(['git','show',H['BASE']+':'+name],cwd=ROOT,text=True)
            self.assertEqual(registration.replace(added,'',1),before)
            self.assertIn(name,H['G']&H['Q']);self.assertNotIn(name,H['N'])
            # Exact frozen readback preserves all original bodies, assertions and signatures in every phase.
            self.assertEqual(ast.dump(ast.parse(registration.replace(added,'',1))),ast.dump(ast.parse(before)))
    def test_navigation_source_amendment_is_exact_and_does_not_expand_registration(self):
        frozen=H['manifest'](ROOT);current=frozen['account_files'];extra='apps/web/e2e/tenant-settings.spec.ts';ui='apps/web/src/TenantDateTime.tsx'
        # Frozen prior-map commitments preserve exact Q74/N17/Reg7 provenance even after a squash merge.
        prior={name:sha for name,sha in current.items() if name!=extra}
        self.assertEqual(set(current)-set(prior),{extra})
        self.assertNotEqual(current[ui],'dcef6962145d75fb6d69ad987d791776e009211589e4a8377e75139c56f93712')
        prior[ui]='dcef6962145d75fb6d69ad987d791776e009211589e4a8377e75139c56f93712'
        self.assertEqual(H['digest'](prior),'29da7a92dac5c0255f0bb8ecdef58fada04eb05063caa38fba117a98f336bcf1')
        self.assertEqual(H['digest'](frozen['native_files']),'9d75706b3c13b288a864f3ac5b6811919a8b9955f0b7ee938d26f94006fd7fd1')
        self.assertEqual(H['digest'](frozen['registration_fixture_files']),'904b32abd66a61bf2da0272130edcb3f496d11db1c6567714579d7f3fca389b7')
        self.assertNotIn(extra,H['G']|H['N']);self.assertNotIn(ui,H['G']|H['N'])
        self.assertEqual(len(H['G']),21);self.assertEqual(len(H['REG_FIXTURES']),7)
if __name__=='__main__':unittest.main()
