# Public-repository safety change

Work: APBRA-85 and APBRA-127. Execution reference: GH-PUBLIC-20260916-01. Prepared by ChatGPT through the owner's connection, not a separately authenticated independent reviewer.

## Authorized boundary

The owner confirmed public visibility and requested free-license-compatible safeguards, documentation alignment and removal of any exposed credentials. This authorizes public-safety work, not a licence purchase, product-stack change, automatic merge, blanket review waiver or unrelated history rewrite.

## Change content

- Public/free wording replaces current private-only assumptions in README, AGENTS, the Task Contract and repository controls. Historical evidence is preserved as historical.
- SECURITY.md defines public-data rules and exposure response; ignore patterns cover local keys, state, credentials and data files.
- The existing bounded CI job now fetches history and uses a checksum-pinned standalone Gitleaks CLI. No new paid Action, provider or runner is introduced.
- Six configuration tests cover the import target, bypass policy, required independent review, real check publisher, scanner pin/history/redaction and ignore behavior.
- A free-compatible branch ruleset import candidate is versioned. It has not been applied to GitHub by committing this file.

## Verification scope

The local environment could not clone GitHub because DNS resolution failed. Local configuration tests and shell syntax checking are separate from the actual secret scan. The full scan and combined engineering tests must run in GitHub-hosted CI, with the exact head and outcome recorded in PR #1. Adding this document does not assert that a scan has passed.

Gitleaks checks the exact tracked checkout tree and history reachable from fetched refs. Its synthetic detector self-test does not call a credential provider. No native secret-alert inspection, full manual audit of every historical comment, fork/cache removal or guarantee of zero possible secrets is implied. If findings exist, retain redacted evidence and follow SECURITY.md rather than suppressing them.

The native rulesets API was readable after public conversion and returned no rules. Branch-protection administration remains unavailable to the connector. The one-review requirement is preserved; shared-account limitations remain explicit. No production or paid service is activated.

## Cost and licence preflight rule

Before choosing an external service, runner, marketplace Action or platform feature: identify the exact capability, official licence/free entitlement, usage cap, required permissions and side effects. Record supported versus unavailable. Ask the owner before a paid dependency or an alternative that changes security, visibility or product scope. GitHub public availability does not authorize publishing private Jira/Confluence contents or activating billable Azure/model integrations.
