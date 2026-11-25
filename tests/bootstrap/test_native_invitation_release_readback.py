"""Exercise the four-file authority and real frozen invitation release shapes."""
from contextlib import contextmanager
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = "scripts/check_recovered_native_registration.py"
CHECKER = "scripts/check_bootstrap.py"
RECOVERED = runpy.run_path(ROOT / WRAPPER)
READBACK = runpy.run_path(ROOT / RECOVERED["INVITATION_READBACK_HELPER"])
METADATA = runpy.run_path(ROOT / READBACK["METADATA"])
INVITATION = runpy.run_path(ROOT / "scripts/native_invitation_scope.py")
NATIVE = runpy.run_path(ROOT / "scripts/check_nv.py")
BASE, MAIN, SCOPE = READBACK["BASE"], READBACK["MAIN"], READBACK["SCOPE"]
FROZEN, BRANCH = READBACK["FROZEN"], READBACK["BRANCH"]
PRODUCT, PRODUCT_PATHS = METADATA["PRODUCT_BRANCH"], METADATA["PRODUCT_PATHS"]
INVITE, INVITE_PATHS = INVITATION["B"], INVITATION["P"]
OWNER_MERGE = "Merge pull request #185 from haseebulhaque/" + INVITE
PIN, OVERLAP = NATIVE["CANDIDATE"], NATIVE["OVERLAP"]
APPLICATION = "apps/api/src/apbra_api/application.py"


def git(root, *args, github=False):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="Synthetic fixture", GIT_AUTHOR_EMAIL="test@example.org",
        GIT_COMMITTER_NAME="GitHub" if github else "Synthetic fixture",
        GIT_COMMITTER_EMAIL="noreply@github.com" if github else "test@example.org",
    )
    return subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(root), "-c", "core.hooksPath=/dev/null",
         "-c", "commit.gpgsign=false", *args],
        env=env, stderr=subprocess.PIPE, timeout=30,
    )


def ref(root, revision="HEAD"):
    return git(root, "rev-parse", "--verify", revision).decode().strip()


def ancestry_commit(root, tree, parents, title, *, github=True):
    args = [arg for parent in parents for arg in ("-p", parent)]
    return git(root, "commit-tree", tree, *args, "-m", title, github=github).decode().strip()


def point_main(root, commit):
    git(root, "switch", "main")
    git(root, "reset", "--hard", commit)
    git(root, "update-ref", MAIN, commit)


def candidate(root, before):
    git(root, "switch", "-C", INVITE, FROZEN)
    git(root, "merge", "--no-ff", before, "-m", "Synthetic frozen PR185 refresh")
    return ref(root)


def invitation_merge(root, before, head, title=OWNER_MERGE):
    git(root, "switch", "main")
    git(root, "reset", "--hard", before)
    git(root, "merge", "--no-ff", head, "-m", title, github=True)
    return ref(root)


def metadata_candidate(root):
    git(root, "switch", "-C", PRODUCT)
    for name in PRODUCT_PATHS:
        target = root / name
        target.write_bytes(target.read_bytes() + b"\n# Synthetic metadata product fixture.\n")
    git(root, "add", "--", *sorted(PRODUCT_PATHS))
    git(root, "commit", "-m", "Synthetic metadata product candidate")
    return ref(root)


def metadata_release(root, head, before):
    git(root, "switch", "main")
    git(root, "reset", "--hard", before)
    title = "Merge pull request #9875 from haseebulhaque/" + PRODUCT
    git(root, "merge", "--no-ff", head, "-m", title, github=True)
    release = ref(root)
    git(root, "update-ref", MAIN, release)
    return release


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(prefix="apbra-invitation-release-") as directory:
        root = Path(directory)
        git(root, "init", "-q", "-b", "main")
        git(root, "fetch", "--no-tags", str(ROOT), BASE + ":" + MAIN,
            FROZEN + ":refs/fixtures/frozen-invitation")
        git(root, "reset", "--hard", BASE)
        git(root, "switch", "-c", BRANCH)
        for name in SCOPE:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        git(root, "add", "--", *sorted(SCOPE))
        git(root, "commit", "-m", "Synthetic exact readback candidate")
        head = ref(root)
        checker = runpy.run_path(root / CHECKER)
        recovered = runpy.run_path(root / WRAPPER)
        yield root, head, checker, recovered


