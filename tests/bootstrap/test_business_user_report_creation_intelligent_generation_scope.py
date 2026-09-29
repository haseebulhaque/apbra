"""Exact APBRA-171 registration, provenance and active-authority regression tests."""

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
    "bootstrap_apbra_171", ROOT / "scripts/check_bootstrap.py"
)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class BusinessUserIntelligentGenerationScopeTests(unittest.TestCase):
    ORIGINAL_IMPLEMENTATION_PATHS = {
        "apps/api/.env.example",
        "apps/api/README.md",
        "apps/api/alembic/versions/20260929_05_business_user_intelligent_generation.py",
        "apps/api/src/apbra_api/api.py",
        "apps/api/src/apbra_api/application.py",
        "apps/api/src/apbra_api/config.py",
        "apps/api/src/apbra_api/domain.py",
        "apps/api/src/apbra_api/evidence.py",
        "apps/api/src/apbra_api/generation.py",
        "apps/api/src/apbra_api/model_provider.py",
        "apps/api/src/apbra_api/persistence.py",
        "apps/api/src/apbra_api/reference_material.py",
        "apps/api/src/apbra_api/semantic_bridge.py",
        "apps/api/tests/conftest.py",
        "apps/api/tests/test_api.py",
        "apps/api/tests/test_authorization.py",
        "apps/api/tests/test_cases.py",
        "apps/api/tests/test_conversations.py",
        "apps/api/tests/test_evidence.py",
        "apps/api/tests/test_generation.py",
        "apps/api/tests/test_migrations.py",
        "apps/api/tests/test_model_provider.py",
        "apps/api/tests/test_reference_material.py",
        "apps/api/tests/test_semantic_bridge.py",
        "apps/web/e2e/durable-conversation.spec.ts",
        "apps/web/e2e/private-case.spec.ts",
        "apps/web/e2e/protected-generation.spec.ts",
        "apps/web/scripts/generation-bridge.ts",
        "apps/web/scripts/semantic-bridge.ts",
        "apps/web/src/api.test.ts",
        "apps/web/src/api.ts",
        "apps/web/src/clarification.test.ts",
        "apps/web/src/clarification.ts",
        "apps/web/src/confirmedRequirements.test.ts",
        "apps/web/src/confirmedRequirements.ts",
        "apps/web/src/durableConversation.test.tsx",
        "apps/web/src/durableConversation.tsx",
        "apps/web/src/durableGeneration.test.tsx",
        "apps/web/src/durableGeneration.tsx",
        "apps/web/src/foundry.test.ts",
        "apps/web/src/foundry.ts",
        "apps/web/src/genericFoundry.integration.test.ts",
        "apps/web/src/genericPowerBI.test.ts",
        "apps/web/src/genericPowerBI.ts",
        "apps/web/src/guardrail.test.ts",
        "apps/web/src/guardrail.ts",
        "apps/web/src/privateCases.test.tsx",
        "apps/web/src/privateCases.tsx",
        "apps/web/src/reportDesignNormalization.test.ts",
        "apps/web/src/reportDesignNormalization.ts",
        "apps/web/src/style.css",
        "compose.yaml",
    }

    def setUp(self):
        self.task_path = "tasks/APBRA-171-business-user-report-creation-intelligent-generation.json"
        self.task = json.loads((ROOT / self.task_path).read_text())

    def copy_repository(self, root: Path) -> None:
        names = {file.relative_to(ROOT).as_posix() for file in c.repo_files(ROOT)}
        names.update(c.BUSINESS_USER_INTELLIGENT_GENERATION_PATHS)
        names.update(c.BUSINESS_USER_INTELLIGENT_GENERATION_REGISTRATION_PATHS)
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / name
            if source.exists():
                shutil.copyfile(source, target)
            else:
                target.write_text("APBRA-171 fixture\n")

    def check(self, root: Path, changed_paths, *, task_id="APBRA-171", branch=None):
        return c.check(
            root,
            active_task_id=task_id,
            active_branch=self.task["branch"] if branch is None else branch,
            changed_paths=set(changed_paths),
        )[0]

    def test_finite_implementation_authority_and_exact_hash(self):
        expected = set(self.task["allowed_paths"])
        self.assertEqual(expected, c.BUSINESS_USER_INTELLIGENT_GENERATION_PATHS)
        self.assertEqual(len(expected), 53)
        self.assertEqual(
            expected - {"apps/web/playwright.config.ts"},
            self.ORIGINAL_IMPLEMENTATION_PATHS,
        )
        self.assertTrue(all("*" not in path for path in expected))
        self.assertIn("apps/api/src/apbra_api/model_provider.py", expected)
        self.assertIn("apps/api/src/apbra_api/reference_material.py", expected)
        self.assertIn("apps/web/src/genericPowerBI.ts", expected)
        self.assertIn("apps/web/scripts/generation-bridge.ts", expected)
        self.assertIn("apps/web/playwright.config.ts", expected)
        self.assertNotIn("apps/web/playwright.config.ts", self.task["restricted_paths"])
        self.assertNotIn("apps/api/pyproject.toml", expected)
        self.assertNotIn("apps/web/package.json", expected)
        self.assertNotIn("apps/web/src/App.tsx", expected)
        canonical = json.dumps(self.task, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            c.BUSINESS_USER_INTELLIGENT_GENERATION_TASK_SHA256,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in sorted(expected):
                with self.subTest(path=path):
                    self.assertEqual(self.check(root, {path}), [])

    def test_registration_is_exact_five_paths_and_separate(self):
        expected = {
            "scripts/check_bootstrap.py",
            self.task_path,
            "tests/bootstrap/test_business_user_report_creation_intelligent_generation_scope.py",
            "tests/bootstrap/test_invited_private_case_foundation_scope.py",
            "docs/source-register.json",
        }
        self.assertEqual(expected, c.BUSINESS_USER_INTELLIGENT_GENERATION_REGISTRATION_PATHS)
        self.assertTrue(expected.isdisjoint(c.BUSINESS_USER_INTELLIGENT_GENERATION_PATHS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(
                self.check(
                    root,
                    expected,
                    branch=c.BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_BRANCH,
                ),
                [],
            )
            for omitted in sorted(expected):
                with self.subTest(omitted=omitted):
                    errors = self.check(
                        root,
                        expected - {omitted},
                        branch=c.BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_BRANCH,
                    )
                    self.assertIn(
                        "APBRA-171 registration must change exactly its five governance files",
                        errors,
                    )
                    self.assertIn(
                        "Active branch conflicts with task authority: "
                        + c.BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_BRANCH,
                        errors,
                    )
            errors = self.check(root, expected | {"apps/api/src/apbra_api/model_provider.py"})
            self.assertIn("APBRA-171 registration and implementation changes must remain separate", errors)

    def test_playwright_authority_is_narrow_and_github_remains_restricted(self):
        rejected = (
            ".github/workflows/bootstrap.yml",
            ".github/workflows/apbra-171.yml",
            "apps/web/package.json",
            "apps/web/package-lock.json",
            "apps/web/vite.config.ts",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            for path in rejected:
                with self.subTest(path=path):
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        target.write_text("outside APBRA-171 scope\n")
                    self.assertIn(
                        f"File outside active task scope: {path}",
                        self.check(root, {path}),
                    )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            changed = copy.deepcopy(self.task)
            changed["allowed_paths"].append(".github/workflows/bootstrap.yml")
            (root / self.task_path).write_text(json.dumps(changed))
            errors = self.check(root, {".github/workflows/bootstrap.yml"})
            self.assertIn(
                "Business-user intelligent-generation contract differs from accepted authority",
                errors,
            )
            self.assertIn(
                "File outside active task scope: .github/workflows/bootstrap.yml",
                errors,
            )

    def test_hash_source_and_identity_mutations_fail_closed(self):
        new_file = "apps/api/src/apbra_api/model_provider.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            task = copy.deepcopy(self.task)
            task["allowed_paths"].append("apps/api/pyproject.toml")
            (root / self.task_path).write_text(json.dumps(task))
            errors = self.check(root, {new_file})
            self.assertIn("Business-user intelligent-generation contract differs from accepted authority", errors)
            self.assertIn(f"File outside safe bootstrap scope: {new_file}", errors)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            sources = json.loads((root / "docs/source-register.json").read_text())
            source = next(
                item for item in sources["sources"]
                if item["id"] == c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID
            )
            source["acceptance"] += " silently broadened"
            (root / "docs/source-register.json").write_text(json.dumps(sources))
            errors = self.check(root, {new_file})
            self.assertIn("Business-user intelligent-generation source differs from accepted provenance", errors)
            self.assertIn(f"File outside safe bootstrap scope: {new_file}", errors)
        for mutation, expected in (
            ({"task_id": "APBRA-999"}, "Unexpected business-user intelligent-generation identity"),
            ({"branch": "agent/APBRA-DEVOPS/APBRA-171-wrong"}, "Unexpected business-user intelligent-generation branch"),
            ({"base_commit": "0" * 40}, "Stale business-user intelligent-generation base"),
            ({"owner_acceptance": "PENDING"}, "Business-user intelligent generation requires issued implementation acceptance"),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_repository(root)
                task = copy.deepcopy(self.task)
                task.update(mutation)
                (root / self.task_path).write_text(json.dumps(task))
                self.assertIn(expected, self.check(root, {new_file}))

    def test_historical_tree_safety_is_not_historical_change_authority(self):
        new_file = "apps/api/src/apbra_api/model_provider.py"
        older = json.loads(
            (ROOT / "tasks/APBRA-170-professional-saas-experience-visual-system.json").read_text()
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            self.assertEqual(self.check(root, {"apps/web/src/style.css"}, task_id="APBRA-170", branch=older["branch"]), [])
            errors = self.check(root, {new_file}, task_id="APBRA-170", branch=older["branch"])
            self.assertIn(f"File outside active task scope: {new_file}", errors)
            self.assertNotIn(f"File outside safe bootstrap scope: {new_file}", errors)
            task = copy.deepcopy(older)
            task["objective"] += " modified"
            prior_path = root / "tasks/APBRA-170-professional-saas-experience-visual-system.json"
            prior_path.write_text(json.dumps(task))
            errors = self.check(root, {new_file})
            self.assertIn("Professional SaaS experience visual-system contract differs from accepted authority", errors)

    def test_unknown_files_wrong_branch_and_unregistered_task_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            unknown = "apps/api/src/apbra_api/unregistered_provider.py"
            (root / unknown).write_text("not registered\n")
            errors = self.check(root, {unknown})
            self.assertIn(f"File outside active task scope: {unknown}", errors)
            self.assertIn(f"File outside safe bootstrap scope: {unknown}", errors)
            errors = self.check(
                root, {"apps/api/src/apbra_api/model_provider.py"},
                branch="agent/APBRA-DEVOPS/APBRA-171-unauthorised",
            )
            self.assertIn("Active branch conflicts with task authority: agent/APBRA-DEVOPS/APBRA-171-unauthorised", errors)
            (root / self.task_path).unlink()
            errors = self.check(root, {"apps/api/src/apbra_api/model_provider.py"})
            self.assertIn("Unknown or invalid active task authority: APBRA-171", errors)

    def test_architecture_and_historical_source_order_are_explicit(self):
        words = " ".join(
            self.task["requirements"] + self.task["adrs"]
            + self.task["acceptance_criteria"] + self.task["out_of_scope"]
        )
        for required in (
            "ordinary", "provider-neutral", "reviewed_design_id", "canonical",
            "reference material", "difference", "expert", "no automatic fallback",
            "untrusted", "immutable", "server-side",
        ):
            with self.subTest(required=required):
                self.assertIn(required.lower(), words.lower())
        sources = json.loads((ROOT / "docs/source-register.json").read_text())
        ids = [source["id"] for source in sources["sources"]]
        self.assertEqual(ids.count(c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID), 1)
        self.assertEqual(
            ids.index(c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID) + 2,
            ids.index(c.PROFESSIONAL_SAAS_EXPERIENCE_VISUAL_SYSTEM_SOURCE_ID),
        )
        self.assertEqual(
            ids[ids.index(c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID) + 1],
            c.BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_SOURCE_ID,
        )
        source = next(
            item for item in sources["sources"]
            if item["id"] == c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID
        )
        canonical = json.dumps(source, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_SHA256,
        )
        amendment = next(
            item for item in sources["sources"]
            if item["id"] == c.BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_SOURCE_ID
        )
        canonical_amendment = json.dumps(
            amendment, sort_keys=True, separators=(",", ":")
        ).encode()
        self.assertEqual(
            hashlib.sha256(canonical_amendment).hexdigest(),
            c.BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_SOURCE_SHA256,
        )
        historical = (ROOT / "tests/bootstrap/test_invited_private_case_foundation_scope.py").read_text()
        self.assertEqual(historical.count('"mvp1-business-user-report-creation-intelligent-generation"'), 1)
        self.assertEqual(
            historical.count(
                '"mvp1-business-user-report-creation-intelligent-generation-playwright-runtime-amendment"'
            ),
            1,
        )

    def test_runtime_configuration_invariant_is_hash_bound_and_fail_closed(self):
        invariant = (
            "No environment-, provider-, customer-, deployment-, capability- or "
            "policy-dependent runtime value may be hardcoded in application logic."
        )
        adrs = " ".join(self.task["adrs"])
        self.assertIn(invariant, adrs)
        for required in (
            "validated server-side configuration",
            "governed tenant/product configuration",
            "provider selection",
            "endpoint/base URL",
            "configurable API version",
            "vision/structured-output capabilities",
            "upload file types and size/count limits",
            "storage/runtime endpoints",
            "customer/tenant policy choices",
            "truthful capability/configuration error",
            "No silent compiled-in default provider",
            "test values must never become production defaults",
        ):
            with self.subTest(required=required):
                self.assertIn(required.lower(), adrs.lower())
        self.assertTrue(any("Configuration-matrix tests" in item for item in self.task["verification_required"]))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            task = copy.deepcopy(self.task)
            task["adrs"] = [item for item in task["adrs"] if invariant not in item]
            (root / self.task_path).write_text(json.dumps(task))
            self.assertIn(
                "Business-user intelligent-generation contract differs from accepted authority",
                self.check(root, {"apps/api/src/apbra_api/model_provider.py"}),
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            sources = json.loads((root / "docs/source-register.json").read_text())
            source = next(
                item for item in sources["sources"]
                if item["id"] == c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID
            )
            self.assertIn(invariant, source["acceptance"])
            source["acceptance"] = source["acceptance"].replace(invariant, "")
            (root / "docs/source-register.json").write_text(json.dumps(sources))
            self.assertIn(
                "Business-user intelligent-generation source differs from accepted provenance",
                self.check(root, {"apps/api/src/apbra_api/model_provider.py"}),
            )

    def test_current_confluence_direction_is_exactly_bound(self):
        current = "03.07 - Business-User Self-Service Generation & Hosted Preview Direction 8519682 v2"
        refs = " ".join(self.task["architecture_refs"])
        self.assertIn(current, refs)
        self.assertNotIn("8519682 v1", refs)
        for unchanged in (
            "Business & Functional Requirements 3932362 v4",
            "Product Vision 3965201 v4",
            "RTM 3932382 v6",
        ):
            with self.subTest(unchanged=unchanged):
                self.assertIn(unchanged, refs)
        sources = json.loads((ROOT / "docs/source-register.json").read_text())
        source = next(
            item for item in sources["sources"]
            if item["id"] == c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID
        )
        self.assertIn(current, source["version"])
        self.assertNotIn("8519682 v1", source["version"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            task = copy.deepcopy(self.task)
            task["architecture_refs"] = [
                item.replace(current, "03.07 - Business-User Self-Service Generation & Hosted Preview Direction 8519682 v1")
                for item in task["architecture_refs"]
            ]
            (root / self.task_path).write_text(json.dumps(task))
            self.assertIn(
                "Business-user intelligent-generation contract differs from accepted authority",
                self.check(root, {"apps/api/src/apbra_api/model_provider.py"}),
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            sources = json.loads((root / "docs/source-register.json").read_text())
            source = next(
                item for item in sources["sources"]
                if item["id"] == c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID
            )
            source["version"] = source["version"].replace(
                current, "03.07 - Business-User Self-Service Generation & Hosted Preview Direction 8519682 v1"
            )
            (root / "docs/source-register.json").write_text(json.dumps(sources))
            self.assertIn(
                "Business-user intelligent-generation source differs from accepted provenance",
                self.check(root, {"apps/api/src/apbra_api/model_provider.py"}),
            )

    def test_playwright_amendment_source_and_runtime_limits_are_hash_bound(self):
        amendment_ref = (
            "03.07 - Business-User Self-Service Generation & Hosted Preview "
            "Direction 8519682 v3"
        )
        self.assertIn(amendment_ref, " ".join(self.task["architecture_refs"]))
        source = next(
            item for item in json.loads((ROOT / "docs/source-register.json").read_text())["sources"]
            if item["id"] == c.BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_SOURCE_ID
        )
        for required in (
            "apps/web/playwright.config.ts",
            "fifty-third",
            "synthetic/test-only",
            "external or paid model call",
            ".github/workflows/bootstrap.yml remain restricted",
            "APBRA_E2E",
            "database-isolation",
            "implementation PR #66",
        ):
            with self.subTest(required=required):
                self.assertIn(required, source["acceptance"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            sources = json.loads((root / "docs/source-register.json").read_text())
            changed = next(
                item for item in sources["sources"]
                if item["id"] == c.BUSINESS_USER_INTELLIGENT_GENERATION_AMENDMENT_SOURCE_ID
            )
            changed["acceptance"] += " broader workflow authority"
            (root / "docs/source-register.json").write_text(json.dumps(sources))
            self.assertIn(
                "Business-user intelligent-generation Playwright amendment source differs from accepted provenance",
                self.check(root, {"apps/web/playwright.config.ts"}),
            )

    def test_p0_responsive_journey_is_explicit_and_hash_bound(self):
        invariant = "Responsive UX and cross-flow consistency are P0 acceptance scope inside APBRA-171"
        self.assertTrue(any(invariant in item for item in self.task["requirements"]))
        acceptance = " ".join(self.task["acceptance_criteria"]).lower()
        verification = " ".join(self.task["verification_required"]).lower()
        for required in (
            "desktop, laptop, tablet and narrow/mobile",
            "horizontal page overflow",
            "hidden primary actions",
            "overlapping or broken sticky regions",
            "navigation rail, top bar, sticky six-stage journey",
            "upload/drop zone",
            "requirement review, clarification, build/report states, durable history and expert escalation",
            "long report titles, filenames, field names, validation text and user-entered requirements",
            "keyboard accessible and touch-usable",
            "empty, loading, disabled, success, warning, stale, error and unavailable",
            "business terminology and primary action labels",
            "progressively disclosed at every viewport size",
            "centralized in the design/style system",
            "desktop screenshot alone is insufficient",
        ):
            with self.subTest(required=required):
                self.assertIn(required.lower(), acceptance)
        self.assertIn("real-browser responsive regression coverage", verification)
        self.assertIn("viewport matrix", verification)
        self.assertIn("keyboard/focus and touch-usable controls", verification)
        for path in (
            "apps/web/src/privateCases.tsx",
            "apps/web/src/durableConversation.tsx",
            "apps/web/src/durableGeneration.tsx",
            "apps/web/src/style.css",
            "apps/web/e2e/durable-conversation.spec.ts",
        ):
            self.assertIn(path, self.task["allowed_paths"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            task = copy.deepcopy(self.task)
            task["requirements"] = [item for item in task["requirements"] if invariant not in item]
            (root / self.task_path).write_text(json.dumps(task))
            self.assertIn(
                "Business-user intelligent-generation contract differs from accepted authority",
                self.check(root, {"apps/web/src/privateCases.tsx"}),
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_repository(root)
            sources = json.loads((root / "docs/source-register.json").read_text())
            source = next(
                item for item in sources["sources"]
                if item["id"] == c.BUSINESS_USER_INTELLIGENT_GENERATION_SOURCE_ID
            )
            self.assertIn(invariant, source["acceptance"])
            source["acceptance"] = source["acceptance"].replace(invariant, "")
            (root / "docs/source-register.json").write_text(json.dumps(sources))
            self.assertIn(
                "Business-user intelligent-generation source differs from accepted provenance",
                self.check(root, {"apps/web/src/privateCases.tsx"}),
            )


if __name__ == "__main__":
    unittest.main()
