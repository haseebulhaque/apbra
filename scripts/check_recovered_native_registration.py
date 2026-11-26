"""Canonical public v2 registration; frozen observations are not release facts."""
import hashlib,json,subprocess,re
from pathlib import Path
from fnmatch import fnmatchcase
G = {'apps/api/tests/conftest.py', 'apps/api/tests/test_foundry_private_preparation.py', 'apps/api/tests/test_foundry_report_runtime.py', 'apps/api/tests/test_native_case_files.py', 'apps/api/tests/test_native_contracts.py', 'apps/api/tests/test_native_response_integration.py', 'apps/api/tests/test_report_authorization_clock.py', 'docs/engineering/recovered-native-frozen-manifests.json', 'docs/engineering/recovered-native-public-registration.md', 'scripts/check_bootstrap.py', 'scripts/check_nv.py', 'scripts/check_recovered_native_registration.py', 'tasks/APBRA-160-recovered-account-public-v2.json', 'tasks/APBRA-183-native-organisation-public-v2.json', 'tasks/APBRA-183-recovered-native-registration-public-v2.json', 'tests/bootstrap/fixtures/settings-release-proof-c92d488-application.txt', 'tests/bootstrap/test_dispatch_audit_20261019_scope.py', 'tests/bootstrap/test_native_output_verification_20261019_scope.py', 'tests/bootstrap/test_recovered_native_registration_scope.py', 'tests/bootstrap/test_settings_release_proof_scope.py', 'tests/bootstrap/test_tenant_document_drafts_20261013_scope.py'}
Q = {'apps/api/alembic/versions/20261105_15_tenant_date_display.py', 'apps/api/alembic/versions/20261105_16_session_identity_contact.py', 'apps/api/alembic/versions/20261106_17_password_auth.py', 'apps/api/pyproject.toml', 'apps/api/src/apbra_api/api.py', 'apps/api/src/apbra_api/application.py', 'apps/api/src/apbra_api/config.py', 'apps/api/src/apbra_api/domain.py', 'apps/api/src/apbra_api/foundry_admin_reads.py', 'apps/api/src/apbra_api/foundry_agent_details.py', 'apps/api/src/apbra_api/foundry_browser_handoff.py', 'apps/api/src/apbra_api/foundry_browser_relay.py', 'apps/api/src/apbra_api/foundry_catalogue_lease.py', 'apps/api/src/apbra_api/foundry_memory_handoff.py', 'apps/api/src/apbra_api/foundry_private_preparation.py', 'apps/api/src/apbra_api/foundry_report_runtime.py', 'apps/api/src/apbra_api/main.py', 'apps/api/src/apbra_api/native_case_files.py', 'apps/api/src/apbra_api/native_goal_context.py', 'apps/api/src/apbra_api/native_response_api.py', 'apps/api/src/apbra_api/native_response_probe.py', 'apps/api/src/apbra_api/observability.py', 'apps/api/src/apbra_api/oidc_adapter.py', 'apps/api/src/apbra_api/password_auth.py', 'apps/api/src/apbra_api/persistence.py', 'apps/api/src/apbra_api/request_outputs.py', 'apps/api/src/apbra_api/tenant_date_display.py', 'apps/api/tests/conftest.py', 'apps/api/tests/test_authentication.py', 'apps/api/tests/test_foundry_admin_reads.py', 'apps/api/tests/test_foundry_agent_details.py', 'apps/api/tests/test_foundry_artifacts.py', 'apps/api/tests/test_foundry_browser_handoff.py', 'apps/api/tests/test_foundry_browser_relay.py', 'apps/api/tests/test_foundry_catalogue_lease.py', 'apps/api/tests/test_foundry_memory_handoff.py', 'apps/api/tests/test_foundry_private_preparation.py', 'apps/api/tests/test_foundry_report_runtime.py', 'apps/api/tests/test_migrations.py', 'apps/api/tests/test_native_case_files.py', 'apps/api/tests/test_native_contracts.py', 'apps/api/tests/test_native_goal_context.py', 'apps/api/tests/test_native_response_integration.py', 'apps/api/tests/test_observability.py', 'apps/api/tests/test_password_auth.py', 'apps/api/tests/test_report_authorization_clock.py', 'apps/api/tests/test_request_outputs.py', 'apps/api/tests/test_tenant_date_display.py', 'apps/api/uv.lock', 'apps/web/e2e/tenant-settings.spec.ts', 'apps/web/src/AdminUI.test.tsx', 'apps/web/src/AdminUI.tsx', 'apps/web/src/BusinessReportJourney.test.tsx', 'apps/web/src/BusinessReportJourney.tsx', 'apps/web/src/EnterpriseApp.tsx', 'apps/web/src/PasswordAccount.test.tsx', 'apps/web/src/PasswordAccount.tsx', 'apps/web/src/RequestOutputs.test.tsx', 'apps/web/src/RequestOutputs.tsx', 'apps/web/src/SavedAzureAnswer.test.tsx', 'apps/web/src/SavedAzureAnswer.tsx', 'apps/web/src/TenantDateTime.test.tsx', 'apps/web/src/TenantDateTime.tsx', 'apps/web/src/TenantObservability.test.tsx', 'apps/web/src/TenantObservability.tsx', 'apps/web/src/api.test.ts', 'apps/web/src/api.ts', 'apps/web/src/businessAgent.test.ts', 'apps/web/src/businessAgent.ts', 'apps/web/src/durableConversation.tsx', 'apps/web/src/durableGeneration.test.tsx', 'apps/web/src/durableGeneration.tsx', 'apps/web/src/privateCases.test.tsx', 'apps/web/src/privateCases.tsx', 'apps/web/src/style.css'}
N = {'apps/api/src/apbra_api/api.py', 'apps/api/src/apbra_api/password_auth.py', 'apps/api/alembic/versions/20261108_18_native_organisation.py', 'apps/api/src/apbra_api/domain.py', 'apps/web/src/api.ts', 'apps/api/tests/test_request_outputs.py', 'apps/web/src/privateCases.test.tsx', 'apps/web/src/privateCases.tsx', 'apps/api/tests/test_password_auth.py', 'apps/web/src/style.css', 'apps/api/src/apbra_api/persistence.py', 'apps/api/tests/test_migrations.py', 'apps/api/tests/test_native_organisation.py', 'apps/api/src/apbra_api/native_organisation.py', 'apps/api/src/apbra_api/application.py', 'apps/web/src/PasswordAccount.tsx', 'apps/web/src/PasswordAccount.test.tsx'}
R = 'agent/APBRA-DEVOPS/APBRA-183-public-governance'
QB = 'agent/APBRA-DEVOPS/APBRA-160-recovered-account-public-v2'
NB = 'agent/APBRA-DEVOPS/APBRA-183-native-organisation-public-v2'
RT = 'tasks/APBRA-183-recovered-native-registration-public-v2.json'
QT = 'tasks/APBRA-160-recovered-account-public-v2.json'
NT = 'tasks/APBRA-183-native-organisation-public-v2.json'
RT_SHA = '55f825a6d98eb7c6027bc060d9fefe75a7b3cb0f8b72bd9bcf63422400df494f'
QT_SHA = 'ad826b7b4c7c87a47538955d55a557c4b434de6de788a04a597617fb84751b90'
NT_SHA = '70ae82cf6d86de62c0f89806775aa2c40d6d8d6a64cf341124d92113d7bf877c'
SOURCE_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
MANIFEST = 'docs/engineering/recovered-native-frozen-manifests.json'
MANIFEST_SHA = '78fbc2dc6597d885344321cf668f8df28ffaa76ab5d27bc78a6746ed1e1d6433'
BASE = '444f4828c87a3a158fc102efae37196540cbbafa'
BOOT_EDITS = [("    'apps/web/e2e/tenant-settings.spec.ts',\n", "'apps/web/e2e/tenant-settings.spec.ts',\n"), ("    'tasks/APBRA-160-demo-ux.json',\n", "'tasks/APBRA-160-demo-ux.json',\n"), ("    'tests/bootstrap/test_demo_ux_scope.py',\n", "'tests/bootstrap/test_demo_ux_scope.py',\n"), ("    ('apbra-160-historical-business-shell','8388610',2,'b44375446b2ce03e03c22136aa0cd74938253a88ab0c27cb7bbac89fc6ea4304'),\n", "('apbra-160-historical-business-shell','8388610',2,'b44375446b2ce03e03c22136aa0cd74938253a88ab0c27cb7bbac89fc6ea4304'),\n"), ("    ('apbra-160-conversational-ux-history','3932422',8,'c3eaabbceee9fa5f3f1f4cd18bfb4fe0f6a63a6b447731d920cac35bcbc6174a'),\n", "('apbra-160-conversational-ux-history','3932422',8,'c3eaabbceee9fa5f3f1f4cd18bfb4fe0f6a63a6b447731d920cac35bcbc6174a'),\n"), ("    ('apbra-160-future-native-platform','7864321',2,'10502b3d6cf59134982ec231ed0081aaac7a6c8a1cd070bdd3f969d366494444'),\n", "('apbra-160-future-native-platform','7864321',2,'10502b3d6cf59134982ec231ed0081aaac7a6c8a1cd070bdd3f969d366494444'),\n"), ("    ('apbra-160-use-cases-acceptance','3932402',5,'3faf1efa272470e3771f72f65d7a47e9d5026e12d31a689c19378f3ac9e644d5'),\n", "('apbra-160-use-cases-acceptance','3932402',5,'3faf1efa272470e3771f72f65d7a47e9d5026e12d31a689c19378f3ac9e644d5'),\n"), ("    'apps/web/.env.example','apps/web/README.md',\n", "'apps/web/.env.example','apps/web/README.md',\n"), ("    'apps/web/knowledge/accessibility-standards.md',\n", "'apps/web/knowledge/accessibility-standards.md',\n"), ("    'apps/web/knowledge/corporate-branding.md',\n", "'apps/web/knowledge/corporate-branding.md',\n"), ("    'apps/web/knowledge/deployment-standards.md',\n", "'apps/web/knowledge/deployment-standards.md',\n"), ("    'apps/web/knowledge/powerbi-modelling-standards.md',\n", "'apps/web/knowledge/powerbi-modelling-standards.md',\n"), ("    'apps/web/knowledge/report-design-standards.md',\n", "'apps/web/knowledge/report-design-standards.md',\n"), ("    'apps/web/package-lock.json','apps/web/package.json',\n", "'apps/web/package-lock.json','apps/web/package.json',\n"), ("    'apps/web/scripts/foundry-smoke.mjs','apps/web/src/App.test.tsx',\n", "'apps/web/scripts/foundry-smoke.mjs','apps/web/src/App.test.tsx',\n"), ("    'apps/web/src/App.tsx','apps/web/src/EnterpriseApp.tsx',\n", "'apps/web/src/App.tsx','apps/web/src/EnterpriseApp.tsx',\n"), ("    'apps/web/src/archive.ts','apps/web/src/foundry.test.ts',\n", "'apps/web/src/archive.ts','apps/web/src/foundry.test.ts',\n"), ("    'apps/web/src/foundry.ts','apps/web/src/genericFoundry.integration.test.ts',\n", "'apps/web/src/foundry.ts','apps/web/src/genericFoundry.integration.test.ts',\n"), ("    'apps/web/src/genericPowerBI.test.ts','apps/web/src/genericPowerBI.ts',\n", "'apps/web/src/genericPowerBI.test.ts','apps/web/src/genericPowerBI.ts',\n"), ("    'apps/web/src/guardrail.test.ts','apps/web/src/guardrail.ts',\n", "'apps/web/src/guardrail.test.ts','apps/web/src/guardrail.ts',\n"), ("    'apps/web/src/guardrailPolicy.json','apps/web/src/main.tsx',\n", "'apps/web/src/guardrailPolicy.json','apps/web/src/main.tsx',\n"), ("    'apps/web/src/powerbi.test.ts','apps/web/src/powerbi.ts',\n", "'apps/web/src/powerbi.test.ts','apps/web/src/powerbi.ts',\n"), ("    'apps/web/src/rag.test.ts','apps/web/src/rag.ts','apps/web/src/raw.d.ts',\n", "'apps/web/src/rag.test.ts','apps/web/src/rag.ts','apps/web/src/raw.d.ts',\n"), ("    'apps/web/src/requirements.test.ts','apps/web/src/requirements.ts',\n", "'apps/web/src/requirements.test.ts','apps/web/src/requirements.ts',\n"), ("    'apps/web/src/schemaIngestion.test.ts','apps/web/src/schemaIngestion.ts',\n", "'apps/web/src/schemaIngestion.test.ts','apps/web/src/schemaIngestion.ts',\n"), ("    'apps/web/src/style.css','apps/web/src/tenant.ts',\n", "'apps/web/src/style.css','apps/web/src/tenant.ts',\n"), ("    'apps/web/src/validationProfile.json','apps/web/src/workflow.ts',\n", "'apps/web/src/validationProfile.json','apps/web/src/workflow.ts',\n"), ("    'README.md','AGENTS.md','ARCHITECTURE.md','REQUIREMENTS.md',\n", "'README.md','AGENTS.md','ARCHITECTURE.md','REQUIREMENTS.md',\n"), ("    'DATA-MODEL.md','AI-RAG-SPEC.md','POWERBI-GENERATION-SPEC.md',\n", "'DATA-MODEL.md','AI-RAG-SPEC.md','POWERBI-GENERATION-SPEC.md',\n"), ("    'MVP-ACCEPTANCE-CRITERIA.md','docs/source-register.json',\n", "'MVP-ACCEPTANCE-CRITERIA.md','docs/source-register.json',\n"), ("    'agents/catalog.json','tasks/APBRA-85-bootstrap.json',\n", "'agents/catalog.json','tasks/APBRA-85-bootstrap.json',\n"), ("    'contracts/engineering/task-contract.schema.json',\n", "'contracts/engineering/task-contract.schema.json',\n"), ("    'contracts/engineering/agent-catalog.schema.json',\n", "'contracts/engineering/agent-catalog.schema.json',\n"), ("    '.github/CODEOWNERS','.github/pull_request_template.md',\n", "'.github/CODEOWNERS','.github/pull_request_template.md',\n"), ("    '.github/workflows/bootstrap.yml','requirements-bootstrap.txt',\n", "'.github/workflows/bootstrap.yml','requirements-bootstrap.txt',\n"), ("    'docs/engineering/repository-controls.md','docs/engineering/codex-handoff.md',\n", "'docs/engineering/repository-controls.md','docs/engineering/codex-handoff.md',\n"), ("    'docs/decisions/implementation-baseline.md','tests/bootstrap/test_bootstrap.py',\n", "'docs/decisions/implementation-baseline.md','tests/bootstrap/test_bootstrap.py',\n"), ("    'PLANNER','ARCH','DEV-BE','DEV-FE','AI','RAG','PBI',\n", "'PLANNER','ARCH','DEV-BE','DEV-FE','AI','RAG','PBI',\n"), ("    'QA','SEC','REVIEW','DEVOPS','DOCS')}\n", "'QA','SEC','REVIEW','DEVOPS','DOCS')}\n"), ("        not path.startswith('/')and all(p not in('','.','..')for p in path.split('/'))\n", "not path.startswith('/')and all(p not in('','.','..')for p in path.split('/'))\n"), ("        task.get('task_id') in {'APBRA-163', 'APBRA-164'} and\n", "task.get('task_id') in {'APBRA-163', 'APBRA-164'} and\n"), ("        path == 'tests/bootstrap/test_ci_policy.py' and\n", "path == 'tests/bootstrap/test_ci_policy.py' and\n"), ("        path in task['allowed_paths']\n", "path in task['allowed_paths']\n"), ("        any(matches(path, p) for p in task['allowed_paths']) and\n", "any(matches(path, p) for p in task['allowed_paths']) and\n"), ("        any(matches(path, p) for p in card['allowed_paths'])\n", "any(matches(path, p) for p in card['allowed_paths'])\n"), ("    registered['branch'],registered['base_commit'])!=('APBRA-160','APBRA-DEVOPS','0.1',branch,base):\n", "registered['branch'],registered['base_commit'])!=('APBRA-160','APBRA-DEVOPS','0.1',branch,base):\n"), ("     rows[0].get('status'))!=(content_id,version,'ACCEPTED')or digest(rows[0])!=expected):\n", "rows[0].get('status'))!=(content_id,version,'ACCEPTED')or digest(rows[0])!=expected):\n"), ("                [row.get('id') for row in appended_rows] !=\n", "[row.get('id') for row in appended_rows] !=\n"), ("            active_branch == 'agent/APBRA-DEVOPS/APBRA-163-durable-conversation-evidence-acceptance' and\n", "active_branch == 'agent/APBRA-DEVOPS/APBRA-163-durable-conversation-evidence-acceptance' and\n"), ("                        'mvp1-invited-private-case-foundation',\n", "'mvp1-invited-private-case-foundation',\n"), ("                        'mvp1-invited-private-case-foundation-scope-amendment']:\n", "'mvp1-invited-private-case-foundation-scope-amendment']:\n"), ("                        'mvp1-durable-conversation-evidence-acceptance',\n", "'mvp1-durable-conversation-evidence-acceptance',\n"), ("                        'mvp1-durable-conversation-evidence-acceptance-ci-amendment',\n", "'mvp1-durable-conversation-evidence-acceptance-ci-amendment',\n"), ("                        'mvp1-durable-conversation-evidence-acceptance-historical-capacity-fixture']:\n", "'mvp1-durable-conversation-evidence-acceptance-historical-capacity-fixture']:\n"), ("                        model_led_flexible_delivery_task['agent_card_version']) != ('APBRA-174', 'APBRA-DEVOPS', '0.1'):\n", "model_led_flexible_delivery_task['agent_card_version']) != ('APBRA-174', 'APBRA-DEVOPS', '0.1'):\n"), ("                        model_led_flexible_delivery_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):\n", "model_led_flexible_delivery_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):\n"), ("                                       if source['id'] == MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_ID), None)\n", "if source['id'] == MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_ID), None)\n"), ("                                         if source['id'] == MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_SOURCE_ID), None)\n", "if source['id'] == MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_SOURCE_ID), None)\n"), ("                                        if source['id'] == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_SOURCE_ID), None)\n", "if source['id'] == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_SOURCE_ID), None)\n"), ("                        deployment_portability_entitlement_docs_task['agent_card_version']) != ('APBRA-175', 'APBRA-DEVOPS', '0.1'):\n", "deployment_portability_entitlement_docs_task['agent_card_version']) != ('APBRA-175', 'APBRA-DEVOPS', '0.1'):\n"), ("                        deployment_portability_entitlement_docs_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):\n", "deployment_portability_entitlement_docs_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):\n"), ("                    (DEPLOYMENT_PORTABILITY_SOURCE_ID, '9568258', DEPLOYMENT_PORTABILITY_SOURCE_SHA256),\n", "(DEPLOYMENT_PORTABILITY_SOURCE_ID, '9568258', DEPLOYMENT_PORTABILITY_SOURCE_SHA256),\n"), ("                    (ENTITLEMENT_ARCHITECTURE_SOURCE_ID, '9535525', ENTITLEMENT_ARCHITECTURE_SOURCE_SHA256),\n", "(ENTITLEMENT_ARCHITECTURE_SOURCE_ID, '9535525', ENTITLEMENT_ARCHITECTURE_SOURCE_SHA256),\n"), ("                                package_source.get('version') != 1 or package_source.get('status') != 'ACCEPTED'):\n", "package_source.get('version') != 1 or package_source.get('status') != 'ACCEPTED'):\n"), ("                        owner_onboarding_identity_docs_task['agent_card_version']) != ('APBRA-176', 'APBRA-DOCS', '0.1'):\n", "owner_onboarding_identity_docs_task['agent_card_version']) != ('APBRA-176', 'APBRA-DOCS', '0.1'):\n"), ("                        owner_onboarding_identity_docs_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):\n", "owner_onboarding_identity_docs_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):\n"), ("                    (OWNER_ONBOARDING_IDENTITY_SOURCE_ID, '4030847', 4, OWNER_ONBOARDING_IDENTITY_SOURCE_SHA256),\n", "(OWNER_ONBOARDING_IDENTITY_SOURCE_ID, '4030847', 4, OWNER_ONBOARDING_IDENTITY_SOURCE_SHA256),\n"), ("                    (OWNER_ONBOARDING_REQUIREMENTS_SOURCE_ID, '3932362', 7, OWNER_ONBOARDING_REQUIREMENTS_SOURCE_SHA256),\n", "(OWNER_ONBOARDING_REQUIREMENTS_SOURCE_ID, '3932362', 7, OWNER_ONBOARDING_REQUIREMENTS_SOURCE_SHA256),\n"), ("                        candidate_source_safety_task['agent_card_version']) != ('APBRA-108', 'APBRA-DEVOPS', '0.1'):\n", "candidate_source_safety_task['agent_card_version']) != ('APBRA-108', 'APBRA-DEVOPS', '0.1'):\n"), ("                        len(candidate_source_safety_task['allowed_paths']) != len(CANDIDATE_SOURCE_SAFETY_PATHS)):\n", "len(candidate_source_safety_task['allowed_paths']) != len(CANDIDATE_SOURCE_SAFETY_PATHS)):\n"), ("                        candidate_source_safety_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):\n", "candidate_source_safety_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):\n"), ("            root, catalog, sources, filename='APBRA-160-provider-retrieval.json', label='provider retrieval',\n", "root, catalog, sources, filename='APBRA-160-provider-retrieval.json', label='provider retrieval',\n"), ("            branch=PROVIDER_RETRIEVAL_BRANCH, base='e3f782535e41bef1034222227ef706e1cf0bfac1', paths=PROVIDER_RETRIEVAL_PATHS,\n", "branch=PROVIDER_RETRIEVAL_BRANCH, base='e3f782535e41bef1034222227ef706e1cf0bfac1', paths=PROVIDER_RETRIEVAL_PATHS,\n"), ("            count_label='29')\n", "count_label='29')\n"), ("            root, catalog, sources, filename='APBRA-160-foundry-host.json', label='Foundry host',\n", "root, catalog, sources, filename='APBRA-160-foundry-host.json', label='Foundry host',\n"), ("            branch=FOUNDRY_HOST_BRANCH, base='78346bb7d253e7f649858f4a251a04d8663670b7', paths=FOUNDRY_HOST_PATHS,\n", "branch=FOUNDRY_HOST_BRANCH, base='78346bb7d253e7f649858f4a251a04d8663670b7', paths=FOUNDRY_HOST_PATHS,\n"), ("            count_label='six')\n", "count_label='six')\n"), ("            root, catalog, sources, filename='APBRA-160-foundry-qualification.json', label='Foundry qualification',\n", "root, catalog, sources, filename='APBRA-160-foundry-qualification.json', label='Foundry qualification',\n"), ("            branch=FOUNDRY_QUALIFICATION_BRANCH, base='3f27674158d0924545ccf9f9f70e549c0292377b', paths=FOUNDRY_QUALIFICATION_PATHS,\n", "branch=FOUNDRY_QUALIFICATION_BRANCH, base='3f27674158d0924545ccf9f9f70e549c0292377b', paths=FOUNDRY_QUALIFICATION_PATHS,\n"), ("            count_label='three')\n", "count_label='three')\n"), ("                    foundry_schema_task, sort_keys=True, separators=(',', ':'),\n", "foundry_schema_task, sort_keys=True, separators=(',', ':'),\n"), ("                    foundry_schema_task['task_id'],\n", "foundry_schema_task['task_id'],\n"), ("                    foundry_schema_task['assigned_agent'],\n", "foundry_schema_task['assigned_agent'],\n"), ("                    foundry_schema_task['agent_card_version'],\n", "foundry_schema_task['agent_card_version'],\n"), ("                ) != ('APBRA-160', 'APBRA-DEVOPS', '0.1'):\n", ") != ('APBRA-160', 'APBRA-DEVOPS', '0.1'):\n"), ("                    set(foundry_schema_task['allowed_paths']) != FOUNDRY_SCHEMA_PATHS\n", "set(foundry_schema_task['allowed_paths']) != FOUNDRY_SCHEMA_PATHS\n"), ("                    or len(foundry_schema_task['allowed_paths']) != len(FOUNDRY_SCHEMA_PATHS)\n", "or len(foundry_schema_task['allowed_paths']) != len(FOUNDRY_SCHEMA_PATHS)\n"), ("                    foundry_schema_task['task_mode'],\n", "foundry_schema_task['task_mode'],\n"), ("                    foundry_schema_task['readiness'],\n", "foundry_schema_task['readiness'],\n"), ("                    foundry_schema_task['owner_acceptance'],\n", "foundry_schema_task['owner_acceptance'],\n"), ("                        foundry_schema_task[section], sort_keys=True, separators=(',', ':'),\n", "foundry_schema_task[section], sort_keys=True, separators=(',', ':'),\n"), ("                    demo_ux_task, sort_keys=True, separators=(',', ':'),\n", "demo_ux_task, sort_keys=True, separators=(',', ':'),\n"), ("                    demo_ux_task['task_id'], demo_ux_task['assigned_agent'],\n", "demo_ux_task['task_id'], demo_ux_task['assigned_agent'],\n"), ("                    demo_ux_task['agent_card_version'], demo_ux_task['branch'],\n", "demo_ux_task['agent_card_version'], demo_ux_task['branch'],\n"), ("                    demo_ux_task['base_commit'],\n", "demo_ux_task['base_commit'],\n"), ("                    'APBRA-160', 'APBRA-DEVOPS', '0.1', DEMO_UX_BRANCH,\n", "'APBRA-160', 'APBRA-DEVOPS', '0.1', DEMO_UX_BRANCH,\n"), ("                    '6ad7ee7e2d6a16fb71cc8f05ebf35f3affaf49a7',\n", "'6ad7ee7e2d6a16fb71cc8f05ebf35f3affaf49a7',\n"), ("                    set(demo_ux_task['allowed_paths']) != DEMO_UX_PATHS\n", "set(demo_ux_task['allowed_paths']) != DEMO_UX_PATHS\n"), ("                    or len(demo_ux_task['allowed_paths']) != len(DEMO_UX_PATHS)\n", "or len(demo_ux_task['allowed_paths']) != len(DEMO_UX_PATHS)\n"), ("                    or any('*' in path for path in demo_ux_task['allowed_paths'])\n", "or any('*' in path for path in demo_ux_task['allowed_paths'])\n"), ("                    demo_ux_task['task_mode'], demo_ux_task['readiness'],\n", "demo_ux_task['task_mode'], demo_ux_task['readiness'],\n"), ("                    demo_ux_task['owner_acceptance'],\n", "demo_ux_task['owner_acceptance'],\n"), ("                        demo_ux_task[section], sort_keys=True, separators=(',', ':'),\n", "demo_ux_task[section], sort_keys=True, separators=(',', ':'),\n"), ("                            row.get('content_id'), row.get('version'), row.get('status')\n", "row.get('content_id'), row.get('version'), row.get('status')\n"), ("                    private_content_storage_task, sort_keys=True, separators=(',', ':')\n", "private_content_storage_task, sort_keys=True, separators=(',', ':')\n"), ("                    private_content_storage_task['task_id'],\n", "private_content_storage_task['task_id'],\n"), ("                    private_content_storage_task['assigned_agent'],\n", "private_content_storage_task['assigned_agent'],\n"), ("                    private_content_storage_task['agent_card_version'],\n", "private_content_storage_task['agent_card_version'],\n"), ("                    set(private_content_storage_task['allowed_paths']) != PRIVATE_CONTENT_STORAGE_PATHS\n", "set(private_content_storage_task['allowed_paths']) != PRIVATE_CONTENT_STORAGE_PATHS\n"), ("nv=runpy.run_path(Path(__file__).parent/'check_nv.py')\n", "nv=runpy.run_path(Path(__file__).parent/'check_nv.py')\npn=runpy.run_path(Path(__file__).parent/'check_recovered_native_registration.py') if (Path(__file__).parent/'check_recovered_native_registration.py').is_file() else None\n"), ("        nvt,ne=nv['bind'](root,catalog,sources,bound_provider_registration);errors+=ne\n", "        nvt,ne=nv['bind'](root,catalog,sources,bound_provider_registration);errors+=ne\n        pa,na,pg,pe=pn['bind'](root,catalog,sources,schema_errors,task_errors) if pn else (None,None,None,[]);errors+=pe\n"), ("        registered_tasks = {registered['task_id']: registered for registered, _ in\n", "        if pn:bound_authorities+=((pa,pn['scope'](root,'Q')),(na,pn['scope'](root,'N')),(pg,pn['scope'](root,'G')))\n        registered_tasks = {registered['task_id']: registered for registered, _ in\n"), ('        if changed_paths is not None and changed_paths:\n', "        if pn and active_task_id=='APBRA-183':registered_tasks['APBRA-183']=pg if active_branch==pn['R'] else na if active_branch==pn['branch'](root,'N') else None\n        if pn and active_task_id=='APBRA-160' and active_branch==pn['branch'](root,'Q'):registered_tasks['APBRA-160']=pa\n        if changed_paths is not None and changed_paths:\n"), ("            errors+=nv['errors'](nvt,active_branch,changed_paths)\n", "            errors+=nv['errors'](nvt,active_branch,changed_paths)\n            if pn:errors+=pn['errors'](root,pa,na,pg,active_branch,changed_paths)\n"), ('        errors += workflow_errors(workflow_text)\n', "        errors += workflow_errors(pn['workflow_projection'](root,workflow_text) if pn else workflow_text)\n")]
NV_EDITS = [('def strip_hooks(source):\n', 'def strip_hooks(source):\n    source=strip_public_bootstrap(source)\n'), ("        identity,branch,paths=c['delivery_context'](root)\n", "        identity,branch,paths=c['delivery_context'](root)\n        public=Path(__file__).with_name('check_recovered_native_registration.py')\n        if public.is_file():\n            qualified=runpy.run_path(public)['qualified_paths'](root,c,identity,branch,paths,OVERLAP,CANDIDATE)\n            if qualified:return qualified\n"), ('def strip_dispatch_test_changes(source):return inverse(source,DISPATCH_TEST_EDITS)\n', 'def strip_dispatch_test_changes(source):return inverse(strip_public_dispatch_test(source),DISPATCH_TEST_EDITS)\n'), ('', '\n# Exact additive public-v2 inverse; historical fixtures need no future helper.\nPUBLIC_BOOT_EDITS = [("    \'apps/web/e2e/tenant-settings.spec.ts\',\\n", "\'apps/web/e2e/tenant-settings.spec.ts\',\\n"), ("    \'tasks/APBRA-160-demo-ux.json\',\\n", "\'tasks/APBRA-160-demo-ux.json\',\\n"), ("    \'tests/bootstrap/test_demo_ux_scope.py\',\\n", "\'tests/bootstrap/test_demo_ux_scope.py\',\\n"), ("    (\'apbra-160-historical-business-shell\',\'8388610\',2,\'b44375446b2ce03e03c22136aa0cd74938253a88ab0c27cb7bbac89fc6ea4304\'),\\n", "(\'apbra-160-historical-business-shell\',\'8388610\',2,\'b44375446b2ce03e03c22136aa0cd74938253a88ab0c27cb7bbac89fc6ea4304\'),\\n"), ("    (\'apbra-160-conversational-ux-history\',\'3932422\',8,\'c3eaabbceee9fa5f3f1f4cd18bfb4fe0f6a63a6b447731d920cac35bcbc6174a\'),\\n", "(\'apbra-160-conversational-ux-history\',\'3932422\',8,\'c3eaabbceee9fa5f3f1f4cd18bfb4fe0f6a63a6b447731d920cac35bcbc6174a\'),\\n"), ("    (\'apbra-160-future-native-platform\',\'7864321\',2,\'10502b3d6cf59134982ec231ed0081aaac7a6c8a1cd070bdd3f969d366494444\'),\\n", "(\'apbra-160-future-native-platform\',\'7864321\',2,\'10502b3d6cf59134982ec231ed0081aaac7a6c8a1cd070bdd3f969d366494444\'),\\n"), ("    (\'apbra-160-use-cases-acceptance\',\'3932402\',5,\'3faf1efa272470e3771f72f65d7a47e9d5026e12d31a689c19378f3ac9e644d5\'),\\n", "(\'apbra-160-use-cases-acceptance\',\'3932402\',5,\'3faf1efa272470e3771f72f65d7a47e9d5026e12d31a689c19378f3ac9e644d5\'),\\n"), ("    \'apps/web/.env.example\',\'apps/web/README.md\',\\n", "\'apps/web/.env.example\',\'apps/web/README.md\',\\n"), ("    \'apps/web/knowledge/accessibility-standards.md\',\\n", "\'apps/web/knowledge/accessibility-standards.md\',\\n"), ("    \'apps/web/knowledge/corporate-branding.md\',\\n", "\'apps/web/knowledge/corporate-branding.md\',\\n"), ("    \'apps/web/knowledge/deployment-standards.md\',\\n", "\'apps/web/knowledge/deployment-standards.md\',\\n"), ("    \'apps/web/knowledge/powerbi-modelling-standards.md\',\\n", "\'apps/web/knowledge/powerbi-modelling-standards.md\',\\n"), ("    \'apps/web/knowledge/report-design-standards.md\',\\n", "\'apps/web/knowledge/report-design-standards.md\',\\n"), ("    \'apps/web/package-lock.json\',\'apps/web/package.json\',\\n", "\'apps/web/package-lock.json\',\'apps/web/package.json\',\\n"), ("    \'apps/web/scripts/foundry-smoke.mjs\',\'apps/web/src/App.test.tsx\',\\n", "\'apps/web/scripts/foundry-smoke.mjs\',\'apps/web/src/App.test.tsx\',\\n"), ("    \'apps/web/src/App.tsx\',\'apps/web/src/EnterpriseApp.tsx\',\\n", "\'apps/web/src/App.tsx\',\'apps/web/src/EnterpriseApp.tsx\',\\n"), ("    \'apps/web/src/archive.ts\',\'apps/web/src/foundry.test.ts\',\\n", "\'apps/web/src/archive.ts\',\'apps/web/src/foundry.test.ts\',\\n"), ("    \'apps/web/src/foundry.ts\',\'apps/web/src/genericFoundry.integration.test.ts\',\\n", "\'apps/web/src/foundry.ts\',\'apps/web/src/genericFoundry.integration.test.ts\',\\n"), ("    \'apps/web/src/genericPowerBI.test.ts\',\'apps/web/src/genericPowerBI.ts\',\\n", "\'apps/web/src/genericPowerBI.test.ts\',\'apps/web/src/genericPowerBI.ts\',\\n"), ("    \'apps/web/src/guardrail.test.ts\',\'apps/web/src/guardrail.ts\',\\n", "\'apps/web/src/guardrail.test.ts\',\'apps/web/src/guardrail.ts\',\\n"), ("    \'apps/web/src/guardrailPolicy.json\',\'apps/web/src/main.tsx\',\\n", "\'apps/web/src/guardrailPolicy.json\',\'apps/web/src/main.tsx\',\\n"), ("    \'apps/web/src/powerbi.test.ts\',\'apps/web/src/powerbi.ts\',\\n", "\'apps/web/src/powerbi.test.ts\',\'apps/web/src/powerbi.ts\',\\n"), ("    \'apps/web/src/rag.test.ts\',\'apps/web/src/rag.ts\',\'apps/web/src/raw.d.ts\',\\n", "\'apps/web/src/rag.test.ts\',\'apps/web/src/rag.ts\',\'apps/web/src/raw.d.ts\',\\n"), ("    \'apps/web/src/requirements.test.ts\',\'apps/web/src/requirements.ts\',\\n", "\'apps/web/src/requirements.test.ts\',\'apps/web/src/requirements.ts\',\\n"), ("    \'apps/web/src/schemaIngestion.test.ts\',\'apps/web/src/schemaIngestion.ts\',\\n", "\'apps/web/src/schemaIngestion.test.ts\',\'apps/web/src/schemaIngestion.ts\',\\n"), ("    \'apps/web/src/style.css\',\'apps/web/src/tenant.ts\',\\n", "\'apps/web/src/style.css\',\'apps/web/src/tenant.ts\',\\n"), ("    \'apps/web/src/validationProfile.json\',\'apps/web/src/workflow.ts\',\\n", "\'apps/web/src/validationProfile.json\',\'apps/web/src/workflow.ts\',\\n"), ("    \'README.md\',\'AGENTS.md\',\'ARCHITECTURE.md\',\'REQUIREMENTS.md\',\\n", "\'README.md\',\'AGENTS.md\',\'ARCHITECTURE.md\',\'REQUIREMENTS.md\',\\n"), ("    \'DATA-MODEL.md\',\'AI-RAG-SPEC.md\',\'POWERBI-GENERATION-SPEC.md\',\\n", "\'DATA-MODEL.md\',\'AI-RAG-SPEC.md\',\'POWERBI-GENERATION-SPEC.md\',\\n"), ("    \'MVP-ACCEPTANCE-CRITERIA.md\',\'docs/source-register.json\',\\n", "\'MVP-ACCEPTANCE-CRITERIA.md\',\'docs/source-register.json\',\\n"), ("    \'agents/catalog.json\',\'tasks/APBRA-85-bootstrap.json\',\\n", "\'agents/catalog.json\',\'tasks/APBRA-85-bootstrap.json\',\\n"), ("    \'contracts/engineering/task-contract.schema.json\',\\n", "\'contracts/engineering/task-contract.schema.json\',\\n"), ("    \'contracts/engineering/agent-catalog.schema.json\',\\n", "\'contracts/engineering/agent-catalog.schema.json\',\\n"), ("    \'.github/CODEOWNERS\',\'.github/pull_request_template.md\',\\n", "\'.github/CODEOWNERS\',\'.github/pull_request_template.md\',\\n"), ("    \'.github/workflows/bootstrap.yml\',\'requirements-bootstrap.txt\',\\n", "\'.github/workflows/bootstrap.yml\',\'requirements-bootstrap.txt\',\\n"), ("    \'docs/engineering/repository-controls.md\',\'docs/engineering/codex-handoff.md\',\\n", "\'docs/engineering/repository-controls.md\',\'docs/engineering/codex-handoff.md\',\\n"), ("    \'docs/decisions/implementation-baseline.md\',\'tests/bootstrap/test_bootstrap.py\',\\n", "\'docs/decisions/implementation-baseline.md\',\'tests/bootstrap/test_bootstrap.py\',\\n"), ("    \'PLANNER\',\'ARCH\',\'DEV-BE\',\'DEV-FE\',\'AI\',\'RAG\',\'PBI\',\\n", "\'PLANNER\',\'ARCH\',\'DEV-BE\',\'DEV-FE\',\'AI\',\'RAG\',\'PBI\',\\n"), ("    \'QA\',\'SEC\',\'REVIEW\',\'DEVOPS\',\'DOCS\')}\\n", "\'QA\',\'SEC\',\'REVIEW\',\'DEVOPS\',\'DOCS\')}\\n"), ("        not path.startswith(\'/\')and all(p not in(\'\',\'.\',\'..\')for p in path.split(\'/\'))\\n", "not path.startswith(\'/\')and all(p not in(\'\',\'.\',\'..\')for p in path.split(\'/\'))\\n"), ("        task.get(\'task_id\') in {\'APBRA-163\', \'APBRA-164\'} and\\n", "task.get(\'task_id\') in {\'APBRA-163\', \'APBRA-164\'} and\\n"), ("        path == \'tests/bootstrap/test_ci_policy.py\' and\\n", "path == \'tests/bootstrap/test_ci_policy.py\' and\\n"), ("        path in task[\'allowed_paths\']\\n", "path in task[\'allowed_paths\']\\n"), ("        any(matches(path, p) for p in task[\'allowed_paths\']) and\\n", "any(matches(path, p) for p in task[\'allowed_paths\']) and\\n"), ("        any(matches(path, p) for p in card[\'allowed_paths\'])\\n", "any(matches(path, p) for p in card[\'allowed_paths\'])\\n"), ("    registered[\'branch\'],registered[\'base_commit\'])!=(\'APBRA-160\',\'APBRA-DEVOPS\',\'0.1\',branch,base):\\n", "registered[\'branch\'],registered[\'base_commit\'])!=(\'APBRA-160\',\'APBRA-DEVOPS\',\'0.1\',branch,base):\\n"), ("     rows[0].get(\'status\'))!=(content_id,version,\'ACCEPTED\')or digest(rows[0])!=expected):\\n", "rows[0].get(\'status\'))!=(content_id,version,\'ACCEPTED\')or digest(rows[0])!=expected):\\n"), ("                [row.get(\'id\') for row in appended_rows] !=\\n", "[row.get(\'id\') for row in appended_rows] !=\\n"), ("            active_branch == \'agent/APBRA-DEVOPS/APBRA-163-durable-conversation-evidence-acceptance\' and\\n", "active_branch == \'agent/APBRA-DEVOPS/APBRA-163-durable-conversation-evidence-acceptance\' and\\n"), ("                        \'mvp1-invited-private-case-foundation\',\\n", "\'mvp1-invited-private-case-foundation\',\\n"), ("                        \'mvp1-invited-private-case-foundation-scope-amendment\']:\\n", "\'mvp1-invited-private-case-foundation-scope-amendment\']:\\n"), ("                        \'mvp1-durable-conversation-evidence-acceptance\',\\n", "\'mvp1-durable-conversation-evidence-acceptance\',\\n"), ("                        \'mvp1-durable-conversation-evidence-acceptance-ci-amendment\',\\n", "\'mvp1-durable-conversation-evidence-acceptance-ci-amendment\',\\n"), ("                        \'mvp1-durable-conversation-evidence-acceptance-historical-capacity-fixture\']:\\n", "\'mvp1-durable-conversation-evidence-acceptance-historical-capacity-fixture\']:\\n"), ("                        model_led_flexible_delivery_task[\'agent_card_version\']) != (\'APBRA-174\', \'APBRA-DEVOPS\', \'0.1\'):\\n", "model_led_flexible_delivery_task[\'agent_card_version\']) != (\'APBRA-174\', \'APBRA-DEVOPS\', \'0.1\'):\\n"), ("                        model_led_flexible_delivery_task[\'owner_acceptance\']) != (\'IMPLEMENTATION\', \'READY_FOR_IMPLEMENTATION\', \'RECORDED\'):\\n", "model_led_flexible_delivery_task[\'owner_acceptance\']) != (\'IMPLEMENTATION\', \'READY_FOR_IMPLEMENTATION\', \'RECORDED\'):\\n"), ("                                       if source[\'id\'] == MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_ID), None)\\n", "if source[\'id\'] == MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_ID), None)\\n"), ("                                         if source[\'id\'] == MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_SOURCE_ID), None)\\n", "if source[\'id\'] == MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_SOURCE_ID), None)\\n"), ("                                        if source[\'id\'] == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_SOURCE_ID), None)\\n", "if source[\'id\'] == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_SOURCE_ID), None)\\n"), ("                        deployment_portability_entitlement_docs_task[\'agent_card_version\']) != (\'APBRA-175\', \'APBRA-DEVOPS\', \'0.1\'):\\n", "deployment_portability_entitlement_docs_task[\'agent_card_version\']) != (\'APBRA-175\', \'APBRA-DEVOPS\', \'0.1\'):\\n"), ("                        deployment_portability_entitlement_docs_task[\'owner_acceptance\']) != (\'IMPLEMENTATION\', \'READY_FOR_IMPLEMENTATION\', \'RECORDED\'):\\n", "deployment_portability_entitlement_docs_task[\'owner_acceptance\']) != (\'IMPLEMENTATION\', \'READY_FOR_IMPLEMENTATION\', \'RECORDED\'):\\n"), ("                    (DEPLOYMENT_PORTABILITY_SOURCE_ID, \'9568258\', DEPLOYMENT_PORTABILITY_SOURCE_SHA256),\\n", "(DEPLOYMENT_PORTABILITY_SOURCE_ID, \'9568258\', DEPLOYMENT_PORTABILITY_SOURCE_SHA256),\\n"), ("                    (ENTITLEMENT_ARCHITECTURE_SOURCE_ID, \'9535525\', ENTITLEMENT_ARCHITECTURE_SOURCE_SHA256),\\n", "(ENTITLEMENT_ARCHITECTURE_SOURCE_ID, \'9535525\', ENTITLEMENT_ARCHITECTURE_SOURCE_SHA256),\\n"), ("                                package_source.get(\'version\') != 1 or package_source.get(\'status\') != \'ACCEPTED\'):\\n", "package_source.get(\'version\') != 1 or package_source.get(\'status\') != \'ACCEPTED\'):\\n"), ("                        owner_onboarding_identity_docs_task[\'agent_card_version\']) != (\'APBRA-176\', \'APBRA-DOCS\', \'0.1\'):\\n", "owner_onboarding_identity_docs_task[\'agent_card_version\']) != (\'APBRA-176\', \'APBRA-DOCS\', \'0.1\'):\\n"), ("                        owner_onboarding_identity_docs_task[\'owner_acceptance\']) != (\'IMPLEMENTATION\', \'READY_FOR_IMPLEMENTATION\', \'RECORDED\'):\\n", "owner_onboarding_identity_docs_task[\'owner_acceptance\']) != (\'IMPLEMENTATION\', \'READY_FOR_IMPLEMENTATION\', \'RECORDED\'):\\n"), ("                    (OWNER_ONBOARDING_IDENTITY_SOURCE_ID, \'4030847\', 4, OWNER_ONBOARDING_IDENTITY_SOURCE_SHA256),\\n", "(OWNER_ONBOARDING_IDENTITY_SOURCE_ID, \'4030847\', 4, OWNER_ONBOARDING_IDENTITY_SOURCE_SHA256),\\n"), ("                    (OWNER_ONBOARDING_REQUIREMENTS_SOURCE_ID, \'3932362\', 7, OWNER_ONBOARDING_REQUIREMENTS_SOURCE_SHA256),\\n", "(OWNER_ONBOARDING_REQUIREMENTS_SOURCE_ID, \'3932362\', 7, OWNER_ONBOARDING_REQUIREMENTS_SOURCE_SHA256),\\n"), ("                        candidate_source_safety_task[\'agent_card_version\']) != (\'APBRA-108\', \'APBRA-DEVOPS\', \'0.1\'):\\n", "candidate_source_safety_task[\'agent_card_version\']) != (\'APBRA-108\', \'APBRA-DEVOPS\', \'0.1\'):\\n"), ("                        len(candidate_source_safety_task[\'allowed_paths\']) != len(CANDIDATE_SOURCE_SAFETY_PATHS)):\\n", "len(candidate_source_safety_task[\'allowed_paths\']) != len(CANDIDATE_SOURCE_SAFETY_PATHS)):\\n"), ("                        candidate_source_safety_task[\'owner_acceptance\']) != (\'IMPLEMENTATION\', \'READY_FOR_IMPLEMENTATION\', \'RECORDED\'):\\n", "candidate_source_safety_task[\'owner_acceptance\']) != (\'IMPLEMENTATION\', \'READY_FOR_IMPLEMENTATION\', \'RECORDED\'):\\n"), ("            root, catalog, sources, filename=\'APBRA-160-provider-retrieval.json\', label=\'provider retrieval\',\\n", "root, catalog, sources, filename=\'APBRA-160-provider-retrieval.json\', label=\'provider retrieval\',\\n"), ("            branch=PROVIDER_RETRIEVAL_BRANCH, base=\'e3f782535e41bef1034222227ef706e1cf0bfac1\', paths=PROVIDER_RETRIEVAL_PATHS,\\n", "branch=PROVIDER_RETRIEVAL_BRANCH, base=\'e3f782535e41bef1034222227ef706e1cf0bfac1\', paths=PROVIDER_RETRIEVAL_PATHS,\\n"), ("            count_label=\'29\')\\n", "count_label=\'29\')\\n"), ("            root, catalog, sources, filename=\'APBRA-160-foundry-host.json\', label=\'Foundry host\',\\n", "root, catalog, sources, filename=\'APBRA-160-foundry-host.json\', label=\'Foundry host\',\\n"), ("            branch=FOUNDRY_HOST_BRANCH, base=\'78346bb7d253e7f649858f4a251a04d8663670b7\', paths=FOUNDRY_HOST_PATHS,\\n", "branch=FOUNDRY_HOST_BRANCH, base=\'78346bb7d253e7f649858f4a251a04d8663670b7\', paths=FOUNDRY_HOST_PATHS,\\n"), ("            count_label=\'six\')\\n", "count_label=\'six\')\\n"), ("            root, catalog, sources, filename=\'APBRA-160-foundry-qualification.json\', label=\'Foundry qualification\',\\n", "root, catalog, sources, filename=\'APBRA-160-foundry-qualification.json\', label=\'Foundry qualification\',\\n"), ("            branch=FOUNDRY_QUALIFICATION_BRANCH, base=\'3f27674158d0924545ccf9f9f70e549c0292377b\', paths=FOUNDRY_QUALIFICATION_PATHS,\\n", "branch=FOUNDRY_QUALIFICATION_BRANCH, base=\'3f27674158d0924545ccf9f9f70e549c0292377b\', paths=FOUNDRY_QUALIFICATION_PATHS,\\n"), ("            count_label=\'three\')\\n", "count_label=\'three\')\\n"), ("                    foundry_schema_task, sort_keys=True, separators=(\',\', \':\'),\\n", "foundry_schema_task, sort_keys=True, separators=(\',\', \':\'),\\n"), ("                    foundry_schema_task[\'task_id\'],\\n", "foundry_schema_task[\'task_id\'],\\n"), ("                    foundry_schema_task[\'assigned_agent\'],\\n", "foundry_schema_task[\'assigned_agent\'],\\n"), ("                    foundry_schema_task[\'agent_card_version\'],\\n", "foundry_schema_task[\'agent_card_version\'],\\n"), ("                ) != (\'APBRA-160\', \'APBRA-DEVOPS\', \'0.1\'):\\n", ") != (\'APBRA-160\', \'APBRA-DEVOPS\', \'0.1\'):\\n"), ("                    set(foundry_schema_task[\'allowed_paths\']) != FOUNDRY_SCHEMA_PATHS\\n", "set(foundry_schema_task[\'allowed_paths\']) != FOUNDRY_SCHEMA_PATHS\\n"), ("                    or len(foundry_schema_task[\'allowed_paths\']) != len(FOUNDRY_SCHEMA_PATHS)\\n", "or len(foundry_schema_task[\'allowed_paths\']) != len(FOUNDRY_SCHEMA_PATHS)\\n"), ("                    foundry_schema_task[\'task_mode\'],\\n", "foundry_schema_task[\'task_mode\'],\\n"), ("                    foundry_schema_task[\'readiness\'],\\n", "foundry_schema_task[\'readiness\'],\\n"), ("                    foundry_schema_task[\'owner_acceptance\'],\\n", "foundry_schema_task[\'owner_acceptance\'],\\n"), ("                        foundry_schema_task[section], sort_keys=True, separators=(\',\', \':\'),\\n", "foundry_schema_task[section], sort_keys=True, separators=(\',\', \':\'),\\n"), ("                    demo_ux_task, sort_keys=True, separators=(\',\', \':\'),\\n", "demo_ux_task, sort_keys=True, separators=(\',\', \':\'),\\n"), ("                    demo_ux_task[\'task_id\'], demo_ux_task[\'assigned_agent\'],\\n", "demo_ux_task[\'task_id\'], demo_ux_task[\'assigned_agent\'],\\n"), ("                    demo_ux_task[\'agent_card_version\'], demo_ux_task[\'branch\'],\\n", "demo_ux_task[\'agent_card_version\'], demo_ux_task[\'branch\'],\\n"), ("                    demo_ux_task[\'base_commit\'],\\n", "demo_ux_task[\'base_commit\'],\\n"), ("                    \'APBRA-160\', \'APBRA-DEVOPS\', \'0.1\', DEMO_UX_BRANCH,\\n", "\'APBRA-160\', \'APBRA-DEVOPS\', \'0.1\', DEMO_UX_BRANCH,\\n"), ("                    \'6ad7ee7e2d6a16fb71cc8f05ebf35f3affaf49a7\',\\n", "\'6ad7ee7e2d6a16fb71cc8f05ebf35f3affaf49a7\',\\n"), ("                    set(demo_ux_task[\'allowed_paths\']) != DEMO_UX_PATHS\\n", "set(demo_ux_task[\'allowed_paths\']) != DEMO_UX_PATHS\\n"), ("                    or len(demo_ux_task[\'allowed_paths\']) != len(DEMO_UX_PATHS)\\n", "or len(demo_ux_task[\'allowed_paths\']) != len(DEMO_UX_PATHS)\\n"), ("                    or any(\'*\' in path for path in demo_ux_task[\'allowed_paths\'])\\n", "or any(\'*\' in path for path in demo_ux_task[\'allowed_paths\'])\\n"), ("                    demo_ux_task[\'task_mode\'], demo_ux_task[\'readiness\'],\\n", "demo_ux_task[\'task_mode\'], demo_ux_task[\'readiness\'],\\n"), ("                    demo_ux_task[\'owner_acceptance\'],\\n", "demo_ux_task[\'owner_acceptance\'],\\n"), ("                        demo_ux_task[section], sort_keys=True, separators=(\',\', \':\'),\\n", "demo_ux_task[section], sort_keys=True, separators=(\',\', \':\'),\\n"), ("                            row.get(\'content_id\'), row.get(\'version\'), row.get(\'status\')\\n", "row.get(\'content_id\'), row.get(\'version\'), row.get(\'status\')\\n"), ("                    private_content_storage_task, sort_keys=True, separators=(\',\', \':\')\\n", "private_content_storage_task, sort_keys=True, separators=(\',\', \':\')\\n"), ("                    private_content_storage_task[\'task_id\'],\\n", "private_content_storage_task[\'task_id\'],\\n"), ("                    private_content_storage_task[\'assigned_agent\'],\\n", "private_content_storage_task[\'assigned_agent\'],\\n"), ("                    private_content_storage_task[\'agent_card_version\'],\\n", "private_content_storage_task[\'agent_card_version\'],\\n"), ("                    set(private_content_storage_task[\'allowed_paths\']) != PRIVATE_CONTENT_STORAGE_PATHS\\n", "set(private_content_storage_task[\'allowed_paths\']) != PRIVATE_CONTENT_STORAGE_PATHS\\n"), ("nv=runpy.run_path(Path(__file__).parent/\'check_nv.py\')\\n", "nv=runpy.run_path(Path(__file__).parent/\'check_nv.py\')\\npn=runpy.run_path(Path(__file__).parent/\'check_recovered_native_registration.py\') if (Path(__file__).parent/\'check_recovered_native_registration.py\').is_file() else None\\n"), ("        nvt,ne=nv[\'bind\'](root,catalog,sources,bound_provider_registration);errors+=ne\\n", "        nvt,ne=nv[\'bind\'](root,catalog,sources,bound_provider_registration);errors+=ne\\n        pa,na,pg,pe=pn[\'bind\'](root,catalog,sources,schema_errors,task_errors) if pn else (None,None,None,[]);errors+=pe\\n"), ("        registered_tasks = {registered[\'task_id\']: registered for registered, _ in\\n", "        if pn:bound_authorities+=((pa,pn[\'scope\'](root,\'Q\')),(na,pn[\'scope\'](root,\'N\')),(pg,pn[\'scope\'](root,\'G\')))\\n        registered_tasks = {registered[\'task_id\']: registered for registered, _ in\\n"), (\'        if changed_paths is not None and changed_paths:\\n\', "        if pn and active_task_id==\'APBRA-183\':registered_tasks[\'APBRA-183\']=pg if active_branch==pn[\'R\'] else na if active_branch==pn[\'branch\'](root,\'N\') else None\\n        if pn and active_task_id==\'APBRA-160\' and active_branch==pn[\'branch\'](root,\'Q\'):registered_tasks[\'APBRA-160\']=pa\\n        if changed_paths is not None and changed_paths:\\n"), ("            errors+=nv[\'errors\'](nvt,active_branch,changed_paths)\\n", "            errors+=nv[\'errors\'](nvt,active_branch,changed_paths)\\n            if pn:errors+=pn[\'errors\'](root,pa,na,pg,active_branch,changed_paths)\\n"), (\'        errors += workflow_errors(workflow_text)\\n\', "        errors += workflow_errors(pn[\'workflow_projection\'](root,workflow_text) if pn else workflow_text)\\n")]\ndef strip_public_bootstrap(source):\n    if not any(after in source for _,after in PUBLIC_BOOT_EDITS):return source\n    for before,after in reversed(PUBLIC_BOOT_EDITS):\n        if source.count(after)!=1:raise ValueError(\'Public canonical inverse differs\')\n        source=source.replace(after,before,1)\n    return source\n\nPUBLIC_DISPATCH_TEST_EDIT = (\'        current=(ROOT/name).read_text()\\n\', "        current=(ROOT/name).read_text()\\n        native=ROOT/\'scripts/check_recovered_native_registration.py\'\\n        if native.is_file():current=__import__(\'runpy\').run_path(native)[\'historical_fixture_source\'](name,current)\\n")\ndef strip_public_dispatch_test(source):\n    before,after=PUBLIC_DISPATCH_TEST_EDIT\n    if after not in source:return source\n    if source.count(after)!=1:raise ValueError(\'Public historical dispatch test inverse differs\')\n    return source.replace(after,before,1)\n')]

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def safe(root,name):
    p=root/name
    return p.is_file() and not p.is_symlink() and not any(x.is_symlink() for x in p.parents if x==root or root in x.parents)
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.DEVNULL,timeout=10)
def ancestor(root,sha,ref):return subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',sha,ref],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10).returncode==0
def inverse(source,edits):
    if not any(after in source for _,after in edits):return source
    for before,after in reversed(edits):
        if source.count(after)!=1:raise ValueError('Public registration inverse differs')
        source=source.replace(after,before,1)
    return source
