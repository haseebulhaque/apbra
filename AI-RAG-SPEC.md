# AI and governed retrieval specification

This document describes the current in-app Capstone implementation and the accepted, separately unimplemented `APBRA-PRODUCT-2026-09-22` AI/knowledge target.

## Current AI profile

The adapter uses an Azure AI Foundry/Azure OpenAI-compatible endpoint. The configured chat deployment is GPT-4.1; live evidence observed `gpt-4.1-2025-04-14`. Embeddings use `text-embedding-3-small` with 1,536 dimensions. Secrets remain server-side in the ignored local environment configuration.

GPT is responsible for domain-neutral requirement interpretation, material-ambiguity detection, bounded iterative clarification, natural-language answer interpretation and grounded ReportDesign. Business Mode is default; Advanced/BI Mode accepts optional preferences. Human confirmation creates the authority boundary; deterministic code decides state validity, obligation preservation, references, measures, capability, guardrails, compiler validity and candidate validity.

Raw requests, questions and answers remain immutable provenance. Only confirmed structured meaning enters ConfirmedRequirementContract v2; deterministic downstream code does not reinterpret arbitrary prose. One bounded ReportDesign correction may receive exact findings, but cannot invent or alter confirmed measures and must pass complete revalidation.

## Capstone governed RAG

The governed corpus contains five substantive fictional APBRA policy documents covering corporate branding, semantic modelling, report design and visualisation, accessibility, and deployment/handover.

Chunking is heading-aware and token-aware. Meaningful sections are preserved; larger sections are split near a 400–600-token target with limited overlap only for continuity. Tiny sections are not padded. Each chunk retains document, version, heading, stable ID, size, content and citation metadata. The current corpus contains 20 chunks.

At runtime APBRA retrieves relevant context during clarification where useful and again for detailed ReportDesign. `text-embedding-3-small` embeds the query; exact in-memory cosine similarity returns configurable top-k chunks. Retrieval cannot authorize or silently override confirmed requirements; conflicts surface for clarification/review.

The uploaded CSV/XLSX schema is request context and is never indexed into tenant-wide governed knowledge. Workbook bytes, secrets, local paths and unrelated environment data are not retrieval content.

## Provenance and authority

Retrieved evidence retains source document, category, version, heading, chunk ID, similarity and latency. The model cannot activate a policy, authorize a user or approve generation. Retrieved text and model output are untrusted inputs to typed contracts and deterministic validation.

The canonical Sales run recorded citations `CB-001`, `PM-002`, `RD-004`, `RD-001`. Its `embeddingCalls` value is null; no embedding-call count or precise embedding cost is claimed.

## Historical Foundry boundary

The APBRA Capstone does **not** use the old S08 Foundry Knowledge store. APBRA documents were not uploaded to that historical source, and it is not evidence for the current governed corpus.

## Production knowledge gap

The Capstone corpus and exact in-memory index are bounded prototype choices. Production still requires tenant document upload, replacement and deletion; robust extraction; version and chunk lifecycle; stale-chunk cleanup; re-indexing; permissions; durable vector/index infrastructure; tenant isolation; monitoring; retention; and operational recovery. Any future lexical/hybrid retrieval, approximate index or external service requires separate evaluation and accepted architecture authority.

## Accepted target AI and knowledge model — planned

Guided and Advanced experiences will use the same reasoning/assurance engine. The target accepts conversation-first requirements, optional qualified uploads and plain-language source descriptions. Schema/data screenshots and report/sketch references are different evidence classes: AI may use them to identify uncertainty or inform design, but neither can silently establish missing source truth, measures, permissions or authority.

Tenant-governed terminology, KPI definitions, branding, accessibility and reporting standards should be reusable during clarification and ReportDesign. Explicit user meaning remains authoritative within policy; a conflict with mandatory tenant policy must be surfaced for acceptance or review. Durable production RAG requires tenant isolation, authorization-aware ingestion and retrieval, replacement/deletion, versioned citations, retention and evaluation. Demo fixtures remain classified separately and never become universal policy.

### Planned activation, permission and policy controls

These controls describe the accepted target and are **planned**, not capabilities already implemented by the bounded prototype:

- Knowledge becomes eligible for activation only after both required source approval and successful required ingestion/index verification. Approval alone is insufficient.
- Current company and private case/project/source permissions apply before retrieval eligibility, ranking and model context. They are rechecked before protected work is resumed; an earlier permitted retrieval does not grant continuing access.
- A citation must substantively support the associated claim using eligible, versioned evidence. Merely appearing in a retrieved result list is not sufficient support.
- Mandatory-policy coverage cannot depend only on similarity top-k. Failure to retrieve a mandatory policy is not permission to proceed without it.
- A compliant revised business approach requires explicit acceptance of its material meaning. User acceptance or BI-expert assignment cannot waive mandatory policy; unresolved policy authority is referred to the authorised policy owner.

The target supports qualified APBRA-managed and customer-managed model profiles, including approved private/local profiles where feasible. Each profile requires explicit provider/model/capability, data-handling, identity, quota, cost and failure-mode qualification. Separately consented customer Azure provisioning is a future management capability; a model inference key, company membership or UI mode grants no such authority.

Cross-cutting controls include prompt-injection and retrieval safety, structured-output evaluation, red teaming, traceability, reliability and cost visibility. No provider, model, region, routing rule, price, SLA or numerical limit is selected merely by documenting the target.

## Evaluation boundary

Retrieval quality, citation provenance, structured output, clarification quality and guardrail behaviour require real recorded executions. An LLM cannot be the sole oracle for arithmetic, authorization, compiler correctness or candidate validity. Historical evaluation evidence remains historical and must not be relabelled as current execution.

“No dead ends” requires useful supported alternatives or an actionable authorized-expert route. It never permits the AI to invent missing evidence, hide omissions, bypass explicit acceptance or recast a technical failure as a semantic success.
