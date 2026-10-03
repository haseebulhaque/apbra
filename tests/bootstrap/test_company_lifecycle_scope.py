"""APBRA-151 exact company-lifecycle authority and separate registration."""

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
SPEC = importlib.util.spec_from_file_location("bootstrap_apbra151", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class CompanyLifecycleScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-151-company-lifecycle.json"
        self.source_path = "docs/source-register.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.sources = json.loads((ROOT / self.source_path).read_text())

    def copy_repository(self, root):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.COMPANY_LIFECYCLE_PATHS)
        names.update(c.COMPANY_LIFECYCLE_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-151 fixture\n")

    def check(self, root, paths, branch=None):
        return c.check(
            root,
            active_task_id="APBRA-151",
            active_branch=branch or c.COMPANY_LIFECYCLE_BRANCH,
            changed_paths=set(paths),
        )[0]

    def test_exact_task_and_seven_accepted_sources(self):
        self.assertEqual(len(c.COMPANY_LIFECYCLE_PATHS), 19)
        self.assertEqual(len(c.COMPANY_LIFECYCLE_REGISTRATION_PATHS), 8)
        self.assertEqual(set(self.task["allowed_paths"]), c.COMPANY_LIFECYCLE_PATHS)
        self.assertTrue(c.COMPANY_LIFECYCLE_PATHS.isdisjoint(c.COMPANY_LIFECYCLE_REGISTRATION_PATHS))
        self.assertTrue(all("*" not in path for path in self.task["allowed_paths"]))
        self.assertEqual(self.task["base_commit"], "9e90bcc3c716dc2d24bb58192096d2429d531043")
        self.assertEqual(self.task["branch"], c.COMPANY_LIFECYCLE_BRANCH)
        self.assertEqual(digest(self.task), c.COMPANY_LIFECYCLE_TASK_SHA256)
        self.assertEqual(self.task["source_ids"], [row[0] for row in c.COMPANY_LIFECYCLE_SOURCES])
        self.assertEqual(
            [source["id"] for source in self.sources["sources"][-7:]],
            self.task["source_ids"],
        )
        source_map = {source["id"]: source for source in self.sources["sources"]}
        for source_id, content_id, version, expected in c.COMPANY_LIFECYCLE_SOURCES:
            with self.subTest(source_id=source_id):
                source = source_map[source_id]
                self.assertEqual(
                    (source["content_id"], source["version"], source["status"]),
                    (content_id, version, "ACCEPTED"),
                )
                self.assertEqual(digest(source), expected)

    def test_registration_and_later_implementation_remain_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(
                self.check(
                    root,
                    c.COMPANY_LIFECYCLE_REGISTRATION_PATHS,
                    c.COMPANY_LIFECYCLE_REGISTRATION_BRANCH,
                ),
                [],
            )
            self.assertEqual(self.check(root, c.COMPANY_LIFECYCLE_PATHS), [])
            errors = self.check(
                root,
                c.COMPANY_LIFECYCLE_REGISTRATION_PATHS - {self.task_path},
                c.COMPANY_LIFECYCLE_REGISTRATION_BRANCH,
            )
            self.assertIn(
                "APBRA-151 registration must change exactly its eight governance files", errors
            )
            errors = self.check(
                root,
                c.COMPANY_LIFECYCLE_REGISTRATION_PATHS | {"apps/api/src/apbra_api/api.py"},
                c.COMPANY_LIFECYCLE_REGISTRATION_BRANCH,
            )
            self.assertIn(
                "APBRA-151 registration and implementation changes must remain separate", errors
            )
            self.assertIn("File outside active task scope: apps/api/src/apbra_api/api.py", errors)
            errors = self.check(root, {self.task_path})
            self.assertIn(
                "APBRA-151 implementation branch cannot change governance registration files", errors
            )

    def test_initial_settings_gate_is_explicit_in_each_contract_section(self):
        required_fragments = {
            "requirements": (
                "Haseeb must first record either",
                "tenant_settings.seed_settings() is local/development/test bootstrap only",
                "company creation must fail closed",
            ),
            "acceptance_criteria": (
                "only Haseeb's accepted validated onboarding-settings template/policy",
                "roll back company, owner membership, settings, idempotency and audit state",
                "Development/test seeds must not become customer policy",
            ),
            "dependencies": (
                "Registration may be reviewed and merged",
                "product implementation must not select, synthesize or persist",
                "must escalate the owner decision",
            ),
            "escalate_when": (
                "product implementation must stop before enabled company creation",
                "must not copy seed_settings()",
                "leave partial company state",
            ),
        }
        self.assertEqual(set(required_fragments), set(c.COMPANY_LIFECYCLE_INITIAL_SETTINGS_GATE_SHA256))
        for field, fragments in required_fragments.items():
            with self.subTest(field=field):
                matches = [item for item in self.task[field] if all(fragment in item for fragment in fragments)]
                self.assertEqual(len(matches), 1)
                self.assertEqual(
                    hashlib.sha256(matches[0].encode()).hexdigest(),
                    c.COMPANY_LIFECYCLE_INITIAL_SETTINGS_GATE_SHA256[field],
                )

    def test_removed_or_weakened_initial_settings_gate_fails_even_if_task_rehashed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for field, gate_sha in c.COMPANY_LIFECYCLE_INITIAL_SETTINGS_GATE_SHA256.items():
                original = next(
                    item for item in self.task[field]
                    if hashlib.sha256(item.encode()).hexdigest() == gate_sha
                )
                for mutation in ("remove", "weaken"):
                    with self.subTest(field=field, mutation=mutation):
                        changed = copy.deepcopy(self.task)
                        if mutation == "remove":
                            changed[field].remove(original)
                        else:
                            changed[field][changed[field].index(original)] = original.replace("must", "may", 1)
                        (root / self.task_path).write_text(json.dumps(changed))
                        with patch.object(c, "COMPANY_LIFECYCLE_TASK_SHA256", digest(changed)):
                            errors = self.check(root, {"apps/api/src/apbra_api/tenant_settings.py"})
                        self.assertIn(
                            "APBRA-151 initial Tenant Settings gate missing or weakened: " + field,
                            errors,
                        )
                        self.assertIn(
                            "File outside active task scope: apps/api/src/apbra_api/tenant_settings.py",
                            errors,
                        )
            (root / self.task_path).write_text(json.dumps(self.task))

    def test_unregistered_paths_and_wrong_branch_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in (
                "infrastructure/azure/main.bicep",
                "apps/api/requirements.txt",
                "apps/web/package-lock.json",
                ".github/workflows/bootstrap.yml",
                "apps/api/src/apbra_api/oidc_adapter.py",
                "apps/api/src/apbra_api/authorization.py",
                "apps/web/src/App.tsx",
            ):
                with self.subTest(path=path):
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        target.write_text("outside scope\n")
                    self.assertIn("File outside active task scope: " + path, self.check(root, {path}))
            errors = self.check(
                root,
                c.COMPANY_LIFECYCLE_REGISTRATION_PATHS,
                "agent/APBRA-DEVOPS/APBRA-151-wrong-registration",
            )
            self.assertTrue(any("Active branch conflicts with task authority" in e for e in errors), errors)

    def test_task_and_source_mutations_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for field, value, expected in (
                ("base_commit", "0" * 40, "Stale APBRA-151 registration base"),
                ("branch", "agent/APBRA-DEVOPS/APBRA-151-wrong", "Unexpected APBRA-151 implementation branch"),
                ("allowed_paths", ["apps/api/**"], "Unexpected APBRA-151 implementation scope"),
                ("allowed_paths", self.task["allowed_paths"] + ["apps/api/src/apbra_api/entra_hidden.py"],
                 "Unexpected APBRA-151 implementation scope"),
                ("source_ids", ["implementation-contract"], "APBRA-151 requires its seven accepted sources"),
                ("owner_acceptance", "PENDING", "APBRA-151 requires issued implementation acceptance"),
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
                    self.assertTrue(
                        any("APBRA-151 source differs from accepted provenance" in e for e in errors),
                        errors,
                    )
                    self.assertIn("File outside active task scope: apps/api/src/apbra_api/api.py", errors)
                    (root / self.source_path).write_text(json.dumps(self.sources))


if __name__ == "__main__":
    unittest.main()
