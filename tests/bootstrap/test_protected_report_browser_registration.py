"""Verify the registration, prospective checkout and actual-main successor proofs."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
CHECKER_FILE = "scripts/check_bootstrap.py"
RECOVERED_FILE = "scripts/check_recovered_native_registration.py"
CHECKER = runpy.run_path(ROOT / CHECKER_FILE)
RECOVERED = runpy.run_path(ROOT / RECOVERED_FILE)
SCOPE = runpy.run_path(ROOT / RECOVERED["BROWSER_HELPER"])
V7 = runpy.run_path(ROOT / RECOVERED["V7_HELPER"])
NATIVE = runpy.run_path(ROOT / "scripts/check_nv.py")
CATALOG = json.loads((ROOT / "agents/catalog.json").read_bytes())


def git(root, *args, github_fixture=False):
    identity = (
        ["-c", "user.name=GitHub", "-c", "user.email=noreply@github.com"]
        if github_fixture
        else ["-c", "user.name=APBRA fixture", "-c", "user.email=apbra-fixture@example.invalid"]
    )
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    return subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(root), *identity, *args],
        env=env, stderr=subprocess.DEVNULL, timeout=20,
    )


def binding(root, issue, branch, paths):
    return SCOPE["bind"](
        root, V7["raw"], RECOVERED["V3"], CATALOG, CHECKER["schema_errors"], CHECKER["task_errors"],
        issue, branch, paths,
    )


class ProtectedReportBrowserRegistration(unittest.TestCase):
    def test_exact_scope_tasks_and_original_source(self):
        spec = SCOPE["SPEC"]
        self.assertEqual(SCOPE["PRODUCT"], {spec})
        self.assertEqual(len(SCOPE["GOVERNANCE"]), 5)
        self.assertFalse(any(path.startswith(("apps/", ".github/")) for path in SCOPE["GOVERNANCE"]))
        original = git(ROOT, "show", SCOPE["BASE"] + ":" + spec)
        self.assertEqual(SCOPE["sha"](original), SCOPE["SPEC_SHA"])
        historical = RECOVERED["V3"]["manifest"](ROOT)
        self.assertEqual(historical["account_files"][spec], SCOPE["SPEC_SHA"])
        files = SCOPE["protected_snapshot"](ROOT, RECOVERED["V3"])
        for path, expected in NATIVE["OVERLAP"].items():
            with self.subTest(protected_native_path=path):
                self.assertEqual(files[path], SCOPE["sha"](git(ROOT, "show", SCOPE["BASE"] + ":" + path)))
                if path in SCOPE["NATIVE_BASE_PATHS"]:
                    self.assertEqual(files[path], expected)
        task = SCOPE["product_task"](ROOT, V7["raw"], CATALOG, CHECKER["schema_errors"], CHECKER["task_errors"])
        self.assertEqual(task["execution_id"], "APBRA-164-20261124-BROWSER-STABILISATION-01")
        self.assertIn("11099", task["requirements"][0])
        registration = SCOPE["issuance_task"](task)
        self.assertEqual(registration["execution_id"], "APBRA-85-20261124-BROWSER-REGISTER-01")
        self.assertIn("apps/**", registration["restricted_paths"])
        self.assertEqual(set(registration["allowed_paths"]), SCOPE["GOVERNANCE"])

    def test_historical_projections_are_exact_and_preserve_negative_checks(self):
        for name, fn in ((CHECKER_FILE, "strip_browser_bootstrap"), (RECOVERED_FILE, "strip_browser_recovered")):
            current = (ROOT / name).read_bytes()
            self.assertEqual(RECOVERED[fn](current), git(ROOT, "show", SCOPE["BASE"] + ":" + name))
            with self.assertRaises(ValueError):
                RECOVERED[fn](b"# altered prefix\n" + current)
        current = (ROOT / CHECKER_FILE).read_text()
        hook = RECOVERED["BROWSER_BOOT_HOOK"]
        self.assertLessEqual(len(current.encode()), 262076)
        for bad in (current.replace(hook, ""), current + hook, current.replace(hook, hook + " ")):
            with self.assertRaises(ValueError):
                RECOVERED["strip_browser_bootstrap"](bad.encode())
        self.assertIn("# retained mutation", RECOVERED["remove_v7_bootstrap_hook"](current + "\n# retained mutation\n"))

    def test_current_registration_uses_the_real_canonical_and_historical_checks(self):
        context = ("APBRA-85", SCOPE["REG_BRANCH"], SCOPE["GOVERNANCE"])
        if CHECKER["delivery_context"](ROOT) == context:
            self.assertEqual(binding(ROOT, *context)[1], [])
            overlap = NATIVE["OVERLAP"]
            witness = RECOVERED["qualified_paths"]
            self.assertEqual(witness(ROOT, CHECKER, *context, overlap, NATIVE["CANDIDATE"]), set(overlap))
            self.assertEqual(witness(ROOT, CHECKER, *context, overlap, "f" * 40), set())
            corrupted = {**overlap, next(iter(overlap)): "f" * 64}
            self.assertEqual(witness(ROOT, CHECKER, *context, corrupted, NATIVE["CANDIDATE"]), set())

    @patch.dict(os.environ, PR_HEAD_SHA="")
    def test_disposable_release_and_successor_are_deny_by_default(self):
        with tempfile.TemporaryDirectory(prefix="apbra-browser-registration-") as directory:
            path = Path(directory)
            git(path, "init", "-q", "-b", "main")
            git(path, "fetch", "--no-tags", str(ROOT), SCOPE["BASE"] + ":refs/remotes/origin/main")
            git(path, "reset", "--hard", SCOPE["BASE"])
            reg_branch, prod_branch = SCOPE["REG_BRANCH"], SCOPE["PRODUCT_BRANCH"]
            reg_scope, prod_scope = SCOPE["GOVERNANCE"], SCOPE["PRODUCT"]
            registration = ("APBRA-85", reg_branch, reg_scope)
            product = ("APBRA-164", prod_branch, prod_scope)
            git(path, "switch", "-c", reg_branch)
            for name in reg_scope:
                target = path / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            git(path, "add", "--", *sorted(reg_scope))
            git(path, "commit", "-m", "Synthetic registration candidate")
            reg_head = SCOPE["ref"](path, "HEAD")
            self.assertEqual(binding(path, *registration)[1], [])
            self.assertTrue(binding(path, "APBRA-164", reg_branch, reg_scope)[1])
            self.assertTrue(binding(path, "APBRA-85", reg_branch, reg_scope | prod_scope)[1])
            self.assertTrue(binding(path, "APBRA-85", "agent/APBRA-DEVOPS/APBRA-85-foreign", reg_scope)[1])
            self.assertTrue(binding(path, *product)[1])
            self.assertIsNone(SCOPE["registration_merge"](path, V7["raw"]))

            git(path, "switch", "main")
            title = "Merge pull request #9876 from haseebulhaque/" + reg_branch
            git(path, "merge", "--no-ff", reg_head, "-m", title, github_fixture=True)
            reg_merge = SCOPE["ref"](path, "HEAD")
            self.assertIsNone(SCOPE["registration_merge"](path, V7["raw"]))
            with patch.dict(os.environ, PR_HEAD_SHA=reg_head):
                self.assertEqual(binding(path, *registration)[1], [])
                self.assertTrue(binding(path, *product)[1])
            with patch.dict(os.environ, PR_HEAD_SHA=reg_merge):
                self.assertTrue(binding(path, *registration)[1])
            git(path, "update-ref", SCOPE["MAIN"], reg_merge)
            self.assertEqual(SCOPE["registration_merge"](path, V7["raw"]), reg_merge)

            checker = runpy.run_path(path / CHECKER_FILE)
            recovered = runpy.run_path(path / RECOVERED_FILE)
            overlap = NATIVE["OVERLAP"]
            native_candidate = NATIVE["CANDIDATE"]

            def witness(issue, branch, scope):
                with patch.dict(os.environ, GITHUB_HEAD_REF=branch, GITHUB_BASE_REF="main"):
                    return recovered["qualified_paths"](
                        path, checker, issue, branch, scope, overlap, native_candidate,
                    )

            self.assertEqual(witness(None, "main", set()), set(overlap))
            git(path, "update-index", "--chmod=+x", "--", SCOPE["SPEC"])
            self.assertTrue(binding(path, "APBRA-164", "agent/APBRA-DEVOPS/APBRA-164-foreign", prod_scope)[1])
            git(path, "update-index", "--chmod=-x", "--", SCOPE["SPEC"])
            git(path, "update-index", "--chmod=+x", "--", SCOPE["SPEC"])
            git(path, "commit", "-m", "Synthetic mode-only protected browser commit")
            git(path, "restore", "--source=" + reg_merge, "--staged", "--worktree", "--", SCOPE["SPEC"])
            self.assertTrue(binding(path, "APBRA-164", "agent/APBRA-DEVOPS/APBRA-164-foreign", prod_scope)[1])
            git(path, "reset", "--hard", reg_merge)
            destination = "apps/web/src/tenant.test.ts"
            git(path, "config", "diff.renames", "true")
            git(path, "mv", "--", SCOPE["SPEC"], destination)
            git(path, "commit", "-m", "Synthetic out-of-branch browser rename")
            with patch.dict(os.environ, GITHUB_HEAD_REF="agent/APBRA-DEVOPS/APBRA-174-model-led-clarification-flexible-generation-delivery-guide", GITHUB_BASE_REF="main"):
                rename_context = checker["delivery_context"](path)
                self.assertEqual(rename_context[2], {destination})
                codes, _ = checker["check"](
                    path, active_task_id=rename_context[0], active_branch=rename_context[1],
                    changed_paths=rename_context[2],
                )
            self.assertIn("Protected-report browser successor requires the registered maintenance branch", codes)
            git(path, "reset", "--hard", reg_merge)
            for index, name in enumerate(sorted(overlap)):
                with self.subTest(unrelated_current_main_drift=name):
                    unrelated = path / name
                    unrelated.write_bytes(unrelated.read_bytes() + b"\n")
                    git(path, "add", "--", name)
                    git(path, "commit", "-m", "Synthetic protected current-main drift")
                    git(path, "update-ref", SCOPE["MAIN"], SCOPE["ref"](path, "HEAD"))
                    git(path, "switch", "-c", "synthetic-drift-product-" + str(index))
                    changed_spec = path / SCOPE["SPEC"]
                    changed_spec.write_bytes(changed_spec.read_bytes() + b"\n")
                    git(path, "add", "--", SCOPE["SPEC"])
                    git(path, "commit", "-m", "Synthetic product on drifted main")
                    self.assertTrue(binding(path, *product)[1])
                    self.assertEqual(witness(*product), set())
                    git(path, "switch", "main")
                    git(path, "reset", "--hard", reg_merge)
                    git(path, "update-ref", SCOPE["MAIN"], reg_merge)

            git(path, "switch", "-c", prod_branch)
            spec = path / SCOPE["SPEC"]
            before = spec.read_bytes()
            spec.write_bytes(before + b"\n// Synthetic successor fixture.\n")
            self.assertTrue(binding(path, *product)[1])
            git(path, "add", "--", SCOPE["SPEC"])
            git(path, "commit", "-m", "Synthetic browser source candidate")
            prod_head = SCOPE["ref"](path, "HEAD")
            self.assertEqual(binding(path, *product)[1], [])
            self.assertTrue(binding(path, "APBRA-164", "agent/APBRA-DEVOPS/APBRA-164-foreign", prod_scope)[1])
            self.assertTrue(binding(path, "APBRA-164", prod_branch, prod_scope | {"README.md"})[1])
            self.assertEqual(witness(*product), set(overlap))
            spec.write_bytes(spec.read_bytes() + b"\n")
            self.assertTrue(binding(path, *product)[1])
            self.assertEqual(witness(*product), set())
            git(path, "restore", "--", SCOPE["SPEC"])
            git(path, "commit", "--allow-empty", "-m", "Unexpected extra commit")
            self.assertTrue(binding(path, *product)[1])
            git(path, "reset", "--hard", prod_head)
            (path / "stray.txt").write_text("Unexpected untracked source.")
            git(path, "config", "status.showUntrackedFiles", "no")
            self.assertTrue(binding(path, *product)[1])
            (path / "stray.txt").unlink()

            git(path, "switch", "main")
            title = "Merge pull request #9877 from haseebulhaque/" + prod_branch
            git(path, "merge", "--no-ff", prod_head, "-m", title, github_fixture=True)
            merged_product = SCOPE["ref"](path, "HEAD")
            self.assertEqual(witness(None, "main", set()), set())
            git(path, "update-ref", SCOPE["MAIN"], merged_product)
            self.assertEqual(witness(None, "main", set()), set(overlap))
            self.assertTrue(binding(path, *product)[1])
            spec.write_bytes(before)
            self.assertEqual(witness(None, "main", set()), set())
            git(path, "restore", "--", SCOPE["SPEC"])
            protected = path / next(iter(overlap))
            protected.write_bytes(protected.read_bytes() + b"\n")
            self.assertEqual(witness(None, "main", set()), set())

    def test_packet_missing_and_tampered_task_deny(self):
        with tempfile.TemporaryDirectory(prefix="apbra-browser-packet-") as directory:
            root = Path(directory)
            for name in SCOPE["GOVERNANCE"] | {SCOPE["SOURCE_REGISTER"], "contracts/engineering/task-contract.schema.json"}:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            # Copied historical fixtures lack a Git release context. Their old
            # path assertions stay visible, while neither new authority is issued.
            legacy = ("APBRA-164", "agent/APBRA-DEVOPS/APBRA-164-protected-generation-output-history", SCOPE["PRODUCT"])
            self.assertEqual(binding(root, *legacy)[1], [])
            self.assertTrue(binding(root, "APBRA-85", SCOPE["REG_BRANCH"], SCOPE["GOVERNANCE"])[1])
            self.assertTrue(binding(root, "APBRA-164", SCOPE["PRODUCT_BRANCH"], SCOPE["PRODUCT"])[1])
            task = root / SCOPE["TASK"]
            task.write_bytes(task.read_bytes() + b"\n")
            self.assertTrue(binding(root, "APBRA-164", SCOPE["PRODUCT_BRANCH"], SCOPE["PRODUCT"])[1])
            task.unlink()
            self.assertTrue(binding(root, "APBRA-164", SCOPE["PRODUCT_BRANCH"], SCOPE["PRODUCT"])[1])
