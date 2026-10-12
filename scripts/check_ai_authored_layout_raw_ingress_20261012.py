"""Additive raw-ingress integrity registration; no runtime or paid authority."""
import hashlib
import json

P = {'apps/api/src/apbra_api/tenant_settings.py', 'apps/web/src/foundry.test.ts', 'apps/web/src/reportDesignNormalization.ts', 'apps/web/src/aiGeometry.test.ts', 'apps/web/e2e/protected-generation.spec.ts', 'apps/web/src/guardrail.ts', 'apps/web/src/tenant.ts', 'apps/api/tests/test_config.py', 'apps/web/knowledge/report-design-format-contract-v2.md', 'apps/web/scripts/generation-bridge.ts', 'apps/web/src/EnterpriseApp.tsx', 'apps/web/src/foundry.ts', 'apps/web/src/rag.test.ts', 'apps/web/src/aiGeometry.ts', 'apps/web/src/api.ts', 'apps/api/src/apbra_api/model_provider.py', 'apps/api/src/apbra_api/generation.py', 'apps/web/src/guardrail.test.ts', 'apps/web/src/genericPowerBI.test.ts', 'apps/api/tests/test_api.py', 'apps/web/src/durableGeneration.tsx', 'apps/api/tests/test_tenant_settings.py', 'apps/api/src/apbra_api/config.py', 'apps/web/src/App.test.tsx', 'apps/web/e2e/tenant-settings.spec.ts', 'apps/web/src/reportDesignNormalization.test.ts', 'apps/api/tests/test_generation.py', 'apps/web/src/genericPowerBI.ts', 'apps/api/src/apbra_api/api.py', 'apps/api/tests/test_model_provider.py', 'apps/web/src/rag.ts'}
G = {'scripts/check_ai_authored_layout_raw_ingress_20261012.py', 'tests/bootstrap/test_ai_authored_layout_raw_ingress_20261012_scope.py', 'tasks/APBRA-160-ai-authored-layout-raw-ingress-20261012.json', 'scripts/check_bootstrap.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-ai-authored-layout-raw-ingress'
R = 'agent/APBRA-DEVOPS/APBRA-160-ai-authored-layout-raw-ingress-registration'
BASE = 'ad236e098199bfd1500f1010535e4f5a2317fc38'
RELEASE_BOUND = True
ACTOR = 'Codex via haseebulhaque authenticated GitHub and Atlassian tools'
OWNER = 'Haseeb Ul Haque'
AUTHORITY = 'Direct Haseeb existing-MVP outcome renewal2026-10-11T23:11:44Z/23:12:19Z under JiraAPBRA-16010757 and new raw-ingress PLAN10766 authorizes the existing AI geometry correction and necessary raw-source format-integrity repair until complete; no invented future expiry. Confluence4063307v41/8519682v56 supplement rather than replace historical accepted authority.'
TASK_SHA = '53f79b67180f70570711e3d90663ab07cc2451cafa4805945dca25cb6f0a41bb'
GATES = {'requirements': 'b97b5c809b18bf93804a5bd44078e0d0c881a351955e55db57d08bcbc5f96fe9', 'adrs': '95cee7994a8c0c6b4b6a34c9bd998d4b178d927124477a2d3503e81c55e19cda', 'architecture_refs': 'f111475dbb878d7ee1a80da53b4726779a2efc458e1c60f4a5d1fd8b4516c9ae', 'restricted_paths': '43db2c6c687f070551a6092c32614003ab957e456f764b5c6d989a82a110293c', 'acceptance_criteria': '7f52c364de53df01aa30ccfcb12556ca9e37511f6c849a54fac2793e2ba97fc8', 'verification_required': '12231f39f7b612f0732b864031a7be2e808ceffb84ecd2029006ff80a8cfbd7c', 'out_of_scope': '717d50b40d31728e5d909cf5446a075c73890de593cdbbbddf155f38772e083b', 'escalate_when': '2c02a91667db7e1c598b62f6e624940d7bccdeab8f62ce45b36b1fa5ccd8656c', 'dependencies': 'ed9808cab67be9c367f9fbccb537fc80e0bdfc443c0ecc3bc706c648ab5c0cdd', 'effective_release': '60acbffd8c49215ec031bd77acf418efe56381dddbee8e0edeca7ed7462086dc', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
SOURCE_FILE_SHA = '086e26d0f83e76347ab709d8859dd013513240a4e86ee9861af2086f38bb0f3e'
HISTORY = ('APBRA-108-candidate-source-safety.json', 'APBRA-129-capstone-shell.json', 'APBRA-130-requirements-snapshot.json', 'APBRA-131-curated-knowledge.json', 'APBRA-132-design-plan.json', 'APBRA-133-powerbi-project.json', 'APBRA-134-validation.json', 'APBRA-135-release.json', 'APBRA-136-orchestration.json', 'APBRA-137-final-capstone-ux.json', 'APBRA-138-measure-resolution.json', 'APBRA-139-report-design-normalization.json', 'APBRA-140-capstone-documentation.json', 'APBRA-141-measure-contract-pipeline.json', 'APBRA-142-layout-repair.json', 'APBRA-143-typed-confirmed-requirements.json', 'APBRA-144-ai-native-iterative-clarification.json', 'APBRA-145-generic-time-grain-support.json', 'APBRA-146-post-capstone-mvp-baseline-reconciliation.json', 'APBRA-147-confirmation-readiness-integrity.json', 'APBRA-148-post-capstone-product-reconciliation.json', 'APBRA-151-company-lifecycle.json', 'APBRA-159-data-model-documentation-reconciliation.json', 'APBRA-160-ai-authored-layout-20261012.json', 'APBRA-160-demo-ux.json', 'APBRA-160-foundry-host.json', 'APBRA-160-foundry-owner-metadata-20261012.json', 'APBRA-160-foundry-qualification-renewal-20261011.json', 'APBRA-160-foundry-qualification-renewal.json', 'APBRA-160-foundry-qualification.json', 'APBRA-160-foundry-structured-output.json', 'APBRA-160-local-rekey.json', 'APBRA-160-provider-retrieval.json', 'APBRA-160-renderer-geometry-20261011.json', 'APBRA-162-invited-private-case-foundation.json', 'APBRA-163-durable-conversation-evidence-acceptance.json', 'APBRA-164-protected-generation-output-history.json', 'APBRA-169-business-friendly-ux-application-shell.json', 'APBRA-170-professional-saas-experience-visual-system.json', 'APBRA-171-business-user-report-creation-intelligent-generation.json', 'APBRA-172-provider-neutral-sso.json', 'APBRA-173-private-content-storage.json', 'APBRA-173-production-web-release.json', 'APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json', 'APBRA-175-deployment-portability-entitlement-docs.json', 'APBRA-176-owner-onboarding-identity-docs.json', 'APBRA-177-current-state-docs.json', 'APBRA-27-build.json', 'APBRA-76-deployment-guide.json', 'APBRA-85-bootstrap.json', 'APBRA-92-evaluation.json')
HISTORY_SHA = 'be4dd3551b8d0d0cf719ca066799513ff287f8314dc70e0d8879c912aed63dae'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bind(root, catalog, sources, validate):
    if not RELEASE_BOUND:
        return None, []
    task, failures = validate(root, catalog, sources,
        filename='APBRA-160-ai-authored-layout-raw-ingress-20261012.json', label='AI layout raw ingress',
        branch=B, base=BASE, paths=P, task_sha=TASK_SHA, gates=GATES,
        source_bindings=SOURCES, sources_sha=SOURCES_SHA, count_label='31')
    if task is not None:
        if (task['actual_authenticated_actor'], task['human_owner'], task['human_initiator']) != (ACTOR, OWNER, OWNER):
            failures.append('APBRA-160 raw ingress actor/owner differs')
        if task['requirements'][0] != AUTHORITY:
            failures.append('APBRA-160 raw ingress outcome authority differs')
        if (task['task_mode'], task['readiness'], task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
            failures.append('APBRA-160 raw ingress release is not ready')
        if not (root / 'scripts/check_ai_authored_layout_raw_ingress_20261012.py').is_file():
            failures.append('APBRA-160 raw ingress helper missing')
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
        return ['APBRA-160 raw ingress registration requires exactly four governance paths']
    if task_id == 'APBRA-160' and branch == B and (not paths or not paths <= P):
        return ['APBRA-160 raw ingress product requires exactly its 31 literal paths']
    return []
