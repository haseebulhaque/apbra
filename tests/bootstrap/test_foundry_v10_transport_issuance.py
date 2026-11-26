"""Exercise transport issuance and its two-path successor with actual Git checkouts."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from test_foundry_report_documentation_scope import (
    CHECKER, DOCS, FROZEN, INVITE, INVITE_PATHS, MAIN, PRODUCT_PATHS, V10_PRODUCT_BRANCH,
    V10_RESERVED, WRAPPER, ancestry_commit, check_query, commit, git, hosted_checkout,
    invitation_candidate, invitation_merge, ordinary, point_main, ref,
)


ROOT = Path(__file__).resolve().parents[2]
BASE = "7312873d998efa7b420115114ae2f43535123d2c"
ISSUER = "agent/APBRA-DEVOPS/APBRA-160-foundry-v10-transport-issuance"
TASK = "tasks/APBRA-160-foundry-v10-transport-issuance-20261126.json"
ISSUANCE = {WRAPPER, TASK, "tests/bootstrap/test_foundry_v10_transport_issuance.py"}
ISSUE_CONTEXT = ("APBRA-160", ISSUER, ISSUANCE)
PRODUCT_CONTEXT = ("APBRA-160", V10_PRODUCT_BRANCH, V10_RESERVED)
MAIN_CONTEXT = (None, "main", set())


@contextmanager
def issuance_fixture():
    with tempfile.TemporaryDirectory(prefix="apbra-v10-issuance-") as directory:
        root = Path(directory) / "checkout"
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        git(root, "fetch", "--no-tags", str(ROOT), BASE + ":" + MAIN,
            FROZEN + ":refs/fixtures/frozen-invitation")
        git(root, "reset", "--hard", BASE)
        git(root, "switch", "-c", ISSUER)
        # Later product revisions must still test the first issuance's unchanged sources.
        releases = git(ROOT, "log", "--first-parent", "--diff-filter=A", "--format=%H",
                       MAIN, "--", TASK).decode().splitlines()
        for path in ISSUANCE:
            data = git(ROOT, "show", releases[-1] + ":" + path) if releases else (ROOT / path).read_bytes()
            (root / path).write_bytes(data)
        head = commit(root, ISSUANCE, "Synthetic transport issuance")
        yield root, head, runpy.run_path(root / CHECKER)


def propose_product(root, base, paths=V10_RESERVED):
    git(root, "switch", "-C", V10_PRODUCT_BRANCH, base)
    for path in paths:
        (root / path).write_text("# Inert synthetic source for the transport scope check.\n")
    return commit(root, paths, "Synthetic transport scope proposal")


@patch.dict(os.environ, GITHUB_HEAD_REF="", GITHUB_BASE_REF="", PR_HEAD_SHA="")
class FoundryV10TransportIssuance(unittest.TestCase):
    def assert_allowed(self, root, checker, context):
        self.assertEqual(checker["delivery_context"](root), context)
        self.assertEqual(check_query(root, checker, *context), [])

    def assert_denied(self, root, checker, context):
        errors = check_query(root, checker, *context)
        self.assertTrue(errors, "Unexpected governance authority for " + str(context[:2]))
        self.assertFalse(any(e.startswith("Checker failure:") for e in errors), errors)

    def assert_hosted(self, root, checker, context, base, head):
        hosted_checkout(root, base, head)
        with patch.dict(os.environ, GITHUB_HEAD_REF=context[1], GITHUB_BASE_REF="main", PR_HEAD_SHA=head):
            self.assert_allowed(root, checker, context)
            with patch.dict(os.environ, PR_HEAD_SHA=base):
                self.assert_denied(root, checker, context)

    def test_issuer_direct_and_hosted_identify_only_governance_files(self):
        with issuance_fixture() as (root, head, checker):
            task = json.loads((root / TASK).read_bytes())
            self.assertEqual(task["assigned_agent"], "APBRA-DEV-BE")
            self.assertEqual(task["branch"], V10_PRODUCT_BRANCH)
            self.assertEqual(set(task["allowed_paths"]), V10_RESERVED)
            self.assert_allowed(root, checker, ISSUE_CONTEXT)
            for context in (
                ("APBRA-85", ISSUER, ISSUANCE),
                ("APBRA-160", ISSUER, ISSUANCE - {TASK}),
                ("APBRA-160", ISSUER, ISSUANCE | V10_RESERVED),
                PRODUCT_CONTEXT,
            ):
                with self.subTest(context=context):
                    self.assert_denied(root, checker, context)
            self.assert_hosted(root, checker, ISSUE_CONTEXT, BASE, head)

    def test_registration_alone_and_nonordinary_issuance_refuse_product(self):
        with issuance_fixture() as (root, head, checker):
            point_main(root, BASE)
            propose_product(root, BASE)
            self.assert_denied(root, checker, PRODUCT_CONTEXT)
            tree = ref(root, head + "^{tree}")
            flattened = ancestry_commit(root, tree, [BASE], "Synthetic nonordinary issuance")
            point_main(root, flattened)
            self.assert_denied(root, checker, MAIN_CONTEXT)
            propose_product(root, flattened)
            self.assert_denied(root, checker, PRODUCT_CONTEXT)

    def test_product_direct_hosted_and_ordinary_release_preserve_other_sources(self):
        with issuance_fixture() as (root, issuer_head, checker):
            released = ordinary(root, BASE, issuer_head, 9901, ISSUER)
            self.assert_allowed(root, checker, MAIN_CONTEXT)
            self.assertFalse(git(root, "ls-tree", "-r", released, "--", *sorted(V10_RESERVED)))
            head = propose_product(root, released)
            self.assert_allowed(root, checker, PRODUCT_CONTEXT)
            self.assert_hosted(root, checker, PRODUCT_CONTEXT, released, head)
            # No event metadata may turn a nonmatching merge tree into this proposal.
            different = ancestry_commit(root, ref(root, released + "^{tree}"), [released, head],
                                        "Synthetic merge with prior tree")
            git(root, "switch", "--detach", different)
            with patch.dict(os.environ, GITHUB_HEAD_REF=V10_PRODUCT_BRANCH, GITHUB_BASE_REF="main",
                            PR_HEAD_SHA=head):
                self.assert_denied(root, checker, PRODUCT_CONTEXT)
            integrated = ordinary(root, released, head, 9902, V10_PRODUCT_BRANCH)
            self.assert_allowed(root, checker, MAIN_CONTEXT)
            for paths, expected in ((ISSUANCE, issuer_head), (V10_RESERVED, head),
                                    (DOCS | PRODUCT_PATHS, BASE)):
                with self.subTest(expected=expected):
                    args = ("--", *sorted(paths))
                    self.assertEqual(git(root, "ls-tree", "-rz", integrated, *args),
                                     git(root, "ls-tree", "-rz", expected, *args))
            invite = invitation_candidate(root, integrated)
            self.assert_allowed(root, checker, ("APBRA-184", INVITE, INVITE_PATHS))
            merged = invitation_merge(root, integrated, invite)
            point_main(root, merged)
            self.assert_allowed(root, checker, MAIN_CONTEXT)
            args = ("--", *sorted(INVITE_PATHS))
            self.assertEqual(git(root, "ls-tree", "-rz", merged, *args),
                             git(root, "ls-tree", "-rz", FROZEN, *args))
            path = sorted(V10_RESERVED)[0]
            (root / path).write_text("# Replacement after the qualified release.\n")
            drift = commit(root, {path}, "Synthetic unreviewed change after product release")
            point_main(root, drift)
            self.assert_denied(root, checker, MAIN_CONTEXT)

    def test_product_requires_both_regular_files_and_exact_checkout(self):
        with issuance_fixture() as (root, issuer_head, checker):
            released = ordinary(root, BASE, issuer_head, 9901, ISSUER)
            path = sorted(V10_RESERVED)[0]
            propose_product(root, released, {path})
            self.assert_denied(root, checker, checker["delivery_context"](root))
            head = propose_product(root, released)
            file = root / path
            file.write_bytes(file.read_bytes() + b"# Changed after commit\n")
            self.assert_denied(root, checker, PRODUCT_CONTEXT)
            git(root, "restore", "--", path)
            git(root, "update-index", "--chmod=+x", "--", path)
            executable = ancestry_commit(root, git(root, "write-tree").decode().strip(),
                                         [released], "Synthetic executable entry")
            git(root, "reset", "--hard", executable)
            self.assert_denied(root, checker, PRODUCT_CONTEXT)
            git(root, "reset", "--hard", head)
            git(root, "update-ref", MAIN, BASE)
            self.assert_denied(root, checker, PRODUCT_CONTEXT)
            git(root, "update-ref", MAIN, released)
            git(root, "switch", "-c", ISSUER + "-unrelated")
            self.assert_denied(root, checker, PRODUCT_CONTEXT)
            git(root, "switch", V10_PRODUCT_BRANCH)
            extra = "README.md"
            (root / extra).write_bytes((root / extra).read_bytes() + b"\n")
            git(root, "add", "--", extra)
            mixed = ancestry_commit(root, git(root, "write-tree").decode().strip(),
                                    [released], "Synthetic proposal with a third path")
            git(root, "reset", "--hard", mixed)
            self.assert_denied(root, checker, checker["delivery_context"](root))

    def test_historical_source_and_reverted_early_product_are_rejected(self):
        with issuance_fixture() as (root, issuer_head, checker):
            historical = root / "docs/source-register-apbra160-v10-report-transport.json"
            historical.write_bytes(historical.read_bytes() + b"\n")
            self.assert_denied(root, checker, ISSUE_CONTEXT)
            git(root, "restore", "--", str(historical.relative_to(root)))
            released = ordinary(root, BASE, issuer_head, 9901, ISSUER)
            path = sorted(V10_RESERVED)[0]
            (root / path).write_text("# Synthetic unissued early path.\n")
            introduced = commit(root, {path}, "Synthetic change outside an ordinary release")
            point_main(root, introduced)
            self.assert_denied(root, checker, MAIN_CONTEXT)
            (root / path).unlink()
            self.assert_denied(root, checker, MAIN_CONTEXT)
            removed = commit(root, {path}, "Synthetic removal of that path")
            point_main(root, removed)
            self.assertEqual(ref(root, removed + "^{tree}"), ref(root, released + "^{tree}"))
            self.assert_denied(root, checker, MAIN_CONTEXT)

    def test_source_only_issuance_and_product_queries_have_no_authority(self):
        with issuance_fixture() as (root, _, checker):
            (root / ".git").rename(root.parent / "saved-metadata")
            self.assert_denied(root, checker, ISSUE_CONTEXT)
            self.assert_denied(root, checker, PRODUCT_CONTEXT)
            for path in V10_RESERVED:
                (root / path).write_text("# Inert future released source for a historical inventory.\n")
            historical_context = ("APBRA-174", checker["MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_BRANCH"],
                                  checker["MODEL_LED_FLEXIBLE_DELIVERY_AMENDMENT_PATHS"])
            self.assertEqual(check_query(root, checker, *historical_context), [])
            self.assert_denied(root, checker, ISSUE_CONTEXT)
            self.assert_denied(root, checker, PRODUCT_CONTEXT)
