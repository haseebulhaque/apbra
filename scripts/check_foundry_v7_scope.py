"""Validate the exact APBRA-160 v7 governance packet and registration stage."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ISSUE = "APBRA-160"
BASE = "b30ede8f7235e50561f7d4c49146830901ecb99d"
BASE_TREE = "51486a5e19710ad88d65f96084082aabb7b5954d"
REGISTRATION_BRANCH = "agent/APBRA-DEVOPS/APBRA-160-foundry-v7-registration"
TASK = "tasks/APBRA-160-foundry-v7-qualification-20261124.json"
SOURCE = "docs/source-register-apbra160-v7.json"
ADR = "docs/decisions/foundry-v7-qualification.md"
HISTORICAL_SOURCE = "docs/source-register.json"
HELPER = "scripts/check_foundry_v7_scope.py"
TESTS = "tests/bootstrap/test_foundry_v7_scope.py"
REGISTRATION_PATHS = frozenset({
    ADR, SOURCE, TASK, HELPER, TESTS, "scripts/check_bootstrap.py",
    "scripts/check_recovered_native_registration.py", "scripts/check_nv.py",
})
EXCLUSIVE_PATHS = frozenset({ADR, SOURCE, TASK, HELPER, TESTS})
SOURCE_ID = "apbra-160-v7-registration-acceptance"
BRANCH_PREFIX = "agent/APBRA-DEVOPS/APBRA-160-foundry-v7-"
FUTURE_SLICES = {
    BRANCH_PREFIX + "metadata": frozenset({
        "apps/api/src/apbra_api/foundry_owner_metadata.py",
        "apps/api/tests/test_foundry_owner_metadata.py",
    }),
    BRANCH_PREFIX + "runtime": frozenset({
        "apps/api/src/apbra_api/foundry_report_runtime.py",
        "apps/api/src/apbra_api/foundry_browser_handoff.py",
        "apps/api/src/apbra_api/foundry_memory_handoff.py",
        "apps/api/src/apbra_api/foundry_private_preparation.py",
        "apps/api/tests/test_foundry_report_runtime.py",
        "apps/api/tests/test_foundry_browser_handoff.py",
        "apps/api/tests/test_foundry_memory_handoff.py",
        "apps/api/tests/test_foundry_private_preparation.py",
    }),
    BRANCH_PREFIX + "report-workflow": frozenset({
        "apps/web/src/BusinessReportJourney.tsx",
        "apps/web/src/BusinessReportJourney.test.tsx",
        "apps/web/src/privateCases.tsx",
        "apps/web/src/privateCases.test.tsx",
        "apps/web/src/durableGeneration.tsx",
        "apps/web/src/durableGeneration.test.tsx",
        "apps/web/e2e/protected-generation.spec.ts",
    }),
}
BRANCHES = frozenset({REGISTRATION_BRANCH, *FUTURE_SLICES})

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def raw(root: Path, relative: str) -> bytes:
    target = root / relative
    if not target.is_file() or any(
        parent.is_symlink() for parent in (target, *target.parents)
        if parent == root or root in parent.parents
    ):
        raise ValueError("Missing or unsafe v7 packet file: " + relative)
    return target.read_bytes()


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(root), *args],
        stderr=subprocess.DEVNULL, timeout=10,
    )


def validate(root: Path, catalog: dict, schema_errors, task_errors):
    try:
        for path, expected in PINNED_FILES.items():
            if sha(raw(root, path)) != expected:
                return None, ["APBRA-160 v7 exact packet differs: " + path]
        for path in REGISTRATION_PATHS:
            raw(root, path)
        task = json.loads(raw(root, TASK))
        registration = json.loads(raw(root, SOURCE))
        historical = json.loads(raw(root, HISTORICAL_SOURCE))
        new_sources = registration["sources"]
        accepted = new_sources[0]
        if (
            len(new_sources) != 1 or accepted["id"] != SOURCE_ID
            or any(row["id"] == SOURCE_ID for row in historical["sources"])
            or accepted["status"] != "ACCEPTED"
            or accepted["repository_decision"] != ADR
            or accepted["repository_decision_sha256"] != PINNED_FILES[ADR]
            or registration["historical_source_register"] != HISTORICAL_SOURCE
            or registration["historical_source_register_sha256"] != PINNED_FILES[HISTORICAL_SOURCE]
        ):
            return None, ["APBRA-160 v7 source provenance differs"]
        schema = json.loads(raw(root, "contracts/engineering/task-contract.schema.json"))
        faults = schema_errors(schema, task)
        if not faults:
            faults = task_errors(task, catalog, {
                **historical, "sources": historical["sources"] + new_sources,
            })
        exact = (
            task["task_id"], task["assigned_agent"], task["agent_card_version"],
            task["base_commit"], task["branch"], task["task_mode"],
            task["readiness"], task["owner_acceptance"],
        )
        if exact != (
            ISSUE, "APBRA-DEVOPS", "0.1", BASE, REGISTRATION_BRANCH,
            "SPECIFICATION", "READY_FOR_SPECIFICATION", "RECORDED",
        ):
            faults.append("APBRA-160 v7 registration identity, authority or base differs")
        if (
            len(task["allowed_paths"]) != len(REGISTRATION_PATHS)
            or set(task["allowed_paths"]) != REGISTRATION_PATHS
            or task["source_ids"] != [SOURCE_ID]
        ):
            faults.append("APBRA-160 v7 literal registration scope differs")
        return (None if faults else task), faults
    except (OSError, ValueError, KeyError, TypeError):
        return None, ["APBRA-160 v7 exact governance packet is unreadable"]


def registration_base(root: Path) -> bool:
    try:
        return (
            git(root, "rev-parse", "origin/main").strip().decode() == BASE
            and git(root, "rev-parse", BASE + "^{tree}").strip().decode() == BASE_TREE
            and git(root, "merge-base", BASE, "HEAD").strip().decode() == BASE
        )
    except (OSError, subprocess.SubprocessError):
        return False


def phase_errors(root: Path, task: dict | None, identity, branch, paths):
    if branch in FUTURE_SLICES:
        return ["APBRA-160 v7 product execution has not been issued"]
    if branch == REGISTRATION_BRANCH:
        if identity != ISSUE or task is None or paths != REGISTRATION_PATHS:
            return ["APBRA-160 v7 registration requires its exact governance scope"]
        if not registration_base(root):
            return ["APBRA-160 v7 registration requires refreshed actual-main ancestry"]
    elif paths and paths & EXCLUSIVE_PATHS:
        return ["APBRA-160 v7 governance files require the registered branch"]
    return []


def bind(root: Path, catalog: dict, schema_errors, task_errors, identity, branch, paths):
    task, faults = validate(root, catalog, schema_errors, task_errors)
    faults += phase_errors(root, task, identity, branch, paths)
    if task is None or faults:
        return (), faults
    return ((task, REGISTRATION_PATHS),), []


PINNED_FILES = {
    'docs/decisions/foundry-v7-qualification.md': '016401fadf78e113faf7aac7d0b7915188f8235256b16a85d669300a40b00602',
    'docs/source-register-apbra160-v7.json': 'c61391c563d5bbf253fccfe8c35f9374aa72f4280cd1ecff56a6b839848c52dd',
    'tasks/APBRA-160-foundry-v7-qualification-20261124.json': '6d1b64370fdea9b0c18436c98ce0106a52df039178ef1e04aac5151ede20587f',
    'docs/source-register.json': '086e26d0f83e76347ab709d8859dd013513240a4e86ee9861af2086f38bb0f3e',
}


def qualified_prior_release(root, checker, identity, branch, paths, overlap, candidate,
                            historical, project):
    """Recheck the complete already-released application under the v7 governance stage."""
    try:
        context = (ISSUE, REGISTRATION_BRANCH, REGISTRATION_PATHS)
        if (identity, branch, paths) != context or checker["delivery_context"](root) != context:
            return set()
        if not registration_base(root):
            return set()
        catalog = json.loads(raw(root, "agents/catalog.json"))
        sources = json.loads(raw(root, HISTORICAL_SOURCE))
        parent, native, previous, faults = historical["bind"](
            root, catalog, sources, checker["schema_errors"], checker["task_errors"],
        )
        if faults or parent is None or native is None or previous is None:
            return set()
        for commit in (candidate, historical["BASE"]):
            for ref in ("HEAD", "origin/main"):
                if git(root, "merge-base", commit, ref).strip().decode() != commit:
                    return set()
        for name, expected in overlap.items():
            if sha(git(root, "show", candidate + ":" + name)) != expected:
                return set()
        for name in historical["G"] - historical["REG_FIXTURES"]:
            current = raw(root, name)
            if name in project:
                current = project[name](current.decode()).encode()
            if current != git(root, "show", BASE + ":" + name):
                return set()
        frozen = historical["manifest"](root)
        if frozen["product_status"] != "FROZEN":
            return set()
        complete = {**frozen["account_files"], **frozen["native_files"]}
        matches = historical["files_match"]
        if not (matches(root, complete, "origin/main") and matches(root, complete)):
            return set()
        protected = {name: complete.get(name, expected) for name, expected in overlap.items()}
        if not matches(root, protected):
            return set()
        faults, _ = checker["check"](
            root, active_task_id=identity, active_branch=branch, changed_paths=paths,
        )
        return set() if faults else set(overlap)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, RecursionError):
        return set()
