"""Finite local dispatch/audit scope proposal; no operational or publication authority."""
import hashlib
import json
from pathlib import Path
import runpy

P = {'apps/api/src/apbra_api/api.py', 'apps/api/alembic/versions/20261018_14_request_outputs.py', 'apps/api/tests/test_diagnostic_grammar_postgresql.py', 'apps/api/src/apbra_api/model_provider.py', 'apps/web/src/privateCases.test.tsx', 'apps/web/e2e/protected-generation.spec.ts', 'apps/web/src/TenantObservability.tsx', 'apps/api/src/apbra_api/native_response_index.py', 'apps/api/alembic/versions/20261017_12_native_receipts.py', 'apps/api/src/apbra_api/native_response_api.py', 'apps/web/e2e/private-case.spec.ts', 'apps/api/src/apbra_api/knowledge_documents.py', 'apps/web/src/NativeAgentCheck.tsx', 'apps/web/src/SavedAzureAnswer.test.tsx', 'apps/web/src/SavedAzureAnswer.tsx', 'apps/web/e2e/durable-conversation.spec.ts', 'apps/api/src/apbra_api/native_response_archive.py', 'apps/web/src/api.test.ts', 'apps/web/src/TenantObservability.test.tsx', 'apps/api/tests/test_provider_diagnostics.py', 'apps/web/e2e/native-outputs.spec.ts', 'apps/api/tests/test_foundry_artifacts.py', 'apps/web/src/NativeAgentCheck.test.tsx', 'apps/api/tests/test_native_contracts.py', 'apps/api/src/apbra_api/native_case_files.py', 'apps/api/src/apbra_api/provider_diagnostics.py', 'apps/api/src/apbra_api/native_contracts.py', 'apps/api/tests/test_native_case_files.py', 'apps/api/alembic/versions/20261015_10_knowledge_dispatch.py', 'apps/api/tests/test_migrations.py', 'apps/api/src/apbra_api/observability.py', 'apps/api/tests/test_diagnostic_grammar.py', 'apps/api/src/apbra_api/foundry_report_runtime.py', 'apps/api/src/apbra_api/foundry_artifacts.py', 'apps/web/e2e/audit-history.spec.ts', 'apps/api/src/apbra_api/native_response_runtime.py', 'apps/web/src/privateCases.tsx', 'apps/api/alembic/versions/20261017_13_native_contract_bindings.py', 'apps/api/alembic/versions/20261015_11_audit_errors.py', 'apps/web/src/api.ts', 'apps/api/tests/test_native_contract_diagnostics.py', 'apps/api/tests/test_native_response_integration.py', 'apps/api/src/apbra_api/request_outputs.py', 'apps/api/tests/fixtures/saved_design_unobserved_citations.json', 'apps/api/src/apbra_api/native_response_probe.py', 'apps/api/src/apbra_api/knowledge_dispatch.py', 'apps/web/src/RequestOutputs.tsx', 'apps/api/tests/test_foundry_report_runtime.py', 'apps/api/tests/test_observability.py', 'apps/api/src/apbra_api/application.py', 'apps/api/src/apbra_api/persistence.py', 'apps/api/src/apbra_api/generation.py', 'apps/web/src/RequestOutputs.test.tsx', 'apps/api/tests/test_knowledge_dispatch.py', 'apps/api/tests/test_request_outputs.py', 'apps/api/tests/test_knowledge_documents.py', 'apps/api/src/apbra_api/domain.py'}
G = {'scripts/check_bootstrap.py', 'tasks/APBRA-160-dispatch-audit-20261019.json', 'tests/bootstrap/test_dispatch_audit_20261019_scope.py', 'scripts/check_sp.py', 'tests/bootstrap/test_tenant_document_drafts_20261013_scope.py', 'scripts/check_dispatch_audit_20261019.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-native-output-ui-local'
R = 'agent/APBRA-DEVOPS/APBRA-160-audit-errors-registration'
BASE = 'f7a363dc7e5a958585f65f4cfeedf69ac20890d7'
FILENAME = 'APBRA-160-dispatch-audit-20261019.json'
TASK_SHA = '6570f88499f3557709d964f06196cd301ff3eaae96c1b7567cdd7d463fe90bd8'
GATES_NAMES = ('schema_version', 'task_id', 'work_item_system', 'execution_id', 'human_owner', 'assigned_agent', 'agent_card_version', 'risk_class', 'objective', 'requirements', 'adrs', 'architecture_refs', 'allowed_paths', 'restricted_paths', 'acceptance_criteria', 'verification_required', 'out_of_scope', 'escalate_when', 'task_mode', 'readiness', 'actual_authenticated_actor', 'human_initiator', 'base_commit', 'branch', 'source_ids', 'owner_acceptance', 'effective_release', 'dependencies')
GATES_HASHES = ('6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b', '3763d9b604cd78c31fc718c1c496b2d6bc6e59465b0db87bb021814857590cb8', '00c978369cecd75539a692e4a7fdbe0bffbfc97525ef2fedb33465bd72f22cb0', 'b630203993ca354609f1ae5655852da7e3141ad6d6113dec8dfc3641aa347caa', '54f2a2a986034ada4ea531a38415dcd35b08b62f16e5eb6638225080cbf6b542', '147a2ff6bedcf2bf79790001c78723b3edaa334d988f525ee2f82e9db8498f9c', '5a4747fcdafec66d8d8812022e3b7d2666d886ec0e0ee7926ec8c50db40f29d5', 'cb0314876ed8f3ae55780cabf10f4a8b458793c66979d8f2fe4faec57ec463c4', '5df54f3b779f66762425c0dd3d9dba6e477e8892254f3d7c5c70f870d252e182', '86305ca98a31f4e83f9e02f64cd6b1c3683ae94fb06320f87dadb1d0f1db4bd4', '8d6305199658c7b8f43912e7a2f53ffebb8c49b831b132cddfa14f6c2936b30e', 'fb5d0e21aa7f38e5a0b152da308e1b3978177e76ab24513fc41a59eb2a8aff7c', 'c211ae2219f3952382601cbd8d103fc0c1507409d376dc3c7639d3f1c1fb132f', '9fba0340ce17a65af8d1ae5978a918edddcab898b12f3f0c1e6b9ec98e837e43', 'e426c1ebec43f1155c24b6ffd180450b84eaf7e2ba4c70f57ba30e5b931a5bf3', '6f2b0a33c7ea9f6e82ebba67e1ac49979a4d0edc4d6cec0c394804a883c80088', 'e0e34c662c7ae8a71e4da59bb3464f20e75cf4c4a8f115794bf905a96e0ed9f7', '0f7e115f687a17dad40fa70f2d9b8287ba868fdd97127e46b16f0f8b96c888f4', '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582', '7448bc706f4c48de0e9f2b194be21b12687511342228d2de44bb82b986b6b181', '54f2a2a986034ada4ea531a38415dcd35b08b62f16e5eb6638225080cbf6b542', '2723e53fb79b29c78f975696288652256ba0577c9b0a3d5fd2665f116a77a802', '69139bc3039fac8c798a08575a604142409483d2887af998d4fc0f549704a765', 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'a012cfbab201c90e1dd7b34f62f5553ad4f0a358ea6e6c2a9982cbd425cc0344', '2bb764fced05347a59a748d1252e8e77f3500832832128742b01997a5e2f35f2')
GATES = dict(zip(GATES_NAMES, GATES_HASHES, strict=True))
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
HISTORY_NAMES = ('tasks/APBRA-108-candidate-source-safety.json', 'tasks/APBRA-129-capstone-shell.json', 'tasks/APBRA-130-requirements-snapshot.json', 'tasks/APBRA-131-curated-knowledge.json', 'tasks/APBRA-132-design-plan.json', 'tasks/APBRA-133-powerbi-project.json', 'tasks/APBRA-134-validation.json', 'tasks/APBRA-135-release.json', 'tasks/APBRA-136-orchestration.json', 'tasks/APBRA-137-final-capstone-ux.json', 'tasks/APBRA-138-measure-resolution.json', 'tasks/APBRA-139-report-design-normalization.json', 'tasks/APBRA-140-capstone-documentation.json', 'tasks/APBRA-141-measure-contract-pipeline.json', 'tasks/APBRA-142-layout-repair.json', 'tasks/APBRA-143-typed-confirmed-requirements.json', 'tasks/APBRA-144-ai-native-iterative-clarification.json', 'tasks/APBRA-145-generic-time-grain-support.json', 'tasks/APBRA-146-post-capstone-mvp-baseline-reconciliation.json', 'tasks/APBRA-147-confirmation-readiness-integrity.json', 'tasks/APBRA-148-post-capstone-product-reconciliation.json', 'tasks/APBRA-151-company-lifecycle.json', 'tasks/APBRA-159-data-model-documentation-reconciliation.json', 'tasks/APBRA-160-agent-details-20261013.json', 'tasks/APBRA-160-ai-authored-layout-20261012.json', 'tasks/APBRA-160-ai-authored-layout-raw-ingress-20261012.json', 'tasks/APBRA-160-browser-metadata-runtime-20261013.json', 'tasks/APBRA-160-demo-ux.json', 'tasks/APBRA-160-foundry-host.json', 'tasks/APBRA-160-foundry-owner-metadata-20261012.json', 'tasks/APBRA-160-foundry-qualification-renewal-20261011.json', 'tasks/APBRA-160-foundry-qualification-renewal.json', 'tasks/APBRA-160-foundry-qualification.json', 'tasks/APBRA-160-foundry-structured-output.json', 'tasks/APBRA-160-guided-preparation-20261014.json', 'tasks/APBRA-160-historical-fixture-staging-20261012.json', 'tasks/APBRA-160-knowledge-lifecycle-20261012.json', 'tasks/APBRA-160-local-rekey.json', 'tasks/APBRA-160-memory-handoff-20261013.json', 'tasks/APBRA-160-metadata-observations-20261013.json', 'tasks/APBRA-160-provider-retrieval.json', 'tasks/APBRA-160-released-runtime-fixtures-20261014.json', 'tasks/APBRA-160-renderer-geometry-20261011.json', 'tasks/APBRA-160-report-runtime-20261014.json', 'tasks/APBRA-160-settings-context-20261015.json', 'tasks/APBRA-160-settings-release-proof-20261015.json', 'tasks/APBRA-160-tenant-document-drafts-20261013.json', 'tasks/APBRA-162-invited-private-case-foundation.json', 'tasks/APBRA-163-durable-conversation-evidence-acceptance.json', 'tasks/APBRA-164-protected-generation-output-history.json', 'tasks/APBRA-169-business-friendly-ux-application-shell.json', 'tasks/APBRA-170-professional-saas-experience-visual-system.json', 'tasks/APBRA-171-business-user-report-creation-intelligent-generation.json', 'tasks/APBRA-172-provider-neutral-sso.json', 'tasks/APBRA-173-private-content-storage.json', 'tasks/APBRA-173-production-web-release.json', 'tasks/APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json', 'tasks/APBRA-175-deployment-portability-entitlement-docs.json', 'tasks/APBRA-176-owner-onboarding-identity-docs.json', 'tasks/APBRA-177-current-state-docs.json', 'tasks/APBRA-27-build.json', 'tasks/APBRA-76-deployment-guide.json', 'tasks/APBRA-85-bootstrap.json', 'tasks/APBRA-92-evaluation.json')
HISTORY_HASHES = ('d42e7fd2e5357fe770cbe67b4536bb5cbd455467d3a718566c0ecac357b913a7', '3e05efd9d2db7702192aa9e9203081d12a34a7518caad02d4a9f498fc048de29', '3155a2713be67e92ace41cf1365d807ffbbcfa8dc57345d3ce6da43087a63a97', '23fd841cebffd4cf1f57513920521ed8a26e614bd5273129de6a77ea032d6796', '50633731a437a40d1ef07122860278acaa5a3a090f1f89e58ad646816cadcb92', '330db17dbc8a2f1fb38808217c6c705fd1c45965c0b729835f87cd4bb02a87cd', '40966539d73a4005bf6e35e6039823438c19191ffcb7da6b9befc427ee5bb86e', '60b6ec67ad73df401a2d017536fe0d72b59ee78e3516409e4bad479e2d9abc86', '0c8450c665bfbec024590cd70bba9a01b500a60d3b91467c261c8b269ba6ee6a', '068848a69f18fc7d9ffddeb0296f624d17223377f8b4fe33991a506a82e32ddd', '3da155be8a85d249baa86db057a14f398a63b6ea5e6c5659d961fd44ca56a320', 'bc8ae0f00a65be8591ea65c42c7bcde3efabc0445db06e2943c4e22bc5d1b877', '7c8896c9b057022307e18cbd1ba298af5e993494b3dbe3f5ac664f0a7fdd5b47', 'f59591a1014ecd6905e8732824325a70484fef0fc1f3cbdf42d125d4439bbb0c', '06c996d7b61a8bea2ddea05fe105133a0e1d56d4ba0c3e74bf0b72510b89016b', '9bc453d9e5309afbd5129d05c3c3612c2aaa25bfcafb50cd0f393b253504955d', '87cd80146c0837ae52c56f4dc755866559419902b3c18dd5b54b995656aba8bb', '9e23f1efb28cee7ec42d095f759965560c7651f3d4113b27eea18a95b2d1acc1', 'c8cdcc62a1ef6e70cbe3d4297f6ba4d2dc7ad0c2edd3158440798f568fc1add5', '9645eac75ee20d25b676b112fecb2bfdd5cdfb43781d6c8354dd7c471023aaf1', 'dabab378832998778203a2b0f17682b6d24ce6bf93461ba2f93677e6cdd94da3', '574d6c14f37e23785e85540857b3c53553323a603d19e4383ab1a3477d1eec34', 'b8f922284844c7fa1ffd715b97dfc877bf59d8c4853ac3a96a798852ccaece5f', 'e4b0f5b865156176108e765cf4fdaae52f72b3ad48f234f9e751987df06284a6', '35deb0c7603c6c587c50d83b4c82809b0cee4056cd93f7f232247775394bbe1f', '3aabf439ab78ac7c21090617543958f99828647b9cd0ae40479770a62f7eae77', '705a575cfef49e10588e1e14cbb2979afb9589767374fae2236406828e1baf47', '91c9820dc442af7e3b7419baca9c45902519c910a5606f1eb3962fbeb486206d', 'f24f372095419e3b5d9fc389a653bf185fdd1ebec479c38e77fe6362d8a707cc', 'a7274831eb2950322bedc6fd552748040e9f9d48439f3f3c1b7328f460c67ce4', '256e05b62c282596d5b54acbbe69a3ed7557128e156a53fa54a02fbe2a5ab65c', '482bc4d5116907812bde8272887efd4b2b8a02c02aff9e2d369819b6fa0acfdf', '8d8d86c0165ba1f5bbda1b9e34173d4deb272a120bb5200c269bc401fdd61228', '728e1b82b87b2e71b37cdb995882ba7eaa7e80a12339ca5fab4bf2ba80230db0', 'c548a0351be13a0a83ef0bc2e78369c82cdda03a7d3c72044c3a90b0e68508ea', 'e3107f259ac178bfcbed22ffffd19b3c1836a2855d0ca05c15c1de1b59aebdb4', '03b6656db92ac5e49ac9a77dfb66e56bad34f2ca91097b494fd5a2343dbf7131', '9abf0760b6d30fab880436414d61ffaa94cc25494cfccbc3e54818c7fd3a80e8', '7ddb0248602163af40594aff2fad793320b71d04d5899787fa9b03b686abe7e5', 'c69c0050c252e4f9a0e25b8c97a6745800c2301bf5a547e5fe2f2dc92d8066a1', '66a41066a012839970bf4588c72967138ca6dd61b94d5d75ea8a9309d4d021b7', '2d4475602e540bfcdc72500ed460e182c96927373ac1e77b998aa41bab010977', '4700aa2cc1b26ebf9844eafd7445d7c8940c8c71a55d1a5536ad1cac72160247', 'eef778939ddef51e248f325263dc488cecd40f56d87a0acd2edeabdfe366d8e0', '6fad3868e3d34201769cdb1e926717591664635082a1331f91ae3a4f5e39dae2', '3632de6e673b8cfa5cd109ae9987bf2db74bbbf00057f9ffd1e939ef66c73d61', '521da20e06cf8b5c1e2806fe21b5babbe7c2c37fcc1cf3197033cbbaa8f9b448', '858d6288387d2c8596e7a258b521e10fabc91ba2a0d6e399546eb7d6e5389534', 'fa8215fc588ba5df22ec8c49de44c99a3120e70787a181dcd26bf2845d383463', 'f4e6a2b14682a68c96646f9c76b96f942e6f9a6927f9eac8c53ceb3cc422053d', '537a803bf2354a099b14dde12dd874922d24c7ceed14d4eb5ce03d609e41889a', '9d81771cc9ce9921b2c044e5732cb5d17ad94bd86d412d4b56a3a985adf5188e', 'b353f1882cb801bd5ffeffa1969f2485906723c0ac7bde8516b3f1ac1572a3a8', '4b308ad91c90afda156241a7bfcf98887897bdb920ae5dbd34f8bf6ee00736e7', 'fc091f799a651c8976df1d43b0358c6c4214ebd511669da6f1ad407341e4acb4', 'ba2e92af65a8b0335a6e422fb4f4005d3185c5d3f4f3d571538c6beafa35a3cc', '81d7f8f92db54b5357c98b7bd22a003a6d7697d23efc159de444a25304f58949', '036b3bb0d5e4b5956259ae6df65aee29c62f1bb6e1050692c3d4bf702633deaf', '0ef2f3dd9d794e44b385cf1ebbbcd225dd298deb3448d388cef63a6f19be5d2d', '7d50ed3d0a7eb5faaf361aa8f252d2e548a3e793b4765ee19e19afd29283ef71', '8df6ea632a1a36de03b8621daa4e68901891c6dfa593f9f09ae8f7fcf877af07', 'c7aab1b39825c5202bf4258447ffe0c1fa083bed5790bce87fc836c603b2510a', 'ebc880c2f7cb4f6f6d0d58d05b3b15c0ed8b737002b37c20748a3e62e58ce462', 'cac9e3cc9596be6eea982513e7fcf70d419416f6377029097f979ebfdb3c61a5')
HISTORY = dict(zip(HISTORY_NAMES, HISTORY_HASHES, strict=True))
SOURCE_FILE_SHA = '086e26d0f83e76347ab709d8859dd013513240a4e86ee9861af2086f38bb0f3e'
CATALOG_SHA = 'e8fcc0667f9e185e41617e1d2eb5da6d3c350844326bf3f56ddd58c6d843bce7'
AUTHORITY = 'Direct owner-delegated local MVP continuation2026-10-19: integrate the reviewed dispatch/audit checkpoint with dependent native receipts and contract bindings, opaque request outputs and artifact transport/UI; preserve original model output and the separate compiler. Prepare combined release/adoption plan. No publication/merge, live preview change, credential change, owner configuration/database inspection, paid service invocation or WhatsApp access is authorized.'

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bind(root, catalog, sources, validate):
    target = root / 'tasks' / FILENAME
    if not target.exists():
        return None, []
    if target.is_symlink():
        return None, ['Dispatch/audit task cannot be a symlink']
    task, failures = validate(root, catalog, sources, filename=FILENAME,
        label='local dispatch/audit', branch=B, base=BASE, paths=P,
        task_sha=TASK_SHA, gates=GATES, source_bindings=SOURCES,
        sources_sha=SOURCES_SHA, count_label='fifty-seven')
    for name, expected in {**HISTORY, 'docs/source-register.json': SOURCE_FILE_SHA,
                           'agents/catalog.json': CATALOG_SHA}.items():
        path = root / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append('Dispatch/audit historical binding differs: ' + name)
    if task is not None and task['requirements'][0] != AUTHORITY:
        failures.append('Dispatch/audit local owner scope differs')
    return (None if failures else task), failures


def stage(task_id, branch, paths):
    return task_id == 'APBRA-160' and branch == R and paths == G


def ok(task, branch, paths):
    return task is not None and ((branch == R and paths == G) or
                                (branch == B and bool(paths) and paths <= P))


def errors(task, branch, paths):
    if branch in {B, R} and not ok(task, branch, paths):
        return ['Dispatch/audit requires exact six-path registration or literal product-only scope']
    return []


def strip_hooks(source):
    for count, hook in HOOKS:
        if source.count(hook) != count:
            raise ValueError('Dispatch/audit hook differs')
        source = source.replace(hook, '')
    return source


def strip_sp_changes(source):
    for before, after in SP_EDITS:
        if source.count(after) != 1:
            raise ValueError('Dispatch/audit helper inverse differs')
        source = source.replace(after, before, 1)
    return source

HOOKS = [(1, "da=runpy.run_path(Path(__file__).parent/'check_dispatch_audit_20261019.py')\n"), (1, "        dat,de=da['bind'](root,catalog,sources,bound_provider_registration);errors+=de\n"), (1, "(dat,da['P']),\n"), (1, "                else dat if active_branch in {da['B'],da['R']}\n"), (2, " and not da['ok'](dat,active_branch,changed_paths)"), (1, "            errors+=da['errors'](dat,active_branch,changed_paths)\n"), (1, "                    not da['stage'](active_task_id, active_branch, changed_paths) and\n"), (1, "                    (active_task is not None and da['stage'](active_task_id, active_branch, changed_paths)\n                     and name in da['G'] and path_allowed(name, task, card)) or\n")]
SP_EDITS = [('def strip_hooks(source):\n', 'def strip_hooks(source):\n    if "da=runpy.run_path(" in source:\n        source=runpy.run_path(Path(__file__).with_name(\'check_dispatch_audit_20261019.py\'))[\'strip_hooks\'](source)\n')]

HISTORICAL_TREE = '072273dcae5a5d1cdc2038795b393aa2cf93d6b0'
HISTORICAL_UNIVERSE_SHA = '819ecdf4399d9ea6d714e1be5cb220814c20e3ac88709c0c4a6be663fb80cb36'
DOCUMENT_FIXTURE_EDIT = ("        for name in {p.relative_to(ROOT).as_posix() for p in c.repo_files(ROOT)} | h['G']:\n", "        for name in c.da['historical_document_fixture_names'](ROOT, h['G']):\n")


def historical_document_fixture_names(source_root, additions):
    """Test-only pinned prior universe plus explicit old scope and helper dependency.

    Actual checker enumeration remains exhaustive. No runtime authority or
    historical assertion changes; a prospective old fixture omits future tasks.
    """
    import subprocess
    from pathlib import PurePosixPath

    try:
        tree = subprocess.check_output(['git', '-C', str(source_root), 'rev-parse',
                                       BASE + '^{tree}'], stderr=subprocess.PIPE, timeout=10).decode().strip()
        if tree != HISTORICAL_TREE:
            raise ValueError('Historical fixture tree differs')
        raw = subprocess.check_output(['git', '-C', str(source_root), 'ls-tree', '-rz',
                                      '--name-only', BASE], stderr=subprocess.PIPE, timeout=10)
        if hashlib.sha256(raw).hexdigest() != HISTORICAL_UNIVERSE_SHA:
            raise ValueError('Historical fixture universe differs')
        names = raw.decode().split('\0')
        if not names or names[-1] != '' or len(set(names[:-1])) != len(names) - 1:
            raise ValueError('Historical fixture universe malformed')
        selected = set(names[:-1])
        for name in [*selected, *additions, 'scripts/check_dispatch_audit_20261019.py']:
            if (type(name) is not str or not name or '\\' in name or '\0' in name
                    or PurePosixPath(name).is_absolute()
                    or any(part in ('', '.', '..', '.git') for part in name.split('/'))):
                raise ValueError('Historical fixture path unsafe')
            selected.add(name)
        return selected
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        raise ValueError('Document historical fixture context unavailable') from None
