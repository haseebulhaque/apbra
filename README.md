# AI-Powered Power BI Report Automation (APBRA)

Governed report engineering: business intent and a declared schema become a typed BI DesignPlan, an editable Power BI candidate, independent validation evidence and a controlled deployment pack.

## Current repository state

The repository is public by owner decision and uses applicable GitHub Free engineering capabilities. This PR branch contains the engineering bootstrap, not a running report builder. Main remains unchanged until Haseeb manually merges after review. No application, Azure deployment, model evaluation or Power BI Desktop verification is claimed here.

The owner configured an active default-branch ruleset and removed all bypass actors. It requires a PR, resolved review threads and a current APBRA Bootstrap Checks result from GitHub Actions. Zero native approving reviews is intentional under the [accepted solo-owner process](docs/decisions/solo-owner-process.md). Separate AI review and Haseeb's manual merge remain process gates; no automatic merge is authorized.

## Start here

1. Read [AGENTS.md](AGENTS.md), [ARCHITECTURE.md](ARCHITECTURE.md) and [REQUIREMENTS.md](REQUIREMENTS.md).
2. Load the relevant specifications, source register, Agent Card and bounded task.
3. Follow [the Codex handoff](docs/engineering/codex-handoff.md): a fresh review of PR 1 before any application build.
4. The first future build is [APBRA-27](docs/engineering/APBRA-27-build-contract.md), not the entire MVP. Its JSON is a planning draft until rebound to merged main and accepted source versions.

## Engineering verification

Use Python 3.13 and an isolated environment:

```sh
python -m venv .venv
# Activate .venv for your shell.
python -m pip install --only-binary=:all: --no-deps -r requirements-bootstrap.txt
python scripts/check_ci_policy.py
python scripts/check_bootstrap.py
python -m unittest discover -s tests/bootstrap -v
# Linux x64, full non-shallow Git checkout:
bash scripts/scan_secrets.sh
```

These validate engineering metadata, explicit scope, mandatory workflow shape and selected secret/hygiene checks, not application security or report correctness. Targeted local tests and complete hosted CI evidence are distinguished in [the review record](docs/engineering/review-20260916.md). Consult PR 1's current head/checks for the final run; an earlier successful run does not cover later changes.

No cloud key or live model call is needed. The original full dependency hash-lock attempt failed due authoring-environment DNS; exact bootstrap package versions are recorded, but full product lock/build verification is APBRA-27 work. Missing tests or dependencies are not a passing result.

## Public content and cost controls

Never publish credentials, private keys, customer data, confidential documents, raw authenticated URLs, private transcripts or unredacted logs. Ignore rules cannot remove tracked content or history. [SECURITY.md](SECURITY.md) explains safe reporting and credential revocation/rotation before coordinated cleanup.

The pinned standalone Gitleaks CLI scans the tracked tree and fetched-reference history. It is bounded detection evidence, not proof that every possible secret, external clone or native alert was audited. Native secret-scanning settings must be checked through an authorized owner interface.

Research each platform's entitlement, usage limits, integration permissions and costs BEFORE implementation. GitHub public availability does not grant free Azure inference, Power BI sharing or unlimited Codex usage. No paid upgrade, larger runner, live service or additional credits are authorized automatically.

## Sources and decisions

Confluence owns architecture, Jira owns work intent and GitHub owns implementation/evidence. Public repository specifications are curated implementation views; access-controlled references do not authorize bulk exporting private content.

- [Source versions](docs/source-register.json)
- [Implementation baseline](docs/decisions/implementation-baseline.md)
- [Verified repository controls and limits](docs/engineering/repository-controls.md)
- [Confluence governance 22.05](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/4391060)
- [Jira APBRA-85](https://arkitektz.atlassian.net/browse/APBRA-85)
- [Jira APBRA-27](https://arkitektz.atlassian.net/browse/APBRA-27)

The detailed product baseline still retains its recorded Proposed source status until acceptance is reconciled before application dispatch. Documented technology choices are not tested cloud/model/runtime capabilities.

## License

Public visibility is intentional; no open-source license has been selected. License selection is a separate owner decision, not something an implementation agent silently adds.
