"""Exact APBRA-144 authority and fail-closed governance checks."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_ai_native_clarification", ROOT / "scripts/check_bootstrap.py"
)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class AINativeClarificationScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-144-ai-native-iterative-clarification.json"
        self.task = json.loads((ROOT / self.task_path).read_text())

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.AI_NATIVE_CLARIFICATION_PATHS)
        names.update(c.AI_NATIVE_CLARIFICATION_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-144 fixture\n")

    def check_path(self, root: Path, path: str, *, task_id="APBRA-144", branch=None):
        return c.check(
            root,
            active_task_id=task_id,
            active_branch=self.task["branch"] if branch is None else branch,
            changed_paths={path},
        )[0]

    def test_exact_nine_implementation_paths_pass_only_with_apbra_144(self):
        expected = {
            "apps/web/src/clarification.ts",
            "apps/web/src/clarification.test.ts",
            "apps/web/src/foundry.ts",
            "apps/web/src/foundry.test.ts",
            "apps/web/src/confirmedRequirements.ts",
            "apps/web/src/confirmedRequirements.test.ts",
            "apps/web/src/EnterpriseApp.tsx",
            "apps/web/src/App.test.tsx",
            "apps/web/src/tenant.ts",
        }
        self.assertEqual(c.AI_NATIVE_CLARIFICATION_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertEqual(
            self.task["base_commit"],
            "3e9d2f9c06c4e19046068923687af9d9defcdbf5",
        )
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        prior = json.loads((ROOT / "tasks/APBRA-143-typed-confirmed-requirements.json").read_text())
        for path in expected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                self.assertEqual(self.check_path(root, path), [])
                if path.startswith("apps/web/src/clarification") or path == "apps/web/src/tenant.ts":
                    errors, _ = c.check(
                        root,
                        active_task_id="APBRA-143",
                        active_branch=prior["branch"],
                        changed_paths={path},
                    )
                    self.assertIn(f"File outside active task scope: {path}", errors)

    def test_registration_scope_is_exact_and_separate(self):
        expected = {
            "scripts/check_bootstrap.py",
            "tasks/APBRA-144-ai-native-iterative-clarification.json",
            "tests/bootstrap/test_ai_native_clarification_scope.py",
        }
        self.assertEqual(c.AI_NATIVE_CLARIFICATION_REGISTRATION_PATHS, expected)
        self.assertTrue(expected.isdisjoint(c.AI_NATIVE_CLARIFICATION_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors, _ = c.check(
                root,
                active_task_id="APBRA-144",
                active_branch=self.task["branch"],
                changed_paths=expected,
            )
            self.assertEqual(errors, [])

    def test_excluded_architecture_layers_are_rejected(self):
        rejected = (
            "apps/web/src/rag.ts",
            "apps/web/knowledge/report-design-standards.md",
            "apps/web/src/reportDesignNormalization.ts",
            "apps/web/src/genericPowerBI.ts",
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
                    target.write_text("outside APBRA-144 scope\n")
                self.assertIn(
                    f"File outside active task scope: {path}",
                    self.check_path(root, path),
                )

    def test_missing_malformed_broadened_and_stale_contracts_fail_closed(self):
        mutations = (
            (None, "Unknown or invalid active task authority"),
            ({"allowed_paths": ["apps/web/src/**"]}, "Unexpected AI-native clarification scope"),
            (
                {"allowed_paths": self.task["allowed_paths"] + ["apps/web/src/rag.ts"]},
                "Unexpected AI-native clarification scope",
            ),
            ({"task_id": "APBRA-999"}, "Unexpected AI-native clarification identity"),
            ({"assigned_agent": "APBRA-AI"}, "Unexpected AI-native clarification identity"),
            (
                {"branch": "agent/APBRA-DEVOPS/APBRA-144-other"},
                "Unexpected AI-native clarification branch",
            ),
            ({"base_commit": "0" * 40}, "Stale AI-native clarification base"),
            ({"owner_acceptance": "PENDING"}, "AI-native clarification requires issued implementation acceptance"),
            ({"source_ids": ["repo-bootstrap"]}, "AI-native clarification requires its specific accepted source"),
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
                errors = self.check_path(root, "apps/web/src/clarification.ts")
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn(
                    "File outside active task scope: apps/web/src/clarification.ts",
                    errors,
                )

    def test_contract_encodes_ai_human_and_deterministic_boundaries(self):
        criteria = " ".join(self.task["acceptance_criteria"])
        for required in (
            "Business Mode",
            "Advanced or BI Mode",
            "NEEDS_CLARIFICATION",
            "READY_FOR_CONFIRMATION",
            "HUMAN_REVIEW_REQUIRED",
            "natural-language answers",
            "Confirm or Correct",
            "PLATFORM_POLICY",
            "TENANT_GOVERNED",
            "DEMO_FIXTURE",
            "deterministic TypeScript never parses arbitrary prose",
            "GPT-4.1",
            "service or operations",
            "sales or performance",
            "marketing or effectiveness",
            "customer or retention",
        ):
            with self.subTest(required=required):
                self.assertIn(required, criteria)
        exclusions = " ".join(self.task["out_of_scope"])
        self.assertIn("Application behavior on the APBRA-144 governance branch", exclusions)
        self.assertIn("universal Power BI compatibility", exclusions)

    def test_apbra_143_remains_independently_active(self):
        task = json.loads((ROOT / "tasks/APBRA-143-typed-confirmed-requirements.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(
                c.check(
                    root,
                    active_task_id="APBRA-143",
                    active_branch=task["branch"],
                    changed_paths={"apps/web/src/confirmedRequirements.ts"},
                )[0],
                [],
            )
            self.assertIn(
                "File outside active task scope: apps/web/src/clarification.ts",
                c.check(
                    root,
                    active_task_id="APBRA-143",
                    active_branch=task["branch"],
                    changed_paths={"apps/web/src/clarification.ts"},
                )[0],
            )


if __name__ == "__main__":
    unittest.main()
