# APBRA Capstone web demo

This local React/Vite application demonstrates a real, bounded AI architecture for the synthetic Sales Performance scenario:

`requirement + schema → GPT-4.1 interpretation → dynamic clarification → confirmed snapshot → text-embedding-3-small retrieval → grounded GPT-4.1 DesignPlan → deterministic guardrails/generation/validation`

## Local configuration

Copy `.env.example` to `.env.local` and fill the Azure AI values. `.env.local` is ignored by Git. The Vite server reads the API key and proxies only the bounded chat and embedding routes; browser JavaScript never receives the key. The configured endpoint may use the Azure OpenAI `/openai/v1` contract or the deployment/API-version contract. No version is guessed: non-v1 endpoints require `AZURE_AI_API_VERSION`.

```sh
npm test
npm run build
npm run dev
```

If Foundry is unavailable, AI-dependent stages show `AI SERVICE UNAVAILABLE` and remain incomplete. There is no fixture fallback presented as AI output.

## Dynamic workflow

GPT-4.1 interprets the current request and schema and returns typed objective, KPI, dimension, filter, page, assumption, and clarification fields. Clarification controls are rendered from that response. APBRA-90 remains the default prompt and offers explicit convenience answers, but its old three questions are not rendered as the normal workflow.

The real AI DesignPlan is a structured advisory artefact. The unchanged, manually Desktop-verified PBIP compiler remains intentionally bound to the exact APBRA-90 sample decisions; arbitrary AI plans are not silently converted to executable DAX, M, or Power BI metadata.

## Governed local RAG

The fictional corpus is stored under `knowledge/` as five Markdown documents. `rag.ts` loads each document and creates one chunk per level-two policy heading. The current corpus has 10 chunks. This heading-aware strategy is more appropriate than arbitrary 400–600-token windows because each short section is one complete policy topic. It uses zero overlap to avoid duplicated rules in ranking and records source, version, heading, stable chunk ID, token estimate, and citation.

`text-embedding-3-small` embeds the chunks and query. The application retains vectors only in an in-memory exact-vector index and ranks by cosine similarity. It supplies the top four chunks, including their citations, to the grounded DesignPlan call. No raw vectors are displayed or persisted. The evaluation set contains seven branding, KPI, date, accessibility, visual, security, and handover queries and measures Hit@3.

Run the real smoke/evaluation against a running local server:

```sh
node scripts/foundry-smoke.mjs
```

Secret-free evidence is written under ignored `artifacts/local/`.

## Authority and claim boundary

The LLM proposes typed interpretation and design outputs. Deterministic code retains guardrail, schema validation, candidate validation, governance, and release authority. The 250-visual request remains `HUMAN REVIEW REQUIRED / BLOCKED_NOT_RUN`; the marketing request remains `OUT OF SCOPE`.

Implemented here: real Azure-hosted inference and embeddings, dynamic clarification, local semantic retrieval with citations, structured grounded design, deterministic policy, and the bounded Power BI sample path.

Prototype: fictional customer corpus, local Vite adapter, in-memory exact-vector index, and the Sales Performance compiler.

Not implemented: production hosting, Azure AI Search, production identity or multi-tenancy, tenant publishing, reviewer workflow, arbitrary AI-to-PBIP compilation, automated deployment, or dynamic handover-document generation.
