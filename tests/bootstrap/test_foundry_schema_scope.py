"""Exact APBRA-160 Foundry schema registration and implementation authority."""

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
SPEC = importlib.util.spec_from_file_location("bootstrap_apbra160_foundry", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class FoundrySchemaScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-160-foundry-structured-output.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.sources = json.loads((ROOT / "docs/source-register.json").read_text())

    def copy_repository(self, root):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.FOUNDRY_SCHEMA_PATHS)
        names.update(c.FOUNDRY_SCHEMA_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-160 fixture\n")

    def check(self, root, paths, branch=None):
        return c.check(
            root,
            active_task_id="APBRA-160",
            active_branch=branch or c.FOUNDRY_SCHEMA_BRANCH,
            changed_paths=set(paths),
        )[0]

    def test_exact_scope_sources_and_gates(self):
        expected = {
            'apps/api/src/apbra_api/application.py',
            'apps/api/src/apbra_api/model_provider.py',
            'apps/api/src/apbra_api/generation.py',
            'apps/api/tests/test_conversations.py',
            'apps/api/tests/test_model_provider.py',
            'apps/api/tests/test_generation.py',
            'apps/api/tests/test_semantic_bridge.py',
            'apps/web/scripts/semantic-bridge.ts',
            'apps/web/scripts/generation-bridge.ts',
            'apps/web/src/clarification.ts',
            'apps/web/src/clarification.test.ts',
            'apps/web/src/confirmedRequirements.ts',
            'apps/web/src/confirmedRequirements.test.ts',
            'apps/web/src/foundry.ts',
            'apps/web/src/foundry.test.ts',
            'apps/web/src/guardrail.ts',
            'apps/web/src/guardrail.test.ts',
            'apps/web/src/genericPowerBI.test.ts',
            'apps/web/src/durableConversation.tsx',
            'apps/web/src/durableConversation.test.tsx',
            'apps/web/src/durableGeneration.tsx',
            'apps/web/src/durableGeneration.test.tsx',
            'apps/web/src/deploymentGuide.ts',
            'apps/web/src/deploymentGuide.test.ts',
            'apps/web/e2e/durable-conversation.spec.ts',
            'apps/web/e2e/protected-generation.spec.ts',
        }
        self.assertEqual(c.FOUNDRY_SCHEMA_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertEqual(len(self.task["allowed_paths"]), 26)
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        self.assertEqual(self.task["branch"], c.FOUNDRY_SCHEMA_BRANCH)
        self.assertEqual(self.task["base_commit"], "efb11f5004961ceff9318d6d6f12f88ecd7b2c4a")
        self.assertEqual(digest(self.task), c.FOUNDRY_SCHEMA_TASK_SHA256)
        self.assertEqual(len(c.FOUNDRY_SCHEMA_REGISTRATION_PATHS), 5)
        self.assertTrue(expected.isdisjoint(c.FOUNDRY_SCHEMA_REGISTRATION_PATHS))
        self.assertEqual(self.task["source_ids"], [row[0] for row in c.FOUNDRY_SCHEMA_SOURCES])
        for source_id, page, version, expected_hash in c.FOUNDRY_SCHEMA_SOURCES:
            rows = [row for row in self.sources["sources"] if row["id"] == source_id]
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]["content_id"], rows[0]["version"], rows[0]["status"]),
                             (page, version, "ACCEPTED"))
            self.assertEqual(digest(rows[0]), expected_hash)
        for section, expected_hash in c.FOUNDRY_SCHEMA_GATE_SHA256.items():
            self.assertEqual(digest(self.task[section]), expected_hash)

    def test_registration_and_implementation_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, c.FOUNDRY_SCHEMA_REGISTRATION_PATHS,
                                        c.FOUNDRY_SCHEMA_REGISTRATION_BRANCH), [])
            self.assertEqual(self.check(root, c.FOUNDRY_SCHEMA_PATHS), [])
            for omitted in c.FOUNDRY_SCHEMA_REGISTRATION_PATHS:
                errors = self.check(root, c.FOUNDRY_SCHEMA_REGISTRATION_PATHS - {omitted},
                                    c.FOUNDRY_SCHEMA_REGISTRATION_BRANCH)
                self.assertIn("APBRA-160 Foundry registration must change exactly five governance files", errors)
            for extra in ("apps/api/src/apbra_api/model_provider.py", "docs/decisions/implementation-baseline.md"):
                errors = self.check(root, c.FOUNDRY_SCHEMA_REGISTRATION_PATHS | {extra},
                                    c.FOUNDRY_SCHEMA_REGISTRATION_BRANCH)
                self.assertTrue(errors)
            errors = self.check(root, {self.task_path})
            self.assertIn("APBRA-160 Foundry implementation cannot change governance files", errors)

    def test_scope_mutations_fail_with_recomputed_task_digest(self):
        mutations = [[p for p in self.task["allowed_paths"] if p != omitted]
                     for omitted in self.task["allowed_paths"]]
        mutations += [self.task["allowed_paths"] + [duplicate]
                      for duplicate in self.task["allowed_paths"]]
        mutations += [
            [p for p in self.task["allowed_paths"] if p != "apps/api/src/apbra_api/model_provider.py"],
            self.task["allowed_paths"] + ["apps/api/src/apbra_api/persistence.py"],
            self.task["allowed_paths"] + ["apps/api/alembic/versions/new.py"],
            self.task["allowed_paths"] + ["apps/api/src/**"],
            self.task["allowed_paths"] + ["apps/web/src/genericPowerBI.ts"],
            self.task["allowed_paths"] + ["apps/api/src/apbra_api/domain.py"],
            self.task["allowed_paths"] + ["apps/web/src/rag.ts"],
            self.task["allowed_paths"] + ["apps/web/package.json"],
            self.task["allowed_paths"] + [".github/workflows/apbra.yml"],
            [p for p in self.task["allowed_paths"] if p != "apps/web/scripts/semantic-bridge.ts"],
            self.task["allowed_paths"] + ["apps/api/src/apbra_api/model_provider.py"],
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for paths in mutations:
                with self.subTest(paths=paths):
                    changed = copy.deepcopy(self.task)
                    changed["allowed_paths"] = paths
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "FOUNDRY_SCHEMA_TASK_SHA256", digest(changed)):
                        errors = self.check(root, {"apps/api/src/apbra_api/model_provider.py"})
                    self.assertTrue(errors)
            (root / self.task_path).write_text(json.dumps(self.task))

    def test_current_apbra160_source_binding_cannot_revert_to_hosting_sources(self):
        self.assertEqual(self.task["source_ids"], [
            "apbra-160-editable-first-draft-direction",
            "apbra-160-editable-first-draft-delivery",
        ])
        self.assertEqual([row[2] for row in c.FOUNDRY_SCHEMA_SOURCES], [28, 9])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for source_ids in (
                ["apbra-173b-preview-direction", "apbra-173b-mvp-scope", "apbra-173b-traceability"],
                ["apbra-160-current-six-stage-direction"],
                self.task["source_ids"] + ["apbra-173b-preview-direction"],
            ):
                with self.subTest(source_ids=source_ids):
                    changed = copy.deepcopy(self.task)
                    changed["source_ids"] = source_ids
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "FOUNDRY_SCHEMA_TASK_SHA256", digest(changed)):
                        errors = self.check(root, c.FOUNDRY_SCHEMA_REGISTRATION_PATHS,
                                            c.FOUNDRY_SCHEMA_REGISTRATION_BRANCH)
                    self.assertIn("APBRA-160 Foundry requires exact accepted sources", errors)

    def test_safety_gate_mutations_fail_with_recomputed_task_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for section, needle in (
                ("requirements", "Paid calls remain prohibited"),
                ("requirements", "across Understanding/readiness, confirmation materialization and generation"),
                ("requirements", "exact visible interpretation"),
                ("requirements", "private-resource isolation"),
                ("adrs", "The qualified LLM owns interpretation"),
                ("acceptance_criteria", "protected editable artifact download"),
                ("acceptance_criteria", "Malformed protocol/shape"),
                ("verification_required", "genuinely separate independent exact-head review"),
                ("dependencies", "Haseeb manual merge"),
                ("out_of_scope", "Paid provider calls"),
            ):
                with self.subTest(section=section):
                    changed = copy.deepcopy(self.task)
                    changed[section] = [entry.replace(needle, "WEAKENED") for entry in changed[section]]
                    self.assertNotEqual(changed[section], self.task[section])
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "FOUNDRY_SCHEMA_TASK_SHA256", digest(changed)):
                        errors = self.check(root, {"apps/api/src/apbra_api/model_provider.py"})
                    self.assertIn("APBRA-160 Foundry safety/review gate differs: " + section, errors)
            (root / self.task_path).write_text(json.dumps(self.task))


if __name__ == "__main__":
    unittest.main()
