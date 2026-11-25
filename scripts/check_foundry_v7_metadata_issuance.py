"""Issue the bounded v7 metadata lane and verify its protected-main lifecycle."""
from __future__ import annotations

import json
import os
import re
import subprocess


ISSUE = "APBRA-160"
MAIN = "refs/remotes/origin/main"
V7_MAIN = "65945fb410ed439497487fbe1c5ff990c847d39a"
BASE = "577b5e23434353e2e825391b1454a585bcf509b9"
V7_TREE = "0879df8aa27cdde2f9cb2631689c8ce7470e208f"
BASE_TREE = "c398f952b5e19a215123b955737dd34d467a740d"
REGISTRATION = "bf182ab7d86ab5e02771d4e056327f0b46d031c9"
PRODUCT_BRANCH = "agent/APBRA-DEVOPS/APBRA-160-foundry-v7-metadata"
ISSUANCE_BRANCH = PRODUCT_BRANCH + "-issuance-finite-context"
BRANCHES = frozenset({ISSUANCE_BRANCH, PRODUCT_BRANCH})
TASK = "tasks/APBRA-160-foundry-v7-metadata-issuance-20261124.json"
TASK_SHA = "bf9d73ab9697f8224b83556a3fff81db9163ea9b272368029dfbceba7a15a4ed"
HELPER = "scripts/check_foundry_v7_metadata_issuance.py"
TESTS = "tests/bootstrap/test_foundry_v7_metadata_issuance.py"
PACKET = frozenset({TASK, HELPER, TESTS})
ISSUANCE_PATHS = PACKET | {
    "scripts/check_bootstrap.py",
    "scripts/check_recovered_native_registration.py",
}
PRODUCT_PATHS = frozenset({
    "apps/api/src/apbra_api/foundry_owner_metadata.py",
    "apps/api/tests/test_foundry_owner_metadata.py",
})
UNISSUED = "APBRA-160 v7 product execution has not been issued"


def git(root, *args):
    return subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(root), *args],
        stderr=subprocess.DEVNULL, timeout=10,
    )


def ref(root, name):
    return git(root, "rev-parse", "--verify", name).decode().strip()


def ancestor(root, commit, successor):
    return ref(root, commit) == git(root, "merge-base", commit, successor).decode().strip()


def changed(root, parent, commit):
    return set(git(root, "diff", "--no-renames", "--name-only", "-z", parent, commit).decode().split("\0")[:-1])


def matches_commit(root, paths, commit, raw):
    for path in paths:
        mode = git(root, "ls-tree", commit, "--", path).split(b" ", 1)[0]
        if mode != b"100644" or raw(root, path) != git(root, "show", commit + ":" + path):
            return False
    return True


def approved_base(root):
    return (
        ref(root, BASE + "^{tree}") == BASE_TREE
        and ref(root, V7_MAIN + "^{tree}") == V7_TREE
        and git(root, "rev-list", "--parents", "-n", "1", V7_MAIN).decode().split()[-1] == REGISTRATION
        and ancestor(root, V7_MAIN, BASE)
        and all(ancestor(root, BASE, name) for name in ("HEAD", MAIN))
    )


def candidate_head(root, base, paths, raw):
    """Accept one clean direct commit, including GitHub's equivalent checkout merge."""
    head, *parents = git(root, "rev-list", "--parents", "-n", "1", "HEAD").decode().split()
    if not parents or parents[0] != base or len(parents) > 2:
        return False
    pr_head = os.environ.get("PR_HEAD_SHA")
    if len(parents) == 2:
        child = parents[1]
        if (
            pr_head != child
            or git(root, "rev-list", "--parents", "-n", "1", child).decode().split() != [child, base]
            or ref(root, head + "^{tree}") != ref(root, child + "^{tree}")
        ):
            return False
    elif pr_head and pr_head != head:
        return False
    return (
        changed(root, base, head) == paths
        and not git(root, "status", "--porcelain", "--untracked-files=all", "-z")
        and matches_commit(root, paths, head, raw)
    )


def owner_merge(root, commit, branch, paths):
    """Recognize the ordinary GitHub merge shape on an already trusted main ref."""
    parents = git(root, "rev-list", "--parents", "-n", "1", commit).decode().split()
    if len(parents) != 3:
        return False
    _, parent, head = parents
    committer, subject = git(root, "show", "-s", "--format=%cn <%ce>%n%s", commit).decode().splitlines()
    expected = r"Merge pull request #[1-9][0-9]* from haseebulhaque/" + re.escape(branch)
    return (
        committer == "GitHub <noreply@github.com>"
        and re.fullmatch(expected, subject) is not None
        and git(root, "rev-list", "--parents", "-n", "1", head).decode().split() == [head, parent]
        and ref(root, commit + "^{tree}") == ref(root, head + "^{tree}")
        and changed(root, parent, commit) == paths
    )