def strip_bootstrap(source):return inverse(source,BOOT_EDITS)
def strip_nv(source):return inverse(source,NV_EDITS)
LOGICAL_INVENTORY_SHA = 'db613c1753e914f598e00d566a8e453f321387e710181bc900c9dbf7b22eaa0e'
PRIVACY_PATHS = {'tasks/APBRA-160-business-journey-20261104.json', 'tasks/APBRA-160-business-registration-20261104.json'}
REG_FIXTURES = {'apps/api/tests/conftest.py', 'apps/api/tests/test_foundry_private_preparation.py', 'apps/api/tests/test_foundry_report_runtime.py', 'apps/api/tests/test_native_case_files.py', 'apps/api/tests/test_native_contracts.py', 'apps/api/tests/test_native_response_integration.py', 'apps/api/tests/test_report_authorization_clock.py'}

def parse_inventory(rows,expected_paths):
    if type(rows) is not list:raise ValueError('Checksum inventory is not an array')
    result={}
    for row in rows:
        if type(row) is not list or len(row)!=2:raise ValueError('Checksum inventory row is not a path/hash pair')
        path,sha=row
        if type(path) is not str or type(sha) is not str or re.fullmatch(r'[0-9a-f]{64}',sha) is None:raise ValueError('Checksum inventory types/hash format differ')
        if path in result:raise ValueError('Checksum inventory contains duplicate paths')
        result[path]=sha
    if set(result)!=expected_paths:raise ValueError('Checksum inventory literal paths differ')
    return result
