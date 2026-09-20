"""Exact APBRA-141 authority and fail-closed active-task scope checks."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_measure_contract_pipeline", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class MeasureContractPipelineScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-141-measure-contract-pipeline.json"
        self.task = json.loads((ROOT / self.task_path).read_text())

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.MEASURE_CONTRACT_PIPELINE_PATHS | {self.task_path})
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-141 fixture\n")

    def check_path(self, root: Path, path: str, *, task_id="APBRA-141", branch=None):
        return c.check(root, active_task_id=task_id,
                       active_branch=self.task["branch"] if branch is None else branch,
                       changed_paths={path})[0]

    def test_exact_four_paths_pass_real_check_only_with_apbra_141(self):
        expected = {
            "apps/web/src/foundry.ts", "apps/web/src/foundry.test.ts",
            "apps/web/src/EnterpriseApp.tsx", "apps/web/src/App.test.tsx",
        }
        self.assertEqual(c.MEASURE_CONTRACT_PIPELINE_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        for path in expected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy_repository(root)
                self.assertEqual(self.check_path(root, path), [])
                errors, _ = c.check(root, active_task_id="APBRA-140",
                                    active_branch=json.loads((ROOT / "tasks/APBRA-140-capstone-documentation.json").read_text())["branch"],
                                    changed_paths={path})
                self.assertIn(f"File outside active task scope: {path}", errors)

    def test_registration_scope_is_exact_and_separate(self):
        expected = {
            "scripts/check_bootstrap.py", "tasks/APBRA-141-measure-contract-pipeline.json",
            "tests/bootstrap/test_measure_contract_pipeline_scope.py",
        }
        self.assertEqual(c.MEASURE_CONTRACT_PIPELINE_REGISTRATION_PATHS, expected)
        self.assertTrue(expected.isdisjoint(c.MEASURE_CONTRACT_PIPELINE_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.copy_repository(root)
            errors, _ = c.check(root, active_task_id="APBRA-141",
                                active_branch=self.task["branch"], changed_paths=expected)
            self.assertEqual(errors, [])

    def test_explicit_exclusions_and_historical_paths_are_rejected(self):
        rejected = (
            "apps/web/src/reportDesignNormalization.ts", "apps/web/src/reportDesignNormalization.test.ts",
            "apps/web/src/genericPowerBI.ts", "apps/web/src/genericPowerBI.test.ts",
            "apps/web/src/guardrail.ts", "apps/web/src/guardrail.test.ts",
            "apps/web/src/rag.ts", "apps/web/src/schemaIngestion.ts",
            "apps/web/src/deploymentGuide.ts", "apps/web/src/style.css",
            "apps/web/src/EnterpriseUI.tsx", "apps/web/package.json", "apps/web/package-lock.json",
            "apps/api/src/handler.ts", "packages/domain/index.ts", "apps/web/.env.local", ".env.local",
            "output/report.candidate.zip", "manual-testing/report.candidate.zip", "artifacts/run.json",
            "tasks/APBRA-140-capstone-documentation.json", "docs/source-register.json",
            "docs/engineering/unrelated.md",
        )
        for path in rejected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy_repository(root)
                target = root / path; target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists(): target.write_text("outside APBRA-141 scope\n")
                self.assertIn(f"File outside active task scope: {path}", self.check_path(root, path))

    def test_contract_missing_malformed_broadened_and_stale_fail_closed(self):
        mutations = (
            (None, "Unknown or invalid active task authority"),
            ({"allowed_paths": ["apps/web/src/**"]}, "Unexpected measure contract pipeline scope"),
            ({"allowed_paths": self.task["allowed_paths"] + ["apps/web/src/genericPowerBI.ts"]}, "Unexpected measure contract pipeline scope"),
            ({"task_id": "APBRA-999"}, "Unexpected measure contract pipeline identity"),
            ({"assigned_agent": "APBRA-DEV-FE"}, "Unexpected measure contract pipeline identity"),
            ({"branch": "agent/APBRA-DEVOPS/APBRA-141-other"}, "Unexpected measure contract pipeline branch"),
            ({"base_commit": "0" * 40}, "Stale measure contract pipeline base"),
            ({"source_ids": ["engineering-structure"]}, "Measure contract pipeline requires its specific accepted source"),
            ({"objective": None}, "None is not of type 'string'"),
        )
        for mutation, expected in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy_repository(root)
                if mutation is None: (root / self.task_path).unlink()
                else:
                    changed = copy.deepcopy(self.task); changed.update(mutation)
                    (root / self.task_path).write_text(json.dumps(changed))
                errors = self.check_path(root, "apps/web/src/foundry.ts")
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn("File outside active task scope: apps/web/src/foundry.ts", errors)

    def test_active_identity_and_branch_conflicts_fail_closed(self):
        cases = (
            (None, self.task["branch"], "Active task identity missing"),
            ("APBRA141", self.task["branch"], "Malformed active task identity"),
            ("APBRA-999", self.task["branch"], "Unknown or invalid active task authority"),
            ("APBRA-141", "agent/APBRA-DEVOPS/APBRA-140-reused", "Active branch conflicts"),
            ("APBRA-141", None, "Active task branch identity missing"),
        )
        for task_id, branch, expected in cases:
            with self.subTest(task_id=task_id, branch=branch), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy_repository(root)
                errors, _ = c.check(root, active_task_id=task_id, active_branch=branch,
                                    changed_paths={"apps/web/src/foundry.ts"})
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn("File outside active task scope: apps/web/src/foundry.ts", errors)

    def test_secret_and_symlink_controls_remain_effective(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.copy_repository(root)
            target = root / "apps/web/src/foundry.ts"
            target.write_text("credential='ghp_" + "A" * 36 + "'\n")
            self.assertIn("High-confidence credential pattern in: apps/web/src/foundry.ts", self.check_path(root, "apps/web/src/foundry.ts"))
            target.unlink(); target.symlink_to(root / "apps/web/src/App.test.tsx")
            self.assertIn("File outside safe bootstrap scope: apps/web/src/foundry.ts", self.check_path(root, "apps/web/src/foundry.ts"))

    def test_historical_contracts_remain_individually_active(self):
        contracts = (
            ("tasks/APBRA-140-capstone-documentation.json", c.CAPSTONE_DOCUMENTATION_PATHS),
            ("tasks/APBRA-139-report-design-normalization.json", c.REPORT_DESIGN_NORMALIZATION_PATHS),
            ("tasks/APBRA-138-measure-resolution.json", c.MEASURE_RESOLUTION_PATHS),
            ("tasks/APBRA-137-final-capstone-ux.json", c.CAPSTONE_UX_PATHS),
            ("tasks/APBRA-92-evaluation.json", c.CAPSTONE_EVALUATION_PATHS),
            ("tasks/APBRA-76-deployment-guide.json", c.DEPLOYMENT_GUIDE_PATHS),
        )
        for contract_path, expected_paths in contracts:
            task = json.loads((ROOT / contract_path).read_text()); sample = next(iter(expected_paths))
            with self.subTest(task=task["task_id"]), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy_repository(root)
                self.assertEqual(c.check(root, active_task_id=task["task_id"], active_branch=task["branch"], changed_paths={sample})[0], [])
        baseline = json.loads((ROOT / "tasks/APBRA-85-bootstrap.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.copy_repository(root)
            self.assertEqual(c.check(root, active_task_id="APBRA-85", active_branch=baseline["branch"], changed_paths={baseline["allowed_paths"][0]})[0], [])

    def test_historical_registration_never_widens_apbra_141(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.copy_repository(root)
            for path in ("apps/web/src/reportDesignNormalization.ts", "apps/web/src/genericPowerBI.ts", "README.md"):
                with self.subTest(path=path):
                    self.assertIn(f"File outside active task scope: {path}", self.check_path(root, path))


if __name__ == "__main__":
    unittest.main()
