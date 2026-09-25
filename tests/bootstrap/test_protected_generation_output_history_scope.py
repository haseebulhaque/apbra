"""Exact APBRA-164 registration, authority and fail-closed scope checks."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_apbra_164", ROOT / "scripts/check_bootstrap.py"
)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class ProtectedGenerationOutputHistoryScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-164-protected-generation-output-history.json"
        self.task = json.loads((ROOT / self.task_path).read_text())

    def copy_repository(self, root: Path) -> None:
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.PROTECTED_GENERATION_OUTPUT_HISTORY_PATHS)
        names.update(c.PROTECTED_GENERATION_OUTPUT_HISTORY_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-164 fixture\n")

    def check(self, root: Path, changed_paths, *, task_id="APBRA-164", branch=None):
        return c.check(
            root,
            active_task_id=task_id,
            active_branch=self.task["branch"] if branch is None else branch,
            changed_paths=set(changed_paths),
        )[0]

    def test_exact_finite_implementation_scope_is_registered(self):
        expected = set(self.task["allowed_paths"])
        self.assertEqual(c.PROTECTED_GENERATION_OUTPUT_HISTORY_PATHS, expected)
        self.assertEqual(len(expected), 70)
        self.assertTrue(all("*" not in path for path in expected))
        canonical = json.dumps(self.task, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            c.PROTECTED_GENERATION_OUTPUT_HISTORY_TASK_SHA256,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in sorted(expected):
                with self.subTest(path=path):
                    self.assertEqual(self.check(root, {path}), [])

    def test_registration_is_exact_disjoint_and_positive(self):
        expected = {
            "scripts/check_bootstrap.py",
            self.task_path,
            "tests/bootstrap/test_protected_generation_output_history_scope.py",
            "tests/bootstrap/test_invited_private_case_foundation_scope.py",
            "docs/source-register.json",
        }
        self.assertEqual(c.PROTECTED_GENERATION_OUTPUT_HISTORY_REGISTRATION_PATHS, expected)
        self.assertTrue(expected.isdisjoint(c.PROTECTED_GENERATION_OUTPUT_HISTORY_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, expected), [])
            for omitted in expected:
                errors = self.check(root, expected - {omitted})
                self.assertIn(
                    "APBRA-164 registration must change exactly its five governance files",
                    errors,
                )

    def test_registration_and_implementation_cannot_be_mixed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors = self.check(
                root,
                {"scripts/check_bootstrap.py", "apps/api/src/apbra_api/generation.py"},
            )
            self.assertIn(
                "APBRA-164 registration and implementation changes must remain separate",
                errors,
            )

    def test_wrong_identity_branch_base_source_acceptance_and_scope_fail(self):
        mutations = (
            ({"task_id": "APBRA-999"}, "Unexpected protected generation output history identity"),
            ({"assigned_agent": "APBRA-DEV-BE"}, "Unexpected protected generation output history identity"),
            ({"agent_card_version": "9.9"}, "Stale protected generation output history agent card version"),
            ({"branch": "agent/APBRA-DEVOPS/APBRA-164-wrong"}, "Unexpected protected generation output history branch"),
            ({"base_commit": "0" * 40}, "Stale protected generation output history base"),
            ({"owner_acceptance": "PENDING"}, "Protected generation output history requires issued implementation acceptance"),
            ({"source_ids": ["mvp1-durable-conversation-evidence-acceptance"]}, "Protected generation output history requires its specific accepted source"),
            ({"allowed_paths": ["apps/**"]}, "Unexpected protected generation output history scope"),
            ({"allowed_paths": self.task["allowed_paths"] + ["apps/api/extra.py"]}, "Unexpected protected generation output history scope"),
        )
        for mutation, expected in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                changed = copy.deepcopy(self.task)
                changed.update(mutation)
                (root / self.task_path).write_text(json.dumps(changed))
                errors = self.check(root, {"apps/api/src/apbra_api/generation.py"})
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_contract_and_source_are_hash_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            changed = copy.deepcopy(self.task)
            changed["objective"] += " broadened"
            (root / self.task_path).write_text(json.dumps(changed))
            self.assertIn(
                "Protected generation output history contract differs from accepted authority",
                self.check(root, {"apps/api/src/apbra_api/generation.py"}),
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            sources = json.loads((root / "docs/source-register.json").read_text())
            source = next(
                item
                for item in sources["sources"]
                if item["id"] == "mvp1-protected-generation-output-history"
            )
            source["acceptance"] += " broadened"
            (root / "docs/source-register.json").write_text(json.dumps(sources))
            self.assertIn(
                "Protected generation output history source differs from accepted provenance",
                self.check(root, {"apps/api/src/apbra_api/generation.py"}),
            )

    def test_missing_malformed_unknown_task_and_branch_fail_closed(self):
        cases = (
            (None, self.task["branch"], "Active task identity missing"),
            ("APBRA164", self.task["branch"], "Malformed active task identity"),
            ("APBRA-999", self.task["branch"], "Unknown or invalid active task authority"),
            ("APBRA-164", "agent/APBRA-DEVOPS/APBRA-164-wrong", "Active branch conflicts with task authority"),
        )
        for task_id, branch, expected in cases:
            with self.subTest(task_id=task_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                errors = self.check(
                    root,
                    {"apps/api/src/apbra_api/generation.py"},
                    task_id=task_id,
                    branch=branch,
                )
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_unrelated_sensitive_and_historical_governance_paths_fail(self):
        rejected = {
            "apps/api/src/apbra_api/oidc_adapter.py",
            "apps/api/src/apbra_api/bootstrap.py",
            "apps/web/knowledge/report-design-standards.md",
            "tests/bootstrap/test_bootstrap.py",
            "tests/bootstrap/test_durable_conversation_evidence_acceptance_scope.py",
            "output/candidate.zip",
            "artifacts/runtime-evidence.json",
            ".env",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in rejected:
                with self.subTest(path=path):
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        target.write_text("{}" if target.suffix == ".json" else "outside\n")
                    self.assertIn(
                        f"File outside active task scope: {path}", self.check(root, {path})
                    )

    def test_registration_files_and_source_append_are_exact(self):
        expected_ids = [
            source["id"]
            for source in json.loads((ROOT / "docs/source-register.json").read_text())["sources"]
        ]
        self.assertEqual(expected_ids[-1], "mvp1-protected-generation-output-history")
        historical = (ROOT / "tests/bootstrap/test_invited_private_case_foundation_scope.py").read_text()
        self.assertEqual(historical.count('"mvp1-protected-generation-output-history"'), 1)
        for path in c.PROTECTED_GENERATION_OUTPUT_HISTORY_REGISTRATION_PATHS:
            target = ROOT / path
            self.assertTrue(target.is_file())
            self.assertFalse(target.is_symlink())

    def test_new_authority_cannot_mask_invalid_historical_authority(self):
        historical_task_path = "tasks/APBRA-76-deployment-guide.json"
        protected_path = "apps/web/src/deploymentGuide.ts"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            historical_task = json.loads((root / historical_task_path).read_text())
            historical_task["owner_acceptance"] = "PENDING"
            (root / historical_task_path).write_text(json.dumps(historical_task))
            errors, _ = c.check(root)
            self.assertIn(
                f"File outside safe bootstrap scope: {protected_path}", errors
            )


if __name__ == "__main__":
    unittest.main()
