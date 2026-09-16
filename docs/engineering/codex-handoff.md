# Codex handoff: review first, build second

## Entitlement and setup check

Use the owner's existing Codex access only. Check available usage before launching; no API key, additional subscription, purchased credits or new paid Action is authorized. If access/quota is unavailable, stop and report it. Public GitHub does not make Codex usage unlimited. Official setup references: https://developers.openai.com/codex/cloud/code-review/ and https://developers.openai.com/codex/cloud/environments/ .

Connect only haseebulhaque/apbra. Select the bootstrap branch for review: agent/APBRA-DEVOPS/APBRA-85-repository-bootstrap. Do not assume main contains these instructions before the owner merges PR 1. No Azure secrets, business data or elevated GitHub token is needed. The application has not been built.

## First task: fresh review-only execution

Record the actual PR head/base at dispatch, then give a NEW review execution this instruction:

> Review PR 1 in haseebulhaque/apbra against its current main base. Read AGENTS.md, docs/decisions/solo-owner-process.md, tasks/APBRA-85-bootstrap.json, the engineering schemas, source register, CI policy and tests. Record the exact head/base SHA and actual runtime identity when exposed. Review the full diff and relevant existing code. Pay particular attention to policy bypasses, path/secret handling, Git history scanning, false-green CI, truthful source status, and the unexecuted APBRA-27 build contract. Run documented bootstrap and CI-policy checks and unit tests. Run the scanner only in its supported Linux/full-history environment; unavailable tests are NOT RUN, not PASS. Do not modify files, approve as the PR author, merge, change permissions, provision resources or implement product features. Return findings with severity, file/line, expected/actual and evidence, followed by PASS_WITH_FINDINGS, CHANGES_REQUIRED or BLOCKED as justified. A clean result may recommend manual merge, not perform it. Changes to the head after review require a fresh/reconciled review.

A different role label in the authoring session is not a fresh review. If the reviewer finds a defect, the implementer fixes it on the PR branch, CI reruns, and the reviewer reassesses the new revision. Do not issue an automatic GitHub APPROVE action using the author's account. Haseeb is the final manual merge authority under the accepted solo process.

## Second task: APBRA-27 local application bootstrap

Only after bootstrap review and Haseeb's merge, use [the detailed build contract](APBRA-27-build-contract.md) and tasks/APBRA-27-build.json. The JSON is currently a planning draft: its base and execution fields are unbound to the future merged source. Refresh Jira/Confluence acceptance and rebind these fields before dispatch. Do not carry the APBRA-85 bootstrap scope into application implementation.

The build creates only a local Python API bootstrap, locked dependencies, validated configuration, liveness/readiness, safe errors/correlation and tests. No frontend, live AI, Azure, Power BI generation or business persistence is included. Preserve security and review requirements when adapting bootstrap-only CI for this first implementation. Do not send the entire MVP backlog in one prompt.
