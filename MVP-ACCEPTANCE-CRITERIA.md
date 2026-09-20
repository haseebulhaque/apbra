# Capstone acceptance and evidence status

This is a current evidence map, not a production-readiness claim. Results apply only to the recorded revisions and candidate bytes.

## Completed Capstone capabilities

| Gate | Current result | Evidence boundary |
| --- | --- | --- |
| AI interpretation | PASS | Real GPT-4.1 interpreted the requirement and supplied schema metadata |
| Dynamic clarification | PASS | Current run generated three input-specific questions |
| Governed RAG | PASS | Five fictional standards, 20 chunks, two embedding calls, top-k 4 and four citations |
| Grounded Report Design | PASS | Original structured AI design retained with provenance |
| Deterministic normalization | PASS | Two identical field/category duplicates collapsed; original and normalized designs remain distinct |
| Strict integrity | PASS | Zero findings after normalization; measure, dependency, reference and cardinality rules executed |
| Guardrails | PASS | Generation decision AVAILABLE |
| PBIP/PBIR compilation | PASS | Compiler COMPLETED for the bounded supported design |
| Deterministic candidate validation | PASS | Required project and reference checks passed |
| Page bounds | PASS | Eight visuals over two pages; maximum right 1,210 and bottom 520 inside 1,280 × 720 |
| Candidate result | PASS | Final status Candidate ready |

Current run: `d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa`.

Current candidate SHA-256: `833dff4ba7de7045e23ff6b42ce1e48e73b33534f1f910e7420753a1c5eab0f3`.

## Pending Capstone evidence

- **Power BI Desktop validation of the exact current ServiceManagementFunnel candidate: PENDING.**
- Final unsupported/unrealistic failure-run capture.
- Attributable cost calculation.
- Final screenshots, demo recording and nine-slide presentation/evidence pack.

Historical Power BI Desktop PASS results for `SalesPerformance.candidate.zip` and `ServiceDeskOperations.candidate.zip` remain valid only for those exact historical archives.

## Required negative behaviour

Invalid or unsafe input must finish Human Review Required, Unsupported or Blocked. Missing required grounding, invalid measures/references, dependency cycles, invalid visual cardinality, unknown fields and insufficient layout capacity must prevent compilation. Skipped, crashed, timed-out or not-run mandatory validation is incomplete.

The final failure demonstration should use an intentionally unsupported or unrealistic request, such as a 25-page report demanding unsupported custom visuals, predictive forecasting, write-back, workflow approvals, inferred RLS, gateway/credential configuration and direct production publishing. It should not reuse a historical ServiceNow engineering defect as the product failure example.

## Revision-specific engineering evidence

APBRA-139 delivery: 47 focused tests passed; full web 118 passed and 3 skipped; production build, bootstrap, CI policy and hosted secret scan passed; full bootstrap suite 168 passed.

APBRA-140 governance: 8 focused tests passed; 74 historical authority regressions passed; full bootstrap suite 176 passed; tracked-tree validation passed over 162 files; CI policy, hosted required check and secret scan passed.

Test totals are revision-specific and must be refreshed after changes.

## Production acceptance remains open

The prototype does not satisfy production acceptance for identity/RBAC, multitenancy and tenant isolation, durable knowledge lifecycle, managed secrets, broad Power BI compatibility, publishing, gateway/credential orchestration, reviewer workflow, performance/load, resilience/DR, SLOs/monitoring/on-call, broad evaluation, privacy/compliance operations or commercial operations.

Generated ≠ validated ≠ Desktop verified ≠ approved ≠ released ≠ deployed.
