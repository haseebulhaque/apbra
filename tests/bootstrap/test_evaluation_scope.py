"""Exact APBRA-92 Capstone architecture scope and fail-closed regression checks."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_evaluation_scope", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class EvaluationScopeTests(unittest.TestCase):
    def setUp(self):
        self.task = json.loads((ROOT / "tasks/APBRA-92-evaluation.json").read_text())

    def copy_repository(self, root):
        for file in c.repo_files(ROOT):
            target = root / file.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, target)

    def test_exact_approved_application_paths_only(self):
        self.assertEqual(set(self.task["allowed_paths"]), c.CAPSTONE_EVALUATION_PATHS)
        self.assertNotIn("apps/web/**", self.task["allowed_paths"])
        self.assertNotIn("apps/**", self.task["allowed_paths"])
        for path in (
            "apps/api/main.py", "packages/domain.py", "infrastructure/main.tf",
            "apps/web/.env.local", "apps/web/src/unapproved.ts", "artifacts/local/candidate.zip",
        ):
            self.assertFalse(any(c.matches(path, pattern) for pattern in self.task["allowed_paths"]))

    def test_valid_contract_admits_the_approved_architecture(self):
        errors, _ = c.check(ROOT)
        self.assertEqual(errors, [])

    def test_wildcard_or_stale_contract_fails_closed(self):
        mutations = [
            {"allowed_paths": ["apps/web/**"]},
            {"allowed_paths": ["apps/**"]},
            {"task_id": "APBRA-999"},
            {"assigned_agent": "APBRA-QA"},
            {"task_mode": "REVIEW"},
            {"readiness": "NEEDS_REFINEMENT"},
            {"owner_acceptance": "PENDING"},
            {"source_ids": ["engineering-structure"]},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                task = copy.deepcopy(self.task)
                task.update(mutation)
                (root / "tasks/APBRA-92-evaluation.json").write_text(json.dumps(task))
                errors, _ = c.check(root)
                self.assertTrue(errors)
                self.assertTrue(
                    "Unexpected Capstone evaluation scope" in errors
                    or any("evaluation requires" in error for error in errors)
                    or any("Branch must match" in error for error in errors)
                    or any("source" in error.lower() for error in errors),
                    errors,
                )

    def test_unapproved_product_file_remains_outside_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            path = root / "apps/web/src/unapproved.ts"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("// must remain outside the approved APBRA-92 scope\n")
            errors, _ = c.check(root)
            self.assertIn("File outside safe bootstrap scope: apps/web/src/unapproved.ts", errors)


if __name__ == "__main__":
    unittest.main()
