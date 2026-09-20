"""Exact APBRA-142 authority and fail-closed active-task scope checks."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_layout_repair", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class LayoutRepairScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-142-layout-repair.json"
        self.task = json.loads((ROOT / self.task_path).read_text())

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.LAYOUT_REPAIR_PATHS | c.LAYOUT_REPAIR_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-142 fixture\n")

    def check_path(self, root: Path, path: str, *, task_id="APBRA-142", branch=None):
        return c.check(root, active_task_id=task_id,
                       active_branch=self.task["branch"] if branch is None else branch,
                       changed_paths={path})[0]

    def test_exact_six_implementation_paths_pass_only_with_apbra_142(self):
        expected = {
            "apps/web/src/foundry.ts", "apps/web/src/foundry.test.ts",
            "apps/web/src/EnterpriseApp.tsx", "apps/web/src/App.test.tsx",
            "apps/web/src/reportDesignNormalization.ts",
            "apps/web/src/reportDesignNormalization.test.ts",
        }
        self.assertEqual(c.LAYOUT_REPAIR_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        prior = json.loads((ROOT / "tasks/APBRA-141-measure-contract-pipeline.json").read_text())
        for path in expected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy_repository(root)
                self.assertEqual(self.check_path(root, path), [])
                if path.startswith("apps/web/src/reportDesignNormalization"):
                    errors, _ = c.check(root, active_task_id="APBRA-141",
                                        active_branch=prior["branch"], changed_paths={path})
                    self.assertIn(f"File outside active task scope: {path}", errors)

    def test_registration_scope_is_exact_and_separate(self):
        expected = {
            "scripts/check_bootstrap.py", "tasks/APBRA-142-layout-repair.json",
            "tests/bootstrap/test_layout_repair_scope.py",
        }
        self.assertEqual(c.LAYOUT_REPAIR_REGISTRATION_PATHS, expected)
        self.assertTrue(expected.isdisjoint(c.LAYOUT_REPAIR_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.copy_repository(root)
            errors, _ = c.check(root, active_task_id="APBRA-142",
                                active_branch=self.task["branch"], changed_paths=expected)
            self.assertEqual(errors, [])

    def test_explicit_exclusions_are_rejected(self):
        rejected = (
            "apps/web/src/genericPowerBI.ts", "apps/web/src/guardrail.ts",
            "apps/web/src/rag.ts", "apps/web/src/schemaIngestion.ts",
            "apps/web/src/deploymentGuide.ts", "apps/web/src/style.css",
            "apps/web/package.json", "apps/api/src/handler.ts",
            "packages/domain/index.ts", "apps/web/.env.local", ".env.local",
            "output/report.candidate.zip", "artifacts/run.json", "README.md",
        )
        for path in rejected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy_repository(root)
                target = root / path; target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists(): target.write_text("outside APBRA-142 scope\n")
                self.assertIn(f"File outside active task scope: {path}", self.check_path(root, path))

    def test_missing_malformed_broadened_and_stale_contracts_fail_closed(self):
        mutations = (
            (None, "Unknown or invalid active task authority"),
            ({"allowed_paths": ["apps/web/src/**"]}, "Unexpected layout repair scope"),
            ({"allowed_paths": self.task["allowed_paths"] + ["apps/web/src/genericPowerBI.ts"]}, "Unexpected layout repair scope"),
            ({"task_id": "APBRA-999"}, "Unexpected layout repair identity"),
            ({"assigned_agent": "APBRA-DEV-FE"}, "Unexpected layout repair identity"),
            ({"branch": "agent/APBRA-DEVOPS/APBRA-142-other"}, "Unexpected layout repair branch"),
            ({"base_commit": "0" * 40}, "Stale layout repair base"),
            ({"source_ids": ["engineering-structure"]}, "Layout repair requires its specific accepted source"),
        )
        for mutation, expected in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy_repository(root)
                if mutation is None:
                    (root / self.task_path).unlink()
                else:
                    changed = copy.deepcopy(self.task); changed.update(mutation)
                    (root / self.task_path).write_text(json.dumps(changed))
                errors = self.check_path(root, "apps/web/src/reportDesignNormalization.ts")
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn("File outside active task scope: apps/web/src/reportDesignNormalization.ts", errors)

    def test_identity_branch_secret_and_symlink_controls_remain_effective(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.copy_repository(root)
            errors, _ = c.check(root, active_task_id="APBRA-142",
                                active_branch="agent/APBRA-DEVOPS/APBRA-141-reused",
                                changed_paths={"apps/web/src/reportDesignNormalization.ts"})
            self.assertIn("Active branch conflicts with task authority: agent/APBRA-DEVOPS/APBRA-141-reused", errors)
            target = root / "apps/web/src/reportDesignNormalization.ts"
            target.write_text("credential='ghp_" + "A" * 36 + "'\n")
            self.assertIn("High-confidence credential pattern in: apps/web/src/reportDesignNormalization.ts", self.check_path(root, "apps/web/src/reportDesignNormalization.ts"))
            target.unlink(); target.symlink_to(root / "apps/web/src/App.test.tsx")
            self.assertIn("File outside safe bootstrap scope: apps/web/src/reportDesignNormalization.ts", self.check_path(root, "apps/web/src/reportDesignNormalization.ts"))

    def test_apbra_141_remains_independently_active(self):
        task = json.loads((ROOT / "tasks/APBRA-141-measure-contract-pipeline.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.copy_repository(root)
            self.assertEqual(c.check(root, active_task_id="APBRA-141", active_branch=task["branch"],
                                     changed_paths={"apps/web/src/foundry.ts"})[0], [])
            self.assertIn("File outside active task scope: apps/web/src/reportDesignNormalization.ts",
                          c.check(root, active_task_id="APBRA-141", active_branch=task["branch"],
                                  changed_paths={"apps/web/src/reportDesignNormalization.ts"})[0])


if __name__ == "__main__":
    unittest.main()
