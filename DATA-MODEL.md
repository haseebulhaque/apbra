# APBRA data responsibilities and lineage

This document separates three things that must not be conflated:

1. **Implemented contracts and behaviour** in the bounded prototype.
2. **Planned durable logical responsibilities** accepted for the product direction.
3. **Historical names** retained only for traceability while older code and evidence still use them.

Controlling sources at APBRA-159 reconciliation time are [Confluence 11.01 Conceptual, Logical and Physical Data Models v4](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/3932664), [11.02 Data Dictionary and Lineage v3](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/3965422), [02.05 Data, Integration, Identity and Audit Requirements v3](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/4063348), and [02.06 Requirements Traceability Matrix v6](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/3932382). These sources define logical responsibilities and target requirements; they do not prove that a production database, migration or security control exists.

## Implemented bounded-prototype contracts

The application currently has two generations of code and evidence. Their names are not interchangeable aliases.

| Current code/evidence term | Implemented role |
| --- | --- |
| Original request, schema and clarification transcript | Preserved inputs and provenance for the current workflow. Raw prose is evidence, not downstream deterministic business authority. |
| `ConfirmedRequirementContract` | The authoritative typed contract for material business meaning explicitly accepted by the human. Version 2 binds the original request, schema context, iterative clarification analyses, raw answers, confirmation summary and exact confirmation event. |
| `ReportDesign` | AI-produced, subordinate technical report design. It may make ordinary supported BI-design choices but cannot redefine the confirmed business meaning or certify itself. |
| Normalization, coverage, integrity, guardrail, compiler and candidate-validation results | Deterministic evidence attached to the exact design/candidate processed. Missing, failed or skipped mandatory checks are not PASS. |
| Generated candidate/archive records | Bounded prototype artifacts and evidence. A digest demonstrates byte identity/integrity; it does not by itself prove producer identity, Desktop compatibility, approval, release or deployment. |

The repository also still contains legacy Capstone fixture types such as `RequirementsSnapshot`, `DesignPlan` and `AIRequirementsSnapshot`. They support historical tests or earlier bounded paths and have not been renamed out of the source tree. They do not supersede `ConfirmedRequirementContract`, and conceptual correspondences below must not be read as literal TypeScript aliases.

The current web prototype does not implement the planned durable product store described in the next sections. Browser state, generated files and engineering evidence are not a substitute for tenant-safe durable case history, transactional audit or production retention/deletion controls.

## Meaning and design authority

The authoritative flow is:

```text
original business input and qualified evidence
  -> AI-interpreted proposals and unresolved ambiguity
  -> raw clarification answers retained as provenance
  -> explicit human acceptance of an exact structured interpretation
  -> ConfirmedRequirementContract
  -> subordinate AI ReportDesign
  -> deterministic preservation, capability, compilation and candidate validation
```

In the bounded prototype, original submissions, AI proposals, accepted meaning and subsequent report-design choices remain distinct **semantic stages** with the clarification session nested in confirmation provenance; this is not a durable store of separate business-version records. The planned durable model requires corrections to create new immutable versions rather than rewrite originals and requires acceptance to bind an exact proposal rather than later, stale or materially changed meaning. Durable expert-assignment and actual-continuation records are also planned responsibilities, distinct from business acceptance, inspection, release approval and successful deployment. `ConfirmedRequirementContract` schema version 2 identifies the current contract shape; it is not itself a persisted requirement-version instance.

## Planned durable logical responsibilities

The following are target logical concepts. Their names describe responsibilities, not required table names, APIs, services or storage technologies.

