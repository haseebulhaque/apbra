"""Finite historical fixture staging registration; no runtime or paid authority."""
import hashlib
import json

P = {'tests/bootstrap/test_foundry_qualification_scope.py', 'tests/bootstrap/test_generation_scope.py', 'tests/bootstrap/test_foundry_qualification_renewal_20261011_scope.py', 'tests/bootstrap/test_foundry_qualification_renewal_scope.py', 'tests/bootstrap/historical_fixture_staging.py'}
G = {'tests/bootstrap/test_foundry_qualification_scope.py', 'tests/bootstrap/historical_fixture_staging.py', 'tests/bootstrap/test_historical_fixture_staging_20261012_scope.py', 'tests/bootstrap/test_foundry_qualification_renewal_scope.py', 'scripts/check_historical_fixture_staging_20261012.py', 'tests/bootstrap/test_generation_scope.py', 'tasks/APBRA-160-historical-fixture-staging-20261012.json', 'tests/bootstrap/test_foundry_qualification_renewal_20261011_scope.py', 'scripts/check_bootstrap.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-historical-fixture-staging'
R = 'agent/APBRA-DEVOPS/APBRA-160-historical-fixture-staging-registration'
BASE = '3dfae4294334fa934223b8b1ab2654ffcc9c04f4'
RELEASE_BOUND = True
ACTOR = 'Codex via haseebulhaque authenticated GitHub and Atlassian tools'
OWNER = 'Haseeb Ul Haque'
AUTHORITY = 'Direct Haseeb existing-MVP outcome renewal2026-10-11T23:11:44Z/23:12:19Z under JiraAPBRA-16010757 and finite historical-fixture PLAN10770 authorizes this nine-path governance/test-staging correction until complete; no invented expiry. Current owner records are additive, never replacements for accepted-source hashes or historical cutoffs.'
TASK_SHA = '2f7635cf9f33e1a0fceb588d6aeefc53d8f7c561f36e067f5bb06a17e93b3f0f'
GATES = {'requirements': '8b90fbea23bb9b7c16c90392b6b2bebb29424f8aadd46c0b1c1617736fd6749e', 'adrs': 'ff97235e6354c8b368f9c39e4c12d43623f825b7ada6a74c234b85ac0ec96672', 'architecture_refs': '81353e02fc4aae2c98e51d3a396e92ec5bc9c2b3a42665a883f2faf54fef3b8a', 'restricted_paths': '1e666d52128a5a362cae27449fbdc1bd521038c59dfa675c81c2f9dd169cddbc', 'acceptance_criteria': '5a02edebd116f8acee16ff2e7dd3b825a16ac3c1c2090d23810d6369ae91b3aa', 'verification_required': 'ca3805f91e7299b623fd4ef332aeb6a156ceafacdbd40932d472f0273706081a', 'out_of_scope': '72b99d0b20fa687f9e9c2c5737eca02c3b2e6640a4eb85124226e0976e8369ab', 'escalate_when': '434903ed0194f40b7f5cefaf3e455b5dd73da9531af64d39771cc7995ad86dc6', 'dependencies': '8027223bf534b19ae5b82dd75f37c849dd29fce30b6ef1f2fd01f3d9ad650620', 'effective_release': '4e8c06142ca0b0c943c73c1930e7c4678692ac4837bca407124a15c48999b74f', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
SOURCE_FILE_SHA = '086e26d0f83e76347ab709d8859dd013513240a4e86ee9861af2086f38bb0f3e'
HISTORY = ('APBRA-108-candidate-source-safety.json', 'APBRA-129-capstone-shell.json', 'APBRA-130-requirements-snapshot.json', 'APBRA-131-curated-knowledge.json', 'APBRA-132-design-plan.json', 'APBRA-133-powerbi-project.json', 'APBRA-134-validation.json', 'APBRA-135-release.json', 'APBRA-136-orchestration.json', 'APBRA-137-final-capstone-ux.json', 'APBRA-138-measure-resolution.json', 'APBRA-139-report-design-normalization.json', 'APBRA-140-capstone-documentation.json', 'APBRA-141-measure-contract-pipeline.json', 'APBRA-142-layout-repair.json', 'APBRA-143-typed-confirmed-requirements.json', 'APBRA-144-ai-native-iterative-clarification.json', 'APBRA-145-generic-time-grain-support.json', 'APBRA-146-post-capstone-mvp-baseline-reconciliation.json', 'APBRA-147-confirmation-readiness-integrity.json', 'APBRA-148-post-capstone-product-reconciliation.json', 'APBRA-151-company-lifecycle.json', 'APBRA-159-data-model-documentation-reconciliation.json', 'APBRA-160-ai-authored-layout-20261012.json', 'APBRA-160-ai-authored-layout-raw-ingress-20261012.json', 'APBRA-160-demo-ux.json', 'APBRA-160-foundry-host.json', 'APBRA-160-foundry-owner-metadata-20261012.json', 'APBRA-160-foundry-qualification-renewal-20261011.json', 'APBRA-160-foundry-qualification-renewal.json', 'APBRA-160-foundry-qualification.json', 'APBRA-160-foundry-structured-output.json', 'APBRA-160-local-rekey.json', 'APBRA-160-provider-retrieval.json', 'APBRA-160-renderer-geometry-20261011.json', 'APBRA-162-invited-private-case-foundation.json', 'APBRA-163-durable-conversation-evidence-acceptance.json', 'APBRA-164-protected-generation-output-history.json', 'APBRA-169-business-friendly-ux-application-shell.json', 'APBRA-170-professional-saas-experience-visual-system.json', 'APBRA-171-business-user-report-creation-intelligent-generation.json', 'APBRA-172-provider-neutral-sso.json', 'APBRA-173-private-content-storage.json', 'APBRA-173-production-web-release.json', 'APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json', 'APBRA-175-deployment-portability-entitlement-docs.json', 'APBRA-176-owner-onboarding-identity-docs.json', 'APBRA-177-current-state-docs.json', 'APBRA-27-build.json', 'APBRA-76-deployment-guide.json', 'APBRA-85-bootstrap.json', 'APBRA-92-evaluation.json')
HISTORY_SHA = 'ebdadf433060ad93f094e4d17d34a97ab06adf4be3fbb56b10d67dcf40cfea8c'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bind(root, catalog, sources, validate):
    if not RELEASE_BOUND:
        return None, []
    task, failures = validate(root, catalog, sources,
        filename='APBRA-160-historical-fixture-staging-20261012.json', label='Historical fixture staging',
        branch=B, base=BASE, paths=P, task_sha=TASK_SHA, gates=GATES,
        source_bindings=SOURCES, sources_sha=SOURCES_SHA, count_label='five')
    if task is not None:
        if (task['actual_authenticated_actor'], task['human_owner'], task['human_initiator']) != (ACTOR, OWNER, OWNER):
            failures.append('APBRA-160 historical fixture staging actor/owner differs')
        if task['requirements'][0] != AUTHORITY:
            failures.append('APBRA-160 historical fixture staging outcome authority differs')
        if (task['task_mode'], task['readiness'], task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
            failures.append('APBRA-160 historical fixture staging release is not ready')
        if not (root / 'scripts/check_historical_fixture_staging_20261012.py').is_file():
            failures.append('APBRA-160 historical fixture staging helper missing')
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
        return ['APBRA-160 historical fixture staging registration requires exactly nine governance paths']
    if task_id == 'APBRA-160' and branch == B and (not paths or not paths <= P):
        return ['APBRA-160 historical fixture staging product requires exactly its five fixture paths']
    return []
