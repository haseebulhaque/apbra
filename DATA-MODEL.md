# Canonical data and lineage contract

Sources: Confluence 11.01 and 14.07 v1; DATA-001..010/020..023. This is the implementation vocabulary, not database migrations.

| Persisted concept | Meaning |
| --- | --- |
| Request / OriginalSubmission | Stable business request and separately retained immutable submitted payload |
| RequirementVersion / RequirementSpec | Exact structured requirement and confirmation; RequirementsSnapshot is an alias |
| DataSchemaVersion / DataSchema | Exact parsed declared schema; SchemaSnapshot is an alias |
| DesignPlanVersion / DesignPlan | Plan, source facts, evidence and supported capability decisions |
| GenerationAttempt | Logical generation; worker delivery retries do not create a fresh budget |
| Candidate / GenerationManifest | Immutable bytes, file digests and plan/generator provenance |
| ValidationRun / ValidationReport | Immutable executed-rule results, coverage and disposition |
| ReviewTask / GovernanceDecision | Actor, decision, reason, policy and exact candidate binding |
| Release / ReleaseManifest | Controlled package, evidence and pending customer actions |
| AgentExecution | Engineering provenance, not product-generation state |

## Invariants to implement

Opaque application identifiers, UTC timestamps, exact decimal strings across JSON, tenant ownership, tenant-consistent foreign keys, optimistic concurrency and immutable version records. Emails/display names are not stable security keys. Provider/identity/SQL types do not enter pure domain models.

Mutable Draft differs from immutable OriginalSubmission and confirmed versions. Corrections create new versions. Revalidation creates another run, not an edit to a failed run. Audit state changes must be transactionally consistent or use the approved outbox/reconciliation mechanism.

Large files live in authorized object storage; database rows retain ownership, hashes and references. Storage paths are organization aids, never authorization. Hashes detect changes but do not prove producer identity without trusted evidence.

## Required delivery

APBRA-104/105/106 implement schema, migrations, crash-window and audit consistency. APBRA-78 tests database/cache/retrieval/worker isolation. APBRA-114 tests retention/deletion across derived stores. Do not promise selective instant deletion from immutable backups.

The bootstrap only implements engineering metadata schemas in `contracts/engineering/`. Product schemas, migrations and a database are not implemented by this document.
