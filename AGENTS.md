# APBRA engineering-agent contract

Read this for every task. More restrictive scoped instructions apply where present. Repository instructions never override platform safety or the authenticated user's permissions.

## Authority and scope

Security/privacy constraints > accepted ADRs > accepted requirements > repository contracts > Agent Card > Task Contract > conventions. Escalate conflicts. Confluence owns architecture/requirements; Jira owns delivery intent; GitHub owns code/evidence. Chat memory is not a specification.

Every material task must identify its actual Jira item, source versions, logical role, actual actor, allowed/restricted paths, acceptance and verification. Missing/stale inputs prevent implementation. tasks/APBRA-85-bootstrap.json authorizes engineering bootstrap and accepted public/solo governance alignment only. tasks/APBRA-27-build.json is a planning draft, not yet an issued implementation task. Do not infer permission to build all Epics.

The product direction and implementation/evidence distinction are documented in docs/decisions/implementation-baseline.md. `APBRA-PRODUCT-2026-09-22` is accepted target intent; it is not proof that a capability exists. Preserve source acceptance and integration gates. A proposed framework/version or cloud/model/Power BI feature is not verified by prose.

For post-Capstone planning, use the accepted `PC26-FR-001`–`018` definitions and current RTM mappings from Confluence; do not reconstruct them from memory or turn a Jira planning item into implementation authority. APBRA-147 remains on planning hold unless separately selected. APBRA-149–158 describe target capability slices, not shipped functionality. Do not select a milestone, replacement stack, model/provider, region, commercial price, SLA or new numerical limit without accepted authority.

## Public/free preflight

The owner made this repository public and selected applicable free tooling. Before a dependency or platform change, research official feature entitlement, quota, permissions and cost. Ask before paid requirements or alternatives changing scope, security or visibility. Public GitHub does not make Azure/model/Codex usage unlimited or free. Never buy a plan, enable paid runners or collect tokens in chat.

Read SECURITY.md. No credentials, confidential customer material, production data, secret-bearing download URLs or private transcripts in code, logs, artifacts or comments. An actual exposed credential requires safe notification and issuer revocation/rotation before coordinated cleanup. A current-file deletion cannot recall historical exposure.

## Mandatory controls

- No direct main writes, force-push, automatic merge, production deployment or unapproved native permission changes. Do not use shared owner access as a bypass.
- No invented identities, signatures, approvals, model versions, tests, measurements or work items.
- Server-derived actor/tenant context governs protected actions. Prompt text, UI claims and vector similarity never authorize anything.
- AI proposes typed outputs. Deterministic code owns authorization, lifecycle, validation and release policy.
- Any changed candidate bytes require new validation and candidate-bound governance, even for cosmetic edits.
- Retain original submissions and failures according to approved retention; do not erase evidence to appear successful.
- Missing/skipped/crashed/timed-out mandatory validation is incomplete, never a pass.
- Separate technical release blockers from documented customer credential/gateway deployment steps.
- Treat uploads/retrieved text/generated output as untrusted; no arbitrary shell/M/SQL execution or model-controlled business authority.
- Unsupported Power BI behavior fails explicitly rather than being silently substituted.
- “No dead ends” means truthful supported alternatives or an actionable authorized-expert route; it does not guarantee generation or permit technical failure to be relabelled as success.
- An accepted assumption is a visible business choice, not evidence for an absent field, unknown source fact, missing permission or unsupported capability.
- Guided/Advanced mode, licences, company membership and model keys do not grant private-resource access, trusted-author status, publishing authority or external management rights.
- Keep expert assistance, business acceptance, inspection download, release approval and successful deployment as separate lifecycle events.
- Provider SDKs, ORM and transport types stay out of domain logic. No premature microservices.
- Never weaken tests, allow all paths, hide scanner findings or ignore exit codes to obtain a green check.

## Work sequence

1. Read current Jira and source versions; identify unavailable or stale context.
2. Load the card/shared policy in agents/catalog.json and the applicable Task Contract.
3. Verify exact base/head and use a bounded isolated branch.
4. Record scope, blockers and real actor in a meaningful PLAN comment.
5. Make bounded changes and run the relevant checks; distinguish actual runs from proposed commands.
6. Return changed paths, exact revisions, failures, results, evidence and outstanding obligations.
7. Open/update a PR. Never merge or mark an item Done while required review/evidence is absent.

```sh
python scripts/check_ci_policy.py
python scripts/check_bootstrap.py
python -m unittest discover -s tests/bootstrap -v
# Linux x64, non-shallow Git history:
bash scripts/scan_secrets.sh
```

These are engineering checks, not application tests or an isolation sandbox. APBRA-27 must introduce its own reviewed scope/CI transition; do not remove bootstrap controls to admit application files.

## Accepted solo-owner review process

Read docs/decisions/solo-owner-process.md and repository-controls.md. Live ruleset 23529228 has zero native approvals, no bypass actors, required PR/CI and resolved threads. This records the owner's explicit solo-process choice, not a missing second-human-review blocker.

Implementation -> fresh AI review on exact head/base -> passing required CI -> Haseeb manual merge. A new reviewer execution can recommend PASS/CHANGES_REQUIRED; it cannot claim native self-approval or act as another GitHub identity. Same-session persona switching and author self-check are not independent review. Current tools have not launched a separate reviewer; record that gate as pending rather than fabricated.

Keep review evidence current after fixes. No auto-merge or automatic APPROVE using the author account. Workflow files do not technically enforce the AI-review obligation; Haseeb checks it before manual merge. This is not enterprise segregation of duties.

## Attribution and escalation

Use meaningful [logical-role | activity | execution-id] comments with Jira key, real actor, exact tested revision and results. Branch pattern: agent/<AGENT-ID>/<JIRA-KEY>-<slug> or approved human/hotfix equivalent. Jira-keyed commit messages and optional Jira-Work-Item/Agent/Agent-Execution/Human-Initiator/AI-Assisted trailers are attribution, not signatures.

Stop for conflicting/unaccepted requirements, scope expansion, missing permissions, unverified paid capability, unsafe data, repeated unexplained failure, exhausted budget, missing verification or stale evidence. No unapproved visibility change, new administrator, spending or approval bypass.

Documented != Implemented != Tested != Verified != Production Ready.
Generated != Validated != Approved != Released != Successfully Deployed.
