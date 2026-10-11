"""Finite Oct11 renderer registration; historical authorities stay independent."""
import hashlib
import json

P = {'apps/web/src/reportDesignNormalization.test.ts', 'apps/web/src/genericPowerBI.ts', 'apps/api/tests/test_generation.py', 'apps/api/src/apbra_api/model_provider.py', 'apps/api/tests/test_model_provider.py', 'apps/web/src/App.test.tsx', 'apps/web/src/genericPowerBI.test.ts'}
G = {'tests/bootstrap/test_renderer_geometry_20261011_scope.py', 'tasks/APBRA-160-renderer-geometry-20261011.json', 'scripts/check_renderer_geometry_20261011.py', 'scripts/check_bootstrap.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-renderer-geometry-20261011'
R = 'agent/APBRA-DEVOPS/APBRA-160-renderer-geometry-20261011-registration'
BASE = 'cec39faab7ee56750676b25f4f001e26dcd207e6'
CUTOFF = '2026-10-11T20:19:10Z'
ACTOR = 'Codex via haseebulhaque authenticated GitHub and Atlassian tools'
OWNER = 'Haseeb Ul Haque'
TASK_SHA = '9b7e36d3aa58fd532bda6f9e11bc005e08f053f461f33c205bd32765d3bda05a'
GATES = {'requirements': '189204ca1bf2ccb46ea4f91e35a40e70d499968cc4b5d1f82420bd78baf8b900', 'adrs': '430394785cd9f5e6423f92a37c36b4f4c4d57e1c7a4d96eb6bf60779a6114a6c', 'architecture_refs': '103913b4d28dd4fa4ecf67b41f29025abed72485c5114ecc43243a645dc79c7c', 'restricted_paths': 'de77f67e99f52f79647e6f66f7d89bef8f3f4653c23a0675769c5e02b4c6c091', 'acceptance_criteria': '95b54f7bfa7b2e9de88baad810d1f10f3c8d05ce7f9b406757fca2a4ef6b68f9', 'verification_required': '2d48a100844cbb27d07bc4a5ee3059b8586d66f17bb8d61e1966f2a5c1ecc27c', 'out_of_scope': 'daca62a1de319eb0e88ad140a7a0d8b523911f6fd52b47fe2cb24681e35050b5', 'escalate_when': '7c8ce101db298d4afe3912da2b911705b94c52749cbc7fdb6ae4016d5ae2f4c5', 'dependencies': '729715e42715936c556c37d79c70c8a80e01f174ab91216340f792721359f510', 'effective_release': '5a85ffbd5d15386224866cb524ab1281326160ac2cb0d386d69daec8b7c56c7d', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
HISTORY = ('APBRA-108-candidate-source-safety.json', 'APBRA-129-capstone-shell.json', 'APBRA-130-requirements-snapshot.json', 'APBRA-131-curated-knowledge.json', 'APBRA-132-design-plan.json', 'APBRA-133-powerbi-project.json', 'APBRA-134-validation.json', 'APBRA-135-release.json', 'APBRA-136-orchestration.json', 'APBRA-137-final-capstone-ux.json', 'APBRA-138-measure-resolution.json', 'APBRA-139-report-design-normalization.json', 'APBRA-140-capstone-documentation.json', 'APBRA-141-measure-contract-pipeline.json', 'APBRA-142-layout-repair.json', 'APBRA-143-typed-confirmed-requirements.json', 'APBRA-144-ai-native-iterative-clarification.json', 'APBRA-145-generic-time-grain-support.json', 'APBRA-146-post-capstone-mvp-baseline-reconciliation.json', 'APBRA-147-confirmation-readiness-integrity.json', 'APBRA-148-post-capstone-product-reconciliation.json', 'APBRA-151-company-lifecycle.json', 'APBRA-159-data-model-documentation-reconciliation.json', 'APBRA-160-demo-ux.json', 'APBRA-160-foundry-host.json', 'APBRA-160-foundry-qualification-renewal-20261011.json', 'APBRA-160-foundry-qualification-renewal.json', 'APBRA-160-foundry-qualification.json', 'APBRA-160-foundry-structured-output.json', 'APBRA-160-local-rekey.json', 'APBRA-160-provider-retrieval.json', 'APBRA-162-invited-private-case-foundation.json', 'APBRA-163-durable-conversation-evidence-acceptance.json', 'APBRA-164-protected-generation-output-history.json', 'APBRA-169-business-friendly-ux-application-shell.json', 'APBRA-170-professional-saas-experience-visual-system.json', 'APBRA-171-business-user-report-creation-intelligent-generation.json', 'APBRA-172-provider-neutral-sso.json', 'APBRA-173-private-content-storage.json', 'APBRA-173-production-web-release.json', 'APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json', 'APBRA-175-deployment-portability-entitlement-docs.json', 'APBRA-176-owner-onboarding-identity-docs.json', 'APBRA-177-current-state-docs.json', 'APBRA-27-build.json', 'APBRA-76-deployment-guide.json', 'APBRA-85-bootstrap.json', 'APBRA-92-evaluation.json')
HISTORY_SHA = '18403656ba728b948889965ca38c5d86a9828d27d32c93801ab8081b523e2968'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bind(root, catalog, sources, validate):
    task, failures = validate(
        root, catalog, sources, filename='APBRA-160-renderer-geometry-20261011.json',
        label='Oct11 renderer geometry', branch=B, base=BASE, paths=P,
        task_sha=TASK_SHA, gates=GATES, source_bindings=SOURCES,
        sources_sha=SOURCES_SHA, count_label='seven',
    )
    if task is not None:
        if (task['actual_authenticated_actor'], task['human_owner'], task['human_initiator']) != (ACTOR, OWNER, OWNER):
            failures.append('APBRA-160 Oct11 renderer geometry actor/owner differs')
        if not task['requirements'][0].startswith('The sole overnight implementation and conditional merge ceiling is ' + CUTOFF + ' '):
            failures.append('APBRA-160 Oct11 renderer geometry cutoff differs')
        if not (root / 'scripts/check_renderer_geometry_20261011.py').is_file():
            failures.append('APBRA-160 Oct11 renderer geometry helper missing')
        current = {name: hashlib.sha256((root / 'tasks' / name).read_bytes()).hexdigest()
                   for name in HISTORY if (root / 'tasks' / name).is_file()}
        if digest(current) != HISTORY_SHA:
            # Withdraw only new authority; retain historical branches' exact errors.
            return None, failures
    return (None if failures else task), failures


def stage(task_id, branch, paths):
    return task_id == 'APBRA-160' and branch == R and paths == G


def errors(task_id, branch, paths):
    if task_id == 'APBRA-160' and branch == R and paths != G:
        return ['APBRA-160 Oct11 renderer registration requires exactly four governance paths']
    if task_id == 'APBRA-160' and branch == B and (not paths or not paths <= P):
        return ['APBRA-160 Oct11 renderer product changes require only registered seven literal paths']
    return []
