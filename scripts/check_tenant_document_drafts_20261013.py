"""Pure tenant document drafts registration; no provider/runtime or operational authority."""
import hashlib
import json

P = {'apps/api/src/apbra_api/persistence.py', 'apps/api/alembic/versions/20261013_09_tenant_knowledge_drafts.py', 'apps/api/tests/test_knowledge_documents.py', 'apps/api/src/apbra_api/knowledge_documents.py', 'apps/web/src/api.ts', 'apps/api/src/apbra_api/api.py', 'apps/web/e2e/tenant-settings.spec.ts', 'apps/web/src/api.test.ts', 'apps/api/tests/test_migrations.py', 'apps/web/src/EnterpriseApp.tsx'}
G = {'tests/bootstrap/test_knowledge_lifecycle_20261012_scope.py', 'tests/bootstrap/historical_fixture_staging.py', 'scripts/check_bootstrap.py', 'tests/bootstrap/test_tenant_document_drafts_20261013_scope.py', 'scripts/check_tenant_document_drafts_20261013.py', 'tasks/APBRA-160-tenant-document-drafts-20261013.json'}
B = 'agent/APBRA-DEVOPS/APBRA-160-tenant-document-drafts'
R = 'agent/APBRA-DEVOPS/APBRA-160-tenant-document-drafts-registration'
BASE = '7c16f98cfb0d33bd8259dc6d37eb9777f421bb96'
RELEASE_BOUND = True
ACTOR = 'Codex via haseebulhaque authenticated GitHub and Atlassian tools'
OWNER = 'Haseeb Ul Haque'
AUTHORITY = 'Direct accepted existing-MVP outcome10757 and parent-delegated continuation under Jira APBRA-160 PLAN10829 authorizes exactly the unchanged H13 semantic-origin LOCAL Tenant Settings document-drafts contract SHA256556ed2d22ff3d5000142a34d01d3303ccb376d392b90fd668300a28b3b2b5c47 and frozen wire SHA2569da113a39ebd15a9d8cd81adde8ae2b22da07117ca00136df0e19c6e97e4117a on actual normal-released H14 execution base7c16f98cfb0d33bd8259dc6d37eb9777f421bb96; semantic origin remains H1318454c33cff6be0e42c8f412d3cdc1ec75d1c898 and historical H12 snapshots unchanged. No invented expiry, provider/owner/runtime/paid authority or amendment of historical pure P2 semantics.'
TASK_SHA = 'd11edd7b4eb7a488a603d9abe3392271ad3455ee45b0e778096099244208e003'
GATES = {'requirements': '5f196c3725cc25445e248f9bee50db051e83b247e718c1de9182cd1163162ec0', 'adrs': '068408308eff64ce05fbb04b61b33bdece3d5e9d0ed192e0d876d72a8076ac0f', 'architecture_refs': '77802ad4b0beede93925d764b12ae5fe000122d504e2d29f762ea5da62b58d6d', 'restricted_paths': '145489c32fc8bc538fe2e039bf92487f2a54daddcfde84d3901579dc89944ec2', 'acceptance_criteria': '543e483c279429491778dbb7250783572327c4e0a6bca9066f62bb71a8fdfe71', 'verification_required': '629bf54922e333cd816983c013a9884b8d46be3f8a2dc1822ee6d910537586a0', 'out_of_scope': 'd69083caaecae6961e6a60c39ef467c61929ece5600505baa0a006d3f6585e60', 'escalate_when': '3db49058409c4e514da6e629695e3b138215cbb9bd4d5575b22f64f0c436ed7c', 'dependencies': 'c01f6ee77c411d66ead7673f0fc64f26a8be3274c9b8552625e982288c7b983d', 'effective_release': '047fd530f99b63df22f7e1ecdc9d5bb6ec62af0b5b85cdd96f63a0a6f970d9e7', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
SOURCE_FILE_SHA = '086e26d0f83e76347ab709d8859dd013513240a4e86ee9861af2086f38bb0f3e'
HISTORY = ('APBRA-108-candidate-source-safety.json', 'APBRA-129-capstone-shell.json', 'APBRA-130-requirements-snapshot.json', 'APBRA-131-curated-knowledge.json', 'APBRA-132-design-plan.json', 'APBRA-133-powerbi-project.json', 'APBRA-134-validation.json', 'APBRA-135-release.json', 'APBRA-136-orchestration.json', 'APBRA-137-final-capstone-ux.json', 'APBRA-138-measure-resolution.json', 'APBRA-139-report-design-normalization.json', 'APBRA-140-capstone-documentation.json', 'APBRA-141-measure-contract-pipeline.json', 'APBRA-142-layout-repair.json', 'APBRA-143-typed-confirmed-requirements.json', 'APBRA-144-ai-native-iterative-clarification.json', 'APBRA-145-generic-time-grain-support.json', 'APBRA-146-post-capstone-mvp-baseline-reconciliation.json', 'APBRA-147-confirmation-readiness-integrity.json', 'APBRA-148-post-capstone-product-reconciliation.json', 'APBRA-151-company-lifecycle.json', 'APBRA-159-data-model-documentation-reconciliation.json', 'APBRA-160-ai-authored-layout-20261012.json', 'APBRA-160-ai-authored-layout-raw-ingress-20261012.json', 'APBRA-160-demo-ux.json', 'APBRA-160-foundry-host.json', 'APBRA-160-foundry-owner-metadata-20261012.json', 'APBRA-160-foundry-qualification-renewal-20261011.json', 'APBRA-160-foundry-qualification-renewal.json', 'APBRA-160-foundry-qualification.json', 'APBRA-160-foundry-structured-output.json', 'APBRA-160-historical-fixture-staging-20261012.json', 'APBRA-160-knowledge-lifecycle-20261012.json', 'APBRA-160-local-rekey.json', 'APBRA-160-provider-retrieval.json', 'APBRA-160-renderer-geometry-20261011.json', 'APBRA-162-invited-private-case-foundation.json', 'APBRA-163-durable-conversation-evidence-acceptance.json', 'APBRA-164-protected-generation-output-history.json', 'APBRA-169-business-friendly-ux-application-shell.json', 'APBRA-170-professional-saas-experience-visual-system.json', 'APBRA-171-business-user-report-creation-intelligent-generation.json', 'APBRA-172-provider-neutral-sso.json', 'APBRA-173-private-content-storage.json', 'APBRA-173-production-web-release.json', 'APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json', 'APBRA-175-deployment-portability-entitlement-docs.json', 'APBRA-176-owner-onboarding-identity-docs.json', 'APBRA-177-current-state-docs.json', 'APBRA-27-build.json', 'APBRA-76-deployment-guide.json', 'APBRA-85-bootstrap.json', 'APBRA-92-evaluation.json')
HISTORY_SHA = 'dba01cc507e97a2a11c7cafd7bc3688610555805221ee5ba7a313f7210a89d1d'

CONTRACT_SHA = '556ed2d22ff3d5000142a34d01d3303ccb376d392b90fd668300a28b3b2b5c47'
CONTRACT_PREFIX = 'FROZEN_FULL_SEMANTIC_CONTRACT_JSON\n'
WIRE_SHA = '9da113a39ebd15a9d8cd81adde8ae2b22da07117ca00136df0e19c6e97e4117a'
WIRE_PREFIX = 'FROZEN_FULL_PRODUCT_WIRE_JSON\n'

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bind(root, catalog, sources, validate):
    if not RELEASE_BOUND:
        return None, []
    task, failures = validate(root, catalog, sources,
        filename='APBRA-160-tenant-document-drafts-20261013.json', label='Tenant document drafts',
        branch=B, base=BASE, paths=P, task_sha=TASK_SHA, gates=GATES,
        source_bindings=SOURCES, sources_sha=SOURCES_SHA, count_label='ten')
    if task is not None:
        if (task['actual_authenticated_actor'], task['human_owner'], task['human_initiator']) != (ACTOR, OWNER, OWNER):
            failures.append('APBRA-160 tenant document drafts actor/owner differs')
        if task['requirements'][0] != AUTHORITY:
            failures.append('APBRA-160 tenant document drafts outcome authority differs')
        embedded = task['requirements'][1] if len(task['requirements']) > 1 else ''
        if (not embedded.startswith(CONTRACT_PREFIX) or
                hashlib.sha256(embedded[len(CONTRACT_PREFIX):].encode()).hexdigest() != CONTRACT_SHA):
            failures.append('APBRA-160 tenant document drafts frozen contract differs')
        embedded_wire = task['requirements'][6] if len(task['requirements']) > 6 else ''
        if (not embedded_wire.startswith(WIRE_PREFIX) or
                hashlib.sha256(embedded_wire[len(WIRE_PREFIX):].encode()).hexdigest() != WIRE_SHA):
            failures.append('APBRA-160 tenant document drafts frozen wire differs')
        if (task['task_mode'], task['readiness'], task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
            failures.append('APBRA-160 tenant document drafts release is not ready')
        if not (root / 'scripts/check_tenant_document_drafts_20261013.py').is_file():
            failures.append('APBRA-160 tenant document drafts helper missing')
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
        return ['APBRA-160 tenant document drafts registration requires exactly six governance paths']
    if task_id == 'APBRA-160' and branch == B and (not paths or not paths <= P):
        return ['APBRA-160 tenant document drafts product requires exactly its ten literal paths']
    return []
