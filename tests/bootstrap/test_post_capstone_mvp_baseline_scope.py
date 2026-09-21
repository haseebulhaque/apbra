"""Exact APBRA-146 authority and fail-closed governance checks."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_post_capstone_mvp_baseline", ROOT / "scripts/check_bootstrap.py"
)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class PostCapstoneMvpBaselineScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-146-post-capstone-mvp-baseline-reconciliation.json"
        self.task = json.loads((ROOT / self.task_path).read_text())

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.CAPSTONE_DOCUMENTATION_PATHS)
        names.update(c.POST_CAPSTONE_MVP_BASELINE_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-146 fixture\n")

    def check_path(self, root: Path, path: str, *, task_id="APBRA-146", branch=None):
        return c.check(
            root,
            active_task_id=task_id,
            active_branch=self.task["branch"] if branch is None else branch,
            changed_paths={path},
        )[0]

    def test_apbra_146_is_known_and_exact_nine_document_paths_are_authorized(self):
        expected = {
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
        self.assertEqual(c.CAPSTONE_DOCUMENTATION_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertEqual(len(expected), 9)
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        for path in expected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                self.assertEqual(self.check_path(root, path), [])

    def test_registration_scope_is_exact_and_disjoint_from_implementation(self):
        expected = {
            "scripts/check_bootstrap.py",
            "tasks/APBRA-146-post-capstone-mvp-baseline-reconciliation.json",
            "tests/bootstrap/test_post_capstone_mvp_baseline_scope.py",
        }
        self.assertEqual(c.POST_CAPSTONE_MVP_BASELINE_REGISTRATION_PATHS, expected)
        self.assertTrue(expected.isdisjoint(c.CAPSTONE_DOCUMENTATION_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors, _ = c.check(
                root,
                active_task_id="APBRA-146",
                active_branch=self.task["branch"],
                changed_paths=expected,
            )
            self.assertEqual(errors, [])

    def test_wrong_branch_base_identity_owner_scope_and_malformed_contract_fail_closed(self):
        mutations = (
            ({"branch": "agent/APBRA-DEVOPS/APBRA-146-wrong"}, "Unexpected post-Capstone MVP baseline branch"),
            ({"base_commit": "0" * 40}, "Stale post-Capstone MVP baseline base"),
            ({"task_id": "APBRA-999"}, "Unexpected post-Capstone MVP baseline identity"),
            ({"assigned_agent": "APBRA-DOCS"}, "Unexpected post-Capstone MVP baseline identity"),
            ({"owner_acceptance": "PENDING"}, "Post-Capstone MVP baseline requires issued implementation acceptance"),
            ({"allowed_paths": ["docs/**"]}, "Unexpected post-Capstone MVP baseline scope"),
            ({"allowed_paths": self.task["allowed_paths"] + ["docs/engineering/unrelated.md"]}, "Unexpected post-Capstone MVP baseline scope"),
            ({"allowed_paths": self.task["allowed_paths"][:-1]}, "Unexpected post-Capstone MVP baseline scope"),
            ({"source_ids": ["engineering-structure"]}, "Post-Capstone MVP baseline requires its specific accepted source"),
            ({"objective": None}, "None is not of type 'string'"),
        )
        for mutation, expected in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                changed = copy.deepcopy(self.task)
                changed.update(mutation)
                (root / self.task_path).write_text(json.dumps(changed))
                errors = self.check_path(root, "README.md")
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn("File outside active task scope: README.md", errors)

    def test_missing_contract_and_wrong_active_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            (root / self.task_path).unlink()
            errors = self.check_path(root, "README.md")
            self.assertIn("Unknown or invalid active task authority: APBRA-146", errors)
            self.assertIn("File outside active task scope: README.md", errors)

        cases = (
            (None, self.task["branch"], "Active task identity missing"),
            ("APBRA146", self.task["branch"], "Malformed active task identity"),
            ("APBRA-999", self.task["branch"], "Unknown or invalid active task authority"),
            ("APBRA-146", None, "Active task branch identity missing"),
        )
        for task_id, branch, expected in cases:
            with self.subTest(task_id=task_id, branch=branch), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                errors, _ = c.check(
                    root,
                    active_task_id=task_id,
                    active_branch=branch,
                    changed_paths={"README.md"},
                )
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn("File outside active task scope: README.md", errors)

    def test_application_output_evidence_env_candidate_and_unrelated_docs_are_rejected(self):
        rejected = (
            "apps/web/src/foundry.ts",
            "apps/web/src/reportDesignNormalization.ts",
            "apps/web/src/genericPowerBI.ts",
            "apps/web/package.json",
            "apps/web/package-lock.json",
            "apps/web/vite.config.ts",
            "apps/web/.env.local",
            ".env.local",
            "apps/api/src/handler.ts",
            "packages/domain/index.ts",
            "output/candidate.zip",
            "artifacts/live-run.json",
            "manual-testing/candidate.zip",
            "ServiceManagementFunnel.candidate.zip",
            "tests/bootstrap/evaluation/evidence/run-final/result.json",
            "docs/source-register.json",
            "docs/engineering/unrelated.md",
            "tasks/APBRA-145-generic-time-grain-support.json",
        )
        for path in rejected:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_text("{}" if target.suffix == ".json" else "outside APBRA-146 scope\n")
                self.assertIn(f"File outside active task scope: {path}", self.check_path(root, path))

    def test_apbra_140_remains_independently_active_and_unchanged(self):
        historical_path = "tasks/APBRA-140-capstone-documentation.json"
        historical = json.loads((ROOT / historical_path).read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(
                c.check(
                    root,
                    active_task_id="APBRA-140",
                    active_branch=historical["branch"],
                    changed_paths={"README.md"},
                )[0],
                [],
            )
        self.assertEqual(
            set(historical["allowed_paths"]), c.CAPSTONE_DOCUMENTATION_PATHS
        )

    def test_secret_and_symlink_protections_remain_active(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            target = root / "README.md"
            target.write_text("credential: ghp_" + "A" * 36 + "\n")
            self.assertIn(
                "High-confidence credential pattern in: README.md",
                self.check_path(root, "README.md"),
            )
            target.unlink()
            target.symlink_to(root / "ARCHITECTURE.md")
            self.assertIn(
                "File outside safe bootstrap scope: README.md",
                self.check_path(root, "README.md"),
            )

    def test_contract_keeps_reconciliation_bounded_and_evidence_truthful(self):
        criteria = " ".join(self.task["acceptance_criteria"])
        for required in (
            "APBRA-141 through APBRA-145",
            "ConfirmedRequirementContract",
            "DAY, MONTH, QUARTER and YEAR",
            "WEEK",
            "Candidate Ready, Human Review Required, Unsupported and Blocked",
            "working bounded MVP/prototype",
            "not production-ready",
            "d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa",
            "no missing run ID, candidate digest, token count, cost or Desktop result is invented",
        ):
            with self.subTest(required=required):
                self.assertIn(required, criteria)
        exclusions = " ".join(self.task["out_of_scope"])
        self.assertIn("Application source, prompts, validators", exclusions)
        self.assertIn("Generated candidates", exclusions)
        self.assertIn("next MVP feature", exclusions)


if __name__ == "__main__":
    unittest.main()