def released_issuance(root, raw, *, issuance_matches=matches_commit):
    if not approved_base(root):
        return None
    commits = git(root, "rev-list", "--first-parent", "--reverse", BASE + ".." + MAIN).decode().split()
    if not commits:
        return None
    merge = commits[0]
    if not (
        ref(root, merge + "^1") == BASE
        and owner_merge(root, merge, ISSUANCE_BRANCH, ISSUANCE_PATHS)
        and ancestor(root, merge, "HEAD")
        and issuance_matches(root, ISSUANCE_PATHS, merge, raw)
        and issuance_matches(root, ISSUANCE_PATHS, MAIN, raw)
    ):
        return None
    return merge


def first_metadata_change(root, issuance):
    commits = git(root, "rev-list", "--full-history", "--first-parent", "--reverse",
                  issuance + ".." + MAIN, "--", *sorted(PRODUCT_PATHS)).decode().split()
    return next((commit for commit in commits
                 if changed(root, ref(root, commit + "^1"), commit) & PRODUCT_PATHS), None)


def exact_task(root, old, catalog, schema_errors, task_errors):
    task = json.loads(old["raw"](root, TASK))
    if old["sha"](old["raw"](root, TASK)) != TASK_SHA:
        raise ValueError("Metadata product task bytes differ")
    sources = json.loads(old["raw"](root, old["HISTORICAL_SOURCE"]))
    extension = json.loads(old["raw"](root, old["SOURCE"]))
    sources["sources"] += extension["sources"]
    schema = json.loads(old["raw"](root, "contracts/engineering/task-contract.schema.json"))
    faults = schema_errors(schema, task) or task_errors(task, catalog, sources)
    if faults or (
        task["task_id"], task["branch"], task["base_commit"], task["task_mode"], task["owner_acceptance"],
    ) != (ISSUE, PRODUCT_BRANCH, BASE, "IMPLEMENTATION", "RECORDED"):
        raise ValueError("Metadata product task identity, source or acceptance differs")
    if set(task["allowed_paths"]) != PRODUCT_PATHS or PRODUCT_PATHS != old["FUTURE_SLICES"][PRODUCT_BRANCH]:
        raise ValueError("Metadata product task is outside the original literal paths")
    return task


def bind(root, old, catalog, schema_errors, task_errors, identity, branch, paths,
         *, issuance_matches=matches_commit):
    """Select only authorized stages, separately from any operational use."""
    try:
        task = exact_task(root, old, catalog, schema_errors, task_errors)
        if branch not in BRANCHES:
            if paths and paths & PACKET:
                return (), ["Metadata issuance files require their exact issuance branch"]
            # Admit the unchanged files to inventory without binding a new active stage.
            return ((issuance_authority(task), ISSUANCE_PATHS),), []
        if identity != ISSUE:
            return (), ["Foundry v7 metadata issuance requires exact APBRA-160 identity"]
        if branch == ISSUANCE_BRANCH:
            if (
                paths != ISSUANCE_PATHS or ref(root, MAIN) != BASE or not approved_base(root)
                or not candidate_head(root, BASE, ISSUANCE_PATHS, old["raw"])
            ):
                return (), ["Foundry v7 metadata issuance requires its exact clean one-commit base and five-file scope"]
            return ((issuance_authority(task), ISSUANCE_PATHS),), []
        if paths != PRODUCT_PATHS:
            return (), ["Foundry v7 metadata requires the exact issued two-file product scope"]
        issuance = released_issuance(root, old["raw"], issuance_matches=issuance_matches)
        base = ref(root, MAIN)
        if (
            not issuance or first_metadata_change(root, issuance) is not None
            or not candidate_head(root, base, PRODUCT_PATHS, old["raw"])
        ):
            return (), ["Foundry v7 metadata requires verified manual issuance merge and an exact clean candidate on current main"]
        return ((dict(task, base_commit=base), PRODUCT_PATHS),), []
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return (), ["Foundry v7 metadata issuance evidence is unreadable or differs"]


def issuance_authority(product):
    return dict(
        product,
        branch=ISSUANCE_BRANCH, allowed_paths=sorted(ISSUANCE_PATHS),
        restricted_paths=["apps/**", ".github/**", "infra/**", ".env*", "**/.env", "local-data/**"],
        task_mode="SPECIFICATION", readiness="READY_FOR_SPECIFICATION",
    )


def metadata_successor(root, checker, context, old, *, issuance_matches=matches_commit):
    """Allow only the current issued candidate or its exact, already merged bytes."""
    try:
        identity, branch, paths = context
        if checker["delivery_context"](root) != context:
            return set()
        issuance = released_issuance(root, old["raw"], issuance_matches=issuance_matches)
        if not issuance:
            return set()
        merge = first_metadata_change(root, issuance)
        if branch == PRODUCT_BRANCH:
            if identity == ISSUE and paths == PRODUCT_PATHS and merge is None:
                # The preserved caller has already run the real canonical check.
                return set(PRODUCT_PATHS)
            return set()
        if paths and paths & PRODUCT_PATHS:
            return set()
        if merge and (
            owner_merge(root, merge, PRODUCT_BRANCH, PRODUCT_PATHS)
            and ancestor(root, merge, "HEAD")
            and matches_commit(root, PRODUCT_PATHS, merge, old["raw"])
            and matches_commit(root, PRODUCT_PATHS, MAIN, old["raw"])
        ):
            return set(PRODUCT_PATHS)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        pass
    return set()
