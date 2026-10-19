"""Finite already-authorized current-source witness; no runtime authority."""
import hashlib,json,runpy,subprocess
from pathlib import Path
P = {'tests/bootstrap/test_native_output_verification_20261019_scope.py', 'scripts/check_bootstrap.py', 'scripts/check_nv.py', 'tasks/APBRA-160-native-output-verification-20261019.json', 'scripts/check_dispatch_audit_20261019.py', 'tests/bootstrap/test_dispatch_audit_20261019_scope.py', 'scripts/check_sp.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-native-output-verification'
BASE = '93f145300f4002883cf48b8d5c6b0b28053489cb'
CANDIDATE = '15336b8c0ce628511b1dafef0aac9356ae7aeb89'
FILENAME = 'APBRA-160-native-output-verification-20261019.json'
TASK_SHA = 'eae3eecce6b93160a3dcb1102e406c459223890c9aea801b27065a140e60f144'
# Canonical digest of the public attribution text; this is a task binding.
GATES = {'schema_version': '6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b', 'task_id': '3763d9b604cd78c31fc718c1c496b2d6bc6e59465b0db87bb021814857590cb8', 'work_item_system': '00c978369cecd75539a692e4a7fdbe0bffbfc97525ef2fedb33465bd72f22cb0', 'execution_id': '638bca2c51b6a277d3cfae517ef1498f86d5caa99a40dddd06e69473222c6735', 'human_owner': '54f2a2a986034ada4ea531a38415dcd35b08b62f16e5eb6638225080cbf6b542', 'assigned_agent': '147a2ff6bedcf2bf79790001c78723b3edaa334d988f525ee2f82e9db8498f9c', 'agent_card_version': '5a4747fcdafec66d8d8812022e3b7d2666d886ec0e0ee7926ec8c50db40f29d5', 'risk_class': 'cb0314876ed8f3ae55780cabf10f4a8b458793c66979d8f2fe4faec57ec463c4', 'objective': 'd815192be0e57072fd76cf7ea7f775ead6104bb093432a12f5f923c1c6d88ead', 'requirements': 'c92556e5b28ed082712ffae93d4df233c0efb1e3e2399d567ab128f22524ee51', 'adrs': '8d6305199658c7b8f43912e7a2f53ffebb8c49b831b132cddfa14f6c2936b30e', 'architecture_refs': '045e888e46e896044e5451adccfe470c325be955d776ff54bdfa53787d7c9b42', 'allowed_paths': 'b6d0811b732230571f747f0fef4d2851e2fc22b8c3def1c66fb1c47a4e3cc983', 'restricted_paths': 'a9d45c2f2ad83e608e6cf1436c4daec035c5656063d490b0602f0276cc3d7b96', 'acceptance_criteria': '160562717d78b4cf79026ad98154b02df3c22fc45c196ead19997a7cd0383c47', 'verification_required': '8ec4e9d727e86afd242cee84e95c608499bb78c5e6ec3c7eca2e3adb5b2c7053', 'out_of_scope': 'cedd35f7a25b217bc473a2b9cc1963159eebe5e6081e7248f8056a8b412cb855', 'escalate_when': '248af1494b209a4d681382e28371ba149c8056e1e90b45a8e24f11f75c9dce91', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582', 'actual_authenticated_actor': hashlib.sha256(json.dumps('Codex/root owner delegated; local CLI Git uses existing host identity, no new remote identity asserted',sort_keys=True,separators=(',',':')).encode()).hexdigest(), 'human_initiator': '54f2a2a986034ada4ea531a38415dcd35b08b62f16e5eb6638225080cbf6b542', 'base_commit': '34c1e55d096776dc405da4fb55a5871b7edfdcd954efb8289a811f7a73da3da3', 'branch': '128187549a120cd39e72e97382de8d379a53585964986637e75a59eeb024018e', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'effective_release': 'd430ad60d4bf5cf7954b40d02b07f27ed4120cadf2a9077a73246d36873753d5', 'dependencies': '817901be107d8e4611bf0cedf12b68a448e823bdb923281b208c7d5ad72a1769'}
AUTHORITY = 'Owner-approved APBRA-160 MVP release continuation2026-10-19: fix bounded required-check failures for the already reviewed sixty-two-path native output and audit increment; register phase-aware historical-source verification only. Preserve all original task/source/card/history bytes, hashes, assertions and negative checks. No product scope expansion, policy waiver, paid AI, credential/settings change or production deployment.'
OVERLAP = {'apps/api/src/apbra_api/application.py': 'dd1357aa699b090ff5543c69f700e9ceb37559fa24bbb21cc2750033d270e747', 'apps/api/src/apbra_api/generation.py': '02dfc2332e7be7d7305089d2f904ed54c3743ebb9f38abb0695ca75ff8aaaea5', 'apps/api/src/apbra_api/model_provider.py': 'e36fc81d61f300cbecd811ae21b206e4decc7ab4917802bd8583f78848efd483', 'apps/api/src/apbra_api/persistence.py': 'bbe28e09fc1bc9acf8b35195df44e841db299df43d3875a5d783bbaff17076af'}
DISPATCH_RAW_SHA = '5167b79e4488c5cecf5baf786620317d9c50053cd766cff1e0f62a4666c016b4'
HOOKS = [(1, "nv=runpy.run_path(Path(__file__).parent/'check_nv.py')\n"), (1, "        nvt,ne=nv['bind'](root,catalog,sources,bound_provider_registration);errors+=ne\n"), (1, "(nvt,nv['P']),\n"), (1, "                else nvt if active_branch==nv['B']\n"), (2, " and not nv['ok'](nvt,active_branch,changed_paths)"), (1, "            errors+=nv['errors'](nvt,active_branch,changed_paths)\n")]
SP_EDITS = [('        if result.returncode!=0:return set()\n', "        if result.returncode!=0:return set()\n        qualified=runpy.run_path(Path(__file__).with_name('check_nv.py'))['qualified_current_paths'](root)\n        if qualified:return qualified\n")]
DISPATCH_EDITS = [('def strip_hooks(source):\n', 'def strip_hooks(source):\n    if "nv=runpy.run_path(" in source:\n        source=runpy.run_path(Path(__file__).with_name(\'check_nv.py\'))[\'strip_hooks\'](source)\n'), ('def strip_sp_changes(source):\n', 'def strip_sp_changes(source):\n    if "check_nv.py" in source:\n        source=runpy.run_path(Path(__file__).with_name(\'check_nv.py\'))[\'strip_sp_changes\'](source)\n'), ("        for name in [*selected, *additions, 'scripts/check_dispatch_audit_20261019.py']:\n", "        for name in [*selected, *additions, 'scripts/check_dispatch_audit_20261019.py', 'scripts/check_nv.py']:\n")]
RETAINED_CHECKER_COMMENTS = ['# Pinned append-only APBRA-177 source.', '# New scopes cannot rescue old ones.', '# Checked delivery context.', '# Validate before mkdir.', '# Descriptor traversal; no symlinks.', '# Cache exact strings only.', '# Release-transition test uses explicit missing ancestry; authority is unchanged.']

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def dispatch():return runpy.run_path(Path(__file__).with_name('check_dispatch_audit_20261019.py'))
def bind(root,catalog,sources,validate):
    target=root/'tasks'/FILENAME
    if not target.exists():return None,[]
    if target.is_symlink():return None,['Native verification task cannot be a symlink']
    d=dispatch()
    own,errors=validate(root,catalog,sources,filename=FILENAME,label='native output verification',branch=B,base=BASE,paths=P,task_sha=TASK_SHA,gates=GATES,source_bindings=d['SOURCES'],sources_sha=d['SOURCES_SHA'],count_label='seven')
    prior,failures=d['bind'](root,catalog,sources,validate);errors+=failures
    old=root/'tasks'/d['FILENAME']
    if prior is None or old.is_symlink() or not old.is_file() or hashlib.sha256(old.read_bytes()).hexdigest()!=DISPATCH_RAW_SHA:errors.append('Native verification original dispatch authority differs')
    if own is not None and own['requirements'][0]!=AUTHORITY:errors.append('Native verification owner authority differs')
    return (None if errors else own),errors
def ok(task,branch,paths):return task is not None and branch==B and paths==P
def errors(task,branch,paths):return ['Native verification requires exact seven-path governance scope'] if branch==B and not ok(task,branch,paths) else []
def inverse(source,edits):
    for before,after in edits:
        if source.count(after)!=1:raise ValueError('Native verification inverse differs')
        source=source.replace(after,before,1)
    return source
def strip_hooks(source):
    for count,hook in HOOKS:
        if source.count(hook)!=count:raise ValueError('Native verification hook differs')
        source=source.replace(hook,'')
    return source
def strip_sp_changes(source):return inverse(source,SP_EDITS)
def strip_dispatch_changes(source):return inverse(source,DISPATCH_EDITS)
DISPATCH_TEST_EDITS = [("        self.assertEqual(names,expected|{'scripts/check_dispatch_audit_20261019.py'})\n", "        self.assertEqual(names,expected|{'scripts/check_dispatch_audit_20261019.py','scripts/check_nv.py'})\n")]
def strip_dispatch_test_changes(source):return inverse(source,DISPATCH_TEST_EDITS)
def checker():return runpy.run_path(Path(__file__).with_name('check_bootstrap.py'))
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.DEVNULL,timeout=10)
def qualified_current_paths(root):
    try:
        c=checker();d=dispatch()
        if not all(callable(c.get(k)) for k in ('delivery_context','check','bound_provider_registration')):return set()
        own,failures=bind(root,json.loads((root/'agents/catalog.json').read_text()),json.loads((root/'docs/source-register.json').read_text()),c['bound_provider_registration'])
        if own is None or failures:return set()
        identity,branch,paths=c['delivery_context'](root)
        if identity=='APBRA-160' and branch==d['B'] and bool(paths) and paths<=d['P']:
            failures,_=c['check'](root,active_task_id=identity,active_branch=branch,changed_paths=paths)
            return set() if failures else set(OVERLAP)
        for ref in ('HEAD','origin/main'):
            result=subprocess.run(['git','merge-base','--is-ancestor',CANDIDATE,ref],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
            if result.returncode:return set()
        for name,expected in OVERLAP.items():
            target=root/name
            if not target.is_file():return set()
            if target.is_symlink() or any(p.is_symlink() for p in target.parents if p==root or root in p.parents):return set()
            raw=target.read_bytes()
            if len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=expected or hashlib.sha256(git(root,'show',CANDIDATE+':'+name)).hexdigest()!=expected:return set()
        return set(OVERLAP)
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError):return set()
