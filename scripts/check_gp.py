"""Finite guided private preparation scope; no runtime/spend authority."""
P = ['apps/api/src/apbra_api/api.py', 'apps/api/src/apbra_api/config.py', 'apps/api/src/apbra_api/foundry_agent_details.py', 'apps/api/src/apbra_api/foundry_browser_handoff.py', 'apps/api/src/apbra_api/foundry_cost_limits.py', 'apps/api/src/apbra_api/foundry_memory_handoff.py', 'apps/api/src/apbra_api/foundry_metadata_projection.py', 'apps/api/src/apbra_api/foundry_owner_metadata.py', 'apps/api/src/apbra_api/foundry_private_preparation.py', 'apps/api/src/apbra_api/foundry_report_runtime.py', 'apps/api/src/apbra_api/model_provider.py', 'apps/api/src/apbra_api/tenant_settings.py', 'apps/api/tests/test_api.py', 'apps/api/tests/test_foundry_agent_details.py', 'apps/api/tests/test_foundry_browser_handoff.py', 'apps/api/tests/test_foundry_browser_metadata.py', 'apps/api/tests/test_foundry_cost_limits.py', 'apps/api/tests/test_foundry_memory_handoff.py', 'apps/api/tests/test_foundry_owner_metadata.py', 'apps/api/tests/test_foundry_private_preparation.py', 'apps/api/tests/test_foundry_report_runtime.py', 'apps/api/tests/test_model_provider.py', 'apps/api/tests/test_tenant_settings.py', 'apps/web/src/EnterpriseApp.tsx', 'apps/web/src/EnterpriseUI.test.tsx', 'apps/web/src/api.test.ts', 'apps/web/src/api.ts', 'apps/web/src/privateCases.test.tsx', 'apps/web/src/privateCases.tsx', 'scripts/check_bootstrap.py', 'scripts/check_gp.py', 'tasks/APBRA-160-guided-preparation-20261014.json', 'tests/bootstrap/test_agent_details_scope.py', 'tests/bootstrap/test_browser_metadata_runtime_scope.py', 'tests/bootstrap/test_guided_preparation_scope.py', 'tests/bootstrap/test_memory_handoff_scope.py', 'tests/bootstrap/test_metadata_observations_scope.py', 'tests/bootstrap/test_report_runtime_scope.py', 'tests/bootstrap/test_tenant_document_drafts_20261013_scope.py']
GOV = ['scripts/check_bootstrap.py', 'scripts/check_gp.py', 'tasks/APBRA-160-guided-preparation-20261014.json', 'tests/bootstrap/test_agent_details_scope.py', 'tests/bootstrap/test_browser_metadata_runtime_scope.py', 'tests/bootstrap/test_guided_preparation_scope.py', 'tests/bootstrap/test_memory_handoff_scope.py', 'tests/bootstrap/test_metadata_observations_scope.py', 'tests/bootstrap/test_report_runtime_scope.py', 'tests/bootstrap/test_tenant_document_drafts_20261013_scope.py']
PRODUCT = ['apps/api/src/apbra_api/api.py', 'apps/api/src/apbra_api/config.py', 'apps/api/src/apbra_api/foundry_agent_details.py', 'apps/api/src/apbra_api/foundry_browser_handoff.py', 'apps/api/src/apbra_api/foundry_cost_limits.py', 'apps/api/src/apbra_api/foundry_memory_handoff.py', 'apps/api/src/apbra_api/foundry_metadata_projection.py', 'apps/api/src/apbra_api/foundry_owner_metadata.py', 'apps/api/src/apbra_api/foundry_private_preparation.py', 'apps/api/src/apbra_api/foundry_report_runtime.py', 'apps/api/src/apbra_api/model_provider.py', 'apps/api/src/apbra_api/tenant_settings.py', 'apps/api/tests/test_api.py', 'apps/api/tests/test_foundry_agent_details.py', 'apps/api/tests/test_foundry_browser_handoff.py', 'apps/api/tests/test_foundry_browser_metadata.py', 'apps/api/tests/test_foundry_cost_limits.py', 'apps/api/tests/test_foundry_memory_handoff.py', 'apps/api/tests/test_foundry_owner_metadata.py', 'apps/api/tests/test_foundry_private_preparation.py', 'apps/api/tests/test_foundry_report_runtime.py', 'apps/api/tests/test_model_provider.py', 'apps/api/tests/test_tenant_settings.py', 'apps/web/src/EnterpriseApp.tsx', 'apps/web/src/EnterpriseUI.test.tsx', 'apps/web/src/api.test.ts', 'apps/web/src/api.ts', 'apps/web/src/privateCases.test.tsx', 'apps/web/src/privateCases.tsx']
B = 'agent/APBRA-DEVOPS/APBRA-160-guided-preparation'
BASE = '131e6bc9cb2a7fc7646d58d26fb0ac14e1748f94'
TASK_SHA = 'f8f824a1ad13c74d988446059234964352b42dbcb23a611c3386788327455708'
GATES = {'requirements': '3e5e7008ef647b64b398cd02e9686a23bedf45ccd8f7ef3dc54209057beb4987', 'adrs': 'f27c8f6dc945cc6375f9ac8833885d1f2ae87bfcb2741dd4b18a2aafc2441f62', 'architecture_refs': 'aa53221822d13f1ca0ad57999dfcbb9869c06532d17ea4e956bb2008e7503c9c', 'restricted_paths': '4ed07f126d6c6fd8990874b71bb317cd0177a34fd6b8d4d7fb1ef1ff3d51626c', 'acceptance_criteria': '114b85d6da8c96fd7cb0052d6fac107061dcbf4f9f729ce2cc57ebd45a9c1723', 'verification_required': '023812de156703e131e39d0132a3120ed2e828dbdfba2ee871e89009f45ce113', 'out_of_scope': '53431f71937e1d5ecb8167fccf7ed13556ad75a0136d23d80085bed541a7459f', 'escalate_when': '800cc137fe1c33eef97d88a3ddcd2730861e67f126a09e48cdb972dee78ad57b', 'dependencies': '7acaaa8e159736309942a75bbe307c0b4ed64f113839c127b21710c9add80f51', 'effective_release': '66313913e59ba94566abb276d09296cf06332b63e05bed8332ced8bbe1f2e0ea', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
PIN_PATHS = [
    'apps/api/src/apbra_api/api.py',
    'apps/api/src/apbra_api/config.py',
    'apps/api/src/apbra_api/foundry_agent_details.py',
    'apps/api/src/apbra_api/foundry_browser_handoff.py',
    'apps/api/src/apbra_api/foundry_memory_handoff.py',
    'apps/api/src/apbra_api/foundry_metadata_projection.py',
    'apps/api/src/apbra_api/foundry_owner_metadata.py',
    'apps/api/src/apbra_api/foundry_report_runtime.py',
    'apps/api/src/apbra_api/model_provider.py',
    'apps/api/src/apbra_api/tenant_settings.py',
    'apps/api/tests/test_api.py',
    'apps/api/tests/test_foundry_agent_details.py',
    'apps/api/tests/test_foundry_browser_handoff.py',
    'apps/api/tests/test_foundry_browser_metadata.py',
    'apps/api/tests/test_foundry_memory_handoff.py',
    'apps/api/tests/test_foundry_owner_metadata.py',
    'apps/api/tests/test_foundry_report_runtime.py',
    'apps/api/tests/test_model_provider.py',
    'apps/api/tests/test_tenant_settings.py',
    'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/EnterpriseUI.test.tsx',
    'apps/web/src/api.test.ts',
    'apps/web/src/api.ts',
    'apps/web/src/privateCases.test.tsx',
    'apps/web/src/privateCases.tsx',
    'apps/api/src/apbra_api/main.py',
    'apps/api/src/apbra_api/application.py',
    'apps/api/src/apbra_api/generation.py',
    'apps/api/src/apbra_api/auth_boundary.py',
    'apps/api/src/apbra_api/authorization.py',
    'apps/api/src/apbra_api/persistence.py',
    'apps/api/src/apbra_api/tenant_secrets.py',
    '.github/workflows/bootstrap.yml',
    'agents/catalog.json',
    'docs/source-register.json',
]
PIN_SHA256S = [
    '00674718942a8ab9f2746e6b60dff8408b5ca95050b8c9409a3d853543f6d10f',
    '78de10d5d6db9cd92d317cc9ffca52eb4f95a3f6a84ae2a5c9b44423d36b9e26',
    '32227bee0af12673753faabd97ca6dfa0df08f337c8d202aa84364ba67583a40',
    '58f0a7fa6980fa020805d06aa4d2fbcf7d0e2208d3e619605257a04a4b53f813',
    'b2ca368368ff858174bb920ced15fee6d9f0b738e4f48fd11c933e37f2298559',
    '11d3d5b8c13e64177786bac5ba84b4ab34fc655d2e8b42c310fab722630e2eae',
    'd23d75dff41611e7b58ca2ebd9f8c1236cec8c824b80bb5900ad8fd329452365',
    'fb7110ea9f07affc891928f158e2f814049232ab94f11d7554b3fd759b408121',
    '24fa770c795659e0d95d5431780067b3a7450841bb45381f7d5b51145063354f',
    'df030db277f434a9d9103a8a34ed85a90c21e06dc9885af251ca73386c6021af',
    '5305d2900e62faa94a983d747a0ee000b89191fbdf2ff58e107135ebbc62354b',
    'dc49b404c7f73e28bdea8f4792a4976e790c83262dcbb2b925b926b246362cf2',
    '48ba77b007395b878b872d90567ee2f4450224efa389fc9ef140d2534d178afe',
    'fb5e6358b471ca19426e8ede100fb23ffb834435eee39eb0bb42f23c339d681a',
    'e3892da26e9e5401adc4d541fde56a07cf3987edf0d04e7ef66acabb6a734673',
    '31692192b1501457f52dcc86f7075bf525d96a1948afa73adcacdfbc0f9be839',
    '3335b9b7aaac7a9075a913e335c73136445e5a99abbdfb6baf6cd91d56c3aef6',
    'fc3a1020502634c9538939cc5db0b255357d011f80cab9f1783bae2d5db02aa6',
    '29f3caa7c929e4c4d71e62836604d6fb87930e46db688a4772e4c3eef9e0847b',
    '1e0cd1772c275e90e54e59346d1aecb0c8da724ace4ea6c0a8bf4f4b87b1f75b',
    'e6ecd42a1fdbcd6db123e6576a869ea460265d9a8cdc69b00f4f19be6061f2fb',
    '8f68ea447195d1117433d3b4237e79d196410e5d213b9f339f9d1bafb9036673',
    'f59b40379f80ede9f3d35bede34b9a2a03769a3c2cab01de81f945f62e80f703',
    'ee2e05487d348a76f22189870aa7c0964359a9f7c75bd635f3476582747a16fd',
    '551d8ed611122809e889d8afd05978aa1ca04e491cf4ad80d8e4c4848f0cd868',
    'be916f0cb55779437d619e702b9d166e213a81bfabd2cf968ae9e4ed23fcb1f1',
    '7c6994e5cc4c5e01b640c5f9247663aacc16ab111ee89a7e238a88b6e1fbc2d8',
    'a3a94ebc976cd18880463a12b186f10d908ebe9613460bd257a7d97339171f49',
    'f0b82a7ca8f9ed5973263b9da54a6279b97e84f792e4f84cd62965b60b3376b9',
    'e0a4254704ad3acebbaf2b1ad7290130933825b8b92c4b9811e1cb1227b204e6',
    'e3aa2b3922c086bdf2bb0f236648e9624e312447acca828d15516bd198125669',
    '6f91a447711534860cbe7733d3ab86038dc163bc50e072b0ac683ba6c6ede2f2',
    '55314de4067db48231fdc9e5833c66be3cdf4c5594f4ce4aebbb4c1a708cb47d',
    'e8fcc0667f9e185e41617e1d2eb5da6d3c350844326bf3f56ddd58c6d843bce7',
    '086e26d0f83e76347ab709d8859dd013513240a4e86ee9861af2086f38bb0f3e',
]
RETAINED = dict(zip(PIN_PATHS,PIN_SHA256S,strict=True))
HOOKS = [(1, "gp=runpy.run_path(Path(__file__).parent/'check_gp.py')\n"), (1, "        gt,eg=gp['bind'](root,catalog,sources,bound_provider_registration);errors+=eg\n"), (1, "(gt,gp['P']),\n"), (1, "                else gt if active_branch==gp['B']\n"), (2, " and not gp['ok'](gt,active_branch,changed_paths)"), (1, "            errors+=gp['phase_errors'](gt,active_branch,changed_paths)\n")]

P=set(P);GOV=set(GOV);PRODUCT=set(PRODUCT)

def bind(root,catalog,sources,validate):
    if (root/"tasks/APBRA-160-guided-preparation-20261014.json").is_symlink():
        return None,["Guided preparation task cannot be a symlink"]
    return validate(root,catalog,sources,filename="APBRA-160-guided-preparation-20261014.json",label="guided private preparation",branch=B,base=BASE,paths=P,task_sha=TASK_SHA,gates=GATES,source_bindings=SOURCES,sources_sha=SOURCES_SHA,count_label="thirty-nine")
def ok(task,branch,paths):
    return task is not None and branch==B and (paths==GOV or bool(paths) and paths<=PRODUCT)
def phase_errors(task,branch,paths):
    if branch!=B:return []
    return [] if ok(task,branch,paths) else ['APBRA-160 guided preparation requires exact governance-only registration or product-only scope']
def strip_current_hooks(source):
    if "uf=runpy.run_path(" in source:
        import runpy
        from pathlib import Path
        source=runpy.run_path(Path(__file__).with_name('check_uf.py'))['strip_hooks'](source)
    for count,hook in HOOKS:
        if source.count(hook)!=count:raise ValueError('Guided preparation hook differs')
        source=source.replace(hook,'')
    return source

def qualified_product_paths(root,checker):
    if callable(checker.get('delivery_context')) and checker['delivery_context'](root)[1]=='agent/APBRA-DEVOPS/APBRA-160-settings-context':
        import runpy
        from pathlib import Path
        qualified=runpy.run_path(Path(__file__).with_name('check_sc.py'))['qualified_product_paths'](root,checker)
        if qualified:return qualified|runpy.run_path(Path(__file__).with_name('check_uf.py'))['qualified_consumption'](root,checker)
    """Supersede current pins only with actual bound, checked product delivery."""
    import json
    task_id,branch,paths=checker['delivery_context'](root)
    if task_id!='APBRA-160' or branch!=B or not paths or not paths<=PRODUCT:
        import runpy
        from pathlib import Path
        witness=runpy.run_path(Path(__file__).with_name('check_nv.py'))['qualified_for_checker'](root,checker)
        if witness:return witness|runpy.run_path(Path(__file__).with_name('check_uf.py'))['qualified_consumption'](root,checker)
        return runpy.run_path(Path(__file__).with_name('check_uf.py'))['qualified_consumption'](root,checker)
    task,errors=bind(root,json.loads((root/'agents/catalog.json').read_text()),
        json.loads((root/'docs/source-register.json').read_text()),
        checker['bound_provider_registration'])
    if errors or not ok(task,branch,paths):return set()
    errors,_=checker['check'](root,active_task_id=task_id,active_branch=branch,changed_paths=paths)
    return set() if errors else PRODUCT.copy()
