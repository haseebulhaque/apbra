# Repository control verification and open gates

## Current state, 16 September 2026

Repository haseebulhaque/apbra is public by owner decision. The owner configured the native ruleset through GitHub and removed every bypass actor. Readback of ruleset 23529228 confirms Active enforcement on the default branch, currently main; PR and conversation-resolution requirements; zero native approving reviews; APBRA Bootstrap Checks from GitHub Actions app 15368; strict up-to-date checking; deletion and non-fast-forward blocking. The response reports current_user_can_bypass=never.

[Accepted solo-owner process](../decisions/solo-owner-process.md) is authoritative for this bounded demonstration. The earlier private-plan licensing error and empty ruleset list are historical, resolved observations. The connector's lack of native administration does not prevent reading the owner-configured ruleset.

## Files and actual enforcement

.github/rulesets/main-protection.json mirrors selected installed policy fields. Its presence does not apply a rule. The actual evidence is the live ruleset readback; no destructive push/delete/merge probe was performed. Native enforcement tests and GUI settings must never be claimed solely from JSON unit tests.

CODEOWNERS identifies the existing owner and assists routing; native code-owner review is not required in the solo process. Initial API-created commits retain native author metadata. They are not cryptographically signed by a fictitious reviewer. Public owner email/name metadata is separate from a password or token.

## Merge gate

Bounded implementation -> fresh AI review against exact head/base -> required CI -> Haseeb manual merge. Native approving-review count is zero under an explicitly accepted decision, not a silent test workaround. Code-owner and last-push approval are off, and no bypass actors are configured. No collaborator invitation or second GitHub identity is required for this demonstration.

An AI review execution records reviewer runtime when exposed, exact revisions, findings, tests run/not run and the final recommendation. Same-session author self-review is not that independent execution. This PR remains draft until that review is available. No automatic approval or merge has been configured.

## Public CI boundary

Use standard ubuntu-24.04 hosted runners, a contents-read token, pull_request/manual events, and checkout without persisted credentials. No production-connected runner, pull_request_target code execution, cloud identity, production secrets, automatic merge or paid runner. Actions and the standalone MIT Gitleaks CLI are pinned. Public CI is not permission to use billable model calls.

The scanner uses complete fetched Git history and the tracked HEAD tree, offline synthetic detector checks and redacted results. Raw scan reports are not uploaded. This does not audit all native security alerts, forks, caches or unreachable objects. A no-finding result is bounded detection evidence, not proof that every possible secret is absent.

The supplementary CI-policy checker requires the exact mandatory steps and rejects absent/scoped-away checks, job/step conditionals, ignored failures, shallow checkout, unapproved options and duplicate YAML mapping keys. It is intentionally narrow for bootstrap; APBRA-27 must evolve it through a reviewed contract, not delete it to admit product code. Authors can still propose modifications to policy code, so review remains necessary.

## Licensing and availability preflight

Public-repository branch rulesets are eligible on GitHub Free. The standard public hosted-runner path and standalone MIT scanner are selected; no paid push rules, merge queue or licensed scanner Action are used. Review storage/usage allowances before growth. Open-source-license selection for APBRA remains a separate owner decision.

Codex/model access, Azure hosting, database operations, Power BI sharing and other platforms have separate entitlements and costs. Before configuring any of them: check official free features/limits, existing owner access, integration permissions and side effects; ask before purchases or material alternatives. A public GitHub repo does not grant unlimited Codex usage.

## Open work

The live native configuration and solo topology are verified. Remaining evidence: fresh independent AI review, owner merge decision, any specifically required safe enforcement tests, and APBRA-27's actual dependency/build verification. Product sources still carry their recorded status until owner acceptance is reconciled. No full application, tenancy, RAG, DAX, RLS or deployment assurance is claimed.

See [SECURITY.md](../../SECURITY.md) for credential exposure handling. Rotation/revocation precedes coordinated cleanup; current-file deletion cannot recall published history or external copies.

## References

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
- https://docs.github.com/en/actions/reference/security/secure-use
- https://developers.openai.com/codex/cloud/code-review/
- https://developers.openai.com/codex/pricing/
- https://github.com/gitleaks/gitleaks/blob/v8.30.1/LICENSE
