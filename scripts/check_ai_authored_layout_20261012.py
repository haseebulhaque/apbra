"""Additive outcome-bounded AI geometry authority; all prior authorities stay historical."""
import hashlib
import json

P = {'apps/api/src/apbra_api/config.py', 'apps/api/src/apbra_api/generation.py', 'apps/api/src/apbra_api/model_provider.py', 'apps/api/src/apbra_api/tenant_settings.py', 'apps/api/tests/test_api.py', 'apps/api/tests/test_config.py', 'apps/api/tests/test_generation.py', 'apps/api/tests/test_model_provider.py', 'apps/api/tests/test_tenant_settings.py', 'apps/web/e2e/protected-generation.spec.ts', 'apps/web/e2e/tenant-settings.spec.ts', 'apps/web/knowledge/report-design-format-contract-v2.md', 'apps/web/scripts/generation-bridge.ts', 'apps/web/src/App.test.tsx', 'apps/web/src/EnterpriseApp.tsx', 'apps/web/src/aiGeometry.test.ts', 'apps/web/src/aiGeometry.ts', 'apps/web/src/foundry.test.ts', 'apps/web/src/foundry.ts', 'apps/web/src/genericPowerBI.test.ts', 'apps/web/src/genericPowerBI.ts', 'apps/web/src/guardrail.test.ts', 'apps/web/src/guardrail.ts', 'apps/web/src/rag.test.ts', 'apps/web/src/rag.ts', 'apps/web/src/reportDesignNormalization.test.ts', 'apps/web/src/reportDesignNormalization.ts', 'apps/web/src/tenant.ts'}
G = {'scripts/check_ai_authored_layout_20261012.py', 'scripts/check_bootstrap.py', 'tasks/APBRA-160-ai-authored-layout-20261012.json', 'tests/bootstrap/test_ai_authored_layout_20261012_scope.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-ai-authored-layout'
R = 'agent/APBRA-DEVOPS/APBRA-160-ai-authored-layout-registration'
BASE = 'fbbd1b9c2cbde8b89bef8dfd55e29a0c6b1fedef'
ACTOR = 'Codex via haseebulhaque authenticated GitHub and Atlassian tools'
OWNER = 'Haseeb Ul Haque'
AUTHORITY = 'Haseeb directly renewed existing-MVP development at 2026-10-11T23:11:44Z and 2026-10-11T23:12:19Z until the bounded existing MVP correction is complete; this is outcome-bounded additive authority with no invented future expiry. Jira APBRA-160 comment10757 and current Confluence delivery records preserve all historical authorities and expired cutoffs as history.'
TASK_SHA = '305d460360b4d5254fab1cd5dfc09314eaa83f843b59f0ca074ba1cf83bec784'
GATES = {'requirements': '3954cda207340549ab355cce79cc389930cd59eeebfbb26776eb41141b6df5f5', 'adrs': '4625f007238a5b49d8f493f4efd3573f234ad869e2ebfbddd24e2ddbd45e2a55', 'architecture_refs': '680dad1c31639b13b5acf4fd882d4d9bc62538ef519e9540a9d3b92e28898d21', 'restricted_paths': '8efeef4ebffde9f48e8bf124c482f304063e3550acbbd2271354837fb1db0ae6', 'acceptance_criteria': 'f2d0e67d59baad05a4840d7eecbcf6a14df0c62782d6d8c83634717622ecd070', 'verification_required': '66f46a74714752f9479d94a2ed5348d4c5cc3ad1ed985604e2e310947b1b9004', 'out_of_scope': '737031ed5a3917596ba6361f9aa5813210d98d549f077d2a0b665b3dd912f01a', 'escalate_when': '4e826070a3ab7ee8da62a3bf2cee68715564570929d0e471e44b4596afafe67f', 'dependencies': '6ebf1c6c306793ac851999562e1a7be8d78b6e2bc121c2807e915b760527be2a', 'effective_release': '70d45f9f98d19e5d0efbe75768d5831e4963db9ca8b9f64d133198433fb4bec3', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
SOURCE_FILE_SHA = '086e26d0f83e76347ab709d8859dd013513240a4e86ee9861af2086f38bb0f3e'
HISTORY = ('APBRA-108-candidate-source-safety.json', 'APBRA-129-capstone-shell.json', 'APBRA-130-requirements-snapshot.json', 'APBRA-131-curated-knowledge.json', 'APBRA-132-design-plan.json', 'APBRA-133-powerbi-project.json', 'APBRA-134-validation.json', 'APBRA-135-release.json', 'APBRA-136-orchestration.json', 'APBRA-137-final-capstone-ux.json', 'APBRA-138-measure-resolution.json', 'APBRA-139-report-design-normalization.json', 'APBRA-140-capstone-documentation.json', 'APBRA-141-measure-contract-pipeline.json', 'APBRA-142-layout-repair.json', 'APBRA-143-typed-confirmed-requirements.json', 'APBRA-144-ai-native-iterative-clarification.json', 'APBRA-145-generic-time-grain-support.json', 'APBRA-146-post-capstone-mvp-baseline-reconciliation.json', 'APBRA-147-confirmation-readiness-integrity.json', 'APBRA-148-post-capstone-product-reconciliation.json', 'APBRA-151-company-lifecycle.json', 'APBRA-159-data-model-documentation-reconciliation.json', 'APBRA-160-demo-ux.json', 'APBRA-160-foundry-host.json', 'APBRA-160-foundry-qualification-renewal-20261011.json', 'APBRA-160-foundry-qualification-renewal.json', 'APBRA-160-foundry-qualification.json', 'APBRA-160-foundry-structured-output.json', 'APBRA-160-local-rekey.json', 'APBRA-160-provider-retrieval.json', 'APBRA-160-renderer-geometry-20261011.json', 'APBRA-162-invited-private-case-foundation.json', 'APBRA-163-durable-conversation-evidence-acceptance.json', 'APBRA-164-protected-generation-output-history.json', 'APBRA-169-business-friendly-ux-application-shell.json', 'APBRA-170-professional-saas-experience-visual-system.json', 'APBRA-171-business-user-report-creation-intelligent-generation.json', 'APBRA-172-provider-neutral-sso.json', 'APBRA-173-private-content-storage.json', 'APBRA-173-production-web-release.json', 'APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json', 'APBRA-175-deployment-portability-entitlement-docs.json', 'APBRA-176-owner-onboarding-identity-docs.json', 'APBRA-177-current-state-docs.json', 'APBRA-27-build.json', 'APBRA-76-deployment-guide.json', 'APBRA-85-bootstrap.json', 'APBRA-92-evaluation.json')
HISTORY_SHA = '7b11f1b578f38179aac5eb6f94dccba4ab34f9704d0754faa1d64f7b5f46cca7'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bind(root, catalog, sources, validate):
    task, failures = validate(
        root, catalog, sources, filename='APBRA-160-ai-authored-layout-20261012.json',
        label='AI-authored outcome layout', branch=B, base=BASE, paths=P,
        task_sha=TASK_SHA, gates=GATES, source_bindings=SOURCES,
        sources_sha=SOURCES_SHA, count_label='28',
    )
    if task is not None:
        if (task['actual_authenticated_actor'], task['human_owner'], task['human_initiator']) != (ACTOR, OWNER, OWNER):
            failures.append('APBRA-160 AI layout actor/owner differs')
        if task['requirements'][0] != AUTHORITY:
            failures.append('APBRA-160 AI layout outcome authority differs')
        if not (root / 'scripts/check_ai_authored_layout_20261012.py').is_file():
            failures.append('APBRA-160 AI layout helper missing')
        source = root / 'docs/source-register.json'
        current = {name: hashlib.sha256((root / 'tasks' / name).read_bytes()).hexdigest()
                   for name in HISTORY if (root / 'tasks' / name).is_file()}
        if (digest(current) != HISTORY_SHA or not source.is_file() or
                hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_FILE_SHA):
            # Withdraw only additive authority; never rescue historical branches.
            return None, failures
    return (None if failures else task), failures


def stage(task_id, branch, paths):
    return task_id == 'APBRA-160' and branch == R and paths == G


def errors(task_id, branch, paths):
    if task_id == 'APBRA-160' and branch == R and paths != G:
        return ['APBRA-160 AI layout registration requires exactly four governance paths']
    if task_id == 'APBRA-160' and branch == B and (not paths or not paths <= P):
        return ['APBRA-160 AI layout product changes require only registered 28 literal paths']
    return []
