"""Pinned, finite APBRA-160 qualification-only deadline renewal; no runtime execution."""
import hashlib
import json

P = {'apps/api/src/apbra_api/config.py', 'apps/api/tests/test_model_provider.py'}
G = {'tasks/APBRA-160-foundry-qualification-renewal.json', 'scripts/check_bootstrap.py',
     'scripts/check_foundry_qualification_renewal.py', 'tests/bootstrap/test_foundry_qualification_renewal_scope.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-foundry-qualification-renewal'
R = B + '-registration'
BASE = 'b3f177a89f8831b8a4f8857198728878fa0722f6'
CEILING = '2026-10-10T02:09:00Z'
TASK_SHA = 'fcbfb3ccd239521f4f9d46b2765f4f01584c7c0d8aa6f500454da86cb8c87311'
GATES = {'requirements': '6694b5bb3dd2e3cee432811fc1e18c4308100f090c3c4b3e2773176be8a5c693', 'adrs': 'ca2b40469b15adf978548f3a209be59c45c5613b84434704fca2bd6373e7a37c', 'architecture_refs': '71713eae9da423fa1638af32e662f33ef1c0d2c571ec149286b6d8699e29f887', 'restricted_paths': '0cae988d72a0e05108563e7f7127293541a51642b93b679cecbcf0b5a461c7dc', 'acceptance_criteria': '5d809bed443fa210ba69b4854ef1feaa8fd451e85405ec877f7fb0a749e6b94a', 'verification_required': 'df9cd2084acc8bd561eb3de5435a97b33fb731ec3f3277d2d203df01f82ccf5f', 'out_of_scope': 'e6467919c5410fdf0cfa5935ea7bc7ec12b51cd191b733dfb366a3eda6f7f50c', 'escalate_when': '87dc6b165a22facc726c7899add0577dd267179aa35f2b7095f07e1ee028b010', 'dependencies': 'e0d85106d9f4ad71e2be899a17a9c7e7faf19a8fa433f2759c6b24505668fa8d', 'effective_release': 'c5352ef72bcfabaed896cd134d971997540eaa36939702d0394f3abe647991b1', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2'}
SOURCES = (
    ('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'),
    ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9'),
)
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
ORIGINAL_TASK_SHA = '7f238804977619dcc8120b58ae4df562b35a0409ddef545711d1782f51ae4aae'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bind(root, catalog, sources, validate):
    task, errors = validate(
        root, catalog, sources, filename='APBRA-160-foundry-qualification-renewal.json',
        label='Foundry qualification renewal', branch=B, base=BASE, paths=P,
        task_sha=TASK_SHA, gates=GATES, source_bindings=SOURCES,
        sources_sha=SOURCES_SHA, count_label='two',
    )
    if task is not None:
        if not task['requirements'][0].startswith('The sole renewed qualification ceiling is ' + CEILING + ' '):
            errors.append('APBRA-160 Foundry qualification renewal ceiling differs')
        historical = root / 'tasks/APBRA-160-foundry-qualification.json'
        if not historical.is_file():
            # Absence grants no renewal scope and leaves unrelated historical errors unchanged.
            return None, errors
        if digest(json.loads(historical.read_text())) != ORIGINAL_TASK_SHA:
            errors.append('APBRA-160 Foundry qualification renewal historical task differs')
        if not (root / 'scripts/check_foundry_qualification_renewal.py').is_file():
            errors.append('APBRA-160 Foundry qualification renewal helper missing')
    return (None if errors else task), errors


def stage(task_id, branch, paths):
    return task_id == 'APBRA-160' and branch == R and paths == G


def errors(task_id, branch, paths):
    if task_id == 'APBRA-160' and branch == R and paths != G:
        return ['APBRA-160 Foundry qualification renewal registration must change exactly four governance files']
    if task_id == 'APBRA-160' and branch == B and paths != P:
        return ['APBRA-160 Foundry qualification renewal implementation requires exactly its two registered product paths']
    return []
