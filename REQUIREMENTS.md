# APBRA current and target requirements map

## Current APBRA-174 implemented slice

The protected case experience permits zero or optional model-generated clarification questions and explicit bounded Clarify/Enhance cycles. The seeded tenant policy is two clarification rounds per cycle and ten rounds overall; durable server state enforces the active settings version. A ready interpretation may be accepted with optional questions unanswered, but unresolved mandatory blockers cannot be bypassed. Supported partial scope and omissions are shown before exact acceptance; material changes stale earlier acceptance.

Owner/Admin can inspect, edit, version and restore validated tenant settings and replace protected credentials without seeing plaintext. Provider/model/region activation requires qualified explicit configuration. Automatic ReportDesign remains subject to deterministic validation and cannot use a business-specific fallback. The canonical compiler resolves technical measure/column namespace collisions without changing semantic objects. Successful candidate ZIPs include a digest-bound Delivery / Instruction Guide; they are not evidence of Desktop execution, release approval or deployment. Earlier Capstone rows below remain historical evidence.

This repository view separates implemented Capstone behaviour, verified evidence and future product requirements. Confluence remains authoritative for requirements and Jira for delivery intent.

## Accepted APBRA-175 architecture requirements — future implementation

[Confluence 04.07 v1](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/9568258) and [04.08 v1](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/9535525) refine the target without turning deployment or entitlement runtime into a current MVP gate. APBRA Cloud, Dedicated and qualified Private / On-Premises are target deployment profiles; air-gapped support requires later qualification. Azure is a reference/private-preview option, not a core product requirement. The local/CI PostgreSQL case application does not prove any production profile.

The future central control plane may retain minimum organisation, stable `deployment_id`, subscription/edition, entitlement, licence and release/update metadata. Customer users/mappings, Tenant Settings, protected credentials, uploads, prompts, accepted requirements, generated reports/Delivery Guides and audit/history belong to the selected customer data plane; licence checks do not require content transfer. `deployment_id` identifies an installation, while `tenant_id` identifies the company security domain. A shared Cloud installation may host many tenants; Dedicated/Private relationships require qualification.

Commercial availability follows **Subscription → versioned Entitlements → stable Capabilities**. Effective capability is the intersection of installed platform support, entitlement, Tenant Settings, user/application permission, resource permission and current safety/validation/governance. Paid access cannot waive authorization, tenant isolation, private-resource access, target validity, deterministic checks or release approval. Core product logic should use capability keys rather than marketing plan-name branches. Exact plans, prices, quotas, grace periods, provider and billing choices are undecided; APBRA-153 requires separate implementation authority. Current bounded PBIP/PBIR/TMDL output is not an implemented ARD/native renderer or non-Power-BI adapter; Confluence 03.06 v1 and APBRA-165 govern that future direction.

## Historical Capstone requirements and evidence

| Historical capability | Capstone behaviour | Capstone evidence boundary |
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

`APBRA-PRODUCT-2026-09-22` is the accepted target-product baseline. The definitions below preserve the Business and Functional Requirements 02.01 v4 and Requirements Traceability Matrix 02.06 v6 mappings as recorded at the earlier post-Capstone reconciliation. The accepted 04.07 v1 and 04.08 v1 direction above adds deployment and entitlement architecture; this historical mapping is not a claim that those source versions are still the latest. Every row is **TARGET / PLANNED unless separately proven by the current protected slice or historical Capstone evidence above**. A Jira item or target requirement is not implementation evidence.

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
| `PC26-FR-011` | Subscription resolves to versioned capability entitlements and usage visibility under a separately accepted commercial model; no plan name, price or application permission is implied. | APBRA-153, APBRA-83, APBRA-117 | README, acceptance criteria |
| `PC26-FR-012` | Tenant-governed branding, terminology, organisational standards and configuration influence generation without overriding authority. | APBRA-154, APBRA-35, APBRA-41, APBRA-54, APBRA-72 | Architecture, AI/RAG spec, web README |
| `PC26-FR-013` | Qualified APBRA-managed and customer-managed model profiles, including approved private/local profiles where supported. | APBRA-155, APBRA-38, APBRA-46, APBRA-114 | AI/RAG spec, architecture |
| `PC26-FR-014` | Optional customer Azure provisioning in the Azure reference profile requires separate explicit authority; an inference key is not management authority and Azure is not a universal product dependency. | APBRA-156, APBRA-77, APBRA-114, APBRA-117 | Architecture, AI/RAG spec, handoff |
| `PC26-FR-015` | Later bounded source discovery and Power BI/Fabric deployment profiles qualify permissions and evidence for publishing, connections, gateways, refresh and applicable security configuration. | APBRA-157, APBRA-50, APBRA-57, APBRA-73, APBRA-110 | Generation spec, architecture, acceptance criteria |
| `PC26-FR-016` | Optional advanced data-architecture assessment and reviewable scripts remain separate from ordinary report creation; source schemas are not modified automatically. | APBRA-158, APBRA-43, APBRA-46, APBRA-79 | Architecture, generation spec, web README |
| `PC26-FR-017` | Privacy, tenant isolation, RAG safety, deterministic guardrails, evaluations, red teaming, tracing, reliability and cost controls apply across the product. | APBRA-42, APBRA-59, APBRA-60, APBRA-78, APBRA-80, APBRA-81, APBRA-83, APBRA-87, APBRA-117, APBRA-155, APBRA-157 | Architecture, AI/RAG spec, acceptance criteria |
| `PC26-FR-018` | “No dead ends” means truthful recovery, supported alternatives and actionable expert continuation—not guaranteed generation or disguised technical failure. | APBRA-150, APBRA-31, APBRA-63, APBRA-82, APBRA-99; APBRA-147 was a separate planning hold at mapping time | README, architecture, acceptance criteria |

## Target boundary

The accepted target includes company identity and membership, tenant isolation, optional projects and collaboration, capability-based licensing/usage visibility, durable governed knowledge, qualified model profiles, separately consented Azure provisioning where applicable, broader Power BI discovery/delivery, future ARD/native reporting and other adapters, review/release workflow, reliability/FinOps and privacy/compliance operations. Local/CI invited identity, durable private cases/settings/evidence and bounded Power BI generation already exist; production profiles and entitlement runtime do not follow from those foundations. None is marked implemented merely because it appears above.

The target does not select a delivery milestone, replacement stack, model/provider, region, price, SLA or new numerical limit. Licences, modes, company membership and model keys do not grant private-resource access, trusted-author status or external management authority. Expert assistance, business acceptance, inspection download, release approval and successful deployment remain separate events.

A future policy-eligible trusted author may omit only a separate human release-review step where an accepted policy explicitly permits it. Trusted-author eligibility does not collapse business acceptance, inspection download, creation of an eligible release package or successful deployment into one event, and it never grants source, tenant or external-management access by itself.

Generated does not mean validated, approved, released or deployed. Missing or skipped mandatory evidence remains incomplete.
