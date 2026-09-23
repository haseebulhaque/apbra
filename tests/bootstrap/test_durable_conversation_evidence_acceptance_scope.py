"""Exact APBRA-163 registration, authority and fail-closed scope checks."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_apbra_163", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class DurableConversationEvidenceAcceptanceScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-163-durable-conversation-evidence-acceptance.json"
        self.task = json.loads((ROOT / self.task_path).read_text())

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_PATHS)
        names.update(c.DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-163 fixture\n")

    def check(self, root: Path, changed_paths, *, task_id="APBRA-163", branch=None):
        return c.check(
            root,
            active_task_id=task_id,
            active_branch=self.task["branch"] if branch is None else branch,
            changed_paths=set(changed_paths),
        )[0]

    def test_exact_finite_implementation_scope_is_registered(self):
        expected = set(self.task["allowed_paths"])
        self.assertEqual(c.DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_PATHS, expected)
        self.assertEqual(len(expected), 53)
        self.assertTrue(all("*" not in path for path in expected))
        canonical = json.dumps(self.task, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), c.DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_TASK_SHA256)
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
            "tests/bootstrap/test_durable_conversation_evidence_acceptance_scope.py",
            "tests/bootstrap/test_invited_private_case_foundation_scope.py",
            "docs/source-register.json",
        }
        self.assertEqual(c.DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_REGISTRATION_PATHS, expected)
        self.assertTrue(expected.isdisjoint(c.DURABLE_CONVERSATION_EVIDENCE_ACCEPTANCE_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, expected), [])
            for omitted in expected:
                errors = self.check(root, expected - {omitted})
                self.assertIn("APBRA-163 registration must change exactly its five governance files", errors)

    def test_mixed_registration_and_implementation_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors = self.check(root, {"scripts/check_bootstrap.py", "apps/api/src/apbra_api/evidence.py"})
            self.assertIn("APBRA-163 registration and implementation changes must remain separate", errors)

    def test_wrong_identity_branch_base_source_and_broadened_scope_fail(self):
        mutations = (
            ({"task_id": "APBRA-999"}, "Unexpected durable conversation evidence acceptance identity"),
            ({"assigned_agent": "APBRA-DEV-BE"}, "Unexpected durable conversation evidence acceptance identity"),
            ({"agent_card_version": "9.9"}, "Stale durable conversation evidence acceptance agent card version"),
            ({"branch": "agent/APBRA-DEVOPS/APBRA-163-wrong"}, "Unexpected durable conversation evidence acceptance branch"),
            ({"base_commit": "0" * 40}, "Stale durable conversation evidence acceptance base"),
            ({"owner_acceptance": "PENDING"}, "Durable conversation evidence acceptance requires issued implementation acceptance"),
            ({"source_ids": ["mvp1-invited-private-case-foundation"]}, "Durable conversation evidence acceptance requires its specific accepted source"),
            ({"allowed_paths": ["apps/**"]}, "Unexpected durable conversation evidence acceptance scope"),
            ({"allowed_paths": self.task["allowed_paths"] + ["apps/api/extra.py"]}, "Unexpected durable conversation evidence acceptance scope"),
        )
        for mutation, expected in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                changed = copy.deepcopy(self.task)
                changed.update(mutation)
                (root / self.task_path).write_text(json.dumps(changed))
                errors = self.check(root, {"apps/api/src/apbra_api/evidence.py"})
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_material_contract_or_source_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            changed = copy.deepcopy(self.task)
            changed["objective"] += " broadened"
            (root / self.task_path).write_text(json.dumps(changed))
            self.assertIn(
                "Durable conversation evidence acceptance contract differs from accepted authority",
                self.check(root, {"apps/api/src/apbra_api/evidence.py"}),
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            sources = json.loads((root / "docs/source-register.json").read_text())
            next(item for item in sources["sources"] if item["id"] == "mvp1-durable-conversation-evidence-acceptance")["acceptance"] += " broadened"
            (root / "docs/source-register.json").write_text(json.dumps(sources))
            self.assertIn(
                "Durable conversation evidence acceptance source differs from accepted provenance",
                self.check(root, {"apps/api/src/apbra_api/evidence.py"}),
            )

    def test_missing_malformed_unknown_task_and_branch_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            (root / self.task_path).unlink()
            self.assertIn("Unknown or invalid active task authority: APBRA-163", self.check(root, {"apps/api/src/apbra_api/evidence.py"}))
        cases = (
            (None, self.task["branch"], "Active task identity missing"),
            ("APBRA163", self.task["branch"], "Malformed active task identity"),
            ("APBRA-999", self.task["branch"], "Unknown or invalid active task authority"),
            ("APBRA-163", "agent/APBRA-DEVOPS/APBRA-163-wrong", "Active branch conflicts with task authority"),
        )
        for task_id, branch, expected in cases:
            with self.subTest(task_id=task_id, branch=branch), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                self.assertTrue(any(expected in error for error in self.check(root, {"apps/api/src/apbra_api/evidence.py"}, task_id=task_id, branch=branch)))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors = c.check(root, active_task_id="APBRA-163", active_branch=None, changed_paths={"apps/api/src/apbra_api/evidence.py"})[0]
            self.assertIn("Active task branch identity missing for changed paths", errors)

    def test_application_boundaries_and_historical_authority_remain_narrow(self):
        denied = {
            "apps/api/src/apbra_api/oidc_adapter.py",
            "apps/api/src/apbra_api/auth_boundary.py",
            "apps/web/src/genericPowerBI.ts",
            "apps/web/src/powerbi.ts",
            "apps/web/src/rag.ts",
            "tests/bootstrap/test_bootstrap.py",
            "output/candidate.zip",
            ".env",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in denied:
                with self.subTest(path=path):
                    self.assertIn(f"File outside active task scope: {path}", self.check(root, {path}))
            self.assertEqual(
                self.check(
                    root,
                    {"apps/api/src/apbra_api/api.py"},
                    task_id="APBRA-162",
                    branch="agent/APBRA-DEVOPS/APBRA-162-invited-private-case-foundation",
                ),
                [],
            )

    def test_secret_and_symlink_protections_remain_active(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            target = root / "apps/api/src/apbra_api/evidence.py"
            target.write_text("token = 'ghp_" + "A" * 40 + "'\n")
            self.assertIn(
                "High-confidence credential pattern in: apps/api/src/apbra_api/evidence.py",
                self.check(root, {"apps/api/src/apbra_api/evidence.py"}),
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            target = root / "apps/api/src/apbra_api/evidence.py"
            target.unlink()
            target.symlink_to(root / "outside.py")
            self.assertTrue(self.check(root, {"apps/api/src/apbra_api/evidence.py"}))


if __name__ == "__main__":
    unittest.main()
