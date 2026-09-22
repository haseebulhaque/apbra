# APBRA post-Capstone product engineering handoff

## Current merged state

- Capstone: complete/submitted.
- Working bounded MVP baseline: established.
- Product development: continuing.
- APBRA-141 through APBRA-145: merged implementation history.
- APBRA-146: completed post-Capstone MVP documentation baseline.
- APBRA-148: current product-intent/documentation reconciliation task; keep In Progress until its bounded documentation PR is merged, its actual resulting main is verified, and the remaining material cross-system conflicts recorded below are resolved under separate authority.
- APBRA-147: planning hold; do not select or start it implicitly.
- APBRA-149 through APBRA-158: target-product planning items, not implemented capabilities.
- Canonical implementation baseline: `65d7281d1132ce5b4eca6d3cd89fd30e95f5c342`.
- APBRA-148 contract provenance base: `d072870fea8b8ae8caedc5e553653a433b697f11`.
- APBRA-148 post-registration documentation execution base: `c466dcbd928b0b07b5631c61c57b7ca90ce7f965`.

The application is a working bounded MVP/prototype, not production-ready. GPT-4.1 owns ambiguity reasoning and ordinary supported BI design; humans confirm material meaning; ConfirmedRequirementContract v2 freezes authority; deterministic coverage, integrity, normalization, bounded correction/repair, guardrails, compiler and candidate validation enforce the boundary.

## Current evidence

Canonical success `8042cc44-620f-4457-828d-0770749a653f` reached Candidate Ready for SalesPerformance after human confirmation; compiler completed and deterministic validation passed. No exact final candidate digest or Desktop PASS is durably recorded.

Fail-closed run `0927fd18-1c61-4610-8167-de86933a1de1` rejected missing monthly trend/business-question coverage with no candidate. Comparative Sales clarification reached Human Review Required with no contract/candidate; the known Ready-for-Confirmation lifecycle inconsistency remains visible. Historical ServiceNow run `d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa` remains historical only.

## Capability handoff

Business Mode is default; Advanced/BI Mode accepts optional preferences. Governed RAG is the five-document, approximately 20-chunk, `text-embedding-3-small` exact-cosine implementation, not S08 Foundry Knowledge. DAY, MONTH, QUARTER and YEAR are supported; WEEK, fiscal/custom calendars and locale-specific calendar policies are not.

The accepted product intent is `APBRA-PRODUCT-2026-09-22`, backed by Product Vision 01.01 v4, Business and Functional Requirements 02.01 v4 and Requirements Traceability Matrix 02.06 v6 at reconciliation time. It is target scope, not current implementation evidence. All eighteen `PC26-FR` mappings are maintained in [REQUIREMENTS.md](../../REQUIREMENTS.md).

The target adds one-engine Guided/Advanced experiences, conversation-first intake, qualified multimodal evidence, transparent alternatives/rescoping, authorized expert continuation, company identity/membership, optional projects/collaboration/history, entitlements/usage, tenant standards, qualified model profiles, separately consented Azure provisioning, connected Power BI delivery, optional data-architecture advice, and cross-cutting assurance. No next feature, milestone, replacement stack, provider, region, price, SLA or numerical limit is selected by this reconciliation.

## Operating boundaries

- Use synthetic data only and never commit `.env.local`, candidate ZIPs, secrets or private data.
- GPT proposes typed interpretations and designs; deterministic code owns normalization, integrity, policy, compilation and validation.
- The Capstone RAG implementation is the in-app 20-chunk fictional governed corpus, not the old S08 Foundry Knowledge store.
- `Report-Deployment-Guide.pdf` is generated lazily and does not prove deployment.
- APBRA is not production ready and does not publish to a Power BI tenant.
- An accepted assumption is visible business meaning, not proof of an absent field, unknown source fact or missing permission.
- Modes, licences, company membership and model keys do not grant private-resource access, trusted-author status or external management rights.
- “No dead ends” means truthful supported alternatives or authorized expert continuation, not guaranteed generation or disguised technical failure.
- Expert assistance, business acceptance, inspection download, release approval and successful deployment are separate events.
- Every changed candidate byte set requires fresh applicable mandatory validation and candidate-bound governance. Desktop/runtime evidence is required where the selected capability profile, release requirement or compatibility/runtime claim requires it; a runtime result for one byte set never transfers to different candidate bytes. This does not invent a Desktop PASS for the canonical Capstone candidate or make Desktop validation a newly pending Capstone test.
- Any changed material business meaning requires a new explicit acceptance while preserving earlier provenance.
- Implementation → fresh exact-head AI review → required hosted checks → Haseeb manual merge remains the accepted process.

## Production gaps

Production work remains for auth/RBAC, real tenant isolation, durable knowledge ingestion/index lifecycle, managed secrets/configuration, broader Power BI compatibility, publishing and gateway/credential orchestration, reviewer workflow, load/performance, resilience/DR, SLOs/monitoring/on-call, broader evaluation, privacy/compliance operations and commercial operations.

`DATA-MODEL.md` remains a known, separately governed reconciliation gap: it presents historical `DesignPlanVersion / DesignPlan` and older source references as current implementation vocabulary. The current authority boundary is the exact `ConfirmedRequirementContract`, with AI-produced `ReportDesign` subordinate to that confirmed meaning; the stale document must not be read as creating a competing contract or as an implementation instruction. It was intentionally not edited by APBRA-148 because it is outside the registered eleven-file scope.

These are separate gates: completing and merging the bounded eleven-document PR; verifying the actual resulting `main`; resolving the remaining material cross-system conflicts, including `DATA-MODEL.md`, under separately governed authority; and only then assessing overall APBRA-148 closure. Merging the documentation PR and reading back `main` do not by themselves clear the recorded data-model gap or complete APBRA-148.

Do not infer production capabilities from accepted Jira stories, Confluence target requirements, local administration screens or the historical `APBRA-IMPL-0.1` proposal. Read [the implementation and product baseline](../decisions/implementation-baseline.md) before planning.

See [the Capstone evidence index](capstone-evidence.md) for current and historical evidence boundaries.
