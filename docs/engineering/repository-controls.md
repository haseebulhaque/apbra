# Repository control verification and open gates

## Current decision and observations, 16 September 2026

The owner changed haseebulhaque/apbra to PUBLIC and requires free-license-compatible tooling. The repository API confirms public visibility. The rulesets endpoint now succeeds but returns an empty array. This supersedes the earlier private-repository licensing blocker, not the evidence that a rule must actually be configured.

The separate branch-protection read returned Resource not accessible by integration (403). No ruleset/branch-protection administration write operation is exposed by this connection. Reported user admin permissions do not grant the integration every administration permission. No native rule is claimed configured by this change.

The earlier private-rulesets 403 remains a historical finding; it is not a current requirement to buy Pro. Do not change visibility again, purchase anything or create broader permissions to work around a missing capability.

## Researched free-tier choices

| Control | Eligible free approach | Boundary |
| --- | --- | --- |
| Main protection | Public-repository branch ruleset on GitHub Free | Admin configuration and readback still required; not a paid push ruleset |
| CI | Standard ubuntu-24.04 GitHub-hosted public workflow | No larger/paid or production-connected self-hosted runner; evidence retention seven days; storage allowance is not unlimited |
| Secret checks | Public GitHub scanning plus standalone MIT Gitleaks CLI 8.30.1 | Native alerts not inspected here; CLI version and release hash pinned; no licensed organization Action |
| Review | Existing independent-review requirement and actual human decision | Shared-account personas cannot supply qualifying non-author approval |
| Future integrations | Research free entitlement, quota and permissions first | Azure, model APIs, Power BI publishing and other services are not free just because GitHub is public |

## Import candidate, not an installed rule

`.github/rulesets/main-protection.json` is a branch ruleset configuration prepared for owner import. Target: refs/heads/main only. It blocks deletion and non-fast-forward updates, requires a pull request, one non-author approval, approval of the most recent push, resolution of review threads and a current APBRA Bootstrap Checks result from GitHub Actions app 15368. No bypass actors, paid push rules, merge queue or signature requirement have been added.

Import through repository Settings > Rules/Rulesets > New ruleset > Import a ruleset, then confirm the target and enforcement state. Re-read the applied rule and effective main rules afterward. File presence and local JSON tests are not proof of native enforcement.

**Review constraint remains explicit:** the present PR author is haseebulhaque. The same account cannot satisfy its own independent approval requirement. A real eligible non-author reviewer must be available before merge. Alternatively the owner may explicitly choose a limited solo-demo model; it must be described honestly and is not automatically accepted by making the repository public. No such waiver is implemented here. Keep PR #1 in draft.

## Public PR and CI security

Use pull_request and manual dispatch, read-only contents, checkout without persisted credentials and full fetched history for scanning. No production secrets, elevated pull_request_target execution, cloud identity or automatic merge. Third-party actions and scanner downloads are pinned. The scanner self-tests, scans the tracked tree and all fetched refs, redacts findings and does not upload raw scan reports. Forks, remote caches, native security alerts and copies outside fetched history are not covered by that CLI result.

An author can propose changes to workflow/checker code, so a green author-modified workflow alone is not independent security assurance. CODEOWNERS routes to a real existing owner; it does not create another person or enforce a required review itself. Confirm the exact PR base/head and actual checks at review time.

## Public-content incident rule

See [SECURITY.md](../../SECURITY.md). Do not confuse public project metadata with credentials. Keep customer information and secret-bearing connector download URLs out of commits and PR comments. A discovered valid credential must be revoked/rotated; current-file deletion does not purge historical exposure. Coordinate any necessary history rewrite separately and never claim existing forks/caches were recalled.

## Source references

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/managing-rulesets-for-a-repository
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning
- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
- https://github.com/gitleaks/gitleaks/blob/v8.30.1/LICENSE
- https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1

These references support capability/licensing decisions, not a claim of implemented enforcement. APBRA-85/127 remain open until actual control and review evidence is available.
