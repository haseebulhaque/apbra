"""Import-safe owner-manual metadata registration; no runtime or paid authority."""
import hashlib
import json

P = {'apps/api/src/apbra_api/foundry_metadata_projection.py', 'apps/api/src/apbra_api/foundry_owner_metadata.py', 'apps/api/src/apbra_api/main.py', 'apps/api/tests/test_foundry_owner_metadata.py'}
G = {'tests/bootstrap/test_foundry_owner_metadata_20261012_scope.py', 'scripts/check_foundry_owner_metadata_20261012.py', 'tasks/APBRA-160-foundry-owner-metadata-20261012.json', 'scripts/check_bootstrap.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-foundry-owner-metadata'
R = 'agent/APBRA-DEVOPS/APBRA-160-foundry-owner-metadata-registration'
BASE = '19451292d596e0f488887b88c2ce3d420a1b6b51'
RELEASE_BOUND = True
ACTOR = 'Codex via haseebulhaque authenticated GitHub and Atlassian tools'
OWNER = 'Haseeb Ul Haque'
AUTHORITY = 'Direct Haseeb outcome renewal2026-10-11T23:11:44Z/23:12:19Z under JiraAPBRA-16010757 and bounded owner-metadata PLAN10759 authorizes this existing-MVP code/governance preparation until complete; no invented future expiry. Current owner records Confluence4063307v34/8519682v49 supplement rather than rewrite historical accepted authority.'
TASK_SHA = 'ec387c9c55366848e99d0cd5113b0b74eba04eb35a3a3a66a1ba0760192e229c'
GATES = {'requirements': 'c08f42334b0cdc1a28ba545fb50747a82de271df9da84c40c2567e902e074f21', 'adrs': '62c0b2b4af40fa5d0419568e5f4632b415cf2802340121c05daad613684318bc', 'architecture_refs': '98d40037fdbd91ec5a9b63c49d926a45c230e68bbe7df11e91f050b0820320a8', 'restricted_paths': '9633ccde081c38b8eb7c2c04af8735bdf3ee3e638138d4a6b22ceba6a5c978e0', 'acceptance_criteria': 'f028c358ff5392cb0088dad6c42ddc32f48643407bc3573020c547e621cb6d34', 'verification_required': 'a28e0d9a1acd7a6aee5b95d5177dccbf0b610ba57a43ecb02278d23135a8f8c0', 'out_of_scope': 'b8d935da02c05c0ecede3821676e65de1c51a9490050441e1bc6049be5e7a995', 'escalate_when': '05395a4e7f118c23c4205f04e4dfd1842289dd7bf3ab9470ed7510ed7dc8fd44', 'dependencies': 'd937615b73fb6dd2b8b0eda4003e7e3f3740032aec37f36a3d0e4b3ee85ecbb2', 'effective_release': 'd933dd7f617f59ac50f310b1a550c65ea712879064696b78057471a930c5b397', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
SOURCE_FILE_SHA = '086e26d0f83e76347ab709d8859dd013513240a4e86ee9861af2086f38bb0f3e'
HISTORY = ('APBRA-108-candidate-source-safety.json', 'APBRA-129-capstone-shell.json', 'APBRA-130-requirements-snapshot.json', 'APBRA-131-curated-knowledge.json', 'APBRA-132-design-plan.json', 'APBRA-133-powerbi-project.json', 'APBRA-134-validation.json', 'APBRA-135-release.json', 'APBRA-136-orchestration.json', 'APBRA-137-final-capstone-ux.json', 'APBRA-138-measure-resolution.json', 'APBRA-139-report-design-normalization.json', 'APBRA-140-capstone-documentation.json', 'APBRA-141-measure-contract-pipeline.json', 'APBRA-142-layout-repair.json', 'APBRA-143-typed-confirmed-requirements.json', 'APBRA-144-ai-native-iterative-clarification.json', 'APBRA-145-generic-time-grain-support.json', 'APBRA-146-post-capstone-mvp-baseline-reconciliation.json', 'APBRA-147-confirmation-readiness-integrity.json', 'APBRA-148-post-capstone-product-reconciliation.json', 'APBRA-151-company-lifecycle.json', 'APBRA-159-data-model-documentation-reconciliation.json', 'APBRA-160-ai-authored-layout-20261012.json', 'APBRA-160-demo-ux.json', 'APBRA-160-foundry-host.json', 'APBRA-160-foundry-qualification-renewal-20261011.json', 'APBRA-160-foundry-qualification-renewal.json', 'APBRA-160-foundry-qualification.json', 'APBRA-160-foundry-structured-output.json', 'APBRA-160-local-rekey.json', 'APBRA-160-provider-retrieval.json', 'APBRA-160-renderer-geometry-20261011.json', 'APBRA-162-invited-private-case-foundation.json', 'APBRA-163-durable-conversation-evidence-acceptance.json', 'APBRA-164-protected-generation-output-history.json', 'APBRA-169-business-friendly-ux-application-shell.json', 'APBRA-170-professional-saas-experience-visual-system.json', 'APBRA-171-business-user-report-creation-intelligent-generation.json', 'APBRA-172-provider-neutral-sso.json', 'APBRA-173-private-content-storage.json', 'APBRA-173-production-web-release.json', 'APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json', 'APBRA-175-deployment-portability-entitlement-docs.json', 'APBRA-176-owner-onboarding-identity-docs.json', 'APBRA-177-current-state-docs.json', 'APBRA-27-build.json', 'APBRA-76-deployment-guide.json', 'APBRA-85-bootstrap.json', 'APBRA-92-evaluation.json')
HISTORY_SHA = '4d14f65159dbec31ec4b6f1971b915e9bffba57ae57cf1531dfde230fe0fbe0b'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bind(root, catalog, sources, validate):
    if not RELEASE_BOUND:
        return None, []
    task, failures = validate(root, catalog, sources,
        filename='APBRA-160-foundry-owner-metadata-20261012.json', label='Foundry owner metadata',
        branch=B, base=BASE, paths=P, task_sha=TASK_SHA, gates=GATES,
        source_bindings=SOURCES, sources_sha=SOURCES_SHA, count_label='four')
    if task is not None:
        if (task['actual_authenticated_actor'], task['human_owner'], task['human_initiator']) != (ACTOR, OWNER, OWNER):
            failures.append('APBRA-160 owner metadata actor/owner differs')
        if task['requirements'][0] != AUTHORITY:
            failures.append('APBRA-160 owner metadata outcome authority differs')
        if (task['task_mode'], task['readiness'], task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
            failures.append('APBRA-160 owner metadata release is not ready')
        if not (root / 'scripts/check_foundry_owner_metadata_20261012.py').is_file():
            failures.append('APBRA-160 owner metadata helper missing')
        current = {name: hashlib.sha256((root / 'tasks' / name).read_bytes()).hexdigest()
                   for name in HISTORY if (root / 'tasks' / name).is_file()}
        source = root / 'docs/source-register.json'
        if digest(current) != HISTORY_SHA or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_FILE_SHA:
            return None, failures
    return (None if failures else task), failures


def stage(task_id, branch, paths):
    return task_id == 'APBRA-160' and branch == R and paths == G


def errors(task_id, branch, paths):
    if task_id == 'APBRA-160' and branch == R and paths != G:
        return ['APBRA-160 owner metadata registration requires exactly four governance paths']
    if task_id == 'APBRA-160' and branch == B and (not paths or not paths <= P):
        return ['APBRA-160 owner metadata product requires exactly its four literal paths']
    return []
