"""Pinned, finite APBRA-160 qualification-only deadline renewal; no runtime execution."""
import hashlib
import json

P = {'apps/api/src/apbra_api/config.py', 'apps/api/tests/test_model_provider.py'}
G = {'tasks/APBRA-160-foundry-qualification-renewal.json', 'scripts/check_bootstrap.py',
     'scripts/check_foundry_qualification_renewal.py', 'tests/bootstrap/test_foundry_qualification_renewal_scope.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-foundry-qualification-renewal'
R = B + '-registration'
BASE = '7f757a3026a31bf219bf0007f0a8c47b31686c25'
CEILING = '2026-10-10T02:09:00Z'
TASK_SHA = '30e14d2536d712cae7f27bbe40d04243e4438398b664509a39817390f9ed32af'
GATES = {'requirements': 'b78991dc141ab7536398c02584e4bf33a0e08c66bd0e8ec86f175d11d3e8acbe', 'adrs': 'ca2b40469b15adf978548f3a209be59c45c5613b84434704fca2bd6373e7a37c', 'architecture_refs': '78dbb3e337fae75165cec7ae1d23643c93cb6542d33fce8235036ea5ea52218d', 'restricted_paths': '0cae988d72a0e05108563e7f7127293541a51642b93b679cecbcf0b5a461c7dc', 'acceptance_criteria': '5d809bed443fa210ba69b4854ef1feaa8fd451e85405ec877f7fb0a749e6b94a', 'verification_required': '32144ba710846582b01538a23cb65ad1c8609020fe78ccc6c588c9a8098394c6', 'out_of_scope': 'e6467919c5410fdf0cfa5935ea7bc7ec12b51cd191b733dfb366a3eda6f7f50c', 'escalate_when': '87dc6b165a22facc726c7899add0577dd267179aa35f2b7095f07e1ee028b010', 'dependencies': '4f816acf42ffc488056ccd54b2928d9d020b6437f80efabdac137a07cde1dd2e', 'effective_release': 'f06d9577f8d5efa867786de2636f79cc052588d55b7468b8c1d8bf11be93037d', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2'}
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


# Additive Oct11 combined renewal; historical constants/functions above stay exact.
N_PATHS = {'apps/api/tests/test_model_provider.py', 'scripts/check_bootstrap.py', 'tests/bootstrap/test_foundry_qualification_renewal_20261011_scope.py', 'tasks/APBRA-160-foundry-qualification-renewal-20261011.json', 'scripts/check_foundry_qualification_renewal.py', 'apps/api/src/apbra_api/config.py'}
N_BRANCH = 'agent/APBRA-DEVOPS/APBRA-160-foundry-qualification-renewal-20261011-final'
N_BASE = '6b8c1df8371fd836f1940cdb5a34d48933aeda93'
N_CEILING = '2026-10-11T12:24:46Z'
N_HISTORY = (('APBRA-160-foundry-qualification.json', ORIGINAL_TASK_SHA),
             ('APBRA-160-foundry-qualification-renewal.json', TASK_SHA))
N_TASK_SHA = '7a34827573e70cad8fc8d9bacad8526b8b3fdd8e57e5994e3455aecb7a78ae73'
N_GATES = {'requirements': '100cfe70a856ed390f5ada404a894c60576f955c1b8e9b02e6e3616a1c24c89c', 'adrs': 'c6ed06de0c6290f66c8c01664592d0afcb49be9afb2cd9d74c4f64fe507ad549', 'architecture_refs': 'bb39756ff6ae485a7188d86988d49df53ed40d9ded7d8a5fb8804eda3079047b', 'restricted_paths': '0720cb7ba335e128182ed591d77b8ace91783b7df2f1085f9a7aaf348f9d9af8', 'acceptance_criteria': 'ccc1e038b13a9cf40828fa5b817a2cbb91218f7bc1b4379d82f99958cddce1af', 'verification_required': '6dd67451f578536455f0dbf19090f2b96093333340956b1d00cfd6b9aa2e1e71', 'out_of_scope': '6c519ef45b4c073e59354306ba0722b89062f576b8e16368c969f6b2fae10293', 'escalate_when': 'c4a0494152280f7db2e35c8c75390cd4e1b1b660d8e4898b4abd9aec5573458b', 'dependencies': 'c8d8c5a64e003b3cad2113518870a7855f96896f30020e2342c0fc95207ee426', 'effective_release': 'f77e865f43dd0263a4dc0c7ddbc06e44243f8280464eb9fe09fa347e91fb382d', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2'}


def bind11(root, catalog, sources, validate):
    task, failures = validate(
        root, catalog, sources, filename='APBRA-160-foundry-qualification-renewal-20261011.json',
        label='Foundry qualification Oct11 renewal', branch=N_BRANCH, base=N_BASE,
        paths=N_PATHS, task_sha=N_TASK_SHA, gates=N_GATES, source_bindings=SOURCES,
        sources_sha=SOURCES_SHA, count_label='six',
    )
    if task is not None:
        if not task['requirements'][0].startswith('The sole renewed qualification ceiling is ' + N_CEILING + ' '):
            failures.append('APBRA-160 Foundry qualification Oct11 renewal ceiling differs')
        for name, expected in N_HISTORY:
            path = root / 'tasks' / name
            if not path.is_file():
                return None, failures
            if digest(json.loads(path.read_text())) != expected:
                # Reject new scope without changing any historical validator's errors.
                return None, failures
    return (None if failures else task), failures


def errors11(task_id, branch, paths):
    if task_id == 'APBRA-160' and branch == N_BRANCH and paths != N_PATHS:
        return ['APBRA-160 Foundry qualification Oct11 renewal requires exactly six combined files']
    return []
