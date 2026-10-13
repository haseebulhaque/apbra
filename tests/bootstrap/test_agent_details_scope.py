"""Current increment is exact and cannot broaden historical delivery scope."""
import copy
import json
import runpy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = runpy.run_path(str(ROOT / 'scripts/check_agent_details_20261013.py'))
CHECKER = runpy.run_path(str(ROOT / 'scripts/check_bootstrap.py'))


class AgentDetailsScope(unittest.TestCase):
    def test_exact_task_and_scope(self):
        task = json.loads((ROOT / 'tasks/APBRA-160-agent-details-20261013.json').read_text())
        self.assertEqual(set(task['allowed_paths']), HELPER['P'])
        self.assertEqual(len(task['allowed_paths']), 16)
        errors, _ = CHECKER['check'](ROOT, active_task_id='APBRA-160',
            active_branch=HELPER['B'], changed_paths=HELPER['P'])
        self.assertEqual(errors, [])

    def test_extra_or_foreign_paths_and_branch_fail(self):
        for branch, paths in [(HELPER['B'], HELPER['P'] | {'compose.yaml'}),
                              ('agent/APBRA-DEVOPS/APBRA-160-unregistered', HELPER['P'])]:
            errors, _ = CHECKER['check'](ROOT, active_task_id='APBRA-160',
                active_branch=branch, changed_paths=paths)
            self.assertTrue(errors)

    def test_task_pin_covers_every_authority_field(self):
        task = json.loads((ROOT / 'tasks/APBRA-160-agent-details-20261013.json').read_text())
        owner = runpy.run_path(str(ROOT / 'scripts/check_foundry_owner_metadata_20261012.py'))
        self.assertEqual(owner['digest'](task), HELPER['TASK_SHA'])
        for key in ('allowed_paths', 'branch', 'base_commit', 'requirements', 'restricted_paths'):
            changed = copy.deepcopy(task)
            changed[key] = [] if isinstance(task[key], list) else 'changed'
            self.assertNotEqual(owner['digest'](changed), HELPER['TASK_SHA'])
