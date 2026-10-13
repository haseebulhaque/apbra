"""Exact current owner-authorized metadata integration; no runtime authority."""
P = {'apps/api/src/apbra_api/foundry_metadata_projection.py', 'scripts/check_agent_details_20261013.py', 'tests/bootstrap/test_agent_details_scope.py', 'apps/web/e2e/tenant-settings.spec.ts', 'apps/api/tests/test_tenant_settings.py', 'apps/web/src/api.ts', 'apps/web/src/EnterpriseApp.tsx', 'apps/api/src/apbra_api/api.py', 'apps/api/tests/test_foundry_agent_details.py', 'tasks/APBRA-160-agent-details-20261013.json', 'apps/web/src/api.test.ts', 'tests/bootstrap/test_tenant_document_drafts_20261013_scope.py', 'apps/api/tests/test_foundry_owner_metadata.py', 'scripts/check_bootstrap.py', 'apps/api/src/apbra_api/tenant_settings.py', 'apps/api/src/apbra_api/model_provider.py', 'apps/api/src/apbra_api/foundry_agent_details.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-selector-settings'
BASE = 'c2b0ed29f1d03be52498464b2a2d768b08770b8f'
TASK_SHA = '32a1886645f3863db6801a332ad976ad93ddb81cae810c64e624a999cef718bb'
GATES = {'requirements': 'd2ee0c09624da2cf0ec6f5698156dfdb953e7ba50f64f589bc6e570dbd371f68', 'adrs': '819273b12b9b3dc1e9f176aa02434646326099bbdb80f3493bd40a964b862e31', 'architecture_refs': 'ba52fae7e37a12f2f83a8a3813959d53998e09aa29514a68a6142b97826683ac', 'restricted_paths': '38f978ef6f23a74cabb87f5df6d9324cba025855c3bff3c7a46133eb406cd2f4', 'acceptance_criteria': 'e3cdf146cc95d0ce5c5341abecd761f3c712a69e003826b0237fae604bda2d86', 'verification_required': '0781f7246ac1363985e7d8718faf47b05fffa0ae726cfad43fb79d3f5b995e6a', 'out_of_scope': '39703a6a08f18180a74816060adc19c36f0d23f7635617feeb509e6d588eeba6', 'escalate_when': '2e7a79c28a4bac6ebd86b3535634a15ad40a5a54d756829faf62ea01e20e75bb', 'dependencies': 'b53634c0d4501c4de4f409d02ebdc7a26b1b99e25030617ab7e1448270e869f0', 'effective_release': '8cd0025243dc198d933fb707534b05bf1a8a62abd18d6c95aaa87f43817e6571', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'

def bind(root, catalog, sources, validate):
    return validate(root, catalog, sources, filename="APBRA-160-agent-details-20261013.json",
        label="agent details", branch=B, base=BASE, paths=P, task_sha=TASK_SHA,
        gates=GATES, source_bindings=SOURCES, sources_sha=SOURCES_SHA, count_label="seventeen")
HOOKS = [(1, 'n=runpy.run_path(str(Path(__file__).with_name("check_agent_details_20261013.py")))\n'), (1, "        agent_details, e = n['bind'](root, catalog, sources, bound_provider_registration)\n        errors += e\n"), (1, "            (agent_details, n['P']),\n"), (1, "                else agent_details if active_branch == n['B']\n"), (2, " and\n                    not (agent_details is not None and active_branch == n['B'] and changed_paths <= n['P'])")]

def strip_current_hooks(source):
    for count, hook in HOOKS:
        if source.count(hook) != count:
            raise ValueError("Current registration hook differs")
        source = source.replace(hook, "")
    return source

