# APBRA bounded MVP web application

This React/Vite application is a working bounded enterprise Power BI automation prototype. It separates the business workspace from tenant administration.

It is not the complete `APBRA-PRODUCT-2026-09-22` experience. The current UI and the accepted target are distinguished below.

## User experience

Business users use **Create Report** and **My Runs**. Business Mode is default: a run accepts a free-text requirement and synthetic CSV/XLSX data, asks bounded material business questions, interprets natural-language answers, presents a business summary and requires explicit confirmation before ConfirmedRequirementContract v2. Advanced/BI Mode accepts optional supported technical preferences without forcing manual report design.

Administrators inspect Tenant Settings, AI & Models, Governed Knowledge, Branding & Report Standards, and Guardrails & Generation. These are local prototype settings, not production identity or tenant controls. My Runs is browser-session history and does not imply durable persistence.

## Accepted product experience — planned

Guided and Advanced experiences will share this reasoning and assurance engine. The target starts with conversation and does not require a file or project. A user may describe a source in business language and may later provide qualified schema/data uploads, screenshots or report/sketch references. The UI must state what each item can establish: a design reference is not data truth, and an accepted assumption cannot prove a missing field, source fact or permission.

The target keeps material business decisions understandable and explicit while leaving ordinary supported BI design to AI. Supported alternatives must disclose retained intent, changed scope, assumptions, omissions, limitations and evidence needs; material rescoping requires acceptance before generation. “No dead ends” means a useful supported alternative or authorized-expert continuation, not guaranteed generation.

Future case and account UX covers authorized BI-expert takeover of the same conversation/evidence, company registration and membership, optional projects, controlled collaboration, linked histories, licensing/seat entitlement and usage visibility, and tenant branding/terminology/standards. Company membership, a mode, licence or model key does not itself grant private-source, tenant-management, release or deployment authority.

Qualified model profiles, separately consented Azure provisioning, connected Power BI delivery and optional advanced data-architecture advice remain future capabilities. The current local administration screens do not prove any of them. APBRA-149–158 are planning items, not implemented UI.

## Implemented workflow

```text
requirement + parsed schema
→ GPT-4.1 interpretation
→ bounded iterative clarification + immutable raw provenance
→ human confirmation → ConfirmedRequirementContract v2
→ governed in-app RAG
→ original grounded Report Design
→ deterministic obligation coverage, normalization and integrity
→ bounded correction/layout repair when eligible, with full revalidation
→ deterministic guardrails
→ bounded PBIP/PBIR compiler
→ deterministic validation
→ candidate or truthful safe-stop
```

The original AI design is retained. Correction cannot add unconfirmed measures or business meaning. Zero-binding, measure-bound, unknown, ambiguous, unsupported or out-of-capacity designs stop rather than being silently changed. Human Review Required, Unsupported, Out of Scope and technical failure remain distinct.

## Run locally

Copy `.env.example` to ignored `.env.local` and provide the existing Azure AI Foundry configuration. The browser never displays the API key.

```sh
npm ci
npm test
npm run build
npm run dev
```

Vite normally serves `http://127.0.0.1:5173/`. AI-dependent stages show an unavailable/error state if the configured endpoint cannot be reached.

## AI and governed knowledge

The chat adapter uses GPT-4.1 through an Azure AI Foundry/Azure OpenAI-compatible endpoint; live evidence observed `gpt-4.1-2025-04-14`. Five fictional Markdown standards under `knowledge/` form a 20-chunk heading-aware governed corpus. `text-embedding-3-small` produces 1,536-dimensional embeddings, and an in-memory exact cosine index returns configurable top-k citations.

This is APBRA's in-app retrieval implementation, not the historical S08 Foundry Knowledge store. Uploaded report schemas remain request-specific context and are not indexed as tenant knowledge.

## Compiler, validation and downloads

The bounded compiler supports common cards, bar/column/line charts, tables, slicers, supported measures, simple relationships, multiple pages and tenant theme colours. DAY, MONTH, QUARTER and YEAR trends have genuine representations; WEEK remains unsupported. It does not execute arbitrary model-authored DAX/M/SQL or publish to Power BI.

Strict integrity checks cover measure identity and operands, dependency cycles, visual references and visual cardinality. Pages use a 1,280 × 720 bounded grid; a layout without deterministic capacity stops before compilation.

Successful runs expose:

- A generated Power BI project candidate for Desktop validation.
- Lazy-loaded `Report-Deployment-Guide.pdf`, dynamically populated with report-specific handover guidance.

The PDF does not mean deployment occurred. Production publishing, credentials and gateway configuration remain manual/future capabilities.

## Technical evidence and claim boundary

Expandable technical evidence records run ID, model, latency/tokens, embedding calls, retrieval/citations, original and normalized visual counts, normalization actions, integrity findings, guardrails, compiler, validation and final status.

Implemented locally does not mean production ready. Identity/RBAC, real multitenancy, durable knowledge ingestion/indexing, managed secrets, broad compatibility, publishing, reviewer workflow, resilience, monitoring and compliance operations remain future work.
