# APBRA Capstone — enterprise Power BI architecture prototype

This local React/Vite application separates tenant administration from a business report-creation workspace. Its active flow is:

`uploaded CSV/XLSX + requirement → GPT-4.1 interpretation → dynamic clarification → local semantic retrieval → grounded ReportDesign → deterministic policy → bounded PBIP compilation → deterministic candidate validation`

It does not select a canned scenario from prompt text. GPT-4.1 proposes typed advisory outputs; deterministic code owns policy, compilation, validation, and whether generation may start.

## Run locally

Copy `.env.example` to `.env.local` and provide the Azure AI configuration. `.env.local` is ignored. The Vite server holds the credential and exposes only bounded chat and embedding adapters; the browser never receives the API key. The endpoint can use Azure OpenAI's `/openai/v1` contract or an explicitly configured deployment/API-version contract. No API version is guessed.

```sh
npm install
npm test
npm run build
npm run dev
```

If Foundry is unavailable, AI-dependent stages fail visibly and remain incomplete. There is no deterministic response presented as AI output.

## Administration and workspace

The administration plane provides local prototype settings for organisation identity, AI/model status, governed knowledge, branding/report standards, and guardrail/generation thresholds. These settings are browser-local and are not a production tenant control plane.

The business workspace starts empty. A user uploads CSV or XLSX data, reviews the detected tables/columns/types/relationships, enters a requirement, answers questions generated for that input, confirms the requirements, and receives a grounded typed ReportDesign. Policy results and source validation precede candidate download. My Runs is browser-session history only.

## Governed local RAG

Five fictional policy documents under `knowledge/` form the controlled corpus. The index uses heading boundaries; sections beyond the target are split into roughly 500-token windows with about 50 tokens of overlap. Each chunk retains source, version, heading, stable chunk ID, character/token estimates, and citation. `text-embedding-3-small` embeds chunks and queries. A local in-memory exact cosine index returns top-k evidence for the design call.

Administrators can add or replace local Markdown documents and re-index during the browser session. This is a bounded prototype, not enterprise content lifecycle management.

## Bounded PBIP compiler

The compiler accepts the typed ReportDesign contract and detected data structure. It supports embedded CSV data, one or more imported tables, explicit measures using SUM, DISTINCTCOUNT, COUNT, AVERAGE or measure ratios, simple discovered relationships, multiple pages, KPI cards, bar/column/line charts, tables, slicers, and tenant theme colours. It does not execute model-authored DAX, M, SQL or shell content.

Unsupported features, unknown fields, unverified relationships, excessive complexity, missing accessibility metadata, absent grounding, or disabled generation are handled by typed deterministic policy. Human review is a terminal status in this prototype; no approval workflow exists.

Source validation checks project structure, table files, PBIR references and identifiers, visual count/types, unresolved values, measures, and relationships. It is not Power BI Desktop runtime evidence.

## Real Foundry evaluation

With the local server running, execute:

```sh
node scripts/foundry-smoke.mjs
```

The opt-in integration harness runs two materially different natural-language requirements and schemas through real interpretation, embedding retrieval, grounded design, policy, compilation and validation. It also sends an unrelated request through real interpretation and verifies that generation never starts. Secret-free evidence and candidate ZIPs are written under ignored `artifacts/local/`.

## Claim boundary

Implemented locally: CSV/XLSX ingestion, real Azure-hosted inference and embeddings, dynamic clarification, local semantic retrieval with citations, structured grounded design, deterministic guardrails, a bounded generic PBIP compiler, source validation, trace data, downloads, and browser-session run history.

Prototype/staged: tenant administration, fictional customer standards, in-memory index, API-key local adapter, inferred relationships, and PBIP candidates pending manual Desktop testing.

Not implemented: production hosting, persistent multi-tenancy, enterprise identity/RBAC, Azure AI Search, reviewer workflow, production Power BI publishing, arbitrary DAX/M execution, automated deployment, or dynamic handover-document generation.
