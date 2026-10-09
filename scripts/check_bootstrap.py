"""Bounded engineering checks, not an authorization or product-certification engine."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import sys

from jsonschema import Draft202012Validator
from referencing import Registry
import yaml

CAPSTONE_SHELL_PATHS = {'apps/web/src/style.css', 'apps/web/README.md', 'apps/web/src/workflow.test.ts', 'apps/web/src/App.tsx', 'apps/web/tsconfig.json', 'apps/web/package.json', 'apps/web/src/workflow.ts', 'apps/web/package-lock.json', 'apps/web/index.html', 'apps/web/src/App.test.tsx', 'apps/web/src/main.tsx'}

CAPSTONE_REQUIREMENTS_PATHS = {'apps/web/src/App.test.tsx', 'apps/web/src/requirements.test.ts', 'apps/web/README.md', 'apps/web/src/requirements.ts', 'apps/web/src/App.tsx'}

CAPSTONE_KNOWLEDGE_PATHS = {'apps/web/src/knowledge.test.tsx', 'apps/web/src/App.tsx', 'apps/web/src/knowledge.ts', 'apps/web/src/KnowledgePanel.tsx', 'apps/web/README.md'}

CAPSTONE_GOVERNANCE_PATHS = {'apps/web/src/App.test.tsx', 'apps/web/src/GovernancePanel.tsx', 'apps/web/README.md', 'apps/web/src/governance.test.ts', 'apps/web/src/governance.ts', 'apps/web/src/App.tsx'}
CAPSTONE_ORCHESTRATION_PATHS = {'apps/web/src/execution.test.ts', 'apps/web/src/App.tsx', 'apps/web/README.md', 'apps/web/src/GovernancePanel.tsx', 'apps/web/src/execution.ts', 'apps/web/src/App.test.tsx'}
CAPSTONE_VALIDATION_PATHS = {'apps/web/README.md', 'apps/web/src/validation.ts', 'apps/web/src/validation.test.ts', 'apps/web/src/validationProfile.json', 'apps/web/src/App.tsx'}
CAPSTONE_GENERATION_PATHS = {'apps/web/src/archive.ts', 'apps/web/src/App.test.tsx', 'apps/web/src/raw.d.ts', 'apps/web/src/App.tsx', 'apps/web/src/powerbi.ts', 'apps/web/src/powerbi.test.ts', 'apps/web/README.md'}
CAPSTONE_DESIGN_PATHS = {'apps/web/src/KnowledgePanel.tsx', 'apps/web/src/knowledge.test.tsx', 'apps/web/README.md', 'apps/web/src/designPlan.ts', 'apps/web/src/App.tsx', 'apps/web/src/designPlan.test.ts'}
DEPLOYMENT_GUIDE_PATHS = {
    'apps/web/src/deploymentGuide.ts',
    'apps/web/src/deploymentGuide.test.ts',
    'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/App.test.tsx',
    'apps/web/package.json',
    'apps/web/package-lock.json',
}
CAPSTONE_UX_PATHS = {
    'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/style.css',
    'apps/web/src/App.test.tsx',
    'apps/web/src/EnterpriseUI.tsx',
    'apps/web/src/EnterpriseUI.test.tsx',
}
MEASURE_RESOLUTION_PATHS = {
    'apps/web/src/foundry.ts',
    'apps/web/src/foundry.test.ts',
    'apps/web/src/guardrail.ts',
    'apps/web/src/guardrail.test.ts',
    'apps/web/src/genericPowerBI.ts',
    'apps/web/src/genericPowerBI.test.ts',
    'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/App.test.tsx',
}
REPORT_DESIGN_NORMALIZATION_PATHS = {
    'apps/web/src/reportDesignNormalization.ts',
    'apps/web/src/reportDesignNormalization.test.ts',
    'apps/web/src/foundry.ts',
    'apps/web/src/foundry.test.ts',
    'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/App.test.tsx',
}
CAPSTONE_DOCUMENTATION_PATHS = {
    'README.md',
    'ARCHITECTURE.md',
    'REQUIREMENTS.md',
    'AI-RAG-SPEC.md',
    'POWERBI-GENERATION-SPEC.md',
    'MVP-ACCEPTANCE-CRITERIA.md',
    'apps/web/README.md',
    'docs/engineering/capstone-evidence.md',
    'docs/engineering/codex-handoff.md',
}
CAPSTONE_DOCUMENTATION_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-140-capstone-documentation.json',
    'tests/bootstrap/test_capstone_documentation_scope.py',
}
MEASURE_CONTRACT_PIPELINE_PATHS = {
    'apps/web/src/foundry.ts',
    'apps/web/src/foundry.test.ts',
    'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/App.test.tsx',
}
MEASURE_CONTRACT_PIPELINE_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-141-measure-contract-pipeline.json',
    'tests/bootstrap/test_measure_contract_pipeline_scope.py',
}
LAYOUT_REPAIR_PATHS = {
    'apps/web/src/foundry.ts',
    'apps/web/src/foundry.test.ts',
    'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/App.test.tsx',
    'apps/web/src/reportDesignNormalization.ts',
    'apps/web/src/reportDesignNormalization.test.ts',
}
LAYOUT_REPAIR_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-142-layout-repair.json',
    'tests/bootstrap/test_layout_repair_scope.py',
}
TYPED_CONFIRMED_REQUIREMENTS_PATHS = {
    'apps/web/src/foundry.ts',
    'apps/web/src/foundry.test.ts',
    'apps/web/src/confirmedRequirements.ts',
    'apps/web/src/confirmedRequirements.test.ts',
    'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/App.test.tsx',
    'apps/web/src/reportDesignNormalization.ts',
    'apps/web/src/reportDesignNormalization.test.ts',
}
TYPED_CONFIRMED_REQUIREMENTS_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-143-typed-confirmed-requirements.json',
    'tests/bootstrap/test_typed_confirmed_requirements_scope.py',
}
AI_NATIVE_CLARIFICATION_PATHS = {
    'apps/web/src/clarification.ts',
    'apps/web/src/clarification.test.ts',
    'apps/web/src/foundry.ts',
    'apps/web/src/foundry.test.ts',
    'apps/web/src/confirmedRequirements.ts',
    'apps/web/src/confirmedRequirements.test.ts',
    'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/App.test.tsx',
    'apps/web/src/tenant.ts',
}
AI_NATIVE_CLARIFICATION_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-144-ai-native-iterative-clarification.json',
    'tests/bootstrap/test_ai_native_clarification_scope.py',
}
GENERIC_TIME_GRAIN_PATHS = {
    'apps/web/src/App.test.tsx',
    'apps/web/src/foundry.ts',
    'apps/web/src/foundry.test.ts',
    'apps/web/src/reportDesignNormalization.ts',
    'apps/web/src/reportDesignNormalization.test.ts',
    'apps/web/src/genericPowerBI.ts',
    'apps/web/src/genericPowerBI.test.ts',
    'apps/web/src/tenant.ts',
}
GENERIC_TIME_GRAIN_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-145-generic-time-grain-support.json',
    'tests/bootstrap/test_generic_time_grain_scope.py',
}
POST_CAPSTONE_MVP_BASELINE_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-146-post-capstone-mvp-baseline-reconciliation.json',
    'tests/bootstrap/test_post_capstone_mvp_baseline_scope.py',
}
POST_CAPSTONE_PRODUCT_RECONCILIATION_PATHS = {
    'AGENTS.md',
    'docs/decisions/implementation-baseline.md',
    'README.md',
    'ARCHITECTURE.md',
    'REQUIREMENTS.md',
    'AI-RAG-SPEC.md',
    'POWERBI-GENERATION-SPEC.md',
    'MVP-ACCEPTANCE-CRITERIA.md',
    'apps/web/README.md',
    'docs/engineering/capstone-evidence.md',
    'docs/engineering/codex-handoff.md',
}
POST_CAPSTONE_PRODUCT_RECONCILIATION_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-148-post-capstone-product-reconciliation.json',
    'tests/bootstrap/test_post_capstone_product_reconciliation_scope.py',
    'docs/source-register.json',
}
DATA_MODEL_DOCUMENTATION_RECONCILIATION_PATHS = {
    'DATA-MODEL.md',
    'docs/engineering/codex-handoff.md',
}
DATA_MODEL_DOCUMENTATION_RECONCILIATION_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-159-data-model-documentation-reconciliation.json',
    'tests/bootstrap/test_data_model_documentation_reconciliation_scope.py',
    'docs/source-register.json',
}
CONFIRMATION_READINESS_INTEGRITY_PATHS = {
    'apps/web/src/clarification.ts',
    'apps/web/src/clarification.test.ts',
    'apps/web/src/confirmedRequirements.ts',
    'apps/web/src/confirmedRequirements.test.ts',
    'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/App.test.tsx',
    'apps/web/README.md',
    'docs/engineering/codex-handoff.md',
}
CONFIRMATION_READINESS_INTEGRITY_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-147-confirmation-readiness-integrity.json',
    'tests/bootstrap/test_confirmation_readiness_integrity_scope.py',
    'docs/source-register.json',
}
INVITED_PRIVATE_CASE_FOUNDATION_PATHS = {
    'apps/api/.dockerignore',
    'apps/api/.env.example',
    'apps/api/Dockerfile',
    'apps/api/README.md',
    'apps/api/pyproject.toml',
    'apps/api/uv.lock',
    'apps/api/alembic.ini',
    'apps/api/alembic/env.py',
    'apps/api/alembic/script.py.mako',
    'apps/api/alembic/versions/20260923_01_invited_private_case_foundation.py',
    'apps/api/src/apbra_api/__init__.py',
    'apps/api/src/apbra_api/config.py',
    'apps/api/src/apbra_api/domain.py',
    'apps/api/src/apbra_api/application.py',
    'apps/api/src/apbra_api/auth_boundary.py',
    'apps/api/src/apbra_api/oidc_adapter.py',
    'apps/api/src/apbra_api/authorization.py',
    'apps/api/src/apbra_api/persistence.py',
    'apps/api/src/apbra_api/bootstrap.py',
    'apps/api/src/apbra_api/api.py',
    'apps/api/src/apbra_api/main.py',
    'apps/api/tests/conftest.py',
    'apps/api/tests/test_authentication.py',
    'apps/api/tests/test_authorization.py',
    'apps/api/tests/test_invitations.py',
    'apps/api/tests/test_cases.py',
    'apps/api/tests/test_api.py',
    'apps/api/tests/test_migrations.py',
    'apps/api/tests/test_bootstrap.py',
    'apps/web/.env.example',
    'apps/web/README.md',
    'apps/web/package.json',
    'apps/web/package-lock.json',
    'apps/web/vite.config.ts',
    'apps/web/playwright.config.ts',
    'apps/web/e2e/private-case.spec.ts',
    'apps/web/src/api.ts',
    'apps/web/src/api.test.ts',
    'apps/web/src/privateCases.tsx',
    'apps/web/src/privateCases.test.tsx',
    'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/App.test.tsx',
    'apps/web/src/style.css',
    'compose.yaml',
    '.github/workflows/bootstrap.yml',
    'scripts/check_ci_policy.py',
    'tests/bootstrap/test_bootstrap.py',
    'README.md',
}
INVITED_PRIVATE_CASE_FOUNDATION_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-162-invited-private-case-foundation.json',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'docs/source-register.json',
}
INVITED_PRIVATE_CASE_FOUNDATION_TASK_SHA256 = '7acc6d58d90cdd99e2fded77223d6dcc1e80e6d275042f34254d299a3cbaf702'
INVITED_PRIVATE_CASE_FOUNDATION_SOURCE_SHA256 = '067467b5557cf3fa1f381056622b014f3d96cd84a076252f917fcbc186ca23e2'
INVITED_PRIVATE_CASE_FOUNDATION_AMENDMENT_SOURCE_SHA256 = '8f01e0e8b4833c744734e0a872dfe3238c2aae8c6da1b415272608dff49000fa'
INVITED_PRIVATE_CASE_FOUNDATION_BOOTSTRAP_FIX_SHA256 = '5a800efd19a58a14ccff61a2e2cd03deecabed61c5c14cc725bd9ddf09ed2c9c'
DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_PATHS = {
    '.github/workflows/bootstrap.yml', 'README.md', 'compose.yaml',
    'apps/api/.dockerignore', 'apps/api/.env.example', 'apps/api/Dockerfile',
    'apps/api/README.md', 'apps/api/pyproject.toml', 'apps/api/uv.lock',
    'apps/api/alembic/versions/20260924_02_durable_conversation_evidence_acceptance.py',
    'apps/api/src/apbra_api/api.py', 'apps/api/src/apbra_api/application.py',
    'apps/api/src/apbra_api/authorization.py', 'apps/api/src/apbra_api/config.py',
    'apps/api/src/apbra_api/domain.py', 'apps/api/src/apbra_api/evidence.py',
    'apps/api/src/apbra_api/main.py', 'apps/api/src/apbra_api/persistence.py',
    'apps/api/src/apbra_api/semantic_bridge.py', 'apps/api/tests/conftest.py',
    'apps/api/tests/test_acceptance.py', 'apps/api/tests/test_api.py',
    'apps/api/tests/test_authorization.py', 'apps/api/tests/test_cases.py',
    'apps/api/tests/test_conversations.py', 'apps/api/tests/test_evidence.py',
    'apps/api/tests/test_migrations.py', 'apps/api/tests/test_semantic_bridge.py',
    'apps/web/README.md', 'apps/web/e2e/durable-conversation.spec.ts',
    'apps/web/e2e/private-case.spec.ts', 'apps/web/package-lock.json',
    'apps/web/package.json', 'apps/web/playwright.config.ts',
    'apps/web/scripts/semantic-bridge.ts', 'apps/web/src/App.test.tsx',
    'apps/web/src/EnterpriseApp.tsx', 'apps/web/src/api.test.ts',
    'apps/web/src/api.ts', 'apps/web/src/clarification.test.ts',
    'apps/web/src/clarification.ts', 'apps/web/src/confirmedRequirements.test.ts',
    'apps/web/src/confirmedRequirements.ts', 'apps/web/src/durableConversation.test.tsx',
    'apps/web/src/durableConversation.tsx', 'apps/web/src/foundry.test.ts',
    'apps/web/src/foundry.ts', 'apps/web/src/privateCases.test.tsx',
    'apps/web/src/privateCases.tsx', 'apps/web/src/schemaIngestion.test.ts',
    'apps/web/src/schemaIngestion.ts', 'apps/web/src/style.css', 'apps/web/vite.config.ts',
    'scripts/check_ci_policy.py', 'tests/bootstrap/test_ci_policy.py',
}
DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-163-durable-conversation-evidence-acceptance.json',
    'tests/bootstrap/test_durable_conversation_evidence_acceptance_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'docs/source-register.json',
}
DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_AMENDMENT_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-163-durable-conversation-evidence-acceptance.json',
    'tests/bootstrap/test_durable_conversation_evidence_acceptance_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'docs/source-register.json',
}
DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_CAPACITY_AMENDMENT_PATHS = (
    DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_AMENDMENT_PATHS | {
        '.github/workflows/bootstrap.yml',
        'scripts/check_ci_policy.py',
        'tests/bootstrap/test_ci_policy.py',
    }
)
DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_TASK_SHA256 = '613490d5ecf7eca776b89c340bbe657dda3d64ad6b37dcd0d7ed7f16b834ecf1'
DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_SOURCE_SHA256 = '8d294bd8db6ce7928b90d81c74de8d467d29273fb68deab0d43e35d86f151060'
DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_AMENDMENT_SOURCE_SHA256 = '5aff7adca13643781f7ebc219ce92448df9e971ad3301df3dbe31e427db300fa'
DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_HISTORICAL_FIX_SOURCE_SHA256 = '77b1008cac35b06213ce4acfa5fd2f7950f03d84ec33810f6460cbceb45c24c4'
DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_CAPACITY_WORKFLOW_SHA256 = 'c48d57ca571e266883cdc25c37304a16a5a2cf738fe1ccc7d03fa12f3e5d9141'
PROTECTED_GENERATION_OUTPUT_HISTORY_PATHS = {
    '.github/workflows/bootstrap.yml', 'README.md', 'compose.yaml',
    'apps/api/Dockerfile', 'apps/api/README.md', 'apps/api/pyproject.toml',
    'apps/api/uv.lock',
    'apps/api/alembic/versions/20260924_03_protected_generation_output_history.py',
    'apps/api/src/apbra_api/api.py', 'apps/api/src/apbra_api/application.py',
    'apps/api/src/apbra_api/artifacts.py', 'apps/api/src/apbra_api/authorization.py',
    'apps/api/src/apbra_api/config.py', 'apps/api/src/apbra_api/domain.py',
    'apps/api/src/apbra_api/generation.py', 'apps/api/src/apbra_api/main.py',
    'apps/api/src/apbra_api/persistence.py', 'apps/api/src/apbra_api/semantic_bridge.py',
    'apps/api/tests/conftest.py', 'apps/api/tests/test_acceptance.py',
    'apps/api/tests/test_api.py', 'apps/api/tests/test_artifacts.py',
    'apps/api/tests/test_authorization.py', 'apps/api/tests/test_conversations.py',
    'apps/api/tests/test_generation.py', 'apps/api/tests/test_migrations.py',
    'apps/api/tests/test_semantic_bridge.py', 'apps/web/README.md',
    'apps/web/e2e/protected-generation.spec.ts', 'apps/web/package-lock.json',
    'apps/web/package.json', 'apps/web/playwright.config.ts',
    'apps/web/scripts/generation-bridge.ts', 'apps/web/src/App.test.tsx',
    'apps/web/src/EnterpriseApp.tsx', 'apps/web/src/api.test.ts',
    'apps/web/src/api.ts', 'apps/web/src/confirmedRequirements.test.ts',
    'apps/web/src/confirmedRequirements.ts', 'apps/web/src/deploymentGuide.test.ts',
    'apps/web/src/deploymentGuide.ts', 'apps/web/src/durableConversation.test.tsx',
    'apps/web/src/durableConversation.tsx', 'apps/web/src/durableGeneration.test.tsx',
    'apps/web/src/durableGeneration.tsx', 'apps/web/src/execution.test.ts',
    'apps/web/src/execution.ts', 'apps/web/src/foundry.test.ts',
    'apps/web/src/foundry.ts', 'apps/web/src/genericPowerBI.test.ts',
    'apps/web/src/genericPowerBI.ts', 'apps/web/src/governance.test.ts',
    'apps/web/src/governance.ts', 'apps/web/src/guardrail.test.ts',
    'apps/web/src/guardrail.ts', 'apps/web/src/knowledge.test.tsx',
    'apps/web/src/knowledge.ts', 'apps/web/src/powerbi.test.ts',
    'apps/web/src/powerbi.ts', 'apps/web/src/rag.test.ts', 'apps/web/src/rag.ts',
    'apps/web/src/reportDesignNormalization.test.ts',
    'apps/web/src/reportDesignNormalization.ts', 'apps/web/src/style.css',
    'apps/web/src/tenant.ts', 'apps/web/src/validation.test.ts',
    'apps/web/src/validation.ts', 'apps/web/vite.config.ts',
    'scripts/check_ci_policy.py', 'tests/bootstrap/test_ci_policy.py',
}
PROTECTED_GENERATION_OUTPUT_HISTORY_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-164-protected-generation-output-history.json',
    'tests/bootstrap/test_protected_generation_output_history_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'docs/source-register.json',
}
PROTECTED_GENERATION_OUTPUT_HISTORY_TASK_SHA256 = '9b1a1c1b8314dbea829083c83760306808046350c0a541d99d292883a264a34a'
PROTECTED_GENERATION_OUTPUT_HISTORY_SOURCE_SHA256 = 'dd9da96390eec30550204c53a9452095e89ac369c90856acf52e4ea06995acad'
PROTECTED_GENERATION_OUTPUT_HISTORY_AMENDMENT_BRANCH = 'agent/APBRA-DEVOPS/APBRA-164-bootstrap-compatibility-amendment'
PROTECTED_GENERATION_OUTPUT_HISTORY_AMENDMENT_SOURCE_ID = 'mvp1-protected-generation-output-history-bootstrap-compatibility-amendment'
PROTECTED_GENERATION_OUTPUT_HISTORY_AMENDMENT_SOURCE_SHA256 = '08c74385f68523d5e3a69ef7b6caa98a2b6b6760e22808deb3d3e1800a7d7429'
BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_PATHS = {
    'apps/api/alembic/versions/20260929_04_reviewed_report_design.py',
    'apps/api/src/apbra_api/api.py',
    'apps/api/src/apbra_api/domain.py',
    'apps/api/src/apbra_api/generation.py',
    'apps/api/src/apbra_api/persistence.py',
    'apps/api/tests/test_generation.py',
    'apps/api/tests/test_migrations.py',
    'apps/web/e2e/durable-conversation.spec.ts',
    'apps/web/e2e/private-case.spec.ts',
    'apps/web/e2e/protected-generation.spec.ts',
    'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/api.test.ts',
    'apps/web/src/api.ts',
    'apps/web/src/durableConversation.test.tsx',
    'apps/web/src/durableConversation.tsx',
    'apps/web/src/durableGeneration.test.tsx',
    'apps/web/src/durableGeneration.tsx',
    'apps/web/src/privateCases.test.tsx',
    'apps/web/src/privateCases.tsx',
    'apps/web/src/style.css',
}
BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-169-business-friendly-ux-application-shell.json',
    'tests/bootstrap/test_business_friendly_ux_application_shell_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'docs/source-register.json',
}
BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_TASK_SHA256 = '895fc86ccd6d88a5b2f37ffe53c399f9c86f64b739e4586a67d0b187ae3a6592'
BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_SOURCE_SHA256 = 'd8da98d6c8bcd7af6683c4f1f86a0113f11368a317d0053993df50920c875399'
BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_AMENDMENT_BRANCH = 'agent/APBRA-DEVOPS/APBRA-169-reviewed-design-governance-amendment'
BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_AMENDMENT_SOURCE_ID = 'mvp1-business-friendly-ux-reviewed-design-amendment'
BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_AMENDMENT_SOURCE_SHA256 = 'd2eee3c8dcf4c07aee257debe64148fdfc4fd430186ef68c8367cc00fbe81202'
PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_PATHS = {
    'apps/web/e2e/durable-conversation.spec.ts',
    'apps/web/e2e/private-case.spec.ts',
    'apps/web/e2e/protected-generation.spec.ts',
    'apps/web/src/durableConversation.test.tsx',
    'apps/web/src/durableConversation.tsx',
    'apps/web/src/durableGeneration.test.tsx',
    'apps/web/src/durableGeneration.tsx',
    'apps/web/src/privateCases.test.tsx',
    'apps/web/src/privateCases.tsx',
    'apps/web/src/style.css',
}
PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-170-professional-saas-experience-visual-system.json',
    'tests/bootstrap/test_professional_saas_experience_visual_system_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'docs/source-register.json',
}
PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_TASK_SHA256 = 'e6fb9148028b9edcc75039ece3fe7632c6f91fdb2d362190e82b028944b15240'
PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_SOURCE_ID = 'mvp1-professional-saas-experience-visual-system'
PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_SOURCE_SHA256 = 'e3f3dcc0bf39088fc692cdc807190741c154bf562b3f83b5f7de6fab70eb2057'
PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_REGISTRATION_BRANCH = 'agent/APBRA-DEVOPS/APBRA-170-professional-saas-experience'
BUSINESS_USER_INTELLIGENT_GENERATION_PATHS = {
    'apps/api/.env.example',
    'apps/api/README.md',
    'apps/api/alembic/versions/20260929_05_business_user_intelligent_generation.py',
    'apps/api/src/apbra_api/api.py',
    'apps/api/src/apbra_api/application.py',
    'apps/api/src/apbra_api/config.py',
    'apps/api/src/apbra_api/domain.py',
    'apps/api/src/apbra_api/evidence.py',
    'apps/api/src/apbra_api/generation.py',
    'apps/api/src/apbra_api/model_provider.py',
    'apps/api/src/apbra_api/persistence.py',
    'apps/api/src/apbra_api/reference_material.py',
    'apps/api/src/apbra_api/semantic_bridge.py',
    'apps/api/tests/conftest.py',
    'apps/api/tests/test_api.py',
    'apps/api/tests/test_authorization.py',
    'apps/api/tests/test_cases.py',
    'apps/api/tests/test_conversations.py',
    'apps/api/tests/test_evidence.py',
    'apps/api/tests/test_generation.py',
    'apps/api/tests/test_migrations.py',
    'apps/api/tests/test_model_provider.py',
    'apps/api/tests/test_reference_material.py',
    'apps/api/tests/test_semantic_bridge.py',
    'apps/web/e2e/durable-conversation.spec.ts',
    'apps/web/e2e/private-case.spec.ts',
    'apps/web/e2e/protected-generation.spec.ts',
    'apps/web/playwright.config.ts',
    'apps/web/scripts/generation-bridge.ts',
    'apps/web/scripts/semantic-bridge.ts',
    'apps/web/src/App.test.tsx',
    'apps/web/src/api.test.ts',
    'apps/web/src/api.ts',
    'apps/web/src/clarification.test.ts',
    'apps/web/src/clarification.ts',
    'apps/web/src/confirmedRequirements.test.ts',
    'apps/web/src/confirmedRequirements.ts',
    'apps/web/src/durableConversation.test.tsx',
    'apps/web/src/durableConversation.tsx',
    'apps/web/src/durableGeneration.test.tsx',
    'apps/web/src/durableGeneration.tsx',
    'apps/web/src/foundry.test.ts',
    'apps/web/src/foundry.ts',
    'apps/web/src/genericFoundry.integration.test.ts',
    'apps/web/src/genericPowerBI.test.ts',
    'apps/web/src/genericPowerBI.ts',
    'apps/web/src/guardrail.test.ts',
    'apps/web/src/guardrail.ts',
    'apps/web/src/privateCases.test.tsx',
    'apps/web/src/privateCases.tsx',
    'apps/web/src/reportDesignNormalization.test.ts',
    'apps/web/src/reportDesignNormalization.ts',
    'apps/web/src/style.css',
    'compose.yaml',
}
BUSINESS_USER_INTELLIGENT_GENERATION_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-171-business-user-report-creation-intelligent-generation.json',
    'tests/bootstrap/test_business_user_report_creation_intelligent_generation_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'docs/source-register.json',
}
BUSINESS_USER_INTELLIGENT_GENERATION_TASK_SHA256 = '201e4164efbcf18e778f7152d9d3fd67a25b9232b1816ab6178701678358915f'
BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID = 'mvp1-business-user-report-creation-intelligent-generation'
BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_SHA256 = '40a6422f05e2559bab6df41a0082c94a2b0b086817af9cf3361896ed37796fbd'
BUSINESS_USER_INTELLIGENT_GENERATION_BRANCH = 'agent/APBRA-DEVOPS/APBRA-171-business-user-report-creation-intelligent-generation'
BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_BRANCH = 'agent/APBRA-DEVOPS/APBRA-171-playwright-runtime-governance-amendment'
BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_SOURCE_ID = 'mvp1-business-user-report-creation-intelligent-generation-playwright-runtime-amendment'
BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_SOURCE_SHA256 = 'be91d06e76a58f9f2825a20147de96f511933b13abd8c9861d94c7fc5a24e692'
BUSINESS_USER_INTELLIGENT_GENERATION_COMPILER_FIXTURE_AMENDMENT_BRANCH = 'agent/APBRA-DEVOPS/APBRA-171-app-test-governance-amendment'
BUSINESS_USER_INTELLIGENT_GENERATION_COMPILER_FIXTURE_AMENDMENT_SOURCE_ID = 'mvp1-business-user-report-creation-intelligent-generation-compiler-fixture-amendment'
BUSINESS_USER_INTELLIGENT_GENERATION_COMPILER_FIXTURE_AMENDMENT_SOURCE_SHA256 = '4d72de3bd05a2b532cd0b4c5ecdc13926b5e4ca17caeccbc7aa6f0341506c949'

MODEL_LED_FLEXIBLE_DELIVERY_PATHS = set('''
AI-RAG-SPEC.md
ARCHITECTURE.md
POWERBI-GENERATION-SPEC.md
README.md
REQUIREMENTS.md
apps/api/.env.example
apps/api/README.md
apps/api/alembic/versions/20261001_06_model_led_clarification_tenant_settings.py
apps/api/src/apbra_api/api.py
apps/api/src/apbra_api/application.py
apps/api/src/apbra_api/authorization.py
apps/api/src/apbra_api/bootstrap.py
apps/api/src/apbra_api/config.py
apps/api/src/apbra_api/domain.py
apps/api/src/apbra_api/generation.py
apps/api/src/apbra_api/model_provider.py
apps/api/src/apbra_api/persistence.py
apps/api/src/apbra_api/semantic_bridge.py
apps/api/src/apbra_api/tenant_secrets.py
apps/api/src/apbra_api/tenant_settings.py
apps/api/tests/conftest.py
apps/api/tests/test_api.py
apps/api/tests/test_authorization.py
apps/api/tests/test_bootstrap.py
apps/api/tests/test_conversations.py
apps/api/tests/test_generation.py
apps/api/tests/test_migrations.py
apps/api/tests/test_model_provider.py
apps/api/tests/test_tenant_secrets.py
apps/api/tests/test_tenant_settings.py
apps/web/README.md
apps/web/e2e/durable-conversation.spec.ts
apps/web/e2e/private-case.spec.ts
apps/web/e2e/protected-generation.spec.ts
apps/web/e2e/tenant-settings.spec.ts
apps/web/playwright.config.ts
apps/web/scripts/generation-bridge.ts
apps/web/scripts/semantic-bridge.ts
apps/web/src/App.test.tsx
apps/web/src/App.tsx
apps/web/src/EnterpriseApp.tsx
apps/web/src/api.test.ts
apps/web/src/api.ts
apps/web/src/clarification.test.ts
apps/web/src/clarification.ts
apps/web/src/confirmedRequirements.test.ts
apps/web/src/confirmedRequirements.ts
apps/web/src/deploymentGuide.test.ts
apps/web/src/deploymentGuide.ts
apps/web/src/durableConversation.test.tsx
apps/web/src/durableConversation.tsx
apps/web/src/durableGeneration.test.tsx
apps/web/src/durableGeneration.tsx
apps/web/src/foundry.test.ts
apps/web/src/foundry.ts
apps/web/src/genericFoundry.integration.test.ts
apps/web/src/genericPowerBI.test.ts
apps/web/src/genericPowerBI.ts
apps/web/src/guardrail.test.ts
apps/web/src/guardrail.ts
apps/web/src/reportDesignNormalization.test.ts
apps/web/src/reportDesignNormalization.ts
apps/web/src/style.css
apps/web/src/tenant.test.ts
apps/web/src/tenant.ts
apps/web/vite.config.ts
compose.yaml
'''.split())
MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json',
    'tests/bootstrap/test_model_led_clarification_flexible_generation_delivery_guide_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'tests/bootstrap/test_business_friendly_ux_application_shell_scope.py',
    'tests/bootstrap/test_professional_saas_experience_visual_system_scope.py',
    'tests/bootstrap/test_protected_generation_output_history_scope.py',
    'docs/source-register.json',
}
MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_PATHS = {
    'scripts/check_bootstrap.py',
    'tasks/APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json',
    'tests/bootstrap/test_model_led_clarification_flexible_generation_delivery_guide_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'tests/bootstrap/test_business_friendly_ux_application_shell_scope.py',
    'tests/bootstrap/test_professional_saas_experience_visual_system_scope.py',
    'tests/bootstrap/test_protected_generation_output_history_scope.py',
    'docs/source-register.json',
}
MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_PATHS = {
    '.github/workflows/bootstrap.yml',
    'scripts/check_bootstrap.py',
    'scripts/check_ci_policy.py',
    'tests/bootstrap/test_ci_policy.py',
    'tests/bootstrap/test_durable_conversation_evidence_acceptance_scope.py',
}
MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_REGISTRATION_PATHS = {
    'docs/source-register.json',
    'scripts/check_bootstrap.py',
    'tasks/APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'tests/bootstrap/test_model_led_clarification_flexible_generation_delivery_guide_scope.py',
}
MODEL_LED_FLEXIBLE_DELIVERY_TASK_SHA256 = '2ee6f89d627f6b0cbd87520cc908126af2bf20055aa490d8936db70e72fda8bc'
MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_ID = 'mvp1-model-led-clarification-flexible-generation-delivery-guide'
MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_SHA256 = 'a546483c8784c3192c15d20ad21935f7d3bae421ea76ad3086808fb4bf7f6eb6'
MODEL_LED_FLEXIBLE_DELIVERY_BRANCH = 'agent/APBRA-DEVOPS/APBRA-174-model-led-clarification-flexible-generation-delivery-guide'
MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_BRANCH = MODEL_LED_FLEXIBLE_DELIVERY_BRANCH + '-registration'
MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_BRANCH = 'agent/APBRA-DEVOPS/APBRA-174-vite-proxy-governance-amendment'
MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_SOURCE_ID = 'mvp1-model-led-clarification-flexible-generation-delivery-guide-vite-proxy-amendment'
MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_SOURCE_SHA256 = '2f2c952e3186bbd77f005dfb17a6e5688022f25a987c8c06dc7152955cfaa41d'
MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_REGISTRATION_BRANCH = 'agent/APBRA-DEVOPS/APBRA-174-ci-timeout-capacity-governance-amendment'
MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_BRANCH = 'agent/APBRA-DEVOPS/APBRA-174-ci-timeout-capacity-implementation'
MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_SOURCE_ID = 'mvp1-model-led-clarification-flexible-generation-delivery-guide-ci-capacity-amendment'
MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_SOURCE_SHA256 = '6facc17e3cd2f4b7172d8bd13f3337f03c492b0245887599273dbeeaecee58cf'

DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_PATHS = {
    'README.md', 'ARCHITECTURE.md', 'REQUIREMENTS.md', 'AI-RAG-SPEC.md',
    'POWERBI-GENERATION-SPEC.md', 'MVP-ACCEPTANCE-CRITERIA.md', 'DATA-MODEL.md',
    'apps/web/README.md', 'docs/engineering/codex-handoff.md',
}
DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_PATHS = {
    'docs/source-register.json',
    'tasks/APBRA-175-deployment-portability-entitlement-docs.json',
    'scripts/check_bootstrap.py',
    'tests/bootstrap/test_deployment_portability_entitlement_docs_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
}
DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_TASK_SHA256 = '09d86487fe0a3f964f8a00d8755d77953bc01aa941c17448ff9872070504c13f'
DEPLOYMENT_PORTABILITY_SOURCE_ID = 'apbra-175-deployment-model-control-plane'
DEPLOYMENT_PORTABILITY_SOURCE_SHA256 = '803072216d5bafd192ec3a63e64e4b12b6e06d78ab021c83457e4be331c988d5'
ENTITLEMENT_ARCHITECTURE_SOURCE_ID = 'apbra-175-subscription-entitlement-feature-gating'
ENTITLEMENT_ARCHITECTURE_SOURCE_SHA256 = 'a6c0b507deb0976cd97aac95313d5ecdabc159d0265b11e068fe965a1f9f0b25'
DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_BRANCH = 'agent/APBRA-DEVOPS/APBRA-175-deployment-portability-entitlement-docs'
DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_BRANCH = DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_BRANCH + '-registration'

OWNER_ONBOARDING_IDENTITY_DOCS_PATHS = {
    'README.md', 'ARCHITECTURE.md', 'REQUIREMENTS.md', 'DATA-MODEL.md',
    'MVP-ACCEPTANCE-CRITERIA.md', 'SECURITY.md', 'apps/web/README.md',
    'docs/engineering/codex-handoff.md',
    'docs/decisions/implementation-baseline.md',
}
OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_PATHS = {
    'docs/source-register.json',
    'tasks/APBRA-176-owner-onboarding-identity-docs.json',
    'scripts/check_bootstrap.py',
    'tests/bootstrap/test_owner_onboarding_identity_docs_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'tests/bootstrap/test_deployment_portability_entitlement_docs_scope.py',
}
OWNER_ONBOARDING_IDENTITY_DOCS_TASK_SHA256 = '031f9451dd61d481e64208559f698557aec1e47a221f8826e7ba784da0abb43c'
OWNER_ONBOARDING_IDENTITY_SOURCE_ID = 'apbra-176-owner-onboarding-identity'
OWNER_ONBOARDING_IDENTITY_SOURCE_SHA256 = 'f37ae7cd8abe73321e65c6485b7424f4cbecc93edddefc5a1579d7260838fb59'
OWNER_ONBOARDING_REQUIREMENTS_SOURCE_ID = 'apbra-176-owner-onboarding-requirements'
OWNER_ONBOARDING_REQUIREMENTS_SOURCE_SHA256 = 'a99f810212fad2e6f5715b94c311f724bb2f24686d4eda35aadb185f497dd0bb'
OWNER_ONBOARDING_IDENTITY_DOCS_BRANCH = 'agent/APBRA-DOCS/APBRA-176-owner-onboarding-docs'
OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_BRANCH = OWNER_ONBOARDING_IDENTITY_DOCS_BRANCH + '-registration'

PROVIDER_NEUTRAL_SSO_PATHS = {
    'apps/api/.env.example', 'apps/api/README.md',
    'apps/api/alembic/versions/20261002_07_provider_neutral_sso.py',
    'apps/api/src/apbra_api/api.py', 'apps/api/src/apbra_api/application.py',
    'apps/api/src/apbra_api/auth_boundary.py', 'apps/api/src/apbra_api/authorization.py',
    'apps/api/src/apbra_api/config.py', 'apps/api/src/apbra_api/domain.py',
    'apps/api/src/apbra_api/identity_service.py', 'apps/api/src/apbra_api/oidc_adapter.py',
    'apps/api/src/apbra_api/persistence.py',
    'apps/api/tests/test_authentication.py', 'apps/api/tests/test_authorization.py',
    'apps/api/tests/test_identity_service.py', 'apps/api/tests/test_invitations.py',
    'apps/api/tests/test_migrations.py', 'apps/web/README.md',
    'apps/web/e2e/private-case.spec.ts', 'apps/web/src/api.test.ts',
    'apps/web/src/api.ts', 'apps/web/src/privateCases.test.tsx',
    'apps/web/src/privateCases.tsx', 'apps/web/src/style.css',
}
PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS = {
    'docs/source-register.json', 'tasks/APBRA-172-provider-neutral-sso.json',
    'scripts/check_bootstrap.py', 'tests/bootstrap/test_provider_neutral_sso_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'tests/bootstrap/test_owner_onboarding_identity_docs_scope.py',
    'tests/bootstrap/test_deployment_portability_entitlement_docs_scope.py',
}
PROVIDER_NEUTRAL_SSO_TASK_SHA256 = '8edb604b7e9a33c3a7249a71a17b50e8578ad86cf00139f2a9bdfedc9f07a210'
PROVIDER_NEUTRAL_SSO_SOURCES = (
    ('apbra-172-identity-rbac', '4030847', 4, 'a0360420eda28492d9cacfba0c5617a4bfd884034e9397c5de984edf4e1eed00'),
    ('apbra-172-data-integration-identity-audit', '4063348', 4, 'cb3c6716e6784717f5d578614179c257b75364b0087a9f3ca359d20a6a9ccea9'),
    ('apbra-172-business-functional-requirements', '3932362', 7, 'aa7b6f22711923856d302cd9751baff6a508f9031bced9f0c56585400242232b'),
    ('apbra-172-multi-tenancy-isolation', '4063408', 5, '5bdeb6e7532139b3759a80bf9e23462b8f8c3e8bc0f0d1b88dbf8ce72f37b0e1'),
    ('apbra-172-platform-identity-deployment-adrs', '3932483', 4, '81601b05483ced7d44add3cdea5791f6294c7aa5ece0430b249f000a87bf1a8f'),
)
PROVIDER_NEUTRAL_SSO_BRANCH = 'agent/APBRA-DEVOPS/APBRA-172-provider-neutral-sso'
PROVIDER_NEUTRAL_SSO_REGISTRATION_BRANCH = PROVIDER_NEUTRAL_SSO_BRANCH + '-registration'

COMPANY_LIFECYCLE_PATHS = {
    'apps/api/README.md',
    'apps/api/alembic/versions/20261003_08_company_lifecycle.py',
    'apps/api/src/apbra_api/api.py', 'apps/api/src/apbra_api/application.py',
    'apps/api/src/apbra_api/bootstrap.py', 'apps/api/src/apbra_api/domain.py',
    'apps/api/src/apbra_api/persistence.py', 'apps/api/src/apbra_api/tenant_settings.py',
    'apps/api/tests/test_bootstrap.py', 'apps/api/tests/test_company_lifecycle.py',
    'apps/api/tests/test_invitations.py',
    'apps/api/tests/test_migrations.py', 'apps/api/tests/test_tenant_settings.py',
    'apps/web/README.md', 'apps/web/e2e/private-case.spec.ts',
    'apps/web/src/api.ts', 'apps/web/src/api.test.ts',
    'apps/web/src/privateCases.tsx', 'apps/web/src/privateCases.test.tsx',
    'apps/web/src/style.css', 'apps/web/vite.config.ts',
}
COMPANY_LIFECYCLE_REGISTRATION_PATHS = {
    'docs/source-register.json', 'tasks/APBRA-151-company-lifecycle.json',
    'scripts/check_bootstrap.py', 'tests/bootstrap/test_company_lifecycle_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'tests/bootstrap/test_provider_neutral_sso_scope.py',
    'tests/bootstrap/test_owner_onboarding_identity_docs_scope.py',
    'tests/bootstrap/test_deployment_portability_entitlement_docs_scope.py',
}
COMPANY_LIFECYCLE_TASK_SHA256 = '0aac6448de867336932cb2d8dc41dcb79be79d166f98e197e0c14aa501311f97'
COMPANY_LIFECYCLE_INITIAL_SETTINGS_GATE_SHA256 = {
    'requirements': '7168bb73f3b6a3b45f0601810a3c31a7727f46232a019569e6a279af09841e79',
    'acceptance_criteria': '652f822a5e779df287dacc81b40f46c78d28aa859bae00b51feacd912385bd95',
    'dependencies': 'b71fe925da09413cead97beb99533d019d1f2544c2b39fb3d89d6507114ff630',
    'escalate_when': 'c429b700a5b92b57852de4a32622ef8bc5d5a6092974fa8a91aa93d8df48dfbc',
}
COMPANY_LIFECYCLE_AMENDMENT_GATE_SHA256 = {
    'verification_required': '37d0265303bfaeca483ebd5bdf8ffa9c883f8268ff15aef638b2aefdf13a1407',
    'dependencies': '92e34110071c7cd3deeb2eda633da846e6b96fbab7ff9814a94168f0bf08fec5',
}
COMPANY_LIFECYCLE_INVITATION_TEST_AMENDMENT_GATE_SHA256 = {
    'verification_required': '0126b2fab3962f85061f9c31483e9f9fbfba2ea90f35ecc142c7ce529bed26c9',
    'dependencies': 'ef61b89278b2a1e3dc9a7c021156aec094a673cae4206e7d90fc8e9a097820db',
}
COMPANY_LIFECYCLE_SOURCES = (
    ('apbra-151-mvp-scope', '4063307', 6, '8702d2eac2bd58320719074b13b8584ced35c61d6c7ea93573e373a6c9bfb166'),
    ('apbra-151-business-functional-requirements', '3932362', 8, '002f6d7243680ea72dc0885883bc93ff9efd979a5a4e603f7eacbc5187340aef'),
    ('apbra-151-data-identity-audit', '4063348', 5, 'ce65429bcb00e2421f05f8909d95d1813909ac4d72066fcf224b01336cc3d5b1'),
    ('apbra-151-self-service-direction', '8519682', 12, '7533cb4e801480cd7cb40c41c5c36733f8f2ff16fd2d227199d42eae6845ee4e'),
    ('apbra-151-multi-tenancy-isolation', '4063408', 5, '5a614a1f802d306f766d28b3a98c81c39c11a169759f7ec6e834c583fdd2f1ec'),
    ('apbra-151-platform-identity-adrs', '3932483', 4, '69ec3923199b0d0f9b0796002ce2897ef20ddd5b8d9154d19f7a4564b2241ec3'),
    ('apbra-151-identity-rbac', '4030847', 5, '57c91915719f98df0cdfd7d5d2aca8c463ea89dbaf9808b3791c258c27c3c7b0'),
)
COMPANY_LIFECYCLE_BRANCH = 'agent/APBRA-DEVOPS/APBRA-151-company-lifecycle'
COMPANY_LIFECYCLE_REGISTRATION_BRANCH = COMPANY_LIFECYCLE_BRANCH + '-registration'
COMPANY_LIFECYCLE_AMENDMENT_BRANCH = 'agent/APBRA-DEVOPS/APBRA-151-vite-authority-amendment'
COMPANY_LIFECYCLE_AMENDMENT_PATHS = {
    'tasks/APBRA-151-company-lifecycle.json',
    'scripts/check_bootstrap.py',
    'tests/bootstrap/test_company_lifecycle_scope.py',
}
COMPANY_LIFECYCLE_INVITATION_TEST_AMENDMENT_BRANCH = 'agent/APBRA-DEVOPS/APBRA-151-invitation-test-authority-amendment'
COMPANY_LIFECYCLE_INVITATION_TEST_AMENDMENT_PATHS = COMPANY_LIFECYCLE_AMENDMENT_PATHS

CANDIDATE_SOURCE_SAFETY_PATHS = {'apps/web/src/genericPowerBI.test.ts', 'apps/web/src/genericPowerBI.ts', 'apps/api/tests/test_generation.py'}
CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS = {
    'docs/source-register.json',
    'tasks/APBRA-108-candidate-source-safety.json',
    'scripts/check_bootstrap.py',
    'tests/bootstrap/test_candidate_source_safety_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
}
CANDIDATE_SOURCE_SAFETY_TASK_SHA256 = 'e4b2bf150019db34f848a9e94105ac9497a71ee67694348dffe8f3ad0ce17b46'
CANDIDATE_SOURCE_SAFETY_SOURCES = (('apbra-108-pbip-pbir-structure', '3965362', 3, '3dfd8a68066547944885370e7091c0605b6db155c171b74bedbe0b181f78b2d2'), ('apbra-108-connections-source-boundary', '4063608', 3, 'c517844c225c801e8a6653a02fa334ce0e925a0915bfdee47ce5036f4034f9d5'), ('apbra-108-candidate-validation', '4063628', 4, 'ec89a4c144e52de5bf0ee122cf630005a3a57c51de71b14a893b97cfb57c1efe'))
CANDIDATE_SOURCE_SAFETY_GATE_SHA256 = {'requirements': '4f5ddef9ea03936295604fe8eff1d49a5464315ad3296bda0ecc6db6a09da8c0', 'acceptance_criteria': '1b9e5046c9f168a5edb8dcedbc5b611503346ecfe054155ca3905ac01b0092af', 'verification_required': '5c81450d1198062a55a8a7a93273b4c7f70274af3add4bcd0ad4f168dba11623', 'dependencies': '19890e30139c836c46452801cb7af7b3947a095d34700476886eb143d2cb3feb'}
CANDIDATE_SOURCE_SAFETY_BRANCH = 'agent/APBRA-DEVOPS/APBRA-108-candidate-source-safety'
CANDIDATE_SOURCE_SAFETY_REGISTRATION_BRANCH = CANDIDATE_SOURCE_SAFETY_BRANCH + '-registration'

PRIVATE_CONTENT_STORAGE_PATHS = {
    'apps/api/README.md',
    'apps/api/src/apbra_api/content_storage.py',
    'apps/api/src/apbra_api/evidence.py',
    'apps/api/src/apbra_api/artifacts.py',
    'apps/api/src/apbra_api/reference_material.py',
    'apps/api/src/apbra_api/application.py',
    'apps/api/src/apbra_api/generation.py',
    'apps/api/src/apbra_api/api.py',
    'apps/api/tests/test_content_storage.py',
    'apps/api/tests/test_evidence.py',
    'apps/api/tests/test_artifacts.py',
    'apps/api/tests/test_reference_material.py',
    'apps/api/tests/test_generation.py',
}
PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS = {
    'docs/source-register.json',
    'tasks/APBRA-173-private-content-storage.json',
    'scripts/check_bootstrap.py',
    'tests/bootstrap/test_private_content_storage_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
    'tests/bootstrap/test_company_lifecycle_scope.py',
    'tests/bootstrap/test_deployment_portability_entitlement_docs_scope.py',
    'tests/bootstrap/test_owner_onboarding_identity_docs_scope.py',
    'tests/bootstrap/test_provider_neutral_sso_scope.py',
}
PRIVATE_CONTENT_STORAGE_TASK_SHA256 = '7f42a825c59e29f6e29bd4c3f1b24115dd27fd80b670433be45f3751a8c15d72'
PRIVATE_CONTENT_STORAGE_HISTORICAL_TEST_SHA256 = {
    'tests/bootstrap/test_company_lifecycle_scope.py': '96d16ce98256a66cacc35d830731fe4598d493d74a4a75352e1b69053b265b6e',
    'tests/bootstrap/test_deployment_portability_entitlement_docs_scope.py': '258b837f7de4c124bc9de90eafbaac9f61f76cfb943649765d3cd1ea0205aab4',
    'tests/bootstrap/test_owner_onboarding_identity_docs_scope.py': '816a6c530f73918663b48b4a361f007c245b02d22034ade11421f9432d7ec6a1',
    'tests/bootstrap/test_provider_neutral_sso_scope.py': '05551d3e13ef3358249c9c7b7d5a995878d15db9fedd513f6d510364e2e1d2ea',
}
PRIVATE_CONTENT_STORAGE_HISTORICAL_SOURCE_COUNT = 53
PRIVATE_CONTENT_STORAGE_HISTORICAL_SOURCES_SHA256 = '09ff501f7956cc6945dc285d0eaface788b530312212447b690f3482118ec8be'
PRIVATE_CONTENT_STORAGE_SOURCES = (
    ('apbra-173a-self-service-hosted-preview', '8519682', 18, 'f27aff74da373a75991b0cc3745f5d38a692aa00323d6e3cfecfbd1ebd9f6153'),
    ('apbra-173a-deployment-portability', '9568258', 2, '35af4064b38c2aea645cba33b5533cb76a18601b5858c0115f223a5bcd11acc6'),
    ('apbra-173a-entitlement-separation', '9535525', 2, 'b441ac7175311d0a83c18bdc57b7f0869dd0c94d85f5e405955e5c029daddefd'),
    ('apbra-173a-data-integrity', '4063348', 6, 'bef3d94e8eb6a8743fd4e015205b62360e46834d700175783d07423f06e4050c'),
    ('apbra-173a-mvp-scope', '4063307', 9, 'd39334d670c024feb8f4e608dc008a2d89a69288e53f831fc02c59055618245b'),
    ('apbra-173a-owner-reference-decision', 'APBRA-173', 'Jira owner comment 10471, 2026-10-04', 'fdc426f778358c07814273c432f689e6de691a754e75997a11a38eaf335c9db8'),
)
PRIVATE_CONTENT_STORAGE_GATE_SHA256 = {
    'adrs': '9a14402c969227774c249adb8b6a1830f5a000fff43a6a1b6e7cb2f2a46c3d33',
    'architecture_refs': 'd6bd87b5bbe2a6ff878ec4ecbd4b7a91423085570d8ac8eee88ce2112a04540a',
    'restricted_paths': 'f9167fc397a38b89184daf286743ae3ef45ec4dad8b95e7e0ca09bd3ab064f30',
    'requirements': 'eae5c7c141786020c6b894bba2b5290031dcfe9887341d541ab8e7f78ff808e6',
    'acceptance_criteria': '52b418c47b6d23163ba9be33a8fc57875f0c10e1b3e291779daa35c18592f0f7',
    'verification_required': 'aa1cd0dbf831302043388db6524133de163954dbae72ec6c859f0ecd019ce524',
    'dependencies': 'b016d9a7b52e9b552da33a3b96437d8062b66722e62ea6a35c81be7bf0f00a4a',
    'out_of_scope': '1bf6bd8ea3af84cef1f5e7fe3434f0492f43c07e6083f3d796223866ed9f4f91',
    'escalate_when': '3fc83a16b22286990df413c25806f046e85cba8e8110704cbc7904d6ea4c3df2',
}
PRIVATE_CONTENT_STORAGE_BRANCH = 'agent/APBRA-DEVOPS/APBRA-173-private-content-storage'
PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH = 'agent/APBRA-DEVOPS/APBRA-173-private-content-storage-registration'

CURRENT_STATE_DOCS_PATHS = {
    'ARCHITECTURE.md',
    'DATA-MODEL.md',
    'MVP-ACCEPTANCE-CRITERIA.md',
    'README.md',
    'REQUIREMENTS.md',
    'SECURITY.md',
    'apps/web/README.md',
    'docs/decisions/implementation-baseline.md',
    'docs/engineering/codex-handoff.md',
}
CURRENT_STATE_DOCS_REGISTRATION_PATHS = {
    'docs/source-register.json',
    'scripts/check_bootstrap.py',
    'tasks/APBRA-177-current-state-docs.json',
    'tests/bootstrap/test_current_state_docs_scope.py',
    'tests/bootstrap/test_invited_private_case_foundation_scope.py',
}
CURRENT_STATE_DOCS_TASK_SHA256 = '987a8bbf4bfec6e8897fc97cdda6c0739c079d481c876f133cb65490d5ca062a'
CURRENT_STATE_DOCS_HISTORICAL_SOURCE_COUNT = 59
CURRENT_STATE_DOCS_HISTORICAL_SOURCES_SHA256 = '2b82ef1b9074116bdf2939b89e7a47dc7ceddc2ca5e17836eaf4c8d8aa9956d5'
CURRENT_STATE_DOCS_SOURCES = (
    ('apbra-177-mvp-scope', '4063307', 12, 'b57a5f862983532c9424893168c9b38b20935d3714d9da0d7cab90c60654f227'),
    ('apbra-177-preview-direction', '8519682', 21, '9ba429a6e15118994f749fffaa2fbdf1209bffc0181dd2a6033e10d0073c10e3'),
    ('apbra-177-deployment-portability', '9568258', 2, 'e06c67fee11d6e0fa6a223c193f0087944aed092214d4e85c92ce28e0656eb4c'),
    ('apbra-177-identity-rbac', '4030847', 7, '72b866668380680da72719d6cd0bfca176c2066988c95dd56069aa61054e3285'),
    ('apbra-177-entitlement-boundary', '9535525', 2, '5a7f0592d93de23f5ed2c658e25086071bc40f411a83725ac581619a16302e96'),
    ('apbra-177-data-identity', '4063348', 6, '6162d535670ac8b1cb096f1c7062fdf96441d32638103253790ffa70f25daadd'),
    ('apbra-177-owner-doc-clarification', 'APBRA-177', 'Jira owner clarification and controller comment 10481, 2026-10-04', 'dfbc6ba8b83043f24ce9cbdb3b17e609e6dfd611c771c7f98ba2977264f54a48'),
)
CURRENT_STATE_DOCS_GATE_SHA256 = {
    'requirements': 'ae5397a3b7afd81a9a82bd1f8799a263f0b49d30733c883edcf46a89f4d67c22',
    'adrs': '07ad29ec27339ad19f83e47665e71e26ee82447fc9ecd83d2912473c8d90c318',
    'architecture_refs': 'ebb3dd1f8fc3fc8f6e05b2dde0a1cd4b158d0d8d80ef1e12eea5fc88d15c4428',
    'restricted_paths': '34515f1a6ec9922b5544ff0d479b18f14351c1fe892fbd3ceb89569bf05e553e',
    'acceptance_criteria': '56565fb2e88808ec297159f13a666f917dfb921a8095f7bea11179e71003f0f9',
    'verification_required': '00ec41d44c8174a6650758873d56fc8334b3718cae8effef0c742d813854c631',
    'out_of_scope': 'ba7a46e4db326a255fe0c5263204f9c315bb64603c36f8c83f7e6a9efb6bfa4c',
    'escalate_when': 'b122afb2b22af125609b2bf95092a2963dc21080b6c3a536e8abca7dc70fa13c',
    'dependencies': '9c565dd2de061b8cb5cc13341268d5eb5cd615d85e391a7d0166f57529a2df74',
}
CURRENT_STATE_DOCS_BRANCH = 'agent/APBRA-DOCS/APBRA-177-current-state-docs'
CURRENT_STATE_DOCS_REGISTRATION_BRANCH = CURRENT_STATE_DOCS_BRANCH + '-registration'

HOSTED_WEB_RELEASE_PATHS = {
    'apps/api/Dockerfile',
    'apps/api/Dockerfile.dockerignore',
    'apps/api/src/apbra_api/api.py',
    'apps/api/src/apbra_api/web_static.py',
    'apps/api/alembic/env.py',
    'apps/api/tests/test_hosted_web.py',
    'apps/api/tests/test_migrations.py',
    'apps/api/README.md',
    '.github/workflows/bootstrap.yml',
    'scripts/check_ci_policy.py',
    'scripts/check_bootstrap.py',
    'tests/bootstrap/test_ci_policy.py',
    'scripts/smoke_hosted_image.sh',
}
HOSTED_WEB_RELEASE_REGISTRATION_PATHS = {
    'docs/source-register.json',
    'scripts/check_bootstrap.py',
    'tasks/APBRA-173-production-web-release.json',
    'tests/bootstrap/test_hosted_web_release_scope.py',
    'tests/bootstrap/test_current_state_docs_scope.py',
}
HOSTED_WEB_RELEASE_TASK_SHA256 = 'fcf8ffdd388616c27fdf42f3687801df86ccd4f373d3c02b429608460aea2d57'
HOSTED_WEB_RELEASE_HISTORICAL_SOURCE_COUNT = 66
HOSTED_WEB_RELEASE_HISTORICAL_SOURCES_SHA256 = '634e0fc2ab98cf546f93cbae5382d80f5d7f724b9589b4c812606cb702d6b17f'
HOSTED_WEB_RELEASE_SOURCES = (
    ('apbra-173b-preview-direction', '8519682', 23, '8cfc9afefd415ebf632222847183f33b8ac5a364c9cb78d3d8d15957acda10fd'),
    ('apbra-173b-mvp-scope', '4063307', 14, '3f3ff070494b5f529107cdd46562f4fb8276bffbeab53c5598bd13e6c763c633'),
    ('apbra-173b-deployment-portability', '9568258', 2, 'e77c9ce09f9a6b76d36670e6452e289461d86162d019e6d132d280cafcab4d79'),
    ('apbra-173b-entitlement-boundary', '9535525', 2, '08b8d7b79af6c28f1e944ce61cb61e0ba76044beff7f158a0ea7d0c74614e593'),
    ('apbra-173b-data-identity', '4063348', 6, 'b8a8d4773c5d65d24822e3eba1a9ce29ddb37b301bd0726b2d7ffefcb0127ce3'),
    ('apbra-173b-traceability', '3932382', 18, '52e655a7622d425fbc16a0dae6cad0a84c2a3155eba18e6bd6e200fc2d1409d6'),
    ('apbra-173b-reconciliation', '6422580', 62, '5e1e2d49bf682bdb4f44b22a6bb86fec3b1da5cf0d83d495ef999b72abd4fd69'),
    ('apbra-173b-owner-architecture-acceptance', 'APBRA-173', 'Haseeb owner acceptance recorded in APBRA-173 comment 10526, 2026-10-05T15:25:40+1100', 'f2d6f13c02d0661bfd9bcd75ff53e914209cdd7ecc3df593e4ec2dd6085ee58e'),
)
HOSTED_WEB_RELEASE_GATE_SHA256 = {
    'requirements': '09106aa3f2dc3ea4988c6503b2c6ebfd1346a0ad03e5606e5a9401682755ca30',
    'adrs': 'e3858784981e8d32b2b91a16e29f7a13c39a4d7fd65cbb439a1a014e09cdd650',
    'architecture_refs': '9a9c7edc7d0f24ffcf3d1f5500ad9d7c3fc5ca291ba72686678618c7ae28901f',
    'restricted_paths': 'cad1e754c16c18eb51b61061d557b25b9f773eb02a864f494f70c8b86eaac672',
    'acceptance_criteria': 'b399709da52a49a49069897418f05db37028ab003bfd5f715c85df993acd5d2e',
    'verification_required': 'ec602d07d7e6d72d2bc84f716026eec8ad71cb39176b8ab5ad3a9396bfe82356',
    'out_of_scope': '052afe99bea1bdb45f2ac3a0fee686b6860deea70c0f170f7f772bb1f43cd512',
    'escalate_when': '4cb73fd5d33851eea58cbc6b61a5aa9380ecfa2461b5c3cc790fd9b66cc7cb81',
    'dependencies': '6e33e5167238ee9fe43c66c6ec4b8de2ad89888caa36c1d11feb7c237cbd59b1',
}
HOSTED_WEB_RELEASE_BRANCH = 'agent/APBRA-DEVOPS/APBRA-173-production-web-release'
HOSTED_WEB_RELEASE_REGISTRATION_BRANCH = HOSTED_WEB_RELEASE_BRANCH + '-registration'

FOUNDRY_SCHEMA_PATHS = {
    'apps/api/src/apbra_api/application.py',
    'apps/api/src/apbra_api/model_provider.py',
    'apps/api/src/apbra_api/generation.py',
    'apps/api/tests/test_conversations.py',
    'apps/api/tests/test_model_provider.py',
    'apps/api/tests/test_generation.py',
    'apps/api/tests/test_semantic_bridge.py',
    'apps/web/scripts/semantic-bridge.ts',
    'apps/web/scripts/generation-bridge.ts',
    'apps/web/src/clarification.ts',
    'apps/web/src/clarification.test.ts',
    'apps/web/src/confirmedRequirements.ts',
    'apps/web/src/confirmedRequirements.test.ts',
    'apps/web/src/foundry.ts',
    'apps/web/src/foundry.test.ts',
    'apps/web/src/guardrail.ts',
    'apps/web/src/guardrail.test.ts',
    'apps/web/src/genericPowerBI.test.ts',
    'apps/web/src/durableConversation.tsx',
    'apps/web/src/durableConversation.test.tsx',
    'apps/web/src/durableGeneration.tsx',
    'apps/web/src/durableGeneration.test.tsx',
    'apps/web/src/deploymentGuide.ts',
    'apps/web/src/deploymentGuide.test.ts',
    'apps/web/e2e/durable-conversation.spec.ts',
    'apps/web/e2e/protected-generation.spec.ts',
}
FOUNDRY_SCHEMA_REGISTRATION_PATHS = {
    'docs/source-register.json',
    'tasks/APBRA-160-foundry-structured-output.json',
    'scripts/check_bootstrap.py',
    'tests/bootstrap/test_foundry_schema_scope.py',
    'tests/bootstrap/test_current_demo_source_alignment_scope.py',
}
FOUNDRY_SCHEMA_TASK_SHA256 = '88a9577c08461a274f04c7a64c920e032f0c07e5b3baffdfa5ea63aa3318857d'
FOUNDRY_SCHEMA_SOURCES = (
    ('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'),
    ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9'),
)
FOUNDRY_SCHEMA_GATE_SHA256 = {
    'requirements': '843a56bc013e1c0db367b0d6c9f118e6ebbe5d51c03a1931fad930059d963b2f',
    'adrs': '2c7a575cc35488c6e1cd10aeeef41575646c26bc9804e8b446d779c09360fd25',
    'architecture_refs': '756a3adacb850a15bf297617b552e39af2fc630599f900a580d70d437cff8c13',
    'restricted_paths': '5da9a2143668174dc898d0ed884c32c49b587a0524bf2c37bc7ae53e0ccf2fbe',
    'acceptance_criteria': '24df1f8b274ff60bfe8d4a202ceffa1de766e1a00dfe357e811192e4c99c2e97',
    'verification_required': '3e0d547686d5b640d8f207673e3017e8426874607eab3a1ce96af58c8d78582f',
    'out_of_scope': 'd84f2cd70d79358d10e16173234e3f8e5cd9623c4ab2a6dd9432e6a1b27efa29',
    'escalate_when': '434388f945c93c78a0d41534cecf18808d2953a46ca78c1d15d0306007d80ba1',
    'dependencies': '1221beb8ab123577609b619662c9483b192cf0ce44d5da6de61eca5b2af55ded',
}

PROVIDER_RETRIEVAL_PATHS = {'apps/api/src/apbra_api/config.py', 'apps/web/src/durableConversation.tsx', 'apps/web/scripts/generation-bridge.ts', 'apps/web/scripts/semantic-bridge.ts', 'apps/web/src/deploymentGuide.test.ts', 'apps/web/src/deploymentGuide.ts', 'apps/api/src/apbra_api/model_provider.py', 'apps/web/src/privateCases.test.tsx', 'apps/web/src/durableGeneration.tsx', 'apps/web/src/api.test.ts', 'apps/api/src/apbra_api/generation.py', 'apps/web/src/durableGeneration.test.tsx', 'apps/api/tests/test_model_provider.py', 'apps/web/src/foundry.ts', 'apps/api/tests/test_conversations.py', 'apps/web/e2e/protected-generation.spec.ts', 'apps/web/src/api.ts', 'apps/api/src/apbra_api/tenant_settings.py', 'apps/web/src/foundry.test.ts', 'apps/web/src/durableConversation.test.tsx', 'apps/api/tests/test_generation.py', 'apps/web/src/EnterpriseApp.tsx', 'apps/api/src/apbra_api/api.py', 'apps/web/e2e/tenant-settings.spec.ts', 'apps/api/tests/test_tenant_settings.py', 'apps/api/tests/test_semantic_bridge.py', 'apps/web/e2e/durable-conversation.spec.ts', 'apps/api/src/apbra_api/application.py', 'apps/api/tests/test_api.py'}
PROVIDER_RETRIEVAL_REGISTRATION_PATHS = {'tasks/APBRA-160-provider-retrieval.json', 'scripts/check_bootstrap.py', 'tests/bootstrap/test_provider_retrieval_scope.py'}
PROVIDER_RETRIEVAL_BRANCH = 'agent/APBRA-DEVOPS/APBRA-160-provider-retrieval'
PROVIDER_RETRIEVAL_REGISTRATION_BRANCH = 'agent/APBRA-DEVOPS/APBRA-160-provider-retrieval-registration'
PROVIDER_RETRIEVAL_TASK_SHA256 = '78522272fdd8c20c0ce184eec2a22122397e2e49edb3f9fc6a79655ff2338cf2'
PROVIDER_RETRIEVAL_GATE_SHA256 = {'requirements': '323309c11b31b810b31a895c46a1e15a8a948186ebfc5384277bfaa57748625c', 'adrs': 'ebf931961a3783807a614f29ea4be730c3664d0b147cac18d364125cdc631edf', 'architecture_refs': '35c08977912347960b51fc6b7f33ecfc186dd341dc7c864cf802389d9037cfe7', 'restricted_paths': '14419d236e945cea71dc8999014ad50d01d6c5a44a23718612b7f63766481bc7', 'acceptance_criteria': 'dbcb7e2efde54d5d219cdb438011baaf21d6a388dee2e236d53b56f2ba51d9f2', 'verification_required': 'c371ba3f93fe70d9e4aebc8dc0964e98cd0f28e26303a9864e89b1b7e2bf33d0', 'out_of_scope': '23bba94e16b368800cf68b86547a49527a4ef26076aff2067fa1c199b2191f84', 'escalate_when': 'b97ea55133cba8dd8abae0eaa5be205ee1c37aebe52df37b69e99e4137f35375', 'dependencies': 'd05be20dfc2167a0b399ad6a101dc0c91d50095ca546a4f09d797a892d234a66', 'effective_release': '6385f7bf58136115858f87c4dd65c7e39aaf1d225f3cfb3092e8eeb818cbc5cd', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
PROVIDER_RETRIEVAL_SOURCES = FOUNDRY_SCHEMA_SOURCES
PROVIDER_RETRIEVAL_ALL_SOURCES_SHA256 = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'

FOUNDRY_HOST_PATHS = {'apps/api/tests/test_model_provider.py', 'apps/api/pyproject.toml', 'apps/api/src/apbra_api/model_provider.py', 'apps/api/src/apbra_api/main.py', 'apps/api/uv.lock', 'apps/api/src/apbra_api/config.py'}
FOUNDRY_HOST_REGISTRATION_PATHS = {'tasks/APBRA-160-foundry-host.json', 'scripts/check_bootstrap.py', 'tests/bootstrap/test_foundry_host_scope.py'}
FOUNDRY_HOST_BRANCH = 'agent/APBRA-DEVOPS/APBRA-160-foundry-host'
FOUNDRY_HOST_REGISTRATION_BRANCH = 'agent/APBRA-DEVOPS/APBRA-160-foundry-host-registration'
FOUNDRY_HOST_TASK_SHA256 = '8c2df5654d5fac6d929800881d39b54f809be5164c5bf0342328942c89aa4f93'
FOUNDRY_HOST_GATE_SHA256 = {'requirements': '6c28746ffdbda24034f5d4ddcb645f80001e1ff048862fde8ef2e89dd700ff6a', 'adrs': '8d96bab63ecbd37614f9707a709fb9cc0376df4f257b26f1417418b6b80bddad', 'architecture_refs': '3b432bb91142e2f748282a601cd5972d8a236dea6c533f44d2efac7a600043a0', 'restricted_paths': 'be5f05d658cdefb103541b20782fd9634ffa4beb159c2ae0e9757a72bf2ae029', 'acceptance_criteria': 'e25e323fb28f2121e76f798b205a33fa7d56d50b6744a98fb5bad57531aaf848', 'verification_required': 'd071446ffde2a22023dcf474b854d4f7310c3cc066b4f56f39fd4fbe5a7b8257', 'out_of_scope': '9c97c2304236a6db9e19c2c8ed0d48e6453557fe1fa0490e160c251499f03eba', 'escalate_when': '77375135f94a2a32064a4db36dfe18a0a06d1ffedf610b14eba632b24252634c', 'dependencies': '45d36a6c2adcf36bdb7bb4d2de69bc4717e8a2bb4648d2aa33fa5c943b844a88', 'effective_release': 'a214863ef9572e831beece9d1562de0cc93d20cd09473638aa500bc5e1905684', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2'}
FOUNDRY_HOST_SOURCES = FOUNDRY_SCHEMA_SOURCES
FOUNDRY_HOST_ALL_SOURCES_SHA256 = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'

LOCAL_RECOVERY_PATHS = {'apps/api/tests/test_rekey_tenant_secrets.py', 'apps/api/src/apbra_api/rekey_tenant_secrets.py', 'apps/api/src/apbra_api/tenant_secrets.py'}
LOCAL_RECOVERY_REGISTRATION_PATHS = {'tasks/APBRA-160-local-rekey.json', 'scripts/check_bootstrap.py', 'tests/bootstrap/test_local_rekey_scope.py'}
LOCAL_RECOVERY_BRANCH = 'agent/APBRA-DEVOPS/APBRA-160-local-rekey'
LOCAL_RECOVERY_REGISTRATION_BRANCH = 'agent/APBRA-DEVOPS/APBRA-160-local-rekey-clean-registration'
LOCAL_RECOVERY_TASK_SHA256 = '63c5ba8add3f1edaf3433460adbd9c9f504f2885bd832535d08aab6197d8b592'
LOCAL_RECOVERY_GATE_SHA256 = {'requirements': '20a8243d2c014b9254f37f124b92062ab475b3f72429e8085e205a3cd900c9a4', 'adrs': 'b2d848dccced5dad02b35ad8823548df93ed6d26f506879e021685628a38ea51', 'architecture_refs': '3c1e5bd1055f7f60c3248686b7650b2cc39d04c5b7abe132f786c013fee98fb1', 'restricted_paths': 'e515ba02be97593fc54eef10b9284355cb36c792a827638bd1329f93b9f53b46', 'acceptance_criteria': '90d4190ce08546aada6bd478143e171efef9bd67a602b6678976d5ac606ee007', 'verification_required': 'a801e044ceaeb0e74b16035bea0d12306b692cef4a04df525a1a65f326aaa526', 'out_of_scope': '030b4ac42d4a4d59c5eb1ffcaa39c0a8e98bd70cc84d3c03e01cbb8be89e8777', 'escalate_when': '957e029f91dfe88d547fa550fd2a23a3f819f19aa4ac4760896232a3f45c745f', 'dependencies': 'a7ca3f13676c6e1427db2f2b5df9d42965e8458788ff111b22079542a9faf426', 'effective_release': '03fd13e33a9671b7647526a1f06d57fe10f5376cdb75d8e6d06402b0c215cf30', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': '7a1a4b216859154f70d8b3aa0d18b1c679ab8965bd42b97e217b11b385925890', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
LOCAL_RECOVERY_SOURCE_SHA256 = 'a546483c8784c3192c15d20ad21935f7d3bae421ea76ad3086808fb4bf7f6eb6'
LOCAL_RECOVERY_ALL_SOURCES_SHA256 = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'

FOUNDRY_SCHEMA_BRANCH = 'agent/APBRA-DEVOPS/APBRA-160-editable-draft'
FOUNDRY_SCHEMA_REGISTRATION_BRANCH = 'agent/APBRA-DEVOPS/APBRA-160-editable-draft-registration'

DEMO_UX_PATHS = {
    'apps/api/src/apbra_api/api.py',
    'apps/api/src/apbra_api/tenant_settings.py',
    'apps/api/tests/test_tenant_settings.py',
    'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/api.ts',
    'apps/web/src/api.test.ts',
    'apps/web/src/privateCases.tsx',
    'apps/web/src/privateCases.test.tsx',
    'apps/web/src/durableConversation.tsx',
    'apps/web/src/durableConversation.test.tsx',
    'apps/web/src/durableGeneration.tsx',
    'apps/web/src/durableGeneration.test.tsx',
    'apps/web/src/style.css',
    'apps/web/e2e/private-case.spec.ts',
    'apps/web/e2e/tenant-settings.spec.ts',
    'apps/web/e2e/durable-conversation.spec.ts',
    'apps/web/e2e/protected-generation.spec.ts',
    'apps/web/vite.config.ts',
}
DEMO_UX_REGISTRATION_PATHS = {
    'tasks/APBRA-160-demo-ux.json',
    'scripts/check_bootstrap.py',
    'tests/bootstrap/test_demo_ux_scope.py',
}
DEMO_UX_TASK_SHA256 = '306263b7dd0b3f6194f826b7accfd00af993863fc922c2bb236de492337f025a'
DEMO_UX_SOURCES = (
    ('apbra-160-current-six-stage-direction', '8519682', 26, '53cb026ea98269dd7bc7dd7b7da67e0c9003557c183c77467ece89a546a50350'),
    ('apbra-160-current-model-led-delivery', '9404417', 7, '59aead56e1a8d3541268dbd09533c7b5803b02a9e7ab7785035c48dec6c9ffb3'),
    ('apbra-160-screen-interactions', '4063368', 5, '3cf12cb56cf804f3720e9215d15af34a57ec553469699cd635af072147296f3f'),
    ('apbra-160-reviewer-administration', '4063388', 6, '05749da8117cf5495cda152d1e2e1eb42a97494533ab5626f1881d583ddb05a1'),
)
DEMO_UX_GATE_SHA256 = {
    'requirements': 'c5a1307d65817fd8e0c391b740df19d7b4842312f0fe78517ec5a447ec102ec5',
    'adrs': '08944297abd884ee5c68f1eeef814a929fa74f33567b06ea9e3a91cc7ad0adb7',
    'architecture_refs': '6ec72c7e222ce482456ada6b43128865470e2864884a322692b5e0c29d80307a',
    'restricted_paths': '3ccd44f8f74a4ef21f15ddb1fcdd45bdb29b5d83e1a79fdf75bd310b0f9fbf29',
    'acceptance_criteria': 'cfb3ba85f7b20cfe3d6f79e24270c763be58e12a3f4e01fc4de7b5d6d5f75504',
    'verification_required': '13c9be515b02d85ed50994700e3c10da8f9734ef8cbc3c78d3b78f34369798bc',
    'out_of_scope': '4ecc70a57f25006337e6792ae6d1f500281043c26fd21e35ad94995138503ee5',
    'escalate_when': 'b32a0f51f125326763c2b20fa5c23facb3c5010b1d79afa988cd791ea3358eba',
    'dependencies': '3fb8b59c130f0dde1d08cb116628c4211374a1684c1a941a6b861533960519cf',
}
DEMO_UX_BRANCH = 'agent/APBRA-DEVOPS/APBRA-160-demo-ux'
DEMO_UX_REGISTRATION_BRANCH = 'agent/APBRA-DEVOPS/APBRA-160-demo-ux-registration'
DEMO_UX_VITE_ORIGINAL_SHA256 = 'dac004933ad7814f66e4ebaa2116867e151b396f60ef5d80d0a88bd786a8a320'
DEMO_UX_VITE_PROXY_SHA256 = '9f0ec6501192d146afdea639aa0482cb836b6f2a6daf4dc333392dab606b319f'

# A separate, source-only APBRA-160 amendment. Historical APBRA-173B rows
# remain bound to their original packaging authority.
CURRENT_DEMO_SOURCE_BRANCH = 'agent/APBRA-DEVOPS/APBRA-160-current-source-alignment'
CURRENT_DEMO_SOURCE_PATHS = {
    'docs/source-register.json',
    'scripts/check_bootstrap.py',
    'tests/bootstrap/test_hosted_web_release_scope.py',
    'tests/bootstrap/test_current_demo_source_alignment_scope.py',
}
APBRA160_CI_CAPACITY_BRANCH = 'agent/APBRA-DEVOPS/APBRA-160-bootstrap-ci-capacity'
APBRA160_CI_CAPACITY_PATHS = {
    '.github/workflows/bootstrap.yml',
    'scripts/check_bootstrap.py',
    'scripts/check_ci_policy.py',
    'tests/bootstrap/test_ci_policy.py',
}
CURRENT_DEMO_HISTORICAL_SOURCE_COUNT = 74
CURRENT_DEMO_HISTORICAL_SOURCES_SHA256 = '1f1ecb0729abfc6b76671b621208a6c60370a838f91a67050faa7e3c0b51fa4b'
CURRENT_DEMO_SOURCES = (
    ('apbra-160-current-six-stage-direction', '8519682', 26, '53cb026ea98269dd7bc7dd7b7da67e0c9003557c183c77467ece89a546a50350'),
    ('apbra-160-current-model-led-delivery', '9404417', 7, '59aead56e1a8d3541268dbd09533c7b5803b02a9e7ab7785035c48dec6c9ffb3'),
    ('apbra-160-historical-business-shell', '8388610', 2, 'b44375446b2ce03e03c22136aa0cd74938253a88ab0c27cb7bbac89fc6ea4304'),
    ('apbra-160-conversational-ux-history', '3932422', 8, 'c3eaabbceee9fa5f3f1f4cd18bfb4fe0f6a63a6b447731d920cac35bcbc6174a'),
    ('apbra-160-future-native-platform', '7864321', 2, '10502b3d6cf59134982ec231ed0081aaac7a6c8a1cd070bdd3f969d366494444'),
    ('apbra-160-use-cases-acceptance', '3932402', 5, '3faf1efa272470e3771f72f65d7a47e9d5026e12d31a689c19378f3ac9e644d5'),
    ('apbra-160-screen-interactions', '4063368', 5, '3cf12cb56cf804f3720e9215d15af34a57ec553469699cd635af072147296f3f'),
    ('apbra-160-reviewer-administration', '4063388', 6, '05749da8117cf5495cda152d1e2e1eb42a97494533ab5626f1881d583ddb05a1'),
    ('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'),
    ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9'),
)

CAPSTONE_EVALUATION_PATHS = {
    'apps/web/.env.example', 'apps/web/README.md',
    'apps/web/knowledge/accessibility-standards.md',
    'apps/web/knowledge/corporate-branding.md',
    'apps/web/knowledge/deployment-standards.md',
    'apps/web/knowledge/powerbi-modelling-standards.md',
    'apps/web/knowledge/report-design-standards.md',
    'apps/web/package-lock.json', 'apps/web/package.json',
    'apps/web/scripts/foundry-smoke.mjs', 'apps/web/src/App.test.tsx',
    'apps/web/src/App.tsx', 'apps/web/src/EnterpriseApp.tsx',
    'apps/web/src/archive.ts', 'apps/web/src/foundry.test.ts',
    'apps/web/src/foundry.ts', 'apps/web/src/genericFoundry.integration.test.ts',
    'apps/web/src/genericPowerBI.test.ts', 'apps/web/src/genericPowerBI.ts',
    'apps/web/src/guardrail.test.ts', 'apps/web/src/guardrail.ts',
    'apps/web/src/guardrailPolicy.json', 'apps/web/src/main.tsx',
    'apps/web/src/powerbi.test.ts', 'apps/web/src/powerbi.ts',
    'apps/web/src/rag.test.ts', 'apps/web/src/rag.ts', 'apps/web/src/raw.d.ts',
    'apps/web/src/requirements.test.ts', 'apps/web/src/requirements.ts',
    'apps/web/src/schemaIngestion.test.ts', 'apps/web/src/schemaIngestion.ts',
    'apps/web/src/style.css', 'apps/web/src/tenant.ts',
    'apps/web/src/validationProfile.json', 'apps/web/src/workflow.ts',
    'apps/web/vite.config.ts',
}

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    'README.md', 'AGENTS.md', 'ARCHITECTURE.md', 'REQUIREMENTS.md',
    'DATA-MODEL.md', 'AI-RAG-SPEC.md', 'POWERBI-GENERATION-SPEC.md',
    'MVP-ACCEPTANCE-CRITERIA.md', 'docs/source-register.json',
    'agents/catalog.json', 'tasks/APBRA-85-bootstrap.json',
    'contracts/engineering/task-contract.schema.json',
    'contracts/engineering/agent-catalog.schema.json',
    '.github/CODEOWNERS', '.github/pull_request_template.md',
    '.github/workflows/bootstrap.yml', 'requirements-bootstrap.txt',
    'docs/engineering/repository-controls.md', 'docs/engineering/codex-handoff.md',
    'docs/decisions/implementation-baseline.md', 'tests/bootstrap/test_bootstrap.py',
)
ROLE_IDS = {'APBRA-' + s for s in (
    'PLANNER', 'ARCH', 'DEV-BE', 'DEV-FE', 'AI', 'RAG', 'PBI',
    'QA', 'SEC', 'REVIEW', 'DEVOPS', 'DOCS')}
ACTION_PINS = {
    'actions/setup-node': '249970729cb0ef3589644e2896645e5dc5ba9c38',
    'actions/checkout': 'd23441a48e516b6c34aea4fa41551a30e30af803',
    'actions/setup-python': 'ece7cb06caefa5fff74198d8649806c4678c61a1',
    'actions/upload-artifact': 'ea165f8d65b6e75b540449e92b4886f43607fa02',
}


def load_json(path: Path) -> object:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)


def valid_path(path: str) -> bool:
    return bool(path) and not any(c in path for c in '\\:\x00\n\r') and (
        not path.startswith('/') and all(p not in ('', '.', '..') for p in path.split('/'))
    )


def matches(path: str, pattern: str) -> bool:
    if not valid_path(path) or not valid_path(pattern):
        return False
    if pattern == '*':
        return True
    if pattern.endswith('/**'):
        return path.startswith(pattern[:-3] + '/')
    if '/' not in pattern and '/' in path:
        return False
    return fnmatch.fnmatchcase(path, pattern)


def path_allowed(path: str, task: dict, card: dict) -> bool:
    restricted = any(matches(path, p) for p in task['restricted_paths'])
    exact_mvp_ci_policy_test = (
        task.get('task_id') in {'APBRA-163', 'APBRA-164'} and
        path == 'tests/bootstrap/test_ci_policy.py' and
        path in task['allowed_paths']
    )
    return valid_path(path) and (not restricted or exact_mvp_ci_policy_test) and (
        any(matches(path, p) for p in task['allowed_paths']) and
        any(matches(path, p) for p in card['allowed_paths'])
    )


def whole_tree_safe(path: str, bootstrap_task: dict,
                    legacy_authorities: tuple[tuple[dict | None, set[str]], ...],
                    bound_authorities: tuple[tuple[dict | None, set[str]], ...],
                    card: dict) -> bool:
    """Preserve legacy coverage; admit newer files through their first bound scope.

    Existing Capstone tasks may independently cover the same legacy file. New
    hash-bound tasks may introduce files outside that legacy scope, but cannot
    rescue a legacy file or a prior bound task's invalid registration.
    """
    if path_allowed(path, bootstrap_task, card):
        return True
    if any(registered is not None and path_allowed(path, registered, card)
           for registered, _ in legacy_authorities):
        return True
    if any(matches(path, pattern) for _, scope in legacy_authorities
           for pattern in scope):
        return False
    for registered, expected_scope in bound_authorities:
        if any(matches(path, pattern) for pattern in expected_scope):
            return registered is not None and path_allowed(path, registered, card)
    return False


def schema_errors(schema: dict, value: object) -> list[str]:
    Draft202012Validator.check_schema(schema)
    # All current engineering schemas are self-contained: no remote resolution.
    def inspect(node):
        if isinstance(node, dict):
            for keyword in ('$ref', '$dynamicRef'):
                if keyword in node and not node[keyword].startswith('#'):
                    raise ValueError('External schema references are forbidden')
            for item in node.values():
                inspect(item)
        elif isinstance(node, list):
            for item in node:
                inspect(item)
    inspect(schema)
    return [str(e.json_path) + ': ' + e.message for e in
            sorted(Draft202012Validator(schema, registry=Registry()).iter_errors(value), key=lambda e: e.json_path)]


def catalog_errors(catalog: dict) -> list[str]:
    errors = []
    ids = [c['agent_id'] for c in catalog['cards']]
    if len(set(ids)) != len(ids) or set(ids) != ROLE_IDS:
        errors.append('Catalog must contain the exact twelve unique logical roles')
    for card in catalog['cards']:
        if any(not valid_path(p) for p in card['allowed_paths']):
            errors.append('Unsafe card scope: ' + card['agent_id'])
        if any(r not in ROLE_IDS | {'HUMAN_OWNER'} for r in card['required_reviews']):
            errors.append('Unknown reviewer role')
    return errors


def task_errors(task: dict, catalog: dict, sources: dict) -> list[str]:
    errors = []
    cards = {c['agent_id']: c for c in catalog['cards']}
    card = cards.get(task['assigned_agent'])
    if card is None:
        return ['Unknown agent role']
    if task['agent_card_version'] != card['card_version']:
        errors.append('Stale agent card version')
    if any(not valid_path(p) for p in task['allowed_paths'] + task['restricted_paths']):
        errors.append('Unsafe task scope')
    if not task['branch'].startswith('agent/' + task['assigned_agent'] + '/' + task['task_id'] + '-'):
        errors.append('Branch must match the agent and Jira task')
    source_map = {s['id']: s for s in sources['sources']}
    if any(s not in source_map for s in task['source_ids']):
        errors.append('Unknown source reference')
    if task['task_mode'] == 'IMPLEMENTATION' or task['readiness'] == 'READY_FOR_IMPLEMENTATION':
        if task['task_mode'] != 'IMPLEMENTATION' or task['readiness'] != 'READY_FOR_IMPLEMENTATION':
            errors.append('Implementation mode/readiness mismatch')
        if task['owner_acceptance'] != 'RECORDED':
            errors.append('Implementation acceptance is not recorded')
        if card['max_autonomy'] != 'A3':
            errors.append('Role cannot perform implementation')
        if any(source_map[s].get('status') not in {'ACCEPTED', 'BASELINED'} for s in task['source_ids'] if s in source_map):
            errors.append('Proposed sources cannot authorize implementation' if any(source_map[s].get('status') == 'PROPOSED' for s in task['source_ids'] if s in source_map) else 'Unaccepted sources cannot authorize implementation')
    if task['task_mode'] == 'SPECIFICATION' and task['readiness'] == 'READY_FOR_SPECIFICATION':
        if task['owner_acceptance'] not in ('BOOTSTRAP_ONLY', 'RECORDED'):
            errors.append('Specification authority missing')
    return errors


def workflow_errors(text: str) -> list[str]:
    errors = []
    try:
        doc = yaml.load(text, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        return ['Invalid workflow YAML']
    if not isinstance(doc, dict):
        return ['Workflow must be a mapping']
    events = doc.get('on', {})
    if not isinstance(events, dict) or set(events) != {'pull_request', 'workflow_dispatch'}:
        errors.append('Bootstrap requires only pull_request and workflow_dispatch events')
    if doc.get('permissions') != {'contents': 'read'}:
        errors.append('Workflow token must be contents-read only')
    jobs = doc.get('jobs', {})
    if set(jobs) != {'bootstrap'}:
        errors.append('Unexpected job: review bootstrap CI scope')
    for job in jobs.values():
        if job.get('runs-on') != 'ubuntu-24.04' or job.get('timeout-minutes') != '45':
            errors.append('Unexpected runner or unbounded job')
        if 'permissions' in job:
            errors.append('Job permission override prohibited')
        for step in job.get('steps', []):
            if 'uses' in step:
                expected = {n + '@' + sha for n, sha in ACTION_PINS.items()}
                if step['uses'] not in expected:
                    errors.append('Action is not in the exact verified pin allow-list')
                if step['uses'].startswith('actions/checkout@') and step.get('with', {}).get('persist-credentials') != 'false':
                    errors.append('Checkout credentials must not persist')
    # Match the secrets context as a token, including bracket notation. The old
    # substring test incorrectly rejected a harmless path such as scan_secrets.sh.
    if re.search(r'\bsecrets\s*(?:\.|\[)', text) or 'pull_request_target' in text:
        errors.append('Privileged trigger/secret reference prohibited')
    return errors


def repo_files(root: Path) -> list[Path]:
    if (root / '.git').exists():
        result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], check=True,
                                capture_output=True, timeout=10)
        return [root / p for p in result.stdout.decode().split('\x00') if p]
    ignored = {'.git', '.venv', '__pycache__', 'artifacts'}
    return sorted(p for p in root.rglob('*') if (p.is_file() or p.is_symlink()) and not ignored.intersection(p.relative_to(root).parts))


def check(root: Path = ROOT, *, active_task_id: str | None = None,
          active_branch: str | None = None,
          changed_paths: set[str] | None = None) -> tuple[list[str], dict]:
    errors = [f'Missing required file: {name}' for name in REQUIRED if not (root / name).is_file()]
    if errors:
        return errors, {}
    try:
        catalog = load_json(root / 'agents/catalog.json')
        task = load_json(root / 'tasks/APBRA-85-bootstrap.json')
        sources = load_json(root / 'docs/source-register.json')
        errors += schema_errors(load_json(root / 'contracts/engineering/agent-catalog.schema.json'), catalog)
        errors += schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), task)
        if errors:
            return errors, {}
        errors += catalog_errors(catalog)
        errors += task_errors(task, catalog, sources)
        current_rows = sources['sources']
        if hashlib.sha256(json.dumps(
            current_rows[:CURRENT_DEMO_HISTORICAL_SOURCE_COUNT],
            sort_keys=True, separators=(',', ':'),
        ).encode()).hexdigest() != CURRENT_DEMO_HISTORICAL_SOURCES_SHA256:
            errors.append('APBRA-160 current-demo historical source provenance changed')
        appended_rows = current_rows[CURRENT_DEMO_HISTORICAL_SOURCE_COUNT:]
        if (len(appended_rows) != len(CURRENT_DEMO_SOURCES) or
                [row.get('id') for row in appended_rows] !=
                [row[0] for row in CURRENT_DEMO_SOURCES]):
            errors.append('APBRA-160 current-demo source block is not exact and append-only')
        for source_id, content_id, version, expected_sha in CURRENT_DEMO_SOURCES:
            matches = [row for row in current_rows if row.get('id') == source_id]
            if len(matches) != 1:
                errors.append('APBRA-160 current-demo source missing or duplicated: ' + source_id)
                continue
            row = matches[0]
            if (row.get('content_id'), row.get('version'), row.get('status')) != (
                content_id, version, 'ACCEPTED',
            ):
                errors.append('APBRA-160 current-demo source binding differs: ' + source_id)
            if hashlib.sha256(json.dumps(
                row, sort_keys=True, separators=(',', ':'),
            ).encode()).hexdigest() != expected_sha:
                errors.append('APBRA-160 current-demo source differs from provenance: ' + source_id)
        workflow_path = root / '.github/workflows/bootstrap.yml'
        workflow_bytes = workflow_path.read_bytes()
        historical_capacity_fixture = (
            active_task_id == 'APBRA-163' and
            active_branch == 'agent/APBRA-DEVOPS/APBRA-163-durable-conversation-evidence-acceptance' and
            changed_paths == DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_CAPACITY_AMENDMENT_PATHS and
            not workflow_path.is_symlink() and
            hashlib.sha256(workflow_bytes).hexdigest() ==
            DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_CAPACITY_WORKFLOW_SHA256
        )
        workflow_text = workflow_bytes.decode('utf-8')
        if historical_capacity_fixture:
            # The original bytes are digest-bound above and again in APBRA-163's
            # scope check below. Validate every other control through the current
            # checker after normalizing only this historical timeout in memory.
            workflow_text = workflow_text.replace('timeout-minutes: 20', 'timeout-minutes: 45', 1)
        errors += workflow_errors(workflow_text)
        card = next(c for c in catalog['cards'] if c['agent_id'] == task['assigned_agent'])
        # Explicitly bounded Capstone extensions, not arbitrary task discovery.
        shell_path = root / 'tasks/APBRA-129-capstone-shell.json'
        shell_task = None
        if shell_path.exists():
            shell_task = load_json(shell_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), shell_task)
            if not extension_errors:
                extension_errors += task_errors(shell_task, catalog, sources)
                if shell_task['task_id'] != 'APBRA-129' or shell_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected Capstone task identity')
                if set(shell_task['allowed_paths']) != CAPSTONE_SHELL_PATHS:
                    extension_errors.append('Unexpected Capstone shell scope')
                if (shell_task['task_mode'], shell_task['readiness'], shell_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Capstone shell requires issued implementation acceptance')
                if shell_task['source_ids'] != ['capstone-web-shell']:
                    extension_errors.append('Capstone shell requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                shell_task = None
        requirements_path = root / 'tasks/APBRA-130-requirements-snapshot.json'
        requirements_task = None
        if requirements_path.exists():
            requirements_task = load_json(requirements_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), requirements_task)
            if not extension_errors:
                extension_errors += task_errors(requirements_task, catalog, sources)
                if requirements_task['task_id'] != 'APBRA-130' or requirements_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected Capstone task identity')
                if set(requirements_task['allowed_paths']) != CAPSTONE_REQUIREMENTS_PATHS:
                    extension_errors.append('Unexpected Capstone requirements scope')
                if (requirements_task['task_mode'], requirements_task['readiness'], requirements_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Capstone requirements requires issued implementation acceptance')
                if requirements_task['source_ids'] != ['capstone-requirements-snapshot']:
                    extension_errors.append('Capstone requirements requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                requirements_task = None
        knowledge_task = None
        knowledge_path = root / 'tasks/APBRA-131-curated-knowledge.json'
        if knowledge_path.exists():
            knowledge_task = load_json(knowledge_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), knowledge_task)
            if not extension_errors:
                extension_errors += task_errors(knowledge_task, catalog, sources)
                if knowledge_task['task_id'] != 'APBRA-131' or knowledge_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected Capstone knowledge identity')
                if set(knowledge_task['allowed_paths']) != CAPSTONE_KNOWLEDGE_PATHS:
                    extension_errors.append('Unexpected Capstone knowledge scope')
                if (knowledge_task['task_mode'], knowledge_task['readiness'], knowledge_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Capstone knowledge requires issued implementation acceptance')
                if knowledge_task['source_ids'] != ['capstone-curated-knowledge']:
                    extension_errors.append('Capstone knowledge requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                knowledge_task = None
        design_task = None
        design_path = root / 'tasks/APBRA-132-design-plan.json'
        if design_path.exists():
            design_task = load_json(design_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), design_task)
            if not extension_errors:
                extension_errors += task_errors(design_task, catalog, sources)
                if design_task['task_id'] != 'APBRA-132' or design_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected Capstone design identity')
                if set(design_task['allowed_paths']) != CAPSTONE_DESIGN_PATHS:
                    extension_errors.append('Unexpected Capstone design scope')
                if (design_task['task_mode'], design_task['readiness'], design_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Capstone design requires issued implementation acceptance')
                if design_task['source_ids'] != ['capstone-design-plan']:
                    extension_errors.append('Capstone design requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                design_task = None
        generation_task = None
        generation_path = root / 'tasks/APBRA-133-powerbi-project.json'
        if generation_path.exists():
            generation_task = load_json(generation_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), generation_task)
            if not extension_errors:
                extension_errors += task_errors(generation_task, catalog, sources)
                if generation_task['task_id'] != 'APBRA-133' or generation_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected Capstone generation identity')
                if set(generation_task['allowed_paths']) != CAPSTONE_GENERATION_PATHS:
                    extension_errors.append('Unexpected Capstone generation scope')
                if (generation_task['task_mode'], generation_task['readiness'], generation_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Capstone generation requires issued implementation acceptance')
                if generation_task['source_ids'] != ['capstone-powerbi-project']:
                    extension_errors.append('Capstone generation requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                generation_task = None
        validation_task = None
        validation_path = root / 'tasks/APBRA-134-validation.json'
        if validation_path.exists():
            validation_task = load_json(validation_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), validation_task)
            if not extension_errors:
                extension_errors += task_errors(validation_task, catalog, sources)
                if validation_task['task_id'] != 'APBRA-134' or validation_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected Capstone validation identity')
                if set(validation_task['allowed_paths']) != CAPSTONE_VALIDATION_PATHS:
                    extension_errors.append('Unexpected Capstone validation scope')
                if (validation_task['task_mode'], validation_task['readiness'], validation_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Capstone validation requires issued implementation acceptance')
                if validation_task['source_ids'] != ['capstone-validation']:
                    extension_errors.append('Capstone validation requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                validation_task = None
        governance_task = None
        governance_path = root / 'tasks/APBRA-135-release.json'
        if governance_path.exists():
            governance_task = load_json(governance_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), governance_task)
            if not extension_errors:
                extension_errors += task_errors(governance_task, catalog, sources)
                if governance_task['task_id'] != 'APBRA-135' or governance_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected Capstone governance identity')
                if set(governance_task['allowed_paths']) != CAPSTONE_GOVERNANCE_PATHS:
                    extension_errors.append('Unexpected Capstone governance scope')
                if (governance_task['task_mode'], governance_task['readiness'], governance_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Capstone governance requires issued implementation acceptance')
                if governance_task['source_ids'] != ['capstone-governance']:
                    extension_errors.append('Capstone governance requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                governance_task = None
        orchestration_task = None
        orchestration_path = root / 'tasks/APBRA-136-orchestration.json'
        if orchestration_path.exists():
            orchestration_task = load_json(orchestration_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), orchestration_task)
            if not extension_errors:
                extension_errors += task_errors(orchestration_task, catalog, sources)
                if orchestration_task['task_id'] != 'APBRA-136' or orchestration_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected Capstone orchestration identity')
                if set(orchestration_task['allowed_paths']) != CAPSTONE_ORCHESTRATION_PATHS:
                    extension_errors.append('Unexpected Capstone orchestration scope')
                if (orchestration_task['task_mode'], orchestration_task['readiness'], orchestration_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Capstone orchestration requires issued implementation acceptance')
                if orchestration_task['source_ids'] != ['capstone-orchestration']:
                    extension_errors.append('Capstone orchestration requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                orchestration_task = None
        evaluation_task = None
        evaluation_path = root / 'tasks/APBRA-92-evaluation.json'
        if evaluation_path.exists():
            evaluation_task = load_json(evaluation_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), evaluation_task)
            if not extension_errors:
                extension_errors += task_errors(evaluation_task, catalog, sources)
                if evaluation_task['task_id'] != 'APBRA-92' or evaluation_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected Capstone evaluation identity')
                if set(evaluation_task['allowed_paths']) != CAPSTONE_EVALUATION_PATHS:
                    extension_errors.append('Unexpected Capstone evaluation scope')
                if (evaluation_task['task_mode'], evaluation_task['readiness'], evaluation_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Capstone evaluation requires issued implementation acceptance')
                if evaluation_task['source_ids'] != ['capstone-evaluation']:
                    extension_errors.append('Capstone evaluation requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                evaluation_task = None
        deployment_guide_task = None
        deployment_guide_path = root / 'tasks/APBRA-76-deployment-guide.json'
        if deployment_guide_path.exists():
            deployment_guide_task = load_json(deployment_guide_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), deployment_guide_task)
            if not extension_errors:
                extension_errors += task_errors(deployment_guide_task, catalog, sources)
                if deployment_guide_task['task_id'] != 'APBRA-76' or deployment_guide_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected deployment guide identity')
                if set(deployment_guide_task['allowed_paths']) != DEPLOYMENT_GUIDE_PATHS:
                    extension_errors.append('Unexpected deployment guide scope')
                if (deployment_guide_task['task_mode'], deployment_guide_task['readiness'], deployment_guide_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Deployment guide requires issued implementation acceptance')
                if deployment_guide_task['source_ids'] != ['capstone-governance']:
                    extension_errors.append('Deployment guide requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                deployment_guide_task = None
        ux_task = None
        ux_path = root / 'tasks/APBRA-137-final-capstone-ux.json'
        if ux_path.exists():
            ux_task = load_json(ux_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), ux_task)
            if not extension_errors:
                extension_errors += task_errors(ux_task, catalog, sources)
                if ux_task['task_id'] != 'APBRA-137' or ux_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected Capstone UX identity')
                if set(ux_task['allowed_paths']) != CAPSTONE_UX_PATHS:
                    extension_errors.append('Unexpected Capstone UX scope')
                if (ux_task['task_mode'], ux_task['readiness'], ux_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Capstone UX requires issued implementation acceptance')
                if ux_task['source_ids'] != ['capstone-governance']:
                    extension_errors.append('Capstone UX requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                ux_task = None
        measure_resolution_task = None
        measure_resolution_path = root / 'tasks/APBRA-138-measure-resolution.json'
        if measure_resolution_path.exists():
            measure_resolution_task = load_json(measure_resolution_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), measure_resolution_task)
            if not extension_errors:
                extension_errors += task_errors(measure_resolution_task, catalog, sources)
                if measure_resolution_task['task_id'] != 'APBRA-138' or measure_resolution_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected measure resolution identity')
                if set(measure_resolution_task['allowed_paths']) != MEASURE_RESOLUTION_PATHS:
                    extension_errors.append('Unexpected measure resolution scope')
                if (measure_resolution_task['task_mode'], measure_resolution_task['readiness'], measure_resolution_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Measure resolution requires issued implementation acceptance')
                if measure_resolution_task['source_ids'] != ['capstone-governance']:
                    extension_errors.append('Measure resolution requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                measure_resolution_task = None
        report_design_normalization_task = None
        report_design_normalization_path = root / 'tasks/APBRA-139-report-design-normalization.json'
        if report_design_normalization_path.exists():
            report_design_normalization_task = load_json(report_design_normalization_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), report_design_normalization_task)
            if not extension_errors:
                extension_errors += task_errors(report_design_normalization_task, catalog, sources)
                if report_design_normalization_task['task_id'] != 'APBRA-139' or report_design_normalization_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected report design normalization identity')
                if set(report_design_normalization_task['allowed_paths']) != REPORT_DESIGN_NORMALIZATION_PATHS:
                    extension_errors.append('Unexpected report design normalization scope')
                if (report_design_normalization_task['task_mode'], report_design_normalization_task['readiness'], report_design_normalization_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Report design normalization requires issued implementation acceptance')
                if report_design_normalization_task['source_ids'] != ['capstone-governance']:
                    extension_errors.append('Report design normalization requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                report_design_normalization_task = None
        capstone_documentation_task = None
        capstone_documentation_path = root / 'tasks/APBRA-140-capstone-documentation.json'
        if capstone_documentation_path.exists():
            capstone_documentation_task = load_json(capstone_documentation_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), capstone_documentation_task)
            if not extension_errors:
                extension_errors += task_errors(capstone_documentation_task, catalog, sources)
                if capstone_documentation_task['task_id'] != 'APBRA-140' or capstone_documentation_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected Capstone documentation identity')
                if set(capstone_documentation_task['allowed_paths']) != CAPSTONE_DOCUMENTATION_PATHS:
                    extension_errors.append('Unexpected Capstone documentation scope')
                if (capstone_documentation_task['task_mode'], capstone_documentation_task['readiness'], capstone_documentation_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Capstone documentation requires issued implementation acceptance')
                if capstone_documentation_task['source_ids'] != ['capstone-governance']:
                    extension_errors.append('Capstone documentation requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                capstone_documentation_task = None
        measure_contract_pipeline_task = None
        measure_contract_pipeline_path = root / 'tasks/APBRA-141-measure-contract-pipeline.json'
        if measure_contract_pipeline_path.exists():
            measure_contract_pipeline_task = load_json(measure_contract_pipeline_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), measure_contract_pipeline_task)
            if not extension_errors:
                extension_errors += task_errors(measure_contract_pipeline_task, catalog, sources)
                if measure_contract_pipeline_task['task_id'] != 'APBRA-141' or measure_contract_pipeline_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected measure contract pipeline identity')
                if measure_contract_pipeline_task['branch'] != 'agent/APBRA-DEVOPS/APBRA-141-measure-contract-pipeline':
                    extension_errors.append('Unexpected measure contract pipeline branch')
                if measure_contract_pipeline_task['base_commit'] != 'efe4e02603817ae4350565184585bee9333633b4':
                    extension_errors.append('Stale measure contract pipeline base')
                if set(measure_contract_pipeline_task['allowed_paths']) != MEASURE_CONTRACT_PIPELINE_PATHS:
                    extension_errors.append('Unexpected measure contract pipeline scope')
                if (measure_contract_pipeline_task['task_mode'], measure_contract_pipeline_task['readiness'], measure_contract_pipeline_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Measure contract pipeline requires issued implementation acceptance')
                if measure_contract_pipeline_task['source_ids'] != ['capstone-governance']:
                    extension_errors.append('Measure contract pipeline requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                measure_contract_pipeline_task = None
        layout_repair_task = None
        layout_repair_path = root / 'tasks/APBRA-142-layout-repair.json'
        if layout_repair_path.exists():
            layout_repair_task = load_json(layout_repair_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), layout_repair_task)
            if not extension_errors:
                extension_errors += task_errors(layout_repair_task, catalog, sources)
                if layout_repair_task['task_id'] != 'APBRA-142' or layout_repair_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected layout repair identity')
                if layout_repair_task['branch'] != 'agent/APBRA-DEVOPS/APBRA-142-layout-repair':
                    extension_errors.append('Unexpected layout repair branch')
                if layout_repair_task['base_commit'] != 'de6f69766306076b3836e6479d7cd82f2f593465':
                    extension_errors.append('Stale layout repair base')
                if set(layout_repair_task['allowed_paths']) != LAYOUT_REPAIR_PATHS:
                    extension_errors.append('Unexpected layout repair scope')
                if (layout_repair_task['task_mode'], layout_repair_task['readiness'], layout_repair_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Layout repair requires issued implementation acceptance')
                if layout_repair_task['source_ids'] != ['capstone-governance']:
                    extension_errors.append('Layout repair requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                layout_repair_task = None
        typed_confirmed_requirements_task = None
        typed_confirmed_requirements_path = root / 'tasks/APBRA-143-typed-confirmed-requirements.json'
        if typed_confirmed_requirements_path.exists():
            typed_confirmed_requirements_task = load_json(typed_confirmed_requirements_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), typed_confirmed_requirements_task)
            if not extension_errors:
                extension_errors += task_errors(typed_confirmed_requirements_task, catalog, sources)
                if typed_confirmed_requirements_task['task_id'] != 'APBRA-143' or typed_confirmed_requirements_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected typed confirmed requirements identity')
                if typed_confirmed_requirements_task['branch'] != 'agent/APBRA-DEVOPS/APBRA-143-typed-confirmed-requirements':
                    extension_errors.append('Unexpected typed confirmed requirements branch')
                if typed_confirmed_requirements_task['base_commit'] != 'aac4639f30bc1d785972dd48b704537ee98548d7':
                    extension_errors.append('Stale typed confirmed requirements base')
                if set(typed_confirmed_requirements_task['allowed_paths']) != TYPED_CONFIRMED_REQUIREMENTS_PATHS:
                    extension_errors.append('Unexpected typed confirmed requirements scope')
                if (typed_confirmed_requirements_task['task_mode'], typed_confirmed_requirements_task['readiness'], typed_confirmed_requirements_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Typed confirmed requirements requires issued implementation acceptance')
                if typed_confirmed_requirements_task['source_ids'] != ['capstone-governance']:
                    extension_errors.append('Typed confirmed requirements requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                typed_confirmed_requirements_task = None
        ai_native_clarification_task = None
        ai_native_clarification_path = root / 'tasks/APBRA-144-ai-native-iterative-clarification.json'
        if ai_native_clarification_path.exists():
            ai_native_clarification_task = load_json(ai_native_clarification_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), ai_native_clarification_task)
            if not extension_errors:
                extension_errors += task_errors(ai_native_clarification_task, catalog, sources)
                if ai_native_clarification_task['task_id'] != 'APBRA-144' or ai_native_clarification_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected AI-native clarification identity')
                if ai_native_clarification_task['branch'] != 'agent/APBRA-DEVOPS/APBRA-144-ai-native-iterative-clarification':
                    extension_errors.append('Unexpected AI-native clarification branch')
                if ai_native_clarification_task['base_commit'] != '3e9d2f9c06c4e19046068923687af9d9defcdbf5':
                    extension_errors.append('Stale AI-native clarification base')
                if set(ai_native_clarification_task['allowed_paths']) != AI_NATIVE_CLARIFICATION_PATHS:
                    extension_errors.append('Unexpected AI-native clarification scope')
                if (ai_native_clarification_task['task_mode'], ai_native_clarification_task['readiness'], ai_native_clarification_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('AI-native clarification requires issued implementation acceptance')
                if ai_native_clarification_task['source_ids'] != ['capstone-governance']:
                    extension_errors.append('AI-native clarification requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                ai_native_clarification_task = None
        generic_time_grain_task = None
        generic_time_grain_path = root / 'tasks/APBRA-145-generic-time-grain-support.json'
        if generic_time_grain_path.exists():
            generic_time_grain_task = load_json(generic_time_grain_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), generic_time_grain_task)
            if not extension_errors:
                extension_errors += task_errors(generic_time_grain_task, catalog, sources)
                if generic_time_grain_task['task_id'] != 'APBRA-145' or generic_time_grain_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected generic time-grain identity')
                if generic_time_grain_task['branch'] != 'agent/APBRA-DEVOPS/APBRA-145-generic-time-grain-support':
                    extension_errors.append('Unexpected generic time-grain branch')
                if generic_time_grain_task['base_commit'] != 'f25c3caca0ec3364d56be5303dae543bf502a4e1':
                    extension_errors.append('Stale generic time-grain base')
                if set(generic_time_grain_task['allowed_paths']) != GENERIC_TIME_GRAIN_PATHS:
                    extension_errors.append('Unexpected generic time-grain scope')
                if (generic_time_grain_task['task_mode'], generic_time_grain_task['readiness'], generic_time_grain_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Generic time-grain support requires issued implementation acceptance')
                if generic_time_grain_task['source_ids'] != ['capstone-governance']:
                    extension_errors.append('Generic time-grain support requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                generic_time_grain_task = None
        post_capstone_mvp_baseline_task = None
        post_capstone_mvp_baseline_path = root / 'tasks/APBRA-146-post-capstone-mvp-baseline-reconciliation.json'
        if post_capstone_mvp_baseline_path.exists():
            post_capstone_mvp_baseline_task = load_json(post_capstone_mvp_baseline_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), post_capstone_mvp_baseline_task)
            if not extension_errors:
                extension_errors += task_errors(post_capstone_mvp_baseline_task, catalog, sources)
                if post_capstone_mvp_baseline_task['task_id'] != 'APBRA-146' or post_capstone_mvp_baseline_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected post-Capstone MVP baseline identity')
                if post_capstone_mvp_baseline_task['branch'] != 'agent/APBRA-DEVOPS/APBRA-146-post-capstone-mvp-baseline-reconciliation':
                    extension_errors.append('Unexpected post-Capstone MVP baseline branch')
                if post_capstone_mvp_baseline_task['base_commit'] != '65d7281d1132ce5b4eca6d3cd89fd30e95f5c342':
                    extension_errors.append('Stale post-Capstone MVP baseline base')
                if set(post_capstone_mvp_baseline_task['allowed_paths']) != CAPSTONE_DOCUMENTATION_PATHS:
                    extension_errors.append('Unexpected post-Capstone MVP baseline scope')
                if (post_capstone_mvp_baseline_task['task_mode'], post_capstone_mvp_baseline_task['readiness'], post_capstone_mvp_baseline_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Post-Capstone MVP baseline requires issued implementation acceptance')
                if post_capstone_mvp_baseline_task['source_ids'] != ['capstone-governance']:
                    extension_errors.append('Post-Capstone MVP baseline requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                post_capstone_mvp_baseline_task = None
        post_capstone_product_reconciliation_task = None
        post_capstone_product_reconciliation_path = root / 'tasks/APBRA-148-post-capstone-product-reconciliation.json'
        if post_capstone_product_reconciliation_path.exists():
            post_capstone_product_reconciliation_task = load_json(post_capstone_product_reconciliation_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), post_capstone_product_reconciliation_task)
            if not extension_errors:
                extension_errors += task_errors(post_capstone_product_reconciliation_task, catalog, sources)
                if post_capstone_product_reconciliation_task['task_id'] != 'APBRA-148' or post_capstone_product_reconciliation_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected post-Capstone product reconciliation identity')
                if post_capstone_product_reconciliation_task['branch'] != 'agent/APBRA-DEVOPS/APBRA-148-post-capstone-product-reconciliation':
                    extension_errors.append('Unexpected post-Capstone product reconciliation branch')
                if post_capstone_product_reconciliation_task['base_commit'] != 'd072870fea8b8ae8caedc5e553653a433b697f11':
                    extension_errors.append('Stale post-Capstone product reconciliation base')
                if set(post_capstone_product_reconciliation_task['allowed_paths']) != POST_CAPSTONE_PRODUCT_RECONCILIATION_PATHS:
                    extension_errors.append('Unexpected post-Capstone product reconciliation scope')
                if (post_capstone_product_reconciliation_task['task_mode'], post_capstone_product_reconciliation_task['readiness'], post_capstone_product_reconciliation_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Post-Capstone product reconciliation requires issued implementation acceptance')
                if post_capstone_product_reconciliation_task['source_ids'] != ['post-capstone-product-reconciliation']:
                    extension_errors.append('Post-Capstone product reconciliation requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                post_capstone_product_reconciliation_task = None
        data_model_documentation_reconciliation_task = None
        data_model_documentation_reconciliation_path = root / 'tasks/APBRA-159-data-model-documentation-reconciliation.json'
        if data_model_documentation_reconciliation_path.exists():
            data_model_documentation_reconciliation_task = load_json(data_model_documentation_reconciliation_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), data_model_documentation_reconciliation_task)
            if not extension_errors:
                extension_errors += task_errors(data_model_documentation_reconciliation_task, catalog, sources)
                if data_model_documentation_reconciliation_task['task_id'] != 'APBRA-159' or data_model_documentation_reconciliation_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected data-model documentation reconciliation identity')
                if data_model_documentation_reconciliation_task['branch'] != 'agent/APBRA-DEVOPS/APBRA-159-data-model-documentation-reconciliation':
                    extension_errors.append('Unexpected data-model documentation reconciliation branch')
                if data_model_documentation_reconciliation_task['base_commit'] != 'd71c02d84105d4f2be9316778dccaadbc5ef6814':
                    extension_errors.append('Stale data-model documentation reconciliation base')
                if set(data_model_documentation_reconciliation_task['allowed_paths']) != DATA_MODEL_DOCUMENTATION_RECONCILIATION_PATHS:
                    extension_errors.append('Unexpected data-model documentation reconciliation scope')
                if (data_model_documentation_reconciliation_task['task_mode'], data_model_documentation_reconciliation_task['readiness'], data_model_documentation_reconciliation_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Data-model documentation reconciliation requires issued implementation acceptance')
                if data_model_documentation_reconciliation_task['source_ids'] != ['post-capstone-data-model-reconciliation']:
                    extension_errors.append('Data-model documentation reconciliation requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                data_model_documentation_reconciliation_task = None
        confirmation_readiness_integrity_task = None
        confirmation_readiness_integrity_path = root / 'tasks/APBRA-147-confirmation-readiness-integrity.json'
        if confirmation_readiness_integrity_path.exists():
            confirmation_readiness_integrity_task = load_json(confirmation_readiness_integrity_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), confirmation_readiness_integrity_task)
            if not extension_errors:
                extension_errors += task_errors(confirmation_readiness_integrity_task, catalog, sources)
                if confirmation_readiness_integrity_task['task_id'] != 'APBRA-147' or confirmation_readiness_integrity_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected confirmation readiness integrity identity')
                if confirmation_readiness_integrity_task['branch'] != 'agent/APBRA-DEVOPS/APBRA-147-confirmation-readiness-integrity':
                    extension_errors.append('Unexpected confirmation readiness integrity branch')
                if confirmation_readiness_integrity_task['base_commit'] != '9ca65a53c4282d3a7fa3c91732c8c31d809fecce':
                    extension_errors.append('Stale confirmation readiness integrity base')
                if set(confirmation_readiness_integrity_task['allowed_paths']) != CONFIRMATION_READINESS_INTEGRITY_PATHS:
                    extension_errors.append('Unexpected confirmation readiness integrity scope')
                if (confirmation_readiness_integrity_task['task_mode'], confirmation_readiness_integrity_task['readiness'], confirmation_readiness_integrity_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Confirmation readiness integrity requires issued implementation acceptance')
                if confirmation_readiness_integrity_task['source_ids'] != ['post-capstone-confirmation-readiness-integrity']:
                    extension_errors.append('Confirmation readiness integrity requires its specific accepted source')
            errors += extension_errors
            if extension_errors:
                confirmation_readiness_integrity_task = None
        invited_private_case_foundation_task = None
        invited_private_case_foundation_path = root / 'tasks/APBRA-162-invited-private-case-foundation.json'
        if invited_private_case_foundation_path.exists():
            invited_private_case_foundation_task = load_json(invited_private_case_foundation_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), invited_private_case_foundation_task)
            if not extension_errors:
                extension_errors += task_errors(invited_private_case_foundation_task, catalog, sources)
                canonical_task = json.dumps(invited_private_case_foundation_task, sort_keys=True, separators=(',', ':')).encode()
                if hashlib.sha256(canonical_task).hexdigest() != INVITED_PRIVATE_CASE_FOUNDATION_TASK_SHA256:
                    extension_errors.append('Invited private-case foundation contract differs from accepted authority')
                if invited_private_case_foundation_task['task_id'] != 'APBRA-162' or invited_private_case_foundation_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected invited private-case foundation identity')
                if invited_private_case_foundation_task['agent_card_version'] != '0.1':
                    extension_errors.append('Stale invited private-case foundation agent card version')
                if invited_private_case_foundation_task['branch'] != 'agent/APBRA-DEVOPS/APBRA-162-invited-private-case-foundation':
                    extension_errors.append('Unexpected invited private-case foundation branch')
                if invited_private_case_foundation_task['base_commit'] != '02d14e9e2e023661fb0d0d3a20627094d74b8f70':
                    extension_errors.append('Stale invited private-case foundation base')
                if set(invited_private_case_foundation_task['allowed_paths']) != INVITED_PRIVATE_CASE_FOUNDATION_PATHS:
                    extension_errors.append('Unexpected invited private-case foundation scope')
                if (invited_private_case_foundation_task['task_mode'], invited_private_case_foundation_task['readiness'], invited_private_case_foundation_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Invited private-case foundation requires issued implementation acceptance')
                if invited_private_case_foundation_task['source_ids'] != [
                        'mvp1-invited-private-case-foundation',
                        'mvp1-invited-private-case-foundation-scope-amendment']:
                    extension_errors.append('Invited private-case foundation requires its specific accepted source')
                source_map = {source['id']: source for source in sources['sources']}
                invited_source = source_map.get('mvp1-invited-private-case-foundation')
                if invited_source is None:
                    extension_errors.append('Invited private-case foundation accepted source is missing')
                else:
                    canonical_source = json.dumps(invited_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_source).hexdigest() != INVITED_PRIVATE_CASE_FOUNDATION_SOURCE_SHA256:
                        extension_errors.append('Invited private-case foundation source differs from accepted provenance')
                amendment_source = source_map.get('mvp1-invited-private-case-foundation-scope-amendment')
                if amendment_source is None:
                    extension_errors.append('Invited private-case foundation amendment source is missing')
                else:
                    canonical_amendment_source = json.dumps(amendment_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_amendment_source).hexdigest() != INVITED_PRIVATE_CASE_FOUNDATION_AMENDMENT_SOURCE_SHA256:
                        extension_errors.append('Invited private-case foundation amendment source differs from accepted provenance')
            errors += extension_errors
            if extension_errors:
                invited_private_case_foundation_task = None
        durable_conversation_evidence_acceptance_task = None
        durable_conversation_evidence_acceptance_path = root / 'tasks/APBRA-163-durable-conversation-evidence-acceptance.json'
        if durable_conversation_evidence_acceptance_path.exists():
            durable_conversation_evidence_acceptance_task = load_json(durable_conversation_evidence_acceptance_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), durable_conversation_evidence_acceptance_task)
            if not extension_errors:
                extension_errors += task_errors(durable_conversation_evidence_acceptance_task, catalog, sources)
                canonical_task = json.dumps(durable_conversation_evidence_acceptance_task, sort_keys=True, separators=(',', ':')).encode()
                if hashlib.sha256(canonical_task).hexdigest() != DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_TASK_SHA256:
                    extension_errors.append('Durable conversation evidence acceptance contract differs from accepted authority')
                if durable_conversation_evidence_acceptance_task['task_id'] != 'APBRA-163' or durable_conversation_evidence_acceptance_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected durable conversation evidence acceptance identity')
                if durable_conversation_evidence_acceptance_task['agent_card_version'] != '0.1':
                    extension_errors.append('Stale durable conversation evidence acceptance agent card version')
                if durable_conversation_evidence_acceptance_task['branch'] != 'agent/APBRA-DEVOPS/APBRA-163-durable-conversation-evidence-acceptance':
                    extension_errors.append('Unexpected durable conversation evidence acceptance branch')
                if durable_conversation_evidence_acceptance_task['base_commit'] != '8b39b9e3199acdbfcaf5ce75f3cc99ef4371138e':
                    extension_errors.append('Stale durable conversation evidence acceptance base')
                if set(durable_conversation_evidence_acceptance_task['allowed_paths']) != DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_PATHS:
                    extension_errors.append('Unexpected durable conversation evidence acceptance scope')
                if (durable_conversation_evidence_acceptance_task['task_mode'], durable_conversation_evidence_acceptance_task['readiness'], durable_conversation_evidence_acceptance_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Durable conversation evidence acceptance requires issued implementation acceptance')
                if durable_conversation_evidence_acceptance_task['source_ids'] != [
                        'mvp1-durable-conversation-evidence-acceptance',
                        'mvp1-durable-conversation-evidence-acceptance-ci-amendment',
                        'mvp1-durable-conversation-evidence-acceptance-historical-capacity-fixture']:
                    extension_errors.append('Durable conversation evidence acceptance requires its specific accepted source')
                source_map = {source['id']: source for source in sources['sources']}
                package_source = source_map.get('mvp1-durable-conversation-evidence-acceptance')
                if package_source is None:
                    extension_errors.append('Durable conversation evidence acceptance source is missing')
                else:
                    canonical_source = json.dumps(package_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_source).hexdigest() != DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_SOURCE_SHA256:
                        extension_errors.append('Durable conversation evidence acceptance source differs from accepted provenance')
                amendment_source = source_map.get('mvp1-durable-conversation-evidence-acceptance-ci-amendment')
                if amendment_source is None:
                    extension_errors.append('Durable conversation evidence acceptance CI amendment source is missing')
                else:
                    canonical_amendment_source = json.dumps(amendment_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_amendment_source).hexdigest() != DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_AMENDMENT_SOURCE_SHA256:
                        extension_errors.append('Durable conversation evidence acceptance CI amendment source differs from accepted provenance')
                historical_fix_source = source_map.get('mvp1-durable-conversation-evidence-acceptance-historical-capacity-fixture')
                if historical_fix_source is None:
                    extension_errors.append('Durable conversation evidence acceptance historical capacity fixture source is missing')
                else:
                    canonical_historical_fix_source = json.dumps(historical_fix_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_historical_fix_source).hexdigest() != DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_HISTORICAL_FIX_SOURCE_SHA256:
                        extension_errors.append('Durable conversation evidence acceptance historical capacity fixture source differs from accepted provenance')
            errors += extension_errors
            if extension_errors:
                durable_conversation_evidence_acceptance_task = None
        protected_generation_output_history_task = None
        protected_generation_output_history_path = root / 'tasks/APBRA-164-protected-generation-output-history.json'
        if protected_generation_output_history_path.exists():
            protected_generation_output_history_task = load_json(protected_generation_output_history_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), protected_generation_output_history_task)
            if not extension_errors:
                extension_errors += task_errors(protected_generation_output_history_task, catalog, sources)
                canonical_task = json.dumps(protected_generation_output_history_task, sort_keys=True, separators=(',', ':')).encode()
                if hashlib.sha256(canonical_task).hexdigest() != PROTECTED_GENERATION_OUTPUT_HISTORY_TASK_SHA256:
                    extension_errors.append('Protected generation output history contract differs from accepted authority')
                if protected_generation_output_history_task['task_id'] != 'APBRA-164' or protected_generation_output_history_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected protected generation output history identity')
                if protected_generation_output_history_task['agent_card_version'] != '0.1':
                    extension_errors.append('Stale protected generation output history agent card version')
                if protected_generation_output_history_task['branch'] != 'agent/APBRA-DEVOPS/APBRA-164-protected-generation-output-history':
                    extension_errors.append('Unexpected protected generation output history branch')
                if protected_generation_output_history_task['base_commit'] != '12b75a93eebdbbd2a284e6179ae676a8cd411e0f':
                    extension_errors.append('Stale protected generation output history base')
                if set(protected_generation_output_history_task['allowed_paths']) != PROTECTED_GENERATION_OUTPUT_HISTORY_PATHS:
                    extension_errors.append('Unexpected protected generation output history scope')
                if (protected_generation_output_history_task['task_mode'], protected_generation_output_history_task['readiness'], protected_generation_output_history_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Protected generation output history requires issued implementation acceptance')
                if protected_generation_output_history_task['source_ids'] != ['mvp1-protected-generation-output-history', PROTECTED_GENERATION_OUTPUT_HISTORY_AMENDMENT_SOURCE_ID]:
                    extension_errors.append('Protected generation output history requires its specific accepted source')
                source_map = {source['id']: source for source in sources['sources']}
                package_source = source_map.get('mvp1-protected-generation-output-history')
                if package_source is None:
                    extension_errors.append('Protected generation output history accepted source is missing')
                else:
                    canonical_source = json.dumps(package_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_source).hexdigest() != PROTECTED_GENERATION_OUTPUT_HISTORY_SOURCE_SHA256:
                        extension_errors.append('Protected generation output history source differs from accepted provenance')
                amendment_source = source_map.get(PROTECTED_GENERATION_OUTPUT_HISTORY_AMENDMENT_SOURCE_ID)
                if amendment_source is None:
                    extension_errors.append('Protected generation output history bootstrap amendment source is missing')
                else:
                    canonical_amendment_source = json.dumps(amendment_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_amendment_source).hexdigest() != PROTECTED_GENERATION_OUTPUT_HISTORY_AMENDMENT_SOURCE_SHA256:
                        extension_errors.append('Protected generation output history bootstrap amendment source differs from accepted provenance')
            errors += extension_errors
            if extension_errors:
                protected_generation_output_history_task = None
        business_friendly_ux_application_shell_task = None
        business_friendly_ux_application_shell_path = root / 'tasks/APBRA-169-business-friendly-ux-application-shell.json'
        if business_friendly_ux_application_shell_path.exists():
            business_friendly_ux_application_shell_task = load_json(business_friendly_ux_application_shell_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), business_friendly_ux_application_shell_task)
            if not extension_errors:
                extension_errors += task_errors(business_friendly_ux_application_shell_task, catalog, sources)
                canonical_task = json.dumps(business_friendly_ux_application_shell_task, sort_keys=True, separators=(',', ':')).encode()
                if hashlib.sha256(canonical_task).hexdigest() != BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_TASK_SHA256:
                    extension_errors.append('Business-friendly UX application shell contract differs from accepted authority')
                if business_friendly_ux_application_shell_task['task_id'] != 'APBRA-169' or business_friendly_ux_application_shell_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected business-friendly UX application shell identity')
                if business_friendly_ux_application_shell_task['agent_card_version'] != '0.1':
                    extension_errors.append('Stale business-friendly UX application shell agent card version')
                if business_friendly_ux_application_shell_task['branch'] != 'agent/APBRA-DEVOPS/APBRA-169-business-friendly-ux-shell':
                    extension_errors.append('Unexpected business-friendly UX application shell branch')
                if business_friendly_ux_application_shell_task['base_commit'] != 'a34a20ef8448b932bc9537c2b1c377c8de1727d6':
                    extension_errors.append('Stale business-friendly UX application shell base')
                if set(business_friendly_ux_application_shell_task['allowed_paths']) != BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_PATHS:
                    extension_errors.append('Unexpected business-friendly UX application shell scope')
                if (business_friendly_ux_application_shell_task['task_mode'], business_friendly_ux_application_shell_task['readiness'], business_friendly_ux_application_shell_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Business-friendly UX application shell requires issued implementation acceptance')
                if business_friendly_ux_application_shell_task['source_ids'] != ['mvp1-business-friendly-ux-application-shell', BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_AMENDMENT_SOURCE_ID]:
                    extension_errors.append('Business-friendly UX application shell requires its specific accepted source')
                source_map = {source['id']: source for source in sources['sources']}
                package_source = source_map.get('mvp1-business-friendly-ux-application-shell')
                if package_source is None:
                    extension_errors.append('Business-friendly UX application shell accepted source is missing')
                else:
                    canonical_source = json.dumps(package_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_source).hexdigest() != BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_SOURCE_SHA256:
                        extension_errors.append('Business-friendly UX application shell source differs from accepted provenance')
                amendment_source = source_map.get(BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_AMENDMENT_SOURCE_ID)
                if amendment_source is None:
                    extension_errors.append('Business-friendly UX reviewed-design amendment source is missing')
                else:
                    canonical_amendment_source = json.dumps(amendment_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_amendment_source).hexdigest() != BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_AMENDMENT_SOURCE_SHA256:
                        extension_errors.append('Business-friendly UX reviewed-design amendment source differs from accepted provenance')
            errors += extension_errors
            if extension_errors:
                business_friendly_ux_application_shell_task = None
        professional_saas_experience_visual_system_task = None
        professional_saas_experience_visual_system_path = root / 'tasks/APBRA-170-professional-saas-experience-visual-system.json'
        if professional_saas_experience_visual_system_path.exists():
            professional_saas_experience_visual_system_task = load_json(professional_saas_experience_visual_system_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), professional_saas_experience_visual_system_task)
            if not extension_errors:
                extension_errors += task_errors(professional_saas_experience_visual_system_task, catalog, sources)
                canonical_task = json.dumps(professional_saas_experience_visual_system_task, sort_keys=True, separators=(',', ':')).encode()
                if hashlib.sha256(canonical_task).hexdigest() != PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_TASK_SHA256:
                    extension_errors.append('Professional SaaS experience visual-system contract differs from accepted authority')
                if professional_saas_experience_visual_system_task['task_id'] != 'APBRA-170' or professional_saas_experience_visual_system_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected professional SaaS experience visual-system identity')
                if professional_saas_experience_visual_system_task['agent_card_version'] != '0.1':
                    extension_errors.append('Stale professional SaaS experience visual-system agent card version')
                if professional_saas_experience_visual_system_task['branch'] != PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_REGISTRATION_BRANCH:
                    extension_errors.append('Unexpected professional SaaS experience visual-system branch')
                if professional_saas_experience_visual_system_task['base_commit'] != 'd7fc0dfe06ed06fa64ed6cd95ef617a876191565':
                    extension_errors.append('Stale professional SaaS experience visual-system base')
                if set(professional_saas_experience_visual_system_task['allowed_paths']) != PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_PATHS:
                    extension_errors.append('Unexpected professional SaaS experience visual-system scope')
                if (professional_saas_experience_visual_system_task['task_mode'], professional_saas_experience_visual_system_task['readiness'], professional_saas_experience_visual_system_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Professional SaaS experience visual-system requires issued implementation acceptance')
                if professional_saas_experience_visual_system_task['source_ids'] != [PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_SOURCE_ID]:
                    extension_errors.append('Professional SaaS experience visual-system requires its specific accepted source')
                source_map = {source['id']: source for source in sources['sources']}
                package_source = source_map.get(PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_SOURCE_ID)
                if package_source is None:
                    extension_errors.append('Professional SaaS experience visual-system accepted source is missing')
                else:
                    canonical_source = json.dumps(package_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_source).hexdigest() != PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_SOURCE_SHA256:
                        extension_errors.append('Professional SaaS experience visual-system source differs from accepted provenance')
            errors += extension_errors
            if extension_errors:
                professional_saas_experience_visual_system_task = None
        business_user_intelligent_generation_task = None
        business_user_intelligent_generation_path = root / 'tasks/APBRA-171-business-user-report-creation-intelligent-generation.json'
        if business_user_intelligent_generation_path.exists():
            business_user_intelligent_generation_task = load_json(business_user_intelligent_generation_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), business_user_intelligent_generation_task)
            if not extension_errors:
                extension_errors += task_errors(business_user_intelligent_generation_task, catalog, sources)
                canonical_task = json.dumps(business_user_intelligent_generation_task, sort_keys=True, separators=(',', ':')).encode()
                if hashlib.sha256(canonical_task).hexdigest() != BUSINESS_USER_INTELLIGENT_GENERATION_TASK_SHA256:
                    extension_errors.append('Business-user intelligent-generation contract differs from accepted authority')
                if business_user_intelligent_generation_task['task_id'] != 'APBRA-171' or business_user_intelligent_generation_task['assigned_agent'] != 'APBRA-DEVOPS':
                    extension_errors.append('Unexpected business-user intelligent-generation identity')
                if business_user_intelligent_generation_task['agent_card_version'] != '0.1':
                    extension_errors.append('Stale business-user intelligent-generation agent card version')
                if business_user_intelligent_generation_task['branch'] != BUSINESS_USER_INTELLIGENT_GENERATION_BRANCH:
                    extension_errors.append('Unexpected business-user intelligent-generation branch')
                if business_user_intelligent_generation_task['base_commit'] != '2e6dfa67d674015773555aa334ef4561d8b907cb':
                    extension_errors.append('Stale business-user intelligent-generation base')
                if set(business_user_intelligent_generation_task['allowed_paths']) != BUSINESS_USER_INTELLIGENT_GENERATION_PATHS:
                    extension_errors.append('Unexpected business-user intelligent-generation scope')
                if (business_user_intelligent_generation_task['task_mode'], business_user_intelligent_generation_task['readiness'], business_user_intelligent_generation_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('Business-user intelligent generation requires issued implementation acceptance')
                if business_user_intelligent_generation_task['source_ids'] != [
                        BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID,
                        BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_SOURCE_ID,
                        BUSINESS_USER_INTELLIGENT_GENERATION_COMPILER_FIXTURE_AMENDMENT_SOURCE_ID]:
                    extension_errors.append('Business-user intelligent generation requires its specific accepted source')
                source_map = {source['id']: source for source in sources['sources']}
                package_source = source_map.get(BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID)
                if package_source is None:
                    extension_errors.append('Business-user intelligent-generation accepted source is missing')
                else:
                    canonical_source = json.dumps(package_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_source).hexdigest() != BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_SHA256:
                        extension_errors.append('Business-user intelligent-generation source differs from accepted provenance')
                amendment_source = source_map.get(BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_SOURCE_ID)
                if amendment_source is None:
                    extension_errors.append('Business-user intelligent-generation Playwright amendment source is missing')
                else:
                    canonical_amendment_source = json.dumps(amendment_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_amendment_source).hexdigest() != BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_SOURCE_SHA256:
                        extension_errors.append('Business-user intelligent-generation Playwright amendment source differs from accepted provenance')
                compiler_fixture_amendment_source = source_map.get(BUSINESS_USER_INTELLIGENT_GENERATION_COMPILER_FIXTURE_AMENDMENT_SOURCE_ID)
                if compiler_fixture_amendment_source is None:
                    extension_errors.append('Business-user intelligent-generation compiler-fixture amendment source is missing')
                else:
                    canonical_compiler_fixture_amendment_source = json.dumps(compiler_fixture_amendment_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_compiler_fixture_amendment_source).hexdigest() != BUSINESS_USER_INTELLIGENT_GENERATION_COMPILER_FIXTURE_AMENDMENT_SOURCE_SHA256:
                        extension_errors.append('Business-user intelligent-generation compiler-fixture amendment source differs from accepted provenance')
            errors += extension_errors
            if extension_errors:
                business_user_intelligent_generation_task = None
        model_led_flexible_delivery_task = None
        model_led_flexible_delivery_path = root / 'tasks/APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json'
        if model_led_flexible_delivery_path.exists():
            model_led_flexible_delivery_task = load_json(model_led_flexible_delivery_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), model_led_flexible_delivery_task)
            if not extension_errors:
                extension_errors += task_errors(model_led_flexible_delivery_task, catalog, sources)
                canonical_task = json.dumps(model_led_flexible_delivery_task, sort_keys=True, separators=(',', ':')).encode()
                if hashlib.sha256(canonical_task).hexdigest() != MODEL_LED_FLEXIBLE_DELIVERY_TASK_SHA256:
                    extension_errors.append('APBRA-174 contract differs from accepted authority')
                if (model_led_flexible_delivery_task['task_id'], model_led_flexible_delivery_task['assigned_agent'],
                        model_led_flexible_delivery_task['agent_card_version']) != ('APBRA-174', 'APBRA-DEVOPS', '0.1'):
                    extension_errors.append('Unexpected APBRA-174 task or agent identity')
                if model_led_flexible_delivery_task['branch'] != MODEL_LED_FLEXIBLE_DELIVERY_BRANCH:
                    extension_errors.append('Unexpected APBRA-174 implementation branch')
                if model_led_flexible_delivery_task['base_commit'] != 'b2fba8d507262cf912e161b491549ab0d5680b0d':
                    extension_errors.append('Stale APBRA-174 base')
                if set(model_led_flexible_delivery_task['allowed_paths']) != (
                        MODEL_LED_FLEXIBLE_DELIVERY_PATHS | MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_PATHS):
                    extension_errors.append('Unexpected APBRA-174 implementation scope')
                if (model_led_flexible_delivery_task['task_mode'], model_led_flexible_delivery_task['readiness'],
                        model_led_flexible_delivery_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('APBRA-174 requires issued implementation acceptance')
                if model_led_flexible_delivery_task['source_ids'] != [
                    MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_ID,
                    MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_SOURCE_ID,
                    MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_SOURCE_ID,
                ]:
                    extension_errors.append('APBRA-174 requires its specific accepted sources')
                package_source = next((source for source in sources['sources']
                                       if source['id'] == MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_ID), None)
                if package_source is None:
                    extension_errors.append('APBRA-174 accepted source is missing')
                else:
                    canonical_source = json.dumps(package_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_source).hexdigest() != MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_SHA256:
                        extension_errors.append('APBRA-174 source differs from accepted provenance')
                amendment_source = next((source for source in sources['sources']
                                         if source['id'] == MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_SOURCE_ID), None)
                if amendment_source is None:
                    extension_errors.append('APBRA-174 Vite proxy amendment source is missing')
                else:
                    canonical_amendment_source = json.dumps(amendment_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_amendment_source).hexdigest() != MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_SOURCE_SHA256:
                        extension_errors.append('APBRA-174 Vite proxy amendment source differs from accepted provenance')
                capacity_source = next((source for source in sources['sources']
                                        if source['id'] == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_SOURCE_ID), None)
                if capacity_source is None:
                    extension_errors.append('APBRA-174 CI capacity amendment source is missing')
                else:
                    canonical_capacity_source = json.dumps(capacity_source, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(canonical_capacity_source).hexdigest() != MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_SOURCE_SHA256:
                        extension_errors.append('APBRA-174 CI capacity amendment source differs from accepted provenance')
            errors += extension_errors
            if extension_errors:
                model_led_flexible_delivery_task = None
        deployment_portability_entitlement_docs_task = None
        deployment_portability_entitlement_docs_path = root / 'tasks/APBRA-175-deployment-portability-entitlement-docs.json'
        if deployment_portability_entitlement_docs_path.exists():
            deployment_portability_entitlement_docs_task = load_json(deployment_portability_entitlement_docs_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), deployment_portability_entitlement_docs_task)
            if not extension_errors:
                extension_errors += task_errors(deployment_portability_entitlement_docs_task, catalog, sources)
                canonical_task = json.dumps(deployment_portability_entitlement_docs_task, sort_keys=True, separators=(',', ':')).encode()
                if hashlib.sha256(canonical_task).hexdigest() != DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_TASK_SHA256:
                    extension_errors.append('APBRA-175 contract differs from accepted authority')
                if (deployment_portability_entitlement_docs_task['task_id'], deployment_portability_entitlement_docs_task['assigned_agent'],
                        deployment_portability_entitlement_docs_task['agent_card_version']) != ('APBRA-175', 'APBRA-DEVOPS', '0.1'):
                    extension_errors.append('Unexpected APBRA-175 task or agent identity')
                if deployment_portability_entitlement_docs_task['branch'] != DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_BRANCH:
                    extension_errors.append('Unexpected APBRA-175 documentation branch')
                if deployment_portability_entitlement_docs_task['base_commit'] != 'acf1473ea0a05c5f203d85ed55fdc695515880c8':
                    extension_errors.append('Stale APBRA-175 registration base')
                if set(deployment_portability_entitlement_docs_task['allowed_paths']) != DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_PATHS:
                    extension_errors.append('Unexpected APBRA-175 documentation scope')
                if (deployment_portability_entitlement_docs_task['task_mode'], deployment_portability_entitlement_docs_task['readiness'],
                        deployment_portability_entitlement_docs_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('APBRA-175 requires issued documentation-only acceptance')
                if deployment_portability_entitlement_docs_task['source_ids'] != [
                    DEPLOYMENT_PORTABILITY_SOURCE_ID, ENTITLEMENT_ARCHITECTURE_SOURCE_ID,
                ]:
                    extension_errors.append('APBRA-175 requires its two accepted sources')
                for source_id, content_id, expected_sha in (
                    (DEPLOYMENT_PORTABILITY_SOURCE_ID, '9568258', DEPLOYMENT_PORTABILITY_SOURCE_SHA256),
                    (ENTITLEMENT_ARCHITECTURE_SOURCE_ID, '9535525', ENTITLEMENT_ARCHITECTURE_SOURCE_SHA256),
                ):
                    package_source = next((source for source in sources['sources'] if source['id'] == source_id), None)
                    if package_source is None:
                        extension_errors.append('APBRA-175 accepted source is missing: ' + source_id)
                    else:
                        canonical_source = json.dumps(package_source, sort_keys=True, separators=(',', ':')).encode()
                        if hashlib.sha256(canonical_source).hexdigest() != expected_sha:
                            extension_errors.append('APBRA-175 source differs from accepted provenance: ' + source_id)
                        if (package_source.get('content_id') != content_id or
                                package_source.get('version') != 1 or package_source.get('status') != 'ACCEPTED'):
                            extension_errors.append('APBRA-175 source binding differs: ' + source_id)
            errors += extension_errors
            if extension_errors:
                deployment_portability_entitlement_docs_task = None
        owner_onboarding_identity_docs_task = None
        owner_onboarding_identity_docs_path = root / 'tasks/APBRA-176-owner-onboarding-identity-docs.json'
        if owner_onboarding_identity_docs_path.exists():
            owner_onboarding_identity_docs_task = load_json(owner_onboarding_identity_docs_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), owner_onboarding_identity_docs_task)
            if not extension_errors:
                extension_errors += task_errors(owner_onboarding_identity_docs_task, catalog, sources)
                canonical_task = json.dumps(owner_onboarding_identity_docs_task, sort_keys=True, separators=(',', ':')).encode()
                if hashlib.sha256(canonical_task).hexdigest() != OWNER_ONBOARDING_IDENTITY_DOCS_TASK_SHA256:
                    extension_errors.append('APBRA-176 contract differs from accepted authority')
                if (owner_onboarding_identity_docs_task['task_id'], owner_onboarding_identity_docs_task['assigned_agent'],
                        owner_onboarding_identity_docs_task['agent_card_version']) != ('APBRA-176', 'APBRA-DOCS', '0.1'):
                    extension_errors.append('Unexpected APBRA-176 task or agent identity')
                if owner_onboarding_identity_docs_task['branch'] != OWNER_ONBOARDING_IDENTITY_DOCS_BRANCH:
                    extension_errors.append('Unexpected APBRA-176 documentation branch')
                if owner_onboarding_identity_docs_task['base_commit'] != 'd33e6222aaf902da821de2f59f288005f7f6c709':
                    extension_errors.append('Stale APBRA-176 registration base')
                if set(owner_onboarding_identity_docs_task['allowed_paths']) != OWNER_ONBOARDING_IDENTITY_DOCS_PATHS:
                    extension_errors.append('Unexpected APBRA-176 documentation scope')
                if (owner_onboarding_identity_docs_task['task_mode'], owner_onboarding_identity_docs_task['readiness'],
                        owner_onboarding_identity_docs_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('APBRA-176 requires issued documentation-only acceptance')
                if owner_onboarding_identity_docs_task['source_ids'] != [
                    OWNER_ONBOARDING_IDENTITY_SOURCE_ID, OWNER_ONBOARDING_REQUIREMENTS_SOURCE_ID,
                ]:
                    extension_errors.append('APBRA-176 requires its two accepted sources')
                for source_id, content_id, version, expected_sha in (
                    (OWNER_ONBOARDING_IDENTITY_SOURCE_ID, '4030847', 4, OWNER_ONBOARDING_IDENTITY_SOURCE_SHA256),
                    (OWNER_ONBOARDING_REQUIREMENTS_SOURCE_ID, '3932362', 7, OWNER_ONBOARDING_REQUIREMENTS_SOURCE_SHA256),
                ):
                    package_source = next((source for source in sources['sources'] if source['id'] == source_id), None)
                    if package_source is None:
                        extension_errors.append('APBRA-176 accepted source is missing: ' + source_id)
                    else:
                        canonical_source = json.dumps(package_source, sort_keys=True, separators=(',', ':')).encode()
                        if hashlib.sha256(canonical_source).hexdigest() != expected_sha:
                            extension_errors.append('APBRA-176 source differs from accepted provenance: ' + source_id)
                        if (package_source.get('content_id') != content_id or
                                package_source.get('version') != version or package_source.get('status') != 'ACCEPTED'):
                            extension_errors.append('APBRA-176 source binding differs: ' + source_id)
            errors += extension_errors
            if extension_errors:
                owner_onboarding_identity_docs_task = None
        candidate_source_safety_task = None
        candidate_source_safety_path = root / 'tasks/APBRA-108-candidate-source-safety.json'
        if candidate_source_safety_path.exists():
            candidate_source_safety_task = load_json(candidate_source_safety_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), candidate_source_safety_task)
            if not extension_errors:
                extension_errors += task_errors(candidate_source_safety_task, catalog, sources)
                canonical_task = json.dumps(candidate_source_safety_task, sort_keys=True, separators=(',', ':')).encode()
                if hashlib.sha256(canonical_task).hexdigest() != CANDIDATE_SOURCE_SAFETY_TASK_SHA256:
                    extension_errors.append('APBRA-108 contract differs from accepted authority')
                if (candidate_source_safety_task['task_id'], candidate_source_safety_task['assigned_agent'],
                        candidate_source_safety_task['agent_card_version']) != ('APBRA-108', 'APBRA-DEVOPS', '0.1'):
                    extension_errors.append('Unexpected APBRA-108 task or agent identity')
                if candidate_source_safety_task['branch'] != CANDIDATE_SOURCE_SAFETY_BRANCH:
                    extension_errors.append('Unexpected APBRA-108 implementation branch')
                if candidate_source_safety_task['base_commit'] != 'a9fa15de2fa51331e8069eb4519cc6deaf7e6ccf':
                    extension_errors.append('Stale APBRA-108 registration base')
                if (set(candidate_source_safety_task['allowed_paths']) != CANDIDATE_SOURCE_SAFETY_PATHS or
                        len(candidate_source_safety_task['allowed_paths']) != len(CANDIDATE_SOURCE_SAFETY_PATHS)):
                    extension_errors.append('Unexpected APBRA-108 implementation scope')
                if (candidate_source_safety_task['task_mode'], candidate_source_safety_task['readiness'],
                        candidate_source_safety_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('APBRA-108 requires issued implementation acceptance')
                if candidate_source_safety_task['source_ids'] != [row[0] for row in CANDIDATE_SOURCE_SAFETY_SOURCES]:
                    extension_errors.append('APBRA-108 requires exact accepted sources')
                for section, expected in CANDIDATE_SOURCE_SAFETY_GATE_SHA256.items():
                    actual = json.dumps(candidate_source_safety_task[section], sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(actual).hexdigest() != expected:
                        extension_errors.append('APBRA-108 safety/review gate differs: ' + section)
                for source_id, content_id, version, expected_sha in CANDIDATE_SOURCE_SAFETY_SOURCES:
                    package_source = next((source for source in sources['sources'] if source['id'] == source_id), None)
                    if package_source is None:
                        extension_errors.append('APBRA-108 accepted source is missing: ' + source_id)
                    else:
                        canonical_source = json.dumps(package_source, sort_keys=True, separators=(',', ':')).encode()
                        if hashlib.sha256(canonical_source).hexdigest() != expected_sha:
                            extension_errors.append('APBRA-108 source differs from accepted provenance: ' + source_id)
                        if (package_source.get('content_id'), package_source.get('version'), package_source.get('status')) != (content_id, version, 'ACCEPTED'):
                            extension_errors.append('APBRA-108 source binding differs: ' + source_id)
            errors += extension_errors
            if extension_errors:
                candidate_source_safety_task = None
        local_rekey_task = None
        local_rekey_path = root / 'tasks/APBRA-160-local-rekey.json'
        if local_rekey_path.exists():
            local_rekey_task = load_json(local_rekey_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), local_rekey_task)
            if not extension_errors:
                extension_errors += task_errors(local_rekey_task, catalog, sources)
                if hashlib.sha256(json.dumps(local_rekey_task, sort_keys=True, separators=(',', ':')).encode()).hexdigest() != LOCAL_RECOVERY_TASK_SHA256:
                    extension_errors.append('APBRA-160 local rekey contract differs from accepted authority')
                for field, expected in LOCAL_RECOVERY_GATE_SHA256.items():
                    if hashlib.sha256(json.dumps(local_rekey_task[field], sort_keys=True, separators=(',', ':')).encode()).hexdigest() != expected:
                        extension_errors.append('APBRA-160 local rekey protected gate differs: ' + field)
                if (set(local_rekey_task['allowed_paths']) != LOCAL_RECOVERY_PATHS or len(local_rekey_task['allowed_paths']) != 3 or any('*' in p for p in local_rekey_task['allowed_paths'])):
                    extension_errors.append('APBRA-160 local rekey must retain exactly three literal product paths')
                if (local_rekey_task['task_id'], local_rekey_task['assigned_agent'], local_rekey_task['branch'], local_rekey_task['base_commit']) != ('APBRA-160', 'APBRA-DEVOPS', LOCAL_RECOVERY_BRANCH, '356041b4464a500a2ca126bd1d95298405ffe934'):
                    extension_errors.append('APBRA-160 local rekey identity differs')
                if hashlib.sha256(json.dumps(sources, sort_keys=True, separators=(',', ':')).encode()).hexdigest() != LOCAL_RECOVERY_ALL_SOURCES_SHA256:
                    extension_errors.append('APBRA-160 local rekey historical source register changed')
                matches = [row for row in sources['sources'] if row.get('id') == 'mvp1-model-led-clarification-flexible-generation-delivery-guide']
                if len(matches) != 1 or hashlib.sha256(json.dumps(matches[0], sort_keys=True, separators=(',', ':')).encode()).hexdigest() != LOCAL_RECOVERY_SOURCE_SHA256:
                    extension_errors.append('APBRA-160 local rekey historical source binding differs')
            errors += extension_errors
            if extension_errors:
                local_rekey_task = None
        provider_retrieval_task = None
        provider_retrieval_path = root / 'tasks/APBRA-160-provider-retrieval.json'
        if provider_retrieval_path.exists():
            provider_retrieval_task = load_json(provider_retrieval_path)
            extension_errors = schema_errors(
                load_json(root / 'contracts/engineering/task-contract.schema.json'),
                provider_retrieval_task,
            )
            if not extension_errors:
                extension_errors += task_errors(provider_retrieval_task, catalog, sources)
                def provider_registration_digest(value):
                    return hashlib.sha256(json.dumps(
                        value, sort_keys=True, separators=(',', ':'),
                    ).encode()).hexdigest()
                if provider_registration_digest(provider_retrieval_task) != PROVIDER_RETRIEVAL_TASK_SHA256:
                    extension_errors.append('APBRA-160 provider retrieval task binding differs')
                if (provider_retrieval_task['task_id'], provider_retrieval_task['assigned_agent'],
                        provider_retrieval_task['agent_card_version'], provider_retrieval_task['branch'],
                        provider_retrieval_task['base_commit']) != (
                        'APBRA-160', 'APBRA-DEVOPS', '0.1', PROVIDER_RETRIEVAL_BRANCH,
                        'e3f782535e41bef1034222227ef706e1cf0bfac1'):
                    extension_errors.append('APBRA-160 provider retrieval identity/base/branch differs')
                if (set(provider_retrieval_task['allowed_paths']) != PROVIDER_RETRIEVAL_PATHS or
                        len(provider_retrieval_task['allowed_paths']) != len(PROVIDER_RETRIEVAL_PATHS)):
                    extension_errors.append('APBRA-160 provider retrieval requires exact 29 literal paths')
                if provider_retrieval_task['source_ids'] != [row[0] for row in PROVIDER_RETRIEVAL_SOURCES]:
                    extension_errors.append('APBRA-160 provider retrieval requires exact accepted sources')
                for section, expected in PROVIDER_RETRIEVAL_GATE_SHA256.items():
                    if provider_registration_digest(provider_retrieval_task[section]) != expected:
                        extension_errors.append('APBRA-160 provider retrieval changed gate: ' + section)
                if provider_registration_digest(sources) != PROVIDER_RETRIEVAL_ALL_SOURCES_SHA256:
                    extension_errors.append('APBRA-160 provider retrieval historical source register changed')
                for source_id, content_id, version, expected in PROVIDER_RETRIEVAL_SOURCES:
                    source_rows = [row for row in sources['sources'] if row.get('id') == source_id]
                    if (len(source_rows) != 1 or
                            (source_rows[0].get('content_id'), source_rows[0].get('version'),
                             source_rows[0].get('status')) != (content_id, version, 'ACCEPTED') or
                            provider_registration_digest(source_rows[0]) != expected):
                        extension_errors.append('APBRA-160 provider retrieval source binding differs: ' + source_id)
            errors += extension_errors
            if extension_errors:
                provider_retrieval_task = None
        foundry_host_task = None
        foundry_host_path = root / 'tasks/APBRA-160-foundry-host.json'
        if foundry_host_path.exists():
            foundry_host_task = load_json(foundry_host_path)
            extension_errors = schema_errors(
                load_json(root / 'contracts/engineering/task-contract.schema.json'),
                foundry_host_task,
            )
            if not extension_errors:
                extension_errors += task_errors(foundry_host_task, catalog, sources)
                def provider_registration_digest(value):
                    return hashlib.sha256(json.dumps(
                        value, sort_keys=True, separators=(',', ':'),
                    ).encode()).hexdigest()
                if provider_registration_digest(foundry_host_task) != FOUNDRY_HOST_TASK_SHA256:
                    extension_errors.append('APBRA-160 Foundry host task binding differs')
                if (foundry_host_task['task_id'], foundry_host_task['assigned_agent'],
                        foundry_host_task['agent_card_version'], foundry_host_task['branch'],
                        foundry_host_task['base_commit']) != (
                        'APBRA-160', 'APBRA-DEVOPS', '0.1', FOUNDRY_HOST_BRANCH,
                        '78346bb7d253e7f649858f4a251a04d8663670b7'):
                    extension_errors.append('APBRA-160 Foundry host identity/base/branch differs')
                if (set(foundry_host_task['allowed_paths']) != FOUNDRY_HOST_PATHS or
                        len(foundry_host_task['allowed_paths']) != len(FOUNDRY_HOST_PATHS)):
                    extension_errors.append('APBRA-160 Foundry host requires exact six literal paths')
                if foundry_host_task['source_ids'] != [row[0] for row in FOUNDRY_HOST_SOURCES]:
                    extension_errors.append('APBRA-160 Foundry host requires exact accepted sources')
                for section, expected in FOUNDRY_HOST_GATE_SHA256.items():
                    if provider_registration_digest(foundry_host_task[section]) != expected:
                        extension_errors.append('APBRA-160 Foundry host changed gate: ' + section)
                if provider_registration_digest(sources) != FOUNDRY_HOST_ALL_SOURCES_SHA256:
                    extension_errors.append('APBRA-160 Foundry host historical source register changed')
                for source_id, content_id, version, expected in FOUNDRY_HOST_SOURCES:
                    source_rows = [row for row in sources['sources'] if row.get('id') == source_id]
                    if (len(source_rows) != 1 or
                            (source_rows[0].get('content_id'), source_rows[0].get('version'),
                             source_rows[0].get('status')) != (content_id, version, 'ACCEPTED') or
                            provider_registration_digest(source_rows[0]) != expected):
                        extension_errors.append('APBRA-160 Foundry host source binding differs: ' + source_id)
            errors += extension_errors
            if extension_errors:
                foundry_host_task = None
        foundry_schema_task = None
        foundry_schema_path = root / 'tasks/APBRA-160-foundry-structured-output.json'
        if foundry_schema_path.exists():
            foundry_schema_task = load_json(foundry_schema_path)
            extension_errors = schema_errors(
                load_json(root / 'contracts/engineering/task-contract.schema.json'),
                foundry_schema_task,
            )
            if not extension_errors:
                extension_errors += task_errors(foundry_schema_task, catalog, sources)
                canonical_task = json.dumps(
                    foundry_schema_task, sort_keys=True, separators=(',', ':'),
                ).encode()
                if hashlib.sha256(canonical_task).hexdigest() != FOUNDRY_SCHEMA_TASK_SHA256:
                    extension_errors.append('APBRA-160 Foundry contract differs from accepted authority')
                if (
                    foundry_schema_task['task_id'],
                    foundry_schema_task['assigned_agent'],
                    foundry_schema_task['agent_card_version'],
                ) != ('APBRA-160', 'APBRA-DEVOPS', '0.1'):
                    extension_errors.append('Unexpected APBRA-160 Foundry task or agent identity')
                if foundry_schema_task['branch'] != FOUNDRY_SCHEMA_BRANCH:
                    extension_errors.append('Unexpected APBRA-160 Foundry implementation branch')
                if foundry_schema_task['base_commit'] != 'efb11f5004961ceff9318d6d6f12f88ecd7b2c4a':
                    extension_errors.append('Stale APBRA-160 Foundry registration base')
                if (
                    set(foundry_schema_task['allowed_paths']) != FOUNDRY_SCHEMA_PATHS
                    or len(foundry_schema_task['allowed_paths']) != len(FOUNDRY_SCHEMA_PATHS)
                ):
                    extension_errors.append('Unexpected APBRA-160 Foundry implementation scope')
                if (
                    foundry_schema_task['task_mode'],
                    foundry_schema_task['readiness'],
                    foundry_schema_task['owner_acceptance'],
                ) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('APBRA-160 Foundry requires issued implementation acceptance')
                if foundry_schema_task['source_ids'] != [row[0] for row in FOUNDRY_SCHEMA_SOURCES]:
                    extension_errors.append('APBRA-160 Foundry requires exact accepted sources')
                for section, expected in FOUNDRY_SCHEMA_GATE_SHA256.items():
                    actual = json.dumps(
                        foundry_schema_task[section], sort_keys=True, separators=(',', ':'),
                    ).encode()
                    if hashlib.sha256(actual).hexdigest() != expected:
                        extension_errors.append('APBRA-160 Foundry safety/review gate differs: ' + section)
                for source_id, content_id, version, expected_sha in FOUNDRY_SCHEMA_SOURCES:
                    rows = [row for row in sources['sources'] if row.get('id') == source_id]
                    if len(rows) != 1:
                        extension_errors.append('APBRA-160 Foundry source missing or duplicated: ' + source_id)
                    else:
                        row = rows[0]
                        actual = hashlib.sha256(json.dumps(
                            row, sort_keys=True, separators=(',', ':'),
                        ).encode()).hexdigest()
                        if actual != expected_sha:
                            extension_errors.append('APBRA-160 Foundry source differs from provenance: ' + source_id)
                        if (row.get('content_id'), row.get('version'), row.get('status')) != (
                            content_id, version, 'ACCEPTED',
                        ):
                            extension_errors.append('APBRA-160 Foundry source binding differs: ' + source_id)
            errors += extension_errors
            if extension_errors:
                foundry_schema_task = None
        demo_ux_task = None
        demo_ux_path = root / 'tasks/APBRA-160-demo-ux.json'
        if demo_ux_path.exists():
            demo_ux_task = load_json(demo_ux_path)
            extension_errors = schema_errors(
                load_json(root / 'contracts/engineering/task-contract.schema.json'),
                demo_ux_task,
            )
            if not extension_errors:
                extension_errors += task_errors(demo_ux_task, catalog, sources)
                canonical_task = json.dumps(
                    demo_ux_task, sort_keys=True, separators=(',', ':'),
                ).encode()
                if hashlib.sha256(canonical_task).hexdigest() != DEMO_UX_TASK_SHA256:
                    extension_errors.append('APBRA-160 demo UX contract differs from accepted authority')
                if (
                    demo_ux_task['task_id'], demo_ux_task['assigned_agent'],
                    demo_ux_task['agent_card_version'], demo_ux_task['branch'],
                    demo_ux_task['base_commit'],
                ) != (
                    'APBRA-160', 'APBRA-DEVOPS', '0.1', DEMO_UX_BRANCH,
                    '6ad7ee7e2d6a16fb71cc8f05ebf35f3affaf49a7',
                ):
                    extension_errors.append('Unexpected APBRA-160 demo UX identity, branch or base')
                if (
                    set(demo_ux_task['allowed_paths']) != DEMO_UX_PATHS
                    or len(demo_ux_task['allowed_paths']) != len(DEMO_UX_PATHS)
                    or any('*' in path for path in demo_ux_task['allowed_paths'])
                ):
                    extension_errors.append('Unexpected APBRA-160 demo UX implementation scope')
                if (
                    demo_ux_task['task_mode'], demo_ux_task['readiness'],
                    demo_ux_task['owner_acceptance'],
                ) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('APBRA-160 demo UX requires issued implementation acceptance')
                if demo_ux_task['source_ids'] != [row[0] for row in DEMO_UX_SOURCES]:
                    extension_errors.append('APBRA-160 demo UX requires exact accepted sources')
                for section, expected in DEMO_UX_GATE_SHA256.items():
                    actual = json.dumps(
                        demo_ux_task[section], sort_keys=True, separators=(',', ':'),
                    ).encode()
                    if hashlib.sha256(actual).hexdigest() != expected:
                        extension_errors.append('APBRA-160 demo UX safety/review gate differs: ' + section)
                for source_id, content_id, version, expected_sha in DEMO_UX_SOURCES:
                    rows = [row for row in sources['sources'] if row.get('id') == source_id]
                    if len(rows) != 1:
                        extension_errors.append('APBRA-160 demo UX source missing or duplicated: ' + source_id)
                    else:
                        row = rows[0]
                        actual = hashlib.sha256(json.dumps(
                            row, sort_keys=True, separators=(',', ':'),
                        ).encode()).hexdigest()
                        if actual != expected_sha or (
                            row.get('content_id'), row.get('version'), row.get('status')
                        ) != (content_id, version, 'ACCEPTED'):
                            extension_errors.append('APBRA-160 demo UX source differs: ' + source_id)
                if (active_task_id == 'APBRA-160' and
                        active_branch in {DEMO_UX_BRANCH, DEMO_UX_REGISTRATION_BRANCH}):
                    vite_path = root / 'apps/web/vite.config.ts'
                    allowed_vite = {DEMO_UX_VITE_ORIGINAL_SHA256, DEMO_UX_VITE_PROXY_SHA256}
                    if active_branch == DEMO_UX_REGISTRATION_BRANCH:
                        allowed_vite = {DEMO_UX_VITE_ORIGINAL_SHA256}
                    elif changed_paths is not None and 'apps/web/vite.config.ts' in changed_paths:
                        allowed_vite = {DEMO_UX_VITE_PROXY_SHA256}
                    if (not vite_path.is_file() or
                            hashlib.sha256(vite_path.read_bytes()).hexdigest() not in allowed_vite):
                        extension_errors.append('APBRA-160 Vite must preserve the exact accepted proxy-only bytes')
            errors += extension_errors
            if extension_errors:
                demo_ux_task = None
        private_content_storage_task = None
        private_content_storage_path = root / 'tasks/APBRA-173-private-content-storage.json'
        if private_content_storage_path.exists():
            private_content_storage_task = load_json(private_content_storage_path)
            extension_errors = schema_errors(
                load_json(root / 'contracts/engineering/task-contract.schema.json'),
                private_content_storage_task,
            )
            if not extension_errors:
                extension_errors += task_errors(private_content_storage_task, catalog, sources)
                canonical_task = json.dumps(
                    private_content_storage_task, sort_keys=True, separators=(',', ':')
                ).encode()
                if hashlib.sha256(canonical_task).hexdigest() != PRIVATE_CONTENT_STORAGE_TASK_SHA256:
                    extension_errors.append('APBRA-173A contract differs from accepted authority')
                if (
                    private_content_storage_task['task_id'],
                    private_content_storage_task['assigned_agent'],
                    private_content_storage_task['agent_card_version'],
                ) != ('APBRA-173', 'APBRA-DEVOPS', '0.1'):
                    extension_errors.append('Unexpected APBRA-173A task or agent identity')
                if private_content_storage_task['branch'] != PRIVATE_CONTENT_STORAGE_BRANCH:
                    extension_errors.append('Unexpected APBRA-173A implementation branch')
                if private_content_storage_task['base_commit'] != '953835bc1f51895cf15e9ae3784f10a5ac2df0d6':
                    extension_errors.append('Stale APBRA-173A registration base')
                if (
                    set(private_content_storage_task['allowed_paths']) != PRIVATE_CONTENT_STORAGE_PATHS
                    or len(private_content_storage_task['allowed_paths']) != len(PRIVATE_CONTENT_STORAGE_PATHS)
                ):
                    extension_errors.append('Unexpected APBRA-173A implementation scope')
                if (
                    private_content_storage_task['task_mode'],
                    private_content_storage_task['readiness'],
                    private_content_storage_task['owner_acceptance'],
                ) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('APBRA-173A requires issued implementation acceptance')
                if private_content_storage_task['source_ids'] != [
                    row[0] for row in PRIVATE_CONTENT_STORAGE_SOURCES
                ]:
                    extension_errors.append('APBRA-173A requires exact accepted sources')
                source_rows = sources['sources']
                historic = source_rows[:PRIVATE_CONTENT_STORAGE_HISTORICAL_SOURCE_COUNT]
                historic_digest = hashlib.sha256(
                    json.dumps(historic, sort_keys=True, separators=(',', ':')).encode()
                ).hexdigest()
                if historic_digest != PRIVATE_CONTENT_STORAGE_HISTORICAL_SOURCES_SHA256:
                    extension_errors.append('APBRA-173A historical source provenance changed')
                new_source_ids = [
                    row.get('id') for row in source_rows[
                        PRIVATE_CONTENT_STORAGE_HISTORICAL_SOURCE_COUNT:
                        PRIVATE_CONTENT_STORAGE_HISTORICAL_SOURCE_COUNT + len(PRIVATE_CONTENT_STORAGE_SOURCES)
                    ]
                ]
                if new_source_ids != [row[0] for row in PRIVATE_CONTENT_STORAGE_SOURCES]:
                    extension_errors.append('APBRA-173A new source ordering differs')
                if (
                    active_branch == PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH
                    and len(source_rows) !=
                    PRIVATE_CONTENT_STORAGE_HISTORICAL_SOURCE_COUNT + len(PRIVATE_CONTENT_STORAGE_SOURCES)
                ):
                    # A historical registration remains valid after a separately
                    # pinned, append-only APBRA-177 source block is registered.
                    later_rows = source_rows[
                        PRIVATE_CONTENT_STORAGE_HISTORICAL_SOURCE_COUNT
                        + len(PRIVATE_CONTENT_STORAGE_SOURCES):
                    ]
                    expected_later = (
                        CURRENT_STATE_DOCS_SOURCES + HOSTED_WEB_RELEASE_SOURCES +
                        CURRENT_DEMO_SOURCES
                    )
                    if (
                        len(later_rows) != len(expected_later)
                        or any(
                            (row.get('id'), hashlib.sha256(
                                json.dumps(row, sort_keys=True, separators=(',', ':')).encode()
                            ).hexdigest()) != (source_id, expected_sha)
                            for row, (source_id, _content_id, _version, expected_sha)
                            in zip(later_rows, expected_later)
                        )
                    ):
                        extension_errors.append('APBRA-173A registration added unrelated source rows')
                for historical_test, expected_sha in PRIVATE_CONTENT_STORAGE_HISTORICAL_TEST_SHA256.items():
                    historical_path = root / historical_test
                    if (
                        not historical_path.is_file()
                        or hashlib.sha256(historical_path.read_bytes()).hexdigest() != expected_sha
                    ):
                        extension_errors.append('APBRA-173A historical test repair differs: ' + historical_test)
                for section, expected in PRIVATE_CONTENT_STORAGE_GATE_SHA256.items():
                    actual = json.dumps(
                        private_content_storage_task[section],
                        sort_keys=True, separators=(',', ':'),
                    ).encode()
                    if hashlib.sha256(actual).hexdigest() != expected:
                        extension_errors.append('APBRA-173A safety/review gate differs: ' + section)
                for source_id, content_id, version, expected_sha in PRIVATE_CONTENT_STORAGE_SOURCES:
                    package_source = next(
                        (source for source in sources['sources'] if source['id'] == source_id),
                        None,
                    )
                    if package_source is None:
                        extension_errors.append('APBRA-173A accepted source is missing: ' + source_id)
                    else:
                        canonical_source = json.dumps(
                            package_source, sort_keys=True, separators=(',', ':')
                        ).encode()
                        if hashlib.sha256(canonical_source).hexdigest() != expected_sha:
                            extension_errors.append(
                                'APBRA-173A source differs from accepted provenance: ' + source_id
                            )
                        if (
                            package_source.get('content_id'),
                            package_source.get('version'),
                            package_source.get('status'),
                        ) != (content_id, version, 'ACCEPTED'):
                            extension_errors.append('APBRA-173A source binding differs: ' + source_id)
            errors += extension_errors
            if extension_errors:
                private_content_storage_task = None
        current_state_docs_task = None
        current_state_docs_path = root / 'tasks/APBRA-177-current-state-docs.json'
        if current_state_docs_path.exists():
            current_state_docs_task = load_json(current_state_docs_path)
            extension_errors = schema_errors(
                load_json(root / 'contracts/engineering/task-contract.schema.json'),
                current_state_docs_task,
            )
            if not extension_errors:
                extension_errors += task_errors(current_state_docs_task, catalog, sources)
                canonical_task = json.dumps(
                    current_state_docs_task, sort_keys=True, separators=(',', ':'),
                ).encode()
                if hashlib.sha256(canonical_task).hexdigest() != CURRENT_STATE_DOCS_TASK_SHA256:
                    extension_errors.append('APBRA-177 contract differs from accepted authority')
                if (
                    current_state_docs_task['task_id'],
                    current_state_docs_task['assigned_agent'],
                    current_state_docs_task['agent_card_version'],
                ) != ('APBRA-177', 'APBRA-DOCS', '0.1'):
                    extension_errors.append('Unexpected APBRA-177 task or agent identity')
                if current_state_docs_task['branch'] != CURRENT_STATE_DOCS_BRANCH:
                    extension_errors.append('Unexpected APBRA-177 documentation branch')
                if current_state_docs_task['base_commit'] != 'a0085713f2cc007db2f53939c7a46082c6799be0':
                    extension_errors.append('Stale APBRA-177 registration base')
                if (
                    set(current_state_docs_task['allowed_paths']) != CURRENT_STATE_DOCS_PATHS
                    or len(current_state_docs_task['allowed_paths']) != len(CURRENT_STATE_DOCS_PATHS)
                ):
                    extension_errors.append('Unexpected APBRA-177 documentation scope')
                if (
                    current_state_docs_task['task_mode'],
                    current_state_docs_task['readiness'],
                    current_state_docs_task['owner_acceptance'],
                ) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('APBRA-177 requires issued documentation acceptance')
                if current_state_docs_task['source_ids'] != [row[0] for row in CURRENT_STATE_DOCS_SOURCES]:
                    extension_errors.append('APBRA-177 requires exact accepted sources')
                source_rows = sources['sources']
                historical = source_rows[:CURRENT_STATE_DOCS_HISTORICAL_SOURCE_COUNT]
                historical_digest = hashlib.sha256(
                    json.dumps(historical, sort_keys=True, separators=(',', ':')).encode()
                ).hexdigest()
                if historical_digest != CURRENT_STATE_DOCS_HISTORICAL_SOURCES_SHA256:
                    extension_errors.append('APBRA-177 historical source provenance changed')
                registered_rows = source_rows[
                    CURRENT_STATE_DOCS_HISTORICAL_SOURCE_COUNT:
                    CURRENT_STATE_DOCS_HISTORICAL_SOURCE_COUNT + len(CURRENT_STATE_DOCS_SOURCES)
                ]
                if [row.get('id') for row in registered_rows] != [row[0] for row in CURRENT_STATE_DOCS_SOURCES]:
                    extension_errors.append('APBRA-177 source ordering differs')
                if (
                    active_branch == CURRENT_STATE_DOCS_REGISTRATION_BRANCH
                    and len(source_rows) !=
                    CURRENT_STATE_DOCS_HISTORICAL_SOURCE_COUNT + len(CURRENT_STATE_DOCS_SOURCES)
                ):
                    later_rows = source_rows[
                        CURRENT_STATE_DOCS_HISTORICAL_SOURCE_COUNT
                        + len(CURRENT_STATE_DOCS_SOURCES):
                    ]
                    if (
                        len(later_rows) != len(HOSTED_WEB_RELEASE_SOURCES + CURRENT_DEMO_SOURCES)
                        or any(
                            (row.get('id'), hashlib.sha256(json.dumps(
                                row, sort_keys=True, separators=(',', ':'),
                            ).encode()).hexdigest()) != (source_id, expected_sha)
                            for row, (source_id, _content_id, _version, expected_sha)
                            in zip(later_rows, HOSTED_WEB_RELEASE_SOURCES + CURRENT_DEMO_SOURCES)
                        )
                    ):
                        extension_errors.append('APBRA-177 registration added unrelated source rows')
                for section, expected in CURRENT_STATE_DOCS_GATE_SHA256.items():
                    actual = json.dumps(
                        current_state_docs_task[section], sort_keys=True, separators=(',', ':'),
                    ).encode()
                    if hashlib.sha256(actual).hexdigest() != expected:
                        extension_errors.append('APBRA-177 safety/review gate differs: ' + section)
                for source_id, content_id, version, expected_sha in CURRENT_STATE_DOCS_SOURCES:
                    rows = [row for row in source_rows if row.get('id') == source_id]
                    if len(rows) != 1:
                        extension_errors.append('APBRA-177 source missing or duplicated: ' + source_id)
                    else:
                        row = rows[0]
                        canonical_source = json.dumps(
                            row, sort_keys=True, separators=(',', ':'),
                        ).encode()
                        if hashlib.sha256(canonical_source).hexdigest() != expected_sha:
                            extension_errors.append('APBRA-177 source differs from provenance: ' + source_id)
                        if (row.get('content_id'), row.get('version'), row.get('status')) != (
                            content_id, version, 'ACCEPTED',
                        ):
                            extension_errors.append('APBRA-177 source binding differs: ' + source_id)
            errors += extension_errors
            if extension_errors:
                current_state_docs_task = None
        hosted_web_release_task = None
        hosted_web_release_path = root / 'tasks/APBRA-173-production-web-release.json'
        if hosted_web_release_path.exists():
            hosted_web_release_task = load_json(hosted_web_release_path)
            extension_errors = schema_errors(
                load_json(root / 'contracts/engineering/task-contract.schema.json'),
                hosted_web_release_task,
            )
            if not extension_errors:
                extension_errors += task_errors(hosted_web_release_task, catalog, sources)
                if hashlib.sha256(json.dumps(
                    hosted_web_release_task, sort_keys=True, separators=(',', ':'),
                ).encode()).hexdigest() != HOSTED_WEB_RELEASE_TASK_SHA256:
                    extension_errors.append('APBRA-173B contract differs from accepted authority')
                if (
                    hosted_web_release_task['task_id'],
                    hosted_web_release_task['assigned_agent'],
                    hosted_web_release_task['agent_card_version'],
                ) != ('APBRA-173', 'APBRA-DEVOPS', '0.1'):
                    extension_errors.append('Unexpected APBRA-173B task or agent identity')
                if hosted_web_release_task['branch'] != HOSTED_WEB_RELEASE_BRANCH:
                    extension_errors.append('Unexpected APBRA-173B implementation branch')
                if hosted_web_release_task['base_commit'] != '714a53e3e26ea85b176dd6990ccd7229d1ab770c':
                    extension_errors.append('Stale APBRA-173B registration base')
                if (set(hosted_web_release_task['allowed_paths']) != HOSTED_WEB_RELEASE_PATHS
                        or len(hosted_web_release_task['allowed_paths']) != len(HOSTED_WEB_RELEASE_PATHS)):
                    extension_errors.append('Unexpected APBRA-173B implementation scope')
                if (
                    hosted_web_release_task['task_mode'],
                    hosted_web_release_task['readiness'],
                    hosted_web_release_task['owner_acceptance'],
                ) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('APBRA-173B requires issued implementation acceptance')
                if hosted_web_release_task['source_ids'] != [row[0] for row in HOSTED_WEB_RELEASE_SOURCES]:
                    extension_errors.append('APBRA-173B requires exact accepted sources')
                source_rows = sources['sources']
                if hashlib.sha256(json.dumps(
                    source_rows[:HOSTED_WEB_RELEASE_HISTORICAL_SOURCE_COUNT],
                    sort_keys=True, separators=(',', ':'),
                ).encode()).hexdigest() != HOSTED_WEB_RELEASE_HISTORICAL_SOURCES_SHA256:
                    extension_errors.append('APBRA-173B historical source provenance changed')
                registered_rows = source_rows[
                    HOSTED_WEB_RELEASE_HISTORICAL_SOURCE_COUNT:
                    HOSTED_WEB_RELEASE_HISTORICAL_SOURCE_COUNT + len(HOSTED_WEB_RELEASE_SOURCES)
                ]
                if [row.get('id') for row in registered_rows] != [row[0] for row in HOSTED_WEB_RELEASE_SOURCES]:
                    extension_errors.append('APBRA-173B source ordering differs')
                if active_branch == HOSTED_WEB_RELEASE_REGISTRATION_BRANCH:
                    later_rows = source_rows[
                        HOSTED_WEB_RELEASE_HISTORICAL_SOURCE_COUNT + len(HOSTED_WEB_RELEASE_SOURCES):
                    ]
                    if (len(later_rows) != len(CURRENT_DEMO_SOURCES) or any(
                        (row.get('id'), hashlib.sha256(json.dumps(
                            row, sort_keys=True, separators=(',', ':'),
                        ).encode()).hexdigest()) != (source_id, expected_sha)
                        for row, (source_id, _content_id, _version, expected_sha)
                        in zip(later_rows, CURRENT_DEMO_SOURCES)
                    )):
                        extension_errors.append('APBRA-173B registration added unrelated source rows')
                for section, expected in HOSTED_WEB_RELEASE_GATE_SHA256.items():
                    actual = hashlib.sha256(json.dumps(
                        hosted_web_release_task[section], sort_keys=True, separators=(',', ':'),
                    ).encode()).hexdigest()
                    if actual != expected:
                        extension_errors.append('APBRA-173B safety/review gate differs: ' + section)
                for source_id, content_id, version, expected_sha in HOSTED_WEB_RELEASE_SOURCES:
                    matching = [row for row in source_rows if row.get('id') == source_id]
                    if len(matching) != 1:
                        extension_errors.append('APBRA-173B source missing or duplicated: ' + source_id)
                    else:
                        row = matching[0]
                        if hashlib.sha256(json.dumps(
                            row, sort_keys=True, separators=(',', ':'),
                        ).encode()).hexdigest() != expected_sha:
                            extension_errors.append('APBRA-173B source differs from provenance: ' + source_id)
                        if (row.get('content_id'), row.get('version'), row.get('status')) != (
                            content_id, version, 'ACCEPTED',
                        ):
                            extension_errors.append('APBRA-173B source binding differs: ' + source_id)
            errors += extension_errors
            if extension_errors:
                hosted_web_release_task = None
        provider_neutral_sso_task = None
        provider_neutral_sso_path = root / 'tasks/APBRA-172-provider-neutral-sso.json'
        if provider_neutral_sso_path.exists():
            provider_neutral_sso_task = load_json(provider_neutral_sso_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), provider_neutral_sso_task)
            if not extension_errors:
                extension_errors += task_errors(provider_neutral_sso_task, catalog, sources)
                canonical_task = json.dumps(provider_neutral_sso_task, sort_keys=True, separators=(',', ':')).encode()
                if hashlib.sha256(canonical_task).hexdigest() != PROVIDER_NEUTRAL_SSO_TASK_SHA256:
                    extension_errors.append('APBRA-172 contract differs from accepted authority')
                if (provider_neutral_sso_task['task_id'], provider_neutral_sso_task['assigned_agent'],
                        provider_neutral_sso_task['agent_card_version']) != ('APBRA-172', 'APBRA-DEVOPS', '0.1'):
                    extension_errors.append('Unexpected APBRA-172 task or agent identity')
                if provider_neutral_sso_task['branch'] != PROVIDER_NEUTRAL_SSO_BRANCH:
                    extension_errors.append('Unexpected APBRA-172 implementation branch')
                if provider_neutral_sso_task['base_commit'] != '613e43a9a9040428630d73f6ab12fd930f29d830':
                    extension_errors.append('Stale APBRA-172 registration base')
                if set(provider_neutral_sso_task['allowed_paths']) != PROVIDER_NEUTRAL_SSO_PATHS:
                    extension_errors.append('Unexpected APBRA-172 implementation scope')
                if (provider_neutral_sso_task['task_mode'], provider_neutral_sso_task['readiness'],
                        provider_neutral_sso_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('APBRA-172 requires issued implementation acceptance')
                if provider_neutral_sso_task['source_ids'] != [source_id for source_id, _, _, _ in PROVIDER_NEUTRAL_SSO_SOURCES]:
                    extension_errors.append('APBRA-172 requires its five accepted sources')
                for source_id, content_id, version, expected_sha in PROVIDER_NEUTRAL_SSO_SOURCES:
                    package_source = next((source for source in sources['sources'] if source['id'] == source_id), None)
                    if package_source is None:
                        extension_errors.append('APBRA-172 accepted source is missing: ' + source_id)
                    else:
                        canonical_source = json.dumps(package_source, sort_keys=True, separators=(',', ':')).encode()
                        if hashlib.sha256(canonical_source).hexdigest() != expected_sha:
                            extension_errors.append('APBRA-172 source differs from accepted provenance: ' + source_id)
                        if (package_source.get('content_id') != content_id or
                                package_source.get('version') != version or package_source.get('status') != 'ACCEPTED'):
                            extension_errors.append('APBRA-172 source binding differs: ' + source_id)
            errors += extension_errors
            if extension_errors:
                provider_neutral_sso_task = None
        company_lifecycle_task = None
        company_lifecycle_path = root / 'tasks/APBRA-151-company-lifecycle.json'
        if company_lifecycle_path.exists():
            company_lifecycle_task = load_json(company_lifecycle_path)
            extension_errors = schema_errors(load_json(root / 'contracts/engineering/task-contract.schema.json'), company_lifecycle_task)
            if not extension_errors:
                extension_errors += task_errors(company_lifecycle_task, catalog, sources)
                canonical_task = json.dumps(company_lifecycle_task, sort_keys=True, separators=(',', ':')).encode()
                if hashlib.sha256(canonical_task).hexdigest() != COMPANY_LIFECYCLE_TASK_SHA256:
                    extension_errors.append('APBRA-151 contract differs from accepted authority')
                for field, expected_sha in COMPANY_LIFECYCLE_INITIAL_SETTINGS_GATE_SHA256.items():
                    if not any(hashlib.sha256(item.encode()).hexdigest() == expected_sha
                               for item in company_lifecycle_task[field]):
                        extension_errors.append('APBRA-151 initial Tenant Settings gate missing or weakened: ' + field)
                for field, expected_sha in COMPANY_LIFECYCLE_AMENDMENT_GATE_SHA256.items():
                    if not any(hashlib.sha256(item.encode()).hexdigest() == expected_sha
                               for item in company_lifecycle_task[field]):
                        extension_errors.append('APBRA-151 Vite amendment merge gate missing or weakened: ' + field)
                for field, expected_sha in COMPANY_LIFECYCLE_INVITATION_TEST_AMENDMENT_GATE_SHA256.items():
                    if not any(hashlib.sha256(item.encode()).hexdigest() == expected_sha
                               for item in company_lifecycle_task[field]):
                        extension_errors.append('APBRA-151 invitation-test amendment merge gate missing or weakened: ' + field)
                if (company_lifecycle_task['task_id'], company_lifecycle_task['assigned_agent'],
                        company_lifecycle_task['agent_card_version']) != ('APBRA-151', 'APBRA-DEVOPS', '0.1'):
                    extension_errors.append('Unexpected APBRA-151 task or agent identity')
                if company_lifecycle_task['branch'] != COMPANY_LIFECYCLE_BRANCH:
                    extension_errors.append('Unexpected APBRA-151 implementation branch')
                if company_lifecycle_task['base_commit'] != '9e90bcc3c716dc2d24bb58192096d2429d531043':
                    extension_errors.append('Stale APBRA-151 registration base')
                if (set(company_lifecycle_task['allowed_paths']) != COMPANY_LIFECYCLE_PATHS or
                        len(company_lifecycle_task['allowed_paths']) != len(COMPANY_LIFECYCLE_PATHS)):
                    extension_errors.append('Unexpected APBRA-151 implementation scope')
                if (company_lifecycle_task['task_mode'], company_lifecycle_task['readiness'],
                        company_lifecycle_task['owner_acceptance']) != ('IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED'):
                    extension_errors.append('APBRA-151 requires issued implementation acceptance')
                if company_lifecycle_task['source_ids'] != [source_id for source_id, _, _, _ in COMPANY_LIFECYCLE_SOURCES]:
                    extension_errors.append('APBRA-151 requires its seven accepted sources')
                for source_id, content_id, version, expected_sha in COMPANY_LIFECYCLE_SOURCES:
                    package_source = next((source for source in sources['sources'] if source['id'] == source_id), None)
                    if package_source is None:
                        extension_errors.append('APBRA-151 accepted source is missing: ' + source_id)
                    else:
                        canonical_source = json.dumps(package_source, sort_keys=True, separators=(',', ':')).encode()
                        if hashlib.sha256(canonical_source).hexdigest() != expected_sha:
                            extension_errors.append('APBRA-151 source differs from accepted provenance: ' + source_id)
                        if (package_source.get('content_id') != content_id or
                                package_source.get('version') != version or package_source.get('status') != 'ACCEPTED'):
                            extension_errors.append('APBRA-151 source binding differs: ' + source_id)
            errors += extension_errors
            if extension_errors:
                company_lifecycle_task = None
        # Keep established overlapping Capstone coverage while preventing a
        # newer hash-bound registration from rescuing its historical files.
        legacy_authorities = (
            (shell_task, CAPSTONE_SHELL_PATHS),
            (requirements_task, CAPSTONE_REQUIREMENTS_PATHS),
            (knowledge_task, CAPSTONE_KNOWLEDGE_PATHS),
            (design_task, CAPSTONE_DESIGN_PATHS),
            (generation_task, CAPSTONE_GENERATION_PATHS),
            (validation_task, CAPSTONE_VALIDATION_PATHS),
            (governance_task, CAPSTONE_GOVERNANCE_PATHS),
            (orchestration_task, CAPSTONE_ORCHESTRATION_PATHS),
            (evaluation_task, CAPSTONE_EVALUATION_PATHS),
            (deployment_guide_task, DEPLOYMENT_GUIDE_PATHS),
            (ux_task, CAPSTONE_UX_PATHS),
            (measure_resolution_task, MEASURE_RESOLUTION_PATHS),
            (report_design_normalization_task, REPORT_DESIGN_NORMALIZATION_PATHS),
            (capstone_documentation_task, CAPSTONE_DOCUMENTATION_PATHS),
            (measure_contract_pipeline_task, MEASURE_CONTRACT_PIPELINE_PATHS),
            (layout_repair_task, LAYOUT_REPAIR_PATHS),
            (typed_confirmed_requirements_task, TYPED_CONFIRMED_REQUIREMENTS_PATHS),
            (ai_native_clarification_task, AI_NATIVE_CLARIFICATION_PATHS),
            (generic_time_grain_task, GENERIC_TIME_GRAIN_PATHS),
            (post_capstone_mvp_baseline_task, POST_CAPSTONE_MVP_BASELINE_REGISTRATION_PATHS),
            (post_capstone_product_reconciliation_task, POST_CAPSTONE_PRODUCT_RECONCILIATION_PATHS),
            (data_model_documentation_reconciliation_task, DATA_MODEL_DOCUMENTATION_RECONCILIATION_PATHS),
            (confirmation_readiness_integrity_task, CONFIRMATION_READINESS_INTEGRITY_PATHS),
        )
        # Each task object has passed the checks above, or is None if its
        # registration is missing/invalid. Future bound tasks join this ordered
        # sequence without their own whole-tree admission clause or new-file list.
        bound_authorities = (
            (invited_private_case_foundation_task, INVITED_PRIVATE_CASE_FOUNDATION_PATHS),
            (durable_conversation_evidence_acceptance_task, DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_PATHS),
            (protected_generation_output_history_task, PROTECTED_GENERATION_OUTPUT_HISTORY_PATHS),
            (business_friendly_ux_application_shell_task, BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_PATHS),
            (professional_saas_experience_visual_system_task, PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_PATHS),
            (business_user_intelligent_generation_task, BUSINESS_USER_INTELLIGENT_GENERATION_PATHS),
            (model_led_flexible_delivery_task, MODEL_LED_FLEXIBLE_DELIVERY_PATHS),
            (deployment_portability_entitlement_docs_task, DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_PATHS),
            (owner_onboarding_identity_docs_task, OWNER_ONBOARDING_IDENTITY_DOCS_PATHS),
            (provider_neutral_sso_task, PROVIDER_NEUTRAL_SSO_PATHS),
            (company_lifecycle_task, COMPANY_LIFECYCLE_PATHS),
            (candidate_source_safety_task, CANDIDATE_SOURCE_SAFETY_PATHS),
            (local_rekey_task, LOCAL_RECOVERY_PATHS),
            (foundry_schema_task, FOUNDRY_SCHEMA_PATHS),
            (demo_ux_task, DEMO_UX_PATHS),
            (private_content_storage_task, PRIVATE_CONTENT_STORAGE_PATHS),
            (current_state_docs_task, CURRENT_STATE_DOCS_PATHS),
            (hosted_web_release_task, HOSTED_WEB_RELEASE_PATHS),
            (provider_retrieval_task, PROVIDER_RETRIEVAL_PATHS),
            (foundry_host_task, FOUNDRY_HOST_PATHS),
        )
        registered_tasks = {registered['task_id']: registered for registered, _ in
                            legacy_authorities + bound_authorities if registered is not None}
        registered_tasks[task['task_id']] = task
        if active_task_id == 'APBRA-160':
            registered_tasks['APBRA-160'] = (
                task if active_branch in {
                    CURRENT_DEMO_SOURCE_BRANCH, APBRA160_CI_CAPACITY_BRANCH,
                }
                else foundry_host_task if active_branch in {FOUNDRY_HOST_BRANCH, FOUNDRY_HOST_REGISTRATION_BRANCH}
                else local_rekey_task if active_branch in {LOCAL_RECOVERY_BRANCH, LOCAL_RECOVERY_REGISTRATION_BRANCH}
                else demo_ux_task if active_branch in {
                    DEMO_UX_BRANCH, DEMO_UX_REGISTRATION_BRANCH,
                } else provider_retrieval_task if active_branch in {
                    PROVIDER_RETRIEVAL_BRANCH, PROVIDER_RETRIEVAL_REGISTRATION_BRANCH,
                } else foundry_schema_task
            )
        if active_task_id == 'APBRA-173':
            registered_tasks['APBRA-173'] = (
                private_content_storage_task if active_branch in {
                    PRIVATE_CONTENT_STORAGE_BRANCH, PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH
                } else hosted_web_release_task
            )
        if changed_paths is not None and changed_paths:
            active_task = registered_tasks.get(active_task_id or '')
            if active_task_id is None:
                errors.append('Active task identity missing for changed paths')
            elif not re.fullmatch(r'APBRA-[1-9][0-9]*', active_task_id):
                errors.append('Malformed active task identity: ' + active_task_id)
            elif active_task is None:
                errors.append('Unknown or invalid active task authority: ' + active_task_id)
            if active_branch is None:
                errors.append('Active task branch identity missing for changed paths')
                active_task = None
            elif (active_task is not None and active_task['branch'] != active_branch and
                    not (active_task_id == 'APBRA-164' and
                         active_branch == PROTECTED_GENERATION_OUTPUT_HISTORY_AMENDMENT_BRANCH and
                         changed_paths == PROTECTED_GENERATION_OUTPUT_HISTORY_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-169' and
                         active_branch == BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_AMENDMENT_BRANCH and
                         changed_paths == BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-171' and
                         active_branch == BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_BRANCH and
                         changed_paths == BUSINESS_USER_INTELLIGENT_GENERATION_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-171' and
                         active_branch == BUSINESS_USER_INTELLIGENT_GENERATION_COMPILER_FIXTURE_AMENDMENT_BRANCH and
                         changed_paths == BUSINESS_USER_INTELLIGENT_GENERATION_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-174' and
                         active_branch == MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_BRANCH and
                         changed_paths == MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-174' and
                         active_branch == MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_BRANCH and
                         changed_paths == MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_PATHS) and
                    not (active_task_id == 'APBRA-174' and
                         active_branch == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_REGISTRATION_BRANCH and
                         changed_paths == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-174' and
                         active_branch == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_BRANCH and
                         changed_paths == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_PATHS) and
                    not (active_task_id == 'APBRA-175' and
                         active_branch == DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_BRANCH and
                         changed_paths == DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-176' and
                         active_branch == OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_BRANCH and
                         changed_paths == OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-172' and
                         active_branch == PROVIDER_NEUTRAL_SSO_REGISTRATION_BRANCH and
                         changed_paths == PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-108' and
                         active_branch == CANDIDATE_SOURCE_SAFETY_REGISTRATION_BRANCH and
                         changed_paths == CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-160' and
                         active_branch == LOCAL_RECOVERY_REGISTRATION_BRANCH and
                         changed_paths == LOCAL_RECOVERY_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-160' and
                         active_branch == PROVIDER_RETRIEVAL_REGISTRATION_BRANCH and
                         changed_paths == PROVIDER_RETRIEVAL_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-160' and
                         active_branch == FOUNDRY_HOST_REGISTRATION_BRANCH and
                         changed_paths == FOUNDRY_HOST_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-160' and
                         active_branch == FOUNDRY_SCHEMA_REGISTRATION_BRANCH and
                         changed_paths == FOUNDRY_SCHEMA_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-160' and
                         active_branch == DEMO_UX_REGISTRATION_BRANCH and
                         changed_paths == DEMO_UX_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-173' and
                         active_branch == PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH and
                         changed_paths == PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-173' and
                         active_branch == HOSTED_WEB_RELEASE_REGISTRATION_BRANCH and
                         changed_paths == HOSTED_WEB_RELEASE_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-177' and
                         active_branch == CURRENT_STATE_DOCS_REGISTRATION_BRANCH and
                         changed_paths == CURRENT_STATE_DOCS_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-151' and
                         active_branch == COMPANY_LIFECYCLE_REGISTRATION_BRANCH and
                         changed_paths == COMPANY_LIFECYCLE_REGISTRATION_PATHS) and
                    not (active_task_id == 'APBRA-151' and
                         active_branch == COMPANY_LIFECYCLE_AMENDMENT_BRANCH and
                         changed_paths == COMPANY_LIFECYCLE_AMENDMENT_PATHS) and
                    not (active_task_id == 'APBRA-151' and
                         active_branch == COMPANY_LIFECYCLE_INVITATION_TEST_AMENDMENT_BRANCH and
                         changed_paths == COMPANY_LIFECYCLE_INVITATION_TEST_AMENDMENT_PATHS) and
                    not (active_task_id == 'APBRA-160' and
                         active_branch == CURRENT_DEMO_SOURCE_BRANCH and
                         changed_paths == CURRENT_DEMO_SOURCE_PATHS) and
                    not (active_task_id == 'APBRA-160' and
                         active_branch == APBRA160_CI_CAPACITY_BRANCH and
                         changed_paths == APBRA160_CI_CAPACITY_PATHS)):
                errors.append('Active branch conflicts with task authority: ' + active_branch)
                active_task = None
            if (active_task_id == 'APBRA-160' and
                    active_branch == PROVIDER_RETRIEVAL_REGISTRATION_BRANCH and
                    changed_paths != PROVIDER_RETRIEVAL_REGISTRATION_PATHS):
                errors.append('APBRA-160 provider retrieval registration must change exactly three governance files')
            if (active_task_id == 'APBRA-160' and
                    active_branch == PROVIDER_RETRIEVAL_BRANCH and
                    changed_paths.intersection(PROVIDER_RETRIEVAL_REGISTRATION_PATHS)):
                errors.append('APBRA-160 provider retrieval implementation cannot change governance files')
            if (active_task_id == 'APBRA-160' and
                    active_branch == FOUNDRY_HOST_REGISTRATION_BRANCH and
                    changed_paths != FOUNDRY_HOST_REGISTRATION_PATHS):
                errors.append('APBRA-160 Foundry host registration must change exactly three governance files')
            if (active_task_id == 'APBRA-160' and
                    active_branch == FOUNDRY_HOST_BRANCH and
                    changed_paths.intersection(FOUNDRY_HOST_REGISTRATION_PATHS)):
                errors.append('APBRA-160 Foundry host implementation cannot change governance files')
            if active_task_id == 'APBRA-160' and active_branch == LOCAL_RECOVERY_REGISTRATION_BRANCH and changed_paths != LOCAL_RECOVERY_REGISTRATION_PATHS:
                errors.append('APBRA-160 local rekey registration must change exactly three governance files')
            if active_task_id == 'APBRA-160' and active_branch == LOCAL_RECOVERY_BRANCH and changed_paths.intersection(LOCAL_RECOVERY_REGISTRATION_PATHS):
                errors.append('APBRA-160 local rekey implementation cannot change registration files')
            if (active_task_id == 'APBRA-160' and
                    active_branch == CURRENT_DEMO_SOURCE_BRANCH and
                    changed_paths != CURRENT_DEMO_SOURCE_PATHS):
                errors.append('APBRA-160 current-source amendment must change exactly four governance files')
            if (active_task_id == 'APBRA-160' and
                    active_branch == APBRA160_CI_CAPACITY_BRANCH and
                    changed_paths != APBRA160_CI_CAPACITY_PATHS):
                errors.append('APBRA-160 CI-capacity amendment must change exactly four policy files')
            if (active_task_id == 'APBRA-148' and
                    changed_paths.intersection(POST_CAPSTONE_PRODUCT_RECONCILIATION_REGISTRATION_PATHS) and
                    changed_paths.intersection(POST_CAPSTONE_PRODUCT_RECONCILIATION_PATHS)):
                errors.append('APBRA-148 registration and documentation implementation changes must remain separate')
            if (active_task_id == 'APBRA-159' and
                    changed_paths.intersection(DATA_MODEL_DOCUMENTATION_RECONCILIATION_REGISTRATION_PATHS) and
                    changed_paths.intersection(DATA_MODEL_DOCUMENTATION_RECONCILIATION_PATHS)):
                errors.append('APBRA-159 registration and documentation implementation changes must remain separate')
            if (active_task_id == 'APBRA-147' and
                    changed_paths.intersection(CONFIRMATION_READINESS_INTEGRITY_REGISTRATION_PATHS) and
                    changed_paths.intersection(CONFIRMATION_READINESS_INTEGRITY_PATHS)):
                errors.append('APBRA-147 registration and implementation changes must remain separate')
            if (active_task_id == 'APBRA-162' and
                    changed_paths.intersection(INVITED_PRIVATE_CASE_FOUNDATION_REGISTRATION_PATHS) and
                    changed_paths.intersection(INVITED_PRIVATE_CASE_FOUNDATION_PATHS)):
                errors.append('APBRA-162 registration and implementation changes must remain separate')
            if (active_task_id == 'APBRA-162' and
                    changed_paths.intersection(INVITED_PRIVATE_CASE_FOUNDATION_REGISTRATION_PATHS) and
                    changed_paths != INVITED_PRIVATE_CASE_FOUNDATION_REGISTRATION_PATHS):
                errors.append('APBRA-162 registration must change exactly its four governance files')
            if (active_task_id == 'APBRA-163' and
                    changed_paths.intersection(DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_REGISTRATION_PATHS) and
                    changed_paths.intersection(DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_PATHS) and
                    changed_paths != DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_CAPACITY_AMENDMENT_PATHS):
                errors.append('APBRA-163 registration and implementation changes must remain separate')
            if (active_task_id == 'APBRA-163' and
                    changed_paths.intersection(DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_REGISTRATION_PATHS) and
                    changed_paths not in (
                        DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_REGISTRATION_PATHS,
                        DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_AMENDMENT_PATHS,
                        DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_CAPACITY_AMENDMENT_PATHS)):
                errors.append('APBRA-163 registration must change exactly its five governance files')
            if (active_task_id == 'APBRA-163' and
                    changed_paths == DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_CAPACITY_AMENDMENT_PATHS):
                workflow = root / '.github/workflows/bootstrap.yml'
                if (not workflow.is_file() or workflow.is_symlink() or
                        hashlib.sha256(workflow.read_bytes()).hexdigest() !=
                        DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_CAPACITY_WORKFLOW_SHA256):
                    errors.append('APBRA-163 capacity amendment permits only the accepted 20-minute workflow')
            if (active_task_id == 'APBRA-164' and
                    changed_paths.intersection(PROTECTED_GENERATION_OUTPUT_HISTORY_REGISTRATION_PATHS) and
                    changed_paths.intersection(PROTECTED_GENERATION_OUTPUT_HISTORY_PATHS)):
                errors.append('APBRA-164 registration and implementation changes must remain separate')
            if (active_task_id == 'APBRA-164' and
                    changed_paths.intersection(PROTECTED_GENERATION_OUTPUT_HISTORY_REGISTRATION_PATHS) and
                    changed_paths != PROTECTED_GENERATION_OUTPUT_HISTORY_REGISTRATION_PATHS):
                errors.append('APBRA-164 registration must change exactly its five governance files')
            if (active_task_id == 'APBRA-169' and
                    changed_paths.intersection(BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_REGISTRATION_PATHS) and
                    changed_paths.intersection(BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_PATHS)):
                errors.append('APBRA-169 registration and implementation changes must remain separate')
            if (active_task_id == 'APBRA-169' and
                    changed_paths.intersection(BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_REGISTRATION_PATHS) and
                    changed_paths != BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_REGISTRATION_PATHS):
                errors.append('APBRA-169 registration must change exactly its five governance files')
            if (active_task_id == 'APBRA-170' and
                    changed_paths.intersection(PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_REGISTRATION_PATHS) and
                    changed_paths.intersection(PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_PATHS)):
                errors.append('APBRA-170 registration and implementation changes must remain separate')
            if (active_task_id == 'APBRA-170' and
                    changed_paths.intersection(PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_REGISTRATION_PATHS) and
                    changed_paths != PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_REGISTRATION_PATHS):
                errors.append('APBRA-170 registration must change exactly its five governance files')
            if (active_task_id == 'APBRA-171' and
                    changed_paths.intersection(BUSINESS_USER_INTELLIGENT_GENERATION_REGISTRATION_PATHS) and
                    changed_paths.intersection(BUSINESS_USER_INTELLIGENT_GENERATION_PATHS)):
                errors.append('APBRA-171 registration and implementation changes must remain separate')
            if (active_task_id == 'APBRA-171' and
                    changed_paths.intersection(BUSINESS_USER_INTELLIGENT_GENERATION_REGISTRATION_PATHS) and
                    changed_paths != BUSINESS_USER_INTELLIGENT_GENERATION_REGISTRATION_PATHS):
                errors.append('APBRA-171 registration must change exactly its five governance files')
            if (active_task_id == 'APBRA-174' and
                    changed_paths.intersection(MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS) and
                    changed_paths.intersection(MODEL_LED_FLEXIBLE_DELIVERY_PATHS)):
                errors.append('APBRA-174 registration and implementation changes must remain separate')
            if (active_task_id == 'APBRA-174' and
                    changed_paths.intersection(MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS) and
                    changed_paths != MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS and
                    not (active_branch == MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_BRANCH and
                         changed_paths == MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_PATHS) and
                    not (active_branch == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_REGISTRATION_BRANCH and
                         changed_paths == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_REGISTRATION_PATHS) and
                    not (active_branch == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_BRANCH and
                         changed_paths == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_PATHS)):
                errors.append('APBRA-174 registration must change exactly its eight governance files')
            if (active_task_id == 'APBRA-174' and
                    active_branch == MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_BRANCH and
                    changed_paths != MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_PATHS):
                errors.append('APBRA-174 Vite proxy amendment must change exactly its eight governance files')
            if (active_task_id == 'APBRA-174' and
                    active_branch == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_REGISTRATION_BRANCH and
                    changed_paths != MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_REGISTRATION_PATHS):
                errors.append('APBRA-174 CI capacity registration must change exactly its five governance files')
            if (active_task_id == 'APBRA-174' and
                    active_branch == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_BRANCH and
                    changed_paths != MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_PATHS):
                errors.append('APBRA-174 CI capacity implementation must change exactly its five functional files')
            if (active_task_id == 'APBRA-174' and
                    active_branch == MODEL_LED_FLEXIBLE_DELIVERY_BRANCH and
                    changed_paths.intersection(MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_PATHS)):
                errors.append('APBRA-174 product branch cannot change CI capacity files')
            if (active_task_id == 'APBRA-175' and
                    changed_paths.intersection(DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_PATHS) and
                    changed_paths.intersection(DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_PATHS)):
                errors.append('APBRA-175 registration and documentation changes must remain separate')
            if (active_task_id == 'APBRA-175' and
                    active_branch == DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_BRANCH and
                    changed_paths != DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_PATHS):
                errors.append('APBRA-175 registration must change exactly its five governance files')
            if (active_task_id == 'APBRA-175' and
                    active_branch == DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_BRANCH and
                    changed_paths.intersection(DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_PATHS)):
                errors.append('APBRA-175 documentation branch cannot change governance registration files')
            if (active_task_id == 'APBRA-176' and
                    changed_paths.intersection(OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_PATHS) and
                    changed_paths.intersection(OWNER_ONBOARDING_IDENTITY_DOCS_PATHS)):
                errors.append('APBRA-176 registration and documentation changes must remain separate')
            if (active_task_id == 'APBRA-176' and
                    active_branch == OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_BRANCH and
                    changed_paths != OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_PATHS):
                errors.append('APBRA-176 registration must change exactly its six governance files')
            if (active_task_id == 'APBRA-176' and
                    active_branch == OWNER_ONBOARDING_IDENTITY_DOCS_BRANCH and
                    changed_paths.intersection(OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_PATHS)):
                errors.append('APBRA-176 documentation branch cannot change governance registration files')
            if (active_task_id == 'APBRA-108' and
                    changed_paths.intersection(CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS) and
                    changed_paths.intersection(CANDIDATE_SOURCE_SAFETY_PATHS)):
                errors.append('APBRA-108 registration and implementation changes must remain separate')
            if (active_task_id == 'APBRA-108' and
                    active_branch == CANDIDATE_SOURCE_SAFETY_REGISTRATION_BRANCH and
                    changed_paths != CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS):
                errors.append('APBRA-108 registration must change exactly its five governance files')
            if (active_task_id == 'APBRA-108' and
                    active_branch == CANDIDATE_SOURCE_SAFETY_BRANCH and
                    changed_paths.intersection(CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS)):
                errors.append('APBRA-108 implementation branch cannot change governance registration files')
            if (active_task_id == 'APBRA-160' and
                    changed_paths.intersection(FOUNDRY_SCHEMA_REGISTRATION_PATHS) and
                    changed_paths.intersection(FOUNDRY_SCHEMA_PATHS)):
                errors.append('APBRA-160 Foundry registration and implementation must remain separate')
            if (active_task_id == 'APBRA-160' and
                    active_branch == FOUNDRY_SCHEMA_REGISTRATION_BRANCH and
                    changed_paths != FOUNDRY_SCHEMA_REGISTRATION_PATHS):
                errors.append('APBRA-160 Foundry registration must change exactly five governance files')
            if (active_task_id == 'APBRA-160' and
                    active_branch == FOUNDRY_SCHEMA_BRANCH and
                    changed_paths.intersection(FOUNDRY_SCHEMA_REGISTRATION_PATHS)):
                errors.append('APBRA-160 Foundry implementation cannot change governance files')
            if (active_task_id == 'APBRA-160' and
                    changed_paths.intersection(DEMO_UX_REGISTRATION_PATHS) and
                    changed_paths.intersection(DEMO_UX_PATHS)):
                errors.append('APBRA-160 demo UX registration and implementation must remain separate')
            if (active_task_id == 'APBRA-160' and
                    active_branch == DEMO_UX_REGISTRATION_BRANCH and
                    changed_paths != DEMO_UX_REGISTRATION_PATHS):
                errors.append('APBRA-160 demo UX registration must change exactly three governance files')
            if (active_task_id == 'APBRA-160' and
                    active_branch == DEMO_UX_BRANCH and
                    changed_paths.intersection(DEMO_UX_REGISTRATION_PATHS)):
                errors.append('APBRA-160 demo UX implementation cannot change governance files')
            if (active_task_id == 'APBRA-173' and
                    active_branch in {PRIVATE_CONTENT_STORAGE_BRANCH, PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH} and
                    changed_paths.intersection(PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS) and
                    changed_paths.intersection(PRIVATE_CONTENT_STORAGE_PATHS)):
                errors.append('APBRA-173A registration and implementation changes must remain separate')
            if (active_task_id == 'APBRA-173' and
                    active_branch == PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH and
                    changed_paths != PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS):
                errors.append('APBRA-173A registration must change exactly its nine governance files')
            if (active_task_id == 'APBRA-173' and
                    active_branch == PRIVATE_CONTENT_STORAGE_BRANCH and
                    changed_paths.intersection(PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS)):
                errors.append('APBRA-173A implementation branch cannot change governance registration files')
            if (active_task_id == 'APBRA-173' and
                    active_branch == HOSTED_WEB_RELEASE_REGISTRATION_BRANCH and
                    changed_paths != HOSTED_WEB_RELEASE_REGISTRATION_PATHS):
                errors.append('APBRA-173B registration must change exactly its five governance files')
            if (active_task_id == 'APBRA-173' and
                    active_branch == HOSTED_WEB_RELEASE_REGISTRATION_BRANCH and
                    changed_paths.intersection(HOSTED_WEB_RELEASE_PATHS - {'scripts/check_bootstrap.py'})):
                errors.append('APBRA-173B registration and implementation changes must remain separate')
            if (active_task_id == 'APBRA-173' and
                    active_branch == HOSTED_WEB_RELEASE_BRANCH and
                    changed_paths.intersection(HOSTED_WEB_RELEASE_REGISTRATION_PATHS - {'scripts/check_bootstrap.py'})):
                errors.append('APBRA-173B implementation branch cannot change governance registration files')
            if (active_task_id == 'APBRA-177' and
                    changed_paths.intersection(CURRENT_STATE_DOCS_REGISTRATION_PATHS) and
                    changed_paths.intersection(CURRENT_STATE_DOCS_PATHS)):
                errors.append('APBRA-177 registration and documentation changes must remain separate')
            if (active_task_id == 'APBRA-177' and
                    active_branch == CURRENT_STATE_DOCS_REGISTRATION_BRANCH and
                    changed_paths != CURRENT_STATE_DOCS_REGISTRATION_PATHS):
                errors.append('APBRA-177 registration must change exactly its five governance files')
            if (active_task_id == 'APBRA-177' and
                    active_branch == CURRENT_STATE_DOCS_BRANCH and
                    changed_paths.intersection(CURRENT_STATE_DOCS_REGISTRATION_PATHS)):
                errors.append('APBRA-177 documentation branch cannot change governance registration files')
            if (active_task_id == 'APBRA-172' and
                    changed_paths.intersection(PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS) and
                    changed_paths.intersection(PROVIDER_NEUTRAL_SSO_PATHS)):
                errors.append('APBRA-172 registration and implementation changes must remain separate')
            if (active_task_id == 'APBRA-172' and
                    active_branch == PROVIDER_NEUTRAL_SSO_REGISTRATION_BRANCH and
                    changed_paths != PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS):
                errors.append('APBRA-172 registration must change exactly its seven governance files')
            if (active_task_id == 'APBRA-172' and
                    active_branch == PROVIDER_NEUTRAL_SSO_BRANCH and
                    changed_paths.intersection(PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS)):
                errors.append('APBRA-172 implementation branch cannot change governance registration files')
            if (active_task_id == 'APBRA-151' and
                    changed_paths.intersection(COMPANY_LIFECYCLE_REGISTRATION_PATHS) and
                    changed_paths.intersection(COMPANY_LIFECYCLE_PATHS)):
                errors.append('APBRA-151 registration and implementation changes must remain separate')
            if (active_task_id == 'APBRA-151' and
                    active_branch == COMPANY_LIFECYCLE_REGISTRATION_BRANCH and
                    changed_paths != COMPANY_LIFECYCLE_REGISTRATION_PATHS):
                errors.append('APBRA-151 registration must change exactly its eight governance files')
            if (active_task_id == 'APBRA-151' and
                    active_branch == COMPANY_LIFECYCLE_AMENDMENT_BRANCH and
                    changed_paths != COMPANY_LIFECYCLE_AMENDMENT_PATHS):
                errors.append('APBRA-151 Vite amendment must change exactly its three governance files')
            if (active_task_id == 'APBRA-151' and
                    active_branch == COMPANY_LIFECYCLE_INVITATION_TEST_AMENDMENT_BRANCH and
                    changed_paths != COMPANY_LIFECYCLE_INVITATION_TEST_AMENDMENT_PATHS):
                errors.append('APBRA-151 invitation-test amendment must change exactly its three governance files')
            if (active_task_id == 'APBRA-151' and
                    active_branch == COMPANY_LIFECYCLE_BRANCH and
                    changed_paths.intersection(COMPANY_LIFECYCLE_REGISTRATION_PATHS)):
                errors.append('APBRA-151 implementation branch cannot change governance registration files')
            if (active_task_id == 'APBRA-162' and
                    'tests/bootstrap/test_bootstrap.py' in changed_paths):
                bootstrap_fix = root / 'tests/bootstrap/test_bootstrap.py'
                if (not bootstrap_fix.is_file() or bootstrap_fix.is_symlink() or
                        hashlib.sha256(bootstrap_fix.read_bytes()).hexdigest() !=
                        INVITED_PRIVATE_CASE_FOUNDATION_BOOTSTRAP_FIX_SHA256):
                    errors.append('APBRA-162 permits only the accepted test_product_file_is_not_bootstrap fixture correction')
            for name in sorted(changed_paths):
                if not valid_path(name) or not (
                    (active_task is not None and path_allowed(name, active_task, card)) or
                    (active_task_id == 'APBRA-140' and
                     name in CAPSTONE_DOCUMENTATION_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-141' and
                     name in MEASURE_CONTRACT_PIPELINE_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-142' and
                     name in LAYOUT_REPAIR_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-143' and
                     name in TYPED_CONFIRMED_REQUIREMENTS_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-144' and
                     name in AI_NATIVE_CLARIFICATION_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-145' and
                     name in GENERIC_TIME_GRAIN_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-146' and
                     name in POST_CAPSTONE_MVP_BASELINE_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-148' and
                     name in POST_CAPSTONE_PRODUCT_RECONCILIATION_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-159' and
                     name in DATA_MODEL_DOCUMENTATION_RECONCILIATION_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-147' and
                     name in CONFIRMATION_READINESS_INTEGRITY_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-162' and
                     name in INVITED_PRIVATE_CASE_FOUNDATION_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-163' and
                     name in DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-164' and
                     name in PROTECTED_GENERATION_OUTPUT_HISTORY_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-169' and
                     name in BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-170' and
                     name in PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-171' and
                     name in BUSINESS_USER_INTELLIGENT_GENERATION_REGISTRATION_PATHS and
                     path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-174' and
                         name in MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-174' and
                         name in MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-174' and
                         active_branch == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_REGISTRATION_BRANCH and
                         changed_paths == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_REGISTRATION_PATHS and
                         name in MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-174' and active_task is not None and
                         active_branch == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_BRANCH and
                         changed_paths == MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_PATHS and
                         name in MODEL_LED_FLEXIBLE_DELIVERY_CI_CAPACITY_PATHS and
                         name in active_task['allowed_paths'] and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-175' and active_task is not None and
                         active_branch == DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_BRANCH and
                         changed_paths == DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_PATHS and
                         name in DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-176' and active_task is not None and
                         active_branch == OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_BRANCH and
                         changed_paths == OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_PATHS and
                         name in OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-108' and active_task is not None and
                         active_branch == CANDIDATE_SOURCE_SAFETY_REGISTRATION_BRANCH and
                         changed_paths == CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS and
                         name in CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-160' and active_task is not None and
                         active_branch == LOCAL_RECOVERY_REGISTRATION_BRANCH and
                         changed_paths == LOCAL_RECOVERY_REGISTRATION_PATHS and
                         name in LOCAL_RECOVERY_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-160' and active_task is not None and
                         active_branch == PROVIDER_RETRIEVAL_REGISTRATION_BRANCH and
                         changed_paths == PROVIDER_RETRIEVAL_REGISTRATION_PATHS and
                         name in PROVIDER_RETRIEVAL_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-160' and active_task is not None and
                         active_branch == FOUNDRY_HOST_REGISTRATION_BRANCH and
                         changed_paths == FOUNDRY_HOST_REGISTRATION_PATHS and
                         name in FOUNDRY_HOST_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-160' and active_task is not None and
                         active_branch == FOUNDRY_SCHEMA_REGISTRATION_BRANCH and
                         changed_paths == FOUNDRY_SCHEMA_REGISTRATION_PATHS and
                         name in FOUNDRY_SCHEMA_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-160' and active_task is not None and
                         active_branch == DEMO_UX_REGISTRATION_BRANCH and
                         changed_paths == DEMO_UX_REGISTRATION_PATHS and
                         name in DEMO_UX_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-173' and active_task is not None and
                         active_branch == PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH and
                         changed_paths == PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS and
                         name in PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-173' and active_task is not None and
                         active_branch == HOSTED_WEB_RELEASE_REGISTRATION_BRANCH and
                         changed_paths == HOSTED_WEB_RELEASE_REGISTRATION_PATHS and
                         name in HOSTED_WEB_RELEASE_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-177' and active_task is not None and
                         active_branch == CURRENT_STATE_DOCS_REGISTRATION_BRANCH and
                         changed_paths == CURRENT_STATE_DOCS_REGISTRATION_PATHS and
                         name in CURRENT_STATE_DOCS_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-172' and active_task is not None and
                         active_branch == PROVIDER_NEUTRAL_SSO_REGISTRATION_BRANCH and
                         changed_paths == PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS and
                         name in PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-151' and active_task is not None and
                         active_branch == COMPANY_LIFECYCLE_REGISTRATION_BRANCH and
                         changed_paths == COMPANY_LIFECYCLE_REGISTRATION_PATHS and
                         name in COMPANY_LIFECYCLE_REGISTRATION_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-151' and active_task is not None and
                         active_branch == COMPANY_LIFECYCLE_AMENDMENT_BRANCH and
                         changed_paths == COMPANY_LIFECYCLE_AMENDMENT_PATHS and
                         name in COMPANY_LIFECYCLE_AMENDMENT_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-151' and active_task is not None and
                         active_branch == COMPANY_LIFECYCLE_INVITATION_TEST_AMENDMENT_BRANCH and
                         changed_paths == COMPANY_LIFECYCLE_INVITATION_TEST_AMENDMENT_PATHS and
                         name in COMPANY_LIFECYCLE_INVITATION_TEST_AMENDMENT_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-160' and active_task is not None and
                         active_branch == CURRENT_DEMO_SOURCE_BRANCH and
                         changed_paths == CURRENT_DEMO_SOURCE_PATHS and
                         name in CURRENT_DEMO_SOURCE_PATHS and
                         path_allowed(name, task, card)) or
                    (active_task_id == 'APBRA-160' and active_task is not None and
                         active_branch == APBRA160_CI_CAPACITY_BRANCH and
                         changed_paths == APBRA160_CI_CAPACITY_PATHS and
                         name in APBRA160_CI_CAPACITY_PATHS and
                         path_allowed(name, task, card))
                ):
                    errors.append('File outside active task scope: ' + name)
        manifest = {}
        for file in repo_files(root):
            name = file.relative_to(root).as_posix()
            if file.is_symlink() or not whole_tree_safe(
                    name, task, legacy_authorities, bound_authorities, card):
                errors.append('File outside safe bootstrap scope: ' + name)
                continue
            data = file.read_bytes()
            manifest[name] = hashlib.sha256(data).hexdigest()
            if len(data) > 262144:
                errors.append('Oversize bootstrap file: ' + name)
                continue
            text = data.decode('utf-8')
            if re.search(r'gh[pousr]_[A-Za-z0-9]{36,}', text) or re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', text):
                errors.append('High-confidence credential pattern in: ' + name)
            if file.suffix == '.json':
                load_json(file)
            if file.suffix == '.md':
                for target in re.findall(r'\]\(([^\s)]+)\)', text):
                    if target.startswith(('https://', 'http://', '#', 'mailto:')):
                        continue
                    relative = target.split('#')[0]
                    candidate = root / str(PurePosixPath(name).parent / relative)
                    if not candidate.is_file() or not candidate.resolve().is_relative_to(root.resolve()):
                        errors.append('Broken/unsafe local link: ' + name + ' -> ' + target)
        return errors, manifest
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as exc:
        return ['Checker failure: ' + type(exc).__name__ + ': ' + str(exc)], {}


def delivery_context(root: Path = ROOT) -> tuple[str | None, str | None, set[str]]:
    """Resolve the current branch task and exact Git changes without cumulative authority."""
    branch = os.getenv('GITHUB_HEAD_REF')
    if not branch:
        result = subprocess.run(['git', '-C', str(root), 'branch', '--show-current'], check=True,
                                capture_output=True, text=True, timeout=10)
        branch = result.stdout.strip() or None
    match = re.fullmatch(r'agent/[^/]+/(APBRA-[1-9][0-9]*)-[^/]+', branch or '')
    active_task_id = match.group(1) if match else None
    base_name = os.getenv('GITHUB_BASE_REF') or 'main'
    base_ref = 'origin/' + base_name
    commands = (
        ['git', '-C', str(root), 'diff', '--name-only', '--diff-filter=ACDMRTUXB', base_ref + '...HEAD'],
        ['git', '-C', str(root), 'diff', '--name-only', '--diff-filter=ACDMRTUXB', 'HEAD'],
        ['git', '-C', str(root), 'diff', '--cached', '--name-only', '--diff-filter=ACDMRTUXB'],
        ['git', '-C', str(root), 'ls-files', '--others', '--exclude-standard'],
    )
    changed = set()
    for command in commands:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=10)
        changed.update(line for line in result.stdout.splitlines() if line)
    return active_task_id, branch, changed


def write_report(root: Path, name: str, report: dict) -> None:
    """Create new evidence under artifacts without following symlinks (POSIX)."""
    if not valid_path(name) or not name.startswith('artifacts/'):
        raise ValueError('Report must be a safe relative path under artifacts/')
    root = root.resolve(strict=True)
    parts = name.split('/')
    # Validate every existing component before creating any directories.
    candidate = root
    for index, part in enumerate(parts):
        candidate = candidate / part
        try:
            mode = candidate.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise ValueError('Report path cannot contain symlinks')
        if index == len(parts) - 1:
            raise ValueError('Report already exists; choose a new evidence filename')
        if not stat.S_ISDIR(mode):
            raise ValueError('Report parent must be a directory')
    if not candidate.resolve().is_relative_to(root / 'artifacts'):
        raise ValueError('Report escaped artifacts/')
    # Bind traversal to directory descriptors; never follow a replaced symlink.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(root, flags)
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, flags, dir_fd=directory)
            except FileNotFoundError:
                try:
                    os.mkdir(part, dir_fd=directory)
                except FileExistsError:
                    pass  # A concurrent creator must still pass the no-follow open.
                child = os.open(part, flags, dir_fd=directory)
            os.close(directory)
            directory = child
        output = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
        with os.fdopen(output, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(report, indent=2) + '\n')
    finally:
        os.close(directory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', help='Optional JSON report under artifacts/')
    args = parser.parse_args()
    if args.report and (not valid_path(args.report) or not args.report.startswith('artifacts/')):
        parser.error('Report must be a safe relative path under artifacts/')
    try:
        active_task_id, active_branch, changed_paths = delivery_context()
        errors, manifest = check(active_task_id=active_task_id, active_branch=active_branch,
                                 changed_paths=changed_paths)
    except subprocess.SubprocessError as exc:
        errors, manifest = ['Checker failure: ' + type(exc).__name__ + ': ' + str(exc)], {}
    report = {'scope': 'engineering-bootstrap-only', 'status': 'FAIL' if errors else 'PASS',
              'python': platform.python_version(), 'file_count': len(manifest),
              'file_sha256': manifest, 'findings': errors,
              'github_test_sha': os.getenv('GITHUB_SHA'),
              'pr_head_sha': os.getenv('PR_HEAD_SHA'),
              'claims': {'product_verified': False, 'native_protection_verified': False,
                         'remote_source_freshness_verified': False}}
    if args.report:
        try:
            write_report(ROOT, args.report, report)
        except (OSError, ValueError):
            parser.error('Cannot create report safely; use a new path under artifacts/ without symlinks')
    print(report['status'] + ': engineering bootstrap; ' + str(len(manifest)) + ' files')
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
