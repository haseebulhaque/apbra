"""Lint approved bootstrap CI shape; not a sandbox or independent review."""
from pathlib import Path
import sys
import yaml

PINS = {
    'actions/setup-node': '249970729cb0ef3589644e2896645e5dc5ba9c38',
    'actions/checkout': 'd23441a48e516b6c34aea4fa41551a30e30af803',
    'actions/setup-python': 'ece7cb06caefa5fff74198d8649806c4678c61a1',
    'actions/upload-artifact': 'ea165f8d65b6e75b540449e92b4886f43607fa02',
}
COMMANDS = (
    'bash scripts/scan_secrets.sh',
    'python -m pip install --only-binary=:all: --no-deps -r requirements-bootstrap.txt',
    'python scripts/check_ci_policy.py',
    'python scripts/check_bootstrap.py --report artifacts/bootstrap/checks.json',
    'python -m unittest discover -s tests/bootstrap -v',
)
API_INSTALL = (
    'python -m pip install uv==0.12.3\n'
    'uv --directory apps/api lock --check\n'
    'uv --directory apps/api sync --frozen --python 3.13'
)
API_CHECK = (
    'uv --directory apps/api run --frozen ruff check .\n'
    'uv --directory apps/api run --frozen mypy\n'
    'uv --directory apps/api run --frozen alembic upgrade head\n'
    'uv --directory apps/api run --frozen pytest'
)
WEB_COMMAND = (
    'npm --prefix apps/web ci --ignore-scripts\n'
    'npm --prefix apps/web test\n'
    'npm --prefix apps/web run build\n'
    'npm --prefix apps/web exec playwright install --with-deps chromium\n'
    'npm --prefix apps/web run test:e2e'
)
OPTIONS = {
    'actions/setup-node': {'node-version': '24.19.0'},
    'actions/checkout': {'persist-credentials': 'false', 'fetch-depth': '0'},
    'actions/setup-python': {'python-version': '3.13'},
    'actions/upload-artifact': {
        'name': 'bootstrap-checks-${{ github.run_id }}-${{ github.run_attempt }}',
        'path': 'artifacts/bootstrap/checks.json',
        'if-no-files-found': 'error', 'retention-days': '7',
    },
}


class UniqueLoader(yaml.BaseLoader):
    """Keep scalars as strings and reject ambiguous duplicate mapping keys."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise ValueError('Duplicate or non-scalar YAML key')
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def validate(text: str) -> list[str]:
    """Return errors without echoing potentially sensitive workflow values."""
    try:
        doc = yaml.load(text, Loader=UniqueLoader)
        if not isinstance(doc, dict) or set(doc) != {'name', 'on', 'permissions', 'concurrency', 'jobs'}:
            return ['Unexpected workflow shape']
        errors = []
        if doc['on'] != {'pull_request': {'branches': ['main']}, 'workflow_dispatch': ''}:
            errors.append('Unexpected triggers or event filters')
        if doc['permissions'] != {'contents': 'read'}:
            errors.append('Workflow permissions must remain read-only')
        if doc['concurrency'] != {'group': 'bootstrap-${{ github.ref }}', 'cancel-in-progress': 'true'}:
            errors.append('Unexpected concurrency policy')
        if not isinstance(doc['jobs'], dict) or set(doc['jobs']) != {'bootstrap'}:
            return errors + ['Unexpected job set']
        job = doc['jobs']['bootstrap']
        if not isinstance(job, dict) or set(job) != {'name', 'runs-on', 'timeout-minutes', 'env', 'services', 'steps'}:
            return errors + ['Unexpected job options; skipping or error suppression is forbidden']
        if job['name'] != 'APBRA Bootstrap Checks' or job['runs-on'] != 'ubuntu-24.04' or job['timeout-minutes'] != '10':
            errors.append('Unexpected required check, runner or timeout')
        expected_env = {
            'PR_HEAD_SHA': '${{ github.event.pull_request.head.sha }}',
            'APBRA_PROFILE': 'test',
            'APBRA_DATABASE_URL': 'postgresql+psycopg://postgres@127.0.0.1:5432/apbra',
            'APBRA_TEST_DATABASE_URL': 'postgresql+psycopg://postgres@127.0.0.1:5432/apbra',
            'APBRA_PUBLIC_ORIGIN': 'http://127.0.0.1:5173',
            'APBRA_API_ORIGIN': 'http://127.0.0.1:8000',
            'APBRA_SESSION_SECRET': 'ci-only-generated-context-session-material',
            'APBRA_BOOTSTRAP_ENABLED': 'true',
        }
        if job['env'] != expected_env:
            errors.append('Unexpected job environment')
        expected_service = {
            'postgres': {
                'image': 'postgres:17.11-bookworm',
                'env': {
                    'POSTGRES_DB': 'apbra',
                    'POSTGRES_USER': 'postgres',
                    'POSTGRES_HOST_AUTH_METHOD': 'trust',
                },
                'ports': ['5432:5432'],
                'options': '--health-cmd "pg_isready -U postgres -d apbra" --health-interval 2s --health-timeout 3s --health-retries 30',
            }
        }
        if job['services'] != expected_service:
            errors.append('Unexpected PostgreSQL service configuration')
        if not isinstance(job['steps'], list):
            return errors + ['Steps must be a list']
        sequence = []
        for step in job['steps']:
            if not isinstance(step, dict):
                errors.append('Invalid step')
                continue
            if 'run' in step:
                if not set(step) <= {'name', 'run'} or not isinstance(step['run'], str):
                    errors.append('Command cannot have conditional execution, extra options or ignored errors')
                sequence.append(step['run'].strip() if isinstance(step['run'], str) else '')
            elif 'uses' in step:
                if not isinstance(step['uses'], str):
                    errors.append('Invalid action')
                    continue
                name, _, sha = step['uses'].partition('@')
                sequence.append(name)
                allowed = {'name', 'uses', 'with'}
                if name == 'actions/upload-artifact':
                    allowed.add('if')
                    if step.get('if') != 'always()':
                        errors.append('Evidence upload must run after failures')
                if not set(step) <= allowed or PINS.get(name) != sha or step.get('with') != OPTIONS.get(name):
                    errors.append('Unapproved action configuration')
            else:
                errors.append('Step must be a known command or pinned action')
        expected = ['actions/checkout', 'actions/setup-python', *COMMANDS, API_INSTALL, API_CHECK, 'actions/setup-node', WEB_COMMAND, 'actions/upload-artifact']
        if sequence != expected:
            errors.append('Mandatory steps missing, duplicated, reordered or replaced')
        return errors
    except (yaml.YAMLError, ValueError, TypeError, KeyError, RecursionError):
        return ['Invalid or ambiguous workflow YAML']


def main() -> int:
    path = Path(__file__).resolve().parents[1] / '.github/workflows/bootstrap.yml'
    try:
        errors = validate(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError):
        errors = ['Cannot read bootstrap workflow']
    for error in errors:
        print(error, file=sys.stderr)
    print('FAIL: CI policy' if errors else 'PASS: CI policy')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
