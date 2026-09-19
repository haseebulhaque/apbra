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
        for path in c.CAPSTONE_UX_PATHS:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                errors, _ = c.check(
                    root, active_task_id="APBRA-137", active_branch=self.task["branch"],
                    changed_paths={path})
                self.assertEqual(errors, [])

    def test_unrelated_application_backend_dependency_environment_and_output_paths_are_rejected(self):
        paths = (
            "apps/web/src/unrelated.ts",
            "apps/api/src/handler.ts",
            "apps/web/package.json",
            "apps/web/package-lock.json",
            "apps/web/src/foundry.ts",
            "apps/web/src/rag.ts",
            "apps/web/src/genericPowerBI.ts",
            "apps/web/src/deploymentGuide.ts",
            "apps/web/.env.local",
            "output/ux/screenshot.png",
        )
        for path in paths:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_text("outside APBRA-137 scope\n")
                errors, _ = c.check(
                    root, active_task_id="APBRA-137", active_branch=self.task["branch"],
                    changed_paths={path})
                self.assertIn(f"File outside active task scope: {path}", errors)
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
                errors, _ = c.check(
                    root, active_task_id="APBRA-137", active_branch=self.task["branch"],
                    changed_paths={"apps/web/src/EnterpriseUI.tsx"})
                self.assertTrue(any(expected_error in error for error in errors), errors)

    def test_overlapping_paths_require_active_apbra_137_authority(self):
        overlapping = {
            "apps/web/src/EnterpriseApp.tsx",
            "apps/web/src/style.css",
            "apps/web/src/App.test.tsx",
        }
        for path in overlapping | {"apps/web/src/EnterpriseUI.tsx", "apps/web/src/EnterpriseUI.test.tsx"}:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                task = copy.deepcopy(self.task)
                task["owner_acceptance"] = "PENDING"
                (root / self.task_path).write_text(json.dumps(task))
                errors, _ = c.check(
                    root, active_task_id="APBRA-137", active_branch=self.task["branch"],
                    changed_paths={path})
                self.assertIn(f"File outside active task scope: {path}", errors)

    def test_active_identity_is_required_known_and_branch_bound(self):
        path = "apps/web/src/EnterpriseApp.tsx"
        cases = (
            (None, self.task["branch"], "Active task identity missing"),
            ("APBRA137", self.task["branch"], "Malformed active task identity"),
            ("APBRA-999", self.task["branch"], "Unknown or invalid active task authority"),
            ("APBRA-137", "agent/APBRA-DEVOPS/APBRA-92-reused", "Active branch conflicts"),
            ("APBRA-137", None, "Active task branch identity missing"),
        )
        for task_id, branch, expected in cases:
            with self.subTest(task_id=task_id, branch=branch), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                errors, _ = c.check(root, active_task_id=task_id, active_branch=branch,
                                    changed_paths={path})
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_secret_pattern_and_symlink_remain_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            target = root / "apps/web/src/EnterpriseUI.tsx"
            target.write_text("const credential = 'ghp_" + "A" * 36 + "';\n")
            errors, _ = c.check(
                root, active_task_id="APBRA-137", active_branch=self.task["branch"],
                changed_paths={"apps/web/src/EnterpriseUI.tsx"})
            self.assertIn("High-confidence credential pattern in: apps/web/src/EnterpriseUI.tsx", errors)
            target.unlink()
            target.symlink_to(root / "README.md")
            errors, _ = c.check(
                root, active_task_id="APBRA-137", active_branch=self.task["branch"],
                changed_paths={"apps/web/src/EnterpriseUI.tsx"})
            self.assertIn("File outside safe bootstrap scope: apps/web/src/EnterpriseUI.tsx", errors)

    def test_existing_apbra_92_and_apbra_76_authorities_still_validate(self):
        contracts = (
            ("tasks/APBRA-92-evaluation.json", c.CAPSTONE_EVALUATION_PATHS),
            ("tasks/APBRA-76-deployment-guide.json", c.DEPLOYMENT_GUIDE_PATHS),
        )
        for contract_path, expected_paths in contracts:
            task = json.loads((ROOT / contract_path).read_text())
            self.assertEqual(set(task["allowed_paths"]), expected_paths)
            for path in expected_paths:
                with self.subTest(task=task["task_id"], path=path), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.copy_repository(root)
                    errors, _ = c.check(
                        root, active_task_id=task["task_id"], active_branch=task["branch"],
                        changed_paths={path})
                    self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
