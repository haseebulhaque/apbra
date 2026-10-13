"""Finite owner-approved memory handoff; old task scopes unchanged."""
P = {'apps/api/tests/test_foundry_memory_handoff.py', 'scripts/check_bootstrap.py', 'tests/bootstrap/test_memory_handoff_scope.py', 'tests/bootstrap/test_tenant_document_drafts_20261013_scope.py', 'apps/api/src/apbra_api/foundry_browser_handoff.py', 'tests/bootstrap/test_agent_details_scope.py', 'tests/bootstrap/test_browser_metadata_runtime_scope.py', 'scripts/check_mh.py', 'apps/api/tests/test_foundry_browser_handoff.py', 'tests/bootstrap/test_metadata_observations_scope.py', 'tasks/APBRA-160-memory-handoff-20261013.json', 'apps/api/src/apbra_api/foundry_memory_handoff.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-memory-handoff'
BASE = '582de1565135737983f5bb87bca713d71ab61cd2'
TASK_SHA = '4f939645bee535d6da4b5676a1e686d1a9e2e49559cec9f7b6bccf07b90e0c31'
GATES = {'requirements': '273dde3bc6d8cc3b3d9f4a85defcba0415cf0b4b7e9d436f68d9a0fa2feed8a5', 'adrs': '7f6c3e8c7638b6be9efa734dfb43039d5abe8109b33df0df446646fb2124e045', 'architecture_refs': '2e40abb7844f378b1584c30fc5a7728eb162eb282e80f0c0f356a813345a5572', 'restricted_paths': '01345e0b4b76ca16ec03f0004621e3a395eac654335d4b3bb726927d3c8d4ae1', 'acceptance_criteria': '64136f6f9997f75c4a69a351cfd727a4785fbe78994cde74cc15ba0a37ee76ea', 'verification_required': 'e921efbbcac80179b4193b84623c569eafa7e2063533a5c218c09021b39a506e', 'out_of_scope': 'fefbf50d80c8e1454d540bd0e7f113de0e14b05c9f857d853cd19884c4acf0ab', 'escalate_when': '2e7a79c28a4bac6ebd86b3535634a15ad40a5a54d756829faf62ea01e20e75bb', 'dependencies': '41e0999015c0e505773cc13fa34549f0dbc47276c0ca1e2eca3d99eb8c0576b0', 'effective_release': 'a8eb2e565458f787bdfa1e22204465602e2545693581484e54babe029d5cbebb', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
RETAINED = {'apps/api/src/apbra_api/main.py': 'be916f0cb55779437d619e702b9d166e213a81bfabd2cf968ae9e4ed23fcb1f1', 'apps/api/src/apbra_api/foundry_owner_metadata.py': 'd23d75dff41611e7b58ca2ebd9f8c1236cec8c824b80bb5900ad8fd329452365', 'apps/api/src/apbra_api/model_provider.py': '24fa770c795659e0d95d5431780067b3a7450841bb45381f7d5b51145063354f', 'apps/api/src/apbra_api/tenant_settings.py': 'df030db277f434a9d9103a8a34ed85a90c21e06dc9885af251ca73386c6021af', 'apps/api/src/apbra_api/config.py': '78de10d5d6db9cd92d317cc9ffca52eb4f95a3f6a84ae2a5c9b44423d36b9e26'}

def bind(root,catalog,sources,validate):
    return validate(root,catalog,sources,filename="APBRA-160-memory-handoff-20261013.json",label="memory handoff",branch=B,base=BASE,paths=P,task_sha=TASK_SHA,gates=GATES,source_bindings=SOURCES,sources_sha=SOURCES_SHA,count_label="twelve")
def ok(task,branch,paths):
    return task is not None and branch==B and paths<=P
HOOKS = [(1, "x=runpy.run_path(Path(__file__).parent/'check_mh.py')\n"), (1, "        w,e=x['bind'](root,catalog,sources,bound_provider_registration);errors+=e\n"), (1, "(w,x['P']),\n"), (1, "                else w if active_branch==x['B']\n"), (2, " and not x['ok'](w,active_branch,changed_paths)")]
def strip_current_hooks(source):
    for count,hook in HOOKS:
        if source.count(hook)!=count:raise ValueError("Memory handoff hook differs")
        source=source.replace(hook, "")
    return source
