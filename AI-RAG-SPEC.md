# AI and governed retrieval implementation view

Sources: ADR-001..019, 07.04, 14.07 v1. Product implementation remains planned.

## Authority boundary

Clarification, plan synthesis and bounded repair can use model reasoning. Authentication, tenant selection, policy precedence, workflow transitions, required validation and release eligibility are deterministic application responsibilities. LangGraph subgraphs are invocation-local; PostgreSQL is the durable business system of record. Human waiting uses persisted state, not a live worker.

## Evidence eligibility before ranking

Select active approved product sources and authorized customer sources using server-side tenant/ACL/effective-version constraints. Only eligible chunks enter lexical and exact cosine ranking. The selected small-corpus profile combines ranked candidates through RRF with k=60. It does not deploy an external learned reranker or approximate index.

Precedence: hard security/platform controls; confirmed facts/schema; active mandatory customer policy; active customer preferences/reference standards; product guidance; permitted model prior knowledge. This is typed applicability, not a rule allowing user facts to authorize policy violations. Same-authority incompatible mandatory policies block. Missing mandatory evidence cannot silently fall back to model memory or web browsing.

## Contracts and limits

Model inputs reference exact RequirementVersion, DataSchemaVersion and eligible evidence. Typed outputs must satisfy full application schema and semantic checks, even where the provider supports only a projection of JSON Schema. Reject refusal/truncation/invalid references; persist provenance, not hidden reasoning.

14.07 selects three clarification rounds, five questions/round, two repairs, bounded HTTP attempts, input/completion budgets and aggregate spending. These are proposed application policies, not measured provider capabilities. Do not implement scattered numerical defaults or reset usage by creating another worker delivery. Missing rate/permission/processing evidence blocks live inference. No keys are needed for bootstrap checks.

## Provider profile

Azure OpenAI is the first adapter; gpt-5-mini and text-embedding-3-small are candidate selections from 05.07, not evaluated deployments. No automatic provider/model/region fallback. Actual quota, version, structured-output support and data handling require APBRA-97/115 integration evidence. Australia East application hosting does not imply Australian model processing.

## Evaluation

APBRA-42/91 require held-out cases, citation integrity, correct refusal, adversarial content and honest planned/executed denominators. An LLM judge cannot be the sole arithmetic, authorization or file-validity oracle. RAG source activation and tool permission remain outside model discretion.
