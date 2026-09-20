# APBRA Capstone evidence index

Evidence is revision- and candidate-specific. Historical results are retained but never transferred to different bytes.

## Current live happy path

| Evidence | Observed result |
| --- | --- |
| Run ID | `d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa` |
| Chat model | GPT-4.1; observed `gpt-4.1-2025-04-14` |
| Clarifications | 3 dynamic questions |
| Embeddings | 2 calls using `text-embedding-3-small`, 1,536 dimensions |
| Governed corpus | 5 fictional documents, 20 indexed chunks |
| Retrieval | top-k 4, four citations, 454 ms |
| Original Report Design | 8 visuals |
| Normalized Report Design | 8 visuals |
| Normalization | 2 `DUPLICATE_BINDING_COLLAPSED` actions |
| Integrity | 0 findings; PASS |
| Guardrails | PASS; generation AVAILABLE |
| Compiler | COMPLETED |
| Deterministic validation | PASS |
| Final status | Candidate ready |

The evidence sequence is original AI Report Design → deterministic normalization → normalized compiler-safe design → strict integrity validation → guardrails → compiler → deterministic candidate validation. The original design is preserved separately from the normalized design.

## Current candidate

- File: `ServiceManagementFunnel.d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa.candidate.zip`
- Size: 227,770 bytes
- SHA-256: `833dff4ba7de7045e23ff6b42ce1e48e73b33534f1f910e7420753a1c5eab0f3`
- Contains `ServiceManagementFunnel.pbip` and `ReportDesign.json`
- Power BI Desktop open/render validation: **PENDING**

The archive is evidence referenced by name and digest; candidate ZIPs are not committed to the repository.

## Layout evidence

The candidate has two report pages and eight visuals. Maximum right edge is 1,210 and maximum bottom edge is 520. Every reviewed visual is within the 1,280 × 720 page bounds, and no overlap was found in the reviewed layout. This is deterministic structural/layout evidence, not Desktop rendering evidence.

## Historical evidence

**HISTORICAL — exact candidate Desktop validation**

- `SalesPerformance.candidate.zip` — PASS
- `ServiceDeskOperations.candidate.zip` — PASS

**HISTORICAL — defect discovery and regression evidence**

Earlier ServiceNow executions exposed an unresolved ratio measure, invalid multi-binding slicers and off-page normalized layout. Those defects drove APBRA-138 integrity controls and APBRA-139 normalization/layout work. They are engineering history, not the current product outcome.

## Test and CI evidence

**APBRA-139 delivery revision:** 47 focused tests passed; full web suite 118 passed and 3 skipped; build PASS; bootstrap PASS; full bootstrap suite 168 passed; CI policy PASS; hosted secret scan PASS.

**APBRA-140 governance revision:** 8 focused tests passed; 74 historical authority regressions passed; full bootstrap suite 176 passed; tracked-tree validation PASS over 162 files; CI policy PASS; hosted required check PASS; secret scan PASS.

Counts are revision-specific and must not be presented as permanent totals.

## Remaining evidence tasks

1. Validate the exact current candidate in Windows Power BI Desktop and record open/render results.
2. Capture a final failure run using an intentionally unsupported/unrealistic requirement. Do not use a corrected ServiceNow defect as the failure demonstration.
3. Record attributable model/embedding cost evidence.
4. Capture final screenshots and the 90-second demonstration.
5. Complete the nine-slide presentation/evidence pack.

## Deployment-guide boundary

Successful runs offer dynamically generated, lazy-loaded `Report-Deployment-Guide.pdf`. It supplies handover, configuration and validation instructions. It does not prove publishing or deployment, and APBRA does not autonomously deploy to a production tenant.
