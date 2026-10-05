"""APBRA-173B finite registration, historical source and negative authority gates."""

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
SPEC = importlib.util.spec_from_file_location("bootstrap_apbra173b", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class HostedWebReleaseScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-173-production-web-release.json"
        self.source_path = "docs/source-register.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.sources = json.loads((ROOT / self.source_path).read_text())

    def copy_repository(self, root):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.HOSTED_WEB_RELEASE_PATHS)
        names.update(c.HOSTED_WEB_RELEASE_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-173B future-path fixture\n")

    def check(self, root, paths, branch=None):
        return c.check(root, active_task_id="APBRA-173",
                       active_branch=branch or c.HOSTED_WEB_RELEASE_BRANCH,
                       changed_paths=set(paths))[0]

    def test_exact_task_paths_sources_and_gates(self):
        expected = {
            "apps/api/Dockerfile", "apps/api/Dockerfile.dockerignore",
            "apps/api/src/apbra_api/api.py", "apps/api/src/apbra_api/web_static.py",
            "apps/api/alembic/env.py", "apps/api/tests/test_hosted_web.py",
            "apps/api/tests/test_migrations.py", "apps/api/README.md",
            ".github/workflows/bootstrap.yml", "scripts/check_ci_policy.py",
            "scripts/check_bootstrap.py", "tests/bootstrap/test_ci_policy.py",
            "scripts/smoke_hosted_image.sh",
        }
        self.assertEqual(c.HOSTED_WEB_RELEASE_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertEqual(len(self.task["allowed_paths"]), 13)
        self.assertTrue(all("*" not in path for path in expected))
        self.assertEqual(self.task["branch"], c.HOSTED_WEB_RELEASE_BRANCH)
        self.assertEqual(self.task["base_commit"], "714a53e3e26ea85b176dd6990ccd7229d1ab770c")
        self.assertEqual(digest(self.task), c.HOSTED_WEB_RELEASE_TASK_SHA256)
        self.assertEqual(len(c.HOSTED_WEB_RELEASE_REGISTRATION_PATHS), 5)
        self.assertEqual(self.task["source_ids"], [row[0] for row in c.HOSTED_WEB_RELEASE_SOURCES])
        self.assertEqual(digest(self.sources["sources"][:66]),
                         c.HOSTED_WEB_RELEASE_HISTORICAL_SOURCES_SHA256)
        self.assertEqual(len(self.sources["sources"]), 66 + len(c.HOSTED_WEB_RELEASE_SOURCES))
        self.assertEqual([row["id"] for row in self.sources["sources"][66:]],
                         self.task["source_ids"])
        for sid, cid, version, expected_hash in c.HOSTED_WEB_RELEASE_SOURCES:
            matches = [row for row in self.sources["sources"] if row["id"] == sid]
            self.assertEqual(len(matches), 1)
            self.assertEqual((matches[0]["content_id"], matches[0]["version"],
                              matches[0]["status"]), (cid, version, "ACCEPTED"))
            self.assertEqual(digest(matches[0]), expected_hash)
        owner_row = self.sources["sources"][-1]
        self.assertEqual(owner_row["id"], "apbra-173b-owner-architecture-acceptance")
        self.assertEqual(owner_row["url"],
                         "https://arkitektz.atlassian.net/browse/APBRA-173?focusedCommentId=10526")
        self.assertIn("10526", owner_row["version"])
        self.assertIn("Confirmed and approved", owner_row["acceptance"])
        self.assertIn("required backend runtime code/resources", owner_row["acceptance"])
        for section, expected_hash in c.HOSTED_WEB_RELEASE_GATE_SHA256.items():
            self.assertEqual(digest(self.task[section]), expected_hash)
        words = " ".join(self.task["requirements"] + self.task["acceptance_criteria"]
                         + self.task["verification_required"] + self.task["out_of_scope"])
        for phrase in ("10522", "10526", "45-minute", "manifest-reachable", "same connection",
                       "private", "rollout", "schema compatibility", "Live Canvas",
                       "APBRA-173C", "Haseeb"):
            self.assertIn(phrase, words)
        image_rule = self.task["acceptance_criteria"][2]
        self.assertIn("Required backend runtime code/resources", image_rule)
        self.assertIn("never served by public static routes", image_rule)
        self.assertIn("secrets", image_rule)
        self.assertIn("synthetic build-context markers", image_rule)
        build_rule = self.task["requirements"][5]
        self.assertIn("Raw frontend source may enter the build stage", build_rule)
        self.assertIn("must not remain in the final runtime image", build_rule)
        self.assertIn("Required backend runtime code/resources", build_rule)

    def test_registration_exactly_five_and_product_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            registration = c.HOSTED_WEB_RELEASE_REGISTRATION_PATHS
            self.assertEqual(self.check(root, registration,
                                        c.HOSTED_WEB_RELEASE_REGISTRATION_BRANCH), [])
            for path in registration:
                with self.subTest(missing=path):
                    self.assertIn("APBRA-173B registration must change exactly its five governance files",
                                  self.check(root, registration - {path},
                                             c.HOSTED_WEB_RELEASE_REGISTRATION_BRANCH))
            for extra in ("apps/api/Dockerfile", "apps/api/src/apbra_api/api.py",
                          ".github/workflows/bootstrap.yml", "README.md",
                          "tests/bootstrap/test_private_content_storage_scope.py"):
                with self.subTest(extra=extra):
                    self.assertIn("APBRA-173B registration must change exactly its five governance files",
                                  self.check(root, registration | {extra},
                                             c.HOSTED_WEB_RELEASE_REGISTRATION_BRANCH))
            self.assertIn("APBRA-173B registration and implementation changes must remain separate",
                          self.check(root, registration | {"apps/api/Dockerfile"},
                                     c.HOSTED_WEB_RELEASE_REGISTRATION_BRANCH))
            for path in c.HOSTED_WEB_RELEASE_PATHS:
                with self.subTest(implementation=path):
                    self.assertEqual(self.check(root, {path}), [])
            for path in (self.task_path, self.source_path,
                         "tests/bootstrap/test_hosted_web_release_scope.py"):
                self.assertIn("APBRA-173B implementation branch cannot change governance registration files",
                              self.check(root, {path}))
            self.assertEqual(c.check(root, active_task_id="APBRA-173",
                                     active_branch=c.PRIVATE_CONTENT_STORAGE_REGISTRATION_BRANCH,
                                     changed_paths=c.PRIVATE_CONTENT_STORAGE_REGISTRATION_PATHS)[0], [])

    def test_rehashed_path_and_gate_mutations_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for paths in (self.task["allowed_paths"][:-1],
                          self.task["allowed_paths"] + ["apps/api/src/apbra_api/config.py"],
                          self.task["allowed_paths"] + ["apps/api/alembic/versions/new.py"],
                          self.task["allowed_paths"] + ["apps/web/vite.config.ts"],
                          self.task["allowed_paths"] + ["apps/api/uv.lock"],
                          ["apps/api/**"]):
                with self.subTest(paths=paths):
                    changed = copy.deepcopy(self.task)
                    changed["allowed_paths"] = paths
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "HOSTED_WEB_RELEASE_TASK_SHA256", digest(changed)):
                        self.assertIn("Unexpected APBRA-173B implementation scope",
                                      self.check(root, {"apps/api/Dockerfile"}))
            for section in c.HOSTED_WEB_RELEASE_GATE_SHA256:
                with self.subTest(section=section):
                    changed = copy.deepcopy(self.task)
                    changed[section] = changed[section][:-1]
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "HOSTED_WEB_RELEASE_TASK_SHA256", digest(changed)):
                        errors = self.check(root, {"apps/api/Dockerfile"})
                    self.assertIn("APBRA-173B safety/review gate differs: " + section, errors)
            for section, needle, replacement in (
                ("requirements", "comment 10526", "comment 10522"),
                ("requirements", "must never be publicly served", "may be publicly served"),
                ("requirements", "must not remain in the final runtime image",
                 "may remain in the final runtime image"),
                ("acceptance_criteria", "never served by public static routes",
                 "served by public static routes"),
                ("acceptance_criteria", "Private evidence", "Evidence"),
                ("dependencies", "comment 10526", "comment 10522"),
            ):
                with self.subTest(section=section, needle=needle):
                    changed = copy.deepcopy(self.task)
                    index = next(i for i, value in enumerate(changed[section]) if needle in value)
                    changed[section][index] = changed[section][index].replace(
                        needle, replacement, 1)
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "HOSTED_WEB_RELEASE_TASK_SHA256", digest(changed)):
                        errors = self.check(root, {"apps/api/Dockerfile"})
                    self.assertIn("APBRA-173B safety/review gate differs: " + section, errors)

    def test_append_only_source_mutations_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            original = copy.deepcopy(self.sources)
            cases = []
            changed = copy.deepcopy(original)
            changed["sources"][60]["acceptance"] += " altered"
            cases.append((changed, "APBRA-173B historical source provenance changed"))
            changed = copy.deepcopy(original)
            changed["sources"][66], changed["sources"][67] = changed["sources"][67], changed["sources"][66]
            cases.append((changed, "APBRA-173B source ordering differs"))
            changed = copy.deepcopy(original)
            changed["sources"][66]["acceptance"] += " altered"
            cases.append((changed, "APBRA-173B source differs from provenance"))
            changed = copy.deepcopy(original)
            changed["sources"][-1]["url"] = "https://arkitektz.atlassian.net/browse/APBRA-173"
            cases.append((changed, "APBRA-173B source differs from provenance"))
            changed = copy.deepcopy(original)
            changed["sources"][-1]["acceptance"] = "Controller recommendation 10522 is accepted."
            cases.append((changed, "APBRA-173B source differs from provenance"))
            changed = copy.deepcopy(original)
            changed["sources"].append(copy.deepcopy(changed["sources"][-1]))
            cases.append((changed, "APBRA-173B registration added unrelated source rows"))
            for changed, expected in cases:
                with self.subTest(expected=expected):
                    (root / self.source_path).write_text(json.dumps(changed))
                    self.assertTrue(any(expected in error for error in self.check(
                        root, c.HOSTED_WEB_RELEASE_REGISTRATION_PATHS,
                        c.HOSTED_WEB_RELEASE_REGISTRATION_BRANCH)))


if __name__ == "__main__":
    unittest.main()
