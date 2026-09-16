# AI-Powered Power BI Report Automation (APBRA)

Governed report engineering: business intent and a declared schema become a structured BI DesignPlan, editable Power BI project candidate, independent validation evidence and a controlled deployment pack.

## Repository status

This branch contains the **engineering bootstrap**, not a running report builder. Product implementation, Azure configuration, model evaluation and Power BI Desktop verification have not been completed here. `main` is not changed by preparing this branch. The pull request must be reviewed before merge.

The selected direction is Python/FastAPI, React/TypeScript, PostgreSQL/pgvector, bounded LangGraph reasoning, Azure adapters and Import-mode PBIP/PBIR/TMDL output. Concrete product dependency locks remain APBRA-27 work. Confluence 05.07 and 14.07 still label the detailed baseline Proposed; authorization for this isolated bootstrap does not invent approval of unverified versions, production processing or expenditure.

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

These checks validate repository contracts, agent metadata, references, bounded scope and selected hygiene controls. They do **not** certify application authorization, RAG quality, DAX correctness or Power BI compatibility. No cloud keys or live model calls are needed. The exact bootstrap dependency versions are recorded; package hash locking could not be generated in the authoring environment because PyPI DNS was unavailable. That limitation is not a passing supply-chain check.

## Sources of truth

- [Confluence architecture](https://arkitektz.atlassian.net/wiki/spaces/APBRA/overview)
- [Jira APBRA-85](https://arkitektz.atlassian.net/browse/APBRA-85): repository foundation
- [Jira APBRA-18](https://arkitektz.atlassian.net/browse/APBRA-18): module boundaries
- [Jira APBRA-86](https://arkitektz.atlassian.net/browse/APBRA-86): agent and task contracts
- [Jira APBRA-87](https://arkitektz.atlassian.net/browse/APBRA-87): CI assurance
- [Jira APBRA-127](https://arkitektz.atlassian.net/browse/APBRA-127): actual identity/protection feasibility

Repository specifications are implementation views of those sources, not a replacement architecture. Source versions are recorded in `docs/source-register.json`.

## Known gates

GitHub returned HTTP 403 for private-repository rulesets with an upgrade requirement. The observed `main` branch was unprotected. CI files and CODEOWNERS do not themselves enable protected branches. All writes so far use Haseeb's connected identity; a different agent role label does not create an independent GitHub approver. See [repository controls](docs/engineering/repository-controls.md).

No open-source licence has been selected. Do not publish this private repository or add a licence without owner approval.
