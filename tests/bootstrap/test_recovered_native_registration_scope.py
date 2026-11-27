"""Public canonical phases preserve historical intent without private ancestry."""
import ast,copy,hashlib,json,os,re,runpy,shutil,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
H=runpy.run_path(ROOT/'scripts/check_recovered_native_registration.py')
C=runpy.run_path(ROOT/'scripts/check_bootstrap.py')
REGISTRATION_RELEASE = '257695d3931830f340f313c1c9ebcd305e7ae11d'
ACCOUNT_RELEASE = 'f3e241bbca1358b3cc24738f1a523cadc9a2066f'


def historical_git_blob(revision, path):
    return subprocess.check_output(
        ['git', '--no-replace-objects', 'show', f'{revision}:{path}'], cwd=ROOT,
    )


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
        # Each frozen map describes an earlier public release. The live tree is
        # checked separately below when it claims that earlier authority.
        for revision, expected in ((REGISTRATION_RELEASE, registration), (ACCOUNT_RELEASE, product)):
            inventory = {name: hashlib.sha256(historical_git_blob(revision, name)).hexdigest()
                         for name in H['REG_FIXTURES']}
            self.assertEqual(inventory, expected, revision)
        faults=C['check'](ROOT,active_task_id='APBRA-183',active_branch=H['R'],changed_paths=H['G'])[0]
        if H['v3_present'](ROOT):
            self.assertIn('V3 registration requires exact finite G41 CI/governance scope',faults)
            current_faults=C['check'](ROOT,active_task_id='APBRA-183',active_branch=H['R'],changed_paths=H['scope'](ROOT,'G'))[0]
            self.assertIn('V3 registration test-fixture phase differs',current_faults)
        else:
            self.assertIn('Public registration test fixtures differ from their frozen phase',faults)
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
        proof=H['V3']['registration_published'] if H['v3_present'](ROOT) else H['registration_published']
        git_failure=unittest.mock.Mock(side_effect=subprocess.CalledProcessError(1,['git']))
        with patch.dict(proof.__globals__,{'git':git_failure}):
            self.assertFalse(H['registration_published'](ROOT))
        git_failure.assert_called()
    def test_additional_approval_consumers_only_opt_into_the_existing_clock(self):
        case='apps/api/tests/test_native_case_files.py';response='apps/api/tests/test_native_response_integration.py'
        marker='@pytest.mark.usefixtures("approved_report_authorization_clock")\n'
        module='\npytestmark = pytest.mark.usefixtures("approved_report_authorization_clock")\n'
        frozen = H['manifest'](ROOT)
        for name,added in [(case,marker),(response,module)]:
            snapshot = historical_git_blob(REGISTRATION_RELEASE, name)
            account = historical_git_blob(ACCOUNT_RELEASE, name)
            self.assertEqual(hashlib.sha256(snapshot).hexdigest(), frozen['registration_fixture_files'][name])
            self.assertEqual(hashlib.sha256(account).hexdigest(), frozen['account_files'][name])
            registration=snapshot.decode();self.assertEqual(registration.count(added),1)
            before=historical_git_blob(H['BASE'], name).decode()
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

# Additive finite-stage cross-phase controls.
class AcceptedFiniteStageCrossPhase184(unittest.TestCase):
    def test_original_source_and_v3_helper_remain_byte_exact(self):
        for name in ['docs/source-register.json','scripts/check_ci_browser_registration_v3.py',
                'docs/engineering/recovered-native-frozen-manifests.json',
                'docs/engineering/recovered-native-frozen-manifests-v3.json']:
            self.assertEqual((ROOT/name).read_bytes(),subprocess.check_output(
                ['git','show','2d7fd0f2121c4bc6a6be6aa70ece317428168c28:'+name],cwd=ROOT))
    def test_registration_is_not_combined_with_another_task_or_product(self):
        stage=runpy.run_path(ROOT/'scripts/native_invitation_scope.py')
        scope=stage['G']
        for foreign in ['apps/api/src/apbra_api/api.py','apps/web/package.json','infrastructure/unissued.json']:
            self.assertTrue(C['check'](ROOT,active_task_id='APBRA-184',active_branch=stage['R'],changed_paths=scope|{foreign})[0])
        self.assertTrue(C['check'](ROOT,active_task_id='APBRA-85',active_branch=stage['R'],changed_paths=scope)[0])


