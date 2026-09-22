"""Exact APBRA-147 registration, stage separation and fail-closed scope checks."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_confirmation_readiness", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class ConfirmationReadinessIntegrityScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-147-confirmation-readiness-integrity.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.sources = json.loads((ROOT / "docs/source-register.json").read_text())

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.CONFIRMATION_READINESS_INTEGRITY_PATHS)
        names.update(c.CONFIRMATION_READINESS_INTEGRITY_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-147 fixture\n")

    def check(self, root: Path, changed_paths, *, task_id="APBRA-147", branch=None):
        return c.check(root, active_task_id=task_id,
                       active_branch=self.task["branch"] if branch is None else branch,
                       changed_paths=set(changed_paths))[0]

    def test_task_is_known_with_exact_eight_path_maximum_scope(self):
        expected = {
            "apps/web/src/clarification.ts", "apps/web/src/clarification.test.ts",
            "apps/web/src/confirmedRequirements.ts", "apps/web/src/confirmedRequirements.test.ts",
            "apps/web/src/EnterpriseApp.tsx", "apps/web/src/App.test.tsx",
            "apps/web/README.md", "docs/engineering/codex-handoff.md",
        }
        self.assertEqual(c.CONFIRMATION_READINESS_INTEGRITY_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertTrue(all("*" not in path for path in expected))
        for path in expected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy_repository(root)
                self.assertEqual(self.check(root, {path}), [])

    def test_registration_scope_is_exact_disjoint_and_admitted(self):
        expected = {"scripts/check_bootstrap.py", self.task_path,
                    "tests/bootstrap/test_confirmation_readiness_integrity_scope.py",
                    "docs/source-register.json"}
        self.assertEqual(c.CONFIRMATION_READINESS_INTEGRITY_REGISTRATION_PATHS, expected)
        self.assertTrue(expected.isdisjoint(c.CONFIRMATION_READINESS_INTEGRITY_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.copy_repository(root)
            self.assertEqual(self.check(root, expected), [])

    def test_registration_and_implementation_cannot_be_mixed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.copy_repository(root)
            errors = self.check(root, {"scripts/check_bootstrap.py", "apps/web/src/clarification.ts"})
            self.assertIn("APBRA-147 registration and implementation changes must remain separate", errors)

    def test_wrong_identity_branch_base_source_acceptance_and_scope_fail(self):
        mutations = (
            ({"task_id": "APBRA-999"}, "Unexpected confirmation readiness integrity identity"),
            ({"assigned_agent": "APBRA-AI"}, "Unexpected confirmation readiness integrity identity"),
            ({"branch": "agent/APBRA-DEVOPS/APBRA-147-wrong"}, "Unexpected confirmation readiness integrity branch"),
            ({"base_commit": "0" * 40}, "Stale confirmation readiness integrity base"),
            ({"owner_acceptance": "PENDING"}, "Confirmation readiness integrity requires issued implementation acceptance"),
            ({"source_ids": ["post-capstone-product-reconciliation"]}, "Confirmation readiness integrity requires its specific accepted source"),
            ({"allowed_paths": ["apps/web/src/**"]}, "Unexpected confirmation readiness integrity scope"),
            ({"allowed_paths": self.task["allowed_paths"][:-1]}, "Unexpected confirmation readiness integrity scope"),
            ({"allowed_paths": self.task["allowed_paths"] + ["apps/web/src/foundry.ts"]}, "Unexpected confirmation readiness integrity scope"),
        )
        for mutation, expected in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy_repository(root)
                changed = copy.deepcopy(self.task); changed.update(mutation)
                (root / self.task_path).write_text(json.dumps(changed))
                errors = self.check(root, {"apps/web/src/clarification.ts"})
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn("File outside active task scope: apps/web/src/clarification.ts", errors)

    def test_missing_malformed_unknown_task_and_wrong_branch_fail_closed(self):
        cases = ((None, self.task["branch"], "Active task identity missing"),
                 ("APBRA147", self.task["branch"], "Malformed active task identity"),
                 ("APBRA-999", self.task["branch"], "Unknown or invalid active task authority"),
                 ("APBRA-147", None, "Active task branch identity missing"),
                 ("APBRA-147", "agent/APBRA-DEVOPS/APBRA-147-wrong", "Active branch conflicts with task authority"))
        for task_id, branch, expected in cases:
            with self.subTest(task_id=task_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy_repository(root)
                errors = c.check(root, active_task_id=task_id, active_branch=branch,
                                 changed_paths={"apps/web/src/clarification.ts"})[0]
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_outside_scope_application_governance_artifact_env_and_historical_paths_fail(self):
        rejected = ("apps/web/src/foundry.ts", "apps/web/src/tenant.ts", "apps/web/package.json",
                    ".github/workflows/bootstrap.yml", "tasks/APBRA-144-ai-native-iterative-clarification.json",
                    "tests/bootstrap/test_ai_native_clarification_scope.py", "output/candidate.zip",
                    "artifacts/runtime-evidence.json", ".env.local", "apps/web/.env.local")
        for path in rejected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy_repository(root)
                target = root / path; target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists(): target.write_text("outside scope\n")
                self.assertIn(f"File outside active task scope: {path}", self.check(root, {path}))

    def test_source_and_contract_preserve_slice_boundaries(self):
        source_map = {source["id"]: source for source in self.sources["sources"]}
        current = source_map["post-capstone-confirmation-readiness-integrity"]
        self.assertEqual(current["content_id"], "APBRA-147")
        self.assertEqual(current["status"], "ACCEPTED")
        for historical in ("capstone-governance", "post-capstone-product-reconciliation",
                           "post-capstone-data-model-reconciliation"):
            self.assertIn(historical, source_map)
        criteria = " ".join(self.task["acceptance_criteria"] + self.task["out_of_scope"])
        for required in ("READY_FOR_CONFIRMATION", "exact visible interpretation", "Late analysis responses",
                         "Repeated answer", "Provider or technical failures", "previous accepted contract",
                         "configured aggregate effect", "Four unrelated synthetic domains",
                         "APBRA-143/APBRA-144", "expert service", "APBRA-150"):
            self.assertIn(required, criteria)

    def test_historical_authority_and_secret_symlink_protections_remain_active(self):
        for task_id, path in (("APBRA-140", "README.md"), ("APBRA-146", "README.md"),
                              ("APBRA-148", "AGENTS.md"), ("APBRA-159", "DATA-MODEL.md")):
            task_file = next(ROOT.glob(f"tasks/{task_id}-*.json"))
            historical = json.loads(task_file.read_text())
            with self.subTest(task_id=task_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.copy_repository(root)
                self.assertEqual(c.check(root, active_task_id=task_id,
                                         active_branch=historical["branch"], changed_paths={path})[0], [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.copy_repository(root)
            target = root / "apps/web/src/clarification.ts"
            target.write_text("credential: ghp_" + "A" * 36 + "\n")
            self.assertIn("High-confidence credential pattern in: apps/web/src/clarification.ts",
                          self.check(root, {"apps/web/src/clarification.ts"}))
            target.unlink(); target.symlink_to(root / "README.md")
            self.assertIn("File outside safe bootstrap scope: apps/web/src/clarification.ts",
                          self.check(root, {"apps/web/src/clarification.ts"}))


if __name__ == "__main__":
    unittest.main()
