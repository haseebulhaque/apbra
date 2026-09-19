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
    return valid_path(path) and not any(matches(path, p) for p in task['restricted_paths']) and (
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
        if job.get('runs-on') != 'ubuntu-24.04' or job.get('timeout-minutes') != '10':
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


def check(root: Path = ROOT) -> tuple[list[str], dict]:
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
        manifest = {}
        for file in repo_files(root):
            name = file.relative_to(root).as_posix()
            if file.is_symlink() or not (path_allowed(name, task, card) or (shell_task is not None and path_allowed(name, shell_task, card)) or (requirements_task is not None and path_allowed(name, requirements_task, card)) or (knowledge_task is not None and path_allowed(name, knowledge_task, card)) or (design_task is not None and path_allowed(name, design_task, card)) or (generation_task is not None and path_allowed(name, generation_task, card)) or (validation_task is not None and path_allowed(name, validation_task, card)) or (governance_task is not None and path_allowed(name, governance_task, card)) or (orchestration_task is not None and path_allowed(name, orchestration_task, card)) or (evaluation_task is not None and path_allowed(name, evaluation_task, card))):
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
    errors, manifest = check()
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
