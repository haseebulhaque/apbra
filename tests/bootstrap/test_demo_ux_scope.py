"""Exact APBRA-160 demo UX registration and implementation authority."""

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
SPEC = importlib.util.spec_from_file_location("bootstrap_apbra160_demo_ux", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class DemoUXScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-160-demo-ux.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.sources = json.loads((ROOT / "docs/source-register.json").read_text())

    def copy_repository(self, root):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.DEMO_UX_PATHS)
        names.update(c.DEMO_UX_REGISTRATION_PATHS)
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
            active_branch=branch or c.DEMO_UX_BRANCH,
            changed_paths=set(paths),
        )[0]

    def test_exact_seventeen_paths_sources_and_hashes(self):
        expected = {
            "apps/api/src/apbra_api/api.py", "apps/api/src/apbra_api/tenant_settings.py",
            "apps/api/tests/test_tenant_settings.py",
            "apps/web/src/EnterpriseApp.tsx", "apps/web/src/privateCases.tsx",
            "apps/web/src/api.ts", "apps/web/src/api.test.ts",
            "apps/web/src/privateCases.test.tsx", "apps/web/src/durableConversation.tsx",
            "apps/web/src/durableConversation.test.tsx", "apps/web/src/durableGeneration.tsx",
            "apps/web/src/durableGeneration.test.tsx", "apps/web/src/style.css",
            "apps/web/e2e/private-case.spec.ts", "apps/web/e2e/tenant-settings.spec.ts",
            "apps/web/e2e/durable-conversation.spec.ts", "apps/web/e2e/protected-generation.spec.ts",
        }
        self.assertEqual(c.DEMO_UX_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        self.assertEqual(len(self.task["allowed_paths"]), 17)
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        self.assertEqual(self.task["branch"], c.DEMO_UX_BRANCH)
        self.assertEqual(self.task["base_commit"], "6ad7ee7e2d6a16fb71cc8f05ebf35f3affaf49a7")
        self.assertEqual(digest(self.task), c.DEMO_UX_TASK_SHA256)
        self.assertEqual(len(c.DEMO_UX_REGISTRATION_PATHS), 3)
        self.assertTrue(expected.isdisjoint(c.DEMO_UX_REGISTRATION_PATHS))
        self.assertEqual(self.task["source_ids"], [row[0] for row in c.DEMO_UX_SOURCES])
        for source_id, page, version, expected_hash in c.DEMO_UX_SOURCES:
            rows = [row for row in self.sources["sources"] if row["id"] == source_id]
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]["content_id"], rows[0]["version"], rows[0]["status"]),
                             (page, version, "ACCEPTED"))
            self.assertEqual(digest(rows[0]), expected_hash)
        for section, expected_hash in c.DEMO_UX_GATE_SHA256.items():
            self.assertEqual(digest(self.task[section]), expected_hash)

    def test_registration_and_implementation_remain_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, c.DEMO_UX_REGISTRATION_PATHS,
                                        c.DEMO_UX_REGISTRATION_BRANCH), [])
            self.assertEqual(self.check(root, c.DEMO_UX_PATHS), [])
            for omitted in c.DEMO_UX_REGISTRATION_PATHS:
                errors = self.check(root, c.DEMO_UX_REGISTRATION_PATHS - {omitted},
                                    c.DEMO_UX_REGISTRATION_BRANCH)
                self.assertIn("APBRA-160 demo UX registration must change exactly three governance files", errors)
            for extra in ("apps/web/src/privateCases.tsx", "docs/source-register.json",
                          ".github/workflows/bootstrap.yml"):
                errors = self.check(root, c.DEMO_UX_REGISTRATION_PATHS | {extra},
                                    c.DEMO_UX_REGISTRATION_BRANCH)
                self.assertTrue(errors)
            errors = self.check(root, {self.task_path})
            self.assertIn("APBRA-160 demo UX implementation cannot change governance files", errors)

    def test_member_branding_exception_is_finite_and_read_only(self):
        requirement = self.task["requirements"][-1]
        for boundary in (
            "authenticated GET /api/workspace/branding",
            "exactly version, primary and accent",
            "server-derived actor.company_id",
            "no caller-supplied company selector",
            "actors with authenticated active APBRA membership (COMPANY_OWNER, COMPANY_ADMIN, MEMBER or EXPERT)",
            "existing admin settings and every write permission remain unchanged",
        ):
            self.assertIn(boundary, requirement)
        self.assertIn("inactive Expert denial", self.task["verification_required"][-1])
        self.assertIn("before projection product edits", self.task["verification_required"][-1])
        self.assertIn("no combined governance/product diff", self.task["dependencies"][-1])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, c.DEMO_UX_REGISTRATION_PATHS,
                                        c.DEMO_UX_REGISTRATION_BRANCH), [])

    def test_member_branding_access_and_response_mutations_fail_closed(self):
        mutations = (
            ("requirements", "exactly version, primary and accent", "all tenant settings"),
            ("requirements", "server-derived actor.company_id", "client company_id"),
            ("requirements", "no caller-supplied company selector", "accept caller-supplied company selector"),
            ("requirements", "actors with authenticated active APBRA membership (COMPANY_OWNER, COMPANY_ADMIN, MEMBER or EXPERT)", "any authenticated identity"),
            ("requirements", "every write permission remain unchanged", "members can write settings"),
            ("acceptance_criteria", "missing or inactive membership", "only missing membership"),
            ("acceptance_criteria", "No other settings or credentials are returned", "Include provider and credential settings"),
            ("acceptance_criteria", "stale responses cannot apply a previous tenant palette", "stale responses may apply any palette"),
            ("verification_required", "before projection product edits", "after projection product edits"),
            ("out_of_scope", "three-field read-only projection", "unrestricted settings endpoint"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for section, before, after in mutations:
                with self.subTest(section=section, boundary=before):
                    changed = copy.deepcopy(self.task)
                    changed[section] = [entry.replace(before, after) for entry in changed[section]]
                    self.assertNotEqual(changed[section], self.task[section])
                    (root / self.task_path).write_text(json.dumps(changed))
                    # Rehashing the overall document cannot authorize weakened gates.
                    with patch.object(c, "DEMO_UX_TASK_SHA256", digest(changed)):
                        errors = self.check(root, {"apps/api/src/apbra_api/api.py"})
                    self.assertIn("APBRA-160 demo UX safety/review gate differs: " + section, errors)

    def test_scope_mutations_fail_even_with_recomputed_task_digest(self):
        mutations = [
            [p for p in self.task["allowed_paths"] if p != "apps/web/e2e/tenant-settings.spec.ts"],
            [p for p in self.task["allowed_paths"] if p != "apps/api/src/apbra_api/tenant_settings.py"],
            [p for p in self.task["allowed_paths"] if p != "apps/api/tests/test_tenant_settings.py"],
            self.task["allowed_paths"] + ["apps/api/src/apbra_api/application.py"],
            self.task["allowed_paths"] + ["apps/api/tests/test_authentication.py"],
            self.task["allowed_paths"] + ["apps/web/src/EnterpriseUI.tsx"],
            self.task["allowed_paths"] + ["apps/web/package.json"],
            self.task["allowed_paths"] + [".github/workflows/bootstrap.yml"],
            self.task["allowed_paths"] + ["apps/web/src/another.tsx"],
            self.task["allowed_paths"] + ["apps/web/src/**"],
            self.task["allowed_paths"] + ["apps/api/**"],
            self.task["allowed_paths"] + ["apps/web/e2e/tenant-settings.spec.ts"],
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for paths in mutations:
                with self.subTest(paths=paths):
                    changed = copy.deepcopy(self.task)
                    changed["allowed_paths"] = paths
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "DEMO_UX_TASK_SHA256", digest(changed)):
                        self.assertTrue(self.check(root, {"apps/web/src/privateCases.tsx"}))

    def test_security_and_review_gates_fail_with_recomputed_task_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for section, needle in (
                ("requirements", "A$10 total cap"),
                ("requirements", "does not resubmit unrelated AI"),
                ("adrs", "expected_version"),
                ("acceptance_criteria", "another unsaved section"),
                ("acceptance_criteria", "rejects unknown or cross-section fields"),
                ("verification_required", "genuinely separate independent exact-head"),
                ("dependencies", "No paid retry"),
            ):
                with self.subTest(section=section):
                    changed = copy.deepcopy(self.task)
                    changed[section] = [entry.replace(needle, "WEAKENED") for entry in changed[section]]
                    self.assertNotEqual(changed[section], self.task[section])
                    (root / self.task_path).write_text(json.dumps(changed))
                    with patch.object(c, "DEMO_UX_TASK_SHA256", digest(changed)):
                        errors = self.check(root, {"apps/web/src/privateCases.tsx"})
                    self.assertIn("APBRA-160 demo UX safety/review gate differs: " + section, errors)
            (root / self.task_path).write_text(json.dumps(self.task))

    def test_source_binding_and_history_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            changed = copy.deepcopy(self.task)
            changed["source_ids"] = changed["source_ids"][:-1]
            (root / self.task_path).write_text(json.dumps(changed))
            with patch.object(c, "DEMO_UX_TASK_SHA256", digest(changed)):
                errors = self.check(root, c.DEMO_UX_REGISTRATION_PATHS,
                                    c.DEMO_UX_REGISTRATION_BRANCH)
            self.assertIn("APBRA-160 demo UX requires exact accepted sources", errors)
            (root / self.task_path).write_text(json.dumps(self.task))
            source = json.loads((root / "docs/source-register.json").read_text())
            source["sources"][0]["acceptance"] = "mutated historical provenance"
            (root / "docs/source-register.json").write_text(json.dumps(source))
            self.assertTrue(self.check(root, c.DEMO_UX_REGISTRATION_PATHS,
                                       c.DEMO_UX_REGISTRATION_BRANCH))


if __name__ == "__main__":
    unittest.main()