def manifest(root):
    if not safe(root,MANIFEST):raise ValueError('Frozen manifest missing or symlink')
    raw=(root/MANIFEST).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:raise ValueError('Frozen observed manifest differs')
    value=json.loads(raw)
    if value.get('schema_version')!=2 or value.get('hash_inventory_format')!='path-sha256-pairs-v1':raise ValueError('Frozen checksum inventory format differs')
    for key,paths in [('account_files',Q),('native_files',N),('privacy_originals_sha256',PRIVACY_PATHS),('registration_fixture_files',REG_FIXTURES)]:value[key]=parse_inventory(value[key],paths)
    logical={key:value[key] for key in ['account_files','native_files','privacy_originals_sha256','registration_fixture_files']}
    if digest(logical)!=LOGICAL_INVENTORY_SHA:raise ValueError('Frozen logical path/hash associations differ')
    return value
def ready(task):return task is not None and (task.get('task_mode'),task.get('readiness'),task.get('owner_acceptance'))==('IMPLEMENTATION','READY_FOR_IMPLEMENTATION','RECORDED')
def bind(root,catalog,sources,schema_errors,task_errors):
    errors=[];tasks=[]
    for name,key,branch,paths,sha in [(QT,'APBRA-160',QB,Q,QT_SHA),(NT,'APBRA-183',NB,N,NT_SHA),(RT,'APBRA-183',R,G,RT_SHA)]:
        if not (root/name).exists() and not (root/name).is_symlink():tasks.append(None);continue
        if not safe(root,name):errors.append('Public v2 task is missing or symlink');tasks.append(None);continue
        try:
            task=json.loads((root/name).read_text())
            faults=schema_errors(json.loads((root/'contracts/engineering/task-contract.schema.json').read_text()),task)
            if not faults:faults+=task_errors(task,catalog,sources)
            if digest(task)!=sha:faults.append('Public v2 exact task binding differs')
            if (task.get('task_id'),task.get('assigned_agent'),task.get('agent_card_version'),task.get('branch'),task.get('base_commit'))!=(key,'APBRA-DEVOPS','0.1',branch,BASE):faults.append('Public v2 identity/base/branch differs')
            if set(task.get('allowed_paths',[]))!=paths or len(task.get('allowed_paths',[]))!=len(paths):faults.append('Public v2 literal scope differs')
            if any(fnmatchcase(name,pattern) for name in task.get('allowed_paths',[]) for pattern in task.get('restricted_paths',[])):faults.append('Public v2 allowed/restricted scope conflict')
            if digest(sources)!=SOURCE_SHA:faults.append('Historical source register changed')
            errors+=faults;tasks.append(task if not faults and ready(task) else None)
        except (ValueError,OSError,KeyError,TypeError):errors.append('Public v2 task unreadable');tasks.append(None)
    if any(task is not None for task in tasks):
        try:manifest(root)
        except (ValueError,OSError,KeyError,TypeError):errors.append('Public v2 frozen manifest invalid')
    return (*tasks,errors)
