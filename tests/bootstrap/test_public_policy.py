"""Configuration regression checks; they do not prove native GitHub enforcement."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PublicPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / '.github/rulesets/main-protection.json').read_text())
        self.rules = {r['type']: r.get('parameters', {}) for r in self.policy['rules']}

    def test_exact_main_target_and_no_bypass(self):
        self.assertEqual(self.policy['target'], 'branch')
        self.assertEqual(self.policy['conditions']['ref_name'], {'include': ['refs/heads/main'], 'exclude': []})
        self.assertEqual(self.policy['bypass_actors'], [])

    def test_no_paid_push_rules_or_merge_queue(self):
        self.assertEqual(set(self.rules), {'deletion', 'non_fast_forward', 'pull_request', 'required_status_checks'})

    def test_independent_review_not_silently_removed(self):
        self.assertEqual(self.rules['pull_request']['required_approving_review_count'], 1)
        self.assertTrue(self.rules['pull_request']['require_last_push_approval'])
        self.assertTrue(self.rules['pull_request']['required_review_thread_resolution'])

    def test_actual_check_publisher_and_context(self):
        self.assertEqual(self.rules['required_status_checks']['required_status_checks'],
                         [{'context': 'APBRA Bootstrap Checks', 'integration_id': 15368}])
        self.assertTrue(self.rules['required_status_checks']['strict_required_status_checks_policy'])

    def test_scanner_is_pinned_redacted_and_history_aware(self):
        text = (ROOT / 'scripts/scan_secrets.sh').read_text()
        for required in ("version='8.30.1'", 'sha256sum --check --status', '--redact=100',
                         "--log-opts='--all'", '--is-shallow-repository', '--ignore-gitleaks-allow'):
            self.assertIn(required, text)
        self.assertNotIn('gitleaks/gitleaks-action@', text)

    def test_ignore_rules_block_local_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['git', 'init', '-q', tmp], check=True)
            (Path(tmp) / '.gitignore').write_text((ROOT / '.gitignore').read_text())
            for path in ('.env', '.env.production', 'secrets/key.json', 'id_rsa', 'file.pfx',
                         'infra/demo.tfstate', 'credentials.json', 'local.settings.json', 'report.pbix'):
                result = subprocess.run(['git', '-C', tmp, 'check-ignore', '-q', path])
                self.assertEqual(result.returncode, 0, path)
            self.assertEqual(subprocess.run(['git', '-C', tmp, 'check-ignore', '-q', '.env.example']).returncode, 1)


if __name__ == '__main__':
    unittest.main()
