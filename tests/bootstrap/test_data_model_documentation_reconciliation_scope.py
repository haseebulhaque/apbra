"""Exact APBRA-159 registration, authority and fail-closed scope checks."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_data_model_documentation_reconciliation", ROOT / "scripts/check_bootstrap.py"
)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class DataModelDocumentationReconciliationScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-159-data-model-documentation-reconciliation.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.source_path = "docs/source-register.json"
        self.sources = json.loads((ROOT / self.source_path).read_text())

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.DATA_MODEL_DOCUMENTATION_RECONCILIATION_PATHS)
        names.update(c.DATA_MODEL_DOCUMENTATION_RECONCILIATION_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-159 fixture\n")

    def check(self, root: Path, changed_paths, *, task_id="APBRA-159", branch=None):
        return c.check(
            root,
            active_task_id=task_id,
            active_branch=self.task["branch"] if branch is None else branch,
            changed_paths=set(changed_paths),
        )[0]

    def test_task_is_known_with_exact_two_document_scope(self):
        expected = {"DATA-MODEL.md", "docs/engineering/codex-handoff.md"}
        self.assertEqual(c.DATA_MODEL_DOCUMENTATION_RECONCILIATION_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        for path in expected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                self.assertEqual(self.check(root, {path}), [])

    def test_registration_scope_is_exact_disjoint_and_admitted_together(self):
        expected = {
            "scripts/check_bootstrap.py",
            "tasks/APBRA-159-data-model-documentation-reconciliation.json",
            "tests/bootstrap/test_data_model_documentation_reconciliation_scope.py",
            "docs/source-register.json",
        }
        self.assertEqual(c.DATA_MODEL_DOCUMENTATION_RECONCILIATION_REGISTRATION_PATHS, expected)
        self.assertTrue(expected.isdisjoint(c.DATA_MODEL_DOCUMENTATION_RECONCILIATION_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, expected), [])

    def test_registration_and_documentation_changes_cannot_be_mixed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors = self.check(root, {"scripts/check_bootstrap.py", "DATA-MODEL.md"})
            self.assertIn(
                "APBRA-159 registration and documentation implementation changes must remain separate",
                errors,
            )

    def test_wrong_identity_branch_base_role_source_acceptance_and_scope_fail(self):
        mutations = (
            ({"task_id": "APBRA-999"}, "Unexpected data-model documentation reconciliation identity"),
            ({"assigned_agent": "APBRA-DOCS"}, "Unexpected data-model documentation reconciliation identity"),
            ({"agent_card_version": "9.9"}, "Stale agent card version"),
            ({"branch": "agent/APBRA-DEVOPS/APBRA-159-wrong"}, "Unexpected data-model documentation reconciliation branch"),
            ({"base_commit": "0" * 40}, "Stale data-model documentation reconciliation base"),
            ({"owner_acceptance": "PENDING"}, "Data-model documentation reconciliation requires issued implementation acceptance"),
            ({"source_ids": ["post-capstone-product-reconciliation"]}, "Data-model documentation reconciliation requires its specific accepted source"),
            ({"source_ids": ["implementation-contract"]}, "Proposed sources cannot authorize implementation"),
            ({"allowed_paths": ["docs/**"]}, "Unexpected data-model documentation reconciliation scope"),
            ({"allowed_paths": self.task["allowed_paths"][:-1]}, "Unexpected data-model documentation reconciliation scope"),
            ({"allowed_paths": self.task["allowed_paths"] + ["README.md"]}, "Unexpected data-model documentation reconciliation scope"),
            ({"objective": None}, "None is not of type 'string'"),
        )
        for mutation, expected in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                changed = copy.deepcopy(self.task)
                changed.update(mutation)
                (root / self.task_path).write_text(json.dumps(changed))
                errors = self.check(root, {"DATA-MODEL.md"})
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn("File outside active task scope: DATA-MODEL.md", errors)

    def test_missing_malformed_unknown_active_task_and_branch_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            (root / self.task_path).unlink()
            errors = self.check(root, {"DATA-MODEL.md"})
            self.assertIn("Unknown or invalid active task authority: APBRA-159", errors)
            self.assertIn("File outside active task scope: DATA-MODEL.md", errors)

        cases = (
            (None, self.task["branch"], "Active task identity missing"),
            ("APBRA159", self.task["branch"], "Malformed active task identity"),
            ("APBRA-999", self.task["branch"], "Unknown or invalid active task authority"),
            ("APBRA-159", None, "Active task branch identity missing"),
            ("APBRA-159", "agent/APBRA-DEVOPS/APBRA-159-wrong", "Active branch conflicts with task authority"),
        )
        for task_id, branch, expected in cases:
            with self.subTest(task_id=task_id, branch=branch), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                errors = c.check(root, active_task_id=task_id, active_branch=branch, changed_paths={"DATA-MODEL.md"})[0]
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn("File outside active task scope: DATA-MODEL.md", errors)

    def test_extra_wildcard_application_output_env_candidate_and_unrelated_paths_fail(self):
        rejected = (
            "README.md",
            "docs/decisions/implementation-baseline.md",
            "apps/web/src/foundry.ts",
            "apps/web/package.json",
            "apps/web/.env.local",
            ".env.local",
            "packages/domain/index.ts",
            "requirements-bootstrap.txt",
            ".github/workflows/bootstrap.yml",
            "output/candidate.zip",
            "artifacts/runtime-evidence.json",
            "manual-testing/candidate.zip",
            "SalesPerformance.candidate.zip",
            "tasks/APBRA-148-post-capstone-product-reconciliation.json",
            "tests/bootstrap/test_post_capstone_product_reconciliation_scope.py",
        )
        for path in rejected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_text("{}" if target.suffix == ".json" else "outside scope\n")
                self.assertIn(f"File outside active task scope: {path}", self.check(root, {path}))

    def test_source_is_exact_and_historical_sources_are_preserved(self):
        source_map = {source["id"]: source for source in self.sources["sources"]}
        current = source_map["post-capstone-data-model-reconciliation"]
        self.assertEqual(current["content_id"], "APBRA-159")
        self.assertEqual(current["status"], "ACCEPTED")
        self.assertIn("comment 10176", current["version"])
        self.assertIn("Data Models v4", current["version"])
        for historical in (
            "engineering-structure",
            "implementation-contract",
            "task-contract",
            "capstone-governance",
            "post-capstone-product-reconciliation",
        ):
            self.assertIn(historical, source_map)
        self.assertNotEqual(current["id"], "post-capstone-product-reconciliation")

    def test_apbra_140_146_and_148_remain_independently_valid_and_unchanged(self):
        historical = {
            "APBRA-140": json.loads((ROOT / "tasks/APBRA-140-capstone-documentation.json").read_text()),
            "APBRA-146": json.loads((ROOT / "tasks/APBRA-146-post-capstone-mvp-baseline-reconciliation.json").read_text()),
            "APBRA-148": json.loads((ROOT / "tasks/APBRA-148-post-capstone-product-reconciliation.json").read_text()),
        }
        self.assertEqual(set(historical["APBRA-140"]["allowed_paths"]), c.CAPSTONE_DOCUMENTATION_PATHS)
        self.assertEqual(set(historical["APBRA-146"]["allowed_paths"]), c.CAPSTONE_DOCUMENTATION_PATHS)
        self.assertEqual(set(historical["APBRA-148"]["allowed_paths"]), c.POST_CAPSTONE_PRODUCT_RECONCILIATION_PATHS)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for task_id, path in (("APBRA-140", "README.md"), ("APBRA-146", "README.md"), ("APBRA-148", "AGENTS.md")):
                with self.subTest(task_id=task_id):
                    self.assertEqual(c.check(root, active_task_id=task_id, active_branch=historical[task_id]["branch"], changed_paths={path})[0], [])

    def test_secret_unsafe_path_and_symlink_protections_remain_active(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            target = root / "DATA-MODEL.md"
            target.write_text("credential: ghp_" + "A" * 36 + "\n")
            self.assertIn("High-confidence credential pattern in: DATA-MODEL.md", self.check(root, {"DATA-MODEL.md"}))
            target.unlink()
            target.symlink_to(root / "README.md")
            self.assertIn("File outside safe bootstrap scope: DATA-MODEL.md", self.check(root, {"DATA-MODEL.md"}))
            self.assertIn("File outside active task scope: ../DATA-MODEL.md", self.check(root, {"../DATA-MODEL.md"}))

    def test_contract_preserves_authority_lineage_genericity_and_runtime_boundaries(self):
        criteria = " ".join(self.task["acceptance_criteria"])
        for required in (
            "ConfirmedRequirementContract",
            "AI-produced ReportDesign is subordinate",
            "original submissions",
            "optional-project",
            "expert assignment and actual continuation",
            "requirement, design, attempt, candidate, validation, review, release and deployment lineage",
            "aggregate budget boundaries",
            "Changed candidate bytes",
            "runtime evidence",
            "domain-independent",
            "PR #44",
            "Compatible DATA requirement identifiers",
            "APBRA-148 remains In Progress",
            "APBRA-147 remains on planning hold",
        ):
            with self.subTest(required=required):
                self.assertIn(required, criteria)
        exclusions = " ".join(self.task["out_of_scope"])
        self.assertIn("database tables", exclusions)
        self.assertIn("scenario templates", exclusions)
        self.assertIn("automatic merge", exclusions)


if __name__ == "__main__":
    unittest.main()