def files_match(root,files,ref=None):
    try:
        for name,expected in files.items():
            if ref is None:
                if not safe(root,name):return False
                raw=(root/name).read_bytes()
            else:raw=git(root,'show',ref+':'+name)
            if hashlib.sha256(raw).hexdigest()!=expected:return False
        return True
    except (OSError,subprocess.SubprocessError):return False
def registration_published(root):
    try:
        if not ancestor(root,BASE,'HEAD') or not ancestor(root,BASE,'origin/main'):return False
        if not all(safe(root,name) and git(root,'show','origin/main:'+name)==(root/name).read_bytes() for name in G-REG_FIXTURES):return False
        frozen=manifest(root)
        # Only complete released product source can transition these seven TEST paths.
        released=files_match(root,frozen['account_files'],'origin/main') or files_match(root,{**frozen['account_files'],**frozen['native_files']},'origin/main')
        expected={name:frozen['account_files'][name] for name in REG_FIXTURES} if released else frozen['registration_fixture_files']
        return files_match(root,expected,'origin/main')
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):return False
def parent_released(root):
    return registration_published(root) and files_match(root,manifest(root)['account_files'],'origin/main')
def errors(root,parent,native,registration,branch,paths):
    if branch not in (R,QB,NB):return []
    if branch==R:
        if registration is None or paths!=G:return ['Public registration requires exact G21 governance-only scope']
        if not ancestor(root,BASE,'HEAD'):return ['Public registration base ancestry missing']
        return [] if files_match(root,manifest(root)['registration_fixture_files']) else ['Public registration test fixtures differ from their frozen phase']
    if not paths:return ['Public product phase is empty']
    if branch==QB:
        if parent is None:return ['Recovered Q75 implementation authority is not accepted; corrected financial/source version required']
        if not paths<=Q:return ['Recovered product requires exact finite Q75-only scope']
    else:
        if native is None or parent is None:return ['Native P17 requires accepted native and corrected parent source authority']
        if not paths<=N:return ['Native product requires finite P17-only scope']
    if registration is None or not registration_published(root):return ['Public product registration is not effective on actual main']
    frozen=manifest(root)
    if branch==QB:
        return [] if files_match(root,frozen['account_files']) else ['Recovered product differs from frozen reviewed source']
    if not parent_released(root):return ['Native product requires actually released frozen Q75 source on real main']
    combined={**frozen['account_files'],**frozen['native_files']}
    return [] if files_match(root,combined) else ['Native product differs from frozen reviewed source']
def qualified_paths(root,c,identity,branch,paths,overlap,candidate):
    try:
        if (identity,branch,paths)!=c['delivery_context'](root):return set()
        parent,native,registration,faults=bind(root,json.loads((root/'agents/catalog.json').read_text()),json.loads((root/'docs/source-register.json').read_text()),c['schema_errors'],c['task_errors'])
        if faults or parent is None or registration is None:return set()
        if not all(ancestor(root,candidate,ref) for ref in ('HEAD','origin/main')):return set()
        for name,expected in overlap.items():
            if hashlib.sha256(git(root,'show',candidate+':'+name)).hexdigest()!=expected:return set()
        faults,_=c['check'](root,active_task_id=identity,active_branch=branch,changed_paths=paths)
        if faults:return set()
        frozen=manifest(root)
        if branch in (QB,NB):
            if identity!=('APBRA-160' if branch==QB else 'APBRA-183') or errors(root,parent,native,registration,branch,paths):return set()
            return set(overlap)
        # Read-only historical supersession requires actual published frozen bytes,
        # never just a branch label or a hash from an unmerged candidate.
        for files in [{**frozen['account_files'],**frozen['native_files']},frozen['account_files']]:
            if not registration_published(root) or not files_match(root,files,'origin/main'):continue
            protected={name:files.get(name,expected) for name,expected in overlap.items()}
            if files_match(root,protected):return set(overlap)
        return set()
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):return set()

FIXTURE_BEFORE = "            gitdir = ROOT / '.git'\n            (source / '.git').write_text('gitdir: ' + str(gitdir.resolve()) + '\\n')\n"
FIXTURE_AFTER = "            gitdir = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--absolute-git-dir'], text=True).strip()\n            (source / '.git').write_text('gitdir: ' + gitdir + '\\n')\n"
def historical_fixture_source(name,source):
    if name!='tests/bootstrap/test_tenant_document_drafts_20261013_scope.py':return source
    if V3 is not None:source=V3['strip_historical_tenant_adapter'](source)
    if source.count(FIXTURE_AFTER)!=1 or FIXTURE_BEFORE in source:raise ValueError('Historical fixture producer inverse differs')
    return source.replace(FIXTURE_AFTER,FIXTURE_BEFORE,1)

