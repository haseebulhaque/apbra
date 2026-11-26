"""Exercise the signed-in demo issuance and its twelve-file successor on real Git trees."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from test_foundry_report_documentation_scope import (
    CHECKER, DOCS, FROZEN, INVITE, INVITE_PATHS, MAIN, PRODUCT_PATHS, V10_RESERVED, WRAPPER,
    ancestry_commit, check_query, commit, git, hosted_checkout, invitation_candidate,
    invitation_merge, ordinary, point_main, ref,
)
from test_native_invitation_release_readback import OVERLAP, PIN


ROOT = Path(__file__).resolve().parents[2]
BASE = "959f39a89911b05e278feedd0cdc8edd8e1d77d9"
TRANSPORT_BASE = "bfb87010d2a4f7571069522ce57438a35f720391"
TRANSPORT_HEAD = "5f4f082fb17358ed77d3c119d8f46ccd628ac179"
TRANSPORT_TREE = "5429c192037029c4c58661a3d49f2b79a712e2db"
PRODUCT = "agent/APBRA-DEVOPS/APBRA-160-foundry-v10-signed-in-demo"
ISSUER = PRODUCT + "-issuance"
TASK = "tasks/APBRA-160-foundry-v10-signed-in-demo-20261126.json"
PACKET = {TASK, WRAPPER, "tests/bootstrap/test_foundry_v10_signed_in_demo_scope.py"}
SIGNED_IN = {
    "apps/api/src/apbra_api/api.py",
    "apps/api/src/apbra_api/foundry_browser_handoff.py",
    "apps/api/src/apbra_api/foundry_memory_handoff.py",
    "apps/api/src/apbra_api/foundry_v10_demo_receiver.py",
    "apps/api/src/apbra_api/native_response_api.py",
    "apps/api/src/apbra_api/request_outputs.py",
    "apps/api/tests/test_foundry_v10_demo_receiver.py",
    "apps/api/tests/test_native_response_integration.py",
    "apps/web/e2e/native-outputs.spec.ts",
    "apps/web/src/BusinessReportJourney.test.tsx",
    "apps/web/src/BusinessReportJourney.tsx",
    "apps/web/src/api.ts",
}
INVITE_SHARED = {"apps/api/src/apbra_api/api.py", "apps/web/src/api.ts"}
RECEIVER = "apps/api/src/apbra_api/foundry_v10_demo_receiver.py"
NEW_SOURCES = {RECEIVER, "apps/api/tests/test_foundry_v10_demo_receiver.py"}
STYLE = "apps/web/src/style.css"
PROTECTED = DOCS | PRODUCT_PATHS | V10_RESERVED | {
    "tasks/APBRA-160-foundry-v10-transport-issuance-20261126.json",
    "tests/bootstrap/test_foundry_v10_transport_issuance.py",
    "docs/source-register-apbra160-v10-report-transport.json",
}


@contextmanager
def issuer_fixture():
    """A later checkout keeps exercising the first release of this exact registration."""
    with tempfile.TemporaryDirectory(prefix="apbra-signed-in-") as directory:
        root = Path(directory) / "checkout"
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        git(root, "fetch", "--no-tags", str(ROOT), BASE + ":" + MAIN,
            FROZEN + ":refs/fixtures/frozen-invitation")
        git(root, "reset", "--hard", BASE)
        git(root, "switch", "-c", ISSUER)
        releases = git(ROOT, "log", "--first-parent", "--diff-filter=A", "--format=%H", MAIN,
                       "--", TASK).decode().splitlines()
        for path in PACKET:
            data = git(ROOT, "show", releases[-1] + ":" + path) if releases else (ROOT / path).read_bytes()
            (root / path).write_bytes(data)
        yield root, commit(root, PACKET, "Synthetic signed-in issuance"), runpy.run_path(root / CHECKER)


def propose(root, base, paths=SIGNED_IN):
    git(root, "switch", "-C", PRODUCT, base)
    for path in paths:
        marker = b"#" if path.endswith(".py") else b"//"
        with (root / path).open("ab") as file:
            file.write(b"\n" + marker + b" Inert synthetic fixture for the issued file inventory.\n")
    return commit(root, paths, "Synthetic signed-in scope proposal")


def entries(root, revision, paths):
    return git(root, "ls-tree", "-rz", revision, "--", *sorted(paths))


@patch.dict(os.environ, GITHUB_HEAD_REF="", GITHUB_BASE_REF="", PR_HEAD_SHA="")
class FoundryV10SignedInDemoScope(unittest.TestCase):
    def allowed(self, root, checker, branch, paths):
        context = (None if branch == "main" else ("APBRA-184" if branch == INVITE else "APBRA-160"),
                   branch, set(paths))
        self.assertEqual(checker["delivery_context"](root), context)
        self.assertEqual(check_query(root, checker, *context), [])

    def denied(self, root, checker, context):
        errors = check_query(root, checker, *context)
        self.assertTrue(errors, context[:2])
        self.assertFalse(any(message.startswith("Checker failure:") for message in errors), errors)

    def historical_browser(self, root, checker):
        wrapper = runpy.run_path(root / WRAPPER)
        return wrapper["qualified_paths"](root, checker, *checker["delivery_context"](root),
                                          OVERLAP, PIN)

    def hosted(self, root, checker, base, head, branch, paths):
        hosted_checkout(root, base, head)
        with patch.dict(os.environ, GITHUB_HEAD_REF=branch, GITHUB_BASE_REF="main", PR_HEAD_SHA=head):
            self.allowed(root, checker, branch, paths)
            with patch.dict(os.environ, PR_HEAD_SHA=base):
                self.denied(root, checker, ("APBRA-160", branch, paths))

    def test_issued_packet_requires_real_transport_and_exact_physical_issuer(self):
        with issuer_fixture() as (root, head, checker):
            self.assertEqual(git(root, "show", "-s", "--format=%P", BASE).decode().split(),
                             [TRANSPORT_BASE, TRANSPORT_HEAD])
            self.assertEqual(ref(root, BASE + "^{tree}"), TRANSPORT_TREE)
            self.assertEqual(entries(root, BASE, V10_RESERVED), entries(root, TRANSPORT_HEAD, V10_RESERVED))
            task = json.loads((root / TASK).read_bytes())
            self.assertEqual(task["assigned_agent"], "APBRA-DEVOPS")
            self.assertEqual(task["base_commit"], BASE)
            self.assertEqual(task["branch"], PRODUCT)
            self.assertEqual(len(task["allowed_paths"]), 12)
            self.assertEqual(set(task["allowed_paths"]), SIGNED_IN)
            self.allowed(root, checker, ISSUER, PACKET)
            self.assertEqual(self.historical_browser(root, checker), set(OVERLAP) | PRODUCT_PATHS)
            for context in (("APBRA-85", ISSUER, PACKET), ("APBRA-160", ISSUER, PACKET - {TASK}),
                            ("APBRA-160", ISSUER, PACKET | {STYLE}), ("APBRA-160", PRODUCT, SIGNED_IN),
                            ("APBRA-160", "agent/APBRA-DEV-FE/APBRA-160-workspace-pagination-chevron", {STYLE})):
                with self.subTest(context=context[:2]):
                    self.denied(root, checker, context)
            self.hosted(root, checker, BASE, head, ISSUER, PACKET)
            git(root, "switch", ISSUER)
            git(root, "update-ref", MAIN, TRANSPORT_BASE)
            self.denied(root, checker, ("APBRA-160", ISSUER, PACKET))
            git(root, "update-ref", MAIN, BASE)
            (root / ".git").rename(root.parent / "saved-checkout-metadata")
            self.denied(root, checker, ("APBRA-160", ISSUER, PACKET))
            self.denied(root, checker, ("APBRA-160", PRODUCT, SIGNED_IN))

    def test_registration_and_product_require_ordinary_first_parent_transitions(self):
        with issuer_fixture() as (root, issuer, checker):
            propose(root, BASE)
            self.denied(root, checker, ("APBRA-160", PRODUCT, SIGNED_IN))
            tree = ref(root, issuer + "^{tree}")
            fake = ancestry_commit(root, tree, [BASE], "Synthetic nonordinary issuer")
            point_main(root, fake)
            self.denied(root, checker, (None, "main", set()))
            issued = ordinary(root, BASE, issuer, 9941, ISSUER)
            self.allowed(root, checker, "main", set())
            self.assertEqual(entries(root, issued, SIGNED_IN), entries(root, BASE, SIGNED_IN))
            names = git(root, "ls-tree", "-r", "--name-only", issued, "--", *sorted(SIGNED_IN))
            self.assertEqual(set(names.decode().splitlines()), SIGNED_IN - NEW_SOURCES)
            head = propose(root, issued)
            self.allowed(root, checker, PRODUCT, SIGNED_IN)
            self.assertEqual(self.historical_browser(root, checker), set(OVERLAP) | PRODUCT_PATHS)
            self.hosted(root, checker, issued, head, PRODUCT, SIGNED_IN)
            wrong_tree = ancestry_commit(root, ref(root, issued + "^{tree}"), [issued, head],
                                         "Synthetic checkout with wrong tree")
            git(root, "switch", "--detach", wrong_tree)
            with patch.dict(os.environ, GITHUB_HEAD_REF=PRODUCT, GITHUB_BASE_REF="main", PR_HEAD_SHA=head):
                self.denied(root, checker, ("APBRA-160", PRODUCT, SIGNED_IN))
            released = ordinary(root, issued, head, 9942, PRODUCT)
            self.allowed(root, checker, "main", set())
            self.assertEqual(entries(root, released, PROTECTED | {STYLE}), entries(root, BASE, PROTECTED | {STYLE}))
            self.assertEqual(entries(root, released, SIGNED_IN), entries(root, head, SIGNED_IN))
            self.assertEqual(self.historical_browser(root, checker), set(OVERLAP) | PRODUCT_PATHS)
            historical = root / "apps/api/src/apbra_api/model_provider.py"
            historical.write_bytes(historical.read_bytes() + b"\n")
            self.assertEqual(self.historical_browser(root, checker), set())
            git(root, "restore", "--", str(historical.relative_to(root)))
            self.assertEqual(INVITE_PATHS & SIGNED_IN, INVITE_SHARED)
            incoming = invitation_candidate(root, released)
            self.assertEqual(len(git(root, "diff", "--name-only", released, incoming).splitlines()), 28)
            self.assertNotEqual(entries(root, incoming, INVITE_SHARED), entries(root, FROZEN, INVITE_SHARED))
            self.denied(root, checker, ("APBRA-184", INVITE, INVITE_PATHS))

    def test_product_recognizes_a_real_earlier_invitation_and_its_original_28_files(self):
        with issuer_fixture() as (root, issuer, checker):
            issued = ordinary(root, BASE, issuer, 9941, ISSUER)
            incoming = invitation_candidate(root, issued)
            self.allowed(root, checker, INVITE, INVITE_PATHS)
            invited = invitation_merge(root, issued, incoming)
            point_main(root, invited)
            self.assertEqual(entries(root, invited, INVITE_PATHS), entries(root, FROZEN, INVITE_PATHS))
            self.allowed(root, checker, "main", set())
            head = propose(root, invited)
            self.allowed(root, checker, PRODUCT, SIGNED_IN)
            released = ordinary(root, invited, head, 9942, PRODUCT)
            self.allowed(root, checker, "main", set())
            self.assertEqual(entries(root, released, INVITE_PATHS - INVITE_SHARED),
                             entries(root, FROZEN, INVITE_PATHS - INVITE_SHARED))
            self.assertEqual(entries(root, released, INVITE_SHARED), entries(root, head, INVITE_SHARED))
            self.assertEqual(self.historical_browser(root, checker), set(OVERLAP) | PRODUCT_PATHS)

    def test_product_denies_wrong_branch_incomplete_mixed_dirty_or_executable_sources(self):
        with issuer_fixture() as (root, issuer, checker):
            issued = ordinary(root, BASE, issuer, 9941, ISSUER)
            for paths in (SIGNED_IN - {RECEIVER}, SIGNED_IN | {STYLE}):
                with self.subTest(paths=paths):
                    propose(root, issued, paths)
                    self.denied(root, checker, checker["delivery_context"](root))
            head = propose(root, issued)
            git(root, "switch", "-c", PRODUCT + "-other")
            self.denied(root, checker, ("APBRA-160", PRODUCT, SIGNED_IN))
            git(root, "switch", PRODUCT)
            (root / RECEIVER).write_bytes(b"# Different working bytes\n")
            self.denied(root, checker, ("APBRA-160", PRODUCT, SIGNED_IN))
            git(root, "restore", "--", RECEIVER)
            git(root, "update-index", "--chmod=+x", "--", RECEIVER)
            wrong_mode = ancestry_commit(root, git(root, "write-tree").decode().strip(), [issued],
                                         "Synthetic executable candidate")
            git(root, "reset", "--hard", wrong_mode)
            self.denied(root, checker, ("APBRA-160", PRODUCT, SIGNED_IN))
            git(root, "reset", "--hard", head)
            self.allowed(root, checker, PRODUCT, SIGNED_IN)

    def test_reverted_early_product_and_drifted_historical_companions_stay_ineligible(self):
        with issuer_fixture() as (root, issuer, checker):
            issued = ordinary(root, BASE, issuer, 9941, ISSUER)
            file = root / RECEIVER
            file.write_text("# Synthetic early product file.\n")
            early = commit(root, {RECEIVER}, "Synthetic unissued direct product touch")
            point_main(root, early)
            file.unlink()
            reverted = commit(root, {RECEIVER}, "Synthetic revert of unissued direct touch")
            point_main(root, reverted)
            self.assertEqual(ref(root, reverted + "^{tree}"), ref(root, issued + "^{tree}"))
            self.denied(root, checker, (None, "main", set()))
            # The original transport and task cannot be replaced even when working bytes
            # are restored. Check each committed entry independently of the other one.
            for path in (sorted(V10_RESERVED)[0], "tasks/APBRA-160-foundry-v10-transport-issuance-20261126.json"):
                with self.subTest(path=path):
                    point_main(root, issued)
                    target = root / path
                    original = target.read_bytes()
                    target.write_bytes(original + b"\n")
                    drift = commit(root, {path}, "Synthetic protected file change")
                    point_main(root, drift)
                    target.write_bytes(original)
                    self.denied(root, checker, (None, "main", set()))
                    git(root, "restore", "--", path)
