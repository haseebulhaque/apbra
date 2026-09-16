"""Check the future task draft without pretending it is ready or implemented."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('next_task_check', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class NextTaskTests(unittest.TestCase):
    def setUp(self):
        self.task = c.load_json(ROOT / 'tasks/APBRA-27-build.json')

    def test_schema_valid(self):
        schema = c.load_json(ROOT / 'contracts/engineering/task-contract.schema.json')
        self.assertEqual(c.schema_errors(schema, self.task), [])

    def test_not_dispatched(self):
        self.assertEqual(self.task['task_id'], 'APBRA-27')
        self.assertEqual(self.task['task_mode'], 'SPECIFICATION')
        self.assertEqual(self.task['readiness'], 'NEEDS_REFINEMENT')
        self.assertTrue(self.task['execution_id'].startswith('UNBOUND:'))
        self.assertNotEqual(self.task['owner_acceptance'], 'RECORDED')

    def test_scope_is_bounded(self):
        catalog = c.load_json(ROOT / 'agents/catalog.json')
        card = next(x for x in catalog['cards'] if x['agent_id'] == self.task['assigned_agent'])
        self.assertTrue(c.path_allowed('apps/api/apbra_api/config.py', self.task, card))
        for path in ('apps/web/main.ts', 'packages/powerbi/generate.py', 'infrastructure/main.bicep', '.env', '.github/rulesets/main-protection.json'):
            self.assertFalse(c.path_allowed(path, self.task, card), path)

    def test_declared_sources_and_acceptance_exist(self):
        sources = c.load_json(ROOT / 'docs/source-register.json')
        self.assertTrue(set(self.task['source_ids']) <= {s['id'] for s in sources['sources']})
        text = (ROOT / 'docs/engineering/APBRA-27-build-contract.md').read_text()
        for number in range(1, 11):
            self.assertIn(f'B27-{number:02}', text)


if __name__ == '__main__':
    unittest.main()
