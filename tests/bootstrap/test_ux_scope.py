"""Exact APBRA-137 presentation authority and fail-closed scope checks."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_ux", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class CapstoneUXScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-137-final-capstone-ux.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        catalog = json.loads((ROOT / "agents/catalog.json").read_text())
        self.card = next(card for card in catalog["cards"] if card["agent_id"] == self.task["assigned_agent"])

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.CAPSTONE_UX_PATHS | {self.task_path})
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("// APBRA-137 scope fixture\n")

    def test_valid_authority_admits_only_the_exact_presentation_paths(self):
        self.assertEqual(set(self.task["allowed_paths"]), c.CAPSTONE_UX_PATHS)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors, _ = c.check(root)
            self.assertEqual(errors, [])

    def test_unrelated_application_backend_dependency_environment_and_output_paths_are_rejected(self):
        paths = (
            "apps/web/src/unrelated.ts",
            "apps/api/src/handler.ts",
            "apps/web/package.json.extra",
            "apps/web/.env.local",
            "output/ux/screenshot.png",
        )
        for path in paths:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("outside APBRA-137 scope\n")
                errors, _ = c.check(root)
                self.assertIn(f"File outside safe bootstrap scope: {path}", errors)
        for path in ("apps/web/package.json", "artifacts/ux/report.json"):
            self.assertFalse(c.path_allowed(path, self.task, self.card))

    def test_missing_stale_malformed_or_reused_authority_cannot_admit_new_files(self):
        mutations = [
            (None, "File outside safe bootstrap scope: apps/web/src/EnterpriseUI.tsx"),
            ({"allowed_paths": ["apps/web/**"]}, "Unexpected Capstone UX scope"),
            ({"allowed_paths": self.task["allowed_paths"] + ["apps/web/src/unrelated.ts"]}, "Unexpected Capstone UX scope"),
            ({"task_id": "APBRA-999"}, "Unexpected Capstone UX identity"),
            ({"assigned_agent": "APBRA-QA"}, "Unexpected Capstone UX identity"),
            ({"branch": "agent/APBRA-DEVOPS/APBRA-76-reused"}, "Branch must match the agent and Jira task"),
            ({"task_mode": "REVIEW"}, "Capstone UX requires issued implementation acceptance"),
            ({"readiness": "NEEDS_REFINEMENT"}, "Implementation mode/readiness mismatch"),
            ({"owner_acceptance": "PENDING"}, "Implementation acceptance is not recorded"),
            ({"source_ids": ["engineering-structure"]}, "Capstone UX requires its specific accepted source"),
            ({"objective": None}, "None is not of type 'string'"),
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
                self.assertTrue(any(expected_error in error for error in errors), errors)

    def test_secret_pattern_and_symlink_remain_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            target = root / "apps/web/src/EnterpriseUI.tsx"
            target.write_text("const credential = 'ghp_" + "A" * 36 + "';\n")
            errors, _ = c.check(root)
            self.assertIn("High-confidence credential pattern in: apps/web/src/EnterpriseUI.tsx", errors)
            target.unlink()
            target.symlink_to(root / "README.md")
            errors, _ = c.check(root)
            self.assertIn("File outside safe bootstrap scope: apps/web/src/EnterpriseUI.tsx", errors)

    def test_existing_apbra_92_and_apbra_76_authorities_still_validate(self):
        self.assertEqual(set(json.loads((ROOT / "tasks/APBRA-76-deployment-guide.json").read_text())["allowed_paths"]), c.DEPLOYMENT_GUIDE_PATHS)
        self.assertEqual(set(json.loads((ROOT / "tasks/APBRA-92-evaluation.json").read_text())["allowed_paths"]), c.CAPSTONE_EVALUATION_PATHS)
        errors, _ = c.check(ROOT)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
