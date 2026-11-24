"""Bind the protected-report browser maintenance task to the released registration."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess


BASE = "65945fb410ed439497487fbe1c5ff990c847d39a"
MAIN = "refs/remotes/origin/main"
BASE_TREE = "0879df8aa27cdde2f9cb2631689c8ce7470e208f"
SPEC = "apps/web/e2e/protected-generation.spec.ts"
SPEC_SHA = "5930a80aa12588a93e7f8591b94acd666a991ff0a1092d68e35a35b00f366b59"
PRODUCT = frozenset({SPEC})
REG_BRANCH = "agent/APBRA-DEVOPS/APBRA-85-protected-report-browser-registration"
PRODUCT_BRANCH = "agent/APBRA-DEVOPS/APBRA-164-protected-report-browser-stabilisation"
TASK = "tasks/APBRA-164-protected-report-browser-stabilisation-20261124.json"
TASK_SHA = "254d69bcd3003b4d44141a84b6562785dab6e0d84e310a142d404760c37c05c6"
PACKET = frozenset({
    TASK,
    "scripts/check_protected_report_browser_registration.py",
    "tests/bootstrap/test_protected_report_browser_registration.py",
})
GOVERNANCE = PACKET | {"scripts/check_bootstrap.py", "scripts/check_recovered_native_registration.py"}
SOURCE_REGISTER = "docs/source-register.json"
# The older native source witness also protects these two files outside V3's maps.
NATIVE_BASE_PATHS = (
    "apps/api/src/apbra_api/generation.py",
    "apps/api/src/apbra_api/model_provider.py",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(root), *args],
        stderr=subprocess.DEVNULL, timeout=10,
    )


def ref(root, revision):
    return git(root, "rev-parse", "--verify", revision).decode().strip()


def ancestor(root, older, newer):
    return git(root, "merge-base", older, newer).decode().strip() == older


def parents(root, commit):
    return git(root, "rev-list", "--parents", "-n", "1", commit).decode().split()[1:]


def delta(root, base, commit):
    names = git(root, "diff", "--no-renames", "--name-only", "-z", base, commit)
    return set(names.decode().split("\0")[:-1])


def matches(root, paths, commit, raw):
    for path in paths:
        mode = git(root, "ls-tree", commit, "--", path).split(b" ", 1)[0]
        if mode != b"100644" or git(root, "show", commit + ":" + path) != raw(root, path):
            return False
    return True


def original_base(root):
    return (
        ref(root, BASE + "^{tree}") == BASE_TREE
        and all(ancestor(root, BASE, revision) for revision in ("HEAD", MAIN))
    )


def exact_candidate(root, base, scope, raw):
    head = ref(root, "HEAD")
    shape = parents(root, head)
    reported = os.environ.get("PR_HEAD_SHA")
    direct = shape == [base] and reported in (None, "", head)
    synthetic = (
        len(shape) == 2 and shape == [base, reported]
        and parents(root, reported) == [base]
        and ref(root, head + "^{tree}") == ref(root, reported + "^{tree}")
    )
    return (
        (direct or synthetic)
        and delta(root, base, head) == scope
        and not git(root, "status", "--porcelain", "--untracked-files=all", "-z")
        and matches(root, scope, head, raw)
    )


def merge_for(root, commit, branch, scope):
    merge_parents = parents(root, commit)
    if len(merge_parents) != 2:
        return False
    base, head = merge_parents
    identity, title = git(root, "show", "-s", "--format=%cn <%ce>%n%s", commit).decode().splitlines()
    subject = r"Merge pull request #[1-9][0-9]* from haseebulhaque/" + re.escape(branch)
    return (
        identity == "GitHub <noreply@github.com>"
        and re.fullmatch(subject, title) is not None
        and parents(root, head) == [base]
        and ref(root, commit + "^{tree}") == ref(root, head + "^{tree}")
        and delta(root, base, commit) == scope
    )


def registration_merge(root, raw):
    if not original_base(root):
        return None
    first = git(root, "rev-list", "--first-parent", "--reverse", BASE + ".." + MAIN).decode().split()
    if not first:
        return None
    merge = first[0]
    if (
        ref(root, merge + "^1") == BASE and merge_for(root, merge, REG_BRANCH, GOVERNANCE)
        and ancestor(root, merge, "HEAD")
        and matches(root, GOVERNANCE, merge, raw) and matches(root, GOVERNANCE, MAIN, raw)
    ):
        return merge
    return None


def first_browser_change(root, registration):
    candidates = git(root, "rev-list", "--full-history", "--first-parent", "--reverse",
                     registration + ".." + MAIN, "--", SPEC).decode().split()
    return next((commit for commit in candidates if SPEC in delta(root, ref(root, commit + "^1"), commit)), None)


def product_task(root, raw, catalog, schema_errors, task_errors):
    content = raw(root, TASK)
    if sha(content) != TASK_SHA:
        raise ValueError("Browser maintenance task bytes differ")
    task = json.loads(content)
    schema = json.loads(raw(root, "contracts/engineering/task-contract.schema.json"))
    sources = json.loads(raw(root, SOURCE_REGISTER))
    if schema_errors(schema, task) or task_errors(task, catalog, sources):
        raise ValueError("Browser maintenance task schema or source authority differs")
    if (task["task_id"], task["branch"], task["base_commit"], task["allowed_paths"]) != (
        "APBRA-164", PRODUCT_BRANCH, BASE, [SPEC],
    ):
        raise ValueError("Browser maintenance task identity or scope differs")
    return task


def issuance_task(task):
    return dict(
        task, task_id="APBRA-85", execution_id="APBRA-85-20261124-BROWSER-REGISTER-01",
        branch=REG_BRANCH, allowed_paths=sorted(GOVERNANCE),
        restricted_paths=["apps/**", ".github/**", "packages/**", ".env*", "local-data/**"],
        task_mode="SPECIFICATION", readiness="READY_FOR_SPECIFICATION",
    )


def protected_snapshot(root, historical):
    original = historical["manifest"](root)
    if original["product_status"] != "FROZEN":
        raise ValueError("Recovered snapshot is not frozen")
    files = {**original["account_files"], **original["native_files"]}
    if files.get(SPEC) != SPEC_SHA or not historical["files_match"](root, files, BASE):
        raise ValueError("Original recovered browser snapshot differs")
    for path in NATIVE_BASE_PATHS:
        files[path] = sha(git(root, "show", BASE + ":" + path))
    return files


def bind(root, raw, historical, catalog, schema_errors, task_errors, identity, branch, paths):
    try:
        task = product_task(root, raw, catalog, schema_errors, task_errors)
        registration = ((issuance_task(task), GOVERNANCE),)
        if branch == REG_BRANCH:
            if (identity == "APBRA-85" and paths == GOVERNANCE and ref(root, MAIN) == BASE
                    and original_base(root) and exact_candidate(root, BASE, GOVERNANCE, raw)):
                return registration, []
            return (), ["Protected-report browser registration requires its exact five-path candidate on actual main"]
        if branch == PRODUCT_BRANCH:
            if identity != "APBRA-164" or paths != PRODUCT:
                return (), ["Protected-report browser maintenance requires its exact one-file task and branch"]
            merged = registration_merge(root, raw)
            current = ref(root, MAIN)
            if (merged and first_browser_change(root, merged) is None
                    and exact_candidate(root, current, PRODUCT, raw)
                    and historical["files_match"](root, protected_snapshot(root, historical), MAIN)):
                return registration + ((dict(task, base_commit=current), PRODUCT),), []
            return (), ["Protected-report browser maintenance requires actual manual registration merge and exact current-main candidate"]
        if paths and paths & PACKET:
            return (), ["Protected-report browser registration files require the exact registration branch"]
        if paths and (root / ".git").exists():
            # Old delivery contexts may report only a rename destination. Inspect
            # the literal spec in each actual Git delta without rename collapsing.
            options = ("--no-renames", "--name-only", "-z")
            if (git(root, "diff", *options, MAIN + "...HEAD", "--", SPEC)
                    or git(root, "diff", *options, "HEAD", "--", SPEC)
                    or git(root, "diff", *options, "--cached", "HEAD", "--", SPEC)):
                return (), ["Protected-report browser successor requires the registered maintenance branch"]
        return registration, []
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return (), ["Protected-report browser registration proof is unreadable or differs"]


def qualified(root, checker, raw, historical, projections, context, overlap, candidate):
    """Prove the full recovered snapshot through this registration and the one-file successor."""
    try:
        identity, branch, paths = context
        if checker["delivery_context"](root) != context or not original_base(root):
            return set()
        catalog = json.loads(raw(root, "agents/catalog.json"))
        sources = json.loads(raw(root, SOURCE_REGISTER))
        parent, native, registration, faults = historical["bind"](
            root, catalog, sources, checker["schema_errors"], checker["task_errors"],
        )
        if faults or parent is None or native is None or registration is None:
            return set()
        if not all(ancestor(root, commit, name)
                   for commit in (candidate, historical["BASE"]) for name in ("HEAD", MAIN)):
            return set()
        if any(sha(git(root, "show", candidate + ":" + path)) != digest for path, digest in overlap.items()):
            return set()
        full = protected_snapshot(root, historical)
        match_files = historical["files_match"]
        for path in historical["G"] - historical["REG_FIXTURES"]:
            current = raw(root, path)
            if path in projections:
                current = projections[path](current)
            if current != git(root, "show", BASE + ":" + path):
                return set()

        main_files = full.copy()
        current_files = full.copy()
        if context != ("APBRA-85", REG_BRANCH, GOVERNANCE):
            merged = registration_merge(root, raw)
            if not merged:
                return set()
            successor = first_browser_change(root, merged)
            if context == ("APBRA-164", PRODUCT_BRANCH, PRODUCT):
                if successor or not exact_candidate(root, ref(root, MAIN), PRODUCT, raw):
                    return set()
                current_files[SPEC] = sha(raw(root, SPEC))
            elif successor:
                if ((paths and paths & PRODUCT) or not merge_for(root, successor, PRODUCT_BRANCH, PRODUCT)
                        or not ancestor(root, successor, "HEAD") or not matches(root, PRODUCT, successor, raw)
                        or not matches(root, PRODUCT, MAIN, raw)):
                    return set()
                main_files[SPEC] = current_files[SPEC] = sha(raw(root, SPEC))

        protected = {path: current_files.get(path, digest) for path, digest in overlap.items()}
        if not (match_files(root, main_files, MAIN) and match_files(root, current_files)
                and match_files(root, protected)):
            return set()
        errors, _ = checker["check"](root, active_task_id=identity, active_branch=branch, changed_paths=paths)
        return set() if errors else set(overlap)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, RecursionError):
        return set()
