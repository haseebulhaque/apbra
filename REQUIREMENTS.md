# APBRA bounded MVP requirements and delivery map

This repository view separates implemented Capstone behaviour, verified evidence and future product requirements. Confluence remains authoritative for requirements and Jira for delivery intent.

## Implemented Capstone requirements

| Capability | Implemented behaviour | Current evidence boundary |
| --- | --- | --- |
| Requirement discovery | Free text, CSV/XLSX schema, Business Mode default and optional Advanced/BI preferences | Bounded iterative GPT-4.1 clarification |
| Requirements confirmation | Immutable raw provenance, business summary and explicit human confirmation | Confirmation precedes authority |
| Semantic contract | ConfirmedRequirementContract v2 freezes exact typed meaning and obligations | APBRA-143/144 tests and live acceptance |
| Governed retrieval | Five fictional organisational standards, 20 heading-aware chunks, exact cosine retrieval and citations | Canonical citations: `CB-001`, `PM-002`, `RD-004`, `RD-001`; `embeddingCalls` is null, so no call count is claimed |
| Report Design | GPT-4.1 produces a grounded typed original design | Original design is retained separately from normalized design |
| Preservation/correction | Exact obligation coverage; one bounded correction with deterministic findings and full revalidation | Confirmed measures cannot change |
| Normalization/layout | Safe structural normalization, geometry validation and bounded repair | Original/repaired designs remain distinct |
| Integrity | Measures, ratio operands, cycles, visual references and visual cardinality are checked deterministically | Canonical run: recorded `MEASURE_INTEGRITY` PASS; no unsupported finding count is claimed |
| Guardrails | Structured policies return pass, warning, review, blocked or out-of-scope results | Current happy path PASS; unsupported requests stop safely |
| Generation | Bounded deterministic PBIP/PBIR compiler supports common model and visual structures | Current compiler result COMPLETED |
| Candidate validation | Required files and references are checked without trusting compiler success | Current deterministic validation PASS |
| Handover | Successful runs can generate `Report-Deployment-Guide.pdf` | Dynamic and lazy-loaded; does not mean deployed |

The runtime order is requirement/schema/context → iterative interpretation/clarification → human confirmation → typed contract → governed RAG → original GPT ReportDesign → coverage/integrity/normalization/layout → bounded correction/repair when eligible → guardrails → compiler → candidate validation.

## Current acceptance evidence

Run `8042cc44-620f-4457-828d-0770749a653f` reached Candidate Ready after human confirmation. It created `SalesPerformance` with `Total Sales = SUM(Sales_Data.Revenue)`, an Executive Summary, Total Sales card, regional bar chart and Region slicer. Compiler and recorded deterministic candidate checks passed. No durable digest or exact-candidate Desktop PASS is recorded.

Interpretation recorded 8,608 prompt + 1,207 completion = 9,815 tokens; ReportDesign recorded 6,430 + 964 = 7,394. Both used `gpt-4.1-2025-04-14`. `embeddingCalls` is null; no precise embedding cost is claimed.

## Negative evidence and supported boundary

Run `0927fd18-1c61-4610-8167-de86933a1de1` confirmed monthly intent but stopped at `REPORT_DESIGN_COVERAGE_INVALID` with no candidate. A comparative Sales scenario exhausted clarification/correction and routed to Human Review Required with no contract/candidate; the known prototype could briefly show Ready for Confirmation immediately beforehand.

DAY, MONTH, QUARTER and YEAR are genuinely represented. WEEK, fiscal/custom calendars and locale-specific policies are unsupported. Historical ServiceNow/Sales measure, reference, layout, clarification, citation and coverage failures remain regression evidence, not the current happy path.

## Future product requirements

Production work remains for authentication/RBAC, real multitenancy and tenant isolation; durable knowledge upload/extraction/version/index lifecycle; managed secrets; broader Power BI compatibility; tenant publishing; gateway and credential orchestration; production reviewer workflow; load, resilience and disaster recovery; SLOs, monitoring and on-call; broader evaluation; privacy/compliance operations; and commercial operations.

Generated does not mean validated, approved, released or deployed. Missing or skipped mandatory evidence remains incomplete.
