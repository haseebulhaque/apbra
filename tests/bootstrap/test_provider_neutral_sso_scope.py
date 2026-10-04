"""APBRA-172 exact provider-neutral SSO authority and separate registration."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_apbra172", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class ProviderNeutralSsoScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-172-provider-neutral-sso.json"
        self.source_path = "docs/source-register.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.sources = json.loads((ROOT / self.source_path).read_text())

    def copy_repository(self, root):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.PROVIDER_NEUTRAL_SSO_PATHS)
        names.update(c.PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-172 fixture\n")

    def check(self, root, paths, branch=None):
        return c.check(root, active_task_id="APBRA-172",
                       active_branch=branch or c.PROVIDER_NEUTRAL_SSO_BRANCH,
                       changed_paths=set(paths))[0]

    def test_exact_task_and_five_accepted_sources(self):
        digest = lambda x: hashlib.sha256(json.dumps(x, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(len(c.PROVIDER_NEUTRAL_SSO_PATHS), 24)
        self.assertEqual(len(c.PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS), 7)
        self.assertEqual(set(self.task["allowed_paths"]), c.PROVIDER_NEUTRAL_SSO_PATHS)
        self.assertTrue(c.PROVIDER_NEUTRAL_SSO_PATHS.isdisjoint(c.PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS))
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        self.assertEqual(self.task["base_commit"], "613e43a9a9040428630d73f6ab12fd930f29d830")
        self.assertEqual(self.task["branch"], c.PROVIDER_NEUTRAL_SSO_BRANCH)
        self.assertEqual(digest(self.task), c.PROVIDER_NEUTRAL_SSO_TASK_SHA256)
        self.assertEqual(self.task["source_ids"], [row[0] for row in c.PROVIDER_NEUTRAL_SSO_SOURCES])
        source_map = {source["id"]: source for source in self.sources["sources"]}
        source_ids = [source["id"] for source in self.sources["sources"]]
        self.assertEqual(source_ids.count(self.task["source_ids"][0]), 1)
        start = source_ids.index(self.task["source_ids"][0])
        self.assertEqual(source_ids[start:start + len(self.task["source_ids"])], self.task["source_ids"])
        for source_id, content_id, version, expected in c.PROVIDER_NEUTRAL_SSO_SOURCES:
            with self.subTest(source_id=source_id):
                source = source_map[source_id]
                self.assertEqual((source["content_id"], source["version"], source["status"]),
                                 (content_id, version, "ACCEPTED"))
                self.assertEqual(digest(source), expected)

    def test_registration_and_later_implementation_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, c.PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS,
                                        c.PROVIDER_NEUTRAL_SSO_REGISTRATION_BRANCH), [])
            self.assertEqual(self.check(root, c.PROVIDER_NEUTRAL_SSO_PATHS), [])
            errors = self.check(root, c.PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS - {self.task_path},
                                c.PROVIDER_NEUTRAL_SSO_REGISTRATION_BRANCH)
            self.assertIn("APBRA-172 registration must change exactly its seven governance files", errors)
            errors = self.check(root, c.PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS | {"apps/api/src/apbra_api/api.py"},
                                c.PROVIDER_NEUTRAL_SSO_REGISTRATION_BRANCH)
            self.assertIn("APBRA-172 registration and implementation changes must remain separate", errors)
            self.assertIn("File outside active task scope: apps/api/src/apbra_api/api.py", errors)
            errors = self.check(root, {self.task_path})
            self.assertIn("APBRA-172 implementation branch cannot change governance registration files", errors)

    def test_unregistered_paths_and_wrong_branch_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in ("infrastructure/azure/main.bicep", "apps/api/requirements.txt",
                         "apps/web/package-lock.json", ".github/workflows/bootstrap.yml",
                         "apps/api/src/apbra_api/entra_hidden.py", "apps/web/src/googleLogin.tsx"):
                with self.subTest(path=path):
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        target.write_text("outside scope\n")
                    self.assertIn("File outside active task scope: " + path, self.check(root, {path}))
            errors = self.check(root, c.PROVIDER_NEUTRAL_SSO_REGISTRATION_PATHS,
                                "agent/APBRA-DEVOPS/APBRA-172-wrong-registration")
            self.assertTrue(any("Active branch conflicts with task authority" in e for e in errors), errors)

    def test_task_and_source_mutations_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for field, value, expected in (
                ("base_commit", "0" * 40, "Stale APBRA-172 registration base"),
                ("branch", "agent/APBRA-DEVOPS/APBRA-172-wrong", "Unexpected APBRA-172 implementation branch"),
                ("allowed_paths", ["apps/api/**"], "Unexpected APBRA-172 implementation scope"),
                ("allowed_paths", self.task["allowed_paths"] + ["apps/api/src/apbra_api/entra_hidden.py"], "Unexpected APBRA-172 implementation scope"),
                ("source_ids", ["implementation-contract"], "APBRA-172 requires its five accepted sources"),
                ("owner_acceptance", "PENDING", "APBRA-172 requires issued implementation acceptance"),
            ):
                with self.subTest(field=field):
                    changed = copy.deepcopy(self.task)
                    changed[field] = value
                    (root / self.task_path).write_text(json.dumps(changed))
                    errors = self.check(root, {"apps/api/src/apbra_api/api.py"})
                    self.assertTrue(any(expected in error for error in errors), errors)
                    self.assertIn("File outside active task scope: apps/api/src/apbra_api/api.py", errors)
                    (root / self.task_path).write_text(json.dumps(self.task))
            for source_id in self.task["source_ids"]:
                with self.subTest(source_id=source_id):
                    changed = copy.deepcopy(self.sources)
                    next(x for x in changed["sources"] if x["id"] == source_id)["acceptance"] += " broadened"
                    (root / self.source_path).write_text(json.dumps(changed))
                    errors = self.check(root, {"apps/api/src/apbra_api/api.py"})
                    self.assertTrue(any("APBRA-172 source differs from accepted provenance" in e for e in errors), errors)
                    self.assertIn("File outside active task scope: apps/api/src/apbra_api/api.py", errors)
                    (root / self.source_path).write_text(json.dumps(self.sources))


if __name__ == "__main__":
    unittest.main()