@patch.dict(os.environ, GITHUB_HEAD_REF='', GITHUB_BASE_REF='', PR_HEAD_SHA='')
class ReleasedHistoricalFixtureCorrection(unittest.TestCase):
    def test_exact_correction_and_separate_signedin_product_on_physical_git_trees(self):
        from test_foundry_report_documentation_scope import (
            CHECKER, FROZEN, INVITE, INVITE_PATHS, MAIN, PRODUCT_PATHS, WRAPPER,
            ancestry_commit, check_query, commit, git, hosted_checkout, invitation_candidate,
            ordinary, point_main, ref,
        )
        from test_foundry_v10_signed_in_demo_scope import PRODUCT, SIGNED_IN, propose
        from test_native_invitation_release_readback import OVERLAP, PIN

        base = H['HISTORICAL_FIXTURE_BASE']
        branch = H['HISTORICAL_FIXTURE_BRANCH']
        paths = H['HISTORICAL_FIXTURE_PATHS']
        memory_test = 'apps/api/tests/test_foundry_memory_handoff.py'
        stylesheet = 'apps/web/src/style.css'
        self.assertEqual(paths, {WRAPPER, memory_test, 'tests/bootstrap/test_recovered_native_registration_scope.py',
                                 'tests/bootstrap/test_ci_browser_registration_v3_scope.py'})

        with tempfile.TemporaryDirectory(prefix='apbra-fixture-release-') as directory:
            root = Path(directory)
            git(root, 'init', '-q', '-b', 'main')
            git(root, 'fetch', '--no-tags', str(ROOT), base + ':' + MAIN, FROZEN + ':refs/fixtures/invitation')
            git(root, 'reset', '--hard', base)
            git(root, 'switch', '-c', branch)
            releases = git(ROOT, 'log', '--first-parent', '--format=%H', f'{base}..{MAIN}',
                           '--', WRAPPER).decode().splitlines()
            for path in paths:
                source = historical_git_blob(releases[-1], path) if releases else (ROOT / path).read_bytes()
                (root / path).write_bytes(source)
            head = commit(root, paths, 'Synthetic exact four-file fixture correction')
            checker = runpy.run_path(root / CHECKER)
            wrapper = runpy.run_path(root / WRAPPER)
            correction = ('APBRA-160', branch, paths)
            product = ('APBRA-160', PRODUCT, SIGNED_IN)
            main = (None, 'main', set())
            catalog = json.loads((root / 'agents/catalog.json').read_bytes())

            def allow_with_browser_witness(context):
                self.assertEqual(checker['delivery_context'](root), context)
                self.assertEqual(check_query(root, checker, *context), [])
                self.assertEqual(wrapper['qualified_paths'](root, checker, *context, OVERLAP, PIN),
                                 set(OVERLAP) | PRODUCT_PATHS)

            def allow_shape(context, protected, correction_release):
                self.assertEqual(checker['delivery_context'](root), context)
                self.assertEqual(wrapper['historical_fixture_state'](root),
                                 (protected, ref(root), correction_release))

            def deny_authority(context):
                _, faults = wrapper['stage_authorities'](
                    root, catalog, checker['schema_errors'], checker['task_errors'], *context,
                )
                self.assertTrue(faults, context)

            allow_with_browser_witness(correction)
            for wrong in (('APBRA-85', branch, paths), ('APBRA-160', branch, paths - {memory_test}),
                          ('APBRA-160', branch, paths | {stylesheet}), product):
                with self.subTest(context=wrong):
                    deny_authority(wrong)
            target = root / memory_test
            target.write_bytes(target.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'Historical fixture correction test bytes differ'):
                wrapper['historical_fixture_state'](root)
            git(root, 'restore', '--', memory_test)

            hosted_checkout(root, base, head)
            with patch.dict(os.environ, GITHUB_HEAD_REF=branch, GITHUB_BASE_REF='main', PR_HEAD_SHA=head):
                allow_shape(correction, base, None)
                with patch.dict(os.environ, PR_HEAD_SHA=base):
                    with self.assertRaisesRegex(ValueError, 'clean direct or hosted four-file candidate'):
                        wrapper['historical_fixture_state'](root)

            tree = ref(root, head + '^{tree}')
            wrong = ancestry_commit(root, tree, [head, base], f'Merge pull request #9961 from haseebulhaque/{branch}')
            point_main(root, wrong)
            with self.assertRaisesRegex(ValueError, 'requires its ordinary merge'):
                wrapper['historical_fixture_state'](root)
            released = ordinary(root, base, head, 9961, branch)
            allow_shape(main, released, released)

            # PR185's direct refresh intentionally brings the corrected main
            # in as the second parent of the original frozen invitation.
            refreshed = invitation_candidate(root, released)
            self.assertEqual(git(root, 'show', '-s', '--format=%P', refreshed).decode().split(),
                             [FROZEN, released])
            allow_shape(('APBRA-184', INVITE, INVITE_PATHS), released, released)
            entries = ('--', *sorted(paths))
            self.assertEqual(git(root, 'ls-tree', '-rz', refreshed, *entries),
                             git(root, 'ls-tree', '-rz', released, *entries))

            git(root, 'switch', '-c', INVITE + '-unissued')
            with self.assertRaisesRegex(ValueError, 'requires its ordinary merge'):
                wrapper['historical_fixture_state'](root)
            git(root, 'switch', INVITE)
            target.write_bytes(target.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'Historical fixture correction test bytes differ'):
                wrapper['historical_fixture_state'](root)
            git(root, 'restore', '--', memory_test)
            altered_path = sorted(INVITE_PATHS - {stylesheet})[0]
            altered = root / altered_path
            altered.write_bytes(altered.read_bytes() + b'\n')
            altered_head = commit(root, {altered_path}, 'Synthetic altered invitation source')
            false_refresh = ancestry_commit(root, ref(root, altered_head + '^{tree}'),
                                             [FROZEN, released], 'Synthetic false invitation refresh')
            git(root, 'reset', '--hard', false_refresh)
            with self.assertRaisesRegex(ValueError, 'Invitation refresh differs'):
                wrapper['historical_fixture_state'](root)

            git(root, 'switch', '-c', 'transient-fixture-drift', released)
            target.write_bytes(target.read_bytes() + b'\n')
            commit(root, {memory_test}, 'Synthetic transient correction edit')
            git(root, 'restore', '--source', released, '--', memory_test)
            reverted = commit(root, {memory_test}, 'Synthetic correction edit revert')
            self.assertEqual(git(root, 'ls-tree', '-rz', reverted, *entries),
                             git(root, 'ls-tree', '-rz', released, *entries))
            with self.assertRaisesRegex(ValueError, 'requires its ordinary merge'):
                wrapper['historical_fixture_state'](root)

            candidate = propose(root, released)
            allow_with_browser_witness(product)

            hosted_checkout(root, released, candidate)
            with patch.dict(os.environ, GITHUB_HEAD_REF=PRODUCT, GITHUB_BASE_REF='main', PR_HEAD_SHA=candidate):
                allow_shape(product, released, released)
                self.assertEqual(wrapper['signedin_product_parent'](root), (released, None))
            product_release = ordinary(root, released, candidate, 9962, PRODUCT)
            allow_shape(main, product_release, released)
            self.assertEqual(wrapper['signedin_product_parent'](root), (released, product_release))
            self.assertEqual(git(root, 'ls-tree', '-rz', 'HEAD', *entries),
                             git(root, 'ls-tree', '-rz', released, *entries))


if __name__ == '__main__':
    unittest.main()
