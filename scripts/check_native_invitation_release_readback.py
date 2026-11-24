"""Verify the approved APBRA-85 amendment and exact frozen invitation release."""
from __future__ import annotations

import functools
import os
from pathlib import Path
import re


ISSUE = "APBRA-85"
BRANCH = "agent/APBRA-DEVOPS/APBRA-85-native-invitation-release-readback"
EXECUTION = "APBRA-85-20261125-INVITATION-READBACK-01"
BASE = "b58dbf6825dabbdf3c007aca672d1e38615ca5e8"
BASE_TREE = "b2c48d5da81c6ed79964a4a29a897020a43258d4"
REGISTRATION = "b29be2b7eb663c4d50fd8658cf06fa214be50a87"
FROZEN = "b86b0e1d78a71572d07a0582035cb003713f895a"
FROZEN_TREE = "a03aedccdbcd7b1e4c5a5bb26a086376e9d624e3"
FROZEN_PARENT = "b30ede8f7235e50561f7d4c49146830901ecb99d"
INVITATION_BRANCH = "agent/APBRA-DEVOPS/APBRA-184-native-colleague-invitations"
MAIN = "refs/remotes/origin/main"
WRAPPER = "scripts/check_recovered_native_registration.py"
METADATA = "scripts/check_foundry_v7_metadata_issuance.py"
HELPER = "scripts/check_native_invitation_release_readback.py"
TESTS = "tests/bootstrap/test_native_invitation_release_readback.py"
SCOPE = frozenset({WRAPPER, METADATA, HELPER, TESTS})
ADDITIONS = frozenset({HELPER, TESTS})
ISSUANCE_INVERSES = frozenset({WRAPPER, METADATA})


def parents(root, git, revision):
    return git(root, "rev-list", "-n", "1", "--parents", revision).decode().split()[1:]


def first_touch(root, metadata, lower, main, paths):
    git, changed = metadata["git"], metadata["changed"]
    commits = git(root, "rev-list", "--first-parent", "--reverse",
                  lower + ".." + main).decode().split()
    return next((commit for commit in commits
                 if changed(root, parents(root, git, commit)[0], commit) & paths), None)


def actual_branch(root, metadata, branch):
    supplied = os.environ.get("GITHUB_HEAD_REF")
    if supplied:
        return supplied == branch and os.environ.get("GITHUB_BASE_REF") == "main"
    return metadata["git"](root, "branch", "--show-current").decode().strip() == branch


def require_checkout(root, metadata):
    """Keep inherited repository locators and parent Git discovery out of release proof."""
    locator = root / ".git"
    if locator.is_symlink() or not (locator.is_dir() or locator.is_file()):
        raise ValueError("Invitation readback requires its own Git checkout")
    git = metadata["git"]
    local_environment = set(git(root, "rev-parse", "--local-env-vars").decode().splitlines())
    if (local_environment - {"GIT_NO_REPLACE_OBJECTS"}) & os.environ.keys():
        raise ValueError("Invitation readback rejects inherited Git repository overrides")
    top = Path(git(root, "rev-parse", "--show-toplevel").decode().strip())
    if top.resolve() != root.resolve():
        raise ValueError("Invitation readback checkout root differs")


def amendment_state(root, metadata, raw):
    """Return the exact candidate or protected release of the four governance paths."""
    require_checkout(root, metadata)
    ref, ancestor = metadata["ref"], metadata["ancestor"]
    main = ref(root, MAIN)
    if not (
        ref(root, BASE + "^{tree}") == BASE_TREE
        and ancestor(root, REGISTRATION, BASE)
        and all(ancestor(root, BASE, commit) for commit in (main, "HEAD"))
    ):
        raise ValueError("Invitation readback base or registration differs")
    if main == BASE:
        if (actual_branch(root, metadata, BRANCH)
                and metadata["candidate_head"](root, BASE, SCOPE, raw)):
            return main, None
        raise ValueError("Invitation readback requires its exact four-path candidate on actual main")
    release = first_touch(root, metadata, BASE, main, SCOPE)
    if not (
        release
        and parents(root, metadata["git"], release)[0] == BASE
        and metadata["owner_merge"](root, release, BRANCH, SCOPE)
        and ancestor(root, release, "HEAD")
        and metadata["matches_commit"](root, SCOPE, release, raw)
        and metadata["matches_commit"](root, SCOPE, main, raw)
    ):
        raise ValueError("Invitation readback requires its exact ordinary protected-main merge")
    return main, release


