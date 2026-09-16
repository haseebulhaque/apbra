# APBRA-27: first local application build contract

Prepared on 16 September 2026 from the actual APBRA-27 Jira task, the repository architecture and APBRA-IMPL-0.1. This is a bounded implementation specification, not built software or an issued Codex execution. The companion tasks/APBRA-27-build.json is deliberately NEEDS_REFINEMENT until its pre-dispatch bindings are refreshed.

## Outcome

A fresh checkout can install a reproducible local Python API, validate configuration, expose distinct liveness/readiness endpoints, return safe errors/correlation IDs and execute positive/negative tests without production credentials or a live model. This is not the reporting application, a hosted service or a completed tenant-security boundary.

## Preconditions and dispatch

1. PR 1 must receive a fresh review-only AI execution; fixes must be re-reviewed on the final head. Haseeb alone makes the manual merge decision.
2. Read current main after that merge. Replace the draft task's planning base with the actual merged commit; record real execution ID, author identity, source/card versions and the accepted local task scope. Do not use main's original README-only commit as a ready application base.
3. Refresh APBRA-27 and the APBRA-96 decision dependency. Resolve the product source records still marked Proposed before calling the task READY_FOR_IMPLEMENTATION. Public/solo governance acceptance alone does not approve every unverified implementation choice.
4. Check that the selected Codex mode is covered by existing access/quota. Do not buy credits, switch to a billable API key or add a paid Action. Standard public Ubuntu CI remains the verification path.
5. The current checker deliberately only authorizes engineering-bootstrap paths and reads APBRA-85's task. Before adding app files, propose the explicit APBRA-27 task/scope selection and accompanying regression tests. Never widen the bootstrap task to all paths or delete the gate.

## Exact boundaries