PUBLIC_NATIVE_TEST_EDITS = [("['git','log','-1','--no-merges','--format=%H','HEAD','--','scripts/check_nv.py']", "['git','log','-1','--no-merges','--format=%H','444f4828c87a3a158fc102efae37196540cbbafa','--','scripts/check_nv.py']"), ("for name in H['P']:self.assertEqual(subprocess.check_output(['git','show',governance+':'+name],cwd=ROOT),(ROOT/name).read_bytes())", "for name in H['P']:self.assertEqual(subprocess.check_output(['git','show',governance+':'+name],cwd=ROOT),runpy.run_path(ROOT/'scripts/check_recovered_native_registration.py')['historical_native_source'](ROOT,name))")]
PUBLIC_DISPATCH_TEST_EDIT = ('        current=(ROOT/name).read_text()\n', "        current=(ROOT/name).read_text()\n        native=ROOT/'scripts/check_recovered_native_registration.py'\n        if native.is_file():current=__import__('runpy').run_path(native)['historical_fixture_source'](name,current)\n")
PUBLIC_HISTORY_HASHES = dict([('scripts/check_bootstrap.py', '9de4749e114784768df6e3b1da3cd9351b1b21cdbdc609477decb864beaf97c2'), ('scripts/check_dispatch_audit_20261019.py', 'c6f6c3183cc46999da41c0a1664c9d284512af2a8f30bbc8150aea77774bef2e'), ('scripts/check_gp.py', '16ef88d898ba8e3da9ead68c94f9f4544f128b5585ae9dae305c523ace11d06b'), ('scripts/check_nv.py', '26f16c49170602baff75dec1c30fdec30290791fdfdcf5a28eea53aa44d5378c'), ('scripts/check_sc.py', '2e7d43054fd2cd880b2c242a5f0acefd220286047025f1ac4f642cd09ff7ae78'), ('scripts/check_sp.py', 'c7a90d65744af1b61cdc63319722cb76c7fd7742d5eb4e9ba7611b87fd0c0213'), ('tasks/APBRA-160-native-output-verification-20261019.json', '8b1fb495ae3aedf11bc6b01c2fb9307fe9d98917478813b3c6657fa4c78ec141'), ('tests/bootstrap/test_dispatch_audit_20261019_scope.py', '22f4b9ab86bd9363d76ea8de9c1aee35b23edfa5e7ad1aa5607fa9c2af6a41fe'), ('tests/bootstrap/test_native_output_verification_20261019_scope.py', '70091afe9773a53b56b06ec32740f96e0a57831d6fbb1450c89dba4382bd2194')])

def historical_native_source(root,name):
    if name not in PUBLIC_HISTORY_HASHES or not safe(root,name):raise ValueError('Historical native readback path differs')
    source=(root/name).read_text()
    if name=='scripts/check_bootstrap.py':source=strip_bootstrap(source)
    elif name=='scripts/check_nv.py':source=strip_nv(source)
    elif name=='tests/bootstrap/test_dispatch_audit_20261019_scope.py':source=inverse(source,[PUBLIC_DISPATCH_TEST_EDIT])
    elif name=='tests/bootstrap/test_native_output_verification_20261019_scope.py':source=inverse(source,PUBLIC_NATIVE_TEST_EDITS)
    raw=source.encode()
    if hashlib.sha256(raw).hexdigest()!=PUBLIC_HISTORY_HASHES[name]:raise ValueError('Historical native readback bytes differ')
    return raw

# V3 is a separately bound CI/source version; v2 task/manifests remain immutable.
V3_PATH = 'scripts/check_ci_browser_registration_v3.py'
V3_HELPER_SHA = '0226cfb94e9c723b1f88459d897ea702fe130a8f742f68d4c66519f2c950d116'
V3_TASKS = ('tasks/APBRA-183-ci-browser-registration-v3.json', 'tasks/APBRA-160-recovered-account-public-v3.json', 'tasks/APBRA-183-native-organisation-public-v3.json')
V3_BRANCHES = {'G': R, 'Q': 'agent/APBRA-DEVOPS/APBRA-160-recovered-account-public-v3', 'N': 'agent/APBRA-DEVOPS/APBRA-183-native-organisation-public-v3'}
_v2_bind = bind
_v2_errors = errors
_v3_file = Path(__file__).with_name('check_ci_browser_registration_v3.py')
V3 = __import__('runpy').run_path(_v3_file) if _v3_file.is_file() else None

def v3_present(root):
    return any((root/name).exists() or (root/name).is_symlink() for name in V3_TASKS)

def v3_safe(root):
    return V3 is not None and safe(root,V3_PATH) and hashlib.sha256((root/V3_PATH).read_bytes()).hexdigest()==V3_HELPER_SHA

def scope(root,kind):
    if v3_present(root):
        if not v3_safe(root):return set()
        # Only the seven explicit TEST overlaps belong first to registration.
        # Declared product task paths remain complete; no runtime path is shifted.
        return V3['Q']-V3['REG_FIXTURES'] if kind=='Q' else V3[kind]
    return {'G':G,'Q':Q,'N':N}[kind]

def branch(root,kind):
    return V3_BRANCHES[kind] if v3_present(root) else {'G':R,'Q':QB,'N':NB}[kind]

def bind(root,catalog,sources,schema_errors,task_errors):
    if v3_present(root):
        if not v3_safe(root):return None,None,None,['V3 canonical helper missing, mutated or unsafe']
        return V3['bind'](root,catalog,sources,schema_errors,task_errors)
    return _v2_bind(root,catalog,sources,schema_errors,task_errors)

def errors(root,parent,native,registration,active_branch,paths):
    if active_branch in (V3_BRANCHES['Q'],V3_BRANCHES['N']) or (active_branch==R and v3_present(root)):
        if not v3_present(root) or not v3_safe(root):return ['V3 task/helper/manifest authority missing']
        return V3['errors'](root,parent,native,registration,active_branch,paths)
    return _v2_errors(root,parent,native,registration,active_branch,paths)

def workflow_projection(root,text):
    return V3['workflow_projection'](root,text) if V3 is not None else text

# Runtime and historical readback qualification select one complete authority version.
_v2_qualified_paths = qualified_paths
_v2_registration_published = registration_published
_v2_parent_released = parent_released

def registration_published(root):
    if v3_present(root):return v3_safe(root) and V3['registration_published'](root)
    return _v2_registration_published(root)

def parent_released(root):
    if v3_present(root):return v3_safe(root) and V3['parent_released'](root)
    return _v2_parent_released(root)

def qualified_paths(root,checker,identity,active_branch,paths,overlap,candidate):
    if v3_present(root) or active_branch in (V3_BRANCHES['Q'],V3_BRANCHES['N']):
        if not v3_present(root) or not v3_safe(root):return set()
        return V3['qualified_paths'](root,checker,identity,active_branch,paths,overlap,candidate)
    return _v2_qualified_paths(root,checker,identity,active_branch,paths,overlap,candidate)

# Accepted finite stages; all original helpers, pins and maps above are retained.
FINITE_STAGES = [('184', 'scripts/native_invitation_scope.py', '0240b66f84bf96f8b30d2fa7c4ad66e62b897aad657dc8302eeb426d4bdd7e6d', 'tasks/APBRA-184-native-invitations.json', 'docs/source-register-apbra184.json', 'docs/decisions/native-invitation-acceptance.md'), ('185', 'scripts/dependency_maintenance_scope.py', 'e4b82c9f4d75975f6bbf1b1b52e84f402a1a5c29118724d3ab885f20310d487c', 'tasks/APBRA-185-development-dependency-maintenance.json', 'docs/source-register-apbra185.json', 'docs/decisions/development-dependency-maintenance.md')]
FINITE_BOOT_HOOK = "        nt,nf=pn['stage_authorities'](root,catalog,schema_errors,task_errors,active_task_id,active_branch,changed_paths) if pn else ((),[]);errors+=nf;bound_authorities=bound_authorities+nt  # 184,185\n"
FINITE_BOOT_BASE_SHA = "6a6674e1d86b2e9f83c0f6a263130c53d8771f700bcc5169fa146f2f76ff4c4b"
FINITE_NV_BASE_SHA = "cbbf837ad996d00b85dd592c9b39a13bba319218adbedba830140c0c4cc50049"
FINITE_NV_APPEND = '\n# Exact finite-stage inverse; historical fixtures need no future helper.\nFINITE_BOOT_HOOK = "        nt,nf=pn[\'stage_authorities\'](root,catalog,schema_errors,task_errors,active_task_id,active_branch,changed_paths) if pn else ((),[]);errors+=nf;bound_authorities=bound_authorities+nt  # 184,185\\n"\n_finite_prior_strip_public_bootstrap = strip_public_bootstrap\n\ndef strip_public_bootstrap(source):\n    if "pn[\'stage_authorities\']" in source:\n        if source.count(FINITE_BOOT_HOOK)!=1:\n            raise ValueError("Finite stage bootstrap hook missing, duplicate or inexact")\n        source=source.replace(FINITE_BOOT_HOOK,"",1)\n    return _finite_prior_strip_public_bootstrap(source)\n'
_finite_modules = {}
_finite_prior_strip_bootstrap = strip_bootstrap
_finite_prior_strip_nv = strip_nv
_finite_prior_qualified_paths = qualified_paths

def finite_strip_bootstrap(source):
    if source.count(FINITE_BOOT_HOOK)!=1:
        raise ValueError("Finite bootstrap inverse missing, duplicate or inexact")
    restored=source.replace(FINITE_BOOT_HOOK,"",1)
    if hashlib.sha256(restored.encode()).hexdigest()!=FINITE_BOOT_BASE_SHA:
        raise ValueError("Finite bootstrap inverse changed original bytes")
    return restored

def strip_bootstrap(source):
    if "pn['stage_authorities']" in source:source=finite_strip_bootstrap(source)
    return _finite_prior_strip_bootstrap(source)

def finite_strip_nv(source):
    if source.count(FINITE_NV_APPEND)!=1:
        raise ValueError("Finite native inverse missing, duplicate or inexact")
    restored=source.replace(FINITE_NV_APPEND,"",1)
    if hashlib.sha256(restored.encode()).hexdigest()!=FINITE_NV_BASE_SHA:
        raise ValueError("Finite native inverse changed original bytes")
    return restored

def strip_nv(source):
    if "FINITE_BOOT_HOOK" in source:source=finite_strip_nv(source)
    return _finite_prior_strip_nv(source)

def finite_modules(root):
    modules=[];faults=[]
    for key,name,expected,task,source,adr in FINITE_STAGES:
        paths=(name,task,source,adr)
        if not any((root/p).exists() or (root/p).is_symlink() for p in paths):continue
        if not all(safe(root,p) for p in paths):
            faults.append(key+" incomplete or unsafe finite-stage packet");continue
        raw=(root/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected:
            faults.append(key+" finite helper differs");continue
        cachekey=(str(root.resolve()),name,expected)
        if cachekey not in _finite_modules:_finite_modules[cachekey]=__import__('runpy').run_path(root/name)
        modules.append(_finite_modules[cachekey])
    return modules,faults

def stage_authorities(root,catalog,schema_errors,task_errors,identity,branch,paths):
    modules,faults=finite_modules(root);authorities=()
    if modules:
        try:
            finite_strip_bootstrap((root/'scripts/check_bootstrap.py').read_text())
            finite_strip_nv((root/'scripts/check_nv.py').read_text())
        except (OSError,ValueError):faults.append("Finite canonical integration/preimage differs")
    for module in modules:
        bound,errors=module['bind'](root,catalog,schema_errors,task_errors,identity,branch,paths)
        authorities=authorities+bound;faults+=errors
    return authorities,faults

def qualified_paths(root,checker,identity,active_branch,paths,overlap,candidate):
    modules,faults=finite_modules(root)
    if faults:return set()
    for module in modules:
        if identity=='APBRA-'+module['KEY'] and active_branch in (module['R'],module['B']):
            return module['qualified_paths'](root,checker,identity,active_branch,paths,overlap,candidate)
    return _finite_prior_qualified_paths(root,checker,identity,active_branch,paths,overlap,candidate)

# APBRA-160 v7 registration extension. The existing inverses still verify their original hashes.
V7_REGISTRATION_BRANCH = "agent/APBRA-DEVOPS/APBRA-160-foundry-v7-registration"
V7_BOOT_HOOK = "        if pn and active_task_id=='APBRA-160' and active_branch==pn['V7_REGISTRATION_BRANCH']:\n            registered_tasks['APBRA-160']=next((t for t,_ in nt if t['branch']==active_branch),None)\n"
V7_BOOT_PREIMAGE = "52645c0d15c915b3e95e92575411434a9e1f766f73e6ac264c8b804f2e6d1313"
V7_NV_MARKER = "\n# APBRA-160 v7 native historical inverse.\n"
V7_NV_PREIMAGE = "8656ae1ba85d2a0be6d612630ae4f08782f8f22c93b9652da4e18f1c452e43fd"
V7_NV_ADDEND = "9eaecb3dd4ec1bd836b7d4b030bbfe14c1d4ac0f8ddc7e41957017cb5013d617"
V7_HELPER = "scripts/check_foundry_v7_scope.py"
V7_HELPER_SHA = "ab2efab7f487f342f05e4bf1bd32bdbe66e668a29212a21b11925e6a47002b33"
V7_FILES = {
    V7_HELPER,
    "docs/decisions/foundry-v7-qualification.md",
    "docs/source-register-apbra160-v7.json",
    "tasks/APBRA-160-foundry-v7-qualification-20261124.json",
    "tests/bootstrap/test_foundry_v7_scope.py",
}
_pre_v7_finite_bootstrap = finite_strip_bootstrap
_pre_v7_finite_nv = finite_strip_nv
_pre_v7_stage_authorities = stage_authorities
_v7_modules = {}


def remove_v7_bootstrap_hook(source):
    if source.count(V7_BOOT_HOOK) != 1:
        raise ValueError("v7 canonical hook missing, duplicate or inexact")
    return source.replace(V7_BOOT_HOOK, "", 1)


def strip_v7_bootstrap(source):
    restored = remove_v7_bootstrap_hook(source)
    if hashlib.sha256(restored.encode()).hexdigest() != V7_BOOT_PREIMAGE:
        raise ValueError("v7 canonical hook inverse changed the previous bytes")
    return restored


def strip_v7_nv(source):
    if source.count(V7_NV_MARKER) != 1:
        raise ValueError("v7 native hook missing, duplicate or inexact")
    restored, marker, tail = source.partition(V7_NV_MARKER)
    if (hashlib.sha256(restored.encode()).hexdigest() != V7_NV_PREIMAGE
            or hashlib.sha256((marker + tail).encode()).hexdigest() != V7_NV_ADDEND):
        raise ValueError("v7 native hook or its previous bytes differ")
    return restored


def finite_strip_bootstrap(source):
    if "V7_REGISTRATION_BRANCH" in source:
        source = strip_v7_bootstrap(source)
    return _pre_v7_finite_bootstrap(source)


def finite_strip_nv(source):
    if V7_NV_MARKER in source:
        source = strip_v7_nv(source)
    return _pre_v7_finite_nv(source)


def stage_authorities(root, catalog, schema_errors, task_errors, identity, branch, paths):
    authorities, faults = _pre_v7_stage_authorities(
        root, catalog, schema_errors, task_errors, identity, branch, paths,
    )
    if not (any((root / path).exists() or (root / path).is_symlink() for path in V7_FILES)
            or (branch or "").startswith("agent/APBRA-DEVOPS/APBRA-160-foundry-v7-")):
        return authorities, faults
    try:
        if not all(safe(root, path) for path in V7_FILES | {
            "scripts/check_bootstrap.py", "scripts/check_nv.py",
            "scripts/check_recovered_native_registration.py",
        }):
            raise ValueError("Missing or unsafe v7 governance path")
        strip_v7_bootstrap((root / "scripts/check_bootstrap.py").read_text())
        strip_v7_nv((root / "scripts/check_nv.py").read_text())
        helper = root / V7_HELPER
        if hashlib.sha256(helper.read_bytes()).hexdigest() != V7_HELPER_SHA:
            raise ValueError("v7 scope helper hash differs")
        key = str(root.resolve())
        if key not in _v7_modules:
            _v7_modules[key] = __import__("runpy").run_path(helper)
        bound, errors = _v7_modules[key]["bind"](
            root, catalog, schema_errors, task_errors, identity, branch, paths,
        )
    except (OSError, ValueError, KeyError, TypeError):
        return authorities, faults + ["APBRA-160 v7 exact authority or historical integration differs"]
    return authorities + bound, faults + errors


V7_RECOVERED_MARKER = '\n# APBRA-160 v7 registration extension. The existing inverses still verify their original hashes.\n'
V7_RECOVERED_PREIMAGE = "ac236229b06da685e248b98b1f39dfde20cb313d99e2376e5db625e311f75610"
_pre_v7_qualified_paths = qualified_paths


def strip_v7_recovered(source):
    if source.count(V7_RECOVERED_MARKER) != 1:
        raise ValueError("v7 recovered hook missing, duplicate or inexact")
    previous, _, _ = source.partition(V7_RECOVERED_MARKER)
    if hashlib.sha256(previous.encode()).hexdigest() != V7_RECOVERED_PREIMAGE:
        raise ValueError("v7 recovered hook inverse changed the previous bytes")
    return previous


def qualified_paths(root, checker, identity, active_branch, paths, overlap, candidate):
    if active_branch != V7_REGISTRATION_BRANCH:
        return _pre_v7_qualified_paths(root, checker, identity, active_branch, paths, overlap, candidate)
    if not v3_safe(root):
        return set()
    try:
        helper = root / V7_HELPER
        if not safe(root, V7_HELPER) or hashlib.sha256(helper.read_bytes()).hexdigest() != V7_HELPER_SHA:
            return set()
        origin = str(root.resolve())
        if origin not in _v7_modules:
            _v7_modules[origin] = __import__("runpy").run_path(helper)
        project = {
            "scripts/check_bootstrap.py": strip_v7_bootstrap,
            "scripts/check_nv.py": strip_v7_nv,
            "scripts/check_recovered_native_registration.py": strip_v7_recovered,
        }
        return _v7_modules[origin]["qualified_prior_release"](
            root, checker, identity, active_branch, paths, overlap, candidate, V3, project,
        )
    except (OSError, ValueError, KeyError, TypeError):
        return set()

# Separate APBRA-85 registration for the APBRA-164 browser test successor.
BROWSER_REG_BRANCH = "agent/APBRA-DEVOPS/APBRA-85-protected-report-browser-registration"
BROWSER_PRODUCT_BRANCH = "agent/APBRA-DEVOPS/APBRA-164-protected-report-browser-stabilisation"
BROWSER_MARKER = b"\n# Separate APBRA-85 registration for the APBRA-164 browser test successor.\n"
BROWSER_BOOT_HOOK = "        if pn and pn['browser_maintenance_branch'](active_branch):registered_tasks[active_task_id]=next((t for t,_ in nt if t['branch']==active_branch),None)\n"
BROWSER_BOOT_PREIMAGE = "b720e986c000c4e11f91ae5acb499cf717c11c16e0e52d029d96d7a969fc9bdd"
BROWSER_RECOVERED_PREIMAGE = "428ee9f72b746e2b9cec2893395b40a0c16a7da300c5695cf714973d4696a0cf"
BROWSER_HELPER = "scripts/check_protected_report_browser_registration.py"
BROWSER_HELPER_SHA = "08ae498ec47f5d85dee481ace67d7b1628b8c72cf8481c0bdf5ccbbff6c45f46"
BROWSER_PACKET = {
    BROWSER_HELPER,
    "tasks/APBRA-164-protected-report-browser-stabilisation-20261124.json",
    "tests/bootstrap/test_protected_report_browser_registration.py",
}
_pre_browser_remove_v7_bootstrap = remove_v7_bootstrap_hook
_pre_browser_strip_v7_recovered = strip_v7_recovered
_pre_browser_stage_authorities = stage_authorities
_pre_browser_qualified_paths = qualified_paths
_browser_modules = {}


def browser_maintenance_branch(branch):
    return branch in (BROWSER_REG_BRANCH, BROWSER_PRODUCT_BRANCH)


def remove_browser_bootstrap_hook(source):
    if source.count(BROWSER_BOOT_HOOK) != 1:
        raise ValueError("Browser registration canonical hook missing, duplicate or inexact")
    return source.replace(BROWSER_BOOT_HOOK, "", 1)


def remove_v7_bootstrap_hook(source):
    if "browser_maintenance_branch" in source:
        source = remove_browser_bootstrap_hook(source)
    return _pre_browser_remove_v7_bootstrap(source)


def strip_browser_bootstrap(source):
    restored = remove_browser_bootstrap_hook(source.decode()).encode()
    if hashlib.sha256(restored).hexdigest() != BROWSER_BOOT_PREIMAGE:
        raise ValueError("Browser registration canonical preimage differs")
    return restored


def strip_browser_recovered(source):
    if source.count(BROWSER_MARKER) != 1:
        raise ValueError("Browser registration recovered marker missing or duplicate")
    restored = source.split(BROWSER_MARKER, 1)[0]
    if hashlib.sha256(restored).hexdigest() != BROWSER_RECOVERED_PREIMAGE:
        raise ValueError("Browser registration recovered preimage differs")
    return restored


def strip_v7_recovered(source):
    if BROWSER_MARKER.decode() in source:
        source = strip_browser_recovered(source.encode()).decode()
    return _pre_browser_strip_v7_recovered(source)


def browser_packet_present(root, branch, paths):
    return (
        browser_maintenance_branch(branch)
        or bool(paths and paths & BROWSER_PACKET)
        or any((root / name).exists() or (root / name).is_symlink() for name in BROWSER_PACKET)
    )


def browser_module(root):
    if not all(safe(root, name) for name in BROWSER_PACKET | {
        "scripts/check_bootstrap.py", "scripts/check_recovered_native_registration.py", V7_HELPER,
    }):
        raise ValueError("Browser registration packet missing or unsafe")
    strip_browser_bootstrap((root / "scripts/check_bootstrap.py").read_bytes())
    strip_browser_recovered((root / "scripts/check_recovered_native_registration.py").read_bytes())
    helper = root / BROWSER_HELPER
    if hashlib.sha256(helper.read_bytes()).hexdigest() != BROWSER_HELPER_SHA:
        raise ValueError("Browser registration helper bytes differ")
    if hashlib.sha256((root / V7_HELPER).read_bytes()).hexdigest() != V7_HELPER_SHA:
        raise ValueError("Original v7 helper bytes differ")
    key = str(root.resolve())
    if key not in _browser_modules:
        _browser_modules[key] = __import__("runpy").run_path(helper)
    if key not in _v7_modules:
        _v7_modules[key] = __import__("runpy").run_path(root / V7_HELPER)
    return _browser_modules[key], _v7_modules[key]["raw"]


def stage_authorities(root, catalog, schema_errors, task_errors, identity, branch, paths):
    authorities, faults = _pre_browser_stage_authorities(
        root, catalog, schema_errors, task_errors, identity, branch, paths,
    )
    if not browser_packet_present(root, branch, paths):
        return authorities, faults
    try:
        module, raw = browser_module(root)
        selected, errors = module["bind"](
            root, raw, V3, catalog, schema_errors, task_errors, identity, branch, paths,
        )
        return authorities + selected, faults + errors
    except (OSError, ValueError, KeyError, TypeError):
        return authorities, faults + ["Protected-report browser registration packet or exact integration differs"]


def qualified_paths(root, checker, identity, active_branch, paths, overlap, candidate):
    if not browser_packet_present(root, active_branch, paths):
        return _pre_browser_qualified_paths(root, checker, identity, active_branch, paths, overlap, candidate)
    try:
        module, raw = browser_module(root)
        # For prior registered lanes, preserve their own verified evidence whenever it applies.
        if not browser_maintenance_branch(active_branch):
            prior = _pre_browser_qualified_paths(root, checker, identity, active_branch, paths, overlap, candidate)
            if prior:
                return prior
        if not v3_safe(root):
            return set()
        projections = {
            "scripts/check_bootstrap.py": strip_browser_bootstrap,
            "scripts/check_recovered_native_registration.py": strip_browser_recovered,
        }
        return module["qualified"](
            root, checker, raw, V3, projections, (identity, active_branch, paths), overlap, candidate,
        )
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, RecursionError):
        return set()

