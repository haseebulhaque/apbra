"""APBRA-175 exact documentation authority and separate governance registration."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_apbra175", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class DeploymentPortabilityEntitlementDocsScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-175-deployment-portability-entitlement-docs.json"
        self.source_path = "docs/source-register.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.sources = json.loads((ROOT / self.source_path).read_text())

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_PATHS)
        names.update(c.DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-175 fixture\n")

    def check(self, root: Path, changed_paths, branch=None):
        return c.check(
            root,
            active_task_id="APBRA-175",
            active_branch=branch or self.task["branch"],
            changed_paths=set(changed_paths),
        )[0]

    def test_exact_task_and_source_bindings(self):
        expected_docs = {
            "README.md", "ARCHITECTURE.md", "REQUIREMENTS.md", "AI-RAG-SPEC.md",
            "POWERBI-GENERATION-SPEC.md", "MVP-ACCEPTANCE-CRITERIA.md", "DATA-MODEL.md",
            "apps/web/README.md", "docs/engineering/codex-handoff.md",
        }
        expected_registration = {
            "docs/source-register.json",
            "tasks/APBRA-175-deployment-portability-entitlement-docs.json",
            "scripts/check_bootstrap.py",
            "tests/bootstrap/test_deployment_portability_entitlement_docs_scope.py",
            "tests/bootstrap/test_invited_private_case_foundation_scope.py",
        }
        self.assertEqual(c.DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_PATHS, expected_docs)
        self.assertEqual(set(self.task["allowed_paths"]), expected_docs)
        self.assertEqual(c.DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_PATHS, expected_registration)
        self.assertTrue(expected_docs.isdisjoint(expected_registration))
        self.assertNotIn("apps/api/README.md", expected_docs)
        self.assertTrue(all("*" not in path for path in expected_docs))
        self.assertEqual(self.task["base_commit"], "acf1473ea0a05c5f203d85ed55fdc695515880c8")
        self.assertEqual(self.task["source_ids"], [
            c.DEPLOYMENT_PORTABILITY_SOURCE_ID, c.ENTITLEMENT_ARCHITECTURE_SOURCE_ID,
        ])
        digest = lambda record: hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(digest(self.task), c.DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_TASK_SHA256)
        source_map = {source["id"]: source for source in self.sources["sources"]}
        for source_id, content_id, expected_digest in (
            (c.DEPLOYMENT_PORTABILITY_SOURCE_ID, "9568258", c.DEPLOYMENT_PORTABILITY_SOURCE_SHA256),
            (c.ENTITLEMENT_ARCHITECTURE_SOURCE_ID, "9535525", c.ENTITLEMENT_ARCHITECTURE_SOURCE_SHA256),
        ):
            with self.subTest(source_id=source_id):
                source = source_map[source_id]
                self.assertEqual((source["content_id"], source["version"], source["status"]), (content_id, 1, "ACCEPTED"))
                self.assertEqual(digest(source), expected_digest)
        source_ids = [source["id"] for source in self.sources["sources"]]
        self.assertEqual(source_ids.count(self.task["source_ids"][0]), 1)
        start = source_ids.index(self.task["source_ids"][0])
        self.assertEqual(source_ids[start:start + len(self.task["source_ids"])], self.task["source_ids"])

    def test_documentation_and_registration_are_separately_admitted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in sorted(c.DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_PATHS):
                with self.subTest(path=path):
                    self.assertEqual(self.check(root, {path}), [])
            self.assertEqual(self.check(
                root,
                c.DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_PATHS,
                branch=c.DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_BRANCH,
            ), [])

    def test_registration_requires_exact_five_and_cannot_mix_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            registration = c.DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_PATHS
            errors = self.check(root, registration - {self.task_path},
                                branch=c.DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_BRANCH)
            self.assertIn("APBRA-175 registration must change exactly its five governance files", errors)
            errors = self.check(root, registration | {"README.md"},
                                branch=c.DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_BRANCH)
            self.assertIn("APBRA-175 registration and documentation changes must remain separate", errors)
            self.assertIn("File outside active task scope: README.md", errors)
            errors = self.check(root, {"README.md", self.task_path})
            self.assertIn("APBRA-175 documentation branch cannot change governance registration files", errors)

    def test_extra_paths_and_wrong_registration_branch_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in ("apps/api/README.md", "apps/web/src/main.tsx", "docs/decisions/implementation-baseline.md",
                         ".github/workflows/bootstrap.yml", "apps/web/package-lock.json", "docs/other.md"):
                with self.subTest(path=path):
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        target.write_text("outside scope\n")
                    self.assertIn("File outside active task scope: " + path, self.check(root, {path}))
            errors = self.check(root, c.DEPLOYMENT_PORTABILITY_ENTITLEMENT_DOCS_REGISTRATION_PATHS,
                                branch="agent/APBRA-DEVOPS/APBRA-175-wrong-registration")
            self.assertTrue(any("Active branch conflicts with task authority" in error for error in errors), errors)

    def test_task_and_source_mutations_fail_closed(self):
        mutations = (
            ("base_commit", "0" * 40, "Stale APBRA-175 registration base"),
            ("branch", "agent/APBRA-DEVOPS/APBRA-175-wrong", "Unexpected APBRA-175 documentation branch"),
            ("allowed_paths", ["docs/**"], "Unexpected APBRA-175 documentation scope"),
            ("owner_acceptance", "PENDING", "APBRA-175 requires issued documentation-only acceptance"),
            ("source_ids", [c.DEPLOYMENT_PORTABILITY_SOURCE_ID], "APBRA-175 requires its two accepted sources"),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                task = copy.deepcopy(self.task)
                task[field] = value
                (root / self.task_path).write_text(json.dumps(task))
                errors = self.check(root, {"README.md"})
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn("File outside active task scope: README.md", errors)
        for source_id in self.task["source_ids"]:
            with self.subTest(source_id=source_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                sources = copy.deepcopy(self.sources)
                source = next(item for item in sources["sources"] if item["id"] == source_id)
                source["acceptance"] += " altered"
                (root / self.source_path).write_text(json.dumps(sources))
                errors = self.check(root, {"README.md"})
                self.assertTrue(any("APBRA-175 source differs from accepted provenance" in error for error in errors), errors)
                self.assertIn("File outside active task scope: README.md", errors)

    def test_contract_prohibits_runtime_and_commercial_implementation(self):
        text = " ".join(self.task["requirements"] + self.task["adrs"] +
                        self.task["acceptance_criteria"] + self.task["out_of_scope"] +
                        self.task["verification_required"] + self.task["dependencies"])
        for required in (
            "customer data plane", "deployment_id", "tenant_id", "NO HARDCODING",
            "plan-name", "ARD", "prices", "provider", "cloud resource",
            "hosted CI", "independent", "manual merge", "separate",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
