# APBRA bounded MVP web application

This React/Vite application is a working bounded enterprise Power BI automation prototype. It separates the business workspace from tenant administration.

## User experience

Business users use **Create Report** and **My Runs**. Business Mode is default: a run accepts a free-text requirement and synthetic CSV/XLSX data, asks bounded material business questions, interprets natural-language answers, presents a business summary and requires explicit confirmation before ConfirmedRequirementContract v2. Advanced/BI Mode accepts optional supported technical preferences without forcing manual report design.

Administrators inspect Tenant Settings, AI & Models, Governed Knowledge, Branding & Report Standards, and Guardrails & Generation. These are local prototype settings, not production identity or tenant controls. My Runs is browser-session history and does not imply durable persistence.

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
