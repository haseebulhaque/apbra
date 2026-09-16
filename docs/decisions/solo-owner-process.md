# Accepted solo-owner engineering process

Decision date: 16 September 2026. Owner: Haseeb Ul Haque.
Work: APBRA-85 / APBRA-127. Source: Confluence 22.05 v5 and the owner's explicit selection of the solo-owner process in the conversation.

## Accepted scope

The public repository uses GitHub Free. Native pull-request approving-review count is zero. The delivery process is:

1. A bounded implementation execution proposes a branch and PR.
2. A fresh AI review execution examines the exact head/base, code, requirements and verification evidence.
3. Required GitHub Actions checks pass for the applicable revision.
4. Haseeb reviews the evidence and manually merges the PR.

A second human collaborator is not required for this solo demonstration. A second logical agent is not a second GitHub identity. An AI review is a review result, not native owner self-approval. No automated merge, permission bypass or production authorization is granted.

## Verified native configuration

Ruleset ID 23529228, APBRA main - public GitHub Free: Active, default-branch target (currently main), zero approving reviews, no bypass actors and current_user_can_bypass=never. PRs, resolved review threads and APBRA Bootstrap Checks from GitHub Actions app 15368 are required. Strict up-to-date checking, deletion blocking and non-fast-forward blocking are configured. Code-owner and last-push approval are off.

These facts were read through the repository ruleset API after the owner configured the GUI. The JSON under .github/rulesets mirrors the selected policy fields; it is not a complete server export or an administration program. No destructive main push, deletion or failed-merge probe was performed.

## Limits and open evidence

The native ruleset does not verify that a separate AI review happened. That is a documented process gate checked by Haseeb before merge. A shared account still has shared authority; Markdown cannot technically distinguish human and agent sessions. An author-editable workflow is not a tamper-proof independent security service. Never describe this as enterprise segregation of duties.

This ChatGPT session may assess and fix the earlier bootstrap, but its own fixes are not independently reviewed by changing its role label. A fresh review-only Codex run must still be recorded before the bootstrap is considered reviewed. No such run is claimed yet.

Public GitHub authorization does not select an open-source license, buy Codex/API usage, activate Azure services or approve production data. Research entitlement, usage limits and actual permissions before using each external service. Stop and ask before a paid dependency or security/scope alternative.

The decision does not retrospectively certify the application, Power BI runtime or selected dependency versions.
