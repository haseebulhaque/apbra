"""APBRA-176 exact documentation authority and separate governance registration."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_apbra176", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class OwnerOnboardingIdentityDocsScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-176-owner-onboarding-identity-docs.json"
        self.source_path = "docs/source-register.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.sources = json.loads((ROOT / self.source_path).read_text())

    def copy_repository(self, root):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.OWNER_ONBOARDING_IDENTITY_DOCS_PATHS)
        names.update(c.OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-176 fixture\n")

    def check(self, root, paths, branch=None):
        return c.check(root, active_task_id="APBRA-176",
                       active_branch=branch or self.task["branch"],
                       changed_paths=set(paths))[0]

    def test_exact_contract_and_sources(self):
        digest = lambda x: hashlib.sha256(
            json.dumps(x, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        docs = c.OWNER_ONBOARDING_IDENTITY_DOCS_PATHS
        registration = c.OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_PATHS
        self.assertEqual(len(docs), 9)
        self.assertEqual(len(registration), 6)
        self.assertTrue(docs.isdisjoint(registration))
        self.assertEqual(set(self.task["allowed_paths"]), docs)
        self.assertTrue(all("*" not in path for path in docs))
        self.assertEqual(self.task["base_commit"], "d33e6222aaf902da821de2f59f288005f7f6c709")
        self.assertEqual(digest(self.task), c.OWNER_ONBOARDING_IDENTITY_DOCS_TASK_SHA256)
        source_map = {x["id"]: x for x in self.sources["sources"]}
        for source_id, content_id, version, expected in (
            (c.OWNER_ONBOARDING_IDENTITY_SOURCE_ID, "4030847", 4,
             c.OWNER_ONBOARDING_IDENTITY_SOURCE_SHA256),
            (c.OWNER_ONBOARDING_REQUIREMENTS_SOURCE_ID, "3932362", 7,
             c.OWNER_ONBOARDING_REQUIREMENTS_SOURCE_SHA256),
        ):
            with self.subTest(source_id=source_id):
                source = source_map[source_id]
                self.assertEqual((source["content_id"], source["version"], source["status"]),
                                 (content_id, version, "ACCEPTED"))
                self.assertEqual(digest(source), expected)
        source_ids = [source["id"] for source in self.sources["sources"]]
        self.assertEqual(source_ids.count(self.task["source_ids"][0]), 1)
        start = source_ids.index(self.task["source_ids"][0])
        self.assertEqual(source_ids[start:start + len(self.task["source_ids"])],
                         self.task["source_ids"])

    def test_separate_registration_and_docs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in c.OWNER_ONBOARDING_IDENTITY_DOCS_PATHS:
                with self.subTest(path=path):
                    self.assertEqual(self.check(root, {path}), [])
            registration = c.OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_PATHS
            self.assertEqual(self.check(root, registration,
                                        c.OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_BRANCH), [])
            errors = self.check(root, registration - {self.task_path},
                                c.OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_BRANCH)
            self.assertIn("APBRA-176 registration must change exactly its six governance files", errors)
            errors = self.check(root, registration | {"README.md"},
                                c.OWNER_ONBOARDING_IDENTITY_DOCS_REGISTRATION_BRANCH)
            self.assertIn("APBRA-176 registration and documentation changes must remain separate", errors)
            self.assertIn("File outside active task scope: README.md", errors)
            errors = self.check(root, {"README.md", self.task_path})
            self.assertIn("APBRA-176 documentation branch cannot change governance registration files", errors)

    def test_mutations_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in ("apps/api/README.md", ".github/workflows/bootstrap.yml", "docs/other.md"):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("outside scope\n")
                self.assertIn("File outside active task scope: " + path,
                              self.check(root, {path}))
            for field, value, expected in (
                ("base_commit", "0" * 40, "Stale APBRA-176 registration base"),
                ("branch", "agent/APBRA-DOCS/APBRA-176-wrong", "Unexpected APBRA-176 documentation branch"),
                ("allowed_paths", ["docs/**"], "Unexpected APBRA-176 documentation scope"),
                ("source_ids", ["implementation-contract"], "APBRA-176 requires its two accepted sources"),
            ):
                with self.subTest(field=field):
                    changed = copy.deepcopy(self.task)
                    changed[field] = value
                    (root / self.task_path).write_text(json.dumps(changed))
                    errors = self.check(root, {"README.md"})
                    self.assertTrue(any(expected in error for error in errors), errors)
                    self.assertIn("File outside active task scope: README.md", errors)
                    (root / self.task_path).write_text(json.dumps(self.task))
            changed = copy.deepcopy(self.sources)
            next(x for x in changed["sources"] if x["id"] == c.OWNER_ONBOARDING_REQUIREMENTS_SOURCE_ID)["acceptance"] += " altered"
            (root / self.source_path).write_text(json.dumps(changed))
            errors = self.check(root, {"README.md"})
            self.assertTrue(any("APBRA-176 source differs from accepted provenance" in e for e in errors), errors)
            self.assertIn("File outside active task scope: README.md", errors)


if __name__ == "__main__":
    unittest.main()
