# APBRA Capstone engineering handoff

## Current merged state

- APBRA-137 final enterprise UX: done and merged.
- APBRA-138 Report Design measure/reference integrity: done and merged.
- APBRA-139 deterministic Report Design normalization and bounded layout: done and merged.
- APBRA-140 documentation/evidence reconciliation: current task.

The application is beyond bootstrap. It is a working bounded Capstone prototype with real GPT-4.1 interpretation, dynamic clarification, in-app governed RAG, original and normalized Report Designs, strict integrity, deterministic guardrails, PBIP/PBIR compilation, deterministic validation and a generated deployment guide.

## Current happy-path evidence

Run `d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa` reached Candidate Ready. The exact archive is `ServiceManagementFunnel.d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa.candidate.zip`, SHA-256 `833dff4ba7de7045e23ff6b42ce1e48e73b33534f1f910e7420753a1c5eab0f3`.

It recorded three clarifications, two embedding calls, top-k 4/four citations, two duplicate-binding collapses, zero integrity findings, guardrails PASS, compiler COMPLETED and deterministic validation PASS. All eight visuals fit inside the bounded pages.

Power BI Desktop validation for these exact current bytes remains **PENDING**. Do not transfer the historical SalesPerformance or ServiceDeskOperations Desktop results to this candidate.

## Remaining Capstone work

1. Open and inspect the exact current candidate in Windows Power BI Desktop.
2. Capture a final unsupported/unrealistic failure run that safely stops without a candidate.
3. Record attributable cost evidence.
4. Capture final screenshots and a 90-second demonstration.
5. Complete the nine-slide deck aligned with Confluence 21.02–21.06.

The intended failure request should exceed the bounded product contract through unsupported capabilities such as custom visuals, forecasting, write-back, inferred RLS, gateway/credential setup and direct production publishing. Historical ServiceNow implementation defects are regression evidence, not the final failure story.

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
