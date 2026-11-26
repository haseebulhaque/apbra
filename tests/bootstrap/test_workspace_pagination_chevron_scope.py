"""Exercise the independent pagination issue, exact CSS and both ordinary PR185 orders."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from test_foundry_report_documentation_scope import (
    CHECKER, FROZEN, INVITE, INVITE_PATHS, MAIN, V10_PRODUCT_BRANCH, V10_RESERVED, WRAPPER,
    ancestry_commit, check_query, commit, git, hosted_checkout, invitation_candidate, invitation_merge,
    ordinary, point_main, ref,
)
from test_foundry_v10_signed_in_demo_scope import PRODUCT as SIGNEDIN_PRODUCT, SIGNED_IN, propose as signedin_candidate
from test_native_invitation_release_readback import OVERLAP, PIN, PRODUCT_PATHS

ROOT = Path(__file__).resolve().parents[2]
PR201 = "959f39a89911b05e278feedd0cdc8edd8e1d77d9"
BASE = "a1ec568eefae3e4e8d41cafe6be239dc7c84fb20"
PR200 = "bfb87010d2a4f7571069522ce57438a35f720391"
TRANSPORT_HEAD = "5f4f082fb17358ed77d3c119d8f46ccd628ac179"
ISSUER = "agent/APBRA-DEVOPS/APBRA-160-workspace-pagination-chevron-issuance"
PRODUCT = "agent/APBRA-DEV-FE/APBRA-160-workspace-pagination-chevron"
TASK = "tasks/APBRA-160-workspace-pagination-chevron-20261126.json"
ISSUANCE = {TASK, WRAPPER, "tests/bootstrap/test_workspace_pagination_chevron_scope.py"}
STYLE = "apps/web/src/style.css"
INVITE_STYLE = "df910c2cd12ba284d5ccb1fcc7df78c895dddd89"
COMBINED = "5d640d25164f952a1aeceb1924f488fec7a8218e"
RULE = b'''@media (forced-colors: none) {
  .private-workspace .pagination-summary select:not([multiple]):is(:not([size]), [size="1"]) {
    appearance: none;
    min-inline-size: 88px;
    padding-inline: 12px 36px;
    --chevron-stroke: transparent 34%, currentColor 44% 56%, transparent 66%;
    background-image: linear-gradient(45deg, var(--chevron-stroke)),
                      linear-gradient(-45deg, var(--chevron-stroke));
    background-position: right 18px center, right 12px center;
    background-size: 6px 6px;
    background-repeat: no-repeat;
  }
  .private-workspace .pagination-summary select:dir(rtl):not([multiple]):is(:not([size]), [size="1"]) {
    background-position: left 12px center, left 18px center;
  }
}
'''


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(prefix="apbra-pagination-") as directory:
        root = Path(directory) / "checkout"
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        git(root, "fetch", "--no-tags", str(ROOT), BASE + ":" + MAIN, FROZEN + ":refs/fixtures/invitation")
        git(root, "reset", "--hard", BASE)
        git(root, "switch", "-c", ISSUER)
        releases = git(ROOT, "log", "--first-parent", "--diff-filter=A", "--format=%H", MAIN, "--", TASK)
        for path in ISSUANCE:
            data = git(ROOT, "show", releases.decode().split()[-1] + ":" + path) if releases else (ROOT / path).read_bytes()
            (root / path).write_bytes(data)
        yield root, commit(root, ISSUANCE, "Synthetic finite pagination issuance"), runpy.run_path(root / CHECKER)


def style_candidate(root, base):
    git(root, "switch", "-C", PRODUCT, base)
    file = root / STYLE
    original = file.read_bytes()
    marker = b".record-pagination button{min-width:44px"
    if original.count(marker) != 1:
        raise AssertionError("Original pagination insertion point differs")
    file.write_bytes(original.replace(marker, RULE + marker))
    return commit(root, {STYLE}, "Synthetic selected pagination source")


def invitation_prior(root):
    scope = runpy.run_path(root / WRAPPER)
    readback, state, metadata, original = scope["invitation_readback_context"](root)
    invitation = runpy.run_path(root / "scripts/native_invitation_scope.py")
    return readback["invitation_release_before"](root, metadata, state, invitation, original["raw"])


@patch.dict(os.environ, GITHUB_HEAD_REF="", GITHUB_BASE_REF="", PR_HEAD_SHA="")
class WorkspacePaginationChevronScope(unittest.TestCase):
    def allowed(self, root, checker):
        self.assertEqual(check_query(root, checker, *checker["delivery_context"](root)), [])

    def historical_browser(self, root, checker):
        scope = runpy.run_path(root / WRAPPER)
        return scope["qualified_paths"](root, checker, *checker["delivery_context"](root), OVERLAP, PIN)

    def denied(self, root, checker, context):
        faults = check_query(root, checker, *context)
        self.assertTrue(faults, context)
        self.assertFalse(any(f.startswith("Checker failure:") for f in faults), faults)

    def hosted(self, root, checker, before, head, branch):
        hosted_checkout(root, before, head)
        with patch.dict(os.environ, GITHUB_HEAD_REF=branch, GITHUB_BASE_REF="main", PR_HEAD_SHA=head):
            self.allowed(root, checker)
            with patch.dict(os.environ, PR_HEAD_SHA=before):
                self.denied(root, checker, checker["delivery_context"](root))

    def test_registration_requires_physical_issued_branch_and_all_three_regular_files(self):
        with fixture() as (root, head, checker):
            self.allowed(root, checker)
            for context in (("APBRA-85", ISSUER, ISSUANCE), ("APBRA-160", ISSUER, ISSUANCE - {TASK}),
                            ("APBRA-160", ISSUER, ISSUANCE | {STYLE}), ("APBRA-160", PRODUCT, {STYLE})):
                self.denied(root, checker, context)
            self.hosted(root, checker, BASE, head, ISSUER)
            (root / ".git").rename(root.parent / "saved-git")
            self.denied(root, checker, ("APBRA-160", ISSUER, ISSUANCE))
            self.denied(root, checker, ("APBRA-160", PRODUCT, {STYLE}))

    def test_invitation_first_and_css_first_preserve_exact_frozen_27_and_two_levels(self):
        for invitation_first in (True, False):
            with self.subTest(invitation_first=invitation_first), fixture() as (root, issuance, checker):
                issued = ordinary(root, BASE, issuance, 9931, ISSUER)
                self.allowed(root, checker)
                before = issued
                if invitation_first:
                    incoming = invitation_candidate(root, issued)
                    self.allowed(root, checker)
                    before = invitation_merge(root, issued, incoming)
                    point_main(root, before)
                    self.assertEqual(invitation_prior(root), issued)
                    self.assertEqual(ref(root, "HEAD:" + STYLE), INVITE_STYLE)
                css = style_candidate(root, before)
                self.allowed(root, checker)
                self.hosted(root, checker, before, css, PRODUCT)
                cosmetic = ordinary(root, before, css, 9932, PRODUCT)
                self.allowed(root, checker)
                if invitation_first:
                    expected_prior = issued
                else:
                    self.assertIsNone(invitation_prior(root))
                    self.assertEqual(self.historical_browser(root, checker), set(OVERLAP) | PRODUCT_PATHS)
                    other = root / "apps/api/src/apbra_api/model_provider.py"
                    other.write_bytes(other.read_bytes() + b"\n")
                    self.assertEqual(self.historical_browser(root, checker), set())
                    git(root, "restore", "--", "apps/api/src/apbra_api/model_provider.py")
                    incoming = invitation_candidate(root, cosmetic)
                    self.allowed(root, checker)
                    self.hosted(root, checker, cosmetic, incoming, INVITE)
                    result = invitation_merge(root, cosmetic, incoming)
                    point_main(root, result)
                    expected_prior = cosmetic
                self.allowed(root, checker)
                self.assertEqual(invitation_prior(root), expected_prior)
                self.assertEqual(self.historical_browser(root, checker), set(OVERLAP) | PRODUCT_PATHS)
                scope = runpy.run_path(root / WRAPPER)
                reader, state, metadata, old = scope["invitation_readback_context"](root)
                invite = runpy.run_path(root / "scripts/native_invitation_scope.py")
                wrong_paths = (invite["P"] - {STYLE}) | {"README.md"}
                with self.assertRaisesRegex(ValueError, "Frozen invitation source"):
                    reader["invitation_release_before"](root, metadata, state, dict(invite, P=wrong_paths), old["raw"])
                self.assertEqual(ref(root, "HEAD:" + STYLE), COMBINED)
                args = ("--", *sorted(INVITE_PATHS - {STYLE}))
                self.assertEqual(len(args) - 1, 27)
                self.assertEqual(git(root, "ls-tree", "-rz", "HEAD", *args),
                                 git(root, "ls-tree", "-rz", FROZEN, *args))

    def test_actual_pr201_transport_is_frozen_across_ordinary_pagination_release(self):
        with fixture() as (root, issuer, checker):
            self.assertEqual(git(root, "rev-list", "-n1", "--parents", PR201).decode().split(),
                             [PR201, PR200, TRANSPORT_HEAD])
            entries = ("--", *sorted(V10_RESERVED))
            reviewed = git(root, "ls-tree", "-rz", TRANSPORT_HEAD, *entries)
            self.assertEqual(git(root, "ls-tree", "-rz", BASE, *entries), reviewed)
            issued = ordinary(root, BASE, issuer, 9931, ISSUER)
            head = style_candidate(root, issued)
            self.allowed(root, checker)
            self.hosted(root, checker, issued, head, PRODUCT)
            effective = ordinary(root, issued, head, 9932, PRODUCT)
            self.allowed(root, checker)
            self.assertEqual(git(root, "ls-tree", "-rz", effective, *entries), reviewed)
            self.denied(root, checker, ("APBRA-160", V10_PRODUCT_BRANCH, V10_RESERVED))
            for path in sorted(V10_RESERVED):
                with self.subTest(path=path):
                    file = root / path
                    file.write_bytes(file.read_bytes() + b"\n")
                    self.denied(root, checker, (None, "main", set()))
                    git(root, "restore", "--", path)

    def test_issuer_preceding_actual_pr201_or_stale_normal_refresh_is_denied(self):
        with fixture() as (root, issuer, checker):
            point_main(root, PR200)
            git(root, "switch", "-C", ISSUER, PR200)
            git(root, "restore", "--source", issuer, "--staged", "--worktree", "--", *sorted(ISSUANCE))
            git(root, "commit", "-m", "Synthetic issuer before real transport release")
            self.denied(root, checker, ("APBRA-160", ISSUER, ISSUANCE))
            git(root, "update-ref", MAIN, BASE)
            # The sibling changed the same checker. Preserve the resolved exact tree
            # and both normal merge parents so the physical gate must still refuse it.
            stale = ref(root)
            merged = ancestry_commit(root, ref(root, issuer + "^{tree}"), [stale, BASE],
                                     "Synthetic resolved stale normal main update", github=False)
            git(root, "switch", "-C", ISSUER, merged)
            self.denied(root, checker, ("APBRA-160", ISSUER, ISSUANCE))
            self.assertEqual(ref(root, "HEAD^{tree}"), ref(root, issuer + "^{tree}"))

    def test_old_plan_cannot_register_after_an_ordinary_invitation_release(self):
        with fixture() as (root, original, checker):
            invitation = invitation_candidate(root, BASE)
            later = invitation_merge(root, BASE, invitation)
            point_main(root, later)
            git(root, "switch", "-C", ISSUER, later)
            git(root, "restore", "--source", original, "--staged", "--worktree", "--", *sorted(ISSUANCE))
            stale = commit(root, ISSUANCE, "Synthetic unchanged pagination packet on later main")
            self.assertEqual(git(root, "ls-tree", "-rz", original, "--", *sorted(ISSUANCE)),
                             git(root, "ls-tree", "-rz", stale, "--", *sorted(ISSUANCE)))
            self.denied(root, checker, checker["delivery_context"](root))
            hosted_checkout(root, later, stale)
            with patch.dict(os.environ, GITHUB_HEAD_REF=ISSUER, GITHUB_BASE_REF="main", PR_HEAD_SHA=stale):
                self.denied(root, checker, checker["delivery_context"](root))
            ordinary(root, later, stale, 9937, ISSUER)
            self.denied(root, checker, checker["delivery_context"](root))

    def test_transport_companion_head_entries_are_checked_with_restored_working_sources(self):
        with fixture() as (root, issuer, checker):
            issued = ordinary(root, BASE, issuer, 9931, ISSUER)
            scope = runpy.run_path(root / WRAPPER)
            for path in sorted(scope["V10_ISSUANCE_PATHS"] - {WRAPPER}):
                with self.subTest(path=path):
                    git(root, "switch", "-C", "retained-entry-check", issued)
                    file = root / path
                    original = file.read_bytes()
                    file.write_bytes(original + b"\n")
                    commit(root, {path}, "Synthetic different committed companion entry")
                    file.write_bytes(original)
                    readback, metadata, old = scope["_v10_previous_sources"](root)
                    with self.assertRaisesRegex(ValueError, "exact ordinary three-path issuance"):
                        scope["v10_issuance_state"](root, readback, metadata, old["raw"])
                    git(root, "restore", "--", path)

    def test_original_signed_in_governance_remains_an_exact_first_ordinary_release(self):
        with fixture() as (root, issuer, checker):
            before = ordinary(root, BASE, issuer, 9931, ISSUER)
            self.allowed(root, checker)
            signedin = runpy.run_path(root / WRAPPER)
            previous = signedin["SIGNEDIN_PACKET"] - {WRAPPER}
            self.assertEqual(git(root, "ls-tree", "-rz", BASE, "--", *sorted(previous)),
                             git(root, "ls-tree", "-rz", before, "--", *sorted(previous)))
            self.denied(root, checker, ("APBRA-160", signedin["SIGNEDIN_ISSUER"], signedin["SIGNEDIN_PACKET"]))

    def test_signed_in_product_before_registration_requires_a_new_issued_base(self):
        with fixture() as (root, original, checker):
            proposal = signedin_candidate(root, BASE)
            released = ordinary(root, BASE, proposal, 9934, SIGNEDIN_PRODUCT)
            git(root, "switch", "-C", ISSUER, released)
            git(root, "restore", "--source", original, "--staged", "--worktree", "--", *sorted(ISSUANCE))
            stale = commit(root, ISSUANCE, "Synthetic unchanged Home registration on a later product")
            self.denied(root, checker, checker["delivery_context"](root))
            hosted_checkout(root, released, stale)
            with patch.dict(os.environ, GITHUB_HEAD_REF=ISSUER, GITHUB_BASE_REF="main", PR_HEAD_SHA=stale):
                self.denied(root, checker, checker["delivery_context"](root))
            ordinary(root, released, stale, 9937, ISSUER)
            self.denied(root, checker, checker["delivery_context"](root))

    def test_signed_in_and_pagination_product_entries_are_retained_in_both_orders(self):
        for signedin_first in (False, True):
            with self.subTest(signedin_first=signedin_first), fixture() as (root, registration, checker):
                issued = ordinary(root, BASE, registration, 9931, ISSUER)
                before = issued
                branches = (SIGNEDIN_PRODUCT, PRODUCT) if signedin_first else (PRODUCT, SIGNEDIN_PRODUCT)
                sources = {}
                for number, branch in enumerate(branches, 9935):
                    if branch == SIGNEDIN_PRODUCT:
                        child = signedin_candidate(root, before)
                        selected = SIGNED_IN
                    else:
                        child = style_candidate(root, before)
                        selected = {STYLE}
                    self.allowed(root, checker)
                    before = ordinary(root, before, child, number, branch)
                    sources[child] = selected
                self.allowed(root, checker)
                self.assertEqual(self.historical_browser(root, checker), set(OVERLAP) | PRODUCT_PATHS)
                for child, selected in sources.items():
                    arguments = ("--", *sorted(selected))
                    self.assertEqual(git(root, "ls-tree", "-rz", before, *arguments),
                                     git(root, "ls-tree", "-rz", child, *arguments))

    def test_prior_signed_in_companions_check_actual_head_with_working_source_restored(self):
        with fixture() as (root, issuer, _):
            issued = ordinary(root, BASE, issuer, 9931, ISSUER)
            scope = runpy.run_path(root / WRAPPER)
            for path in sorted(scope["SIGNEDIN_PACKET"] - {WRAPPER}):
                with self.subTest(path=path):
                    git(root, "switch", "-C", "earlier-companion-check", issued)
                    original = (root / path).read_bytes()
                    (root / path).write_bytes(original + b"\n")
                    commit(root, {path}, "Synthetic different committed signed-in companion")
                    (root / path).write_bytes(original)
                    reader, metadata, actual = scope["_v10_previous_sources"](root)
                    with self.assertRaisesRegex(ValueError, "Earlier signed-in task or test"):
                        scope["pager_state"](root, reader, metadata, actual["raw"])
                    git(root, "restore", "--", path)

    def test_extra_css_or_path_nonordinary_release_and_frozen_entry_changes_are_denied(self):
        with fixture() as (root, issuer, checker):
            issued = ordinary(root, BASE, issuer, 9931, ISSUER)
            css = style_candidate(root, issued)
            git(root, "switch", "-C", PRODUCT, css)
            path = root / STYLE
            path.write_bytes(path.read_bytes() + b"\n")
            extra_css = commit(root, {STYLE}, "Synthetic additional CSS")
            tree = ref(root, extra_css + "^{tree}")
            direct = ancestry_commit(root, tree, [issued], "Synthetic additional style bytes")
            git(root, "reset", "--hard", direct)
            self.denied(root, checker, ("APBRA-160", PRODUCT, {STYLE}))
            extra = "README.md"
            git(root, "reset", "--hard", css)
            (root / extra).write_bytes((root / extra).read_bytes() + b"\n")
            mixed = commit(root, {extra}, "Synthetic extra path")
            direct = ancestry_commit(root, ref(root, mixed + "^{tree}"), [issued], "Synthetic mixed source")
            git(root, "reset", "--hard", direct)
            self.denied(root, checker, checker["delivery_context"](root))
            flattened = ancestry_commit(root, ref(root, css + "^{tree}"), [issued], "Synthetic nonordinary release")
            point_main(root, flattened)
            self.denied(root, checker, (None, "main", set()))
            point_main(root, issued)
            cosmetic = ordinary(root, issued, css, 9932, PRODUCT)
            invite = invitation_candidate(root, cosmetic)
            other = sorted(INVITE_PATHS - {STYLE})[0]
            (root / other).write_bytes((root / other).read_bytes() + b"\n")
            changed = commit(root, {other}, "Synthetic altered invitation entry")
            refresh = ancestry_commit(root, ref(root, changed + "^{tree}"), [FROZEN, cosmetic], "Synthetic refresh")
            git(root, "reset", "--hard", refresh)
            self.denied(root, checker, checker["delivery_context"](root))
            self.assertNotEqual(invite, refresh)
