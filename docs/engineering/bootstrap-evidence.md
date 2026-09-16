# Bootstrap verification record

Original execution: GH-BOOTSTRAP-20260916-01. Logical role: APBRA-DEVOPS.
Actual repository writes: GitHub connection for haseebulhaque.
Requested by Haseeb. The original local checks used the assistant Linux sandbox,
Python 3.13.5 and exact installed versions in requirements-bootstrap.txt.
This is implementer-run evidence, not independent QA or human approval.

## Original commands and outcome

- `python scripts/check_bootstrap.py --report artifacts/bootstrap/checks.json`: PASS for the original engineering bootstrap files.
- `python -m unittest discover -s tests/bootstrap -v`: 33 tests passed at the original bootstrap revision.
- Dependency hash-lock generation with uv: FAILED because PyPI DNS was unavailable. Local tests used installed pinned versions rather than a fresh install.
- GitHub Actions run 35060527259 subsequently completed successfully for head 4db9f538783e52bf17d85ad2d611d83a7932e978, including exact tooling installation, contract checks and tests.

Positive/negative cases cover required metadata, Jira/commit identity, stale roles/sources, autonomy, source acceptance, branch/scope, traversal, JSON/schema references, workflow controls, links, selected credential patterns and accidental product code. They are not application integration tests.

## Original defects retained

The first local attempt found a missing workflows directory and an incorrect repository-root expression in the test harness. The second found YAML ambiguity in the unquoted pip command. These were corrected before the original publication; invalid YAML now has a regression test. Failures were not relabelled as passes.

## Public-repository refinement

The owner later made the repository public and authorized public-safety work under GH-PUBLIC-20260916-01. The earlier private-rulesets license error is superseded; public rulesets are eligible but the inspected list was empty and administration access remains unavailable to this connection. See repository-controls.md.

The refinement adds a full-fetched-history/current-tree scanner and six configuration tests. Their current GitHub Actions run and exact head are the verification record; the original 33-test result must not be reused as proof of the new revision. Local configuration tests and shell syntax checks do not establish that Gitleaks ran. No scan conclusion is inferred from this evidence document alone.

## Limits

These checks do not establish product security, guaranteed absence of all secrets, independent review, source freshness, Power BI support or native branch enforcement. No finding report should publish a secret value. See SECURITY.md for actual exposure response. No merge, production operation or paid service is authorized by a successful engineering test.
