"""Exact APBRA-171 registration, provenance and active-authority regression tests."""

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
    "bootstrap_apbra_171", ROOT / "scripts/check_bootstrap.py"
)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class BusinessUserIntelligentGenerationScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-171-business-user-report-creation-intelligent-generation.json"
        self.task = json.loads((ROOT / self.task_path).read_text())

    def copy_repository(self, root: Path) -> None:
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.BUSINESS_USER_INTELLIGENT_GENERATION_PATHS)
        names.update(c.BUSINESS_USER_INTELLIGENT_GENERATION_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-171 fixture\n")

    def check(self, root: Path, changed_paths, *, task_id="APBRA-171", branch=None):
        return c.check(
            root,
            active_task_id=task_id,
            active_branch=self.task["branch"] if branch is None else branch,
            changed_paths=set(changed_paths),
        )[0]

    def test_finite_implementation_authority_and_exact_hash(self):
        expected = set(self.task["allowed_paths"])
        self.assertEqual(expected, c.BUSINESS_USER_INTELLIGENT_GENERATION_PATHS)
        self.assertEqual(len(expected), 52)
        self.assertTrue(all("*" not in path for path in expected))
        self.assertIn("apps/api/src/apbra_api/model_provider.py", expected)
        self.assertIn("apps/api/src/apbra_api/reference_material.py", expected)
        self.assertIn("apps/web/src/genericPowerBI.ts", expected)
        self.assertIn("apps/web/scripts/generation-bridge.ts", expected)
        self.assertNotIn("apps/api/pyproject.toml", expected)
        self.assertNotIn("apps/web/package.json", expected)
        self.assertNotIn("apps/web/src/App.tsx", expected)
        canonical = json.dumps(self.task, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            c.BUSINESS_USER_INTELLIGENT_GENERATION_TASK_SHA256,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in sorted(expected):
                with self.subTest(path=path):
                    self.assertEqual(self.check(root, {path}), [])

    def test_registration_is_exact_five_paths_and_separate(self):
        expected = {
            "scripts/check_bootstrap.py",
            self.task_path,
            "tests/bootstrap/test_business_user_report_creation_intelligent_generation_scope.py",
            "tests/bootstrap/test_invited_private_case_foundation_scope.py",
            "docs/source-register.json",
        }
        self.assertEqual(expected, c.BUSINESS_USER_INTELLIGENT_GENERATION_REGISTRATION_PATHS)
        self.assertTrue(expected.isdisjoint(c.BUSINESS_USER_INTELLIGENT_GENERATION_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, expected), [])
            for omitted in sorted(expected):
                with self.subTest(omitted=omitted):
                    errors = self.check(root, expected - {omitted})
                    self.assertIn(
                        "APBRA-171 registration must change exactly its five governance files",
                        errors,
                    )
            errors = self.check(root, expected | {"apps/api/src/apbra_api/model_provider.py"})
            self.assertIn("APBRA-171 registration and implementation changes must remain separate", errors)

    def test_hash_source_and_identity_mutations_fail_closed(self):
        new_file = "apps/api/src/apbra_api/model_provider.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            task = copy.deepcopy(self.task)
            task["allowed_paths"].append("apps/api/pyproject.toml")
            (root / self.task_path).write_text(json.dumps(task))
            errors = self.check(root, {new_file})
            self.assertIn("Business-user intelligent-generation contract differs from accepted authority", errors)
            self.assertIn(f"File outside safe bootstrap scope: {new_file}", errors)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            sources = json.loads((root / "docs/source-register.json").read_text())
            source = next(
                item for item in sources["sources"]
                if item["id"] == c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID
            )
            source["acceptance"] += " silently broadened"
            (root / "docs/source-register.json").write_text(json.dumps(sources))
            errors = self.check(root, {new_file})
            self.assertIn("Business-user intelligent-generation source differs from accepted provenance", errors)
            self.assertIn(f"File outside safe bootstrap scope: {new_file}", errors)
        for mutation, expected in (
            ({"task_id": "APBRA-999"}, "Unexpected business-user intelligent-generation identity"),
            ({"branch": "agent/APBRA-DEVOPS/APBRA-171-wrong"}, "Unexpected business-user intelligent-generation branch"),
            ({"base_commit": "0" * 40}, "Stale business-user intelligent-generation base"),
            ({"owner_acceptance": "PENDING"}, "Business-user intelligent generation requires issued implementation acceptance"),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                task = copy.deepcopy(self.task)
                task.update(mutation)
                (root / self.task_path).write_text(json.dumps(task))
                self.assertIn(expected, self.check(root, {new_file}))

    def test_historical_tree_safety_is_not_historical_change_authority(self):
        new_file = "apps/api/src/apbra_api/model_provider.py"
        older = json.loads(
            (ROOT / "tasks/APBRA-170-professional-saas-experience-visual-system.json").read_text()
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, {"apps/web/src/style.css"}, task_id="APBRA-170", branch=older["branch"]), [])
            errors = self.check(root, {new_file}, task_id="APBRA-170", branch=older["branch"])
            self.assertIn(f"File outside active task scope: {new_file}", errors)
            self.assertNotIn(f"File outside safe bootstrap scope: {new_file}", errors)
            task = copy.deepcopy(older)
            task["objective"] += " modified"
            prior_path = root / "tasks/APBRA-170-professional-saas-experience-visual-system.json"
            prior_path.write_text(json.dumps(task))
            errors = self.check(root, {new_file})
            self.assertIn("Professional SaaS experience visual-system contract differs from accepted authority", errors)

    def test_unknown_files_wrong_branch_and_unregistered_task_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            unknown = "apps/api/src/apbra_api/unregistered_provider.py"
            (root / unknown).write_text("not registered\n")
            errors = self.check(root, {unknown})
            self.assertIn(f"File outside active task scope: {unknown}", errors)
            self.assertIn(f"File outside safe bootstrap scope: {unknown}", errors)
            errors = self.check(
                root, {"apps/api/src/apbra_api/model_provider.py"},
                branch="agent/APBRA-DEVOPS/APBRA-171-unauthorised",
            )
            self.assertIn("Active branch conflicts with task authority: agent/APBRA-DEVOPS/APBRA-171-unauthorised", errors)
            (root / self.task_path).unlink()
            errors = self.check(root, {"apps/api/src/apbra_api/model_provider.py"})
            self.assertIn("Unknown or invalid active task authority: APBRA-171", errors)

    def test_architecture_and_historical_source_order_are_explicit(self):
        words = " ".join(
            self.task["requirements"] + self.task["adrs"]
            + self.task["acceptance_criteria"] + self.task["out_of_scope"]
        )
        for required in (
            "ordinary", "provider-neutral", "reviewed_design_id", "canonical",
            "reference material", "difference", "expert", "no automatic fallback",
            "untrusted", "immutable", "server-side",
        ):
            with self.subTest(required=required):
                self.assertIn(required.lower(), words.lower())
        sources = json.loads((ROOT / "docs/source-register.json").read_text())
        ids = [source["id"] for source in sources["sources"]]
        self.assertEqual(ids.count(c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID), 1)
        self.assertEqual(
            ids.index(c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID) + 1,
            ids.index(c.PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_SOURCE_ID),
        )
        source = next(
            item for item in sources["sources"]
            if item["id"] == c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID
        )
        canonical = json.dumps(source, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_SHA256,
        )
        historical = (ROOT / "tests/bootstrap/test_invited_private_case_foundation_scope.py").read_text()
        self.assertEqual(historical.count('"mvp1-business-user-report-creation-intelligent-generation"'), 1)


if __name__ == "__main__":
    unittest.main()