Allowed future changes: root Python packaging/lock files, apps/api/apbra_api/**, focused tests under tests/api/** and tests/config/**, docs/engineering/local-development.md, tasks/APBRA-27-build.json, and reviewed extensions to the existing bootstrap workflow/checker/tests. README may link actual verified commands. A .env.example may contain placeholders only; no actual .env file is permitted.

Denied: apps/web/**, packages/powerbi/**, packages/rag/**, live model adapters, workers with business job processing, infrastructure provisioning, product database migrations, role/tenant administration, ruleset changes, merge automation, real data or credentials. The reserved future packages in ARCHITECTURE.md are not a request to scaffold every component.

## Work package A: packaging and dependency evidence

Use Python 3.13 and the selected FastAPI/Pydantic family. One root pyproject.toml installs the apbra_api package from apps/api; avoid premature multi-package workspaces. Select a compatible PEP 517 build backend and record it, then resolve exact dependencies with uv and commit uv.lock. Pin the uv tool version used by CI. Include only API/configuration/probe/test dependencies needed for this task, not all future AI/frontend services. Version-family differences from the current implementation source require an explicit decision, not silently changing to whatever installs.

Record package licenses, verified package versions, platform compatibility and failed resolution attempts. No moving latest actions or containers. Prove a clean locked install and a second --locked run that leaves the lock unchanged. A network failure is BLOCKED, not a reason to hand-write a fabricated lock. Public CI can resolve packages; the current assistant sandbox's lack of DNS is not evidence of compatibility failure. Cross-platform local commands must state which platform was actually tested.

## Work package B: configuration

Create a typed, injectable Settings boundary in apps/api/apbra_api/config.py. Read only explicitly supported APBRA_ variables. For this task permit local and test profiles only; hosted/production profiles and enabling live AI must fail closed. Default bind is 127.0.0.1, port 8000; reject non-loopback exposure in local mode. Use explicit boolean parsing, validate numeric ranges and reject unknown APBRA_ names while ignoring unrelated OS variables.

Define required local PostgreSQL/Azurite connection configuration and validate shape at startup. Actual values stay in an ignored local file or process environment, never a prompt or committed example. Provide field-name-only startup diagnostics and avoid dumping Settings, credentials, DSNs or validation input values. Test fixtures may inject deterministic dependency probes only under the labelled test profile.

Absence of mandatory configuration must fail startup. Configuration validity is distinct from dependency availability: correctly configured but unreachable dependencies can leave the process live and readiness false. No startup schema creation, database auto-migration or automatic repair of user infrastructure. APBRA-104 owns business persistence/migrations; document that separation.

## Work package C: API and health

Use an application factory, not module-import-time network calls. Expose only GET /health/live and GET /health/ready plus deliberately controlled API metadata required for testing. No report, login or dummy AI business endpoints in this task.

Liveness returns HTTP 200 once the process can answer requests; it must not ping databases or providers. Readiness verifies only this bootstrap's required local dependency checks, with each check bounded to two seconds and the complete readiness operation bounded to three seconds. These are task-specific initial timeouts, not measured production SLOs. Use concurrent/cancellable checks or another design that demonstrably meets the total bound; no unbounded retries, model requests, writes or schema migration inside a health probe.

For local mode, implement actual PostgreSQL connectivity (read-only SELECT 1) and an authenticated read-only Azurite probe through replaceable interfaces. Success returns 200; required dependency failure/timeout returns 503 with a stable safe error code. Include readiness_scope=bootstrap_dependencies so no client infers the whole product is ready. Return logical dependency names/status only, no hosts, secrets or stack traces. No readiness success solely because a configuration string exists.

## Work package D: safe errors and correlation

Generate a server-side opaque correlation ID per request, return it in X-Correlation-ID, and include it in safe structured log/error metadata. Do not trust a client ID as actor, tenant or authorization. Accepting an optional incoming identifier requires a strict documented format and length; generating a fresh ID is the simplest approved option. Reject or replace malformed/control-character input without echoing it.

Return a versioned snake_case JSON envelope for 404, method/validation errors and unhandled exceptions: error.code, error.message, error.correlation_id. Preserve correct HTTP status codes and use generic public messages. Do not return raw exception strings or automatically log request bodies, Authorization headers, cookies or settings. Redaction tests inject synthetic secret-like values and prove they are absent from output/log captures. Hidden reasoning and raw private transcripts are never logged.

## Work package E: tests and CI transition

Provide deterministic tests for startup, configuration and the endpoint contracts using injected probes, plus a separate real local-dependency integration lane. Test doubles must not be counted as PostgreSQL/Azurite execution. Choose only free compatible services/tooling for the integration lane; no requirement to buy Docker Desktop or assume a Codex environment can run a Docker daemon. A missing local dependency should produce an explicit test limitation or use the supported hosted CI lane, not a fake pass.

Preserve the native required check name APBRA Bootstrap Checks until an approved setting change. Extend its policy and task selection to allow only the APBRA-27 paths, with denial tests for unrelated frontend/Power BI/IaC files. Preserve scanner, fail-closed errors, no secret context, no error suppression and exact action pins. Retain the original schema/hygiene tests; update their expected scope only through the explicitly approved task transition. Do not make a missing test an optional check just to obtain green CI.

## Acceptance cases

| ID | Expected evidence |
| --- | --- |
| B27-01 | Clean checkout resolves/installs under an exact lock; repeat locked install produces no lock diff. |
| B27-02 | Missing/invalid/unknown APBRA_ configuration fails clearly without revealing supplied values. |
| B27-03 | Local bind remains loopback; unsupported production/live-AI mode is rejected. |
| B27-04 | Liveness is 200 even when an injected dependency fails; no external probe is called by liveness. |
| B27-05 | Readiness is 200 only when all required probes pass, 503 on failure/timeout, within its total bound. |
| B27-06 | A real PostgreSQL/Azurite run is recorded separately from labelled test-double results. |
| B27-07 | Safe 404/405/422/500 envelopes and valid correlation IDs; synthetic credential values absent from bodies/logs. |
| B27-08 | No database migration/model/cloud/provisioning side effect on import, startup or health calls. |
| B27-09 | Retained CI gates fail for omitted tests, ignored exit codes, unauthorized paths or a missing scan. |
| B27-10 | README/local-development commands match the implemented package and actual evidence. |

## Completion and handover

Return the exact head/base, changed paths, lock/tool versions, commands, individual acceptance evidence, NOT RUN cases, reviewed findings and any required permission/cost decision. Keep the build in its own branch agent/APBRA-DEVOPS/APBRA-27-local-bootstrap. A separate AI review and Haseeb's manual merge follow. Do not mark the parent Epic, authentication, persistence, RAG or Power BI items Done from this local bootstrap.

This preparation does not start the future sprint, invent story points or claim code execution in Codex.
