"""Exact APBRA-143 authority and fail-closed active-task scope checks."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_typed_confirmed_requirements", ROOT / "scripts/check_bootstrap.py"
)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class TypedConfirmedRequirementsScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-143-typed-confirmed-requirements.json"
        self.task = json.loads((ROOT / self.task_path).read_text())

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(
            c.TYPED_CONFIRMED_REQUIREMENTS_PATHS
            | c.TYPED_CONFIRMED_REQUIREMENTS_REGISTRATION_PATHS
        )
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-143 fixture\n")

    def check_path(self, root: Path, path: str, *, task_id="APBRA-143", branch=None):
        return c.check(
            root,
            active_task_id=task_id,
            active_branch=self.task["branch"] if branch is None else branch,
            changed_paths={path},
        )[0]

    def test_exact_eight_implementation_paths_pass_only_with_apbra_143(self):
        expected = {
            "apps/web/src/foundry.ts",
            "apps/web/src/foundry.test.ts",
            "apps/web/src/confirmedRequirements.ts",
            "apps/web/src/confirmedRequirements.test.ts",
            "apps/web/src/EnterpriseApp.tsx",
            "apps/web/src/App.test.tsx",
            "apps/web/src/reportDesignNormalization.ts",
            "apps/web/src/reportDesignNormalization.test.ts",
        }
        self.assertEqual(c.TYPED_CONFIRMED_REQUIREMENTS_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertEqual(
            self.task["base_commit"],
            "aac4639f30bc1d785972dd48b704537ee98548d7",
        )
        self.assertTrue(
            any(self.task["base_commit"] in item for item in self.task["dependencies"])
        )
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        prior = json.loads((ROOT / "tasks/APBRA-142-layout-repair.json").read_text())
        for path in expected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                self.assertEqual(self.check_path(root, path), [])
                if path.startswith("apps/web/src/confirmedRequirements"):
                    errors, _ = c.check(
                        root,
                        active_task_id="APBRA-142",
                        active_branch=prior["branch"],
                        changed_paths={path},
                    )
                    self.assertIn(f"File outside active task scope: {path}", errors)

    def test_registration_scope_is_exact_and_separate(self):
        expected = {
            "scripts/check_bootstrap.py",
            "tasks/APBRA-143-typed-confirmed-requirements.json",
            "tests/bootstrap/test_typed_confirmed_requirements_scope.py",
        }
        self.assertEqual(c.TYPED_CONFIRMED_REQUIREMENTS_REGISTRATION_PATHS, expected)
        self.assertTrue(expected.isdisjoint(c.TYPED_CONFIRMED_REQUIREMENTS_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors, _ = c.check(
                root,
                active_task_id="APBRA-143",
                active_branch=self.task["branch"],
                changed_paths=expected,
            )
            self.assertEqual(errors, [])

    def test_explicit_exclusions_are_rejected(self):
        rejected = (
            "apps/web/src/genericPowerBI.ts",
            "apps/web/src/guardrail.ts",
            "apps/web/src/rag.ts",
            "apps/web/knowledge/report-design-standards.md",
            "apps/web/src/schemaIngestion.ts",
            "apps/web/src/deploymentGuide.ts",
            "apps/web/src/style.css",
            "apps/web/package.json",
            "apps/api/src/handler.ts",
            "packages/domain/index.ts",
            "apps/web/.env.local",
            ".env.local",
            "output/report.candidate.zip",
            "artifacts/run.json",
            "README.md",
        )
        for path in rejected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_text("outside APBRA-143 scope\n")
                self.assertIn(
                    f"File outside active task scope: {path}",
                    self.check_path(root, path),
                )

    def test_missing_malformed_broadened_and_stale_contracts_fail_closed(self):
        mutations = (
            (None, "Unknown or invalid active task authority"),
            ({"allowed_paths": ["apps/web/src/**"]}, "Unexpected typed confirmed requirements scope"),
            (
                {"allowed_paths": self.task["allowed_paths"] + ["apps/web/src/genericPowerBI.ts"]},
                "Unexpected typed confirmed requirements scope",
            ),
            ({"task_id": "APBRA-999"}, "Unexpected typed confirmed requirements identity"),
            ({"assigned_agent": "APBRA-DEV-FE"}, "Unexpected typed confirmed requirements identity"),
            (
                {"branch": "agent/APBRA-DEVOPS/APBRA-143-other"},
                "Unexpected typed confirmed requirements branch",
            ),
            ({"base_commit": "0" * 40}, "Stale typed confirmed requirements base"),
            (
                {"source_ids": ["engineering-structure"]},
                "Typed confirmed requirements requires its specific accepted source",
            ),
            (
                {"task_mode": "SPECIFICATION"},
                "Typed confirmed requirements requires issued implementation acceptance",
            ),
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
                errors = self.check_path(root, "apps/web/src/confirmedRequirements.ts")
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn(
                    "File outside active task scope: apps/web/src/confirmedRequirements.ts",
                    errors,
                )

    def test_identity_branch_secret_and_symlink_controls_remain_effective(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors, _ = c.check(
                root,
                active_task_id="APBRA-143",
                active_branch="agent/APBRA-DEVOPS/APBRA-142-reused",
                changed_paths={"apps/web/src/confirmedRequirements.ts"},
            )
            self.assertIn(
                "Active branch conflicts with task authority: agent/APBRA-DEVOPS/APBRA-142-reused",
                errors,
            )
            target = root / "apps/web/src/confirmedRequirements.ts"
            target.write_text("credential='ghp_" + "A" * 36 + "'\n")
            self.assertIn(
                "High-confidence credential pattern in: apps/web/src/confirmedRequirements.ts",
                self.check_path(root, "apps/web/src/confirmedRequirements.ts"),
            )
            target.unlink()
            target.symlink_to(root / "apps/web/src/App.test.tsx")
            self.assertIn(
                "File outside safe bootstrap scope: apps/web/src/confirmedRequirements.ts",
                self.check_path(root, "apps/web/src/confirmedRequirements.ts"),
            )

    def test_apbra_142_remains_independently_active(self):
        task = json.loads((ROOT / "tasks/APBRA-142-layout-repair.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(
                c.check(
                    root,
                    active_task_id="APBRA-142",
                    active_branch=task["branch"],
                    changed_paths={"apps/web/src/reportDesignNormalization.ts"},
                )[0],
                [],
            )
            self.assertIn(
                "File outside active task scope: apps/web/src/confirmedRequirements.ts",
                c.check(
                    root,
                    active_task_id="APBRA-142",
                    active_branch=task["branch"],
                    changed_paths={"apps/web/src/confirmedRequirements.ts"},
                )[0],
            )


if __name__ == "__main__":
    unittest.main()
