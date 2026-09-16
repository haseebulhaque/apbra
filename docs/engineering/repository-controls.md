# Repository control verification and open gates

## Observed, 16 September 2026

Repository haseebulhaque/apbra is private. Initial main commit is e8edf749cbd2009946cc96bdf7ee6850b9d3f44f. A separate APBRA-85 branch was created; a file write succeeded and was read back. That proves branch/file access, not administration.

The main branch read returned protected=false and no required checks. GET /repos/haseebulhaque/apbra/rulesets returned HTTP 403 with: Upgrade to GitHub Pro or make this repository public to enable this feature. We did not make it public, purchase a plan or change access. The connector exposes no verified protection-write operation. Native enforcement remains blocked/unconfigured.

## Files versus enforced controls

CODEOWNERS identifies the real existing owner, not twelve fictitious users. It is routing metadata, not proof of independent review or a required-review rule. The bootstrap workflow is a bounded repository check. A green check is not a required merge gate until the appropriate platform setting is configured and verified.

All connected writes use Haseeb's account. An agent label, changed Git author or a second persona cannot supply a qualifying independent GitHub approval on a PR authored by that account. Do not request the author as their own reviewer. Separate agent review can provide evidence but does not create segregation of duties.

## Before any merge

Inspect the actual PR author, base/head SHA, changed paths, check runs and required human/security review. Resolve one of: separately authorized non-author reviewer/app topology with supported private protection; or an explicitly owner-accepted limited solo-demo operating model with its limitations recorded. No automatic choice of the weaker option. Keep bootstrap as a draft until resolved.

When an eligible plan and admin path exist, configure main to require PRs, relevant named checks, resolved conversations, stale-review invalidation and no force push/deletion. Apply restrictions to bypass actors as supported. Verify with harmless positive/negative test PRs, not a destructive probe of main. Add the precise trusted check publisher where supported. Do not enforce an impossible self-approval rule.

## CI security profile

Use pull_request and manual dispatch, not pull_request_target to execute untrusted PR code. Read-only contents token; checkout does not persist credentials; no secrets, production runner, cloud identity, deploy or automatic merge. Actions are pinned to verified upstream commit references. Check outputs identify the checked-out merge/test SHA and PR head separately.

These controls reduce exposure, but the PR can modify its own workflow/check code. Trusted base-branch enforcement and independent review are still needed. Hygiene patterns are not a full secrets/SAST/supply-chain audit. No application tests are claimed by bootstrap checks.

## Sources consulted

- https://docs.github.com/en/actions/reference/security/secure-use
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- https://docs.github.com/en/pull-requests/reference/pull-request-reviews
- https://developers.openai.com/codex/guides/agents-md/

Vendor statements above are external research, not clauses invented in the APBRA requirements. Repository access findings are direct connector observations. APBRA-127/85 remain open until real control acceptance and enforcement evidence exist.
