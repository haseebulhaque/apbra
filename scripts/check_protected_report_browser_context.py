"""Keep historical branch simulations separate from a verified live browser delta."""
from __future__ import annotations

import json
import os
import subprocess


BASE = "61af5c0c035849918c358fab6b0ecd3371c38340"
TREE = "f499463f7901d06e946a6543519a9235ca344e00"
BRANCH = "agent/APBRA-DEVOPS/APBRA-85-browser-delivery-context"
PLAN = "APBRA-85 PLAN 11103"
WRAPPER = "scripts/check_recovered_native_registration.py"
HELPER = "scripts/check_protected_report_browser_context.py"
TESTS = "tests/bootstrap/test_protected_report_browser_context.py"
PACKET = frozenset({HELPER, TESTS})
SCOPE = PACKET | {WRAPPER}


def anchored(root, old):
    return (
        old["ref"](root, BASE + "^{tree}") == TREE
        and old["merge_for"](root, BASE, old["REG_BRANCH"], old["GOVERNANCE"])
        and old["ref"](root, BASE + "^1") == old["BASE"]
        and all(old["ancestor"](root, BASE, ref) for ref in ("HEAD", old["MAIN"]))
    )


def released(root, old, raw):
    """Read both approved registrations on the protected-main first-parent chain."""
    if not anchored(root, old):
        return None
    main = old["MAIN"]
    commits = old["git"](root, "rev-list", "--first-parent", "--reverse", BASE + ".." + main).decode().split()
    if not commits:
        return None
    correction = commits[0]
    preserved = old["GOVERNANCE"] - {WRAPPER}
    if (
        old["ref"](root, correction + "^1") == BASE
        and old["merge_for"](root, correction, BRANCH, SCOPE)
        and old["ancestor"](root, correction, "HEAD")
        and old["matches"](root, SCOPE, correction, raw)
        and old["matches"](root, SCOPE, main, raw)
        and old["matches"](root, preserved, BASE, raw)
        and old["matches"](root, preserved, main, raw)
    ):
        return correction
    return None


def current_branch(root, old):
    return os.environ.get("GITHUB_HEAD_REF") or old["git"](root, "branch", "--show-current").decode().strip()


def candidate_registration(root, old, raw):
    return (
        current_branch(root, old) == BRANCH
        and os.environ.get("GITHUB_BASE_REF") in (None, "", "main")
        and old["ref"](root, old["MAIN"]) == BASE
        and anchored(root, old)
        and old["exact_candidate"](root, BASE, SCOPE, raw)
        and old["matches"](root, old["GOVERNANCE"] - {WRAPPER}, BASE, raw)
    )


def candidate_product(root, old, raw, historical, correction):
    if (
        current_branch(root, old) != old["PRODUCT_BRANCH"]
        or os.environ.get("GITHUB_BASE_REF") not in (None, "", "main")
        or correction is None
        or old["first_browser_change"](root, correction) is not None
    ):
        return False
    main = old["MAIN"]
    original = historical["manifest"](root)
    protected = set(original["account_files"]) | set(original["native_files"]) | set(old["NATIVE_BASE_PATHS"])
    # BASE has a pinned tree and the original snapshot is still verified
    # independently by the release witness. Compare immutable Git entries here
    # so each historical check need not reread every protected blob twice.
    return (
        original["product_status"] == "FROZEN"
        and original["account_files"].get(old["SPEC"]) == old["SPEC_SHA"]
        and old["delta"](root, BASE, main).isdisjoint(protected)
        and old["exact_candidate"](root, old["ref"](root, main), old["PRODUCT"], raw)
    )


