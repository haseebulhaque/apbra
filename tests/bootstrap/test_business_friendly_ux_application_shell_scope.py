"""Exact APBRA-169 registration, authority and fail-closed scope checks."""

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
    "bootstrap_apbra_169", ROOT / "scripts/check_bootstrap.py"
)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class BusinessFriendlyUxApplicationShellScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-169-business-friendly-ux-application-shell.json"
        self.task = json.loads((ROOT / self.task_path).read_text())

    def copy_repository(self, root: Path) -> None:
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_PATHS)
        names.update(c.BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-169 fixture\n")

    def check(self, root: Path, changed_paths, *, task_id="APBRA-169", branch=None):
        return c.check(
            root,
            active_task_id=task_id,
            active_branch=self.task["branch"] if branch is None else branch,
            changed_paths=set(changed_paths),
        )[0]

    def test_exact_finite_reviewed_design_and_presentation_scope_is_registered(self):
        expected = set(self.task["allowed_paths"])
        self.assertEqual(c.BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_PATHS, expected)
        self.assertEqual(len(expected), 20)
        self.assertTrue(all("*" not in path for path in expected))
        self.assertEqual(
            expected - {
                "apps/api/alembic/versions/20260929_04_reviewed_report_design.py",
                "apps/api/src/apbra_api/api.py",
                "apps/api/src/apbra_api/domain.py",
                "apps/api/src/apbra_api/generation.py",
                "apps/api/src/apbra_api/persistence.py",
                "apps/api/tests/test_generation.py",
                "apps/api/tests/test_migrations.py",
                "apps/web/src/api.ts",
                "apps/web/src/api.test.ts",
            },
            {
                "apps/web/e2e/durable-conversation.spec.ts",
                "apps/web/e2e/private-case.spec.ts",
                "apps/web/e2e/protected-generation.spec.ts",
                "apps/web/src/EnterpriseApp.tsx",
                "apps/web/src/durableConversation.test.tsx",
                "apps/web/src/durableConversation.tsx",
                "apps/web/src/durableGeneration.test.tsx",
                "apps/web/src/durableGeneration.tsx",
                "apps/web/src/privateCases.test.tsx",
                "apps/web/src/privateCases.tsx",
                "apps/web/src/style.css",
            },
        )
        canonical = json.dumps(self.task, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            c.BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_TASK_SHA256,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in sorted(expected):
                with self.subTest(path=path):
                    self.assertEqual(self.check(root, {path}), [])

    def test_registration_scope_is_exact_disjoint_and_admitted_together(self):
        expected = {
            "scripts/check_bootstrap.py",
            "tasks/APBRA-169-business-friendly-ux-application-shell.json",
            "tests/bootstrap/test_business_friendly_ux_application_shell_scope.py",
            "tests/bootstrap/test_invited_private_case_foundation_scope.py",
            "docs/source-register.json",
        }
        self.assertEqual(c.BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_REGISTRATION_PATHS, expected)
        self.assertTrue(expected.isdisjoint(c.BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(
                self.check(root, expected, branch=c.BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_AMENDMENT_BRANCH),
                [],
            )
            for omitted in sorted(expected):
                with self.subTest(omitted=omitted):
                    errors = self.check(
                        root, expected - {omitted},
                        branch=c.BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_AMENDMENT_BRANCH,
                    )
                    self.assertIn("APBRA-169 registration must change exactly its five governance files", errors)
                    self.assertIn("Active branch conflicts with task authority: " + c.BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_AMENDMENT_BRANCH, errors)

    def test_registration_and_implementation_changes_cannot_be_mixed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors = self.check(root, {
                "scripts/check_bootstrap.py", "apps/web/src/durableGeneration.tsx",
            })
            self.assertIn(
                "APBRA-169 registration and implementation changes must remain separate",
                errors,
            )

    def test_task_and_source_are_hash_bound_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            changed = copy.deepcopy(self.task)
            changed["objective"] += " broadened"
            (root / self.task_path).write_text(json.dumps(changed))
            self.assertIn(
                "Business-friendly UX application shell contract differs from accepted authority",
                self.check(root, {"apps/web/src/privateCases.tsx"}),
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            sources = json.loads((root / "docs/source-register.json").read_text())
            source = next(
                item for item in sources["sources"]
                if item["id"] == "mvp1-business-friendly-ux-application-shell"
            )
            source["acceptance"] += " broadened"
            (root / "docs/source-register.json").write_text(json.dumps(sources))
            self.assertIn(
                "Business-friendly UX application shell source differs from accepted provenance",
                self.check(root, {"apps/web/src/privateCases.tsx"}),
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            sources = json.loads((root / "docs/source-register.json").read_text())
            source = next(
                item for item in sources["sources"]
                if item["id"] == c.BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_AMENDMENT_SOURCE_ID
            )
            source["acceptance"] += " unaccepted reviewer"
            (root / "docs/source-register.json").write_text(json.dumps(sources))
            self.assertIn(
                "Business-friendly UX reviewed-design amendment source differs from accepted provenance",
                self.check(root, {"apps/api/src/apbra_api/generation.py"}),
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            changed = copy.deepcopy(self.task)
            changed["allowed_paths"].append("apps/api/src/apbra_api/auth.py")
            (root / self.task_path).write_text(json.dumps(changed))
            (root / "apps/api/src/apbra_api/auth.py").write_text("unregistered fixture\n")
            errors = self.check(root, {"apps/api/src/apbra_api/generation.py"})
            self.assertIn(
                "Business-friendly UX application shell contract differs from accepted authority",
                errors,
            )
            self.assertIn("File outside safe bootstrap scope: apps/api/src/apbra_api/auth.py", errors)

    def test_review_authority_and_canonical_boundary_are_explicit(self):
        text = " ".join(
            self.task["requirements"]
            + self.task["adrs"]
            + self.task["acceptance_criteria"]
        )
        self.assertIn("same-company EXPERT", text)
        self.assertIn("COMPANY_ADMIN, MEMBER", text)
        self.assertIn("reviewed_design_id", text)
        self.assertIn("digest", text)
        self.assertIn("retry", text.lower())
        self.assertIn("canonical TypeScript bridge/compiler", text)
        self.assertNotIn(
            "apps/web/scripts/generation-bridge.ts",
            self.task["allowed_paths"],
        )

    def test_active_task_is_exact_and_historical_tasks_remain_isolated(self):
        rejected = {
            "apps/api/src/apbra_api/auth.py",
            "apps/api/tests/test_api.py",
            "apps/web/scripts/generation-bridge.ts",
            "apps/web/package.json",
            "apps/web/knowledge/report-design-standards.md",
            "tests/bootstrap/test_bootstrap.py",
            "output/candidate.zip",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in rejected:
                with self.subTest(path=path):
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        target.write_text("outside scope\n")
                    self.assertIn(f"File outside active task scope: {path}", self.check(root, {path}))
            prior = json.loads(
                (ROOT / "tasks/APBRA-163-durable-conversation-evidence-acceptance.json").read_text()
            )
            later_path = "apps/web/src/durableGeneration.tsx"
            errors = self.check(root, {later_path}, task_id="APBRA-163", branch=prior["branch"])
            self.assertIn(f"File outside active task scope: {later_path}", errors)
            self.assertNotIn(f"File outside safe bootstrap scope: {later_path}", errors)
            migration = "apps/api/alembic/versions/20260929_04_reviewed_report_design.py"
            errors = self.check(root, {migration}, task_id="APBRA-163", branch=prior["branch"])
            self.assertIn(f"File outside active task scope: {migration}", errors)
            self.assertNotIn(f"File outside safe bootstrap scope: {migration}", errors)

    def test_source_history_append_and_registration_files_are_exact(self):
        ids = [source["id"] for source in json.loads(
            (ROOT / "docs/source-register.json").read_text()
        )["sources"]]
        self.assertEqual(
            ids[:-1][-4:-2],
            [
                "mvp1-business-friendly-ux-application-shell",
                "mvp1-business-friendly-ux-reviewed-design-amendment",
            ],
        )
        historical = (ROOT / "tests/bootstrap/test_invited_private_case_foundation_scope.py").read_text()
        self.assertEqual(historical.count('"mvp1-business-friendly-ux-application-shell"'), 1)
        self.assertEqual(historical.count('"mvp1-business-friendly-ux-reviewed-design-amendment"'), 1)
        for path in c.BUSINESS_FRIENDLY_UX_APPLICATION_SHELL_REGISTRATION_PATHS:
            target = ROOT / path
            self.assertTrue(target.is_file())
            self.assertFalse(target.is_symlink())


if __name__ == "__main__":
    unittest.main()
