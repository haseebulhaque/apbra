# APBRA bounded MVP architecture

This document describes the post-Capstone implementation through APBRA-145 and separates it from the accepted `APBRA-PRODUCT-2026-09-22` target architecture. Capstone is complete/submitted; product development continues.

> **GPT-4.1 reasons. The human clarifies and confirms. The typed contract freezes confirmed meaning. Deterministic software validates safety and preservation.**

## Application planes

The React/Vite prototype has two clearly separated areas:

- **Business workspace:** Create Report and My Runs.
- **Administration:** Tenant Settings, AI & Models, Governed Knowledge, Branding & Report Standards, and Guardrails & Generation.

The separation represents the intended responsibility boundary. The Capstone does not implement authentication, RBAC, durable tenants or a production administration service.

## Accepted target architecture — planned, not implemented

The product target keeps a single reasoning and assurance engine behind Guided and Advanced experiences. Intake becomes conversation-first and may begin without a file or project. Plain-language source descriptions, qualified schema/data uploads, screenshots and report/sketch references are distinct evidence classes: visual evidence can inform questions and design, but cannot prove an absent field, source fact, permission or measure definition.

The case becomes the durable unit of continuation. It may later be assigned to an authorized BI expert without losing the conversation, evidence, accepted decisions or deterministic findings. Optional projects, collaboration and linked requirement/report/candidate/deployment histories sit around that case. Company registration, membership, sign-in profiles, subscriptions and usage visibility are product controls; they do not automatically grant access to customer tenants, private sources, trusted-author status or external management operations.

Tenant configuration is intended to cover branding, terminology, governed standards, model profiles and policy. APBRA-managed and customer-managed model profiles—including separately approved private/local options—must be qualified. Customer Azure provisioning is a separate, explicit-consent management operation; possession of an inference key is not provisioning authority.

PBIP delivery and deployment guidance remain the first delivery boundary. Connected-source discovery, Power BI/Fabric publishing, connections, gateways, refresh and applicable security configuration require separately qualified permissions and evidence. Optional data-architecture assessment and reviewable scripts are a separate advanced capability and must never modify a source schema automatically.

The target architecture adds production identity and tenant isolation, durable persistence and knowledge lifecycle, controlled sharing/review/release, observability, evaluation/red teaming, reliability and FinOps. It does not select a replacement stack, provider, region, commercial price, SLA or numerical limit. APBRA-149–158 describe planning slices; they are not proof that these services exist.

## Implemented processing pipeline

```text
Requirement + request-specific CSV/XLSX schema
→ Azure AI Foundry GPT-4.1 interpretation
→ bounded iterative clarification with immutable raw-answer provenance
→ READY_FOR_CONFIRMATION and explicit human confirmation
→ ConfirmedRequirementContract v2
→ APBRA in-app governed retrieval
→ original AI Report Design
→ deterministic obligation coverage, normalization and integrity validation
→ one bounded structured correction and complete revalidation when eligible
→ bounded layout repair when eligible
→ deterministic guardrails
→ bounded PBIP/PBIR compiler
→ deterministic candidate validation
→ terminal status
```

Terminal statuses include Candidate Ready, Human Review Required, Unsupported, Out of Scope and Blocked. Technical provider/infrastructure failure remains separate. Generation does not start after a semantic, coverage, integrity, capability or policy safe-stop.

### AI boundary

The current adapter uses an Azure AI Foundry/Azure OpenAI-compatible endpoint. Live evidence observed `gpt-4.1-2025-04-14`; embeddings use `text-embedding-3-small` with 1,536 dimensions. GPT detects material ambiguity, interprets natural-language answers and proposes confirmed meaning and a grounded ReportDesign. Business Mode is default; Advanced/BI Mode accepts optional technical preferences. GPT chooses ordinary supported BI presentation but cannot approve guardrails, establish measure correctness, select release authority or certify candidate validity.

### Confirmation boundary

Raw requirements, questions and answers remain immutable provenance. Only human-confirmed structured meaning enters ConfirmedRequirementContract v2. Deterministic TypeScript does not infer business meaning from arbitrary prose. Coverage later proves exact typed obligations, business-question mappings, measures, fields, page scope and time semantics remain represented.

An accepted assumption is a visible business decision, not evidence for an absent field, unknown source fact, missing permission or unsupported capability. Any material rescope must return to explicit acceptance and retain the earlier confirmation as provenance.

### Request schema boundary

