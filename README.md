# AI-Powered Power BI Report Automation (APBRA)

Governed report engineering: business intent and a declared schema become a structured BI DesignPlan, editable Power BI candidate, independent validation evidence and a controlled deployment pack.

## Current scope

The owner has made this repository **public**. Repository engineering uses GitHub Free and free tooling; no Pro upgrade, paid runner, new paid service or automatic expenditure is authorized. This branch is an engineering bootstrap, not a working report builder. Product implementation, live models, Azure deployment and Power BI runtime verification remain separate work.

The selected Python/FastAPI, React/TypeScript, PostgreSQL/pgvector, bounded LangGraph and Azure-adapter direction is an implementation proposal from the recorded Confluence baseline. Product dependency locks and actual integration evidence do not exist merely because the design is documented. See [architecture](ARCHITECTURE.md) and [baseline](docs/decisions/implementation-baseline.md).

## Start here

1. Read [AGENTS.md](AGENTS.md) and the relevant [requirements](REQUIREMENTS.md).
2. Load the assigned logical Agent Card and bounded Task Contract, with current source versions.
3. Work on an isolated branch; retain review and exact-revision evidence.
4. Keep customer material, credentials and raw provider responses out of public files, comments and logs.

## Engineering checks

With Python 3.13 in an isolated environment:

```sh
python -m venv .venv
# Activate the environment using the command for your shell.
python -m pip install --only-binary=:all: --no-deps -r requirements-bootstrap.txt
python scripts/check_bootstrap.py
python -m unittest discover -s tests/bootstrap -v
```

On Linux x64 with Git, curl, tar and sha256sum, from a non-shallow repository:

```sh
bash scripts/scan_secrets.sh
```

The scanner downloads a checksum-pinned, MIT-licensed standalone Gitleaks CLI, checks a synthetic positive/negative detector fixture, and scans the current tracked tree and fetched Git history. It does not validate credentials against providers or inspect copies held by other people. Reports/logs redact secrets. No paid Gitleaks Action is used. CI uses a standard GitHub-hosted public-repository runner, read-only permissions and no cloud secrets.

Bootstrap checks cover engineering metadata and selected hygiene controls, not application authorization, RAG quality, business arithmetic or Power BI compatibility. The original environment could not generate dependency hash locks because PyPI DNS was unavailable; exact-version installation is not a completed hash-lock or vulnerability assessment.

## Public safety and repository controls

See [SECURITY.md](SECURITY.md), [repository controls](docs/engineering/repository-controls.md) and the [public-repository review](docs/engineering/public-repository-review.md). A deleted file or added ignore pattern does not remove a credential from old commits; revoke/rotate actual exposed credentials first.

Public branch rulesets are eligible on GitHub Free. Eligibility is not configuration: the inspected rulesets list was empty, and the current connection cannot administer branch protection. `.github/rulesets/main-protection.json` is an import candidate, not an applied rule. It targets main, blocks deletion/force-push, requires the named GitHub Actions check and preserves one non-author approval. No approval requirement is silently removed to accommodate a shared account. An explicitly accepted solo-review alternative would be a separate decision.

Keep PR #1 in draft until its actual checks, review and control decisions are complete. A green workflow is not enforced merge protection until the platform rule is applied. No automatic merge or direct main write.

## Sources of truth

- [Confluence architecture](https://arkitektz.atlassian.net/wiki/spaces/APBRA/overview)
- [APBRA-85 repository foundation](https://arkitektz.atlassian.net/browse/APBRA-85)
- [APBRA-18 module boundaries](https://arkitektz.atlassian.net/browse/APBRA-18)
- [APBRA-86 agent contracts](https://arkitektz.atlassian.net/browse/APBRA-86)
- [APBRA-87 CI assurance](https://arkitektz.atlassian.net/browse/APBRA-87)
- [APBRA-127 access and protection](https://arkitektz.atlassian.net/browse/APBRA-127)

These access-controlled references preserve traceability; they do not grant anonymous access to Jira or Confluence. Do not export private customer content to make a link readable. Source versions are in `docs/source-register.json`.

## Licence and cost boundary

No open-source licence has been selected for APBRA. Public visibility does not itself select one. A licence choice requires owner approval. GitHub Free does not make Azure, model APIs, Power BI publishing or other services free. Check the relevant free entitlement, quota, technical access and licensing before proposing or implementing a dependency; stop and ask before a paid requirement or a scope-changing alternative.
