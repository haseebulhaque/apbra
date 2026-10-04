"""APBRA-108 finite candidate-source safety authority and separate registration."""

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
SPEC = importlib.util.spec_from_file_location("bootstrap_apbra108", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class CandidateSourceSafetyScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-108-candidate-source-safety.json"
        self.source_path = "docs/source-register.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.sources = json.loads((ROOT / self.source_path).read_text())

    def copy_repository(self, root):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.CANDIDATE_SOURCE_SAFETY_PATHS)
        names.update(c.CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-108 fixture\n")

    def check(self, root, paths, branch=None):
        return c.check(
            root,
            active_task_id="APBRA-108",
            active_branch=branch or c.CANDIDATE_SOURCE_SAFETY_BRANCH,
            changed_paths=set(paths),
        )[0]

    def test_exact_contract_sources_and_claim_gate(self):
        expected = {
            "apps/api/tests/test_generation.py",
            "apps/web/src/genericPowerBI.test.ts",
            "apps/web/src/genericPowerBI.ts",
        }
        self.assertEqual(c.CANDIDATE_SOURCE_SAFETY_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertEqual(len(self.task["allowed_paths"]), 3)
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        self.assertEqual(self.task["branch"], c.CANDIDATE_SOURCE_SAFETY_BRANCH)
        self.assertEqual(self.task["base_commit"], "a9fa15de2fa51331e8069eb4519cc6deaf7e6ccf")
        self.assertEqual(digest(self.task), c.CANDIDATE_SOURCE_SAFETY_TASK_SHA256)
        self.assertEqual(len(c.CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS), 5)
        self.assertTrue(expected.isdisjoint(c.CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS))
        self.assertEqual(self.task["source_ids"], [row[0] for row in c.CANDIDATE_SOURCE_SAFETY_SOURCES])
        source_map = {row["id"]: row for row in self.sources["sources"]}
        for sid, page, version, expected_hash in c.CANDIDATE_SOURCE_SAFETY_SOURCES:
            with self.subTest(source=sid):
                row = source_map[sid]
                self.assertEqual((row["content_id"], row["version"], row["status"]), (page, version, "ACCEPTED"))
                self.assertEqual(digest(row), expected_hash)
        for section, expected_hash in c.CANDIDATE_SOURCE_SAFETY_GATE_SHA256.items():
            self.assertEqual(digest(self.task[section]), expected_hash)
        joined = " ".join(self.task["requirements"] + self.task["acceptance_criteria"] + self.task["out_of_scope"])
        for phrase in ("four unrelated renamed synthetic domains", "Power Query M", "TMDL", "DAX", "APBRA-165", "APBRA-166", "Desktop execution"):
            self.assertIn(phrase, joined)

    def test_registration_and_implementation_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, c.CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS,
                                        c.CANDIDATE_SOURCE_SAFETY_REGISTRATION_BRANCH), [])
            self.assertEqual(self.check(root, c.CANDIDATE_SOURCE_SAFETY_PATHS), [])
            for omitted in c.CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS:
                with self.subTest(omitted=omitted):
                    errors = self.check(root, c.CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS - {omitted},
                                        c.CANDIDATE_SOURCE_SAFETY_REGISTRATION_BRANCH)
                    self.assertIn("APBRA-108 registration must change exactly its five governance files", errors)
            for extra in ("apps/web/src/genericPowerBI.ts", "apps/api/src/apbra_api/evidence.py"):
                with self.subTest(extra=extra):
                    errors = self.check(root, c.CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS | {extra},
                                        c.CANDIDATE_SOURCE_SAFETY_REGISTRATION_BRANCH)
                    self.assertIn("File outside active task scope: " + extra, errors)
            errors = self.check(root, {self.task_path})
            self.assertIn("APBRA-108 implementation branch cannot change governance registration files", errors)

    def test_scope_mutations_fail_even_with_recomputed_task_digest(self):
        base = [p for p in self.task["allowed_paths"] if p != "apps/web/src/genericPowerBI.ts"]
        mutations = {
            "missing compiler": base,
            "web wildcard": base + ["apps/web/src/**"],
            "additional parser": self.task["allowed_paths"] + ["apps/api/src/apbra_api/evidence.py"],
            "additional bridge": self.task["allowed_paths"] + ["apps/web/scripts/generation-bridge.ts"],
            "additional validator": self.task["allowed_paths"] + ["apps/web/src/archive.ts"],
            "duplicate": self.task["allowed_paths"] + ["apps/web/src/genericPowerBI.ts"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for label, paths in mutations.items():
                with self.subTest(label=label):
                    changed = copy.deepcopy(self.task)
                    changed["allowed_paths"] = paths
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "CANDIDATE_SOURCE_SAFETY_TASK_SHA256", digest(changed)):
                        errors = self.check(root, {"apps/web/src/genericPowerBI.ts"})
                    self.assertTrue(errors)
                    self.assertTrue(any("scope" in error.lower() or "unique" in error.lower() for error in errors), errors)
            (root / self.task_path).write_text(json.dumps(self.task))

    def test_safety_and_review_gate_mutations_fail_even_with_recomputed_task_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for section, needle in (
                ("requirements", "four unrelated renamed synthetic domains"),
                ("acceptance_criteria", "No Power BI Desktop PASS"),
                ("verification_required", "genuinely separate independent exact-head review"),
                ("dependencies", "Haseeb manual merge"),
            ):
                with self.subTest(section=section):
                    changed = copy.deepcopy(self.task)
                    changed[section] = [entry.replace(needle, "WEAKENED") for entry in changed[section]]
                    self.assertNotEqual(changed[section], self.task[section])
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "CANDIDATE_SOURCE_SAFETY_TASK_SHA256", digest(changed)):
                        errors = self.check(root, {"apps/web/src/genericPowerBI.ts"})
                    self.assertIn("APBRA-108 safety/review gate differs: " + section, errors)
            (root / self.task_path).write_text(json.dumps(self.task))

    def test_source_provenance_mutation_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            source = copy.deepcopy(self.sources)
            row = next(x for x in source["sources"] if x["id"] == self.task["source_ids"][0])
            row["version"] += 1
            (root / self.source_path).write_text(json.dumps(source))
            errors = self.check(root, c.CANDIDATE_SOURCE_SAFETY_REGISTRATION_PATHS,
                                c.CANDIDATE_SOURCE_SAFETY_REGISTRATION_BRANCH)
            self.assertTrue(any("APBRA-108 source" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
