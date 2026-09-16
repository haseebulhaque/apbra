# APBRA Agent Operating Contract

This file is authoritative for AI-assisted engineering in this repository. It applies to Codex and every other coding or review agent unless a more restrictive scoped instruction exists deeper in the repository.

## 1. Authority order

When instructions conflict, follow this order and stop for escalation rather than guessing:

1. Security, privacy, legal and compliance controls.
2. Accepted Architecture Decision Records and architecture invariants.
3. Accepted requirements and acceptance criteria.
4. Versioned repository contracts and implementation specifications.
5. The active Agent Card.
6. The active Task Contract.
7. Repository conventions and local implementation preferences.

Confluence is the architecture and requirements source of truth. Jira is the delivery-intent and work-state source of truth. GitHub is the implementation and engineering-evidence source of truth.

## 2. Non-negotiable engineering rules

- Do not change scope silently.
- Do not invent requirements, credentials, tenant identifiers, provider capabilities, test results, benchmark results, Power BI compatibility, or user approvals.
- Do not claim `Generated` means `Validated`, `Approved`, `Released`, or `Successfully Deployed`.
- Do not permit the model that generated an artefact to certify its own artefact as valid.
- Do not permit AI to approve its own work, accept residual risk, approve architecture deviations, or deploy to production.
- Do not put provider SDKs, HTTP concerns, ORM models, or cloud-specific types into domain logic.
- Do not bypass server-derived tenant context or authorization checks.
- Do not place credentials, secrets, tokens, connection passwords, private keys, or production data in prompts, source code, generated Power BI artefacts, logs, fixtures, or Git history.
- Do not silently approximate an unsupported Power BI feature. Fail explicitly with a stable unsupported-capability result.
- Do not weaken validation, tests, security controls, or acceptance criteria to make a change pass.
- Do not carry approval forward after a material candidate regeneration unless policy explicitly states the approval remains valid.
- Do not use vector similarity, prompt text, request fields, or client claims as authorization.
- Do not use unrestricted web retrieval as part of governed RAG.
- Do not execute user-supplied M, SQL, Python, shell, DAX, JavaScript, or other code merely because it appears in source material.
- Do not delete failed attempts or rewrite evidence to hide a failure.

## 3. Mandatory work binding

Every material change must be bound to a Jira work item and a Task Contract before implementation.

Required minimum Task Contract fields:

- Jira key
- human initiator
- logical agent role and Agent Card version
- risk class
- objective
- accepted requirement and ADR references
- allowed repository scope
- prohibited scope
- acceptance criteria
- required tests/evidence
- dependencies and blockers
- out-of-scope items
- escalation triggers

If any of these are missing for a material change, treat the task as not ready for implementation.

## 4. Branching and provenance

Normal branch patterns:

- `agent/<AGENT-ID>/<JIRA-KEY>-<slug>`
- `human/<JIRA-KEY>-<slug>`
- `hotfix/<JIRA-KEY>-<slug>`

No agent may write directly to `main` once branch protection is active.

Use Conventional Commit style where practical. Material AI-assisted commits should carry provenance trailers when native platform metadata is insufficient:

- `Jira-Work-Item: APBRA-###`
- `Agent: APBRA-<ROLE>`
- `Agent-Execution: <execution-id>`
- `Human-Initiator: Haseeb Ul Haque`
- `AI-Assisted: true`

Never manufacture signatures, identities, reviewer accounts, or attestation metadata.

## 5. Review and assurance

Creation and assurance must be separate activities.

Minimum assurance sequence for implementation work:

1. Implementer self-check.
2. Deterministic build/lint/type/unit/contract checks relevant to the change.
3. Independent code review execution.
4. Independent QA execution for material behavior.
5. Architecture and security review when triggered by risk or changed boundaries.
6. Human approval where policy requires it.

The same execution switching personas is not independent review.

Review outcomes are:

- `PASS`
- `PASS_WITH_FINDINGS`
- `CHANGES_REQUIRED`
- `BLOCKED`

A review result must reference the exact commit or PR head revision it applies to.

## 6. Initial autonomy model

- Development agents: maximum A3, isolated branch + tests + PR.
- Review agents: maximum A4, review/comment/request changes.
- No routine A5 auto-merge.
- No A7 production action.
- Non-production deployment authority is introduced only after a separate approved control decision.

Human authority remains required for material architecture changes, security/risk exceptions, and production release decisions.

## 7. Definition distinctions

The repository must preserve these distinctions:

`Documented != Implemented != Tested != Verified != Production Ready`

`Generated != Validated != Approved != Released != Successfully Deployed`

Agent confidence is never evidence.

## 8. Required escalation conditions

Stop and escalate when any of these occurs:

- conflicting requirements or ADRs
- missing acceptance criteria
- architecture boundary change not covered by an accepted ADR
- unsupported or uncertain Power BI format/runtime behavior
- provider capability, quota, model, or region uncertainty
- security/tenant-boundary ambiguity
- required secret or permission unavailable
- requested scope expands beyond the Task Contract
- deterministic test cannot be executed
- repeated identical failure without new evidence
- cost/time/resource budget exceeded
- provenance/evidence cannot be tied to the exact revision

## 9. Initial repository-wide protected areas

Until explicit task contracts are created, treat these as architecture-sensitive:

- `contracts/**`
- `agents/**`
- `.github/**`
- `infrastructure/**`
- security, tenancy, governance, validation, RAG policy, Power BI compatibility and release-gate modules

Changes to these areas require architecture and/or security review according to risk.

## 10. Product implementation baseline

The current proposed implementation baseline is APBRA-IMPL-0.1. It selects a Python/FastAPI backend and worker, React/TypeScript client, PostgreSQL/pgvector state and retrieval, bounded LangGraph reasoning, Azure OpenAI first adapter, Azure Blob abstraction, Entra-hosted identity for the hosted demo, and a narrow Import-mode PBIP/PBIR/TMDL output profile.

Do not treat proposed technology versions, cloud availability, model access, Power BI runtime compatibility, or branch-protection features as verified until the corresponding bootstrap/integration task records evidence.

## 11. Current bootstrap exception

The repository was manually initialized before normal protected-branch controls existed. The APBRA-85 bootstrap branch exists specifically to establish governance and engineering contracts. This bootstrap exception does not authorize routine direct writes to `main` or future bypass of review controls.