# APBRA-85 browser delivery context correction. Keep the entire PR188 prefix.
BROWSER_CONTEXT_MARKER = b"\n# APBRA-85 browser delivery context correction. Keep the entire PR188 prefix.\n"
BROWSER_CONTEXT_BASE_SHA = "d0ffc959dfcfe515c43d1c7f8c7bd3cc8701802b59aee7dbeb6a838eca8c9873"
BROWSER_CONTEXT_BRANCH = "agent/APBRA-DEVOPS/APBRA-85-browser-delivery-context"
BROWSER_CONTEXT_HELPER = "scripts/check_protected_report_browser_context.py"
BROWSER_CONTEXT_HELPER_SHA = "4ce3991701f9073890aabf63743eb668aee7b8438783705d7dc0466fd737d54d"
BROWSER_CONTEXT_FILES = {BROWSER_CONTEXT_HELPER, "tests/bootstrap/test_protected_report_browser_context.py"}
_pre_context_browser_branch = browser_maintenance_branch
_pre_context_stage_authorities = stage_authorities
_pre_context_qualified_paths = qualified_paths
_browser_context_modules = {}


def browser_maintenance_branch(branch):
    return branch == BROWSER_CONTEXT_BRANCH or _pre_context_browser_branch(branch)


def browser_context_present(root, branch, paths):
    return (
        branch == BROWSER_CONTEXT_BRANCH
        or bool(paths and paths & BROWSER_CONTEXT_FILES)
        or any((root / name).exists() or (root / name).is_symlink() for name in BROWSER_CONTEXT_FILES)
    )


def strip_browser_context(source):
    if source.count(BROWSER_CONTEXT_MARKER) != 1:
        raise ValueError("Browser delivery context marker missing or duplicate")
    prefix = source.split(BROWSER_CONTEXT_MARKER, 1)[0]
    if hashlib.sha256(prefix).hexdigest() != BROWSER_CONTEXT_BASE_SHA:
        raise ValueError("Browser delivery context PR188 preimage differs")
    return prefix


def browser_context_module(root):
    if not all(safe(root, name) for name in BROWSER_CONTEXT_FILES):
        raise ValueError("Missing or unsafe browser delivery context packet")
    old, raw = browser_module(root)
    strip_browser_context(raw(root, "scripts/check_recovered_native_registration.py"))
    helper = root / BROWSER_CONTEXT_HELPER
    if hashlib.sha256(helper.read_bytes()).hexdigest() != BROWSER_CONTEXT_HELPER_SHA:
        raise ValueError("Browser delivery context helper bytes differ")
    key = str(root.resolve())
    if key not in _browser_context_modules:
        _browser_context_modules[key] = __import__("runpy").run_path(helper)
    return _browser_context_modules[key], old, raw


def stage_authorities(root, catalog, schema_errors, task_errors, identity, branch, paths):
    if not browser_context_present(root, branch, paths):
        return _pre_context_stage_authorities(root, catalog, schema_errors, task_errors, identity, branch, paths)
    authorities, faults = _pre_browser_stage_authorities(
        root, catalog, schema_errors, task_errors, identity, branch, paths,
    )
    try:
        module, old, raw = browser_context_module(root)
        selected, errors = module["bind"](
            root, old, raw, V3, catalog, schema_errors, task_errors, identity, branch, paths,
        )
        return authorities + selected, faults + errors
    except (OSError, ValueError, KeyError, TypeError):
        return authorities, faults + ["Browser delivery context packet or exact integration differs"]


def qualified_paths(root, checker, identity, branch, paths, overlap, candidate):
    if not browser_context_present(root, branch, paths):
        return _pre_context_qualified_paths(root, checker, identity, branch, paths, overlap, candidate)
    try:
        module, old, raw = browser_context_module(root)
        if not browser_maintenance_branch(branch):
            prior = _pre_context_qualified_paths(root, checker, identity, branch, paths, overlap, candidate)
            if prior:
                return prior
        if not v3_safe(root):
            return set()
        return module["qualified"](
            root, old, raw, V3, checker, (identity, branch, paths), overlap, candidate,
        )
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, RecursionError):
        return set()

# APBRA-160 v7 metadata issuance. Preserve the original registration and inverses.
METADATA_ISSUANCE_MARKER = b"\n# APBRA-160 v7 metadata issuance. Preserve the original registration and inverses.\n"
METADATA_BOOT_HOOK = "        if pn and pn['issued_v7_branch'](active_branch):registered_tasks[active_task_id]=pn['metadata_task'](nt,active_branch)\n"
METADATA_BOOT_PREIMAGE = 'fbee1b21f7a17cff347227c2ec820b7e3f764a57302f4eea483bda112ab69b2f'
METADATA_RECOVERED_PREIMAGE = '61ac9f362a90082a69d33d9f0cb4b27e47073813dbe860df4deb18480093e091'
METADATA_SCOPE_HELPER = "scripts/check_foundry_v7_metadata_issuance.py"
METADATA_SCOPE_SHA = "f55a0010fb3d43319112cb896d7af3f825a6255765492a66390be25873bc0daf"
METADATA_PACKET = {
    METADATA_SCOPE_HELPER,
    "tasks/APBRA-160-foundry-v7-metadata-issuance-20261124.json",
    "tests/bootstrap/test_foundry_v7_metadata_issuance.py",
}
METADATA_PRODUCT_BRANCH = "agent/APBRA-DEVOPS/APBRA-160-foundry-v7-metadata"
METADATA_ISSUANCE_BRANCH = METADATA_PRODUCT_BRANCH + "-issuance-finite-context"
_pre_metadata_remove_browser_hook = remove_browser_bootstrap_hook
_pre_metadata_stage_authorities = stage_authorities
_pre_metadata_qualified_paths = qualified_paths
_metadata_modules = {}


def issued_v7_branch(branch):
    return branch in (METADATA_ISSUANCE_BRANCH, METADATA_PRODUCT_BRANCH)


def metadata_task(authorities, branch):
    return next((task for task, _ in authorities if task['branch'] == branch), None)


def remove_metadata_bootstrap_hook(source):
    if source.count(METADATA_BOOT_HOOK) != 1:
        raise ValueError("Metadata issuance bootstrap hook missing, duplicate or inexact")
    return source.replace(METADATA_BOOT_HOOK, "", 1)


def remove_browser_bootstrap_hook(source):
    # Restore the specific next selector before the earlier structural inverse.
    if "issued_v7_branch" in source:
        source = remove_metadata_bootstrap_hook(source)
    return _pre_metadata_remove_browser_hook(source)


def strip_metadata_bootstrap(source):
    restored = remove_metadata_bootstrap_hook(source.decode()).encode()
    if hashlib.sha256(restored).hexdigest() != METADATA_BOOT_PREIMAGE:
        raise ValueError("Metadata issuance canonical preimage differs")
    return restored


def strip_metadata_recovered(source):
    if source.count(METADATA_ISSUANCE_MARKER) != 1:
        raise ValueError("Metadata issuance recovered marker missing or duplicate")
    restored = source.split(METADATA_ISSUANCE_MARKER, 1)[0]
    if hashlib.sha256(restored).hexdigest() != METADATA_RECOVERED_PREIMAGE:
        raise ValueError("Metadata issuance recovered preimage differs")
    return restored


def metadata_packet_present(root, active_branch, paths):
    return (
        issued_v7_branch(active_branch)
        or bool(paths and paths & METADATA_PACKET)
        or any((root / name).exists() or (root / name).is_symlink() for name in METADATA_PACKET)
    )


def metadata_module(root):
    if not all(safe(root, name) for name in METADATA_PACKET | {
        "scripts/check_bootstrap.py", "scripts/check_recovered_native_registration.py",
    }):
        raise ValueError("Metadata issuance packet missing or unsafe")
    strip_metadata_bootstrap((root / "scripts/check_bootstrap.py").read_bytes())
    strip_metadata_recovered((root / "scripts/check_recovered_native_registration.py").read_bytes())
    helper = root / METADATA_SCOPE_HELPER
    if hashlib.sha256(helper.read_bytes()).hexdigest() != METADATA_SCOPE_SHA:
        raise ValueError("Metadata issuance helper bytes differ")
    if not safe(root, V7_HELPER) or hashlib.sha256((root / V7_HELPER).read_bytes()).hexdigest() != V7_HELPER_SHA:
        raise ValueError("Original v7 scope helper bytes differ")
    key = str(root.resolve())
    if key not in _metadata_modules:
        _metadata_modules[key] = __import__("runpy").run_path(helper)
    if key not in _v7_modules:
        _v7_modules[key] = __import__("runpy").run_path(root / V7_HELPER)
    return _metadata_modules[key], _v7_modules[key]


def stage_authorities(root, catalog, schema_errors, task_errors, identity, branch, paths):
    authorities, faults = _pre_metadata_stage_authorities(
        root, catalog, schema_errors, task_errors, identity, branch, paths,
    )
    if not metadata_packet_present(root, branch, paths):
        return authorities, faults
    try:
        module, old = metadata_module(root)
        selected, errors = module["bind"](root, old, catalog, schema_errors, task_errors, identity, branch, paths)
        if branch == METADATA_PRODUCT_BRANCH and selected and not errors:
            # The unmodified registration remains dormant on its own.
            if faults.count(module["UNISSUED"]) != 1:
                raise ValueError("Original v7 metadata denial differs")
            faults = [fault for fault in faults if fault != module["UNISSUED"]]
        return authorities + selected, faults + errors
    except (OSError, ValueError, KeyError, TypeError):
        return authorities, faults + ["Foundry v7 metadata issuance packet or exact integration differs"]


