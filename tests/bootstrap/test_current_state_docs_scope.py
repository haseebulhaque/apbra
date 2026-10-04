"""APBRA-177 finite documentation authority and separate registration gates."""

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
SPEC = importlib.util.spec_from_file_location("bootstrap_apbra177", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class CurrentStateDocsScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-177-current-state-docs.json"
        self.source_path = "docs/source-register.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.sources = json.loads((ROOT / self.source_path).read_text())

    def copy_repository(self, root):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.CURRENT_STATE_DOCS_PATHS)
        names.update(c.CURRENT_STATE_DOCS_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-177 synthetic fixture\n")

    def check(self, root, paths, branch=None):
        return c.check(
            root,
            active_task_id="APBRA-177",
            active_branch=branch or c.CURRENT_STATE_DOCS_BRANCH,
            changed_paths=set(paths),
        )[0]

    def test_exact_task_sources_history_and_paths(self):
        self.assertEqual(digest(self.task), c.CURRENT_STATE_DOCS_TASK_SHA256)
        self.assertEqual(len(c.CURRENT_STATE_DOCS_PATHS), 9)
        self.assertEqual(len(self.task["allowed_paths"]), 9)
        self.assertEqual(set(self.task["allowed_paths"]), c.CURRENT_STATE_DOCS_PATHS)
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        self.assertEqual(len(c.CURRENT_STATE_DOCS_REGISTRATION_PATHS), 5)
        self.assertTrue(c.CURRENT_STATE_DOCS_PATHS.isdisjoint(c.CURRENT_STATE_DOCS_REGISTRATION_PATHS))
        self.assertEqual(
            digest(self.sources["sources"][:c.CURRENT_STATE_DOCS_HISTORICAL_SOURCE_COUNT]),
            c.CURRENT_STATE_DOCS_HISTORICAL_SOURCES_SHA256,
        )
        rows = self.sources["sources"][c.CURRENT_STATE_DOCS_HISTORICAL_SOURCE_COUNT:]
        self.assertEqual(len(rows), len(c.CURRENT_STATE_DOCS_SOURCES))
        self.assertEqual([row["id"] for row in rows], self.task["source_ids"])
        for row, (source_id, content_id, version, expected) in zip(rows, c.CURRENT_STATE_DOCS_SOURCES):
            self.assertEqual((row["id"], row["content_id"], row["version"], row["status"]),
                             (source_id, content_id, version, "ACCEPTED"))
            self.assertEqual(digest(row), expected)

    def test_registration_is_exact_and_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            registration = c.CURRENT_STATE_DOCS_REGISTRATION_PATHS
            self.assertEqual(self.check(root, registration,
                                        c.CURRENT_STATE_DOCS_REGISTRATION_BRANCH), [])
            for missing in registration:
                with self.subTest(missing=missing):
                    errors = self.check(root, registration - {missing},
                                        c.CURRENT_STATE_DOCS_REGISTRATION_BRANCH)
                    self.assertIn("APBRA-177 registration must change exactly its five governance files", errors)
            for added in ("apps/api/README.md", ".github/workflows/bootstrap.yml", "README.md"):
                with self.subTest(added=added):
                    errors = self.check(root, registration | {added},
                                        c.CURRENT_STATE_DOCS_REGISTRATION_BRANCH)
                    self.assertIn("APBRA-177 registration must change exactly its five governance files", errors)
                    self.assertIn("File outside active task scope: " + added, errors)
            self.assertIn(
                "APBRA-177 registration and documentation changes must remain separate",
                self.check(root, registration | {"README.md"},
                           c.CURRENT_STATE_DOCS_REGISTRATION_BRANCH),
            )

    def test_implementation_is_nine_documents_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in c.CURRENT_STATE_DOCS_PATHS:
                with self.subTest(path=path):
                    self.assertEqual(self.check(root, {path}), [])
            for path in ("apps/api/README.md", "docs/other.md", "apps/web/src/api.ts",
                         "tasks/APBRA-177-current-state-docs.json"):
                with self.subTest(path=path):
                    self.assertIn("File outside active task scope: " + path,
                                  self.check(root, {path}))
            self.assertIn(
                "APBRA-177 documentation branch cannot change governance registration files",
                self.check(root, {"README.md", self.task_path}),
            )

    def test_rehashed_scope_and_gate_mutations_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for paths in (["docs/**"], self.task["allowed_paths"] + ["apps/api/README.md"]):
                with self.subTest(paths=paths):
                    changed = copy.deepcopy(self.task)
                    changed["allowed_paths"] = paths
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "CURRENT_STATE_DOCS_TASK_SHA256", digest(changed)):
                        self.assertIn("Unexpected APBRA-177 documentation scope",
                                      self.check(root, {"README.md"}))
            for section in ("requirements", "adrs", "restricted_paths", "acceptance_criteria",
                            "verification_required", "out_of_scope", "dependencies"):
                with self.subTest(section=section):
                    changed = copy.deepcopy(self.task)
                    changed[section] = changed[section][:-1]
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "CURRENT_STATE_DOCS_TASK_SHA256", digest(changed)):
                        errors = self.check(root, {"README.md"})
                    self.assertTrue(any("APBRA-177 safety/review gate differs: " + section in x
                                        for x in errors), errors)

    def test_historical_and_new_source_mutations_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            changed = copy.deepcopy(self.sources)
            historical_row = next(row for row in changed["sources"][:59] if "acceptance" in row)
            historical_row["acceptance"] += " changed"
            (root / self.source_path).write_text(json.dumps(changed))
            self.assertIn("APBRA-177 historical source provenance changed",
                          self.check(root, {"README.md"}))
            changed = copy.deepcopy(self.sources)
            changed["sources"][-1]["acceptance"] += " changed"
            (root / self.source_path).write_text(json.dumps(changed))
            self.assertTrue(any("APBRA-177 source differs from provenance" in x
                                for x in self.check(root, {"README.md"})))
            changed = copy.deepcopy(self.sources)
            changed["sources"][59], changed["sources"][60] = changed["sources"][60], changed["sources"][59]
            (root / self.source_path).write_text(json.dumps(changed))
            self.assertIn("APBRA-177 source ordering differs",
                          self.check(root, {"README.md"}))

    def test_apbra173_historical_registration_accepts_only_pinned_later_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(c.check(
                root,
                active_task_id="APBRA-173",
                active_branch=c.PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH,
                changed_paths=c.PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS,
            )[0], [])
            changed = copy.deepcopy(self.sources)
            changed["sources"].append(copy.deepcopy(changed["sources"][-1]))
            changed["sources"][-1]["id"] = "unregistered-later-source"
            (root / self.source_path).write_text(json.dumps(changed))
            errors = c.check(
                root,
                active_task_id="APBRA-173",
                active_branch=c.PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH,
                changed_paths=c.PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS,
            )[0]
            self.assertIn("APBRA-173A registration added unrelated source rows", errors)


if __name__ == "__main__":
    unittest.main()
