# APBRA implementation and product baseline

This file distinguishes three different authorities that must not be collapsed into one claim.

| Layer | Authority | Meaning |
| --- | --- | --- |
| Current product intent | `APBRA-PRODUCT-2026-09-22`, Confluence 01.01 v4, 02.01 v4 and 02.06 v6 | Accepted direction for post-Capstone product planning; not proof of implementation |
| Verified implementation | GitHub main plus revision-bound tests and evidence | The working bounded React/Vite MVP/prototype delivered through APBRA-145 |
| Historical architecture proposal | `APBRA-IMPL-0.1`, [05.07 v1](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/4653067) and [14.07 v1](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/4751362) | Proposed production architecture retained for traceability; not the current stack or an implementation mandate |

## Current verified implementation

The current application is a browser-based React/TypeScript/Vite prototype. It uses an Azure AI Foundry/Azure OpenAI-compatible GPT-4.1 adapter, `text-embedding-3-small`, in-app governed retrieval, ConfirmedRequirementContract v2, deterministic ReportDesign assurance, and a bounded PBIP/PBIR compiler. Exact capability and evidence boundaries live in [ARCHITECTURE.md](../../ARCHITECTURE.md), [POWERBI-GENERATION-SPEC.md](../../POWERBI-GENERATION-SPEC.md) and [the Capstone evidence record](../engineering/capstone-evidence.md).

This verified implementation is not evidence for PostgreSQL/pgvector, FastAPI, LangGraph, production multitenancy, production identity, durable orchestration, publishing, gateway management or autonomous deployment. Those capabilities remain proposed, planned or unselected unless a later accepted task proves otherwise.

## Accepted product direction

The post-Capstone target is a generic SaaS-based AI-powered Power BI report-generation product. Guided and Advanced experiences share one engine. AI reasons about business ambiguity and ordinary supported BI design; people accept material business meaning; the typed contract freezes that meaning; deterministic software enforces authority, capability, semantic preservation, compilation and candidate validity.

The eighteen `PC26-FR` requirements cover conversation-first intake, qualified multimodal evidence, transparent alternatives and assumptions, explicit rescoping acceptance, expert continuation, company identity and membership, projects and history, licensing/usage visibility, tenant standards, qualified model profiles, separately consented Azure provisioning, connected Power BI delivery, optional data-architecture advice, cross-cutting assurance and truthful recovery. Their exact definitions and Jira mappings are summarized in [REQUIREMENTS.md](../../REQUIREMENTS.md); Confluence remains authoritative.

No target requirement selects a delivery milestone, replacement stack, provider, region, price, SLA or numerical limit by implication. APBRA-147 remains on planning hold. APBRA-149 through APBRA-158 are planning items, not implemented-feature evidence.

## Historical APBRA-IMPL-0.1 proposal

The historical proposal recorded these candidate refinements:

| ADR | Proposed refinement | Evidence still required before adoption |
| --- | --- | --- |
| 055 | Python/FastAPI/Pydantic with React/TypeScript/Vite | Accepted delivery task, lockfiles and builds |
| 056 | PostgreSQL/pgvector with eligible lexical/vector fusion | Isolation, retrieval and pool-reuse evidence |
| 057 | Persisted jobs/outbox/leases with bounded orchestration | Recovery, fencing, idempotency and budget evidence |
| 058 | Azure OpenAI first and synthetic-data profiles | Deployment, quota, processing, identity and spend authority |
| 059 | Narrow Import PBIP/PBIR/TMDL output | Exact schema, Desktop and runtime evidence |
| 060 | Task-bound engineering provenance | Trusted CI, branch controls and review evidence |

These proposals do not override the current repository or the newer accepted product requirements. Original ADR-001–054 remain historical source material. A candidate version or service named in prose is not an installed, entitled or verified dependency.

## Decision gates

Future implementation must still establish scope and architecture acceptance, dependency/provider entitlement, identity and repository-control feasibility, Power BI compatibility, implementation tests/review, and claim-to-evidence reconciliation. Documentation may describe a target; it may not promote that target to Implemented, Tested, Verified or Production Ready.

No production deployment, paid upgrade, customer-data processing, private-resource access or external management authority is granted by this baseline.
