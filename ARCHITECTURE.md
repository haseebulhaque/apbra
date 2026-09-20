# APBRA Capstone architecture

This document describes the merged bounded Capstone implementation and separates it from the future production architecture. It aligns with Confluence 21.03 and the accepted implementation decisions recorded in the repository.

## Application planes

The React/Vite prototype has two clearly separated areas:

- **Business workspace:** Create Report and My Runs.
- **Administration:** Tenant Settings, AI & Models, Governed Knowledge, Branding & Report Standards, and Guardrails & Generation.

The separation represents the intended responsibility boundary. The Capstone does not implement authentication, RBAC, durable tenants or a production administration service.

## Implemented processing pipeline

```text
Requirement + request-specific CSV/XLSX schema
→ Azure AI Foundry GPT-4.1 interpretation
→ dynamic clarification questions and answers
→ confirmed requirements
→ APBRA in-app governed retrieval
→ original AI Report Design
→ deterministic Report Design normalization
→ strict Report Design integrity validation
→ deterministic guardrails
→ bounded PBIP/PBIR compiler
→ deterministic candidate validation
→ terminal status
```

Terminal statuses are Candidate Ready, Human Review Required, Unsupported and Blocked. Generation does not start after a normalization, integrity or policy safe-stop.

### AI boundary

The current adapter uses an Azure AI Foundry/Azure OpenAI-compatible endpoint. Live evidence observed `gpt-4.1-2025-04-14`; embeddings use `text-embedding-3-small` with 1,536 dimensions. GPT interprets requirements, detects ambiguity, creates clarifications and proposes a grounded structured Report Design. It cannot approve guardrails, establish measure correctness, select release authority or certify candidate validity.

### Request schema boundary

CSV/XLSX structure is request-specific context, not tenant knowledge. Parsing extracts bounded table, sheet, column, type, limited sample and explicitly discoverable relationship metadata. Workbook bytes and unnecessary raw business data are not placed in the governed corpus.

## Governed in-app RAG

Five fictional APBRA organisational standards are chunked using headings and bounded token-aware windows. The current corpus contains 20 chunks. `text-embedding-3-small` embeds the corpus and runtime query; an in-memory exact cosine comparison selects configurable top-k results with source, version, heading, chunk and citation provenance.

This Capstone implementation does **not** use the historical S08 Foundry Knowledge store, and no claim is made that APBRA documents were uploaded there. Production still requires tenant upload, replacement/deletion, extraction, versioning, chunk lifecycle, stale-chunk cleanup, re-indexing, permissions, durable vector infrastructure, tenant isolation and monitoring.

## Original and normalized Report Design

The original AI Report Design is retained as evidence. A separate deterministic normalizer converts safely expressible intent into the strict compiler contract before validation. Examples include splitting independent slicer fields into separate slicers and collapsing an identical field/category duplicate.

Normalization uses stable deterministic IDs, deterministic compiler-aligned placement and page-bound checks. It does not repair zero-binding or measure-bound slicers, unknown fields, ambiguous semantics or layouts without capacity. Those cases create a typed finding and stop before compilation. APBRA-139 therefore complements rather than weakens APBRA-138 integrity.

## Strict integrity boundary

Integrity validation enforces canonical unique measure identities, supported aggregations, resolved ratio operands, self-reference prevention, dependency-cycle detection, validity of unused measures, visual measure references and per-type binding cardinality. A slicer must resolve to exactly one field/category binding and zero measures after normalization. The compiler repeats defensive checks before generating files.

## Bounded compiler and layout

The deterministic compiler consumes only the normalized, validated Report Design. Its page contract is 1,280 × 720. The compiler-aligned grid uses columns at x=20 and x=630, and rows at `y = 30 + row × 260`. Cards are 285 × 120; other supported visuals are 580 × 230.

Every visual must satisfy `x ≥ 0`, `y ≥ 0`, `x + width ≤ 1280`, and `y + height ≤ 720`. Existing and expanded visuals both consume capacity. If placement cannot fit, `LAYOUT_CAPACITY_EXCEEDED` records the attempted layout and compilation remains `NOT_STARTED`.

The supported subset includes common KPI cards, bar/column/line charts, tables, slicers, multiple bounded pages, explicit supported measures, simple relationships and tenant theme colours. Unsupported visuals, arbitrary model-authored DAX/M/SQL, DirectQuery/Direct Lake, autonomous publishing and production credential configuration are not silently substituted.

## Validation and handover

Candidate validation checks project/package structure, report/model references, supported visuals, measure and field references, relationships and generated identifiers. Power BI Desktop remains the final runtime proof.

Successful candidates expose a Power BI project archive and lazy-loaded `Report-Deployment-Guide.pdf`. The PDF provides contextual deployment and handover instructions; it is evidence of guide generation, not production deployment.

## Production architecture gap

The Capstone is a local bounded prototype. A production system still needs server-side identity and authorization, durable tenant state, isolated storage/indexes, managed secrets, durable orchestration, production publishing APIs, gateway/credential workflows, reviewer lifecycle, observability/SLOs, resilience/DR, broader compatibility/evaluation and privacy/compliance operations. The modular-monolith and port/adapter direction remains the intended production decomposition; the browser prototype is not evidence those services already exist.
