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
ORIGINAL_PATHS_SHA256 = "cc6dcc37c7da59220e042c772f257670866b63a848b0f3089e1f1f63f8fc203f"
ORIGINAL_REQUIREMENTS_SHA256 = "acb9536cce2cb94a9df3318e39fc07d285c0662001a2905cd140b2951b9238e3"
ORIGINAL_ADRS_SHA256 = "ff1d75011a16790173ec47b41f89318733f8fb0e9e0bf493ba51ced5b2f2acdb"
ORIGINAL_ACCEPTANCE_SHA256 = "96b4599a41d9a36ca1dc35e3cb12b4f5119b6dc39a6be4b267587eaf4ee9950d"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ModelLedFlexibleDeliveryScopeTests(unittest.TestCase):
    def setUp(self):
        self.task = json.loads((ROOT / TASK_PATH).read_text())

    def copy_repository(self, root: Path) -> None:
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.MODEL_LED_FLEXIBLE_DELIVERY_PATHS)
        names.update(c.MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS)
        names.update(c.MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_PATHS)
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
        self.assertEqual(len(paths), 67)
        self.assertEqual(paths, c.MODEL_LED_FLEXIBLE_DELIVERY_PATHS)
        self.assertTrue(all("*" not in path for path in paths))
        self.assertTrue(paths.isdisjoint(c.MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS))
        self.assertEqual(digest(sorted(paths - {"apps/web/vite.config.ts"})), ORIGINAL_PATHS_SHA256)
        self.assertEqual(digest(self.task["requirements"]), ORIGINAL_REQUIREMENTS_SHA256)
        self.assertEqual(digest(self.task["adrs"]), ORIGINAL_ADRS_SHA256)
        self.assertEqual(digest(self.task["acceptance_criteria"]), ORIGINAL_ACCEPTANCE_SHA256)
        self.assertEqual(
            self.task["source_ids"],
            [c.MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_ID, c.MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_SOURCE_ID],
        )
        self.assertEqual(digest(self.task), c.MODEL_LED_FLEXIBLE_DELIVERY_TASK_SHA256)
        sources = json.loads((ROOT / "docs/source-register.json").read_text())
        source = next(item for item in sources["sources"] if item["id"] == c.MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_ID)
        self.assertEqual(source["content_id"], "9404417")
        self.assertEqual(source["version"], 3)
        self.assertEqual(source["status"], "ACCEPTED")
        self.assertEqual(digest(source), c.MODEL_LED_FLEXIBLE_DELIVERY_SOURCE_SHA256)
        amendment = next(item for item in sources["sources"] if item["id"] == c.MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_SOURCE_ID)
        self.assertEqual(amendment["status"], "ACCEPTED")
        self.assertEqual(amendment["content_id"], "APBRA-174")
        self.assertEqual(digest(amendment), c.MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_SOURCE_SHA256)
        self.assertEqual(self.task["base_commit"], "b2fba8d507262cf912e161b491549ab0d5680b0d")

    def test_amendment_is_exact_governance_only_and_implementation_remains_blocked(self):
        amendment = c.MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_PATHS
        self.assertEqual(len(amendment), 8)
        self.assertTrue(amendment.issubset(c.MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS))
        self.assertNotIn("apps/web/vite.config.ts", amendment)
        self.assertNotIn("apps/web/vite.config.ts", self.task["restricted_paths"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, amendment, branch=c.MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_BRANCH), [])
            for omitted in amendment:
                with self.subTest(omitted=omitted):
                    errors = self.check(root, amendment - {omitted}, branch=c.MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_BRANCH)
                    self.assertIn("APBRA-174 Vite proxy amendment must change exactly its eight governance files", errors)
            errors = self.check(root, amendment | {"apps/web/vite.config.ts"}, branch=c.MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_BRANCH)
            self.assertIn("APBRA-174 registration and implementation changes must remain separate", errors)
            self.assertIn("APBRA-174 Vite proxy amendment must change exactly its eight governance files", errors)
            self.assertIn("Active branch conflicts with task authority: " + c.MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_BRANCH, errors)
            self.assertEqual(self.check(root, {"apps/web/vite.config.ts"}, branch=self.task["branch"]), [])

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
            "apps/web/vite.plugins.ts",
            "apps/web/vite.server.config.ts",
            "apps/web/ai-adapter.config.ts",
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
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            sources = json.loads((root / "docs/source-register.json").read_text())
            amendment = next(item for item in sources["sources"] if item["id"] == c.MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_SOURCE_ID)
            amendment["acceptance"] += " and every other Vite file"
            (root / "docs/source-register.json").write_text(json.dumps(sources))
            errors = self.check(root, {"apps/web/vite.config.ts"})
            self.assertIn("APBRA-174 Vite proxy amendment source differs from accepted provenance", errors)
            self.assertIn("File outside active task scope: apps/web/vite.config.ts", errors)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            task = copy.deepcopy(self.task)
            task["allowed_paths"].append("apps/web/**")
            (root / TASK_PATH).write_text(json.dumps(task))
            errors = self.check(root, {"apps/web/vite.config.ts"})
            self.assertIn("APBRA-174 contract differs from accepted authority", errors)
            self.assertIn("File outside active task scope: apps/web/vite.config.ts", errors)

    def test_historical_task_contracts_unchanged(self):
        expected = {
            "tasks/APBRA-143-typed-confirmed-requirements.json": "8a69e853ffe70c342d6f98a38e0d9542fc14b318ed5b00a9d468c2d9c78c01ea",
            "tasks/APBRA-144-ai-native-iterative-clarification.json": "ba498d1716c1f9cf77c21b15bb91307f5f1ae8905ad4a68e1f4b44679e72ae25",
            "tasks/APBRA-171-business-user-report-creation-intelligent-generation.json": "201e4164efbcf18e778f7152d9d3fd67a25b9232b1816ab6178701678358915f",
        }
        for path, expected_hash in expected.items():
            self.assertNotIn(path, c.MODEL_LED_FLEXIBLE_DELIVERY_PATHS)
            self.assertNotIn(path, c.MODEL_LED_FLEXIBLE_DELIVERY_REGISTRATION_PATHS)
            self.assertNotIn(path, c.MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_PATHS)
            self.assertEqual(digest(json.loads((ROOT / path).read_text())), expected_hash)


if __name__ == "__main__":
    unittest.main()
