# AI and governed retrieval specification

This document describes the current in-app Capstone implementation and the separate future production knowledge architecture.

## Current AI profile

The adapter uses an Azure AI Foundry/Azure OpenAI-compatible endpoint. The configured chat deployment is GPT-4.1; live evidence observed `gpt-4.1-2025-04-14`. Embeddings use `text-embedding-3-small` with 1,536 dimensions. Secrets remain server-side in the ignored local environment configuration.

GPT is responsible for requirement interpretation, ambiguity detection, dynamic clarification questions and grounded structured Report Design generation. It is advisory: deterministic code decides reference and measure correctness, compiler compatibility, guardrail outcomes, candidate validity and release eligibility.

## Capstone governed RAG

The governed corpus contains five substantive fictional APBRA policy documents covering corporate branding, semantic modelling, report design and visualisation, accessibility, and deployment/handover.

Chunking is heading-aware and token-aware. Meaningful sections are preserved; larger sections are split near a 400–600-token target with limited overlap only for continuity. Tiny sections are not padded. Each chunk retains document, version, heading, stable ID, size, content and citation metadata. The current corpus contains 20 chunks.

At runtime APBRA constructs an embedding query from the confirmed requirement, request-specific schema/model intent and clarification answers. `text-embedding-3-small` embeds the query. The browser application compares it with the governed corpus through exact in-memory cosine similarity and returns configurable top-k chunks. Those chunks and their citations ground the GPT-4.1 Report Design call.

The uploaded CSV/XLSX schema is request context and is never indexed into tenant-wide governed knowledge. Workbook bytes, secrets, local paths and unrelated environment data are not retrieval content.

## Provenance and authority

Retrieved evidence retains source document, category, version, heading, chunk ID, similarity and latency. The model cannot activate a policy, authorize a user or approve generation. Retrieved text and model output are untrusted inputs to typed contracts and deterministic validation.

The current happy-path run used two embedding calls, 20 indexed chunks, top-k 4, four citations and 454 ms retrieval latency. These are revision-specific observations, not permanent performance claims.

## Historical Foundry boundary

The APBRA Capstone does **not** use the old S08 Foundry Knowledge store. APBRA documents were not uploaded to that historical source, and it is not evidence for the current governed corpus.

## Production knowledge gap

The Capstone corpus and exact in-memory index are bounded prototype choices. Production still requires tenant document upload, replacement and deletion; robust extraction; version and chunk lifecycle; stale-chunk cleanup; re-indexing; permissions; durable vector/index infrastructure; tenant isolation; monitoring; retention; and operational recovery. Any future lexical/hybrid retrieval, approximate index or external service requires separate evaluation and accepted architecture authority.

## Evaluation boundary

Retrieval quality, citation provenance, structured output, clarification quality and guardrail behaviour require real recorded executions. An LLM cannot be the sole oracle for arithmetic, authorization, compiler correctness or candidate validity. Historical evaluation evidence remains historical and must not be relabelled as current execution.
