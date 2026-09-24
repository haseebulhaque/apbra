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
    exact_apbra_163_ci_policy_test = (
        task.get('task_id') == 'APBRA-163' and
        path == 'tests/bootstrap/test_ci_policy.py' and
        path in task['allowed_paths']
    )
    return valid_path(path) and (not restricted or exact_apbra_163_ci_policy_test) and (
        any(matches(path, p) for p in task['allowed_paths']) and
        any(matches(path, p) for p in card['allowed_paths'])
    )


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
        if job.get('runs-on') != 'ubuntu-24.04' or job.get('timeout-minutes') != '20':
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
        errors += workflow_errors((root / '.github/workflows/bootstrap.yml').read_text())
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
        registered_tasks = {
            registered['task_id']: registered for registered in (
                task, shell_task, requirements_task, knowledge_task, design_task,
                generation_task, validation_task, governance_task,
                orchestration_task, evaluation_task, deployment_guide_task, ux_task,
                measure_resolution_task, report_design_normalization_task,
                capstone_documentation_task, measure_contract_pipeline_task,
                layout_repair_task, typed_confirmed_requirements_task,
                ai_native_clarification_task, generic_time_grain_task,
                post_capstone_mvp_baseline_task,
                post_capstone_product_reconciliation_task,
                data_model_documentation_reconciliation_task,
                confirmation_readiness_integrity_task,
                invited_private_case_foundation_task,
                durable_conversation_evidence_acceptance_task,
            ) if registered is not None
        }
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
            elif active_task is not None and active_task['branch'] != active_branch:
                errors.append('Active branch conflicts with task authority: ' + active_branch)
                active_task = None
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
                     path_allowed(name, task, card))
                ):
                    errors.append('File outside active task scope: ' + name)
        manifest = {}
        for file in repo_files(root):
            name = file.relative_to(root).as_posix()
            if file.is_symlink() or not ((durable_conversation_evidence_acceptance_task is not None and path_allowed(name, durable_conversation_evidence_acceptance_task, card)) or (invited_private_case_foundation_task is not None and path_allowed(name, invited_private_case_foundation_task, card)) or (confirmation_readiness_integrity_task is not None and path_allowed(name, confirmation_readiness_integrity_task, card)) or (data_model_documentation_reconciliation_task is not None and path_allowed(name, data_model_documentation_reconciliation_task, card)) or (post_capstone_product_reconciliation_task is not None and path_allowed(name, post_capstone_product_reconciliation_task, card)) or path_allowed(name, task, card) or (shell_task is not None and path_allowed(name, shell_task, card)) or (requirements_task is not None and path_allowed(name, requirements_task, card)) or (knowledge_task is not None and path_allowed(name, knowledge_task, card)) or (design_task is not None and path_allowed(name, design_task, card)) or (generation_task is not None and path_allowed(name, generation_task, card)) or (validation_task is not None and path_allowed(name, validation_task, card)) or (governance_task is not None and path_allowed(name, governance_task, card)) or (orchestration_task is not None and path_allowed(name, orchestration_task, card)) or (evaluation_task is not None and path_allowed(name, evaluation_task, card)) or (deployment_guide_task is not None and path_allowed(name, deployment_guide_task, card)) or (ux_task is not None and path_allowed(name, ux_task, card)) or (measure_resolution_task is not None and path_allowed(name, measure_resolution_task, card)) or (report_design_normalization_task is not None and path_allowed(name, report_design_normalization_task, card)) or (capstone_documentation_task is not None and path_allowed(name, capstone_documentation_task, card)) or (measure_contract_pipeline_task is not None and path_allowed(name, measure_contract_pipeline_task, card)) or (layout_repair_task is not None and path_allowed(name, layout_repair_task, card)) or (typed_confirmed_requirements_task is not None and path_allowed(name, typed_confirmed_requirements_task, card)) or (ai_native_clarification_task is not None and path_allowed(name, ai_native_clarification_task, card)) or (generic_time_grain_task is not None and path_allowed(name, generic_time_grain_task, card)) or (post_capstone_mvp_baseline_task is not None and path_allowed(name, post_capstone_mvp_baseline_task, card))):
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
