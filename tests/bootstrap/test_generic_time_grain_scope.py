"""Exact APBRA-145 authority and fail-closed governance checks."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_generic_time_grain", ROOT / "scripts/check_bootstrap.py"
)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class GenericTimeGrainScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-145-generic-time-grain-support.json"
        self.task = json.loads((ROOT / self.task_path).read_text())

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.GENERIC_TIME_GRAIN_PATHS)
        names.update(c.GENERIC_TIME_GRAIN_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-145 fixture\n")

    def check_path(self, root: Path, path: str, *, task_id="APBRA-145", branch=None):
        return c.check(
            root,
            active_task_id=task_id,
            active_branch=self.task["branch"] if branch is None else branch,
            changed_paths={path},
        )[0]

    def test_exact_seven_implementation_paths_pass_only_with_apbra_145(self):
        expected = {
            "apps/web/src/foundry.ts",
            "apps/web/src/foundry.test.ts",
            "apps/web/src/reportDesignNormalization.ts",
            "apps/web/src/reportDesignNormalization.test.ts",
            "apps/web/src/genericPowerBI.ts",
            "apps/web/src/genericPowerBI.test.ts",
            "apps/web/src/tenant.ts",
        }
        self.assertEqual(c.GENERIC_TIME_GRAIN_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertEqual(
            self.task["base_commit"],
            "f25c3caca0ec3364d56be5303dae543bf502a4e1",
        )
        self.assertNotIn("apps/web/src/confirmedRequirements.ts", expected)
        self.assertNotIn("apps/web/src/confirmedRequirements.test.ts", expected)
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        prior = json.loads((ROOT / "tasks/APBRA-144-ai-native-iterative-clarification.json").read_text())
        for path in expected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                self.assertEqual(self.check_path(root, path), [])
                if path in {
                    "apps/web/src/reportDesignNormalization.ts",
                    "apps/web/src/reportDesignNormalization.test.ts",
                    "apps/web/src/genericPowerBI.ts",
                    "apps/web/src/genericPowerBI.test.ts",
                }:
                    errors, _ = c.check(
                        root,
                        active_task_id="APBRA-144",
                        active_branch=prior["branch"],
                        changed_paths={path},
                    )
                    self.assertIn(f"File outside active task scope: {path}", errors)

    def test_registration_scope_is_exact_and_separate(self):
        expected = {
            "scripts/check_bootstrap.py",
            "tasks/APBRA-145-generic-time-grain-support.json",
            "tests/bootstrap/test_generic_time_grain_scope.py",
        }
        self.assertEqual(c.GENERIC_TIME_GRAIN_REGISTRATION_PATHS, expected)
        self.assertTrue(expected.isdisjoint(c.GENERIC_TIME_GRAIN_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors, _ = c.check(
                root,
                active_task_id="APBRA-145",
                active_branch=self.task["branch"],
                changed_paths=expected,
            )
            self.assertEqual(errors, [])

    def test_unrelated_architecture_layers_are_rejected(self):
        rejected = (
            "apps/web/src/clarification.ts",
            "apps/web/src/confirmedRequirements.ts",
            "apps/web/src/EnterpriseApp.tsx",
            "apps/web/src/rag.ts",
            "apps/web/knowledge/report-design-standards.md",
            "apps/web/src/guardrail.ts",
            "apps/web/src/schemaIngestion.ts",
            "apps/web/src/powerbi.ts",
            "apps/web/src/workflow.ts",
            "apps/web/src/style.css",
            "apps/web/package.json",
            "apps/api/src/handler.ts",
            "packages/domain/index.ts",
            ".env.local",
            "output/report.candidate.zip",
            "artifacts/live-run.json",
            "README.md",
        )
        for path in rejected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_text("outside APBRA-145 scope\n")
                self.assertIn(
                    f"File outside active task scope: {path}",
                    self.check_path(root, path),
                )

    def test_missing_malformed_broadened_and_stale_contracts_fail_closed(self):
        mutations = (
            (None, "Unknown or invalid active task authority"),
            ({"allowed_paths": ["apps/web/src/**"]}, "Unexpected generic time-grain scope"),
            (
                {"allowed_paths": self.task["allowed_paths"] + ["apps/web/src/confirmedRequirements.ts"]},
                "Unexpected generic time-grain scope",
            ),
            ({"task_id": "APBRA-999"}, "Unexpected generic time-grain identity"),
            ({"assigned_agent": "APBRA-AI"}, "Unexpected generic time-grain identity"),
            (
                {"branch": "agent/APBRA-DEVOPS/APBRA-145-other"},
                "Unexpected generic time-grain branch",
            ),
            ({"base_commit": "0" * 40}, "Stale generic time-grain base"),
            (
                {"owner_acceptance": "PENDING"},
                "Generic time-grain support requires issued implementation acceptance",
            ),
            (
                {"source_ids": ["repo-bootstrap"]},
                "Generic time-grain support requires its specific accepted source",
            ),
        )
        for mutation, expected in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                target = root / self.task_path
                if mutation is None:
                    target.unlink()
                else:
                    changed = dict(self.task)
                    changed.update(mutation)
                    target.write_text(json.dumps(changed))
                errors = self.check_path(root, "apps/web/src/genericPowerBI.ts")
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn(
                    "File outside active task scope: apps/web/src/genericPowerBI.ts",
                    errors,
                )

    def test_contract_encodes_time_grain_and_retry_boundaries(self):
        criteria = " ".join(self.task["acceptance_criteria"])
        for required in (
            "DAY",
            "WEEK",
            "MONTH",
            "QUARTER",
            "YEAR",
            "typed ReportDesign",
            "raw Date category binding alone never proves",
            "UNSUPPORTED",
            "HUMAN_REVIEW_REQUIRED",
            "exact structured domain-neutral findings",
            "exact allowed citation IDs",
            "exactly two total model attempts",
            "second invalid Report Design fails closed",
            "APBRA-143 confirmation",
            "APBRA-144 iterative clarification",
        ):
            with self.subTest(required=required):
                self.assertIn(required, criteria)
        exclusions = " ".join(self.task["out_of_scope"])
        self.assertIn("universal date intelligence framework", exclusions)
        self.assertIn("Scenario-specific production logic", exclusions)

    def test_apbra_144_remains_independently_active(self):
        task = json.loads((ROOT / "tasks/APBRA-144-ai-native-iterative-clarification.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(
                c.check(
                    root,
                    active_task_id="APBRA-144",
                    active_branch=task["branch"],
                    changed_paths={"apps/web/src/clarification.ts"},
                )[0],
                [],
            )
            self.assertIn(
                "File outside active task scope: apps/web/src/clarification.ts",
                self.check_path(root, "apps/web/src/clarification.ts"),
            )


if __name__ == "__main__":
    unittest.main()
