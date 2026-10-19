"""Consume one exact reviewed settings-context source after literal release ancestry."""
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
P = ['scripts/check_bootstrap.py', 'scripts/check_uf.py', 'scripts/check_sc.py', 'scripts/check_sp.py', 'tasks/APBRA-160-settings-release-proof-20261015.json', 'tests/bootstrap/test_settings_release_proof_scope.py', 'tests/bootstrap/test_released_runtime_fixture_scope.py']
B = 'agent/APBRA-DEVOPS/APBRA-160-settings-release-proof'
BASE = '4370d42f433969ade23b1806946b380e8b6c3d11'
CANDIDATE = 'c92d488793fb541f79b1fc8ab7637244d96c477b'
PIN_PATHS = ['apps/api/src/apbra_api/application.py']
PIN_HASHES = ['0fcd6ede465a37e3bbb3c9bd4ffc0d5e2825293135f3c0ecec5b4db1e7f7a6d4']
TASK_SHA = '969d0ea53f50de488c6c879f72fde6e5bd6d5b91d8bf3516dace5051d270b7a2'
GATES = {'requirements': 'a294c32116fdd442a729d0cc4cb487e73a75e6c61eae314bb06b5e5336145eec', 'adrs': 'c7a7b98e6972822b8a447056406a383cf7f56d70fccac02ca05e8fde2599a1c8', 'architecture_refs': '4d48ae96bdcaef2f3edbb879c1e7014897cdfc7fcb227d1cdfe5b6fed1beee12', 'restricted_paths': '111284abe57b1d0849b5bd09f67e01c3ae839708be94aacefda0eb31d6aee78b', 'acceptance_criteria': '165858a7798824029439863a7625580025803776fe2926536c32911275070a0b', 'verification_required': '3dc456774fa30876a77e870a6c8d8cc8c973510ee34ea33ae82e191af395ffe3', 'out_of_scope': 'a364953880922933c44dc9aac53798c88f52450187c4eeb9150a6990a6d63e67', 'escalate_when': '63ba8b447c900da9da9345b07372b7f993e49b7905f1a74c9519fc786387b555', 'dependencies': '788eb746ad4af4d68b6a546bbee3d43e020ccd29a4b9fd9e4cd2c3a115da7c02', 'effective_release': '77450688cccf4e4fa0cc6ac6294fcdd2d59f364979b2a961854ce917a246ec23', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
HOOKS = [(1, "sp=runpy.run_path(Path(__file__).parent/'check_sp.py')\n"), (1, "        spt,esp=sp['bind'](root,catalog,sources,bound_provider_registration);errors+=esp\n"), (1, "(spt,sp['P']),\n"), (1, "                else spt if active_branch==sp['B']\n"), (2, " and not sp['ok'](spt,active_branch,changed_paths)"), (1, "            errors+=sp['phase_errors'](spt,active_branch,changed_paths)\n")]
UF_EDITS = [('        return {CONFIG}\n', "        import runpy\n        from pathlib import Path\n        return {CONFIG}|runpy.run_path(Path(__file__).with_name('check_sp.py'))['released_product_paths'](root)\n")]
SC_EDITS = [('def strip_hooks(source):\n', 'def strip_hooks(source):\n    if "sp=runpy.run_path(" in source:\n        source=runpy.run_path(Path(__file__).with_name(\'check_sp.py\'))[\'strip_hooks\'](source)\n'), ('def strip_uf_changes(source):return inverse(source,UF_EDITS)\n', 'def strip_uf_changes(source):\n    if "check_sp.py" in source:\n        source=runpy.run_path(Path(__file__).with_name(\'check_sp.py\'))[\'strip_uf_changes\'](source)\n    return inverse(source,UF_EDITS)\n')]
P=set(P)
def bind(root,catalog,sources,validate):
    if (root/'tasks/APBRA-160-settings-release-proof-20261015.json').is_symlink():return None,['Settings release proof task cannot be a symlink']
    return validate(root,catalog,sources,filename='APBRA-160-settings-release-proof-20261015.json',label='settings release proof',branch=B,base=BASE,paths=P,task_sha=TASK_SHA,gates=GATES,source_bindings=SOURCES,sources_sha=SOURCES_SHA,count_label='seven')
def ok(task,branch,paths):return task is not None and branch==B and paths==P
def phase_errors(task,branch,paths):return ['Settings release proof requires exact governance-only scope'] if branch==B and paths and not ok(task,branch,paths) else []
def inverse(source,edits):
    for before,after in edits:
        if source.count(after)!=1:raise ValueError('Settings release proof inverse differs')
        source=source.replace(after,before)
    return source
def strip_uf_changes(source):
    if 'check_nv.py' in source:
        source=runpy.run_path(Path(__file__).with_name('check_nv.py'))['strip_uf_changes'](source)
    return inverse(source,UF_EDITS)
def strip_sc_changes(source):return inverse(source,SC_EDITS)
def strip_hooks(source):
    if "da=runpy.run_path(" in source:
        source=runpy.run_path(Path(__file__).with_name('check_dispatch_audit_20261019.py'))['strip_hooks'](source)
    for count,hook in HOOKS:
        if source.count(hook)!=count:raise ValueError('Settings release proof hook differs')
        source=source.replace(hook,'')
    return source
def released_product_paths(root):
    try:
        checker=runpy.run_path(Path(__file__).with_name('check_bootstrap.py'))
        own,errors=bind(root,json.loads((root/'agents/catalog.json').read_text()),json.loads((root/'docs/source-register.json').read_text()),checker['bound_provider_registration'])
        if own is None or errors:return set()
        result=subprocess.run(['git','merge-base','--is-ancestor',CANDIDATE,'HEAD'],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        if result.returncode!=0:return set()
        result=set()
        for name,expected in zip(PIN_PATHS,PIN_HASHES,strict=True):
            target=root/name
            if target.is_symlink() or any(parent.is_symlink() for parent in target.parents if parent==root or root in parent.parents):return set()
            raw=target.read_bytes()
            if len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=expected:return set()
            original=subprocess.check_output(['git','show',CANDIDATE+':'+name],cwd=root,stderr=subprocess.DEVNULL,timeout=10)
            if hashlib.sha256(original).hexdigest()!=expected:return set()
            result.add(name)
        return result
    except (OSError,ValueError,subprocess.SubprocessError):return set()

# Release-transition test uses explicit missing ancestry; authority is unchanged.
