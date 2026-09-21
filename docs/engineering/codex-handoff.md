# APBRA post-Capstone MVP engineering baseline

## Current merged state

- Capstone: complete/submitted.
- Working bounded MVP baseline: established.
- Product development: continuing.
- APBRA-141 through APBRA-145: merged implementation history.
- APBRA-146: current documentation/baseline reconciliation task.
- Canonical implementation baseline: `65d7281d1132ce5b4eca6d3cd89fd30e95f5c342`.
- Post-governance documentation base: `39ab131643c77d87359dd3fdb28909021f0e9ba9`.

The application is a working bounded MVP/prototype, not production-ready. GPT-4.1 owns ambiguity reasoning and ordinary supported BI design; humans confirm material meaning; ConfirmedRequirementContract v2 freezes authority; deterministic coverage, integrity, normalization, bounded correction/repair, guardrails, compiler and candidate validation enforce the boundary.

## Current evidence

Canonical success `8042cc44-620f-4457-828d-0770749a653f` reached Candidate Ready for SalesPerformance after human confirmation; compiler completed and deterministic validation passed. No exact final candidate digest or Desktop PASS is durably recorded.

Fail-closed run `0927fd18-1c61-4610-8167-de86933a1de1` rejected missing monthly trend/business-question coverage with no candidate. Comparative Sales clarification reached Human Review Required with no contract/candidate; the known Ready-for-Confirmation lifecycle inconsistency remains visible. Historical ServiceNow run `d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa` remains historical only.

## Capability handoff

Business Mode is default; Advanced/BI Mode accepts optional preferences. Governed RAG is the five-document, approximately 20-chunk, `text-embedding-3-small` exact-cosine implementation, not S08 Foundry Knowledge. DAY, MONTH, QUARTER and YEAR are supported; WEEK, fiscal/custom calendars and locale-specific calendar policies are not.

APBRA-146 deliberately does not select the next MVP feature.

## Operating boundaries

- Use synthetic data only and never commit `.env.local`, candidate ZIPs, secrets or private data.
- GPT proposes typed interpretations and designs; deterministic code owns normalization, integrity, policy, compilation and validation.
- The Capstone RAG implementation is the in-app 20-chunk fictional governed corpus, not the old S08 Foundry Knowledge store.
- `Report-Deployment-Guide.pdf` is generated lazily and does not prove deployment.
- APBRA is not production ready and does not publish to a Power BI tenant.
- Any changed candidate bytes require new validation and candidate-specific Desktop evidence.
- Implementation → fresh exact-head AI review → required hosted checks → Haseeb manual merge remains the accepted process.

## Production gaps

Production work remains for auth/RBAC, real tenant isolation, durable knowledge ingestion/index lifecycle, managed secrets/configuration, broader Power BI compatibility, publishing and gateway/credential orchestration, reviewer workflow, load/performance, resilience/DR, SLOs/monitoring/on-call, broader evaluation, privacy/compliance operations and commercial operations.

See [the Capstone evidence index](capstone-evidence.md) for current and historical evidence boundaries.
