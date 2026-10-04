"""APBRA-173A exact portable protected-content registration and negative scope tests."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_apbra173a", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PrivateContentStorageScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-173-private-content-storage.json"
        self.source_path = "docs/source-register.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.sources = json.loads((ROOT / self.source_path).read_text())

    def copy_repository(self, root):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.PRIVATE_CONTENT_STORAGE_PATHS)
        names.update(c.PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-173A future-path fixture\n")

    def check(self, root, paths, branch=None):
        return c.check(
            root,
            active_task_id="APBRA-173",
            active_branch=branch or c.PRIVATE_CONTENT_STORAGE_BRANCH,
            changed_paths=set(paths),
        )[0]

    def test_exact_contract_sources_and_gates(self):
        expected = {
            "apps/api/README.md",
            "apps/api/src/apbra_api/content_storage.py",
            "apps/api/src/apbra_api/evidence.py",
            "apps/api/src/apbra_api/artifacts.py",
            "apps/api/src/apbra_api/reference_material.py",
            "apps/api/src/apbra_api/application.py",
            "apps/api/src/apbra_api/generation.py",
            "apps/api/src/apbra_api/api.py",
            "apps/api/tests/test_content_storage.py",
            "apps/api/tests/test_evidence.py",
            "apps/api/tests/test_artifacts.py",
            "apps/api/tests/test_reference_material.py",
            "apps/api/tests/test_generation.py",
        }
        self.assertEqual(c.PRIVATE_CONTENT_STORAGE_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertEqual(len(self.task["allowed_paths"]), 13)
        self.assertTrue(all("*" not in name for name in expected))
        self.assertEqual(self.task["branch"], c.PRIVATE_CONTENT_STORAGE_BRANCH)
        self.assertEqual(self.task["base_commit"], "953835bc1f51895cf15e9ae3784f10a5ac2df0d6")
        self.assertEqual(digest(self.task), c.PRIVATE_CONTENT_STORAGE_TASK_SHA256)
        self.assertEqual(len(c.PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS), 9)
        self.assertEqual(
            set(c.PRIVATE_CONTENT_STORAGE_HISTORICAL_TEST_SHA256),
            {
                "tests/bootstrap/test_company_lifecycle_scope.py",
                "tests/bootstrap/test_deployment_portability_entitlement_docs_scope.py",
                "tests/bootstrap/test_owner_onboarding_identity_docs_scope.py",
                "tests/bootstrap/test_provider_neutral_sso_scope.py",
            },
        )
        for name, expected_hash in c.PRIVATE_CONTENT_STORAGE_HISTORICAL_TEST_SHA256.items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected_hash)
        self.assertTrue(expected.isdisjoint(c.PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS))
        self.assertEqual(self.task["source_ids"], [row[0] for row in c.PRIVATE_CONTENT_STORAGE_SOURCES])
        source_map = {row["id"]: row for row in self.sources["sources"]}
        self.assertEqual(
            digest(self.sources["sources"][:c.PRIVATE_CONTENT_STORAGE_HISTORICAL_SOURCE_COUNT]),
            c.PRIVATE_CONTENT_STORAGE_HISTORICAL_SOURCES_SHA256,
        )
        for sid, page, version, expected_hash in c.PRIVATE_CONTENT_STORAGE_SOURCES:
            with self.subTest(source=sid):
                row = source_map[sid]
                self.assertEqual((row["content_id"], row["version"], row["status"]), (page, version, "ACCEPTED"))
                self.assertEqual(digest(row), expected_hash)
        for section, expected_hash in c.PRIVATE_CONTENT_STORAGE_GATE_SHA256.items():
            self.assertEqual(digest(self.task[section]), expected_hash)
        joined = " ".join(
            self.task["requirements"] + self.task["acceptance_criteria"]
            + self.task["out_of_scope"] + self.task["dependencies"]
        )
        for phrase in (
            "Jira APBRA-173",
            "10471",
            "database as authority",
            "SHA-256",
            "idempotent",
            "restore",
            "public container",
            "No Azure SDK",
            "Live Canvas",
            "APBRA-165",
            "APBRA-166",
        ):
            self.assertIn(phrase, joined)
        self.assertNotIn("apps/api/src/apbra_api/config.py", expected)
        self.assertNotIn("apps/api/src/apbra_api/persistence.py", expected)

    def test_registration_and_implementation_remain_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            registration = c.PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS
            self.assertEqual(self.check(root, registration, c.PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH), [])
            for name in sorted(registration):
                with self.subTest(omitted=name):
                    errors = self.check(root, registration - {name}, c.PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH)
                    self.assertIn("APBRA-173A registration must change exactly its nine governance files", errors)
            for extra in (
                "apps/api/src/apbra_api/evidence.py",
                "apps/api/src/apbra_api/content_storage.py",
                "apps/api/src/apbra_api/config.py",
                ".github/workflows/bootstrap.yml",
            ):
                with self.subTest(extra=extra):
                    errors = self.check(root, registration | {extra}, c.PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH)
                    self.assertIn("File outside active task scope: " + extra, errors)
            self.assertEqual(self.check(root, {"apps/api/src/apbra_api/content_storage.py"}), [])
            errors = self.check(root, {self.task_path})
            self.assertIn("APBRA-173A implementation branch cannot change governance registration files", errors)
            errors = self.check(root, {"apps/api/src/apbra_api/api.py", self.task_path})
            self.assertIn("APBRA-173A registration and implementation changes must remain separate", errors)

    def test_path_mutations_fail_with_recomputed_task_digest(self):
        original = self.task["allowed_paths"]
        mutations = {
            "missing port": original[1:],
            "wildcard api": original + ["apps/api/**"],
            "wildcard tests": original + ["apps/api/tests/**"],
            "extra runtime": original + ["apps/api/src/apbra_api/config.py"],
            "extra persistence": original + ["apps/api/src/apbra_api/persistence.py"],
            "extra azure adapter": original + ["apps/api/src/apbra_api/azure_blob.py"],
            "workflow": original + [".github/workflows/bootstrap.yml"],
            "dependency": original + ["apps/api/pyproject.toml"],
            "lockfile": original + ["apps/api/uv.lock"],
            "infrastructure": original + ["infrastructure/azure/main.bicep"],
            "canvas": original + ["apps/web/src/LiveCanvas.tsx"],
            "duplicate": original + [original[0]],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for label, paths in mutations.items():
                with self.subTest(label=label):
                    changed = copy.deepcopy(self.task)
                    changed["allowed_paths"] = paths
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "PRIVATE_CONTENT_STORAGE_TASK_SHA256", digest(changed)):
                        errors = self.check(root, {"apps/api/src/apbra_api/evidence.py"})
                    self.assertTrue(
                        any("scope" in error.lower() or "unique" in error.lower() for error in errors),
                        errors,
                    )
            (root / self.task_path).write_text(json.dumps(self.task))

    def test_security_and_review_gates_fail_with_recomputed_task_digest(self):
        mutations = {
            "requirements": "database as authority",
            "adrs": "storage key is not an authorization token",
            "architecture_refs": "Jira APBRA-173 owner decision comment 10471",
            "restricted_paths": "infrastructure/**",
            "acceptance_criteria": "revoked membership",
            "verification_required": "genuinely separate independent exact-head governance review",
            "out_of_scope": "Live Canvas",
            "dependencies": "Haseeb manual merge",
            "escalate_when": "third-party dependency",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for section, phrase in mutations.items():
                with self.subTest(section=section):
                    changed = copy.deepcopy(self.task)
                    if section == "restricted_paths":
                        changed[section].remove(phrase)
                    else:
                        changed[section] = [
                            item.replace(phrase, "WEAKENED") for item in changed[section]
                        ]
                    self.assertNotEqual(changed[section], self.task[section])
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "PRIVATE_CONTENT_STORAGE_TASK_SHA256", digest(changed)):
                        errors = self.check(root, {"apps/api/src/apbra_api/evidence.py"})
                    self.assertIn("APBRA-173A safety/review gate differs: " + section, errors)
            (root / self.task_path).write_text(json.dumps(self.task))

    def test_source_history_and_new_rows_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            sources = copy.deepcopy(self.sources)
            sources["sources"][0]["status"] = "PROPOSED"
            (root / self.source_path).write_text(json.dumps(sources))
            errors = self.check(root, c.PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS, c.PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH)
            self.assertIn("APBRA-173A historical source provenance changed", errors)
            sources = copy.deepcopy(self.sources)
            row = next(x for x in sources["sources"] if x["id"] == "apbra-173a-data-integrity")
            row["version"] = 5
            (root / self.source_path).write_text(json.dumps(sources))
            errors = self.check(root, c.PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS, c.PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH)
            self.assertTrue(any("APBRA-173A source" in error for error in errors), errors)
            sources = copy.deepcopy(self.sources)
            sources["sources"].append(copy.deepcopy(sources["sources"][-1]))
            sources["sources"][-1]["id"] = "unrelated-extra-source"
            (root / self.source_path).write_text(json.dumps(sources))
            errors = self.check(root, c.PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS, c.PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH)
            self.assertIn("APBRA-173A registration added unrelated source rows", errors)

    def test_historical_test_repairs_cannot_change_beyond_pinned_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for name in c.PRIVATE_CONTENT_STORAGE_HISTORICAL_TEST_SHA256:
                with self.subTest(path=name):
                    path = root / name
                    original = path.read_bytes()
                    path.write_bytes(original + b"# unrelated change\n")
                    errors = self.check(
                        root,
                        c.PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS,
                        c.PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH,
                    )
                    self.assertIn("APBRA-173A historical test repair differs: " + name, errors)
                    path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
