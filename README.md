# AI-Powered Power BI Report Automation (APBRA)

Governed report engineering: business intent and a declared schema become a structured BI DesignPlan, editable Power BI project candidate, independent validation evidence and a controlled deployment pack.

## Repository status

This repository is intentionally **public** and is being operated within capabilities available on GitHub Free. This branch contains the engineering bootstrap, not a running report builder. Product implementation, Azure configuration, model evaluation and Power BI Desktop verification have not been completed here. `main` is unchanged until a reviewed merge occurs.

The selected direction is Python/FastAPI, React/TypeScript, PostgreSQL/pgvector, bounded LangGraph reasoning, Azure adapters and Import-mode PBIP/PBIR/TMDL output. Concrete product dependency locks remain APBRA-27 work. Confluence 05.07 and 14.07 still label the detailed implementation baseline Proposed; this bootstrap does not invent approval of unverified versions, production processing or expenditure.

## Public-repository safety

Never commit real credentials, tenant secrets, private keys, connection strings, production data, customer documents or confidential client material. Use environment variables, local secret stores and synthetic fixtures. `.env` files and common credential/key artefacts are ignored by Git, but ignore rules are not a security boundary.

GitHub secret scanning runs automatically for public repositories. The repository also uses bounded local checks for selected high-confidence credential patterns. Neither control eliminates the requirement to review changes before publication. If a real credential is ever committed, revoke or rotate it immediately; deleting the current file is not sufficient because Git history and forks may retain it. See [SECURITY.md](SECURITY.md).

## Start here

1. Read [AGENTS.md](AGENTS.md) before any agent task.
2. Read [ARCHITECTURE.md](ARCHITECTURE.md) and [REQUIREMENTS.md](REQUIREMENTS.md).
3. Read the relevant specification, not the entire knowledge base.
4. Bind work to a Jira item and a contract under `tasks/`.
5. Run the bootstrap checks; record failures and actual tested revisions.

## Run the engineering checks

Use Python 3.13 in an isolated environment:

```sh
python -m venv .venv
# Activate .venv using the command appropriate to your shell.
python -m pip install --only-binary=:all: --no-deps -r requirements-bootstrap.txt
python scripts/check_bootstrap.py
python -m unittest discover -s tests/bootstrap -v
```

These checks validate repository contracts, agent metadata, references, bounded scope and selected hygiene controls. They do **not** certify application authorization, complete secret detection, RAG quality, DAX correctness or Power BI compatibility. No cloud keys or live model calls are needed. The exact bootstrap dependency versions are recorded; package hash locking could not be generated in the original authoring environment because PyPI DNS was unavailable. That limitation is not a passing supply-chain check.

## Sources of truth

- [Confluence architecture](https://arkitektz.atlassian.net/wiki/spaces/APBRA/overview)
- [Jira APBRA-85](https://arkitektz.atlassian.net/browse/APBRA-85): repository foundation
- [Jira APBRA-18](https://arkitektz.atlassian.net/browse/APBRA-18): module boundaries
- [Jira APBRA-86](https://arkitektz.atlassian.net/browse/APBRA-86): agent and task contracts
- [Jira APBRA-87](https://arkitektz.atlassian.net/browse/APBRA-87): CI assurance
- [Jira APBRA-127](https://arkitektz.atlassian.net/browse/APBRA-127): actual identity/protection feasibility

Repository specifications are implementation views of those sources, not a replacement architecture. Source versions are recorded in `docs/source-register.json`.

## GitHub Free control model

GitHub documents branch protection and repository rulesets as available for **public repositories on GitHub Free**. After the repository was made public, the rulesets endpoint became readable and returned an empty list, so no ruleset is currently evidenced as configured. This connector can inspect rulesets but does not expose a ruleset-administration write operation.

Until a rule is configured and read back, CI files and CODEOWNERS are guidance and evidence, not enforced merge policy. The recommended initial solo-project rule is: require a pull request to `main`, require the `APBRA Bootstrap Checks` status check, block force pushes/deletions, and require conversation resolution where available. Do not require an approving review until a real non-author reviewer exists, because the PR author cannot supply independent approval to their own change.

All connected repository writes currently use Haseeb's GitHub identity. A logical agent role label does not create a different GitHub identity. See [repository controls](docs/engineering/repository-controls.md).

## Licence

The repository is publicly visible, but no open-source licence has been selected yet. Public visibility alone does not grant an open-source licence. Add a licence only through a deliberate owner decision.