def metadata_browser_witness(root, checker, context, overlap, candidate, module, old):
    """Retain the verified browser release across the independently bound v7 layer."""
    branch, paths = context[1:]
    if branch == METADATA_ISSUANCE_BRANCH:
        if paths != module["ISSUANCE_PATHS"] or module["ref"](root, module["MAIN"]) != module["BASE"]:
            return set()
        if not module["candidate_head"](root, module["BASE"], paths, old["raw"]):
            return set()
    elif not module["released_issuance"](root, old["raw"]):
        return set()

    browser, original, raw = browser_context_module(root)
    wrapper = "scripts/check_recovered_native_registration.py"
    canonical = "scripts/check_bootstrap.py"
    projections = {
        wrapper: (METADATA_ISSUANCE_MARKER, strip_metadata_recovered),
        canonical: (METADATA_BOOT_HOOK.encode(), strip_metadata_bootstrap),
    }

    def projected_raw(origin, name):
        current = raw(origin, name)
        return projections[name][1](current) if name in projections else current

    def matches(origin, selected, commit, read):
        # Compare the two strictly governed prefixes and every other source.
        # The exact next issuance layer was already verified above.
        for name in selected & projections.keys():
            current = original["git"](origin, "show", commit + ":" + name)
            mode = original["git"](origin, "ls-tree", commit, "--", name).split(b" ", 1)[0]
            marker, inverse = projections[name]
            if marker in current:
                current = inverse(current)
            if mode != b"100644" or current != read(origin, name):
                return False
        return original["matches"](origin, selected - projections.keys(), commit, read)

    previous = dict(original, matches=matches)
    prior = browser["qualified"](
        root, previous, projected_raw, V3, checker, context, overlap, candidate,
    )
    if prior or context[0] != "APBRA-184":
        return prior

    # The exact metadata release was verified above. Read the existing browser
    # snapshot through the committed main version of just the invitation paths.
    # Both the original browser and invitation witnesses must still pass.
    modules, faults = finite_modules(root)
    invitation = next((stage for stage in modules if stage["KEY"] == "184"), None)
    main = module["ref"](root, module["MAIN"])
    if (
        faults or invitation is None or branch != invitation["B"] or paths != invitation["P"]
        or module["changed"](root, main, "HEAD") != paths
        or module["git"](root, "status", "--porcelain", "--untracked-files=all", "-z")
        or not module["matches_commit"](root, paths, "HEAD", projected_raw)
    ):
        return set()

    def invitation_files_match(origin, expected, ref=None):
        if ref is not None:
            return V3["files_match"](origin, expected, ref)
        scoped = {name: digest for name, digest in expected.items() if name in paths}
        unchanged = {name: digest for name, digest in expected.items() if name not in paths}
        return (
            V3["files_match"](origin, unchanged)
            and V3["files_match"](origin, scoped, main)
        )

    historical = dict(V3, files_match=invitation_files_match)
    earlier = browser["qualified"](
        root, previous, projected_raw, historical, checker, context, overlap, candidate,
    )
    if earlier != set(overlap):
        return set()
    return invitation["qualified_paths"](root, checker, *context, overlap, candidate)


def qualified_paths(root, checker, identity, active_branch, paths, overlap, candidate):
    if not metadata_packet_present(root, active_branch, paths):
        return _pre_metadata_qualified_paths(root, checker, identity, active_branch, paths, overlap, candidate)
    try:
        module, old = metadata_module(root)
        if not v3_safe(root):
            return set()
        context = (identity, active_branch, paths)
        prior = metadata_browser_witness(root, checker, context, overlap, candidate, module, old)
        if prior != set(overlap):
            return set()
        return prior | module["metadata_successor"](root, checker, context, old)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, RecursionError):
        return set()

# APBRA-85 invitation release readback. Retain the complete PR192 sources.
INVITATION_READBACK_MARKER = b"\n# APBRA-85 invitation release readback. Retain the complete PR192 sources.\n"
INVITATION_READBACK_BASE = "b58dbf6825dabbdf3c007aca672d1e38615ca5e8"
INVITATION_READBACK_BRANCH = "agent/APBRA-DEVOPS/APBRA-85-native-invitation-release-readback"
INVITATION_READBACK_WRAPPER_SHA = "06273888ff552a742320efbf51777923d65ecf0eaf49bf856910105db05ae6bd"
INVITATION_READBACK_METADATA_SHA = "9e611ddd17553bcbc6c9e541225102e68bc5e79bed36745b0990553b381a781d"
INVITATION_READBACK_HELPER = "scripts/check_native_invitation_release_readback.py"
INVITATION_READBACK_HELPER_SHA = "7c40af1fcfccd4eca4d3a7df8f16b4b67feb8c53bc830e039a5e3cfd9021a37b"
INVITATION_READBACK_TESTS = "tests/bootstrap/test_native_invitation_release_readback.py"
INVITATION_READBACK_ADDITIONS = {INVITATION_READBACK_HELPER, INVITATION_READBACK_TESTS}
INVITATION_READBACK_WRAPPER = "scripts/check_recovered_native_registration.py"
_pre_readback_browser_branch = browser_maintenance_branch
_pre_readback_metadata_module = metadata_module
_pre_readback_stage_authorities = stage_authorities
_pre_readback_qualified_paths = qualified_paths
_invitation_readback_modules = {}


def browser_maintenance_branch(branch):
    return branch == INVITATION_READBACK_BRANCH or _pre_readback_browser_branch(branch)


def strip_invitation_readback_wrapper(source):
    if source.count(INVITATION_READBACK_MARKER) != 1:
        raise ValueError("Invitation readback wrapper marker missing or duplicate")
    previous = source.split(INVITATION_READBACK_MARKER, 1)[0]
    if hashlib.sha256(previous).hexdigest() != INVITATION_READBACK_WRAPPER_SHA:
        raise ValueError("Invitation readback wrapper PR192 preimage differs")
    return previous


def strip_invitation_readback_metadata(source):
    changes = (
        (b"def released_issuance(root, raw, *, issuance_matches=matches_commit):",
         b"def released_issuance(root, raw):", 1),
        (b"and issuance_matches(root, ISSUANCE_PATHS,", b"and matches_commit(root, ISSUANCE_PATHS,", 2),
        (b"identity, branch, paths,\n         *, issuance_matches=matches_commit):",
         b"identity, branch, paths):", 1),
        (b"def metadata_successor(root, checker, context, old, *, issuance_matches=matches_commit):",
         b"def metadata_successor(root, checker, context, old):", 1),
        (b'released_issuance(root, old["raw"], issuance_matches=issuance_matches)',
         b'released_issuance(root, old["raw"])', 2),
    )
    for added, previous, count in changes:
        if source.count(added) != count:
            raise ValueError("Invitation readback metadata inverse differs")
        source = source.replace(added, previous)
    if hashlib.sha256(source).hexdigest() != METADATA_SCOPE_SHA:
        raise ValueError("Invitation readback metadata PR192 preimage differs")
    return source


def invitation_readback_present(root, branch, paths):
    return (branch == INVITATION_READBACK_BRANCH
            or bool(paths and paths & INVITATION_READBACK_ADDITIONS)
            or any((root / name).exists() or (root / name).is_symlink()
                   for name in INVITATION_READBACK_ADDITIONS))


def invitation_readback_metadata_sources(root):
    packet = METADATA_PACKET | {"scripts/check_bootstrap.py", INVITATION_READBACK_WRAPPER, V7_HELPER}
    if not all(safe(root, name) for name in packet):
        raise ValueError("Invitation readback metadata packet missing or unsafe")
    strip_metadata_bootstrap((root / "scripts/check_bootstrap.py").read_bytes())
    wrapper = strip_invitation_readback_wrapper((root / INVITATION_READBACK_WRAPPER).read_bytes())
    strip_metadata_recovered(wrapper)
    source = (root / METADATA_SCOPE_HELPER).read_bytes()
    if hashlib.sha256(source).hexdigest() != INVITATION_READBACK_METADATA_SHA:
        raise ValueError("Invitation readback metadata helper bytes differ")
    strip_invitation_readback_metadata(source)
    if hashlib.sha256((root / V7_HELPER).read_bytes()).hexdigest() != V7_HELPER_SHA:
        raise ValueError("Original v7 scope helper bytes differ")
    key = str(root.resolve())
    metadata_key = (key, INVITATION_READBACK_METADATA_SHA)
    if metadata_key not in _metadata_modules:
        _metadata_modules[metadata_key] = __import__("runpy").run_path(root / METADATA_SCOPE_HELPER)
    if key not in _v7_modules:
        _v7_modules[key] = __import__("runpy").run_path(root / V7_HELPER)
    return _metadata_modules[metadata_key], _v7_modules[key]


def invitation_readback_sources(root):
    metadata, old = invitation_readback_metadata_sources(root)
    if not all(safe(root, name) for name in INVITATION_READBACK_ADDITIONS):
        raise ValueError("Incomplete or unsafe invitation readback packet")
    helper = root / INVITATION_READBACK_HELPER
    if hashlib.sha256(helper.read_bytes()).hexdigest() != INVITATION_READBACK_HELPER_SHA:
        raise ValueError("Invitation readback helper bytes differ")
    key = str(root.resolve())
    if key not in _invitation_readback_modules:
        _invitation_readback_modules[key] = __import__("runpy").run_path(helper)
    return _invitation_readback_modules[key], metadata, old


def invitation_readback_context(root):
    readback, metadata, old = invitation_readback_sources(root)
    state = readback["amendment_state"](root, metadata, old["raw"])
    inverses = {
        INVITATION_READBACK_WRAPPER: strip_invitation_readback_wrapper,
        METADATA_SCOPE_HELPER: strip_invitation_readback_metadata,
    }
    return readback, state, readback["metadata_view"](metadata, state, inverses), old


def metadata_module(root):
    if invitation_readback_present(root, None, None):
        if not (root / ".git").exists():
            # Older static source checks copy the tracked tree without Git.
            # Keep their original inventory and no-ref metadata behaviour.
            _, metadata, old = invitation_readback_sources(root)
        else:
            _, _, metadata, old = invitation_readback_context(root)
        return metadata, old

    helper = root / METADATA_SCOPE_HELPER
    wrapper = root / INVITATION_READBACK_WRAPPER
    has_readback_marker = (
        safe(root, INVITATION_READBACK_WRAPPER)
        and INVITATION_READBACK_MARKER in wrapper.read_bytes()
    )
    amended_metadata = (
        safe(root, METADATA_SCOPE_HELPER)
        and hashlib.sha256(helper.read_bytes()).hexdigest() == INVITATION_READBACK_METADATA_SHA
    )
    if not (has_readback_marker or amended_metadata):
        return _pre_readback_metadata_module(root)
    metadata, old = invitation_readback_metadata_sources(root)
    # The original PR192 tests build an earlier five-file issuance from
    # current sources and omit later packet files. Keep the original
    # matcher's exact-byte behaviour in those historical Git contexts.
    if not (root / ".git").exists() or not metadata["approved_base"](root):
        raise ValueError("Incomplete invitation readback has no historical scope")
    for revision in ("HEAD", metadata["MAIN"]):
        status = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(root), "merge-base", "--is-ancestor",
             INVITATION_READBACK_BASE, revision], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=10,
        )
        if status.returncode == 0:
            raise ValueError("Incomplete invitation readback on or after actual PR192")
    return metadata, old


def stage_authorities(root, catalog, schema_errors, task_errors, identity, branch, paths):
    if not invitation_readback_present(root, branch, paths):
        return _pre_readback_stage_authorities(root, catalog, schema_errors, task_errors, identity, branch, paths)
    if not (root / ".git").exists():
        live_branches = {INVITATION_READBACK_BRANCH, METADATA_PRODUCT_BRANCH, METADATA_ISSUANCE_BRANCH}
        scope = INVITATION_READBACK_ADDITIONS | {INVITATION_READBACK_WRAPPER, METADATA_SCOPE_HELPER}
        if branch in live_branches or paths and paths & scope:
            return (), ["Native invitation release readback packet or exact authority differs"]
        return _pre_readback_stage_authorities(root, catalog, schema_errors, task_errors, identity, branch, paths)
    authorities, faults = _pre_metadata_stage_authorities(
        root, catalog, schema_errors, task_errors, identity, branch, paths,
    )
    try:
        readback, state, metadata, old = invitation_readback_context(root)
        scope = readback["SCOPE"]
        candidate = branch == INVITATION_READBACK_BRANCH
        if candidate:
            if identity != readback["ISSUE"] or paths != scope or state[1] is not None:
                raise ValueError("Invitation readback candidate identity or scope differs")
        elif paths and paths & readback["ADDITIONS"]:
            raise ValueError("New invitation readback files require their exact governance branch")
        selected, errors = metadata["bind"](
            root, old, catalog, schema_errors, task_errors, identity, branch, None if candidate else paths,
        )
        if branch == METADATA_PRODUCT_BRANCH and selected and not errors:
            if faults.count(metadata["UNISSUED"]) != 1:
                raise ValueError("Original v7 metadata denial differs")
            faults = [fault for fault in faults if fault != metadata["UNISSUED"]]
        if candidate and selected and not errors:
            authority = readback["issuance_authority"](selected[0][0])
            selected += ((authority, scope),)
        return authorities + selected, faults + errors
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return authorities, faults + ["Native invitation release readback packet or exact authority differs"]


def released_invitation_browser_witness(root, checker, context, overlap, candidate, readback,
                                        invitation, prior):
    browser, original, raw = browser_context_module(root)
    canonical = "scripts/check_bootstrap.py"
    projections = {
        INVITATION_READBACK_WRAPPER: (METADATA_ISSUANCE_MARKER, strip_metadata_recovered),
        canonical: (METADATA_BOOT_HOOK.encode(), strip_metadata_bootstrap),
    }

    def projected_raw(origin, name):
        current = raw(origin, name)
        return projections[name][1](current) if name in projections else current

    def matches(origin, selected, commit, read):
        for name in selected & projections.keys():
            current = original["git"](origin, "show", commit + ":" + name)
            mode = original["git"](origin, "ls-tree", commit, "--", name).split(b" ", 1)[0]
            marker, inverse = projections[name]
            if marker in current:
                current = inverse(current)
            if mode != b"100644" or current != read(origin, name):
                return False
        return original["matches"](origin, selected - projections.keys(), commit, read)

    protected = original["protected_snapshot"](root, V3).keys()
    historical = readback["historical_with_invitation"](V3, invitation["P"], prior, protected)
    return browser["qualified"](
        root, dict(original, matches=matches), projected_raw, historical, checker, context, overlap, candidate,
    )


def qualified_paths(root, checker, identity, active_branch, paths, overlap, candidate):
    if not invitation_readback_present(root, active_branch, paths):
        return _pre_readback_qualified_paths(root, checker, identity, active_branch, paths, overlap, candidate)
    try:
        readback, state, metadata, old = invitation_readback_context(root)
        if not v3_safe(root) or not metadata["released_issuance"](root, old["raw"]):
            return set()
        context = (identity, active_branch, paths)
        modules, faults = finite_modules(root)
        invitation = next((module for module in modules if module["KEY"] == "184"), None)
        if faults or invitation is None:
            return set()
        prior = readback["invitation_release_before"](root, metadata, state, invitation, old["raw"])
        if prior is None:
            witness = metadata_browser_witness(root, checker, context, overlap, candidate, metadata, old)
        else:
            witness = released_invitation_browser_witness(
                root, checker, context, overlap, candidate, readback, invitation, prior,
            )
        if witness != set(overlap):
            return set()
        return witness | metadata["metadata_successor"](root, checker, context, old)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, RecursionError):
        return set()

# APBRA-160 issue 193 documentation registration. Keep the PR194 prefix exact.
REPORT_DOCS_MARKER = b"\n# APBRA-160 issue 193 documentation registration. Keep the PR194 prefix exact.\n"
REPORT_DOCS_ANCHOR = "a15e393a4c8dc789d210c905dd885a0a6c650e84"
REPORT_DOCS_ANCHOR_TREE = "0ff18a113dccc4a21c23c89748ab14519b287ba8"
REPORT_DOCS_WRAPPER_SHA = "3a641ba3480c9c57cb5fcb2d023b57bbed6b3cd5aa20fd3ec6286460ad702f26"
REPORT_DOCS_ISSUE = "APBRA-160"
REPORT_DOCS_BRANCH = "agent/APBRA-DOCS/APBRA-160-foundry-report-delivery-docs"
REPORT_DOCS_REGISTRATION_BRANCH = "agent/APBRA-DEVOPS/APBRA-160-foundry-report-delivery-docs-registration"
REPORT_DOCS_BRANCHES = frozenset({REPORT_DOCS_BRANCH, REPORT_DOCS_REGISTRATION_BRANCH})
REPORT_DOCS_TASK = "tasks/APBRA-160-foundry-report-documentation-20261125.json"
REPORT_DOCS_SOURCE = "docs/source-register-apbra160-foundry-report-documentation.json"
REPORT_DOCS_TEST = "tests/bootstrap/test_foundry_report_documentation_scope.py"
REPORT_DOCS_ADDITIONS = frozenset({REPORT_DOCS_TASK, REPORT_DOCS_SOURCE, REPORT_DOCS_TEST})
REPORT_DOCS_REGISTRATION = REPORT_DOCS_ADDITIONS | {INVITATION_READBACK_WRAPPER}
REPORT_DOCS_PATHS = frozenset({
    "AI-RAG-SPEC.md", "ARCHITECTURE.md", "MVP-ACCEPTANCE-CRITERIA.md",
    "POWERBI-GENERATION-SPEC.md", "README.md", "REQUIREMENTS.md",
    "docs/decisions/implementation-baseline.md", "docs/engineering/codex-handoff.md",
})
REPORT_DOCS_METADATA_BLOBS = (
    b"100644 blob e7e37f77f98323c090dfa5f8feda7d74d74df460\tapps/api/src/apbra_api/foundry_owner_metadata.py\x00"
    b"100644 blob 410620efbdf2f25fe8c97fd1f78d643d3c206a16\tapps/api/tests/test_foundry_owner_metadata.py\x00"
)
import os


DOCS_CORRECTION_BASE = "3b5ca7a840b40bdcb3571a1e4aca4809bcd33256"
DOCS_CORRECTION_BRANCH = "agent/APBRA-DEVOPS/APBRA-160-issue193-checkout-correction"
DOCS_CORRECTION_PATHS = frozenset({INVITATION_READBACK_WRAPPER, REPORT_DOCS_TEST})
DOCS_CORRECTION_WRAPPER_SHA = "0c062e8cfd73c26b650748fe5e8e0a667683a6104ef54687563f36cbc377ad60"
DOCS_CORRECTION_TEST_SHA = "c165a7d7cbdaa538f6404329353287bc6de5600dbfd401edae336505d1cc2bb7"
DOCS_ORIGINAL_DIGESTS = {
    INVITATION_READBACK_WRAPPER: "8579cfa859587f34b0e7fe1d82bfadb2e1cdf2ba12fb740462129a8d66debc20",
    REPORT_DOCS_TEST: "9ffafe1af9e8ae2f9b5d00253c7f55863689bc15a2522df7e028429c5a39499b",
}


