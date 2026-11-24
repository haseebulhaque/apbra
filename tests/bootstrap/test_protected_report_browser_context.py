"""Exercise live delivery and historical assertions in the same committed checkout."""
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = "scripts/check_recovered_native_registration.py"
CHECKER = "scripts/check_bootstrap.py"
RECOVERED = runpy.run_path(ROOT / WRAPPER)
CONTEXT = runpy.run_path(ROOT / RECOVERED["BROWSER_CONTEXT_HELPER"])
OLD, RAW = RECOVERED["browser_module"](ROOT)
NATIVE = runpy.run_path(ROOT / "scripts/check_nv.py")


def git(root, *args, merge_fixture=False):
    name, email = ("GitHub", "noreply@github.com") if merge_fixture else ("APBRA fixture", "fixture@example.invalid")
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    return subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(root), "-c", "user.name=" + name,
         "-c", "user.email=" + email, *args],
        env=env, stderr=subprocess.DEVNULL, timeout=20,
    )


class ProtectedReportBrowserContext(unittest.TestCase):
    def test_original_packet_and_historical_proof_bytes_stay_exact(self):
        self.assertEqual(CONTEXT["SCOPE"], {WRAPPER, CONTEXT["HELPER"], CONTEXT["TESTS"]})
        self.assertEqual(
            RECOVERED["strip_browser_context"]((ROOT / WRAPPER).read_bytes()),
            git(ROOT, "show", CONTEXT["BASE"] + ":" + WRAPPER),
        )
        # The canonical source has a strict additive inverse. Verify the
        # original preimage so later reviewed layers can compose that inverse.
        self.assertEqual(
            RECOVERED["strip_browser_bootstrap"](RAW(ROOT, CHECKER)),
            git(ROOT, "show", OLD["BASE"] + ":" + CHECKER),
        )
        for path in OLD["GOVERNANCE"] - {WRAPPER, CHECKER}:
            self.assertEqual(RAW(ROOT, path), git(ROOT, "show", CONTEXT["BASE"] + ":" + path))
        wrapper = (ROOT / WRAPPER).read_bytes()
        with self.assertRaises(ValueError):
            RECOVERED["strip_browser_context"](b"# Previous source changed.\n" + wrapper)
        with self.assertRaises(ValueError):
            RECOVERED["strip_browser_context"](wrapper + RECOVERED["BROWSER_CONTEXT_MARKER"])

    @patch.dict(os.environ, PR_HEAD_SHA="", GITHUB_BASE_REF="main")
    def test_live_and_historical_contexts_share_the_exact_successor_checkout(self):
        with tempfile.TemporaryDirectory(prefix="apbra-browser-context-") as directory:
            root = Path(directory)
            base, branch, scope = CONTEXT["BASE"], CONTEXT["BRANCH"], CONTEXT["SCOPE"]
            main, product, spec = OLD["MAIN"], OLD["PRODUCT_BRANCH"], OLD["SPEC"]
            git(root, "init", "-q", "-b", "main")
            git(root, "fetch", "--no-tags", str(ROOT), base + ":" + main)
            git(root, "reset", "--hard", base)
            git(root, "switch", "-c", branch)
            for name in scope:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            git(root, "add", "--", *sorted(scope))
            git(root, "commit", "-m", "Synthetic context-correction candidate")
            correction_head = OLD["ref"](root, "HEAD")
            checker = runpy.run_path(root / CHECKER)
            recovered = runpy.run_path(root / WRAPPER)
            module, old, raw = recovered["browser_context_module"](root)
            overlap = NATIVE["OVERLAP"]
            legacy = runpy.run_path(root / "scripts/check_agent_details_20261013.py")

            def check(context):
                issue, submitted, paths = context
                return checker["check"](
                    root, active_task_id=issue, active_branch=submitted, changed_paths=paths,
                )[0]

            def witness(context):
                return recovered["qualified_paths"](
                    root, checker, *context, overlap, NATIVE["CANDIDATE"],
                )

            with patch.dict(os.environ, GITHUB_HEAD_REF=branch):
                actual = ("APBRA-85", branch, scope)
                self.assertEqual(checker["delivery_context"](root), actual)
                self.assertEqual(check(actual), [])
                self.assertEqual(witness(actual), set(overlap))
                self.assertTrue(check(("APBRA-85", branch, scope | {spec})))
            git(root, "switch", "main")
            git(root, "merge", "--no-ff", correction_head,
                "-m", "Merge pull request #9876 from haseebulhaque/" + branch, merge_fixture=True)
            correction_merge = OLD["ref"](root, "HEAD")
            self.assertIsNone(module["released"](root, old, raw))
            git(root, "switch", "-c", product)
            original = (root / spec).read_bytes()
            (root / spec).write_bytes(original + b"\n// Synthetic one-file browser successor fixture.\n")
            git(root, "add", "--", spec)
            git(root, "commit", "-m", "Synthetic browser successor candidate")
            product_head = OLD["ref"](root, "HEAD")
            live = ("APBRA-164", product, {spec})
            with patch.dict(os.environ, GITHUB_HEAD_REF=product):
                self.assertTrue(check(live))
                git(root, "update-ref", main, correction_merge)
                self.assertEqual(module["released"](root, old, raw), correction_merge)
                self.assertEqual(checker["delivery_context"](root), live)
                self.assertEqual(check(live), [])
                self.assertEqual(witness(live), set(overlap))
                self.assertEqual(check(("APBRA-160", legacy["B"], legacy["P"])), [])
                self.assertTrue(check(("APBRA-164", product, {spec, "README.md"})))
                self.assertTrue(check(("APBRA-160", legacy["B"], legacy["P"] | {CONTEXT["TESTS"]})))

            foreign = "agent/APBRA-DEVOPS/APBRA-174-model-led-clarification-flexible-generation-delivery-guide"
            with patch.dict(os.environ, GITHUB_HEAD_REF=foreign):
                denied = "Protected-report browser successor requires the registered maintenance branch"
                self.assertIn(denied, check(checker["delivery_context"](root)))
                self.assertTrue(check(live))
                git(root, "reset", "--hard", correction_merge)
                git(root, "config", "diff.renames", "true")
                destination = "apps/web/src/tenant.test.ts"
                git(root, "mv", "--", spec, destination)
                git(root, "commit", "-m", "Synthetic foreign-branch rename")
                renamed = checker["delivery_context"](root)
                self.assertEqual(renamed[2], {destination})
                self.assertIn(denied, check(renamed))
                git(root, "reset", "--hard", correction_merge)
                git(root, "update-index", "--chmod=+x", "--", spec)
                self.assertIn(denied, check(checker["delivery_context"](root)))
                git(root, "reset", "--hard", product_head)

            git(root, "switch", "main")
            git(root, "merge", "--no-ff", product_head,
                "-m", "Merge pull request #9877 from haseebulhaque/" + product, merge_fixture=True)
            product_merge = OLD["ref"](root, "HEAD")
            with patch.dict(os.environ, GITHUB_HEAD_REF="main"):
                clean = (None, "main", set())
                self.assertEqual(witness(clean), set())
                git(root, "update-ref", main, product_merge)
                self.assertEqual(check(clean), [])
                self.assertEqual(witness(clean), set(overlap))
                self.assertTrue(check(live))
                (root / spec).write_bytes(original)
                self.assertEqual(witness(clean), set())
