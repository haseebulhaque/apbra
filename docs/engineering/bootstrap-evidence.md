# Bootstrap verification record

Execution: GH-BOOTSTRAP-20260916-01. Logical role: APBRA-DEVOPS.
Actual repository writes: GitHub connection for haseebulhaque.
Requested by Haseeb. Local checks executed in the assistant Linux sandbox using
Python 3.13.5 and the exact installed versions in requirements-bootstrap.txt.
This is implementer-run evidence, not an independent QA or human approval.

## Commands and observed outcome

- `python scripts/check_bootstrap.py --report artifacts/bootstrap/checks.json`: PASS for the engineering bootstrap files.
- `python -m unittest discover -s tests/bootstrap -v`: 33 tests passed.
- Dependency hash-lock generation with uv: FAILED because PyPI DNS was unavailable. No fresh dependency install is claimed; tests used installed pinned versions.

Positive/negative cases cover required metadata, invalid Jira/commit identity,
unknown or stale roles/sources, excessive autonomy, unaccepted implementation,
branch/scope checks, traversal, restricted paths, duplicate JSON keys, external
schema references, unsafe workflow permissions/triggers/pins, broken local
references, credential-pattern detection and accidental product code.

## Defects found and corrected during this execution

The first local attempt found a missing workflows directory and an incorrect
repository-root expression in the test harness. The second found YAML ambiguity
in the unquoted pip command. These were corrected before publication; malformed
YAML now has an explicit failure outcome and regression test. No failure was
reclassified as a pass or omitted to inflate a product metric.

## Limits

These tests do not establish runtime product security, full secret scanning,
independent review, live source freshness, Power BI support or branch protection.
GitHub-hosted CI is separate; consult the PR's actual checks and run revision.
The private-rulesets 403 and shared-account reviewer gap remain recorded in
repository-controls.md. Nothing here authorizes merge or production actions.