CSV/XLSX structure is request-specific context, not tenant knowledge. Parsing extracts bounded table, sheet, column, type, limited sample and explicitly discoverable relationship metadata. Workbook bytes and unnecessary raw business data are not placed in the governed corpus.

## Governed in-app RAG

Five fictional APBRA organisational standards are chunked using headings and bounded token-aware windows. The current corpus contains 20 chunks. `text-embedding-3-small` embeds the corpus and runtime query; an in-memory exact cosine comparison selects configurable top-k results with source, version, heading, chunk and citation provenance.

This Capstone implementation does **not** use the historical S08 Foundry Knowledge store, and no claim is made that APBRA documents were uploaded there. Production still requires tenant upload, replacement/deletion, extraction, versioning, chunk lifecycle, stale-chunk cleanup, re-indexing, permissions, durable vector infrastructure, tenant isolation and monitoring.

## Original and normalized Report Design

The original AI Report Design is retained as evidence. A separate deterministic normalizer converts safely expressible intent into the strict compiler contract before validation. Examples include splitting independent slicer fields into separate slicers and collapsing an identical field/category duplicate.

Normalization uses stable deterministic IDs, compiler-aligned placement and page-bound checks. One bounded ReportDesign correction may receive exact domain-neutral findings; it cannot alter confirmed measures/business meaning and corrected output is fully revalidated. Bounded layout repair preserves original and repaired designs separately. Unsupported ambiguity or capacity creates a typed finding and stops.

## Strict integrity boundary

Integrity validation enforces canonical unique measure identities, supported aggregations, resolved ratio operands, self-reference prevention, dependency-cycle detection, validity of unused measures, visual measure references and per-type binding cardinality. A slicer must resolve to exactly one field/category binding and zero measures after normalization. The compiler repeats defensive checks before generating files.

## Bounded compiler and layout

The deterministic compiler consumes only the normalized, validated Report Design. Its page contract is 1,280 × 720. The compiler-aligned grid uses columns at x=20 and x=630, and rows at `y = 30 + row × 260`. Cards are 285 × 120; other supported visuals are 580 × 230.

Every visual must satisfy `x ≥ 0`, `y ≥ 0`, `x + width ≤ 1280`, and `y + height ≤ 720`. Existing and expanded visuals both consume capacity. If placement cannot fit, `LAYOUT_CAPACITY_EXCEEDED` records the attempted layout and compilation remains `NOT_STARTED`.

The supported subset includes common KPI cards, bar/column/line charts, tables, slicers, multiple bounded pages, explicit supported measures, simple relationships and tenant theme colours. GPT chooses among supported visual types; deterministic code does not impose universal KPI/card or trend/line preferences.

DAY uses the raw temporal binding. MONTH, QUARTER and YEAR use generated grouping columns based on `Date.StartOfMonth`, `Date.StartOfQuarter` and `Date.StartOfYear`; generated names are collision-checked and candidate validation proves both grouping and visual binding. A raw Date binding cannot falsely prove a non-DAY grain. WEEK, fiscal/custom calendars and locale-specific policies remain unsupported.

Unsupported visuals, arbitrary model-authored DAX/M/SQL, DirectQuery/Direct Lake, write-back, inferred RLS, autonomous publishing and production credential configuration are not silently substituted.

## Validation and handover

Candidate validation checks project/package structure, report/model references, supported visuals, measure and field references, relationships and generated identifiers. Power BI Desktop remains the final runtime proof.

Successful candidates expose a Power BI project archive and lazy-loaded `Report-Deployment-Guide.pdf`. The PDF provides contextual deployment and handover instructions; it is evidence of guide generation, not production deployment.

## Production architecture gap

The Capstone is a local bounded prototype. A production system still needs server-side identity and authorization, durable tenant state, isolated storage/indexes, managed secrets, durable orchestration, production publishing APIs, gateway/credential workflows, reviewer lifecycle, observability/SLOs, resilience/DR, broader compatibility/evaluation and privacy/compliance operations. The modular-monolith and port/adapter direction remains the intended production decomposition; the browser prototype is not evidence those services already exist.

The target “no dead ends” behaviour is truthful recovery: a supported alternative that makes every material change visible, or continuation by an authorized expert. It is not guaranteed generation and cannot convert a provider failure, unsupported capability or missing authority into success. Expert assistance, business acceptance, candidate inspection, release approval and successful deployment remain separate lifecycle events.