def bind(root, old, raw, historical, catalog, schema_errors, task_errors, identity, branch, paths):
    try:
        task = old["product_task"](root, raw, catalog, schema_errors, task_errors)
        prior = old["issuance_task"](task)
        correction = dict(
            prior, base_commit=BASE, execution_id="APBRA-85-20261124-BROWSER-CONTEXT-01",
            branch=BRANCH, allowed_paths=sorted(SCOPE),
            requirements=[PLAN, "Retain the live Git guard and all historical assertions."],
        )
        # Put original registration inventory first and keep the active scope lookup
        # exact. Neither specification record can authorize application paths.
        inventory = ((prior, old["GOVERNANCE"]), (correction, SCOPE))
        if branch == BRANCH:
            if identity == "APBRA-85" and paths == SCOPE and candidate_registration(root, old, raw):
                return inventory, []
            return (), ["Browser delivery context correction needs its exact three-path candidate on actual main"]

        if branch == old["PRODUCT_BRANCH"]:
            if identity != "APBRA-164" or paths != old["PRODUCT"]:
                return (), ["Protected-report browser maintenance requires its exact one-file task and branch"]
            if candidate_product(root, old, raw, historical, released(root, old, raw)):
                return inventory + ((dict(task, base_commit=old["ref"](root, old["MAIN"])), old["PRODUCT"]),), []
            return (), ["Protected-report browser maintenance requires the actual context correction merge and exact current-main candidate"]

        if paths and (paths & PACKET):
            return (), ["Browser delivery context correction files require their exact governance branch"]

        # Historical check() callers may supply a different branch while evaluating
        # this real product checkout. Prove the actual branch, delta and checkout
        # first. Only the new browser path guard is detached from the hypothetical
        # context; the older checker still receives and validates the original paths.
        prior_paths = paths
        if (
            paths and not (paths & old["PACKET"]) and branch != old["REG_BRANCH"]
            and (root / ".git").exists()
            and current_branch(root, old) == old["PRODUCT_BRANCH"]
            and candidate_product(root, old, raw, historical, released(root, old, raw))
        ):
            prior_paths = None
        _, errors = old["bind"](
            root, raw, historical, catalog, schema_errors, task_errors, identity, branch, prior_paths,
        )
        return (() if errors else inventory), errors
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return (), ["Browser delivery context authority or retained source differs"]


def qualified(root, old, raw, historical, checker, context, overlap, candidate):
    """Carry the original frozen readback through the exact browser replacement."""
    try:
        identity, branch, paths = context
        if checker["delivery_context"](root) != context or not anchored(root, old):
            return set()
        catalog = json.loads(raw(root, "agents/catalog.json"))
        sources = json.loads(raw(root, old["SOURCE_REGISTER"]))
        parent, native, original, faults = historical["bind"](
            root, catalog, sources, checker["schema_errors"], checker["task_errors"],
        )
        if faults or parent is None or native is None or original is None:
            return set()
        main = old["MAIN"]
        if not all(old["ancestor"](root, commit, ref)
                   for commit in (candidate, historical["BASE"]) for ref in ("HEAD", main)):
            return set()
        if any(old["sha"](old["git"](root, "show", candidate + ":" + name)) != expected
               for name, expected in overlap.items()):
            return set()

        full = old["protected_snapshot"](root, historical)
        match_files = historical["files_match"]
        actual = full.copy()
        checkout = full.copy()
        spec = old["SPEC"]
        if context == ("APBRA-85", BRANCH, SCOPE):
            if not candidate_registration(root, old, raw):
                return set()
        else:
            correction = released(root, old, raw)
            if not correction:
                return set()
            successor = old["first_browser_change"](root, correction)
            if context == ("APBRA-164", old["PRODUCT_BRANCH"], old["PRODUCT"]):
                if not candidate_product(root, old, raw, historical, correction):
                    return set()
                checkout[spec] = old["sha"](raw(root, spec))
            elif successor:
                if (
                    (paths and paths & old["PRODUCT"])
                    or not old["merge_for"](root, successor, old["PRODUCT_BRANCH"], old["PRODUCT"])
                    or not old["ancestor"](root, successor, "HEAD")
                    or not old["matches"](root, old["PRODUCT"], successor, raw)
                    or not old["matches"](root, old["PRODUCT"], main, raw)
                ):
                    return set()
                actual[spec] = checkout[spec] = old["sha"](raw(root, spec))
        protected = {name: checkout.get(name, frozen) for name, frozen in overlap.items()}
        if not (match_files(root, actual, main) and match_files(root, checkout)
                and match_files(root, protected)):
            return set()
        errors, _ = checker["check"](root, active_task_id=identity, active_branch=branch, changed_paths=paths)
        return set() if errors else set(overlap)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, RecursionError):
        return set()
