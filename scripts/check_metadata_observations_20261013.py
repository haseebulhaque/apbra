"""Exact comprehensive observation correction; no runtime invocation authority."""
P = {'apps/api/src/apbra_api/foundry_metadata_projection.py', 'tests/bootstrap/test_tenant_document_drafts_20261013_scope.py', 'tasks/APBRA-160-metadata-observations-20261013.json', 'apps/api/src/apbra_api/foundry_agent_details.py', 'apps/api/src/apbra_api/foundry_owner_metadata.py', 'scripts/check_metadata_observations_20261013.py', 'apps/api/tests/test_foundry_owner_metadata.py', 'tests/bootstrap/test_agent_details_scope.py', 'scripts/check_bootstrap.py', 'tests/bootstrap/test_metadata_observations_scope.py', 'apps/api/tests/test_foundry_agent_details.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-metadata-observations'
BASE = '998cd35d4971edd81776927704a2a5a6f07fc13b'
TASK_SHA = '6f37823e46370fab339644c6f7b0fe0432e641110a1966ed5c32fada3ad56cb4'
GATES = {'requirements': '2daae995aa910db242e4343e252f5c60aa45bc269ed971b37cec4147348acb47', 'adrs': '819273b12b9b3dc1e9f176aa02434646326099bbdb80f3493bd40a964b862e31', 'architecture_refs': 'cbad004c181f638641208102d28111636a808876b8c423d075a80a51e7071ee1', 'restricted_paths': '38f978ef6f23a74cabb87f5df6d9324cba025855c3bff3c7a46133eb406cd2f4', 'acceptance_criteria': '794ff276ab1cd68e368ba6e77c0421a3eb328fedb787d8f87cad61cdaed96f37', 'verification_required': '8745b639d0ff3282ff8ed5cccfb41388bbe1b48d72b20e9224b5d252a148bb14', 'out_of_scope': '39703a6a08f18180a74816060adc19c36f0d23f7635617feeb509e6d588eeba6', 'escalate_when': '2e7a79c28a4bac6ebd86b3535634a15ad40a5a54d756829faf62ea01e20e75bb', 'dependencies': 'db4149b768dd2ec59b003529149672be25104af6965bd49f55fa880d866331c8', 'effective_release': 'fe9fd9f8a698886f10970f3ee6025b1592bcd1a2f7a7294e7ef0e1c8d92fdadd', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'

def bind(root, catalog, sources, validate):
    return validate(root, catalog, sources, filename="APBRA-160-metadata-observations-20261013.json",
        label="metadata observations", branch=B, base=BASE, paths=P, task_sha=TASK_SHA,
        gates=GATES, source_bindings=SOURCES, sources_sha=SOURCES_SHA, count_label="eleven")
HOOKS = [(1, 'zz=runpy.run_path(str(Path(__file__).with_name("check_metadata_observations_20261013.py")))\n'), (1, "        metadata_observations, e = zz['bind'](root, catalog, sources, bound_provider_registration)\n        errors += e\n"), (1, "            (metadata_observations, zz['P']),\n"), (1, "                else metadata_observations if active_branch == zz['B']\n"), (2, " and\n                    not (metadata_observations is not None and active_branch == zz['B'] and changed_paths <= zz['P'])")]

def strip_current_hooks(source):
    for count, hook in HOOKS:
        if source.count(hook) != count:
            raise ValueError("Current observation registration hook differs")
        source = source.replace(hook, "")
    return source
