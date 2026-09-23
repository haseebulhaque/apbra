# APBRA MVP-1 web application

APBRA-162 adds an invite-only, authenticated reporting-case shell backed by the local FastAPI and PostgreSQL services. The browser derives the signed-in actor from `/api/auth/session`; it never supplies authoritative company, membership, role, or private-case permission claims.

An active invited member can create a case without a project or file, list only authorized cases, resume a case after a restart, save a new request version with optimistic concurrency, and inspect request history returned by the API. Selecting a case initializes the existing clarification experience from its persisted current request. The workflow is keyed to the case's current request-version identity, so a saved or reloaded version resets transient clarification, confirmation, design, and generation state.

Invitation bearer secrets are accepted only from the URL fragment of an original `/invite#token=...` link, removed from the address immediately, and sent in the body of fixed-path POST requests. A signed-out browser does not persist or forward the token through login; the user must sign in and reopen the original invitation link.

This React/Vite application is a working bounded enterprise Power BI automation prototype. It separates the business workspace from tenant administration.

It is not the complete `APBRA-PRODUCT-2026-09-22` experience. The current UI and the accepted target are distinguished below.

## User experience

Business users use **Create Report** and **My Runs**. Business Mode is default: a run accepts a free-text requirement and synthetic CSV/XLSX data, asks bounded material business questions, interprets natural-language answers, presents a business summary and requires explicit confirmation before ConfirmedRequirementContract v2. Readiness and confirmation use the same deterministic semantic prerequisites and are bound to the exact interpretation and material input context shown to the user. Advanced/BI Mode accepts optional supported technical preferences without forcing manual report design.

Administrators inspect Tenant Settings, AI & Models, Governed Knowledge, Branding & Report Standards, and Guardrails & Generation. These remain local prototype settings, not production tenant controls. Reporting cases and their request versions are durable; the separate historical **My Runs** view remains browser-session-only evidence.

## Accepted product experience — planned

Guided and Advanced experiences will share this reasoning and assurance engine. The target starts with conversation and does not require a file or project. A user may describe a source in business language and may later provide qualified schema/data uploads, screenshots or report/sketch references. The UI must state what each item can establish: a design reference is not data truth, and an accepted assumption cannot prove a missing field, source fact or permission.

The target keeps material business decisions understandable and explicit while leaving ordinary supported BI design to AI. Supported alternatives must disclose retained intent, changed scope, assumptions, omissions, limitations and evidence needs; material rescoping requires acceptance before generation. “No dead ends” means a useful supported alternative or authorized-expert continuation, not guaranteed generation.

Later account UX still covers public company registration, authorized BI-expert takeover, optional projects, controlled collaboration, report/output histories, licensing/seat entitlement and usage visibility. APBRA-162 implements only invite-bound membership and private reporting cases. Company membership, a mode, licence or model key does not itself grant private-source, tenant-management, release or deployment authority.

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

Changing the request, parsed schema, governed context or interpretation invalidates earlier readiness. Late asynchronous results and duplicate actions cannot confirm or start generation for superseded meaning. A provider interruption preserves the current request, answers and accepted contract where one exists, and exposes a retry for the affected stage without resetting the configured clarification budget. `READY_FOR_CONFIRMATION` proves only that the displayed business meaning is eligible for acceptance; it does not guarantee later Report Design coverage, compilation, runtime compatibility or deployment.

## Run locally

Start the local API and PostgreSQL services as described in the repository README. Copy `.env.example` to ignored `.env.local`; `APBRA_API_URL` is a non-secret local proxy target. Existing optional Azure AI configuration remains server-side and is not required for case persistence tests. The browser never displays an API key.

```sh
npm ci
npm test
npm run build
npm run dev
```

Vite normally serves `http://127.0.0.1:5173/`. AI-dependent stages show an unavailable/error state if the configured endpoint cannot be reached.

### Isolated browser tests

Playwright never reuses the manual preview on ports 5173/8000. It starts a test-only web/API pair on ports 15173/18000 and requires a separate disposable PostgreSQL database. Each run downgrades and reapplies migrations only in that explicitly named browser-test database, so never point `APBRA_E2E_DATABASE_URL` at preview or backend-test data.

Create the isolated database once inside the committed Compose PostgreSQL service, supply a locally generated test-session value, then run the suite. These commands reuse the already-required local `APBRA_POSTGRES_PASSWORD` environment variable without printing it:

```sh
docker compose exec postgres createdb -U apbra apbra_e2e
export APBRA_E2E_DATABASE_URL="postgresql+psycopg://apbra:${APBRA_POSTGRES_PASSWORD}@127.0.0.1:54321/apbra_e2e"
export APBRA_E2E_SESSION_SECRET="$(openssl rand -hex 32)"
npm run test:e2e
```

Test traces are written outside the repository under `/tmp/apbra-162-playwright-output` by default. Set `APBRA_E2E_OUTPUT_DIR` to another disposable location when needed. These tests may reset only the isolated E2E database; they do not stop, reuse or alter the manual preview database.

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

Implemented locally does not mean production ready. Live Entra qualification, hosted multitenancy, durable knowledge ingestion/indexing, managed secrets, broad compatibility, publishing, reviewer workflow, resilience, monitoring and compliance operations remain future work.
