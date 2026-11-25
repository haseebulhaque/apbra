"""Verify exact issue 193 scope and preserved release authority in isolated Git fixtures."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from test_native_invitation_release_readback import (
    CHECKER, FROZEN, INVITE, INVITE_PATHS, MAIN, OVERLAP, PIN, PRODUCT, PRODUCT_PATHS, WRAPPER,
    ancestry_commit, candidate as invitation_candidate, git, invitation_merge, metadata_candidate,
    metadata_release, point_main, ref,
)


ROOT = Path(__file__).resolve().parents[2]
SCOPE = runpy.run_path(ROOT / WRAPPER)
ANCHOR = SCOPE["REPORT_DOCS_ANCHOR"]
REGISTRATION = SCOPE["REPORT_DOCS_REGISTRATION"]
REGISTRATION_BRANCH = SCOPE["REPORT_DOCS_REGISTRATION_BRANCH"]
DOCS = SCOPE["REPORT_DOCS_PATHS"]
DOCS_BRANCH = SCOPE["REPORT_DOCS_BRANCH"]
PRIOR_DOCS_BRANCH = "agent/APBRA-DEVOPS/APBRA-148-post-capstone-product-reconciliation"
SOURCE = SCOPE["REPORT_DOCS_SOURCE"]
TASK = SCOPE["REPORT_DOCS_TASK"]
PR196 = "3b5ca7a840b40bdcb3571a1e4aca4809bcd33256"
CORRECTION_BRANCH = "agent/APBRA-DEVOPS/APBRA-160-issue193-checkout-correction"
CORRECTION = {WRAPPER, SCOPE["REPORT_DOCS_TEST"]}
# Git tree entries for the eight approved files in the retained documentation candidate.
APPROVED_DOC_ENTRIES_SHA256 = "1d960d4e79117fe91499a368ce7985131683578cd9d8a36ea7c45c7e71fb077d"
DIRECTION = {'AI-RAG-SPEC.md': 'Versioned system instructions specify the required report structure, confirmed '
                   'business requirements and permitted inputs. The configured Foundry LLM and its '
                   'authorised tools must generate and compile the complete downloadable report. A '
                   'standalone ReportDesign is intermediate evidence. APBRA validates the finished '
                   'artifact and controls delivery.',
 'ARCHITECTURE.md': 'Target MVP artifact flow: confirmed requirements and permitted inputs → Foundry '
                    'generation and compilation → APBRA validation, provenance and protected download. '
                    'The current implementation described below includes the earlier APBRA compiler. '
                    'The target runtime and the exact agent capability remain to be qualified.',
 'MVP-ACCEPTANCE-CRITERIA.md': 'Report-generation acceptance requires a recorded run on the configured '
                               'Foundry agent version that generates and compiles the finished report, '
                               'then an authenticated download, successful Power BI open and '
                               'verification that the report answers the confirmed request. The '
                               'earlier synthetic APBRA compiler run provides build and download '
                               'evidence for that earlier route.',
 'POWERBI-GENERATION-SPEC.md': 'Foundry generates and compiles the complete Power BI project artifact. '
                               'APBRA supplies the required structure and checks the resulting package '
                               'for safety, compatibility and fidelity to the confirmed request. The '
                               'technical constraints and existing compiler evidence below retain '
                               'their original scope.',
 'README.md': 'The Foundry LLM and its authorised tools generate and compile the complete downloadable '
              'Power BI report. APBRA supplies instructions and confirmed inputs, validates the '
              'returned artifact and provides the protected download. Current implementation '
              'descriptions below record the earlier APBRA compiler route. Live Foundry generation '
              'remains unverified.',
 'REQUIREMENTS.md': 'The MVP requires the configured Foundry LLM and its authorised tools to produce '
                    'the complete downloadable report from confirmed requirements and permitted '
                    'inputs. APBRA provides the structural instructions and owns authorisation, '
                    'artifact validation and delivery. Use this requirement where earlier sections '
                    'describe an APBRA-owned compiler.',
 'docs/decisions/implementation-baseline.md': 'The owner selected generation and compilation of the '
                                              'complete downloadable report by Foundry. APBRA provides '
                                              'instructions, access controls, artifact validation and '
                                              'delivery. The existing compiler is implementation and '
                                              'test history for the earlier route. Record the updated '
                                              'architecture and issue a bounded task before changing '
                                              'the runtime.',
 'docs/engineering/codex-handoff.md': 'Next report-runtime work must follow the owner-selected Foundry '
                                      'generation and compilation requirement. Preserve previous '
                                      'compiler receipts, qualify exact agent and artifact-return '
                                      'capability, then record a live generation, authenticated '
                                      'download, Power BI open and result check.'}


def commit(root, paths, message):
    git(root, "add", "--", *sorted(paths))
    git(root, "commit", "-m", message)
    return ref(root)


def docs_candidate(root, *, drift=False):
    git(root, "switch", "-C", DOCS_BRANCH)
    for name, paragraph in DIRECTION.items():
        file = root / name
        first, rest = file.read_bytes().split(b"\n\n", 1)
        prefix = (
            "\n\n## Current MVP report-generation direction\n\n" + paragraph + "\n\n"
            "[Confluence generation and acceptance contract]"
            "(https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/9404417)\n\n"
        )
        if drift and name == "README.md":
            paragraph = paragraph + " Different bytes."
            prefix = prefix.replace(DIRECTION[name], paragraph)
        file.write_bytes(first + prefix.encode() + rest)
    return commit(root, DOCS, "Synthetic exact approved documentation")


def ordinary(root, base, head, number, branch):
    point_main(root, base)
    git(root, "merge", "--no-ff", head,
        "-m", f"Merge pull request #{number} from haseebulhaque/{branch}", github=True)
    merged = ref(root)
    git(root, "update-ref", MAIN, merged)
    return merged


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(prefix="apbra-issue193-scope-") as directory:
        root = Path(directory)
        git(root, "init", "-q", "-b", "main")
        git(root, "fetch", "--no-tags", str(ROOT), ANCHOR + ":" + MAIN,
            FROZEN + ":refs/fixtures/frozen-invitation")
        git(root, "reset", "--hard", ANCHOR)
        git(root, "switch", "-c", REGISTRATION_BRANCH)
        for name in REGISTRATION:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            # Rebuild this historical registration from its reviewed, released packet.
            target.write_bytes(git(ROOT, "show", PR196 + ":" + name))
        head = commit(root, REGISTRATION, "Synthetic four-file issue 193 registration")
        checker = runpy.run_path(root / CHECKER)
        yield root, head, checker


@patch.dict(os.environ, GITHUB_HEAD_REF="", GITHUB_BASE_REF="", PR_HEAD_SHA="")
class FoundryReportDocumentationScope(unittest.TestCase):
    def faults(self, root, checker, identity=None, branch=None, paths=None):
        actual = checker["delivery_context"](root)
        return checker["check"](
            root, active_task_id=actual[0] if identity is None else identity,
            active_branch=actual[1] if branch is None else branch,
            changed_paths=actual[2] if paths is None else paths,
        )[0]

    def test_exact_four_path_registration_and_hosted_identity(self):
        with fixture() as (root, head, checker):
            self.assertEqual(self.faults(root, checker), [])
            wrapper = runpy.run_path(root / WRAPPER)
            def historical_paths():
                context = checker["delivery_context"](root)
                return wrapper["qualified_paths"](root, checker, *context, OVERLAP, PIN)

            self.assertEqual(historical_paths(), set(OVERLAP))
            for identity, branch, paths in (
                ("APBRA-85", REGISTRATION_BRANCH, REGISTRATION),
                ("APBRA-160", REGISTRATION_BRANCH, REGISTRATION - {SOURCE}),
                ("APBRA-160", REGISTRATION_BRANCH, REGISTRATION | {"README.md"}),
                ("APBRA-160", REGISTRATION_BRANCH + "-other", REGISTRATION),
            ):
                with self.subTest(identity=identity, branch=branch, paths=paths):
                    self.assertTrue(self.faults(root, checker, identity, branch, paths))
            tree = ref(root, head + "^{tree}")
            hosted = ancestry_commit(root, tree, [ANCHOR, head], "Synthetic GitHub check merge")
            git(root, "switch", "--detach", hosted)
            with patch.dict(os.environ, GITHUB_HEAD_REF=REGISTRATION_BRANCH, GITHUB_BASE_REF="main",
                            PR_HEAD_SHA=head):
                self.assertEqual(self.faults(root, checker), [])
                self.assertEqual(historical_paths(), set(OVERLAP))
                with patch.dict(os.environ, PR_HEAD_SHA=ANCHOR):
                    self.assertTrue(self.faults(root, checker))
                    self.assertEqual(historical_paths(), set())

    def test_prior_wrapper_and_source_pins_are_exact(self):
        previous = git(ROOT, "show", ANCHOR + ":" + WRAPPER)
        source = (ROOT / WRAPPER).read_bytes()
        restore, marker = SCOPE["strip_report_docs_wrapper"], SCOPE["REPORT_DOCS_MARKER"]
        self.assertEqual(restore(source), previous)
        for mutation in (source + marker, source.replace(marker, b"", 1), b"# drift\n" + source):
            with self.assertRaises(ValueError):
                restore(mutation)
        with fixture() as (root, _, checker):
            for name in (SOURCE, TASK, "docs/source-register.json"):
                target = root / name
                original = target.read_bytes()
                target.write_bytes(original + b"\n")
                self.assertTrue(self.faults(root, checker))
                target.write_bytes(original)

    def test_docs_require_ordinary_registration_and_exact_approved_bytes(self):
        with fixture() as (root, head, checker):
            exact = docs_candidate(root)
            self.assertTrue(self.faults(root, checker, paths=DOCS))
            released = ordinary(root, ANCHOR, head, 9821, REGISTRATION_BRANCH)
            self.assertEqual(self.faults(root, checker), [])
            git(root, "switch", "-C", DOCS_BRANCH, released)
            self.assertTrue(self.faults(root, checker, paths=DOCS))
            exact = docs_candidate(root)
            self.assertEqual(self.faults(root, checker), [])
            register = SCOPE["report_docs_packet"](root)[1]
            self.assertEqual(register["approved_patch_sha256"],
                             "cc41fab307718dbcd7cfa43298397c7ac6dc54bb1a3dfce8608f1be30f450f31")
            for name in sorted(DOCS):
                self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(),
                                 register["approved_markdown"][name]["approved_sha256"])
            self.assertTrue(self.faults(root, checker, "APBRA-85", DOCS_BRANCH, DOCS))
            self.assertTrue(self.faults(root, checker, paths=DOCS | {"compose.yaml"}))
            self.assertTrue(self.faults(root, checker, paths=DOCS - {"README.md"}))

            git(root, "reset", "--hard", released)
            docs_candidate(root, drift=True)
            self.assertTrue(self.faults(root, checker))
            ordinary(root, released, exact, 9822, DOCS_BRANCH)
            self.assertEqual(self.faults(root, checker), [])
            target = root / "README.md"
            target.write_bytes(target.read_bytes() + b"\n# Unapproved effective content\n")
            drift = commit(root, {"README.md"}, "Synthetic unauthorized Markdown drift")
            point_main(root, drift)
            self.assertTrue(self.faults(root, checker))

    def test_previous_docs_branch_cannot_break_registered_or_released_bytes(self):
        with fixture() as (root, head, checker):
            registration = ordinary(root, ANCHOR, head, 9825, REGISTRATION_BRANCH)
            approved = docs_candidate(root)
            release = ordinary(root, registration, approved, 9826, DOCS_BRANCH)
            for effective, expected in (
                (registration, "preimages must remain exact"),
                (release, "continued approved bytes differ"),
            ):
                with self.subTest(base=effective):
                    point_main(root, effective)
                    self.assertEqual(self.faults(root, checker), [])
                    git(root, "switch", "-C", PRIOR_DOCS_BRANCH)
                    target = root / "README.md"
                    target.write_bytes(target.read_bytes() + b"\n# Competing documentation\n")
                    commit(root, {"README.md"}, "Synthetic competing documentation")
                    self.assertTrue(any(expected in fault for fault in self.faults(root, checker)))
                    point_main(root, effective)
                    target.chmod(0o755)
                    self.assertTrue(any(expected in fault for fault in self.faults(root, checker)))
                    target.chmod(0o644)
                    self.assertEqual(self.faults(root, checker), [])

    def test_wrong_governance_merge_shape_and_later_packet_drift_are_denied(self):
        with fixture() as (root, head, checker):
            tree = ref(root, head + "^{tree}")
            forged = ancestry_commit(root, tree, [ANCHOR, head], "Different owner merge subject")
            point_main(root, forged)
            self.assertTrue(self.faults(root, checker))
            single_parent = ancestry_commit(
                root, tree, [ANCHOR], "Merge pull request #9823 from haseebulhaque/" + REGISTRATION_BRANCH,
            )
            point_main(root, single_parent)
            self.assertTrue(self.faults(root, checker))
            released = ordinary(root, ANCHOR, head, 9823, REGISTRATION_BRANCH)
            self.assertEqual(self.faults(root, checker), [])
            test = root / SCOPE["REPORT_DOCS_TEST"]
            test.write_bytes(test.read_bytes() + b"\n# Synthetic packet drift\n")
            changed = commit(root, {SCOPE["REPORT_DOCS_TEST"]}, "Synthetic registration drift")
            point_main(root, changed)
            self.assertTrue(self.faults(root, checker))
            git(root, "reset", "--hard", released)

    def test_registered_docs_compose_with_metadata_and_exact_invitation(self):
        with fixture() as (root, head, checker):
            registered = ordinary(root, ANCHOR, head, 9824, REGISTRATION_BRANCH)
            metadata = metadata_candidate(root)
            self.assertEqual(checker["delivery_context"](root), ("APBRA-160", PRODUCT, PRODUCT_PATHS))
            self.assertEqual(self.faults(root, checker), [])
            main = metadata_release(root, metadata, registered)
            self.assertEqual(self.faults(root, checker), [])
            invitation = invitation_candidate(root, main)
            self.assertEqual(checker["delivery_context"](root), ("APBRA-184", INVITE, INVITE_PATHS))
            self.assertEqual(self.faults(root, checker), [])
            released = invitation_merge(root, main, invitation)
            point_main(root, released)
            self.assertEqual(self.faults(root, checker), [])
            expected = git(root, "ls-tree", "-rz", FROZEN, "--", *sorted(INVITE_PATHS))
            self.assertEqual(git(root, "ls-tree", "-rz", "HEAD", "--", *sorted(INVITE_PATHS)), expected)
            docs_candidate(root)
            self.assertEqual(self.faults(root, checker), [])

    def test_registration_rejects_unapproved_metadata_predecessor(self):
        with fixture() as (root, head, checker):
            point_main(root, ANCHOR)
            synthetic = metadata_candidate(root)
            predecessor = metadata_release(root, synthetic, ANCHOR)
            tree = ref(root, head + "^{tree}")
            # Recreate the four-path edit on that predecessor rather than inheriting its old tree.
            git(root, "switch", "-C", REGISTRATION_BRANCH, predecessor)
            git(root, "restore", "--source", tree, "--staged", "--worktree", "--", *sorted(REGISTRATION))
            git(root, "commit", "-m", "Synthetic registration after different metadata bytes")
            self.assertTrue(self.faults(root, checker))


@contextmanager
def correction_fixture():
    with tempfile.TemporaryDirectory(prefix="apbra-issue193-correction-") as directory:
        root = Path(directory)
        git(root, "init", "-q", "-b", "main")
        git(root, "fetch", "--no-tags", str(ROOT), PR196 + ":" + MAIN,
            FROZEN + ":refs/fixtures/frozen-invitation")
        git(root, "reset", "--hard", PR196)
        git(root, "switch", "-c", CORRECTION_BRANCH)
        for name in CORRECTION:
            (root / name).write_bytes((ROOT / name).read_bytes())
        head = commit(root, CORRECTION, "Synthetic two-file issue 193 compatibility correction")
        yield root, head, runpy.run_path(root / CHECKER)


def check_query(root, checker, identity, branch, paths):
    return checker["check"](root, active_task_id=identity, active_branch=branch, changed_paths=paths)[0]


def hosted_checkout(root, base, head):
    merge = ancestry_commit(root, ref(root, head + "^{tree}"), [base, head], "Synthetic PR merge checkout")
    git(root, "switch", "--detach", merge)


@patch.dict(os.environ, GITHUB_HEAD_REF="", GITHUB_BASE_REF="", PR_HEAD_SHA="")
class FoundryReportDocumentationCheckout(unittest.TestCase):
    def test_correction_accepts_exact_branch_and_github_checkout(self):
        with correction_fixture() as (root, head, checker):
            context = ("APBRA-160", CORRECTION_BRANCH, CORRECTION)
            self.assertEqual(checker["delivery_context"](root), context)
            self.assertEqual(check_query(root, checker, *context), [])
            self.assertTrue(check_query(root, checker, "APBRA-160", CORRECTION_BRANCH, CORRECTION | DOCS))
            self.assertTrue(check_query(root, checker, "APBRA-85", CORRECTION_BRANCH, CORRECTION))
            hosted_checkout(root, PR196, head)
            with patch.dict(os.environ, GITHUB_HEAD_REF=CORRECTION_BRANCH, GITHUB_BASE_REF="main",
                            PR_HEAD_SHA=head):
                self.assertEqual(checker["delivery_context"](root), context)
                self.assertEqual(check_query(root, checker, *context), [])
                with patch.dict(os.environ, PR_HEAD_SHA=PR196):
                    self.assertTrue(check_query(root, checker, *context))

            forged_release = ancestry_commit(root, ref(root, head + "^{tree}"), [PR196, head],
                                            "Different correction merge subject")
            point_main(root, forged_release)
            self.assertTrue(check_query(root, checker, None, "main", set()))
            release = ordinary(root, PR196, head, 9860, CORRECTION_BRANCH)
            self.assertEqual(check_query(root, checker, None, "main", set()), [])
            path = SCOPE["REPORT_DOCS_TEST"]
            (root / path).write_bytes((root / path).read_bytes() + b"\n# Unexpected amendment drift\n")
            changed = commit(root, {path}, "Synthetic effective test drift")
            point_main(root, changed)
            self.assertTrue(check_query(root, checker, None, "main", set()))
            self.assertNotEqual(changed, release)

    def test_historical_queries_on_exact_direct_and_hosted_documentation_checkout(self):
        with correction_fixture() as (root, head, checker):
            release = ordinary(root, PR196, head, 9860, CORRECTION_BRANCH)
            docs = docs_candidate(root)
            entries = git(root, "ls-tree", "-rz", docs, "--", *sorted(DOCS))
            self.assertEqual(hashlib.sha256(entries).hexdigest(), APPROVED_DOC_ENTRIES_SHA256)
            legacy = runpy.run_path(root / "scripts/check_agent_details_20261013.py")
            legacy_context = ("APBRA-160", legacy["B"], legacy["P"])

            def assert_qualified_checkout():
                self.assertEqual(check_query(root, checker, *checker["delivery_context"](root)), [])
                self.assertEqual(check_query(root, checker, *legacy_context), [])
                self.assertEqual(checker["check"](root)[0], [])
                self.assertTrue(check_query(root, checker, "APBRA-160", legacy["B"], legacy["P"] | DOCS))

            assert_qualified_checkout()
            hosted_checkout(root, release, docs)
            with patch.dict(os.environ, GITHUB_HEAD_REF=DOCS_BRANCH, GITHUB_BASE_REF="main", PR_HEAD_SHA=docs):
                assert_qualified_checkout()
                for wrong in ({"PR_HEAD_SHA": release}, {"GITHUB_BASE_REF": "other"},
                              {"GITHUB_HEAD_REF": PRIOR_DOCS_BRANCH}):
                    with self.subTest(wrong=wrong), patch.dict(os.environ, wrong):
                        self.assertTrue(check_query(root, checker, *legacy_context))

                wrong_tree = ancestry_commit(root, ref(root, release + "^{tree}"), [release, docs],
                                             "Synthetic merge with a different tree")
                git(root, "switch", "--detach", wrong_tree)
                self.assertTrue(check_query(root, checker, "APBRA-160", DOCS_BRANCH, DOCS))
                git(root, "switch", "--detach", docs)
                self.assertTrue(check_query(root, checker, *legacy_context))

    def test_legacy_query_does_not_exempt_foreign_or_dirty_docs_checkouts(self):
        with correction_fixture() as (root, head, checker):
            release = ordinary(root, PR196, head, 9860, CORRECTION_BRANCH)
            docs = docs_candidate(root)
            legacy = runpy.run_path(root / "scripts/check_agent_details_20261013.py")
            context = ("APBRA-160", legacy["B"], legacy["P"])

            def assert_denied():
                errors = check_query(root, checker, *context)
                self.assertTrue(errors, "A historical query accepted an unqualified checkout")

            git(root, "switch", "-c", PRIOR_DOCS_BRANCH)
            assert_denied()
            with patch.dict(os.environ, GITHUB_HEAD_REF=DOCS_BRANCH, GITHUB_BASE_REF="main", PR_HEAD_SHA=docs):
                assert_denied()
            git(root, "switch", DOCS_BRANCH)
            readme = root / "README.md"
            readme.chmod(0o755)
            assert_denied()
            readme.chmod(0o644)
            readme.write_bytes(readme.read_bytes() + b"\nWrong bytes.\n")
            assert_denied()
            git(root, "add", "--", "README.md")
            assert_denied()
            git(root, "restore", "--source", docs, "--staged", "--worktree", "--", "README.md")
            readme.unlink()
            readme.symlink_to("ARCHITECTURE.md")
            assert_denied()
            git(root, "restore", "--worktree", "--", "README.md")
            extra = root / "unexpected.txt"
            extra.write_text("Synthetic extra path.\n")
            assert_denied()
            commit(root, {extra.name}, "Synthetic extra commit and path")
            assert_denied()
            # One child of current main with all approved entries plus a foreign path.
            mixed = ancestry_commit(root, ref(root, "HEAD^{tree}"), [release], "Synthetic mixed docs")
            git(root, "reset", "--hard", mixed)
            assert_denied()
