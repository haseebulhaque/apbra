"""Exact APBRA-162 registration, authority and fail-closed scope checks."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_invited_private_case_foundation", ROOT / "scripts/check_bootstrap.py"
)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class InvitedPrivateCaseFoundationScopeTests(unittest.TestCase):
    def setUp(self):
        self.task_path = "tasks/APBRA-162-invited-private-case-foundation.json"
        self.task = json.loads((ROOT / self.task_path).read_text())
        self.source_path = "docs/source-register.json"
        self.sources = json.loads((ROOT / self.source_path).read_text())

    def copy_repository(self, root: Path):
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.INVITED_PRIVATE_CASE_FOUNDATION_PATHS)
        names.update(c.INVITED_PRIVATE_CASE_FOUNDATION_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-162 fixture\n")

    def check(self, root: Path, changed_paths, *, task_id="APBRA-162", branch=None):
        return c.check(
            root,
            active_task_id=task_id,
            active_branch=self.task["branch"] if branch is None else branch,
            changed_paths=set(changed_paths),
        )[0]

    def test_task_is_known_with_exact_finite_implementation_scope(self):
        expected = {
            ".github/workflows/bootstrap.yml",
            "README.md",
            "apps/api/.dockerignore",
            "apps/api/.env.example",
            "apps/api/Dockerfile",
            "apps/api/README.md",
            "apps/api/alembic.ini",
            "apps/api/alembic/env.py",
            "apps/api/alembic/script.py.mako",
            "apps/api/alembic/versions/20260923_01_invited_private_case_foundation.py",
            "apps/api/pyproject.toml",
            "apps/api/src/apbra_api/__init__.py",
            "apps/api/src/apbra_api/api.py",
            "apps/api/src/apbra_api/application.py",
            "apps/api/src/apbra_api/auth_boundary.py",
            "apps/api/src/apbra_api/authorization.py",
            "apps/api/src/apbra_api/bootstrap.py",
            "apps/api/src/apbra_api/config.py",
            "apps/api/src/apbra_api/domain.py",
            "apps/api/src/apbra_api/main.py",
            "apps/api/src/apbra_api/oidc_adapter.py",
            "apps/api/src/apbra_api/persistence.py",
            "apps/api/tests/conftest.py",
            "apps/api/tests/test_api.py",
            "apps/api/tests/test_authentication.py",
            "apps/api/tests/test_authorization.py",
            "apps/api/tests/test_bootstrap.py",
            "apps/api/tests/test_cases.py",
            "apps/api/tests/test_invitations.py",
            "apps/api/tests/test_migrations.py",
            "apps/api/uv.lock",
            "apps/web/.env.example",
            "apps/web/README.md",
            "apps/web/e2e/private-case.spec.ts",
            "apps/web/package-lock.json",
            "apps/web/package.json",
            "apps/web/playwright.config.ts",
            "apps/web/src/App.test.tsx",
            "apps/web/src/EnterpriseApp.tsx",
            "apps/web/src/api.test.ts",
            "apps/web/src/api.ts",
            "apps/web/src/privateCases.test.tsx",
            "apps/web/src/privateCases.tsx",
            "apps/web/src/style.css",
            "apps/web/vite.config.ts",
            "compose.yaml",
            "scripts/check_ci_policy.py",
            "tests/bootstrap/test_bootstrap.py",
        }
        self.assertEqual(c.INVITED_PRIVATE_CASE_FOUNDATION_PATHS, expected)
        self.assertEqual(set(self.task["allowed_paths"]), expected)
        canonical = json.dumps(self.task, sort_keys=True, separators=(",", ":")).encode()
        expected_digest = "7acc6d58d90cdd99e2fded77223d6dcc1e80e6d275042f34254d299a3cbaf702"
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), expected_digest)
        self.assertEqual(c.INVITED_PRIVATE_CASE_FOUNDATION_TASK_SHA256, expected_digest)
        self.assertEqual(len(expected), 48)
        self.assertTrue(all("*" not in path for path in expected))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in sorted(expected):
                with self.subTest(path=path):
                    if path == "tests/bootstrap/test_bootstrap.py":
                        fixture = root / path
                        fixture.write_text(
                            fixture.read_text().replace(
                                "p.parent.mkdir(parents=True)",
                                "p.parent.mkdir(parents=True, exist_ok=True)",
                            )
                        )
                    self.assertEqual(self.check(root, {path}), [])

    def test_registration_scope_is_exact_disjoint_and_admitted_together(self):
        expected = {
            "scripts/check_bootstrap.py",
            "tasks/APBRA-162-invited-private-case-foundation.json",
            "tests/bootstrap/test_invited_private_case_foundation_scope.py",
            "docs/source-register.json",
        }
        self.assertEqual(c.INVITED_PRIVATE_CASE_FOUNDATION_REGISTRATION_PATHS, expected)
        self.assertTrue(expected.isdisjoint(c.INVITED_PRIVATE_CASE_FOUNDATION_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, expected), [])
            for omitted in sorted(expected):
                with self.subTest(omitted=omitted):
                    errors = self.check(root, expected - {omitted})
                    self.assertIn("APBRA-162 registration must change exactly its four governance files", errors)

    def test_registration_and_implementation_changes_cannot_be_mixed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            errors = self.check(root, {"scripts/check_bootstrap.py", "apps/api/src/apbra_api/main.py"})
            self.assertIn(
                "APBRA-162 registration and implementation changes must remain separate",
                errors,
            )

    def test_only_literal_historical_bootstrap_fixture_is_implementation_authority(self):
        authorized = "tests/bootstrap/test_bootstrap.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            fixture = root / authorized
            fixture.write_text(
                fixture.read_text().replace(
                    "p.parent.mkdir(parents=True)",
                    "p.parent.mkdir(parents=True, exist_ok=True)",
                )
            )
            self.assertEqual(self.check(root, {authorized}), [])
            self.assertEqual(
                hashlib.sha256(fixture.read_bytes()).hexdigest(),
                c.INVITED_PRIVATE_CASE_FOUNDATION_BOOTSTRAP_FIX_SHA256,
            )
            fixture.write_text(fixture.read_text() + "\n# unauthorized change\n")
            self.assertIn(
                "APBRA-162 permits only the accepted test_product_file_is_not_bootstrap fixture correction",
                self.check(root, {authorized}),
            )
            for path in sorted(
                file.relative_to(ROOT).as_posix()
                for file in (ROOT / "tests/bootstrap").glob("*.py")
                if file.relative_to(ROOT).as_posix() != authorized
            ):
                with self.subTest(path=path):
                    errors = self.check(root, {path})
                    self.assertTrue(errors, f"Unexpectedly admitted bootstrap implementation path: {path}")
                    self.assertTrue(
                        f"File outside active task scope: {path}" in errors
                        or "APBRA-162 registration must change exactly its four governance files" in errors,
                        errors,
                    )

            unsafe_product_path = "apps/api/main.py"
            target = root / unsafe_product_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("outside safe scope\n")
            errors = self.check(root, {unsafe_product_path})
            self.assertIn(f"File outside active task scope: {unsafe_product_path}", errors)
            self.assertIn(f"File outside safe bootstrap scope: {unsafe_product_path}", errors)

    def test_wrong_identity_branch_base_role_source_acceptance_and_scope_fail(self):
        mutations = (
            ({"task_id": "APBRA-999"}, "Unexpected invited private-case foundation identity"),
            ({"assigned_agent": "APBRA-DEV-BE"}, "Unexpected invited private-case foundation identity"),
            ({"agent_card_version": "9.9"}, "Stale invited private-case foundation agent card version"),
            ({"branch": "agent/APBRA-DEVOPS/APBRA-162-wrong"}, "Unexpected invited private-case foundation branch"),
            ({"base_commit": "0" * 40}, "Stale invited private-case foundation base"),
            ({"task_mode": "PLANNING"}, "'PLANNING' is not one of"),
            ({"readiness": "BLOCKED"}, "'BLOCKED' is not one of"),
            ({"owner_acceptance": "PENDING"}, "Invited private-case foundation requires issued implementation acceptance"),
            ({"source_ids": ["post-capstone-confirmation-readiness-integrity"]}, "Invited private-case foundation requires its specific accepted source"),
            ({"source_ids": ["implementation-contract"]}, "Proposed sources cannot authorize implementation"),
            ({"allowed_paths": ["apps/**"]}, "Unexpected invited private-case foundation scope"),
            ({"allowed_paths": self.task["allowed_paths"][:-1]}, "Unexpected invited private-case foundation scope"),
            ({"allowed_paths": self.task["allowed_paths"] + ["apps/api/extra.py"]}, "Unexpected invited private-case foundation scope"),
            ({"objective": None}, "None is not of type 'string'"),
        )
        for mutation, expected in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                changed = copy.deepcopy(self.task)
                changed.update(mutation)
                (root / self.task_path).write_text(json.dumps(changed))
                errors = self.check(root, {"apps/api/src/apbra_api/main.py"})
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn("File outside active task scope: apps/api/src/apbra_api/main.py", errors)

    def test_material_contract_authority_mutations_fail_even_when_schema_and_keywords_survive(self):
        mutations = {
            "objective": "This replacement objective retains APBRA-162 but removes the accepted authority.",
            "requirements": self.task["requirements"] + ["Replacement requirement"],
            "adrs": self.task["adrs"] + ["Replacement ADR retaining PostgreSQL 17 and OIDC words"],
            "architecture_refs": self.task["architecture_refs"] + ["Replacement reference"],
            "restricted_paths": self.task["restricted_paths"][:-1],
            "acceptance_criteria": self.task["acceptance_criteria"] + ["Replacement acceptance while preserving all existing keywords"],
            "verification_required": self.task["verification_required"] + ["Replacement verification"],
            "out_of_scope": self.task["out_of_scope"] + ["Replacement exclusion"],
            "escalate_when": self.task["escalate_when"] + ["Replacement escalation"],
            "dependencies": self.task["dependencies"] + ["Replacement dependency"],
            "effective_release": self.task["effective_release"] + " replacement",
        }
        for field, value in mutations.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                changed = copy.deepcopy(self.task)
                changed[field] = value
                (root / self.task_path).write_text(json.dumps(changed))
                errors = self.check(root, {"apps/api/src/apbra_api/main.py"})
                self.assertIn("Invited private-case foundation contract differs from accepted authority", errors)
                self.assertIn("File outside active task scope: apps/api/src/apbra_api/main.py", errors)

    def test_missing_malformed_unknown_active_task_and_branch_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            (root / self.task_path).unlink()
            errors = self.check(root, {"apps/api/src/apbra_api/main.py"})
            self.assertIn("Unknown or invalid active task authority: APBRA-162", errors)
            self.assertIn("File outside active task scope: apps/api/src/apbra_api/main.py", errors)

        cases = (
            (None, self.task["branch"], "Active task identity missing"),
            ("APBRA162", self.task["branch"], "Malformed active task identity"),
            ("APBRA-999", self.task["branch"], "Unknown or invalid active task authority"),
            ("APBRA-162", None, "Active task branch identity missing"),
            ("APBRA-162", "agent/APBRA-DEVOPS/APBRA-162-wrong", "Active branch conflicts with task authority"),
        )
        for task_id, branch, expected in cases:
            with self.subTest(task_id=task_id, branch=branch), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                errors = c.check(root, active_task_id=task_id, active_branch=branch, changed_paths={"apps/api/src/apbra_api/main.py"})[0]
                self.assertTrue(any(expected in error for error in errors), errors)
                self.assertIn("File outside active task scope: apps/api/src/apbra_api/main.py", errors)

    def test_unsafe_and_out_of_scope_product_paths_fail(self):
        rejected = (
            "apps/api/.env",
            "apps/api/dev.sqlite",
            "apps/api/data/database.db",
            "apps/api/src/apbra_api/object_storage.py",
            "apps/api/src/apbra_api/generation.py",
            "apps/web/src/foundry.ts",
            "apps/web/src/rag.ts",
            "infrastructure/azure/main.bicep",
            "terraform/main.tf",
            "output/candidate.zip",
            "artifacts/runtime-evidence.json",
            "tasks/APBRA-147-confirmation-readiness-integrity.json",
            "tests/bootstrap/test_confirmation_readiness_integrity_scope.py",
            "docs/source-register-extra.json",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in rejected:
                with self.subTest(path=path):
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        target.write_text("{}" if target.suffix == ".json" else "outside scope\n")
                    self.assertIn(f"File outside active task scope: {path}", self.check(root, {path}))

    def test_source_is_exact_accepted_and_preserves_history(self):
        expected_ids = [
            "engineering-structure",
            "implementation-contract",
            "implementation-adrs",
            "task-contract",
            "jira-workflow",
            "solo-owner-policy",
            "capstone-web-shell",
            "capstone-requirements-snapshot",
            "capstone-curated-knowledge",
            "capstone-design-plan",
            "capstone-powerbi-project",
            "capstone-validation",
            "capstone-governance",
            "capstone-orchestration",
            "capstone-evaluation",
            "post-capstone-product-reconciliation",
            "post-capstone-data-model-reconciliation",
            "post-capstone-confirmation-readiness-integrity",
            "mvp1-invited-private-case-foundation",
            "mvp1-invited-private-case-foundation-scope-amendment",
            "mvp1-durable-conversation-evidence-acceptance",
            "mvp1-durable-conversation-evidence-acceptance-ci-amendment",
        ]
        self.assertEqual([source["id"] for source in self.sources["sources"]], expected_ids)
        source_map = {source["id"]: source for source in self.sources["sources"]}
        current = source_map["mvp1-invited-private-case-foundation"]
        self.assertEqual(current["content_id"], "APBRA-162")
        self.assertEqual(current["status"], "ACCEPTED")
        self.assertIn("APBRA-161 accepted decision comment 10211", current["version"])
        self.assertIn("AUD 0", current["acceptance"])
        self.assertIn("manual", current["acceptance"])
        canonical = json.dumps(current, sort_keys=True, separators=(",", ":")).encode()
        expected_digest = "067467b5557cf3fa1f381056622b014f3d96cd84a076252f917fcbc186ca23e2"
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), expected_digest)
        self.assertEqual(c.INVITED_PRIVATE_CASE_FOUNDATION_SOURCE_SHA256, expected_digest)
        amendment = source_map["mvp1-invited-private-case-foundation-scope-amendment"]
        self.assertEqual(amendment["content_id"], "APBRA-162")
        self.assertEqual(amendment["status"], "ACCEPTED")
        self.assertIn("comment 10220", amendment["version"])
        self.assertIn("forty-eighth", amendment["acceptance"])
        self.assertIn("manual merge", amendment["acceptance"])
        canonical_amendment = json.dumps(amendment, sort_keys=True, separators=(",", ":")).encode()
        amendment_digest = "8f01e0e8b4833c744734e0a872dfe3238c2aae8c6da1b415272608dff49000fa"
        self.assertEqual(hashlib.sha256(canonical_amendment).hexdigest(), amendment_digest)
        self.assertEqual(c.INVITED_PRIVATE_CASE_FOUNDATION_AMENDMENT_SOURCE_SHA256, amendment_digest)
        for historical in (
            "capstone-governance",
            "post-capstone-product-reconciliation",
            "post-capstone-data-model-reconciliation",
            "post-capstone-confirmation-readiness-integrity",
        ):
            self.assertIn(historical, source_map)

    def test_material_source_provenance_mutations_fail_closed(self):
        mutations = {
            "content_id": "APBRA-999",
            "version": "; rewritten",
            "section": "rewritten section",
            "url": "https://arkitektz.atlassian.net/browse/APBRA-999",
            "acceptance": " Rewritten while retaining prior keywords.",
        }
        for source_id, expected in (
            ("mvp1-invited-private-case-foundation", "Invited private-case foundation source differs from accepted provenance"),
            ("mvp1-invited-private-case-foundation-scope-amendment", "Invited private-case foundation amendment source differs from accepted provenance"),
        ):
            for field, value in mutations.items():
                with self.subTest(source_id=source_id, field=field), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.copy_repository(root)
                    changed = copy.deepcopy(self.sources)
                    source = next(item for item in changed["sources"] if item["id"] == source_id)
                    source[field] = source[field] + value if field in {"version", "acceptance"} else value
                    (root / self.source_path).write_text(json.dumps(changed))
                    errors = self.check(root, {"apps/api/src/apbra_api/main.py"})
                    self.assertIn(expected, errors)
                    self.assertIn("File outside active task scope: apps/api/src/apbra_api/main.py", errors)

    def test_historical_authorities_remain_independently_valid(self):
        historical = {
            "APBRA-140": ("tasks/APBRA-140-capstone-documentation.json", "README.md"),
            "APBRA-146": ("tasks/APBRA-146-post-capstone-mvp-baseline-reconciliation.json", "README.md"),
            "APBRA-147": ("tasks/APBRA-147-confirmation-readiness-integrity.json", "apps/web/src/clarification.ts"),
            "APBRA-148": ("tasks/APBRA-148-post-capstone-product-reconciliation.json", "AGENTS.md"),
            "APBRA-159": ("tasks/APBRA-159-data-model-documentation-reconciliation.json", "DATA-MODEL.md"),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for task_id, (task_path, path) in historical.items():
                with self.subTest(task_id=task_id):
                    task = json.loads((ROOT / task_path).read_text())
                    self.assertEqual(c.check(root, active_task_id=task_id, active_branch=task["branch"], changed_paths={path})[0], [])

    def test_secret_traversal_and_symlink_protections_remain_active(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            target = root / "apps/api/src/apbra_api/main.py"
            target.write_text("credential = 'ghp_" + "A" * 36 + "'\n")
            self.assertIn("High-confidence credential pattern in: apps/api/src/apbra_api/main.py", self.check(root, {"apps/api/src/apbra_api/main.py"}))
            target.unlink()
            target.symlink_to(root / "README.md")
            self.assertIn("File outside safe bootstrap scope: apps/api/src/apbra_api/main.py", self.check(root, {"apps/api/src/apbra_api/main.py"}))
            self.assertIn("File outside active task scope: ../apps/api/src/apbra_api/main.py", self.check(root, {"../apps/api/src/apbra_api/main.py"}))

    def test_contract_encodes_real_security_persistence_and_zero_spend_boundaries(self):
        criteria = " ".join(self.task["acceptance_criteria"])
        adrs = " ".join(self.task["adrs"])
        verification = " ".join(self.task["verification_required"])
        exclusions = " ".join(self.task["out_of_scope"])
        for required in (
            "signature, exact issuer, audience, expiry and subject validation",
            "re-evaluates active membership",
            "real API and migrated PostgreSQL database",
            "payload-bound idempotency",
            "optimistic concurrency",
            "do not reveal",
            "transactionally",
        ):
            with self.subTest(required=required):
                self.assertIn(required, criteria)
        self.assertIn("PostgreSQL 17", verification)
        self.assertIn("UI-to-API-to-PostgreSQL", verification)
        for role in ("COMPANY_OWNER", "COMPANY_ADMIN", "MEMBER", "EXPERT"):
            self.assertIn(role, criteria + " " + adrs)
        self.assertIn("server-bootstrapped", criteria)
        self.assertIn("idempotent", criteria)
        self.assertIn("explicit conflict", criteria)
        self.assertIn("psycopg 3", criteria)
        self.assertIn("Authlib with cryptography", criteria)
        for protection in (
            "authorization code plus PKCE S256",
            "state and nonce",
            "issuer mix-up protection",
            "exact allowlisted redirect",
            "one-time callback",
            "provider tokens and refresh credentials remain server-side",
            "one-way digest",
            "timing-safe",
            "database rows",
            "company consistency",
        ):
            with self.subTest(protection=protection):
                self.assertIn(protection, criteria + " " + adrs)
        self.assertIn("AUD 0", adrs)
        self.assertIn("Azure Container Apps", exclusions)
        self.assertIn("report-generation API orchestration", exclusions)
        self.assertIn("tests/bootstrap/test_bootstrap.py", self.task["allowed_paths"])
        self.assertNotIn("tests/bootstrap/**", self.task["restricted_paths"])
        self.assertIn("p.parent.mkdir(parents=True, exist_ok=True)", criteria)
        self.assertIn("test_product_file_is_not_bootstrap", criteria)


if __name__ == "__main__":
    unittest.main()
