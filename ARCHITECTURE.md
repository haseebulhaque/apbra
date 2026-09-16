# Implementation architecture map

Source: Confluence 14.01, 14.07 and ADR-041/042/043/044/050/051/054. This is the APBRA-18 bootstrap mapping, subject to review; no application module is claimed implemented.

## Responsibility split

The product is a modular monolith with an asynchronous worker, not a service per agent. UI and API use application commands; application logic calls domain contracts and ports; infrastructure implements those ports. LangGraph reasoning is a bounded adapter inside durable stages, not the owner of human waiting states or release decisions.

| Reserved path | Responsibility | Boundary |
| --- | --- | --- |
| `apps/web/` | React requester/reviewer interface | Uses APIs; no database, provider keys or client role authority |
| `apps/api/` | FastAPI transport and composition | Validates transport, invokes application commands |
| `workers/` | Durable job dispatch/composition | Receives IDs, uses application commands, fencing and budgets |
| `packages/domain/` | Entities, value objects, invariants | Standard library and pure contracts only |
| `packages/application/` | Use cases, ports, lifecycle coordination | Domain/contracts; no concrete provider SDK |
| `packages/infrastructure/` | Database, identity, object-store and provider adapters | Implements ports; no reverse domain dependency |
| `packages/ai/` | Bounded model/graph adapters | Structured results only, no approval authority |
| `packages/rag/` | Eligible evidence, ranking and citations | Mandatory tenant/ACL filters and policy resolution |
| `packages/powerbi/` | Deterministic supported-format generators | Consumes an exact validated DesignPlan |
| `packages/validation/` | Independent byte-level validation | Never trusts generator success flags |
| `packages/governance/` | Deterministic review/release policy | Exact candidate, identity and policy versions |
| `contracts/` | Versioned machine contracts | No duplicate independent schema definitions |
| `infrastructure/` | Reviewed IaC and environments | No provisioning in bootstrap |

The reserved paths are not dummy application packages. Create them under their implementation tasks. This branch creates real engineering scripts, schemas and documentation only.

## Contract boundaries

RequirementVersion references the original submission, confirmed RequirementSpec and DataSchemaVersion. DesignPlanVersion references exact input and governed evidence versions. GenerationAttempt produces a new immutable Candidate and manifest. ValidationRun independently inspects candidate bytes. GovernanceDecision binds to candidate digest and actor/policy. Release packages those exact bytes plus safe evidence and handover.

A repaired candidate is a new identity; historical validation and approval cannot authorize different bytes. Download authorization is evaluated separately from generation. Target connection/gateway/RLS membership configuration is not performed merely by packaging instructions.

## Dependency and security checks

APBRA-20 will implement Python import-boundary checks when packages exist. The bootstrap checker intentionally rejects executable application files outside its narrow scope rather than pretending empty directories pass architecture tests. Later application changes must add real domain/contract/integration gates in a reviewed pipeline change.

Database tenant constraints, row-security policy, actor validation, object authorization, outbox consistency and idempotent job processing are APBRA-77/78/104/99 work. A lint check or JSON Schema cannot prove these runtime properties.

## Runtime separation

Local synthetic development: Linux-compatible Python/API/worker plus PostgreSQL and Azurite. Hosted demo: separately approved Azure resources and Entra identity. Windows Power BI Desktop provides actual open/refresh/DAX/RLS verification; Linux file tests are not a substitute. Do not introduce a fictional headless Desktop converter.

## Change rule

Changing a boundary, selected platform or security responsibility requires the applicable Jira change/ADR and updated tests. Narrow task scope cannot silently waive inherited invariants. Keep implementation-specific paths in reviewed contracts, with source version references in `docs/source-register.json`.
