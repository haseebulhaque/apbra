"""Pure knowledge lifecycle registration; no provider/runtime or operational authority."""
import hashlib
import json

P = {'apps/api/src/apbra_api/knowledge_lifecycle.py', 'apps/api/tests/test_knowledge_lifecycle.py'}
G = {'tests/bootstrap/test_historical_fixture_staging_20261012_scope.py', 'tasks/APBRA-160-knowledge-lifecycle-20261012.json', 'tests/bootstrap/test_knowledge_lifecycle_20261012_scope.py', 'scripts/check_knowledge_lifecycle_20261012.py', 'scripts/check_bootstrap.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-knowledge-lifecycle'
R = 'agent/APBRA-DEVOPS/APBRA-160-knowledge-lifecycle-registration'
BASE = 'a70edb88a7db589d5488932d82a180f18694fb8a'
RELEASE_BOUND = True
ACTOR = 'Codex via haseebulhaque authenticated GitHub and Atlassian tools'
OWNER = 'Haseeb Ul Haque'
AUTHORITY = 'Direct Haseeb accepted existing-MVP outcome10757 and parent-authorized finite offline knowledge-lifecycle component under Jira APBRA-160 PLAN10795/10796; no owner interaction, new provider capability or operational authority. Frozen semantic contract SHA25622ad544614284295b4c2da2f8b024fdc4a5441d4c2cc8764bd7319017e7ea4b5 is accepted by root; only registration geometry names are overridden by PLAN10795/10796.'
TASK_SHA = 'ae151809eaa640572efef9587f66c6ca1176b4cdc826adf83a8c0b2dbe0d1b13'
GATES = {'requirements': '9163b64e4eb875e651b7c6d873c69e7dc39186bd25545bffe46625bb723078f7', 'adrs': '8317d8d4505f1b8b3d2780bebf192e1690bea73a05cd57793cb550737c89c759', 'architecture_refs': '566f7a839633a2b9deb0480c94fa785db11e34449dd043e1c3ec81748fdd1fe7', 'restricted_paths': 'a88aeee7c4738fa1130d04fe93e14aa5201982957af1bfd85087e23abc236d2f', 'acceptance_criteria': '25941c2715ac0b9445beb2769fc05515c6577122a5ca7dec8b90a723ec2ecebf', 'verification_required': 'b8479cd944ae5f9cd1ce36b21d7c2e8773997946bbd371623d095fc3ab34e7a8', 'out_of_scope': '1fca77a952967b94c521bf92fe0c91945ee3f424ed1f4da01289d55116f1830b', 'escalate_when': '0fd6e29e9f5bc16d5d3d8b73d791c394b8d4c54188f1d0246b714cd0c354e2e9', 'dependencies': '2844e42b0d15c6a8b3735d5c4ee7b71b551e2791259931d736195371f161cb86', 'effective_release': '9760bb87338c540a9d243cc8ebe4d78ab2e597d625a2da2adbf9e6bf712c2a2f', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
SOURCE_FILE_SHA = '086e26d0f83e76347ab709d8859dd013513240a4e86ee9861af2086f38bb0f3e'
HISTORY = ('APBRA-108-candidate-source-safety.json', 'APBRA-129-capstone-shell.json', 'APBRA-130-requirements-snapshot.json', 'APBRA-131-curated-knowledge.json', 'APBRA-132-design-plan.json', 'APBRA-133-powerbi-project.json', 'APBRA-134-validation.json', 'APBRA-135-release.json', 'APBRA-136-orchestration.json', 'APBRA-137-final-capstone-ux.json', 'APBRA-138-measure-resolution.json', 'APBRA-139-report-design-normalization.json', 'APBRA-140-capstone-documentation.json', 'APBRA-141-measure-contract-pipeline.json', 'APBRA-142-layout-repair.json', 'APBRA-143-typed-confirmed-requirements.json', 'APBRA-144-ai-native-iterative-clarification.json', 'APBRA-145-generic-time-grain-support.json', 'APBRA-146-post-capstone-mvp-baseline-reconciliation.json', 'APBRA-147-confirmation-readiness-integrity.json', 'APBRA-148-post-capstone-product-reconciliation.json', 'APBRA-151-company-lifecycle.json', 'APBRA-159-data-model-documentation-reconciliation.json', 'APBRA-160-ai-authored-layout-20261012.json', 'APBRA-160-ai-authored-layout-raw-ingress-20261012.json', 'APBRA-160-demo-ux.json', 'APBRA-160-foundry-host.json', 'APBRA-160-foundry-owner-metadata-20261012.json', 'APBRA-160-foundry-qualification-renewal-20261011.json', 'APBRA-160-foundry-qualification-renewal.json', 'APBRA-160-foundry-qualification.json', 'APBRA-160-foundry-structured-output.json', 'APBRA-160-historical-fixture-staging-20261012.json', 'APBRA-160-local-rekey.json', 'APBRA-160-provider-retrieval.json', 'APBRA-160-renderer-geometry-20261011.json', 'APBRA-162-invited-private-case-foundation.json', 'APBRA-163-durable-conversation-evidence-acceptance.json', 'APBRA-164-protected-generation-output-history.json', 'APBRA-169-business-friendly-ux-application-shell.json', 'APBRA-170-professional-saas-experience-visual-system.json', 'APBRA-171-business-user-report-creation-intelligent-generation.json', 'APBRA-172-provider-neutral-sso.json', 'APBRA-173-private-content-storage.json', 'APBRA-173-production-web-release.json', 'APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json', 'APBRA-175-deployment-portability-entitlement-docs.json', 'APBRA-176-owner-onboarding-identity-docs.json', 'APBRA-177-current-state-docs.json', 'APBRA-27-build.json', 'APBRA-76-deployment-guide.json', 'APBRA-85-bootstrap.json', 'APBRA-92-evaluation.json')
HISTORY_SHA = 'ba14da8444d61a7429aabaaaf7f153693ff377979b69da1b845b7c99634c1916'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bind(root, catalog, sources, validate):
    if not RELEASE_BOUND:
        return None, []
    task, failures = validate(root, catalog, sources,
        filename='APBRA-160-knowledge-lifecycle-20261012.json', label='Knowledge lifecycle',
        branch=B, base=BASE, paths=P, task_sha=TASK_SHA, gates=GATES,
        source_bindings=SOURCES, sources_sha=SOURCES_SHA, count_label='two')
    if task is not None:
        if (task['actual_authenticated_actor'], task['human_owner'], task['human_initiator']) != (ACTOR, OWNER, OWNER):
            failures.append('APBRA-160 knowledge lifecycle actor/owner differs')
        if task['requirements'][0] != AUTHORITY:
            failures.append('APBRA-160 knowledge lifecycle outcome authority differs')
        if (task['task_mode'], task['readiness'], task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
            failures.append('APBRA-160 knowledge lifecycle release is not ready')
        if not (root / 'scripts/check_knowledge_lifecycle_20261012.py').is_file():
            failures.append('APBRA-160 knowledge lifecycle helper missing')
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
        return ['APBRA-160 knowledge lifecycle registration requires exactly five governance paths']
    if task_id == 'APBRA-160' and branch == B and (not paths or not paths <= P):
        return ['APBRA-160 knowledge lifecycle product requires exactly its two literal paths']
    return []
