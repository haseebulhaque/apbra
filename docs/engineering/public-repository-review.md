# Historical public-repository safety change

Work: APBRA-85/APBRA-127. Historical execution: GH-PUBLIC-20260916-01. This records the public-visibility transition, before the later solo-owner decision and native ruleset installation. For current controls see [repository-controls.md](repository-controls.md) and [the accepted solo process](../decisions/solo-owner-process.md).

## Authorized boundary at that stage

The owner changed visibility to public, required free-license-compatible safeguards and requested review of possible credential exposure. This did not at that time authorize a review waiver, paid service, new source license, product implementation or unrelated history rewrite.

## Changes and actual historical results

README/AGENTS/task guidance was aligned to public use; SECURITY.md and ignore rules were added. The bounded workflow fetched complete history and ran checksum-pinned standalone Gitleaks 8.30.1 rather than a paid scanner Action. A proposed one-approval ruleset was prepared but not installed by committing it.

At PR head 3e03563ccad677b408bb3e76af21256c2a924eee, hosted run 35062142119 passed engineering checks and 42 tests. Its scanner reported 32 tracked files and eight reachable commits including the PR test-merge commit, with no findings in its configured scope. This is an old exact-revision result, not coverage of later edits. The preceding run 35061955221 failed an overbroad workflow heuristic that mistook the scan_secrets.sh filename for a secret-context reference; regression tests accompanied that correction.

The local clone had failed due DNS. Hosted scanning did not audit native alerts, every comment, forks/caches, unreachable objects or all possible personal information. No real exposed credential was detected or claimed rotated. Failed attempts remain part of the record.

## Later superseding decisions

The owner subsequently selected the solo-owner process and installed ruleset 23529228 with zero native approvals, required PR/CI, and no bypass actors. The current JSON/test expectations intentionally follow that explicit decision. A fresh AI review and Haseeb manual merge remain required. The earlier empty-ruleset and private-license blockers are resolved, not reasons to buy Pro.

Before external feature work, verify exact free entitlement, usage caps and integration permissions. Ask before spending or a material alternative. Public GitHub never authorizes confidential-source publication or billable Azure/model usage.
