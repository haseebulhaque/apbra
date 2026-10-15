"""Finite material-settings context transition; no runtime activation authority."""
import hashlib
import json
import runpy
from pathlib import Path
GOV = ['scripts/check_bootstrap.py', 'scripts/check_gp.py', 'scripts/check_uf.py', 'scripts/check_sc.py', 'tasks/APBRA-160-settings-context-20261015.json', 'tests/bootstrap/test_settings_context_scope.py', 'tests/bootstrap/test_guided_preparation_scope.py']
PRODUCT = ['apps/api/src/apbra_api/application.py', 'apps/api/src/apbra_api/api.py', 'apps/api/src/apbra_api/foundry_report_runtime.py', 'apps/api/tests/test_api.py', 'apps/api/tests/test_foundry_report_runtime.py', 'apps/web/src/api.ts', 'apps/web/src/api.test.ts', 'apps/web/src/durableConversation.tsx', 'apps/web/src/durableConversation.test.tsx']
P = ['apps/api/src/apbra_api/api.py', 'apps/api/src/apbra_api/application.py', 'apps/api/src/apbra_api/foundry_report_runtime.py', 'apps/api/tests/test_api.py', 'apps/api/tests/test_foundry_report_runtime.py', 'apps/web/src/api.test.ts', 'apps/web/src/api.ts', 'apps/web/src/durableConversation.test.tsx', 'apps/web/src/durableConversation.tsx', 'scripts/check_bootstrap.py', 'scripts/check_gp.py', 'scripts/check_sc.py', 'scripts/check_uf.py', 'tasks/APBRA-160-settings-context-20261015.json', 'tests/bootstrap/test_guided_preparation_scope.py', 'tests/bootstrap/test_settings_context_scope.py']
B = 'agent/APBRA-DEVOPS/APBRA-160-settings-context'
BASE = '5a2989b6358b753c49f1390416c72493997bcb64'
TASK_SHA = '214ed5bb40e81aba09ef6d799778383dbea468cd3564cb707a50e346753e3063'
GATES = {'requirements': '59830b5e911fb0e8731f54ee9da6a2c35b93e13b4832dca2bca9007137c7bd0b', 'adrs': 'bb79e084583a0d87f2577ce4dbb0f5705628eef695474214916e8ad99251d3bd', 'architecture_refs': '61c6f2d16b9b40568de223d1a085afca73ea5c85e0eb2e9d9c29c71fc3d91d56', 'restricted_paths': '23136c6383cf6e99d71130df59b9e9fc489dc2f6fa1945ae33116fbfc02b6e1a', 'acceptance_criteria': 'bcb375309409c408e5676ddef165935c7baf09aaf40f91ecb0a22192ef7ff078', 'verification_required': '5f34dd64f2019f720aad0895d1918460e9aa26aceee1d22ab4f501ee34286258', 'out_of_scope': '2bfe8655894cde396b778890496b535fa76c7a9466389e490a23b65fd9f93247', 'escalate_when': 'e1b435966cf09b273313acfd90d84fef5f22c896ba6da845d6f1126dca479ba6', 'dependencies': '7a61fbfffd8bf3c7aa452bbf5a72b4579e588cd3151e3807cf772e59fe528938', 'effective_release': '29c9e465e0d2ff8bc1a6b0bdd61cea05c37ad90f28acf560826da52237a8f605', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
HOOKS = [(1, "sc=runpy.run_path(Path(__file__).parent/'check_sc.py')\n"), (1, "        st,es=sc['bind'](root,catalog,sources,bound_provider_registration);errors+=es\n"), (1, "(st,sc['P']),\n"), (1, "                else st if active_branch==sc['B']\n"), (2, " and not sc['ok'](st,active_branch,changed_paths)"), (1, "            errors+=sc['phase_errors'](st,active_branch,changed_paths)\n")]
GP_EDITS = [('def qualified_product_paths(root,checker):\n', "def qualified_product_paths(root,checker):\n    if callable(checker.get('delivery_context')) and checker['delivery_context'](root)[1]=='agent/APBRA-DEVOPS/APBRA-160-settings-context':\n        import runpy\n        from pathlib import Path\n        qualified=runpy.run_path(Path(__file__).with_name('check_sc.py'))['qualified_product_paths'](root,checker)\n        if qualified:return qualified|runpy.run_path(Path(__file__).with_name('check_uf.py'))['qualified_consumption'](root,checker)\n")]
UF_EDITS = [('def strip_hooks(source):\n', 'def strip_hooks(source):\n    if "sc=runpy.run_path(" in source:\n        import runpy\n        from pathlib import Path\n        source=runpy.run_path(Path(__file__).with_name(\'check_sc.py\'))[\'strip_hooks\'](source)\n'), ('def strip_gp_changes(source):\n', "def strip_gp_changes(source):\n    import runpy\n    from pathlib import Path\n    source=runpy.run_path(Path(__file__).with_name('check_sc.py'))['strip_gp_changes'](source)\n")]
GOV=set(GOV);PRODUCT=set(PRODUCT);P=set(P)
def bind(root,catalog,sources,validate):
    if (root/'tasks/APBRA-160-settings-context-20261015.json').is_symlink():return None,['Settings context task cannot be a symlink']
    return validate(root,catalog,sources,filename='APBRA-160-settings-context-20261015.json',label='settings context',branch=B,base=BASE,paths=P,task_sha=TASK_SHA,gates=GATES,source_bindings=SOURCES,sources_sha=SOURCES_SHA,count_label='sixteen')
def ok(task,branch,paths):return task is not None and branch==B and (paths==GOV or bool(paths) and paths<=PRODUCT)
def phase_errors(task,branch,paths):return ['Settings context requires exact governance or product-only phase'] if branch==B and not ok(task,branch,paths) else []
def inverse(source,edits):
    for before,after in edits:
        if source.count(after)!=1:raise ValueError('Settings context inverse differs')
        source=source.replace(after,before)
    return source
def strip_gp_changes(source):return inverse(source,GP_EDITS)
def strip_uf_changes(source):
    if "check_sp.py" in source:
        source=runpy.run_path(Path(__file__).with_name('check_sp.py'))['strip_uf_changes'](source)
    return inverse(source,UF_EDITS)
def strip_hooks(source):
    if "sp=runpy.run_path(" in source:
        source=runpy.run_path(Path(__file__).with_name('check_sp.py'))['strip_hooks'](source)
    for count,hook in HOOKS:
        if source.count(hook)!=count:raise ValueError('Settings context hook differs')
        source=source.replace(hook,'')
    return source
def qualified_product_paths(root,checker):
    if not callable(checker.get('delivery_context')) or not callable(checker.get('bound_provider_registration')) or not callable(checker.get('check')):return set()
    task_id,branch,paths=checker['delivery_context'](root)
    if task_id!='APBRA-160' or branch!=B or not paths or not paths<=PRODUCT:return set()
    task,errors=bind(root,json.loads((root/'agents/catalog.json').read_text()),json.loads((root/'docs/source-register.json').read_text()),checker['bound_provider_registration'])
    if errors or not ok(task,branch,paths):return set()
    errors,_=checker['check'](root,active_task_id=task_id,active_branch=branch,changed_paths=paths)
    return set() if errors else PRODUCT.copy()

# Release-transition test uses explicit missing ancestry; authority is unchanged.
