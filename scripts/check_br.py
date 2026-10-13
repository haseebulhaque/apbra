"""Exact browser metadata-only runtime source scope; no execution authority."""
P = {'apps/api/src/apbra_api/foundry_browser_metadata.py', 'scripts/check_bootstrap.py', 'apps/api/src/apbra_api/api.py', 'tests/bootstrap/test_browser_metadata_runtime_scope.py', 'tests/bootstrap/test_metadata_observations_scope.py', 'tests/bootstrap/test_agent_details_scope.py', 'apps/api/tests/test_foundry_browser_metadata.py', 'tests/bootstrap/test_tenant_document_drafts_20261013_scope.py', 'scripts/check_br.py', 'apps/api/src/apbra_api/foundry_agent_details.py', 'tasks/APBRA-160-browser-metadata-runtime-20261013.json', 'apps/api/tests/test_foundry_agent_details.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-browser-metadata-runtime'
BASE = 'cceac17498ee2e0118a5c7726163b6ad62a0ccaa'
TASK_SHA = 'e622a5fcfeb0f0a03a5680fc78e61f29c268841a9386363a9efebc51ab7cef4c'
GATES = {'requirements': '203bd7030b38c075717056793b67e1837473fba03193f13241d024907ccceb5d', 'adrs': 'a113a6be8a428f904b4cfdad76b48f9df037bfecb3760ba2571e055dde63ba1d', 'architecture_refs': '10836b0a4f3d114551d10076819bf39189cbf82ba4b9b18d706dda39ea1b1a1d', 'restricted_paths': '01345e0b4b76ca16ec03f0004621e3a395eac654335d4b3bb726927d3c8d4ae1', 'acceptance_criteria': 'e9017c26b84b207696485ec582a6078554eb12b3241fe7fc14d51edccceb4488', 'verification_required': 'b0d46c1f9c3a2b5e58025c4802796c59c268689cedcfbe73d8a3727745c095a7', 'out_of_scope': 'c1346e26db260f30ee70fd980d8550f2c619e79395970e9e4461bdbbb43d96d8', 'escalate_when': '2e7a79c28a4bac6ebd86b3535634a15ad40a5a54d756829faf62ea01e20e75bb', 'dependencies': '2d06b3c07e4a7187f181b2613465890763197bb740f9df4747f51c653ffd13bb', 'effective_release': 'ebdba8a608487284a82512815564e91016e8daff7e45ab71a4d77eefd72e93ed', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
RETAINED = {'apps/api/src/apbra_api/main.py': 'be916f0cb55779437d619e702b9d166e213a81bfabd2cf968ae9e4ed23fcb1f1', 'apps/api/src/apbra_api/foundry_owner_metadata.py': 'd23d75dff41611e7b58ca2ebd9f8c1236cec8c824b80bb5900ad8fd329452365', 'apps/api/src/apbra_api/model_provider.py': '24fa770c795659e0d95d5431780067b3a7450841bb45381f7d5b51145063354f', 'apps/api/src/apbra_api/tenant_settings.py': 'df030db277f434a9d9103a8a34ed85a90c21e06dc9885af251ca73386c6021af', 'apps/api/src/apbra_api/config.py': '78de10d5d6db9cd92d317cc9ffca52eb4f95a3f6a84ae2a5c9b44423d36b9e26'}

def bind(root, catalog, sources, validate):
    return validate(root, catalog, sources, filename="APBRA-160-browser-metadata-runtime-20261013.json",
        label="browser metadata runtime", branch=B, base=BASE, paths=P, task_sha=TASK_SHA,
        gates=GATES, source_bindings=SOURCES, sources_sha=SOURCES_SHA, count_label="twelve")

def ok(task, branch, paths):
    return task is not None and branch == B and paths <= P
HOOKS = [(1, "q=runpy.run_path(Path(__file__).parent/'check_br.py')\n"), (1, "        v,e=q['bind'](root,catalog,sources,bound_provider_registration);errors+=e\n"), (1, "(v,q['P']),\n"), (1, "                else v if active_branch==q['B']\n"), (2, " and not q['ok'](v,active_branch,changed_paths)")]

def strip_current_hooks(source):
    for count, hook in HOOKS:
        if source.count(hook) != count:
            raise ValueError("Current browser runtime registration hook differs")
        source = source.replace(hook, "")
    return source
