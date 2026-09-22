"""Exact APBRA-148 registration, authority and fail-closed scope checks."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_post_capstone_product_reconciliation", ROOT / "scripts/check_bootstrap.py"
)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class PostCapstoneProductReconciliationScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-148-post-capstone-product-reconciliation.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.source_path = "docs/source-register.json"
        self.sources = json.loads((ROOT / self.source_path).read_text())

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.POST_CAPSTONE_PRODUCT_RECONCILIATION_PATHS)
        names.update(c.POST_CAPSTONE_PRODUCT_RECONCILIATION_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-148 fixture\n")

    def check(self, root: Path, changed_paths, *, task_id="APBRA-148", branch=None):
        return c.check(
            root,
            active_task_id=task_id,
            active_branch=self.task["branch"] if branch is None else branch,
            changed_paths=set(changed_paths),
        )[0]

    def test_task_is_known_with_exact_eleven_document_scope(self):
        expected = {
            "AGENTS.md",
            "docs/decisions/implementation-baseline.md",
            "README.md",
            "ARCHITECTURE.md",
            "REQUIREMENTS.md",
            "AI-RAG-SPEC.md",
            "POWERBI-GENERATION-SPEC.md",
            "MVP-ACCEPTANCE-CRITERIA.md",
            "apps/web/README.md",
            "docs/engineering/capstone-evidence.md",
            "docs/engineering/codex-handoff.md",
        }
        self.assertEqual(c.POST_CAPSTONE_PRODUCT_RECONCILIATION_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertEqual(len(expected), 11)
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        for path in expected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                self.assertEqual(self.check(root, {path}), [])

    def test_registration_scope_is_exact_disjoint_and_admitted_together(self):
        expected = {
            "scripts/check_bootstrap.py",
            "tasks/APBRA-148-post-capstone-product-reconciliation.json",
            "tests/bootstrap/test_post_capstone_product_reconciliation_scope.py",
            "docs/source-register.json",
        }
        self.assertEqual(c.POST_CAPSTONE_PRODUCT_RECONCILIATION_REGISTRATION_PATHS, expected)
        self.assertTrue(expected.isdisjoint(c.POST_CAPSTONE_PRODUCT_RECONCILIATION_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, expected), [])

    def test_registration_and_document_implementation_cannot_be_mixed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors = self.check(root, {"scripts/check_bootstrap.py", "README.md"})
            self.assertIn(
                "APBRA-148 registration and documentation implementation changes must remain separate",
                errors,
            )

    def test_wrong_contract_identity_branch_base_agent_card_acceptance_source_and_scope_fail(self):
        mutations = (
            ({"task_id": "APBRA-999"}, "Unexpected post-Capstone product reconciliation identity"),
            ({"assigned_agent": "APBRA-DOCS"}, "Unexpected post-Capstone product reconciliation identity"),
            ({"agent_card_version": "9.9"}, "Stale agent card version"),
            ({"branch": "agent/APBRA-DEVOPS/APBRA-148-wrong"}, "Unexpected post-Capstone product reconciliation branch"),
            ({"base_commit": "0" * 40}, "Stale post-Capstone product reconciliation base"),
            ({"owner_acceptance": "PENDING"}, "Post-Capstone product reconciliation requires issued implementation acceptance"),
            ({"source_ids": ["capstone-governance"]}, "Post-Capstone product reconciliation requires its specific accepted source"),
            ({"source_ids": ["implementation-contract"]}, "Proposed sources cannot authorize implementation"),
            ({"allowed_paths": ["docs/**"]}, "Unexpected post-Capstone product reconciliation scope"),
            ({"allowed_paths": self.task["allowed_paths"][:-1]}, "Unexpected post-Capstone product reconciliation scope"),
            ({"allowed_paths": self.task["allowed_paths"] + ["docs/unrelated.md"]}, "Unexpected post-Capstone product reconciliation scope"),
            ({"objective": None}, "None is not of type 'string'"),
        )
        for mutation, expected in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                changed = copy.deepcopy(self.task)
                changed.update(mutation)
                (root / self.task_path).write_text(json.dumps(changed))
                errors = self.check(root, {"README.md"})
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn("File outside active task scope: README.md", errors)

    def test_missing_unknown_malformed_active_task_and_branch_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            (root / self.task_path).unlink()
            errors = self.check(root, {"README.md"})
            self.assertIn("Unknown or invalid active task authority: APBRA-148", errors)
            self.assertIn("File outside active task scope: README.md", errors)

        cases = (
            (None, self.task["branch"], "Active task identity missing"),
            ("APBRA148", self.task["branch"], "Malformed active task identity"),
            ("APBRA-999", self.task["branch"], "Unknown or invalid active task authority"),
            ("APBRA-148", None, "Active task branch identity missing"),
            ("APBRA-148", "agent/APBRA-DEVOPS/APBRA-148-wrong", "Active branch conflicts with task authority"),
        )
        for task_id, branch, expected in cases:
            with self.subTest(task_id=task_id, branch=branch), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                errors = c.check(
                    root,
                    active_task_id=task_id,
                    active_branch=branch,
                    changed_paths={"README.md"},
                )[0]
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn("File outside active task scope: README.md", errors)

    def test_application_dependency_configuration_existing_contract_evidence_and_unrelated_paths_fail(self):
        rejected = (
            "apps/web/src/foundry.ts",
            "apps/web/package.json",
            "apps/web/package-lock.json",
            "apps/web/vite.config.ts",
            "apps/web/.env.local",
            ".env.local",
            "apps/api/src/handler.ts",
            "packages/domain/index.ts",
            "requirements-bootstrap.txt",
            ".github/workflows/bootstrap.yml",
            "output/candidate.zip",
            "artifacts/live-run.json",
            "manual-testing/candidate.zip",
            "SalesPerformance.candidate.zip",
            "tests/bootstrap/evaluation/evidence/run-final/result.json",
            "docs/engineering/unrelated.md",
            "tasks/APBRA-140-capstone-documentation.json",
            "tasks/APBRA-146-post-capstone-mvp-baseline-reconciliation.json",
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

    def test_new_source_is_exact_and_historical_sources_are_preserved(self):
        source_map = {source["id"]: source for source in self.sources["sources"]}
        current = source_map["post-capstone-product-reconciliation"]
        self.assertEqual(current["content_id"], "APBRA-148")
        self.assertEqual(current["status"], "ACCEPTED")
        self.assertIn("2026-09-22T19:52:41.261+1000", current["version"])
        self.assertIn("comment 10167", current["section"])
        for historical in (
            "engineering-structure",
            "implementation-contract",
            "task-contract",
            "capstone-governance",
            "capstone-evaluation",
        ):
            self.assertIn(historical, source_map)
        self.assertNotEqual(current["id"], "capstone-governance")

    def test_apbra_140_and_apbra_146_remain_independently_valid_and_unchanged(self):
        historical_140 = json.loads((ROOT / "tasks/APBRA-140-capstone-documentation.json").read_text())
        historical_146 = json.loads((ROOT / "tasks/APBRA-146-post-capstone-mvp-baseline-reconciliation.json").read_text())
        self.assertEqual(set(historical_140["allowed_paths"]), c.CAPSTONE_DOCUMENTATION_PATHS)
        self.assertEqual(set(historical_146["allowed_paths"]), c.CAPSTONE_DOCUMENTATION_PATHS)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(c.check(root, active_task_id="APBRA-140", active_branch=historical_140["branch"], changed_paths={"README.md"})[0], [])
            self.assertEqual(c.check(root, active_task_id="APBRA-146", active_branch=historical_146["branch"], changed_paths={"README.md"})[0], [])

    def test_secret_unsafe_path_and_symlink_protections_remain_active(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            target = root / "README.md"
            target.write_text("credential: ghp_" + "A" * 36 + "\n")
            self.assertIn("High-confidence credential pattern in: README.md", self.check(root, {"README.md"}))
            target.unlink()
            target.symlink_to(root / "ARCHITECTURE.md")
            self.assertIn("File outside safe bootstrap scope: README.md", self.check(root, {"README.md"}))
            self.assertIn("File outside active task scope: ../README.md", self.check(root, {"../README.md"}))

    def test_contract_preserves_product_authority_and_evidence_boundaries(self):
        criteria = " ".join(self.task["acceptance_criteria"])
        for required in (
            "ConfirmedRequirementContract",
            "subordinate typed ReportDesign",
            "Every applicable mandatory check",
            "8042cc44-620f-4457-828d-0770749a653f",
            "0927fd18-1c61-4610-8167-de86933a1de1",
            "embeddingCalls",
            "DAY, MONTH, QUARTER and YEAR",
            "unsupported WEEK",
            "APBRA-149 through APBRA-158",
            "APBRA-147 remains on planning hold",
            "Haseeb manually merges",
        ):
            with self.subTest(required=required):
                self.assertIn(required, criteria)
        self.assertIn("Application code, prompts, validators", " ".join(self.task["out_of_scope"]))


if __name__ == "__main__":
    unittest.main()
