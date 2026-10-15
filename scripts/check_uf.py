"""Exact published configuration consumption; no product/runtime authority."""
P = ['scripts/check_bootstrap.py', 'scripts/check_gp.py', 'scripts/check_uf.py', 'tasks/APBRA-160-released-runtime-fixtures-20261014.json', 'tests/bootstrap/test_released_runtime_fixture_scope.py']
B = 'agent/APBRA-DEVOPS/APBRA-160-released-runtime-fixtures'
BASE = '73db18d04b86f3c6c6549c6a045ac6fc861e42b9'
TASK_SHA = 'f8ae9886dfa67908724ab49ec6e6c5bd816ab8c93f1043a3db2d06577b8b7b9f'
GATES = {'requirements': '85ca49e516c020a0308d73e8953756aee0bb4c0588637bda8b9e811b9bc94821', 'adrs': '2ec7cbb1305deea40033f36b9a3599894986f5e0534f781b8ea2a319cad82971', 'architecture_refs': '495cf9fde48e00113a5bfd0fd00eb3f82e99a0107b4cc05c529caf849697ffda', 'restricted_paths': '111284abe57b1d0849b5bd09f67e01c3ae839708be94aacefda0eb31d6aee78b', 'acceptance_criteria': 'f4a9e507f222a1bc81a1d3f1f44f85a3fc597ec8360c91f4a678eca2f4100b1d', 'verification_required': 'fff06389e1dd2e8796d30ed9ee725b70a37e276a554a4620a5e97b38b8d35712', 'out_of_scope': '2538b6e895716eb393c3960c1c9025c18c9b89461e78213749f63551189b3a74', 'escalate_when': '899c7fcc9cfa1feba95115463cb87585b03b0a8709cc4900699b61b5713ac5ae', 'dependencies': 'e6ac0c6a49de895cbd1db3e215235aac40d3c6e5938a08042a79dd5f1681099b', 'effective_release': '474eb4717f2df25321249e16f1be486dbd9b24ade092838ca48dbcf48bdf1f2d', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction','8519682',28,'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'),('apbra-160-editable-first-draft-delivery','9404417',9,'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
CONFIG = 'apps/api/src/apbra_api/config.py'
CONFIG_SHA = '10c8c7f37d20a4fcb22a86d11dc7f14f8d1a342e33a2df331620618f71547510'
P = set(P)
HOOKS = [(1,"uf=runpy.run_path(Path(__file__).parent/'check_uf.py')\n"),
 (1,"        ut,eu=uf['bind'](root,catalog,sources,bound_provider_registration);errors+=eu\n"),
 (1,"(ut,uf['P']),\n"),(1,"                else ut if active_branch==uf['B']\n"),
 (2," and not uf['ok'](ut,active_branch,changed_paths)"),
 (1,"            errors+=uf['phase_errors'](ut,active_branch,changed_paths)\n")]

def bind(root,catalog,sources,validate):
    if (root/'tasks/APBRA-160-released-runtime-fixtures-20261014.json').is_symlink():
        return None,['Released-runtime fixture task cannot be a symlink']
    return validate(root,catalog,sources,filename='APBRA-160-released-runtime-fixtures-20261014.json',label='released runtime fixtures',branch=B,base=BASE,paths=P,task_sha=TASK_SHA,gates=GATES,source_bindings=SOURCES,sources_sha=SOURCES_SHA,count_label='five')

def ok(task,branch,paths):return task is not None and branch==B and paths==P

def phase_errors(task,branch,paths):
    return ['Released runtime fixtures require exact five-file governance-only scope'] if branch==B and paths and not ok(task,branch,paths) else []

def strip_hooks(source):
    if "sc=runpy.run_path(" in source:
        import runpy
        from pathlib import Path
        source=runpy.run_path(Path(__file__).with_name('check_sc.py'))['strip_hooks'](source)
    for count,hook in HOOKS:
        if source.count(hook)!=count:raise ValueError('Released runtime fixture hook differs')
        source=source.replace(hook,'')
    return source

def released_runtime_paths(root):
    # Exact immutable public release, not current-head repinning or branch trust.
    import hashlib
    import subprocess
    target=root/CONFIG
    if target.is_symlink() or any(p.is_symlink() for p in target.parents if p==root or root in p.parents):return set()
    try:
        raw=target.read_bytes()
        if len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=CONFIG_SHA:return set()
        result=subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        if result.returncode!=0:return set()
        original=subprocess.check_output(['git','show',BASE+':'+CONFIG],cwd=root,stderr=subprocess.DEVNULL,timeout=10)
        if hashlib.sha256(original).hexdigest()!=CONFIG_SHA:return set()
        return {CONFIG}
    except (OSError,subprocess.SubprocessError):return set()

GP_EDITS = [('def strip_current_hooks(source):\n', 'def strip_current_hooks(source):\n    if "uf=runpy.run_path(" in source:\n        import runpy\n        from pathlib import Path\n        source=runpy.run_path(Path(__file__).with_name(\'check_uf.py\'))[\'strip_hooks\'](source)\n'), ("    if task_id!='APBRA-160' or branch!=B or not paths or not paths<=PRODUCT:\n        return set()\n", "    if task_id!='APBRA-160' or branch!=B or not paths or not paths<=PRODUCT:\n        import runpy\n        from pathlib import Path\n        return runpy.run_path(Path(__file__).with_name('check_uf.py'))['qualified_consumption'](root,checker)\n")]


def strip_gp_changes(source):
    import runpy
    from pathlib import Path
    source=runpy.run_path(Path(__file__).with_name('check_sc.py'))['strip_gp_changes'](source)
    for before,after in GP_EDITS:
        if source.count(after)!=1:raise ValueError('Released consumption GP hook differs')
        source=source.replace(after,before)
    return source

def qualified_consumption(root,checker):
    import json
    import runpy
    from pathlib import Path
    try:
        if not callable(checker.get('bound_provider_registration')) or not callable(checker.get('delivery_context')):return set()
        actual=runpy.run_path(Path(__file__).with_name('check_bootstrap.py'))
        context=actual['delivery_context'](root)
        if checker['delivery_context'](root)!=context:return set()
        task_id,branch,paths=context
        errors,_=actual['check'](root,active_task_id=task_id,active_branch=branch,changed_paths=paths)
        if errors:return set()
        catalog=json.loads((root/'agents/catalog.json').read_text())
        sources=json.loads((root/'docs/source-register.json').read_text())
        own,errors=bind(root,catalog,sources,checker['bound_provider_registration'])
        if own is None or errors:return set()
        guided=runpy.run_path(Path(__file__).with_name('check_gp.py'))
        prior,errors=guided['bind'](root,catalog,sources,checker['bound_provider_registration'])
        if prior is None or errors:return set()
        return released_runtime_paths(root)
    except (OSError,ValueError):return set()
