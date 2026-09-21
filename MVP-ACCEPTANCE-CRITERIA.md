# MVP acceptance and evidence status

Capstone is complete/submitted. The bounded MVP baseline is working and product development continues. This is not a production-readiness claim.

## Completed Capstone capabilities

| Gate | Current result | Evidence boundary |
| --- | --- | --- |
| AI interpretation | PASS | Real GPT-4.1 interpreted the requirement and supplied schema metadata |
| Iterative clarification | PASS | Business-language clarification and natural-language answers |
| Human confirmation | PASS | Confirmation preceded ConfirmedRequirementContract v2 |
| Governed RAG | PASS | Five fictional standards; citations `CB-001`, `PM-002`, `RD-004`, `RD-001` |
| Grounded Report Design | PASS | Original structured AI design retained with provenance |
| Semantic preservation | PASS | Typed obligation coverage and exact schema/measure checks |
| Deterministic normalization/integrity | PASS | Original and validated designs remain traceable |
| Guardrails | PASS | Generation decision AVAILABLE |
| PBIP/PBIR compilation | PASS | Compiler COMPLETED for the bounded supported design |
| Deterministic candidate validation | PASS | Required project and reference checks passed |
| Candidate result | PASS | Final status Candidate ready |

Canonical run: `8042cc44-620f-4457-828d-0770749a653f`. The confirmed SalesPerformance design contained `Total Sales = SUM(Sales_Data.Revenue)`, an Executive Summary, Total Sales card, regional bar chart and Region slicer.

Interpretation tokens: 8,608 prompt, 1,207 completion, 9,815 total. ReportDesign tokens: 6,430 prompt, 964 completion, 7,394 total. Both used `gpt-4.1-2025-04-14`. `embeddingCalls = null`; no embedding count/cost is claimed.

## Runtime and claim boundary

No durable digest or exact-candidate Power BI Desktop PASS exists for the canonical run. Deterministic validation PASS is the highest verified claim. Desktop/runtime validation remains future engineering evidence, not a pending Capstone submission blocker.

## Required negative behaviour

Invalid or unsafe input must finish Human Review Required, Unsupported or Blocked. Missing required grounding, invalid measures/references, dependency cycles, invalid visual cardinality, unknown fields and insufficient layout capacity must prevent compilation. Skipped, crashed, timed-out or not-run mandatory validation is incomplete.

Run `0927fd18-1c61-4610-8167-de86933a1de1` proved fail-closed trend coverage: confirmed monthly intent, `REPORT_DESIGN_COVERAGE_INVALID`, no candidate. A comparative Sales scenario exhausted clarification/correction and reached Human Review Required without a contract/candidate; the known Ready-for-Confirmation transition inconsistency remains documented.

## Revision-specific engineering evidence

APBRA-141 through APBRA-145 are merged implementation history. DAY, MONTH, QUARTER and YEAR have genuine supported representations; WEEK remains unsupported. Historical APBRA-139/APBRA-140 and ServiceNow evidence remains available but is not the current acceptance baseline.

Test totals are revision-specific and must be refreshed after changes.

## Production acceptance remains open

The prototype does not satisfy production acceptance for identity/RBAC, multitenancy and tenant isolation, durable knowledge lifecycle, managed secrets, broad Power BI compatibility, publishing, gateway/credential orchestration, reviewer workflow, performance/load, resilience/DR, SLOs/monitoring/on-call, broad evaluation, privacy/compliance operations or commercial operations.

Generated ≠ validated ≠ Desktop verified ≠ approved ≠ released ≠ deployed.