_report_docs_previous_branch = issued_v7_branch
_report_docs_previous_authorities = stage_authorities
_report_docs_previous_readback = invitation_readback_context


def issued_v7_branch(branch):
    return branch == DOCS_CORRECTION_BRANCH or branch in REPORT_DOCS_BRANCHES or _report_docs_previous_branch(branch)


def strip_report_docs_wrapper(source):
    if source.count(REPORT_DOCS_MARKER) != 1:
        raise ValueError("Documentation registration marker is missing or duplicate")
    prefix = source.split(REPORT_DOCS_MARKER, 1)[0]
    if hashlib.sha256(prefix).hexdigest() != REPORT_DOCS_WRAPPER_SHA:
        raise ValueError("Documentation registration altered the PR194 wrapper")
    return prefix


def report_docs_packet_present(root):
    return any((root / path).exists() or (root / path).is_symlink()
               for path in REPORT_DOCS_ADDITIONS)


def report_docs_packet(root):
    if not all(safe(root, path) for path in REPORT_DOCS_REGISTRATION):
        raise ValueError("Incomplete or unsafe documentation registration packet")
    strip_report_docs_wrapper((root / INVITATION_READBACK_WRAPPER).read_bytes())
    sources = (root / REPORT_DOCS_SOURCE).read_bytes()
    task = (root / REPORT_DOCS_TASK).read_bytes()
    if (
        hashlib.sha256(sources).hexdigest() != "70326567649ec96191a88aa704c5a030a5ae69e0b5cae668dcb304ef517a53aa"
        or hashlib.sha256(task).hexdigest() != "16d803dce1f497884d42a488c6ed51ba129fa6344656ff88eca4e03fe3db3705"
    ):
        raise ValueError("Exact documentation task or source pin differs")
    source = json.loads(sources)
    historical = source["historical_source_register"]
    if (
        historical != "docs/source-register.json" or not safe(root, historical)
        or hashlib.sha256((root / historical).read_bytes()).hexdigest() != source["historical_source_register_sha256"]
    ):
        raise ValueError("Historical source register differs")
    return json.loads(task), source


def report_docs_registration_base(root, readback, metadata, base):
    if base == REPORT_DOCS_ANCHOR:
        return True
    parents = readback["parents"](root, metadata["git"], base)
    return (
        len(parents) == 2 and parents[0] == REPORT_DOCS_ANCHOR
        and metadata["owner_merge"](root, base, METADATA_PRODUCT_BRANCH, metadata["PRODUCT_PATHS"])
        and readback["entries"](root, metadata, base, metadata["PRODUCT_PATHS"]) == REPORT_DOCS_METADATA_BLOBS
    )


def docs_checkout_candidate(root, readback, metadata, raw, main, branch, paths):
    """Distinguish a named direct child from the CI checkout of that same child."""
    git = metadata["git"]
    attached = git(root, "branch", "--show-current").decode().strip()
    parents = readback["parents"](root, git, "HEAD")
    reported = os.environ.get("GITHUB_HEAD_REF")
    if attached:
        if attached != branch or parents != [main]:
            return False
        if reported and (reported != branch or os.environ.get("GITHUB_BASE_REF") != "main"):
            return False
    elif (
        len(parents) != 2 or reported != branch or os.environ.get("GITHUB_BASE_REF") != "main"
        or os.environ.get("PR_HEAD_SHA") != parents[1]
    ):
        return False
    return metadata["candidate_head"](root, main, paths, raw)


def original_docs_file(root, metadata, path):
    original = metadata["git"](root, "show", DOCS_CORRECTION_BASE + ":" + path)
    if hashlib.sha256(original).hexdigest() != DOCS_ORIGINAL_DIGESTS[path]:
        raise ValueError("PR196 original governance source differs")
    return original


def docs_correction_state(root, readback, metadata, raw, main):
    """Verify the independent two-file change against the real PR196 merge."""
    actual = {path: raw(root, path) for path in DOCS_CORRECTION_PATHS}
    if any((root / path).stat().st_mode & 0o111 for path in actual):
        raise ValueError("Issue 193 governance sources must remain regular 100644 files")
    release = readback["first_touch"](root, metadata, DOCS_CORRECTION_BASE, main, DOCS_CORRECTION_PATHS)
    if not release and all(hashlib.sha256(data).hexdigest() == DOCS_ORIGINAL_DIGESTS[path]
                           for path, data in actual.items()):
        return False
    # Normalize only the checksum value in its one declaration. This binds the
    # complete checker and the test digest without a circular source checksum.
    source = actual[INVITATION_READBACK_WRAPPER]
    declaration = ('DOCS_CORRECTION_WRAPPER_SHA = "' + DOCS_CORRECTION_WRAPPER_SHA + '"').encode()
    template = declaration.replace(DOCS_CORRECTION_WRAPPER_SHA.encode(), b"0" * 64)
    if (
        source.count(declaration) != 1
        or hashlib.sha256(source.replace(declaration, template)).hexdigest() != DOCS_CORRECTION_WRAPPER_SHA
        or hashlib.sha256(actual[REPORT_DOCS_TEST]).hexdigest() != DOCS_CORRECTION_TEST_SHA
    ):
        raise ValueError("Exact issue 193 correction sources differ")
    if not release:
        if main != DOCS_CORRECTION_BASE or not docs_checkout_candidate(
            root, readback, metadata, raw, main, DOCS_CORRECTION_BRANCH, DOCS_CORRECTION_PATHS
        ):
            raise ValueError("Issue 193 correction requires its clean direct or hosted candidate on PR196")
    elif (
        readback["parents"](root, metadata["git"], release)[0] != DOCS_CORRECTION_BASE
        or not metadata["owner_merge"](root, release, DOCS_CORRECTION_BRANCH, DOCS_CORRECTION_PATHS)
        or not metadata["ancestor"](root, release, "HEAD")
        or not all(metadata["matches_commit"](root, DOCS_CORRECTION_PATHS, commit, raw)
                   for commit in (release, main, "HEAD"))
    ):
        raise ValueError("Issue 193 correction release or continued two-file packet differs")
    return True


def report_docs_registration_state(root, readback, metadata, raw):
    """Verify the exact registration commit or its ordinary release from trusted main."""
    readback["require_checkout"](root, metadata)
    ref, ancestor = metadata["ref"], metadata["ancestor"]
    main = ref(root, metadata["MAIN"])
    if (
        ref(root, REPORT_DOCS_ANCHOR + "^{tree}") != REPORT_DOCS_ANCHOR_TREE
        or not all(ancestor(root, REPORT_DOCS_ANCHOR, target) for target in (main, "HEAD"))
    ):
        raise ValueError("Documentation registration requires the actual PR194 anchor")
    release = readback["first_touch"](root, metadata, REPORT_DOCS_ANCHOR, main, REPORT_DOCS_REGISTRATION)
    if release is None:
        if (
            report_docs_registration_base(root, readback, metadata, main)
            and readback["actual_branch"](root, metadata, REPORT_DOCS_REGISTRATION_BRANCH)
            and metadata["candidate_head"](root, main, REPORT_DOCS_REGISTRATION, raw)
        ):
            return main, None, False
        raise ValueError("Documentation registration requires its exact four-file candidate on allowed main")
    corrected = release == DOCS_CORRECTION_BASE and docs_correction_state(root, readback, metadata, raw, main)

    def registration_matches(commit):
        def read(origin, path):
            if corrected and commit == DOCS_CORRECTION_BASE and path in DOCS_CORRECTION_PATHS:
                return original_docs_file(origin, metadata, path)
            return raw(origin, path)

        return metadata["matches_commit"](root, REPORT_DOCS_REGISTRATION, commit, read)

    parents = readback["parents"](root, metadata["git"], release)
    if (
        len(parents) != 2 or not report_docs_registration_base(root, readback, metadata, parents[0])
        or not metadata["owner_merge"](root, release, REPORT_DOCS_REGISTRATION_BRANCH, REPORT_DOCS_REGISTRATION)
        or not ancestor(root, release, "HEAD")
        or not all(registration_matches(commit) for commit in (release, main, "HEAD"))
    ):
        raise ValueError("Documentation registration requires an ordinary release with its exact packet")
    return main, release, corrected


def invitation_readback_context(root):
    if not report_docs_packet_present(root):
        return _report_docs_previous_readback(root)

    readback, metadata, old = invitation_readback_sources(root)
    raw = old["raw"]
    main, release, corrected = report_docs_registration_state(root, readback, metadata, raw)

    def matches(origin, paths, revision, read):
        commit = metadata["ref"](origin, revision)
        if corrected and commit == DOCS_CORRECTION_BASE and paths in (readback["SCOPE"], metadata["ISSUANCE_PATHS"]):
            def pr196_read(checkout, path):
                if path == INVITATION_READBACK_WRAPPER:
                    return original_docs_file(checkout, metadata, path)
                return read(checkout, path)

            return metadata["matches_commit"](origin, paths, commit, pr196_read)
        prior_readback = paths == readback["SCOPE"] and commit == REPORT_DOCS_ANCHOR
        prospective_main = (
            release is None and commit == main
            and paths in (readback["SCOPE"], metadata["ISSUANCE_PATHS"])
        )
        # Compare the original packets against PR194 and against the still
        # unamended protected main only when the doc registration is prospective.
        if not (prior_readback or prospective_main):
            return metadata["matches_commit"](origin, paths, commit, read)
        if metadata["ref"](origin, metadata["MAIN"]) != main:
            return False

        def previous_raw(checkout, path):
            source = read(checkout, path)
            return strip_report_docs_wrapper(source) if path == INVITATION_READBACK_WRAPPER else source

        return metadata["matches_commit"](origin, paths, commit, previous_raw)

    readback_metadata = dict(metadata, matches_commit=matches)
    state = readback["amendment_state"](root, readback_metadata, raw)
    inverses = {
        INVITATION_READBACK_WRAPPER: lambda source: strip_invitation_readback_wrapper(strip_report_docs_wrapper(source)),
        METADATA_SCOPE_HELPER: strip_invitation_readback_metadata,
    }
    return readback, state, readback["metadata_view"](readback_metadata, state, inverses), old


def report_docs_markdown_matches(root, metadata, commit, source, expected, *, raw=None):
    git = metadata["git"]
    for path in sorted(REPORT_DOCS_PATHS):
        mode = git(root, "ls-tree", commit, "--", path).split(b" ", 1)[0]
        blob = git(root, "show", commit + ":" + path)
        if mode != b"100644" or hashlib.sha256(blob).hexdigest() != source["approved_markdown"][path][expected]:
            return False
        if raw is not None and (raw(root, path) != blob or (root / path).stat().st_mode & 0o111):
            return False
    return True


def report_docs_current_markdown(root, metadata, raw, main, source, expected):
    head = metadata["ref"](root, "HEAD")
    return (
        (head == main or report_docs_markdown_matches(root, metadata, main, source, expected))
        and report_docs_markdown_matches(root, metadata, head, source, expected, raw=raw)
    )


def report_docs_product_authority(root, readback, metadata, raw, source, main, registration, branch, corrected):
    if not registration:
        return False

    recent = readback["first_touch"](root, metadata, registration, main, REPORT_DOCS_PATHS)
    if recent:
        parents = readback["parents"](root, metadata["git"], recent)
        if (
            len(parents) != 2
            or not metadata["owner_merge"](root, recent, REPORT_DOCS_BRANCH, REPORT_DOCS_PATHS)
            or not metadata["ancestor"](root, recent, "HEAD")
            or not report_docs_markdown_matches(root, metadata, parents[0], source, "preimage_sha256")
            or not report_docs_markdown_matches(root, metadata, recent, source, "approved_sha256")
            or not report_docs_current_markdown(root, metadata, raw, main, source, "approved_sha256")
        ):
            raise ValueError("Effective issue 193 documentation merge or continued approved bytes differ")
        return False

    if branch != REPORT_DOCS_BRANCH and report_docs_current_markdown(
        root, metadata, raw, main, source, "preimage_sha256"
    ):
        return False
    if corrected:
        admitted = docs_checkout_candidate(root, readback, metadata, raw, main, REPORT_DOCS_BRANCH, REPORT_DOCS_PATHS)
    else:
        admitted = (
            readback["actual_branch"](root, metadata, REPORT_DOCS_BRANCH)
            and metadata["candidate_head"](root, main, REPORT_DOCS_PATHS, raw)
        )
    admitted = (
        admitted and report_docs_markdown_matches(root, metadata, main, source, "preimage_sha256")
        and report_docs_markdown_matches(root, metadata, "HEAD", source, "approved_sha256", raw=raw)
    )
    if branch != REPORT_DOCS_BRANCH:
        if not (corrected and admitted):
            raise ValueError("Registered issue 193 preimages must remain exact before the documentation release")
        # The actual checkout has proved the approved eight outputs. A query
        # about a historical branch receives only its normal historical scope.
        return False
    return admitted


def stage_authorities(root, catalog, schema_errors, task_errors, identity, branch, paths):
    authorities, faults = _report_docs_previous_authorities(
        root, catalog, schema_errors, task_errors, identity, branch, paths,
    )
    if branch != DOCS_CORRECTION_BRANCH and branch not in REPORT_DOCS_BRANCHES and not report_docs_packet_present(root):
        return authorities, faults

    try:
        task, source = report_docs_packet(root)
        schema = json.loads((root / "contracts/engineering/task-contract.schema.json").read_bytes())
        if schema_errors(schema, task) or task_errors(task, catalog, source):
            raise ValueError("Issue 193 documentation task contract is invalid")
        registration = dict(
            task, assigned_agent="APBRA-DEVOPS", branch=REPORT_DOCS_REGISTRATION_BRANCH,
            execution_id="APBRA-160-20261125-DOCS-193-REG-01",
            allowed_paths=sorted(REPORT_DOCS_REGISTRATION),
            restricted_paths=["apps/**", ".github/**", "infra/**", ".env*", "local-data/**"],
            task_mode="SPECIFICATION", readiness="READY_FOR_SPECIFICATION",
        )
        if not (root / ".git").exists():
            # Historical source-only fixtures can inventory the exact packet.
            # Effective branch authority always requires a physical Git checkout.
            if branch == DOCS_CORRECTION_BRANCH or branch in REPORT_DOCS_BRANCHES or paths and paths & REPORT_DOCS_ADDITIONS:
                raise ValueError("Documentation authority requires its own Git checkout")
            return authorities + ((registration, REPORT_DOCS_REGISTRATION),), faults

        readback, metadata, old = invitation_readback_sources(root)
        main, release, corrected = report_docs_registration_state(root, readback, metadata, old["raw"])
        if branch == DOCS_CORRECTION_BRANCH:
            if not (
                corrected and main == DOCS_CORRECTION_BASE and identity == REPORT_DOCS_ISSUE
                and paths == DOCS_CORRECTION_PATHS
                and report_docs_current_markdown(root, metadata, old["raw"], main, source, "preimage_sha256")
            ):
                raise ValueError("Issue 193 correction requires its exact candidate, identity and two paths")
            amendment = dict(registration, branch=DOCS_CORRECTION_BRANCH, base_commit=main,
                             execution_id="APBRA-160-20261126-ISSUE193-CONTEXT",
                             allowed_paths=sorted(DOCS_CORRECTION_PATHS))
            return authorities + ((registration, REPORT_DOCS_REGISTRATION), (amendment, DOCS_CORRECTION_PATHS)), faults
        if branch == REPORT_DOCS_REGISTRATION_BRANCH:
            if (
                identity != REPORT_DOCS_ISSUE or paths != REPORT_DOCS_REGISTRATION or release is not None
                or not report_docs_markdown_matches(root, metadata, main, source, "preimage_sha256")
            ):
                raise ValueError("Issue 193 registration requires its exact branch, scope and eight preimages")
            return authorities + ((dict(registration, base_commit=main), REPORT_DOCS_REGISTRATION),), faults

        if paths and paths & REPORT_DOCS_REGISTRATION:
            raise ValueError("Issue 193 registration paths require their separate branch")
        authorities += ((registration, REPORT_DOCS_REGISTRATION),)
        product_admitted = report_docs_product_authority(
            root, readback, metadata, old["raw"], source, main, release, branch, corrected,
        )
        if branch == REPORT_DOCS_BRANCH:
            if identity != REPORT_DOCS_ISSUE or paths != REPORT_DOCS_PATHS or not product_admitted:
                raise ValueError("Issue 193 requires a released registration and exact approved documentation bytes")
            authorities += ((dict(task, base_commit=main), REPORT_DOCS_PATHS),)
        return authorities, faults
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        return authorities, faults + ["APBRA-160 issue 193 documentation scope denied: " + str(error)]
