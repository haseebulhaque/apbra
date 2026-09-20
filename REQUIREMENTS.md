# APBRA Capstone requirements and delivery map

This repository view separates implemented Capstone behaviour, verified evidence and future product requirements. Confluence remains authoritative for requirements and Jira for delivery intent.

## Implemented Capstone requirements

| Capability | Implemented behaviour | Current evidence boundary |
| --- | --- | --- |
| Requirement discovery | Free-text requirement, real CSV/XLSX schema parsing and GPT-4.1 structured interpretation | Live run produced three dynamic clarification questions |
| Requirements confirmation | Business-facing summary retains original requirement, schema reference, interpretation, questions, answers and assumptions | Browser workflow and tests |
| Governed retrieval | Five fictional organisational standards, 20 heading-aware chunks, exact cosine retrieval and citations | Current run: two embedding calls, top-k 4 and four citations |
| Report Design | GPT-4.1 produces a grounded typed original design | Original design is retained separately from normalized design |
| Normalization | Supported multi-binding slicer intent becomes stable compiler-safe visuals with bounded layout | Current run: two `DUPLICATE_BINDING_COLLAPSED` actions |
| Integrity | Measures, ratio operands, cycles, visual references and visual cardinality are checked deterministically | Current run: zero findings and PASS |
| Guardrails | Structured policies return pass, warning, review, blocked or out-of-scope results | Current happy path PASS; unsupported requests stop safely |
| Generation | Bounded deterministic PBIP/PBIR compiler supports common model and visual structures | Current compiler result COMPLETED |
| Candidate validation | Required files and references are checked without trusting compiler success | Current deterministic validation PASS |
| Handover | Successful runs can generate `Report-Deployment-Guide.pdf` | Dynamic and lazy-loaded; does not mean deployed |

The runtime order is requirement/schema → interpretation → clarification → governed RAG → original AI Report Design → deterministic normalization → strict integrity → guardrails → compiler → deterministic candidate validation.

## Current acceptance evidence

Run `d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa` reached Candidate Ready. Its archive SHA-256 is `833dff4ba7de7045e23ff6b42ce1e48e73b33534f1f910e7420753a1c5eab0f3`. All eight visuals fit the 1,280 × 720 page contract, with maximum right edge 1,210 and maximum bottom edge 520.

Power BI Desktop validation of this exact candidate remains **PENDING**. Historical Desktop PASS results for SalesPerformance and ServiceDeskOperations cannot be transferred to different candidate bytes.

Revision-specific APBRA-139 evidence records 47 focused tests, 118 web tests passing with 3 skipped, build PASS, bootstrap PASS, 168 bootstrap tests, CI policy PASS and hosted secret scan PASS. APBRA-140 governance evidence records 8 focused tests, 74 historical regressions, 176 bootstrap tests, tracked-tree PASS over 162 files, CI policy PASS, hosted required check PASS and secret scan PASS.

## Pending Capstone evidence

- Power BI Desktop open/render inspection of the exact current candidate.
- A final captured unsupported/unrealistic failure demonstration.
- Attributable cost evidence rather than an estimate presented as measured cost.
- Final screenshots, 90-second demonstration and nine-slide evidence deck.

The failure demonstration should use an intentionally unsupported or unrealistic request, not a historical ServiceNow defect. It should finish Unsupported, Human Review Required or Blocked without producing a misleading candidate.

## Future product requirements

Production work remains for authentication/RBAC, real multitenancy and tenant isolation; durable knowledge upload/extraction/version/index lifecycle; managed secrets; broader Power BI compatibility; tenant publishing; gateway and credential orchestration; production reviewer workflow; load, resilience and disaster recovery; SLOs, monitoring and on-call; broader evaluation; privacy/compliance operations; and commercial operations.

Generated does not mean validated, approved, released or deployed. Missing or skipped mandatory evidence remains incomplete.