def issuance_authority(task):
    return dict(task, task_id=ISSUE, execution_id=EXECUTION, branch=BRANCH, base_commit=BASE,
                allowed_paths=sorted(SCOPE),
                restricted_paths=["apps/**", ".github/**", "infra/**", ".env*", "local-data/**"],
                task_mode="SPECIFICATION", readiness="READY_FOR_SPECIFICATION")


def issuance_matcher(metadata, state, inverses):
    """Compare only the amendment's two restored sources at the original issuance."""
    if set(inverses) != ISSUANCE_INVERSES:
        raise ValueError("Invitation readback restores only the two amended issuance paths")
    main, _ = state

    def matches(root, paths, revision, raw):
        original = metadata["matches_commit"]
        commit = metadata["ref"](root, revision)
        if commit != BASE or paths != metadata["ISSUANCE_PATHS"]:
            return original(root, paths, revision, raw)
        if metadata["ref"](root, MAIN) != main:
            return False

        def historical_raw(origin, path):
            source = raw(origin, path)
            return inverses[path](source) if path in inverses else source

        return original(root, paths, commit, historical_raw)

    return matches


def metadata_view(metadata, state, inverses):
    match = issuance_matcher(metadata, state, inverses)
    return dict(metadata, **{
        name: functools.partial(metadata[name], issuance_matches=match)
        for name in ("released_issuance", "bind", "metadata_successor")
    })


def entries(root, metadata, commit, paths):
    return metadata["git"](root, "ls-tree", "-rz", commit, "--", *sorted(paths))


def invitation_release_before(root, metadata, state, invitation, raw):
    """Find the exact pre-invitation parent, with both levels of merge ancestry proved."""
    main, amendment = state
    if not amendment or invitation["B"] != INVITATION_BRANCH or len(invitation["P"]) != 28:
        return None
    if metadata["ref"](root, MAIN) != main:
        raise ValueError("Invitation main changed during readback")
    git, ref, ancestor = metadata["git"], metadata["ref"], metadata["ancestor"]
    paths = invitation["P"]
    release = first_touch(root, metadata, amendment, main, paths)
    if not release:
        return None
    if not (
        ref(root, FROZEN + "^{tree}") == FROZEN_TREE
        and parents(root, git, FROZEN) == [FROZEN_PARENT]
        and ancestor(root, REGISTRATION, FROZEN_PARENT)
        and metadata["changed"](root, FROZEN_PARENT, FROZEN) == paths
        and metadata["matches_commit"](root, invitation["G"], main, raw)
        and not git(root, "status", "--porcelain", "--untracked-files=all", "-z")
    ):
        raise ValueError("Frozen invitation source or clean checkout differs")
    if not ancestor(root, release, "HEAD"):
        raise ValueError("Invitation release is not in the checkout ancestry")
    merge_parents = parents(root, git, release)
    if len(merge_parents) != 2:
        raise ValueError("Invitation release does not have two parents")
    prior, head = merge_parents
    committer, subject = git(root, "show", "-s", "--format=%cn <%ce>%n%s", release).decode().splitlines()
    expected = r"Merge pull request #185 from haseebulhaque/" + re.escape(INVITATION_BRANCH)
    # The normal non-rewritten invitation branch refresh merges its new main
    # into the frozen head. The owner merge puts the main parent first.
    frozen = entries(root, metadata, FROZEN, paths)
    if not (
        committer == "GitHub <noreply@github.com>"
        and re.fullmatch(expected, subject)
        and parents(root, git, head) == [FROZEN, prior]
        and ancestor(root, amendment, prior)
        and ref(root, release + "^{tree}") == ref(root, head + "^{tree}")
        and metadata["changed"](root, prior, release) == paths
        and all(entries(root, metadata, commit, paths) == frozen
                for commit in (release, main, "HEAD"))
        and metadata["matches_commit"](root, paths, "HEAD", raw)
    ):
        raise ValueError("Invitation merge or effective frozen bytes differ")
    return prior


def historical_with_invitation(original, invitation_paths, prior, protected_paths):
    """Only the frozen intersection at effective main and the checkout can transition."""
    original_match = original["files_match"]
    scoped_paths = invitation_paths & protected_paths

    def files_match(root, expected, ref=None):
        if ref is not None and ref != MAIN:
            return original_match(root, expected, ref)
        changed = {name: digest for name, digest in expected.items() if name in scoped_paths}
        unchanged = {name: digest for name, digest in expected.items() if name not in scoped_paths}
        return original_match(root, unchanged, ref) and original_match(root, changed, prior)

    return dict(original, files_match=files_match)
