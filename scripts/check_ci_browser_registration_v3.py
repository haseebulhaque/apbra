"""Finite CI v3 registration; unfrozen product source never establishes release."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE = '444f4828c87a3a158fc102efae37196540cbbafa'
PRIOR = '647712931331e89b1f5257b6443090f98df84b37'
R = 'agent/APBRA-DEVOPS/APBRA-183-public-governance'
QB = 'agent/APBRA-DEVOPS/APBRA-160-recovered-account-public-v3'
NB = 'agent/APBRA-DEVOPS/APBRA-183-native-organisation-public-v3'
RT = 'tasks/APBRA-183-ci-browser-registration-v3.json'
QT = 'tasks/APBRA-160-recovered-account-public-v3.json'
NT = 'tasks/APBRA-183-native-organisation-public-v3.json'
MANIFEST = 'docs/engineering/recovered-native-frozen-manifests-v3.json'
FIXTURE = 'tests/bootstrap/fixtures/bootstrap-workflow-single-job-647.txt'
SOURCE_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
G = {'scripts/check_bootstrap.py', 'tasks/APBRA-183-native-organisation-public-v2.json', 'tests/bootstrap/test_foundry_qualification_renewal_scope.py', 'tasks/APBRA-183-ci-browser-registration-v3.json', 'tests/bootstrap/test_workflow_secrets.py', 'apps/api/tests/test_foundry_report_runtime.py', 'docs/engineering/recovered-native-public-registration.md', 'tests/bootstrap/test_historical_fixture_staging_20261012_scope.py', 'tasks/APBRA-160-recovered-account-public-v3.json', 'tests/bootstrap/test_native_output_verification_20261019_scope.py', 'tests/bootstrap/test_invited_private_case_foundation_scope.py', 'scripts/check_ci_browser_registration_v3.py', 'tests/bootstrap/fixtures/bootstrap-workflow-single-job-647.txt', 'tests/bootstrap/test_foundry_qualification_renewal_20261011_scope.py', 'tests/bootstrap/test_tenant_document_drafts_20261013_scope.py', 'apps/api/tests/test_foundry_private_preparation.py', 'tests/bootstrap/test_foundry_qualification_scope.py', 'docs/engineering/apbra183-ci-browser-recovery-v3.md', 'scripts/check_ci_policy.py', 'tests/bootstrap/test_bootstrap.py', 'apps/api/tests/test_report_authorization_clock.py', 'scripts/check_recovered_native_registration.py', 'scripts/check_nv.py', 'tests/bootstrap/test_settings_release_proof_scope.py', 'tests/bootstrap/test_ci_browser_registration_v3_scope.py', 'tests/bootstrap/test_knowledge_lifecycle_20261012_scope.py', 'apps/api/tests/conftest.py', 'docs/engineering/recovered-native-frozen-manifests-v3.json', 'tests/bootstrap/test_recovered_native_registration_scope.py', 'apps/api/tests/test_native_contracts.py', 'tests/bootstrap/test_dispatch_audit_20261019_scope.py', 'tasks/APBRA-183-native-organisation-public-v3.json', 'tests/bootstrap/test_guided_preparation_scope.py', 'tasks/APBRA-183-recovered-native-registration-public-v2.json', 'tests/bootstrap/fixtures/settings-release-proof-c92d488-application.txt', 'apps/api/tests/test_native_response_integration.py', 'tasks/APBRA-160-recovered-account-public-v2.json', 'docs/engineering/recovered-native-frozen-manifests.json', '.github/workflows/bootstrap.yml', 'tests/bootstrap/test_ci_policy.py', 'apps/api/tests/test_native_case_files.py'}
Q = {'apps/api/alembic/versions/20261105_15_tenant_date_display.py', 'apps/api/alembic/versions/20261105_16_session_identity_contact.py', 'apps/api/alembic/versions/20261106_17_password_auth.py', 'apps/api/pyproject.toml', 'apps/api/src/apbra_api/api.py', 'apps/api/src/apbra_api/application.py', 'apps/api/src/apbra_api/config.py', 'apps/api/src/apbra_api/domain.py', 'apps/api/src/apbra_api/foundry_admin_reads.py', 'apps/api/src/apbra_api/foundry_agent_details.py', 'apps/api/src/apbra_api/foundry_browser_handoff.py', 'apps/api/src/apbra_api/foundry_browser_relay.py', 'apps/api/src/apbra_api/foundry_catalogue_lease.py', 'apps/api/src/apbra_api/foundry_memory_handoff.py', 'apps/api/src/apbra_api/foundry_private_preparation.py', 'apps/api/src/apbra_api/foundry_report_runtime.py', 'apps/api/src/apbra_api/main.py', 'apps/api/src/apbra_api/native_case_files.py', 'apps/api/src/apbra_api/native_goal_context.py', 'apps/api/src/apbra_api/native_response_api.py', 'apps/api/src/apbra_api/native_response_probe.py', 'apps/api/src/apbra_api/observability.py', 'apps/api/src/apbra_api/oidc_adapter.py', 'apps/api/src/apbra_api/password_auth.py', 'apps/api/src/apbra_api/persistence.py', 'apps/api/src/apbra_api/request_outputs.py', 'apps/api/src/apbra_api/tenant_date_display.py', 'apps/api/tests/conftest.py', 'apps/api/tests/test_authentication.py', 'apps/api/tests/test_foundry_admin_reads.py', 'apps/api/tests/test_foundry_agent_details.py', 'apps/api/tests/test_foundry_artifacts.py', 'apps/api/tests/test_foundry_browser_handoff.py', 'apps/api/tests/test_foundry_browser_relay.py', 'apps/api/tests/test_foundry_catalogue_lease.py', 'apps/api/tests/test_foundry_memory_handoff.py', 'apps/api/tests/test_foundry_private_preparation.py', 'apps/api/tests/test_foundry_report_runtime.py', 'apps/api/tests/test_migrations.py', 'apps/api/tests/test_native_case_files.py', 'apps/api/tests/test_native_contracts.py', 'apps/api/tests/test_native_goal_context.py', 'apps/api/tests/test_native_response_integration.py', 'apps/api/tests/test_observability.py', 'apps/api/tests/test_password_auth.py', 'apps/api/tests/test_report_authorization_clock.py', 'apps/api/tests/test_request_outputs.py', 'apps/api/tests/test_tenant_date_display.py', 'apps/api/uv.lock', 'apps/web/e2e/audit-history.spec.ts', 'apps/web/e2e/durable-conversation.spec.ts', 'apps/web/e2e/native-outputs.spec.ts', 'apps/web/e2e/private-case.spec.ts', 'apps/web/e2e/protected-generation.spec.ts', 'apps/web/e2e/tenant-settings.spec.ts', 'apps/web/src/AdminUI.test.tsx', 'apps/web/src/AdminUI.tsx', 'apps/web/src/BusinessReportJourney.test.tsx', 'apps/web/src/BusinessReportJourney.tsx', 'apps/web/src/EnterpriseApp.tsx', 'apps/web/src/PasswordAccount.test.tsx', 'apps/web/src/PasswordAccount.tsx', 'apps/web/src/RequestOutputs.test.tsx', 'apps/web/src/RequestOutputs.tsx', 'apps/web/src/SavedAzureAnswer.test.tsx', 'apps/web/src/SavedAzureAnswer.tsx', 'apps/web/src/TenantDateTime.test.tsx', 'apps/web/src/TenantDateTime.tsx', 'apps/web/src/TenantObservability.test.tsx', 'apps/web/src/TenantObservability.tsx', 'apps/web/src/api.test.ts', 'apps/web/src/api.ts', 'apps/web/src/businessAgent.test.ts', 'apps/web/src/businessAgent.ts', 'apps/web/src/durableConversation.tsx', 'apps/web/src/durableGeneration.test.tsx', 'apps/web/src/durableGeneration.tsx', 'apps/web/src/privateCases.test.tsx', 'apps/web/src/privateCases.tsx', 'apps/web/src/style.css'}
N = {'apps/api/alembic/versions/20261108_18_native_organisation.py', 'apps/api/src/apbra_api/api.py', 'apps/api/src/apbra_api/application.py', 'apps/api/src/apbra_api/domain.py', 'apps/api/src/apbra_api/native_organisation.py', 'apps/api/src/apbra_api/password_auth.py', 'apps/api/src/apbra_api/persistence.py', 'apps/api/tests/test_migrations.py', 'apps/api/tests/test_native_organisation.py', 'apps/api/tests/test_password_auth.py', 'apps/api/tests/test_request_outputs.py', 'apps/web/src/PasswordAccount.test.tsx', 'apps/web/src/PasswordAccount.tsx', 'apps/web/src/api.ts', 'apps/web/src/privateCases.test.tsx', 'apps/web/src/privateCases.tsx', 'apps/web/src/style.css'}
REG_FIXTURES = {'apps/api/tests/conftest.py', 'apps/api/tests/test_foundry_private_preparation.py', 'apps/api/tests/test_foundry_report_runtime.py', 'apps/api/tests/test_native_case_files.py', 'apps/api/tests/test_native_contracts.py', 'apps/api/tests/test_native_response_integration.py', 'apps/api/tests/test_report_authorization_clock.py'}
RT_SHA = '86474848c646a5217a3a1d4a235630906942ec7dd5369b7d29f618af38fe94f5'
QT_SHA = '53e8e90aaa1d25c1d92a9ba061c7bc44790e833571b48feb9ec557592cd14ce1'
NT_SHA = 'c1f0cc0014c75e2242191f16f328132129a0f9b2053126f4dae4ee2a7a7566bd'
MANIFEST_SHA = 'd88d66f5012f932812366e8b77a0efae844af75db568716a46ecd0b3d9b1d162'
APPROVED_WORKFLOW_SHA = 'ae81f766235128ac4cd409549e2846d8dce1ea1893bff63d02455e5d64bb74d2'
LEGACY_WORKFLOW_SHA = '55314de4067db48231fdc9e5833c66be3cdf4c5594f4ce4aebbb4c1a708cb47d'
IMMUTABLE_V2 = {'tasks/APBRA-160-recovered-account-public-v2.json': '9436d80af215710d740931723b0645e0dbda77709303bb0312b1dfbb593f4eb0', 'tasks/APBRA-183-native-organisation-public-v2.json': 'c4fac394d2543196424bc773fe67c6de4b074d70873cfa5d78c5abdaa5071426', 'tasks/APBRA-183-recovered-native-registration-public-v2.json': '94be79c161a078f9d12ed5269a1fea1120e316b6369df33673576a0029c0bf7d', 'docs/engineering/recovered-native-frozen-manifests.json': '78fbc2dc6597d885344321cf668f8df28ffaa76ab5d27bc78a6746ed1e1d6433'}
AGGREGATE_COMMAND = 'test "$GOVERNANCE_RESULT" = success\ntest "$API_RESULT" = success\ntest "$WEB_RESULT" = success\n'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def safe(root, name):
    target = root / name
    return target.is_file() and not target.is_symlink() and not any(
        part.is_symlink() for part in target.parents if part == root or root in part.parents)


class UniqueLoader(yaml.BaseLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise ValueError('Duplicate or invalid workflow mapping key')
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def legacy_workflow():
    raw = (ROOT / FIXTURE).read_bytes()
    if hashlib.sha256(raw).hexdigest() != LEGACY_WORKFLOW_SHA:
        raise ValueError('Frozen single-job workflow differs')
    return raw.decode()


def expected_workflow():
    previous = yaml.load(legacy_workflow(), Loader=UniqueLoader)
    job = previous['jobs']['bootstrap']
    steps = job['steps']
    initial = steps[:3]
    api_names = {'Install and verify locked API dependencies', 'Create isolated backend and browser test databases',
                 'Build canonical TypeScript bridges', 'Check and test the API against PostgreSQL 17'}
    web_names = api_names - {'Check and test the API against PostgreSQL 17'} | {'Build and test locked requester shell'}
    common = {'runs-on': 'ubuntu-24.04', 'timeout-minutes': '45'}
    result = {key: copy.deepcopy(previous[key]) for key in ('name', 'on', 'permissions', 'concurrency')}
    result['jobs'] = {
        'governance': {'name': 'APBRA Governance Checks', **common,
                       'env': {'PR_HEAD_SHA': job['env']['PR_HEAD_SHA']},
                       'steps': copy.deepcopy(initial + steps[3:8] + [steps[-1]])},
        'api': {'name': 'APBRA API Checks', 'needs': 'governance', **common,
                'env': copy.deepcopy(job['env']), 'services': copy.deepcopy(job['services']),
                'steps': copy.deepcopy(initial + [step for step in steps if step.get('name') in api_names])},
        'web': {'name': 'APBRA Web Checks', 'needs': 'governance', **common,
                'env': copy.deepcopy(job['env']), 'services': copy.deepcopy(job['services']),
                'steps': copy.deepcopy(initial + [step for step in steps if step.get('name') in web_names])},
        'bootstrap': {'name': 'APBRA Bootstrap Checks', 'needs': ['governance', 'api', 'web'], 'if': 'always()',
                      **common, 'env': {'GOVERNANCE_RESULT': '${{ needs.governance.result }}',
                                       'API_RESULT': '${{ needs.api.result }}', 'WEB_RESULT': '${{ needs.web.result }}'},
                      'steps': [{'name': 'Require every mandatory job to succeed', 'run': AGGREGATE_COMMAND}]},
    }
    return result


def semantic_workflow(doc):
    value = copy.deepcopy(doc)
    if not isinstance(value, dict) or not isinstance(value.get('jobs'), dict):
        return value
    for job in value['jobs'].values():
        if isinstance(job, dict) and isinstance(job.get('steps'), list):
            for step in job['steps']:
                if isinstance(step, dict):
                    if 'name' not in step or type(step['name']) is str: step.pop('name', None)
    return value


def validate_workflow(text):
    try:
        current = yaml.load(text, Loader=UniqueLoader)
        tree = yaml.compose(text, Loader=yaml.SafeLoader)
        events = next(value for key, value in tree.value if key.value == 'on')
        dispatch = next(value for key, value in events.value if key.value == 'workflow_dispatch')
        if dispatch.tag != 'tag:yaml.org,2002:null':
            return ['workflow_dispatch must preserve the actual null event declaration']
        current['on']['workflow_dispatch'] = ''  # Only after proving the real YAML null type.
        jobs = next(value for key, value in tree.value if key.value == 'jobs')
        for _, job in jobs.value:
            timeout = next(value for key, value in job.value if key.value == 'timeout-minutes')
            if timeout.tag != 'tag:yaml.org,2002:int':
                return ['Job timeout must remain the literal numeric policy value']
        concurrency = next(value for key, value in tree.value if key.value == 'concurrency')
        cancel = next(value for key, value in concurrency.value if key.value == 'cancel-in-progress')
        if cancel.tag != 'tag:yaml.org,2002:bool':
            return ['Concurrency cancellation must preserve the boolean declaration']
        return [] if semantic_workflow(current) == semantic_workflow(expected_workflow()) else [
            'Workflow differs from exact v3 governance/API/web/required-context policy']
    except (yaml.YAMLError, ValueError, TypeError, KeyError, OSError, RecursionError, StopIteration, AttributeError):
        return ['Invalid, ambiguous or unavailable v3 workflow policy']


def workflow_projection(root, text):
    """Validate complete new policy before the unchanged historical shallow check."""
    if hashlib.sha256(text.encode()).hexdigest() == APPROVED_WORKFLOW_SHA and not validate_workflow(text):
        return legacy_workflow()
    return text


def enabled(root):
    return (root / RT).exists() or (root / RT).is_symlink()


def parse_pairs(rows, expected):
    if type(rows) is not list:
        raise ValueError('Source inventory must use typed pairs')
    result = {}
    for row in rows:
        if type(row) is not list or len(row) != 2:
            raise ValueError('Source row must be a path/hash pair')
        name, sha = row
        if type(name) is not str or type(sha) is not str or re.fullmatch(r'[0-9a-f]{64}', sha) is None or name in result:
            raise ValueError('Source pair is malformed or duplicate')
        result[name] = sha
    if set(result) != expected:
        raise ValueError('Source inventory literal paths differ')
    return result


def manifest(root):
    if not safe(root, MANIFEST):
        raise ValueError('V3 manifest missing or symlink')
    raw = (root / MANIFEST).read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
        raise ValueError('V3 manifest differs')
    value = json.loads(raw)
    if value.get('schema_version') != 3 or value.get('public_base') != BASE or value.get('continuation_base') != PRIOR:
        raise ValueError('V3 manifest identity differs')
    if value.get('allowed_account_paths') != sorted(Q) or value.get('allowed_native_paths') != sorted(N):
        raise ValueError('V3 proposed literal paths differ')
    prior = parse_pairs(value.get('immutable_v2_artifacts'), set(IMMUTABLE_V2))
    if prior != IMMUTABLE_V2 or not files_match(root, prior):
        raise ValueError('Immutable v2 artifacts differ')
    value['registration_fixture_files'] = parse_pairs(value.get('registration_fixture_files'), REG_FIXTURES)
    prior = json.loads((root / 'docs/engineering/recovered-native-frozen-manifests.json').read_text())
    if value['registration_fixture_files'] != parse_pairs(prior['registration_fixture_files'], REG_FIXTURES):
        raise ValueError('V3 registration fixtures differ from immutable Reg7 phase')
    if value.get('approved_workflow_sha256') != APPROVED_WORKFLOW_SHA or value.get('legacy_workflow_sha256') != LEGACY_WORKFLOW_SHA:
        raise ValueError('CI workflow provenance differs')
    status = value.get('product_status')
    if status == 'NOT_FROZEN':
        if value.get('account_files') != [] or value.get('native_files') != [] or any(
                value.get(key) is not None for key in ('account_observed_source', 'native_observed_source')):
            raise ValueError('Unfrozen source cannot contain provisional facts')
        value['account_files'] = {}; value['native_files'] = {}
    elif status == 'FROZEN':
        if any(type(value.get(key)) is not str or re.fullmatch(r'[0-9a-f]{40}', value[key]) is None for key in ('account_observed_source', 'native_observed_source')):
            raise ValueError('Frozen observed source identity is absent or invalid')
        value['account_files'] = parse_pairs(value.get('account_files'), Q)
        value['native_files'] = parse_pairs(value.get('native_files'), N)
    else:
        raise ValueError('Source status is unknown')
    return value


def files_match(root, files, ref=None):
    try:
        for name, expected in files.items():
            if ref is None:
                if not safe(root, name): return False
                raw = (root / name).read_bytes()
            else:
                raw = git(root, 'show', ref + ':' + name)
            if hashlib.sha256(raw).hexdigest() != expected: return False
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def ancestor(root, sha, ref):
    return subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', sha, ref],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10).returncode == 0


def ready(task):
    return task is not None and (task.get('task_mode'), task.get('readiness'), task.get('owner_acceptance')) == (
        'IMPLEMENTATION', 'READY_FOR_IMPLEMENTATION', 'RECORDED')


def bind(root, catalog, sources, schema_errors, task_errors):
    tasks = []; faults = []
    for name, key, branch, paths, expected in [(QT, 'APBRA-160', QB, Q, QT_SHA),
                                              (NT, 'APBRA-183', NB, N, NT_SHA),
                                              (RT, 'APBRA-183', R, G, RT_SHA)]:
        try:
            if not safe(root, name): raise ValueError('Missing or symlink v3 task')
            task = json.loads((root / name).read_text())
            errors = schema_errors(json.loads((root / 'contracts/engineering/task-contract.schema.json').read_text()), task)
            if not errors: errors += task_errors(task, catalog, sources)
            if digest(task) != expected: errors.append('V3 complete task binding differs')
            if (task.get('task_id'), task.get('assigned_agent'), task.get('agent_card_version'), task.get('branch'), task.get('base_commit')) != (key, 'APBRA-DEVOPS', '0.1', branch, BASE):
                errors.append('V3 identity/card/base/branch differs')
            if task.get('allowed_paths') != sorted(paths): errors.append('V3 literal scope differs')
            if any(fnmatchcase(path, pattern) for path in task.get('allowed_paths', []) for pattern in task.get('restricted_paths', [])):
                errors.append('V3 allowed/restricted scope conflict')
            if digest(sources) != SOURCE_SHA: errors.append('Historical accepted source register differs')
            faults += errors; tasks.append(task if not errors and ready(task) else None)
        except (OSError, ValueError, KeyError, TypeError):
            faults.append('V3 task missing, unsafe or unreadable'); tasks.append(None)
    try:
        frozen = manifest(root)
        if frozen['product_status'] != 'FROZEN': tasks[:2] = [None, None]
    except (OSError, ValueError, KeyError, TypeError):
        faults.append('V3 source/CI manifest invalid'); tasks = [None, None, None]
    return (*tasks, faults)


def registration_published(root):
    try:
        if not ancestor(root, BASE, 'HEAD') or not ancestor(root, BASE, 'origin/main'): return False
        for name in G - REG_FIXTURES:
            if not safe(root, name): return False
            raw = git(root, 'show', 'origin/main:' + name)
            if raw != (root / name).read_bytes(): return False
        frozen = manifest(root)
        released = frozen['product_status'] == 'FROZEN' and (files_match(root, frozen['account_files'], 'origin/main') or
                  files_match(root, {**frozen['account_files'], **frozen['native_files']}, 'origin/main'))
        expected = {name: frozen['account_files'][name] for name in REG_FIXTURES} if released else frozen['registration_fixture_files']
        return files_match(root, expected, 'origin/main')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return False


def errors(root, parent, native, registration, branch, paths):
    if branch not in (R, QB, NB): return []
    if branch == R:
        if registration is None or paths != G: return ['V3 registration requires exact finite G41 CI/governance scope']
        if not ancestor(root, BASE, 'HEAD'): return ['V3 registration actual-base ancestry missing']
        if not files_match(root, {'.github/workflows/bootstrap.yml': APPROVED_WORKFLOW_SHA}): return ['V3 approved workflow bytes differ']
        return [] if files_match(root, manifest(root)['registration_fixture_files']) else ['V3 registration test-fixture phase differs']
    try: frozen = manifest(root)
    except (OSError, ValueError, KeyError, TypeError): return ['V3 source/CI manifest missing or invalid']
    if frozen['product_status'] != 'FROZEN': return ['V3 product source is NOT_FROZEN and non-admitted']
    if not paths or not paths <= (Q if branch == QB else N): return ['V3 product phase scope differs']
    if parent is None or (branch == NB and native is None): return ['V3 accepted product authority missing']
    if registration is None or not registration_published(root): return ['V3 registration is not effective on actual main']
    if branch == NB and not parent_released(root):
        return ['V3 native requires actually released recovered source']
    expected = frozen['account_files'] if branch == QB else {**frozen['account_files'], **frozen['native_files']}
    return [] if files_match(root, expected) else ['V3 product differs from exact frozen source']

HISTORICAL_COPY_MODULES = {'test_foundry_qualification_renewal_scope.py', 'test_foundry_qualification_renewal_20261011_scope.py', 'test_foundry_qualification_scope.py'}
HISTORICAL_COPY_ADAPTER = "        if historical:\n            workflow = root / '.github/workflows/bootstrap.yml'\n            workflow.write_text(c.pn['workflow_projection'](ROOT, workflow.read_text()))\n\n"
HISTORICAL_GUIDED_ADAPTER = ('                    self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),expected)\n', "                    current=(ROOT/name).read_bytes()\n                    if name=='.github/workflows/bootstrap.yml':\n                        current=C['pn']['workflow_projection'](ROOT,current.decode()).encode()\n                    self.assertEqual(hashlib.sha256(current).hexdigest(),expected)\n")

HISTORICAL_TEST_PREIMAGES = dict([['test_foundry_qualification_renewal_20261011_scope.py', '7b1d45611c7c6986921d817489ab0b89f1917eab077cb3f1be61ceefc5df8718'], ['test_foundry_qualification_renewal_scope.py', '60f92dcbc305155edba0242bd40d6dbd66ec287d452ee07b0d794e1fd32a90ff'], ['test_foundry_qualification_scope.py', '797f19499d90f72532780ddab509b22fd22f8d3f31bd82ab3b8ec53d6735edb1'], ['test_guided_preparation_scope.py', '718c7e3401b3fe3ed41513c8af96553fe82a6b307fb1a0995296fb0f06d20561'], ['test_historical_fixture_staging_20261012_scope.py', '57222c7ae13755f2edbfb60861028ff417a89ac08f41c25f3f4255f642ec3bee']])


def strip_historical_copy_adapter(name, source):
    if name not in HISTORICAL_COPY_MODULES or source.count(HISTORICAL_COPY_ADAPTER) != 1:
        raise ValueError('Historical workflow copier inverse missing, duplicate or inexact')
    restored = source.replace(HISTORICAL_COPY_ADAPTER, '', 1)
    if hashlib.sha256(restored.encode()).hexdigest() != HISTORICAL_TEST_PREIMAGES[name]:
        raise ValueError('Historical copier assertions or bytes differ')
    return restored


def strip_historical_guided_adapter(source):
    before, after = HISTORICAL_GUIDED_ADAPTER
    if source.count(after) != 1:
        raise ValueError('Historical workflow readback inverse missing, duplicate or inexact')
    restored = source.replace(after, before, 1)
    if hashlib.sha256(restored.encode()).hexdigest() != HISTORICAL_TEST_PREIMAGES['test_guided_preparation_scope.py']:
        raise ValueError('Historical guided assertions or bytes differ')
    return restored


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL, timeout=10)


def parent_released(root):
    try:
        frozen = manifest(root)
        if frozen['product_status'] != 'FROZEN' or not registration_published(root): return False
        # An already released native snapshot supersedes shared account bytes.
        return files_match(root, frozen['account_files'], 'origin/main') or files_match(
            root, {**frozen['account_files'], **frozen['native_files']}, 'origin/main')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return False


def qualified_paths(root, checker, identity, branch, paths, overlap, candidate):
    """Version-aware protected readback; never manufacture an original release fact."""
    try:
        if (identity, branch, paths) != checker['delivery_context'](root): return set()
        parent, native, registration, faults = bind(
            root, json.loads((root / 'agents/catalog.json').read_text()),
            json.loads((root / 'docs/source-register.json').read_text()),
            checker['schema_errors'], checker['task_errors'])
        if faults or parent is None or registration is None: return set()
        frozen = manifest(root)
        if frozen['product_status'] != 'FROZEN': return set()
        # Preserve the original immutable candidate's actual ancestry and every original blob pin.
        if not all(ancestor(root, candidate, ref) for ref in ('HEAD', 'origin/main')): return set()
        for name, expected in overlap.items():
            if hashlib.sha256(git(root, 'show', candidate + ':' + name)).hexdigest() != expected: return set()
        if branch in (QB, NB):
            if identity != ('APBRA-160' if branch == QB else 'APBRA-183'): return set()
            if errors(root, parent, native, registration, branch, paths): return set()
            complete = frozen['account_files'] if branch == QB else {**frozen['account_files'], **frozen['native_files']}
        else:
            if not registration_published(root): return set()
            complete = None
            for files in [{**frozen['account_files'], **frozen['native_files']}, frozen['account_files']]:
                if files_match(root, files, 'origin/main') and files_match(root, files):
                    complete = files; break
            if complete is None: return set()
        protected = {name: complete.get(name, expected) for name, expected in overlap.items()}
        if not files_match(root, protected): return set()
        faults, _ = checker['check'](root, active_task_id=identity, active_branch=branch, changed_paths=paths)
        return set() if faults else set(overlap)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, RecursionError):
        return set()

HISTORICAL_STAGING_AST_ADAPTER = ("            new = ast.parse((ROOT / 'tests/bootstrap' / name).read_text())\n", "            current = (ROOT / 'tests/bootstrap' / name).read_text()\n            if name in {'test_foundry_qualification_scope.py', 'test_foundry_qualification_renewal_scope.py', 'test_foundry_qualification_renewal_20261011_scope.py'}:\n                current = c.pn['V3']['strip_historical_copy_adapter'](name, current)\n            new = ast.parse(current)\n")

def strip_historical_staging_adapter(source):
    before, after = HISTORICAL_STAGING_AST_ADAPTER
    if source.count(after) != 1:
        raise ValueError('Historical staging inverse missing, duplicate or inexact')
    restored = source.replace(after, before, 1)
    if hashlib.sha256(restored.encode()).hexdigest() != HISTORICAL_TEST_PREIMAGES['test_historical_fixture_staging_20261012_scope.py']:
        raise ValueError('Historical staging assertions or bytes differ')
    return restored


# Exact finite test/readback adapters: every original test preimage stays committed.
HISTORICAL_TEST_PREIMAGES.update({'test_bootstrap.py': '5a800efd19a58a14ccff61a2e2cd03deecabed61c5c14cc725bd9ddf09ed2c9c', 'test_knowledge_lifecycle_20261012_scope.py': '6bf211788a27705e0798de997e0dc8c305c700f43da5d2489f20ee2641dad836', 'test_tenant_document_drafts_20261013_scope.py': 'e19e5c5e14288931f7c298360176455e5fa9b403a146486c6e5839144aeb2c9c'})
HISTORICAL_BOOTSTRAP_ADAPTER = ("        self.workflow = (ROOT / '.github/workflows/bootstrap.yml').read_text()\n", "        self.workflow = (ROOT / '.github/workflows/bootstrap.yml').read_text()\n        if c.pn:self.workflow = c.pn['workflow_projection'](ROOT, self.workflow)\n")
HISTORICAL_KNOWLEDGE_ADAPTERS = [("self.assertEqual((ROOT / 'scripts' / name).read_bytes(), subprocess.check_output(['git', 'show', h['BASE'] + ':scripts/' + name], cwd=ROOT))", "self.assertEqual(c.pn['V3']['historical_policy_source'](name, (ROOT / 'scripts' / name).read_bytes()), subprocess.check_output(['git', 'show', h['BASE'] + ':scripts/' + name], cwd=ROOT))"), ('        new = restore_h9_fixture_selection(ast.parse((ROOT / name).read_text()))\n', "        new = restore_h9_fixture_selection(ast.parse(c.pn['V3']['strip_historical_staging_adapter']((ROOT / name).read_text())))\n"), ('                new = restore_h9_fixture_selection(ast.parse((ROOT / path).read_text()))\n', "                current = (ROOT / path).read_text()\n                if name == 'test_historical_fixture_staging_20261012_scope.py':\n                    current = c.pn['V3']['strip_historical_staging_adapter'](current)\n                new = restore_h9_fixture_selection(ast.parse(current))\n")]
HISTORICAL_TENANT_ADAPTER = ('        current = (ROOT / path).read_text()\n        replacements = [\n', "        current = c.pn['V3']['strip_historical_knowledge_adapter']((ROOT / path).read_text())\n        replacements = [\n")
HISTORICAL_POLICY_APPEND = b"validate_legacy = validate\n\n\ndef validate(text: str) -> list[str]:\n    import runpy\n    helper = Path(__file__).with_name('check_ci_browser_registration_v3.py')\n    if not helper.is_file() or helper.is_symlink():\n        return ['V3 CI policy helper missing or unsafe']\n    try:\n        return runpy.run_path(helper)['validate_workflow'](text)\n    except (OSError, ValueError, KeyError, TypeError):\n        return ['V3 CI policy unavailable']\n\n\n"
HISTORICAL_POLICY_SHA = '4515647623269aa9ac720269683a907458be9c5f10b60d8ea22e0498325c6f62'


def restore_test_adapters(source, pairs, preimage):
    for before, after in pairs:
        if source.count(after) != 1:
            raise ValueError('Exact historical adapter missing, duplicate or inexact')
        source = source.replace(after, before, 1)
    if hashlib.sha256(source.encode()).hexdigest() != HISTORICAL_TEST_PREIMAGES[preimage]:
        raise ValueError('Historical test assertions or bytes differ')
    return source


def strip_historical_bootstrap_adapter(source):
    return restore_test_adapters(source, [HISTORICAL_BOOTSTRAP_ADAPTER], 'test_bootstrap.py')


def strip_historical_knowledge_adapter(source):
    return restore_test_adapters(source, HISTORICAL_KNOWLEDGE_ADAPTERS, 'test_knowledge_lifecycle_20261012_scope.py')


def strip_historical_tenant_adapter(source):
    return restore_test_adapters(source, [HISTORICAL_TENANT_ADAPTER], 'test_tenant_document_drafts_20261013_scope.py')


def historical_policy_source(name, raw):
    if name != 'check_ci_policy.py': return raw
    if raw.count(HISTORICAL_POLICY_APPEND) != 1:
        raise ValueError('Historical CI policy inverse missing, duplicate or inexact')
    restored = raw.replace(HISTORICAL_POLICY_APPEND, b'', 1)
    if hashlib.sha256(restored).hexdigest() != HISTORICAL_POLICY_SHA:
        raise ValueError('Historical CI policy original bytes differ')
    return restored

HISTORICAL_TEST_PREIMAGES['test_invited_private_case_foundation_scope.py'] = 'd4f056415d18efc8706322b6771c9224ab3035edaa0e9631b0b9efe80024bb0f'
HISTORICAL_FOUNDATION_ADAPTER = ('                shutil.copyfile(source, target)\n', '                shutil.copyfile(source, target)\n                if name == "tests/bootstrap/test_bootstrap.py":\n                    target.write_text(c.pn[\'V3\'][\'strip_historical_bootstrap_adapter\'](target.read_text()))\n')


def strip_historical_foundation_adapter(source):
    return restore_test_adapters(source, [HISTORICAL_FOUNDATION_ADAPTER], 'test_invited_private_case_foundation_scope.py')
