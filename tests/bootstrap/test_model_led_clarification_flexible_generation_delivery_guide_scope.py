"""Fail-closed APBRA-174 registration, source and literal-path tests."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_apbra_174", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
TASK_PATH = "tasks/APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json"


class ModelLedFlexibleDeliveryScopeTests(unittest.TestCase):
    def setUp(self):
        self.task = json.loads((ROOT / TASK_PATH).read_text())

    def copy_repository(self, root: Path) -> None:
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.MODEL_LED_FLEXIBLE_DELIVERY_PATHS)
        names.update(c.MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-174 synthetic fixture\n")

    def check(self, root: Path, paths, *, branch=None):
        return c.check(
            root,
            active_task_id="APBRA-174",
            active_branch=branch or self.task["branch"],
            changed_paths=set(paths),
        )[0]

    def test_exact_finite_future_authority_and_source_hash(self):
        paths = set(self.task["allowed_paths"])
        self.assertEqual(len(paths), 66)
        self.assertEqual(paths, c.MODEL_LED_FLEXIBLE_DELIVERY_PATHS)
        self.assertTrue(all("*" not in path for path in paths))
        self.assertTrue(paths.isdisjoint(c.MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS))
        self.assertEqual(self.task["source_ids"], [c.MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_ID])
        digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(digest(self.task), c.MODEL_LED_FLEXIBLE_DELIVERY_TASK_SHA256)
        sources = json.loads((ROOT / "docs/source-register.json").read_text())
        source = next(item for item in sources["sources"] if item["id"] == c.MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_ID)
        self.assertEqual(source["content_id"], "9404417")
        self.assertEqual(source["version"], 3)
        self.assertEqual(source["status"], "ACCEPTED")
        self.assertEqual(digest(source), c.MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_SHA256)
        self.assertEqual(self.task["base_commit"], "b2fba8d507262cf912e161b491549ab0d5680b0d")

    def test_registration_exactly_eight_and_separate_from_implementation(self):
        registration = c.MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS
        self.assertEqual(len(registration), 8)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, registration, branch=c.MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_BRANCH), [])
            for omitted in registration:
                with self.subTest(omitted=omitted):
                    errors = self.check(root, registration - {omitted}, branch=c.MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_BRANCH)
                    self.assertIn("APBRA-174 registration must change exactly its eight governance files", errors)
            errors = self.check(root, registration | {"apps/api/src/apbra_api/api.py"})
            self.assertIn("APBRA-174 registration and implementation changes must remain separate", errors)

    def test_restricted_paths_stay_restricted(self):
        rejected = (
            ".github/workflows/bootstrap.yml",
            ".github/workflows/apbra-174.yml",
            "apps/api/pyproject.toml",
            "apps/api/uv.lock",
            "apps/web/package.json",
            "apps/web/package-lock.json",
            "apps/web/knowledge/deployment-standards.md",
            "apps/api/alembic/env.py",
            "scripts/check_ci_policy.py",
        )
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

    def test_tampered_task_or_source_cannot_expand_authority(self):
        new_path = "apps/api/src/apbra_api/tenant_settings.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            task = copy.deepcopy(self.task)
            task["allowed_paths"].append(".github/workflows/bootstrap.yml")
            (root / TASK_PATH).write_text(json.dumps(task))
            errors = self.check(root, {new_path})
            self.assertIn("APBRA-174 contract differs from accepted authority", errors)
            self.assertIn(f"File outside safe bootstrap scope: {new_path}", errors)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            sources = json.loads((root / "docs/source-register.json").read_text())
            source = next(item for item in sources["sources"] if item["id"] == c.MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_ID)
            source["acceptance"] += " broadened"
            (root / "docs/source-register.json").write_text(json.dumps(sources))
            errors = self.check(root, {new_path})
            self.assertIn("APBRA-174 source differs from accepted provenance", errors)
            self.assertIn(f"File outside safe bootstrap scope: {new_path}", errors)

    def test_historical_task_contracts_unchanged(self):
        for path in (
            "tasks/APBRA-143-typed-confirmed-requirements.json",
            "tasks/APBRA-144-ai-native-iterative-clarification.json",
            "tasks/APBRA-171-business-user-report-creation-intelligent-generation.json",
        ):
            self.assertNotIn(path, c.MODEL_LED_FLEXIBLE_DELIVERY_PATHS)
            self.assertNotIn(path, c.MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS)


if __name__ == "__main__":
    unittest.main()