def issue(root, head, *, point=True):
    git(root, "switch", "main")
    git(root, "merge", "--no-ff", head,
        "-m", "Merge pull request #9874 from haseebulhaque/" + BRANCH, github=True)
    release = ref(root)
    if point:
        git(root, "update-ref", MAIN, release)
    return release


@patch.dict(os.environ, GITHUB_HEAD_REF="", GITHUB_BASE_REF="", PR_HEAD_SHA="")
class NativeInvitationReleaseReadback(unittest.TestCase):
    def assert_checkout(self, root, checker, recovered, expected):
        context = checker["delivery_context"](root)
        identity, branch, paths = context
        errors, _ = checker["check"](
            root, active_task_id=identity, active_branch=branch, changed_paths=paths,
        )
        self.assertEqual(errors, [])
        self.assertEqual(recovered["qualified_paths"](root, checker, *context, OVERLAP, PIN), expected)

    def witness(self, root, checker, recovered):
        context = checker["delivery_context"](root)
        return recovered["qualified_paths"](root, checker, *context, OVERLAP, PIN)

    def test_inverses_keep_exact_pr192_preimages(self):
        for path, name, marker in (
            (WRAPPER, "strip_invitation_readback_wrapper", RECOVERED["INVITATION_READBACK_MARKER"]),
            (READBACK["METADATA"], "strip_invitation_readback_metadata", b"issuance_matches"),
        ):
            source = (ROOT / path).read_bytes()
            restore = RECOVERED[name]
            self.assertEqual(restore(source), git(ROOT, "show", BASE + ":" + path))
            for mutated in (b"# Unapproved preimage\n" + source, source.replace(marker, b"", 1)):
                with self.assertRaises(ValueError):
                    restore(mutated)
        source = (ROOT / WRAPPER).read_bytes()
        with self.assertRaises(ValueError):
            RECOVERED["strip_invitation_readback_wrapper"](source + RECOVERED["INVITATION_READBACK_MARKER"])

    def test_four_path_candidate_and_hosted_equivalent_require_exact_identity(self):
        with fixture() as (root, head, checker, recovered):
            self.assertEqual(checker["delivery_context"](root), ("APBRA-85", BRANCH, SCOPE))
            self.assert_checkout(root, checker, recovered, set(OVERLAP))
            for identity, branch, paths in (
                ("APBRA-160", BRANCH, SCOPE),
                ("APBRA-85", BRANCH, SCOPE - {READBACK["TESTS"]}),
                ("APBRA-85", BRANCH, SCOPE | {"README.md"}),
                ("APBRA-85", BRANCH + "-wrong", SCOPE),
            ):
                faults, _ = checker["check"](root, active_task_id=identity, active_branch=branch, changed_paths=paths)
                self.assertIn("Native invitation release readback packet or exact authority differs", faults)
            tests = root / READBACK["TESTS"]
            original = tests.read_bytes()
            tests.unlink()
            self.assertEqual(self.witness(root, checker, recovered), set())
            tests.write_bytes(original)
            self.assert_checkout(root, checker, recovered, set(OVERLAP))

            git(root, "switch", "main")
            git(root, "merge", "--no-ff", head, "-m", "Synthetic hosted checkout")
            with patch.dict(os.environ, GITHUB_HEAD_REF=BRANCH, GITHUB_BASE_REF="main", PR_HEAD_SHA=head):
                self.assert_checkout(root, checker, recovered, set(OVERLAP))
            with patch.dict(os.environ, GITHUB_HEAD_REF=BRANCH, GITHUB_BASE_REF="main", PR_HEAD_SHA=BASE):
                self.assertEqual(self.witness(root, checker, recovered), set())
            with patch.dict(os.environ, GIT_DIR=str(root / ".git")):
                with self.assertRaisesRegex(ValueError, "repository overrides"):
                    READBACK["require_checkout"](root, METADATA)
                self.assertEqual(self.witness(root, checker, recovered), set())
            with tempfile.TemporaryDirectory() as directory:
                linked = Path(directory) / "linked"
                git(root, "worktree", "add", "--detach", str(linked), head)
                self.assertTrue((linked / ".git").is_file())
                READBACK["require_checkout"](linked, METADATA)
                git(root, "worktree", "remove", str(linked))

    def test_historical_source_copy_without_git_has_no_new_authority(self):
        with fixture() as (root, _, checker, recovered), tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            shutil.copytree(root, source, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
            for path in ("apps/web/src/foundry.ts", "apps/web/src/clarification.ts"):
                faults, _ = checker["check"](
                    source, active_task_id="APBRA-144",
                    active_branch="agent/APBRA-DEVOPS/APBRA-144-ai-native-iterative-clarification",
                    changed_paths={path},
                )
                self.assertEqual(faults, [])
            nested = root / "static-view"
            with (root / ".git/info/exclude").open("a") as exclusions:
                exclusions.write("\n/static-view/\n")
            shutil.copytree(source, nested)
            discovered = Path(git(nested, "rev-parse", "--show-toplevel").decode().strip())
            self.assertEqual(discovered.resolve(), root.resolve())
            for static in (source, nested):
                with self.assertRaisesRegex(ValueError, "own Git checkout"):
                    READBACK["require_checkout"](static, METADATA)
                for identity, branch, paths in (
                    ("APBRA-85", BRANCH, SCOPE),
                    ("APBRA-160", PRODUCT, PRODUCT_PATHS),
                    ("APBRA-160", METADATA["ISSUANCE_BRANCH"], METADATA["ISSUANCE_PATHS"]),
                ):
                    faults, _ = checker["check"](
                        static, active_task_id=identity, active_branch=branch, changed_paths=paths,
                    )
                    self.assertIn("Native invitation release readback packet or exact authority differs", faults)
                    self.assertEqual(recovered["qualified_paths"](
                        static, checker, identity, branch, paths, OVERLAP, PIN,
                    ), set())

    def test_prospective_and_published_frozen_source_then_two_file_metadata(self):
        with fixture() as (root, head, checker, recovered):
            amendment = issue(root, head, point=False)
            self.assertEqual(self.witness(root, checker, recovered), set())
            git(root, "update-ref", MAIN, amendment)
            self.assert_checkout(root, checker, recovered, set(OVERLAP))
            invitation_head = candidate(root, amendment)
            frozen = READBACK["entries"](root, METADATA, FROZEN, INVITE_PATHS)
            self.assertEqual(METADATA["changed"](root, amendment, invitation_head), INVITE_PATHS)
            self.assertEqual(READBACK["entries"](root, METADATA, invitation_head, INVITE_PATHS), frozen)
            self.assert_checkout(root, checker, recovered, set(OVERLAP))

            invitation = invitation_merge(root, amendment, invitation_head)
            self.assertEqual(self.witness(root, checker, recovered), set())
            git(root, "update-ref", MAIN, invitation)
            self.assertEqual(READBACK["entries"](root, METADATA, invitation, INVITE_PATHS), frozen)
            self.assert_checkout(root, checker, recovered, set(OVERLAP))
            metadata_head = metadata_candidate(root)
            self.assert_checkout(root, checker, recovered, set(OVERLAP) | PRODUCT_PATHS)
            metadata_release(root, metadata_head, invitation)
            self.assert_checkout(root, checker, recovered, set(OVERLAP) | PRODUCT_PATHS)

    def test_governance_then_metadata_then_ordinary_invitation_merge(self):
        with fixture() as (root, head, checker, recovered):
            amendment = issue(root, head)
            actual_metadata_head = metadata_candidate(root)
            self.assert_checkout(root, checker, recovered, set(OVERLAP) | PRODUCT_PATHS)
            effective_metadata = metadata_release(root, actual_metadata_head, amendment)
            self.assert_checkout(root, checker, recovered, set(OVERLAP) | PRODUCT_PATHS)
            refreshed = candidate(root, effective_metadata)
            self.assert_checkout(root, checker, recovered, set(OVERLAP) | PRODUCT_PATHS)
            released = invitation_merge(root, effective_metadata, refreshed)
            git(root, "update-ref", MAIN, released)
            self.assert_checkout(root, checker, recovered, set(OVERLAP) | PRODUCT_PATHS)

    def test_reject_wrong_topology_scope_mode_blob_and_effective_drift(self):
        with fixture() as (root, head, checker, recovered):
            before = issue(root, head)
            refreshed = candidate(root, before)
            valid = invitation_merge(root, before, refreshed)
            tree = ref(root, valid + "^{tree}")
            wrong_order = ancestry_commit(root, tree, [before, FROZEN], "Wrong refresh parent order")
            wrong_parent = ancestry_commit(root, tree, [FROZEN, head], "Wrong refresh main parent")
            cases = {
                "wrong branch subject": ancestry_commit(root, tree, [before, refreshed], OWNER_MERGE + "-wrong"),
                "wrong PR number": ancestry_commit(root, tree, [before, refreshed], OWNER_MERGE.replace("#185", "#186")),
                "wrong committer": ancestry_commit(root, tree, [before, refreshed], OWNER_MERGE, github=False),
                "single parent": ancestry_commit(root, tree, [before], OWNER_MERGE),
                "wrong inner order": ancestry_commit(root, tree, [before, wrong_order], OWNER_MERGE),
                "wrong inner b58 parent": ancestry_commit(root, tree, [before, wrong_parent], OWNER_MERGE),
                "merge tree differs from head": ancestry_commit(root, ref(root, FROZEN + "^{tree}"), [before, refreshed], OWNER_MERGE),
            }
            point_main(root, valid)
            for description in ("extra rename", "partial path set", "frozen blob", "frozen mode"):
                git(root, "reset", "--hard", valid)
                if description == "extra rename":
                    git(root, "mv", "-f", "README.md", APPLICATION)
                elif description == "partial path set":
                    git(root, "restore", "--source=" + before, "--staged", "--worktree", APPLICATION)
                elif description == "frozen blob":
                    path = root / APPLICATION
                    path.write_bytes(path.read_bytes() + b"\n# Changed invitation blob.\n")
                    git(root, "add", "--", APPLICATION)
                else:
                    git(root, "update-index", "--chmod=+x", APPLICATION)
                changed_tree = git(root, "write-tree").decode().strip()
                changed_head = ancestry_commit(root, changed_tree, [FROZEN, before], "Changed refresh")
                cases[description] = ancestry_commit(root, changed_tree, [before, changed_head], OWNER_MERGE)

            for description, attack in cases.items():
                with self.subTest(description=description):
                    point_main(root, attack)
                    self.assertEqual(self.witness(root, checker, recovered), set())
            point_main(root, valid)
            self.assert_checkout(root, checker, recovered, set(OVERLAP))
            path = root / APPLICATION
            path.write_bytes(path.read_bytes() + b"\n# Dirty invitation checkout.\n")
            self.assertEqual(self.witness(root, checker, recovered), set())
            git(root, "add", "--", APPLICATION)
            git(root, "commit", "-m", "Later drift in a released invitation file")
            git(root, "update-ref", MAIN, ref(root))
            self.assertEqual(self.witness(root, checker, recovered), set())
            point_main(root, valid)
            protected = root / "apps/api/src/apbra_api/model_provider.py"
            protected.write_bytes(protected.read_bytes() + b"\n# Unrelated protected source drift.\n")
            git(root, "add", "--", str(protected.relative_to(root)))
            git(root, "commit", "-m", "Later drift outside the invitation inventory")
            git(root, "update-ref", MAIN, ref(root))
            self.assertEqual(self.witness(root, checker, recovered), set())
