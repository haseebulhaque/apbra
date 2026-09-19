"""Exact APBRA-76 deployment-guide authority and fail-closed scope checks."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_deployment_guide", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class DeploymentGuideScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-76-deployment-guide.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        catalog = json.loads((ROOT / "agents/catalog.json").read_text())
        self.card = next(card for card in catalog["cards"] if card["agent_id"] == self.task["assigned_agent"])

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.DEPLOYMENT_GUIDE_PATHS | {self.task_path})
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("// APBRA-76 scope fixture\n")

    def test_valid_authority_admits_only_the_exact_implementation_paths(self):
        self.assertEqual(set(self.task["allowed_paths"]), c.DEPLOYMENT_GUIDE_PATHS)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors, _ = c.check(root)
            self.assertEqual(errors, [])

    def test_unrelated_environment_and_generated_paths_remain_rejected(self):
        for path in ("apps/web/src/unrelated.ts", "apps/web/.env.local", "output/pdf/guide.pdf"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("outside APBRA-76 scope\n")
                errors, _ = c.check(root)
                self.assertIn(f"File outside safe bootstrap scope: {path}", errors)
        self.assertFalse(c.path_allowed("artifacts/local/guide.pdf", self.task, self.card))

    def test_missing_or_invalid_authority_cannot_admit_new_files(self):
        mutations = [
            (None, "File outside safe bootstrap scope: apps/web/src/deploymentGuide.ts"),
            ({"allowed_paths": ["apps/web/**"]}, "Unexpected deployment guide scope"),
            ({"task_id": "APBRA-999"}, "Unexpected deployment guide identity"),
            ({"assigned_agent": "APBRA-QA"}, "Unexpected deployment guide identity"),
            ({"branch": "agent/APBRA-DEVOPS/APBRA-77-stale"}, "Branch must match the agent and Jira task"),
            ({"task_mode": "REVIEW"}, "Deployment guide requires issued implementation acceptance"),
            ({"readiness": "NEEDS_REFINEMENT"}, "Implementation mode/readiness mismatch"),
            ({"owner_acceptance": "PENDING"}, "Implementation acceptance is not recorded"),
            ({"source_ids": ["engineering-structure"]}, "Deployment guide requires its specific accepted source"),
        ]
        for mutation, expected_error in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                if mutation is None:
                    (root / self.task_path).unlink()
                else:
                    task = copy.deepcopy(self.task)
                    task.update(mutation)
                    (root / self.task_path).write_text(json.dumps(task))
                errors, _ = c.check(root)
                self.assertIn(expected_error, errors)

    def test_secret_pattern_and_symlink_remain_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            target = root / "apps/web/src/deploymentGuide.ts"
            target.write_text("const credential = 'ghp_" + "A" * 36 + "';\n")
            errors, _ = c.check(root)
            self.assertIn("High-confidence credential pattern in: apps/web/src/deploymentGuide.ts", errors)
            target.unlink()
            target.symlink_to(root / "README.md")
            errors, _ = c.check(root)
            self.assertIn("File outside safe bootstrap scope: apps/web/src/deploymentGuide.ts", errors)

    def test_existing_apbra_92_authority_still_validates(self):
        errors, _ = c.check(ROOT)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
