# APBRA final Capstone evidence record

Capstone is complete/submitted. The canonical implementation baseline before documentation governance is `65d7281d1132ce5b4eca6d3cd89fd30e95f5c342`; APBRA-146 governance merged at `39ab131643c77d87359dd3fdb28909021f0e9ba9`. The APBRA-148 task contract retains provenance base `d072870fea8b8ae8caedc5e553653a433b697f11`; its registration merged into documentation execution base `c466dcbd928b0b07b5631c61c57b7ca90ce7f965`. These later documentation/governance revisions do not change the recorded Capstone runtime evidence. Historical results remain revision- and candidate-specific.

## Canonical successful acceptance

| Evidence | Observed result |
| --- | --- |
| Run ID | `8042cc44-620f-4457-828d-0770749a653f` |
| Scenario | Simple synthetic SalesPerformance, Business Mode |
| Confirmed meaning | Total Sales = sum Revenue; all data; Sales Managers |
| Contract | ConfirmedRequirementContract v2 after explicit confirmation |
| Model | `gpt-4.1-2025-04-14` |
| Retrieval | `CB-001`, `PM-002`, `RD-004`, `RD-001`; `embeddingCalls = null` |
| ReportDesign | Executive Summary; Total Sales card; regional bar; Region slicer |
| Measure | `Total Sales = SUM(Sales_Data.Revenue)` |
| Guardrails | Recorded checks PASS |
| Compiler | COMPLETED |
| Deterministic validation | PASS |
| Final status | Candidate ready |

Interpretation used 8,608 prompt + 1,207 completion = 9,815 tokens. ReportDesign used 6,430 prompt + 964 completion = 7,394 tokens. No precise embedding cost is claimed.

Recorded PASS checks: `MEASURE_INTEGRITY`, `PROJECT_STRUCTURE`, `TABLE_FILES`, `PAGE_REFERENCES`, `PBIR_IDENTIFIERS`, `VISUAL_IDENTIFIERS`, `VISUAL_COUNT`, `VISUAL_TYPES`, `NO_UNRESOLVED_IDENTIFIERS`, `MEASURE_REFERENCES`, `RELATIONSHIP_REFERENCES`.

No durable candidate digest or exact-candidate Power BI Desktop PASS is recorded. Candidate Ready means generated and deterministically validated—not Desktop verified, deployed or production-ready.

## Fail-closed and HITL evidence

- `0927fd18-1c61-4610-8167-de86933a1de1`: monthly Total Sales was confirmed; GPT ReportDesign failed exact trend/business-question coverage with `REPORT_DESIGN_COVERAGE_INVALID`; no candidate. This proves fail-closed preservation, not lack of MONTH support.
- Comparative Sales clarification exhausted configured limits and routed to Human Review Required with no contract/candidate. Known prototype limitation: the UI could show Ready for Confirmation immediately before confirmation subsequently routed to Human Review.

## Historical evidence

**HISTORICAL — exact candidate Desktop validation**

- `SalesPerformance.candidate.zip` — PASS
- `ServiceDeskOperations.candidate.zip` — PASS

**HISTORICAL — defect discovery and regression evidence**

Earlier ServiceNow/Sales executions exposed measure/reference defects, invalid multi-binding slicers, layout overflow, clarification limits, citation/coverage failures and the monthly-grain mismatch that led to APBRA-145. Run `d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa` and its ServiceManagementFunnel candidate remain historical, not current.

## Test and CI evidence

APBRA-141 through APBRA-145 are merged implementation history covering measure contracts, layout repair, typed confirmation, AI-native clarification and generic time-grain/correction alignment.

Counts are revision-specific and must not be presented as permanent totals.

## Post-Capstone boundary

Desktop/runtime validation may be collected as future engineering evidence but is not a pending Capstone submission task. The demonstrated thesis is: GPT reasons, the human confirms, the typed contract freezes meaning, deterministic controls preserve it, and supported generation can reach Candidate Ready while unsafe/incomplete intent fails closed.

`APBRA-PRODUCT-2026-09-22` defines accepted future product scope. It does not retroactively add company identity, projects, collaboration, licensing, durable tenant RAG, model profiles, Azure provisioning, connected publishing, expert continuation or data-architecture advice to the Capstone evidence. APBRA-149–158 are planning coverage. APBRA-147 remains on planning hold.

The comparative Sales HITL and known Ready-for-Confirmation lifecycle inconsistency remain product evidence to address; they are not a reproduced root-cause diagnosis. The current in-app governed corpus remains distinct from the historical S08 assignment architecture. `embeddingCalls` remains null/unknown where recorded.

## Deployment-guide boundary

Successful runs offer dynamically generated, lazy-loaded `Report-Deployment-Guide.pdf`. It supplies handover, configuration and validation instructions. It does not prove publishing or deployment, and APBRA does not autonomously deploy to a production tenant.
