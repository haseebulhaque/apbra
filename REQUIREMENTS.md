# APBRA current and target requirements map

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

## Accepted post-Capstone product requirements

`APBRA-PRODUCT-2026-09-22` is the accepted target-product baseline. The definitions below summarize Business and Functional Requirements 02.01 v4 and the Jira links reproduce Requirements Traceability Matrix 02.06 v6. Every row is **TARGET / PLANNED unless separately proven in the implemented table above**. A Jira item or target requirement is not implementation evidence.

| Requirement | Accepted target outcome | Existing Jira delivery coverage | Repository documentation home |
| --- | --- | --- | --- |
| `PC26-FR-001` | Guided and Advanced experiences share one engine; suggestions and free text are supported while AI retains ordinary BI-design responsibility. | APBRA-24, APBRA-31, APBRA-103 | README, Architecture, web README |
| `PC26-FR-002` | Conversation-first intake works without mandatory upload or project creation and accepts a plain-language data-source description. | APBRA-13, APBRA-28, APBRA-34 | README, Architecture, web README |
| `PC26-FR-003` | Supported schema/data screenshots are qualified evidence with provenance and uncertainty, never unqualified schema truth. | APBRA-149, APBRA-28, APBRA-79 | Architecture, AI/RAG spec, web README |
| `PC26-FR-004` | Report screenshots and sketches may guide design but remain separate from source, schema and measure truth. | APBRA-149, APBRA-43, APBRA-54 | Architecture, AI/RAG spec, generation spec |
| `PC26-FR-005` | Supported alternatives disclose retained intent, assumptions, changes, omissions, limitations and evidence needs. | APBRA-31, APBRA-33, APBRA-46, APBRA-103 | Requirements, architecture, acceptance criteria |
| `PC26-FR-006` | Material rescoping is version-bound and explicitly accepted; earlier confirmations remain provenance. | APBRA-34, APBRA-102, APBRA-103, APBRA-71 | Requirements, architecture, acceptance criteria |
| `PC26-FR-007` | An authorized BI expert can take over and continue the same case with its conversation, evidence, decisions and findings. | APBRA-150, APBRA-65, APBRA-71, APBRA-99 | Architecture, web README, acceptance criteria |
| `PC26-FR-008` | Company registration, membership and account/sign-in profiles are distinct from consent to external tenant resources. | APBRA-151, APBRA-77, APBRA-78 | Architecture, web README |
| `PC26-FR-009` | Projects are optional; later assignment and authorized sharing/collaboration are supported. | APBRA-152, APBRA-13, APBRA-78, APBRA-104 | README, architecture, web README |
| `PC26-FR-010` | Requirements, outputs, designs, candidates, validation and deployment evidence retain linked histories. | APBRA-152, APBRA-49, APBRA-58, APBRA-71, APBRA-104; APBRA-157 for deployment | Architecture, generation spec, evidence record |
| `PC26-FR-011` | Subscription, seats, feature entitlements and usage visibility follow a separately accepted commercial model; no price is implied. | APBRA-153, APBRA-83, APBRA-117 | README, acceptance criteria |
| `PC26-FR-012` | Tenant-governed branding, terminology, organisational standards and configuration influence generation without overriding authority. | APBRA-154, APBRA-35, APBRA-41, APBRA-54, APBRA-72 | Architecture, AI/RAG spec, web README |
| `PC26-FR-013` | Qualified APBRA-managed and customer-managed model profiles, including approved private/local profiles where supported. | APBRA-155, APBRA-38, APBRA-46, APBRA-114 | AI/RAG spec, architecture |
| `PC26-FR-014` | Optional customer Azure provisioning requires separate explicit authority; an inference key is not management authority. | APBRA-156, APBRA-77, APBRA-114, APBRA-117 | Architecture, AI/RAG spec, handoff |
| `PC26-FR-015` | Later bounded source discovery and Power BI/Fabric deployment profiles qualify permissions and evidence for publishing, connections, gateways, refresh and applicable security configuration. | APBRA-157, APBRA-50, APBRA-57, APBRA-73, APBRA-110 | Generation spec, architecture, acceptance criteria |
| `PC26-FR-016` | Optional advanced data-architecture assessment and reviewable scripts remain separate from ordinary report creation; source schemas are not modified automatically. | APBRA-158, APBRA-43, APBRA-46, APBRA-79 | Architecture, generation spec, web README |
| `PC26-FR-017` | Privacy, tenant isolation, RAG safety, deterministic guardrails, evaluations, red teaming, tracing, reliability and cost controls apply across the product. | APBRA-42, APBRA-59, APBRA-60, APBRA-78, APBRA-80, APBRA-81, APBRA-83, APBRA-87, APBRA-117, APBRA-155, APBRA-157 | Architecture, AI/RAG spec, acceptance criteria |
| `PC26-FR-018` | “No dead ends” means truthful recovery, supported alternatives and actionable expert continuation—not guaranteed generation or disguised technical failure. | APBRA-150, APBRA-31, APBRA-63, APBRA-82, APBRA-99; APBRA-147 remains a separate planning hold | README, architecture, acceptance criteria |

## Target boundary

The accepted target includes company identity and membership, tenant isolation, optional projects and collaboration, licensing/usage visibility, durable governed knowledge, qualified model profiles, separately consented Azure provisioning, broader Power BI discovery/delivery, review/release workflow, reliability/FinOps and privacy/compliance operations. None is marked implemented merely because it appears above.

The target does not select a delivery milestone, replacement stack, model/provider, region, price, SLA or new numerical limit. Licences, modes, company membership and model keys do not grant private-resource access, trusted-author status or external management authority. Expert assistance, business acceptance, inspection download, release approval and successful deployment remain separate events.

A future policy-eligible trusted author may omit only a separate human release-review step where an accepted policy explicitly permits it. Trusted-author eligibility does not collapse business acceptance, inspection download, creation of an eligible release package or successful deployment into one event, and it never grants source, tenant or external-management access by itself.

Generated does not mean validated, approved, released or deployed. Missing or skipped mandatory evidence remains incomplete.
