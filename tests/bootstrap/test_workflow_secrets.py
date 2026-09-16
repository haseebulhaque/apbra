"""Regression: scanner filenames are not GitHub secret-context references."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('workflow_checker', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class WorkflowSecretContextTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / '.github/workflows/bootstrap.yml').read_text()

    def test_scanner_filename_is_allowed(self):
        self.assertIn('scan_secrets.sh', self.workflow)
        self.assertEqual(c.workflow_errors(self.workflow), [])

    def test_dot_secret_reference_still_denied(self):
        value = self.workflow.replace('bash scripts/scan_secrets.sh', 'echo ${{ secrets.TEST_VALUE }}')
        self.assertIn('Privileged trigger/secret reference prohibited', c.workflow_errors(value))

    def test_bracket_secret_reference_is_denied(self):
        value = self.workflow.replace('bash scripts/scan_secrets.sh', "echo ${{ secrets['TEST_VALUE'] }}")
        self.assertIn('Privileged trigger/secret reference prohibited', c.workflow_errors(value))


if __name__ == '__main__':
    unittest.main()
