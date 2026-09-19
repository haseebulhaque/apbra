"""Exact APBRA-138 measure-resolution authority and fail-closed scope checks."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_measure_resolution", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class MeasureResolutionScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-138-measure-resolution.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        catalog = json.loads((ROOT / "agents/catalog.json").read_text())
        self.card = next(card for card in catalog["cards"] if card["agent_id"] == self.task["assigned_agent"])

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.MEASURE_RESOLUTION_PATHS | {self.task_path})
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("// APBRA-138 scope fixture\n")

    def check_path(self, root: Path, path: str, *, task_id="APBRA-138", branch=None):
        return c.check(root, active_task_id=task_id,
                       active_branch=self.task["branch"] if branch is None else branch,
                       changed_paths={path})[0]

    def test_valid_authority_admits_exact_eight_paths_through_real_check(self):
        self.assertEqual(set(self.task["allowed_paths"]), c.MEASURE_RESOLUTION_PATHS)
        self.assertEqual(len(c.MEASURE_RESOLUTION_PATHS), 8)
        for path in c.MEASURE_RESOLUTION_PATHS:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                self.assertEqual(self.check_path(root, path), [])

    def test_historical_contract_paths_do_not_leak_into_apbra_138(self):
        rejected = (
            "apps/web/src/style.css",
            "apps/web/src/EnterpriseUI.tsx",
            "apps/web/src/EnterpriseUI.test.tsx",
            "apps/web/src/deploymentGuide.ts",
            "apps/web/package.json",
            "apps/web/package-lock.json",
            "apps/web/src/rag.ts",
            "apps/web/src/schemaIngestion.ts",
            "apps/web/src/unrelated.ts",
            "apps/api/src/handler.ts",
            "apps/web/.env.local",
            ".env.local",
            "output/candidate.zip",
            "artifacts/generated/result.json",
        )
        for path in rejected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_text("outside APBRA-138 scope\n")
                errors = self.check_path(root, path)
                self.assertIn(f"File outside active task scope: {path}", errors)

    def test_overlapping_paths_require_valid_active_apbra_138_authority(self):
        for path in ("apps/web/src/EnterpriseApp.tsx", "apps/web/src/App.test.tsx",
                     "apps/web/src/genericPowerBI.ts", "apps/web/src/foundry.ts"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                invalid = copy.deepcopy(self.task)
                invalid["owner_acceptance"] = "PENDING"
                (root / self.task_path).write_text(json.dumps(invalid))
                errors = self.check_path(root, path)
                self.assertIn(f"File outside active task scope: {path}", errors)

    def test_wildcard_extra_stale_and_malformed_contracts_fail_closed(self):
        mutations = (
            (None, "Unknown or invalid active task authority"),
            ({"allowed_paths": ["apps/web/**"]}, "Unexpected measure resolution scope"),
            ({"allowed_paths": self.task["allowed_paths"] + ["apps/web/src/style.css"]}, "Unexpected measure resolution scope"),
            ({"task_id": "APBRA-999"}, "Unexpected measure resolution identity"),
            ({"assigned_agent": "APBRA-QA"}, "Unexpected measure resolution identity"),
            ({"branch": "agent/APBRA-DEVOPS/APBRA-137-reused"}, "Branch must match the agent and Jira task"),
            ({"task_mode": "REVIEW"}, "Measure resolution requires issued implementation acceptance"),
            ({"readiness": "NEEDS_REFINEMENT"}, "Implementation mode/readiness mismatch"),
            ({"owner_acceptance": "PENDING"}, "Implementation acceptance is not recorded"),
            ({"source_ids": ["engineering-structure"]}, "Measure resolution requires its specific accepted source"),
            ({"objective": None}, "None is not of type 'string'"),
        )
        for mutation, expected in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                if mutation is None:
                    (root / self.task_path).unlink()
                else:
                    changed = copy.deepcopy(self.task)
                    changed.update(mutation)
                    (root / self.task_path).write_text(json.dumps(changed))
                errors = self.check_path(root, "apps/web/src/genericPowerBI.ts")
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_active_identity_is_required_known_and_branch_bound(self):
        path = "apps/web/src/genericPowerBI.ts"
        cases = (
            (None, self.task["branch"], "Active task identity missing"),
            ("APBRA138", self.task["branch"], "Malformed active task identity"),
            ("APBRA-999", self.task["branch"], "Unknown or invalid active task authority"),
            ("APBRA-138", "agent/APBRA-DEVOPS/APBRA-137-reused", "Active branch conflicts"),
            ("APBRA-138", None, "Active task branch identity missing"),
        )
        for task_id, branch, expected in cases:
            with self.subTest(task_id=task_id, branch=branch), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                errors, _ = c.check(root, active_task_id=task_id, active_branch=branch,
                                    changed_paths={path})
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_secret_and_symlink_protections_remain_effective(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            target = root / "apps/web/src/genericPowerBI.ts"
            target.write_text("const credential = 'ghp_" + "A" * 36 + "';\n")
            errors = self.check_path(root, "apps/web/src/genericPowerBI.ts")
            self.assertIn("High-confidence credential pattern in: apps/web/src/genericPowerBI.ts", errors)
            target.unlink()
            target.symlink_to(root / "README.md")
            errors = self.check_path(root, "apps/web/src/genericPowerBI.ts")
            self.assertIn("File outside safe bootstrap scope: apps/web/src/genericPowerBI.ts", errors)

    def test_apbra_137_76_and_92_remain_individually_active(self):
        contracts = (
            ("tasks/APBRA-137-final-capstone-ux.json", c.CAPSTONE_UX_PATHS),
            ("tasks/APBRA-76-deployment-guide.json", c.DEPLOYMENT_GUIDE_PATHS),
            ("tasks/APBRA-92-evaluation.json", c.CAPSTONE_EVALUATION_PATHS),
        )
        for contract_path, expected_paths in contracts:
            task = json.loads((ROOT / contract_path).read_text())
            self.assertEqual(set(task["allowed_paths"]), expected_paths)
            sample = next(iter(expected_paths))
            with self.subTest(task=task["task_id"], path=sample), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                errors, _ = c.check(root, active_task_id=task["task_id"],
                                    active_branch=task["branch"], changed_paths={sample})
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