| Logical responsibility | Target meaning |
| --- | --- |
| Company, membership and resource permission | Company context plus current, resource-specific authority. Company membership alone does not grant access to every private case, project, source or artifact. |
| Case and optional project | A case is the stable unit of work and may exist without a project. A project may group cases and collaboration/history but is not mandatory intake ceremony. |
| Conversation and qualified evidence | Original conversation, source description, uploaded schema/data and qualified reference/design evidence remain attributable and versioned. Observed facts, inference, uncertainty and accepted assumptions remain distinguishable. |
| Requirement proposal, decision and confirmed version | Proposed alternatives and their acceptance or decline remain explicit. Only the exact accepted structured meaning becomes a confirmed version. |
| Expert assignment and continuation | Authority to assign or involve an expert is recorded separately from the expert actually taking over or continuing the same case. Neither event silently confirms business meaning or releases an output. |
| Report output and version history | One case may have multiple report outputs, each with an independent design, generation and candidate history. |
| Evidence/schema and design versions | Qualified source/schema evidence and subordinate AI design are independently versioned and bound to the exact confirmed meaning they use. |
| Generation attempt and candidate | A logical attempt owns bounded retries and usage. A candidate binds exact bytes, manifests, digests, generator/design provenance and applicable capability profile. |
| Validation and governance | Immutable executed-rule results and human/automated decisions bind the exact candidate and policy/source versions evaluated. Revalidation creates a new result. |
| Release and separately authorised deployment | Release approval, inspection delivery, publication, connection/gateway configuration and successful deployment are separate states with separate authority and evidence. |

Required lineage connects requirement, evidence/schema, design, attempt, candidate, validation, governance, release and any separately authorised deployment without collapsing their identities.

## Planned invariants

- Use opaque stable application identifiers, UTC timestamps and exact numeric representations where interchange requires them. Display names and email addresses are not durable security identities.
- Enforce company consistency and current private case/project/source permissions before protected access, retrieval or continuation. Historical access, an old citation or a company key does not preserve revoked authority.
- Bind material acceptance to an exact version and reject stale decisions. Changed material meaning requires new explicit acceptance.
- Preserve original inputs, proposals, decisions, failures and derived lineage subject to approved retention, legal deletion and privacy requirements. Deletion/recovery must not resurrect revoked access or deleted evidence.
- Keep consequential state, mandatory audit and publication/dispatch records transactionally consistent or use an accepted, verified reconciliation mechanism.
- Bound usage at the correct aggregate. Retries, workers and new attempt identifiers must not reset a case/request budget.
- Treat object paths as organisation, never authorization. Treat hashes as integrity evidence, not automatic proof of actor or producer identity.
- Changed candidate bytes require fresh applicable mandatory validation and candidate-bound governance. Runtime/Desktop evidence is required only where the selected capability profile, release requirement or compatibility claim requires it, and never transfers to different bytes.
- Unsupported capabilities and missing or failed mandatory evidence remain explicit; they are not silently approximated or converted to PASS.

## Domain independence

The logical model is organised around companies, cases, evidence, accepted meaning, designs, outputs and governance—not around a reporting scenario. Sales, service-management, Contoso and other named datasets remain historical examples or synthetic fixtures. A new business domain is new input; it must not require a mandatory scenario entity, KPI recipe, workflow, visual layout or report template.

## Delivery boundaries

Relevant delivery work remains separate and must obtain current task authority before implementation: APBRA-34 (versioned requirements and traceability), APBRA-46 (grounded report design), APBRA-77/APBRA-78 (server-derived tenant context and isolation), APBRA-104/APBRA-105/APBRA-106 (durable persistence, tenant-aware schema and transactional audit/outbox recovery), APBRA-114 (retention/deletion propagation), and APBRA-119 (recovery/backup behaviour).

The accepted `DATA-001`–`DATA-010` and `DATA-020`–`DATA-023` identifiers remain requirement-traceability labels. This reconciliation clarifies their present implementation status; it does not rename them, mark them delivered or turn their target concepts into an installed schema.

This document does **not** authorise tables, migrations, persistence APIs, model-type renames or source changes. The engineering bootstrap only supplies engineering metadata schemas under `contracts/engineering/`. Planned production persistence, tenant isolation, audit, retention/deletion and recovery remain unimplemented until their own accepted contracts and evidence say otherwise.
