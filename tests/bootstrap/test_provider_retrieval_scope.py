"""Finite offline Responses registration, history and fail-closed scope boundaries."""
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
SPEC = importlib.util.spec_from_file_location("bootstrap_provider_retrieval", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
TASK = "tasks/APBRA-160-provider-retrieval.json"
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

EXPECTED_PATHS = {'apps/web/src/api.ts', 'apps/api/src/apbra_api/application.py', 'apps/web/src/durableConversation.test.tsx', 'apps/web/src/privateCases.test.tsx', 'apps/web/src/foundry.test.ts', 'apps/web/src/durableConversation.tsx', 'apps/web/src/api.test.ts', 'apps/web/e2e/tenant-settings.spec.ts', 'apps/web/scripts/semantic-bridge.ts', 'apps/web/e2e/protected-generation.spec.ts', 'apps/api/tests/test_model_provider.py', 'apps/web/src/foundry.ts', 'apps/web/scripts/generation-bridge.ts', 'apps/api/src/apbra_api/config.py', 'apps/web/e2e/durable-conversation.spec.ts', 'apps/api/src/apbra_api/generation.py', 'apps/api/tests/test_tenant_settings.py', 'apps/web/src/deploymentGuide.ts', 'apps/api/tests/test_generation.py', 'apps/api/src/apbra_api/tenant_settings.py', 'apps/web/src/durableGeneration.tsx', 'apps/api/src/apbra_api/api.py', 'apps/api/src/apbra_api/model_provider.py', 'apps/api/tests/test_conversations.py', 'apps/api/tests/test_semantic_bridge.py', 'apps/web/src/deploymentGuide.test.ts', 'apps/api/tests/test_api.py', 'apps/web/src/EnterpriseApp.tsx', 'apps/web/src/durableGeneration.test.tsx'}

class ProviderRetrievalScopeTests(unittest.TestCase):
    def setUp(self):
        self.task = json.loads((ROOT / TASK).read_text())
        self.sources = json.loads((ROOT / "docs/source-register.json").read_text())

    def copy_repository(self, root):
        names = {f.relative_to(ROOT).as_posix() for f in c.repo_files(ROOT)}
        names.update(c.PROVIDER_RETRIEVAL_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.is_file():
                shutil.copyfile(source, target)

    def check(self, root, paths, branch=None):
        return c.check(root, active_task_id="APBRA-160",
                       active_branch=branch or c.PROVIDER_RETRIEVAL_BRANCH,
                       changed_paths=set(paths))[0]

    def test_exact_literal_paths_and_bound_gates(self):
        self.assertEqual(c.PROVIDER_RETRIEVAL_PATHS, EXPECTED_PATHS)
        self.assertEqual(set(self.task["allowed_paths"]), EXPECTED_PATHS)
        self.assertEqual(len(self.task["allowed_paths"]), 29)
        self.assertTrue(all("*" not in p for p in self.task["allowed_paths"]))
        self.assertEqual(c.PROVIDER_RETRIEVAL_REGISTRATION_PATHS,
                         {TASK, "scripts/check_bootstrap.py", "tests/bootstrap/test_provider_retrieval_scope.py"})
        self.assertEqual(self.task["base_commit"], "e3f782535e41bef1034222227ef706e1cf0bfac1")
        self.assertEqual(self.task["branch"], c.PROVIDER_RETRIEVAL_BRANCH)
        self.assertEqual(digest(self.task), c.PROVIDER_RETRIEVAL_TASK_SHA256)
        for section, expected in c.PROVIDER_RETRIEVAL_GATE_SHA256.items():
            self.assertEqual(digest(self.task[section]), expected)

    def test_registration_and_product_stages_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, c.PROVIDER_RETRIEVAL_REGISTRATION_PATHS,
                                        c.PROVIDER_RETRIEVAL_REGISTRATION_BRANCH), [])
            self.assertEqual(self.check(root, EXPECTED_PATHS), [])
            for omitted in c.PROVIDER_RETRIEVAL_REGISTRATION_PATHS:
                self.assertTrue(self.check(root, c.PROVIDER_RETRIEVAL_REGISTRATION_PATHS - {omitted},
                                           c.PROVIDER_RETRIEVAL_REGISTRATION_BRANCH))
            self.assertTrue(self.check(root, {TASK}))
            self.assertTrue(self.check(root, c.PROVIDER_RETRIEVAL_REGISTRATION_PATHS | {
                "apps/api/src/apbra_api/model_provider.py"}, c.PROVIDER_RETRIEVAL_REGISTRATION_BRANCH))
            self.assertTrue(self.check(root, EXPECTED_PATHS, c.DEMO_UX_BRANCH))

    def test_each_missing_duplicate_and_broadened_path_fails_with_recomputed_digest(self):
        paths = self.task["allowed_paths"]
        mutations = [[p for p in paths if p != omitted] for omitted in paths]
        mutations += [paths + [duplicate] for duplicate in paths]
        mutations += [paths + [extra] for extra in (
            "apps/api/src/**", "apps/api/src/apbra_api/domain.py",
            "apps/api/src/apbra_api/persistence.py", "apps/api/src/apbra_api/tenant_secrets.py",
            "apps/api/pyproject.toml", "apps/api/alembic/versions/new.py",
            "apps/web/src/rag.ts", "apps/web/vite.config.ts", "apps/web/package.json",
            "compose.yaml", ".github/workflows/bootstrap.yml", "infrastructure/identity.tf")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for values in mutations:
                with self.subTest(paths=values):
                    changed = copy.deepcopy(self.task)
                    changed["allowed_paths"] = values
                    (root / TASK).write_text(json.dumps(changed))
                    with patch.object(c, "PROVIDER_RETRIEVAL_TASK_SHA256", digest(changed)):
                        self.assertTrue(self.check(root, {"apps/api/src/apbra_api/model_provider.py"}))

    def test_every_acceptance_and_operation_gate_is_independently_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for section in c.PROVIDER_RETRIEVAL_GATE_SHA256:
                with self.subTest(section=section):
                    changed = copy.deepcopy(self.task)
                    value = changed[section]
                    changed[section] = value + ["Broader authority"] if isinstance(value, list) else "PENDING"
                    (root / TASK).write_text(json.dumps(changed))
                    with patch.object(c, "PROVIDER_RETRIEVAL_TASK_SHA256", digest(changed)):
                        self.assertTrue(self.check(root, c.PROVIDER_RETRIEVAL_REGISTRATION_PATHS,
                                                   c.PROVIDER_RETRIEVAL_REGISTRATION_BRANCH))

    def test_accepted_sources_and_historical_rows_cannot_be_rewritten(self):
        self.assertEqual(digest(self.sources), c.PROVIDER_RETRIEVAL_ALL_SOURCES_SHA256)
        self.assertEqual(self.task["source_ids"], [row[0] for row in c.PROVIDER_RETRIEVAL_SOURCES])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for change in ("source_ids", "source_version", "source_acceptance", "history"):
                with self.subTest(change=change):
                    changed_task = copy.deepcopy(self.task)
                    changed_sources = copy.deepcopy(self.sources)
                    if change == "source_ids":
                        changed_task["source_ids"] = ["apbra-160-current-six-stage-direction"]
                    elif change == "history":
                        changed_sources["sources"][0]["title"] = "Rewritten historical acceptance"
                    else:
                        row = next(row for row in changed_sources["sources"]
                                   if row["id"] == self.task["source_ids"][0])
                        row["version" if change == "source_version" else "status"] = 29 if change == "source_version" else "PROPOSED"
                    (root / TASK).write_text(json.dumps(changed_task))
                    (root / "docs/source-register.json").write_text(json.dumps(changed_sources))
                    with patch.object(c, "PROVIDER_RETRIEVAL_TASK_SHA256", digest(changed_task)):
                        self.assertTrue(self.check(root, c.PROVIDER_RETRIEVAL_REGISTRATION_PATHS,
                                                   c.PROVIDER_RETRIEVAL_REGISTRATION_BRANCH))

    def test_identity_base_and_branch_cannot_be_rebound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for field, value in (("base_commit", "0" * 40), ("task_id", "APBRA-173"),
                                 ("assigned_agent", "APBRA-DEV-BE"),
                                 ("branch", "agent/APBRA-DEVOPS/APBRA-160-unrelated")):
                with self.subTest(field=field):
                    changed = copy.deepcopy(self.task)
                    changed[field] = value
                    (root / TASK).write_text(json.dumps(changed))
                    with patch.object(c, "PROVIDER_RETRIEVAL_TASK_SHA256", digest(changed)):
                        self.assertTrue(self.check(root, c.PROVIDER_RETRIEVAL_REGISTRATION_PATHS,
                                                   c.PROVIDER_RETRIEVAL_REGISTRATION_BRANCH))

    def test_missing_registration_never_grants_product_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            (root / TASK).unlink()
            self.assertTrue(self.check(root, {"apps/api/src/apbra_api/model_provider.py"}))

if __name__ == "__main__":
    unittest.main()
