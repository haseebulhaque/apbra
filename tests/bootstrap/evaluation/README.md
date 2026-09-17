# APBRA-91 Capstone evaluation contract

Scope: offline harness, predeclared case registry, metric definitions and safe evidence export. Logical implementation role APBRA-AI (catalog 0.1), QA/domain review required. Human initiator Haseeb Ul Haque; actual actor Codex, exact model metadata unavailable. Base b22680c97b84aa86c78da11a4d4035f7b32af15b. Source APBRA-91 read 2026-09-17 and Section 21.04 v2. Paths limited to this directory and tests/bootstrap/test_evaluation.py. No application, model calls, Power BI execution or paid dependencies.

## Use and evidence boundary

`python tests/bootstrap/evaluation/harness.py --report artifacts/evaluation/<unique-run>.json`

This command exports an **unexecuted** baseline. It does not run the upcoming application. All real cases remain NOT_RUN and quality is TBD. It is not completion evidence for APBRA-91's dependent real-suite execution obligation. Harness self-tests use synthetic observations and never count toward product quality.

A future authorised adapter calls new_run then record for each observed attempt, preserving every returned snapshot. Export each run to a new filename: exclusive directory-relative no-follow writer rejects symlink traversal and overwrites. Reruns use previous_run_id; retries append attempt records, never replace failures. The registry is hashed/frozen at run creation. Store exported records as immutable engineering evidence; this local harness is not a cryptographically tamper-proof audit service.

Before execution review and version the inventory, applicability and rubric. Non-applicable cases require reasons and a new registry version/record. All current bounded cases are applicable, including runtime checks: missing runtime is BLOCKED/NOT_RUN, never a fabricated pass. Production Entra, Azure, tenant deployment, enterprise observability and multi-tenancy are outside this inventory.

sales-v1 is the development set, already available to implementation authors; it is **not held out**. held-out.json is a separate synthetic evaluation mutation reserved from tuning. It is not secret or a statistically representative test set. Record exposure and repartition/version if used for development. Individual APBRA-90 manifest hashes pin fixtures; preserve that manifest and exact Git revision with an evidence pack.

## Outcome accounting

Each applicable case has exactly one current outcome: PASSED, FAILED, ERRORED, NOT_RUN, BLOCKED or UNSUPPORTED. Planned = applicable + excluded; applicable = sum of current outcome counts. Executed includes pass/fail/error/intentional unsupported, not blocked/not-run. Provider errors/timeouts are ERRORED; malformed schema output is FAILED; no retry removes the first observation. Unsupported on a supported request must be FAILED. A correct safe refusal is PASSED with SAFE_REFUSAL terminal, never successful generation/release. UNSUPPORTED records an executed unsupported response without asserting the refusal rubric passed.

Executed pass rate = passed / executed, always shown with execution coverage = executed / applicable. The mandatory gate also requires a nonempty mandatory set and every applicable mandatory case PASSED. Zero executions yields null rate/observed-failures, NOT_RUN and TBD. Raw zero outcome counts describe an empty sample, not zero product defects. Advisory cases cannot supply a missing mandatory pass.

Per-metric rate uses its declared applicable subset; first-pass validation uses the first attempt, repair uses final outcome. Recall@K is intersection of unique expected IDs and ordered top-K returned IDs / unique expected IDs across all recorded retrieval attempts; duplicates cannot inflate recall. Citation integrity and precedence use explicit deterministic rubrics. Business runtime, authorisation and file-validity results cannot rely on an LLM-only assessor. Assessment methods are the explicit enum deterministic/human/llm_only. Governance, authorization, structured output, citations/precedence, generation/validation/repair, end-to-end and runtime truth reject LLM-only passes. Human-quality passes require method human and structured rubric_evidence with matching assessor identity, a numeric min/max scale and scores for all eight dimensions (intent, model, measures, pages, standards, accessibility, deployment, unsupported_assumptions). These are recorded assessor declarations; independent review verifies actual human provenance, which this offline harness cannot authenticate. Imported records revalidate run/version metadata and every attempt execution ID against its containing run.

APBRA-90 numeric.expectations.json is the independent business oracle: monetary absolute tolerance 0.005 AUD; AOV uses exact sales/orders fractions; YoY uses exact (current-prior)/prior fractions, compare with declared decimal tolerance 1e-9; missing prior year is unavailable, not zero. These are expected values, not DAX runtime results. Independent oracle review and actual runtime remain required.

## Measurements and lineage

Every executed record includes actual/expected (registry), assessor and method, rubric evidence for pass, safe repository-relative evidence references, elapsed milliseconds, execution ID, nullable candidate/review/release IDs, usage and cost or explicit unavailable reasons. Adapters must measure elapsed time with a monotonic clock; the harness never invents measurements. Missing provider versions remain null with a reason: model/deployment/profile, prompt/schema, embedding/index/source, generator/validator/compatibility.

Latency reports sample size, min/max/mean/population SD and nearest-rank p95 across all attempts including failures/retries. Cost retains every known attempt grouped by currency/rate version/kind/basis; unknown costs are counted separately, so known totals are partial when any are missing. Cost per successful release includes failed/retried effort and is null without a successful E2E release. Estimates are labelled, never invoices. Usage raw units remain in records; do not add unlike units or different currencies. No production accuracy/cost extrapolation from this small synthetic set.

Evidence paths permit tests/ and artifacts/ only; no external/signed URLs, raw provider response or credentials. Adapters are responsible for sanitizing actual/rubric text and linked content before public export. References do not prove artifact existence or runtime results; independent review verifies them. Summary exports derive solely from the raw inventory/attempts; no manually entered slide percentages.

## Verification

Existing engineering CI discovers tests/bootstrap/test_evaluation.py. Run CI policy, bootstrap, all bootstrap unittests and pip check. Linux-only secret scanner runs hosted, not on macOS. Fresh independent review on exact commit and passing hosted checks precede Haseeb's manual merge. Real suite execution remains pending APBRA-128 components; no APBRA-92/93/94 execution is claimed.

## APBRA-92 actual local execution (2026-09-17)

`execute-local.ts` bundles and invokes the actual merged app modules, not mocks. It reads the unchanged registry and fixture oracles indirectly through the importer. Run from repository root with the locked web dependencies installed:

```sh
node apps/web/node_modules/esbuild/bin/esbuild tests/bootstrap/evaluation/execute-local.ts --bundle --platform=node --format=cjs --loader:.csv=text --outfile=/tmp/apbra-evaluate.cjs
APBRA_SOURCE_REVISION=<verified-app-commit> node /tmp/apbra-evaluate.cjs /tmp/apbra-unique-new-run
python tests/bootstrap/evaluation/import-local.py /tmp/apbra-unique-new-run/observations.json tests/bootstrap/evaluation/evidence/<retained-run>/observations.json artifacts/evaluation/<unique-run>.json
```

Retain the observed source JSON at the exact referenced path before publishing the report. Each output directory/file must be new; original failures are not overwritten. The adapter’s successful process exit means observations were written, **not** that the mandatory product gate passed. Imported report summary owns that conclusion. Existing CI tests the evidence accounting and retained manifests; it does not silently reinterpret blocked product cases as successes.

Stored [run report](evidence/run-fcdff3d3/report.json) has 24 applicable mandatory cases, 21 executed, 20 passed, one failed and three blocked. Mandatory gate is false. Failure: held-out alternate date relationship receives general UNSUPPORTED rather than the targeted clarification demanded by its rubric. Blocked: no repair implementation, no actual Power BI numeric runtime, and no named human quality rubric. Safe escalation is real but does not satisfy the registry’s repair-success expectation. The held-out fixture was exposed only for this evaluation, not used to tune implementation; any future tuning requires honest repartition/new held-out evidence. No registry flags or expected outcomes changed.

The earlier adapter-calibration observations are retained separately. Two incorrect evaluator comparisons included fixture-only metadata in RequirementsSnapshot and rejected an extra eligible citation. Those were evaluator defects, fixed before the reported product run; the initial data and genuine held-out failure remain visible. They are not mixed into product accuracy/latency samples. An independent reviewer must validate this disposition.

Both routes invoke an explicitly isolated **SIMULATED** identity adapter. Source validation and module ZIP writes are real; they are not production authorization, TLS/secure-delivery assurance or actual human approval. Browser Downloads were separately read during APBRA-135/136 and the keyboard journey, with all40source bytes and manifest hashes verified. Numeric oracle values are not DAX measurements. Provider calls/tokens are zero; costs are unknown, not a fabricated zero-cost invoice. The mixed-case harness p95 describes heterogeneous evaluator invocations, **not** an API SLA or end-to-end user latency.

### APBRA-93 genuine failure

[failure.json](evidence/run-fcdff3d3/failure.json) records the predeclared APBRA-134 missing-date-relationship mutation, original and changed TMDL, different candidate hashes, deterministic findings and HUMAN_ESCALATION. Original candidate is retained separately. No repair claim: later submitting the preserved original is a resubmission, not repairing failed bytes. Actual browser failure and source profile checks are documented in PR9/11. [decline.json](evidence/run-fcdff3d3/decline.json) retains a separate simulated decline followed by a new pending revision; release was denied before resubmission.

### Applicable APBRA-122/123/124 disposition

[keyboard.json](evidence/run-fcdff3d3/keyboard.json) records a fresh actual native Chrome keyboard-only journey at the merged app revision, both routes, rejected blank reason, 61 observed focus transitions, save dialogs and physically verified downloads. All observed controls remained reachable. Disabled completed buttons expose HTML focus, with subsequent Tab continuing to adjacent controls; no blanket focus-management or assistive-technology certification is asserted. VoiceOver, actual Power BI report interactions and complete WCAG assessment remain NOT_RUN. Source labels/status text and non-colour state descriptions exist; a source inspection is not proof of spoken announcements.

[performance.json](evidence/run-fcdff3d3/performance.json) is generated by `measure-local.ts`: 20 sequential single-user local module flows, six-table fixed synthetic fixture, Apple M1 Pro/arm64/macOS Darwin25.6, Node24.19, no warmup; first invocation after module load identified, startup excluded. Every fifth validation intentionally fails, all20samples retained. Separate per-stage nearest-rank p50/p95 use actual monotonic durations. No API exists in this bounded architecture, so the non-AI API2s objective is N/A here; no production SLA claim. Model latency/provider saturation/429s, production sessions, tenant isolation, distributed queues and cloud restore are outside128’s local boundary and remain commercial backlog, not passed. Local cancellation is unsupported; input invalidation and stale/incomplete rejection are tested, refresh clears memory as disclosed, saved exports persist independently. Package metadata is inspectable; Desktop interaction/accessibility stays NOT_RUN.

APBRA-92 remains incomplete. APBRA-94’s measured final narrative and owner approval cannot claim CAPSTONE_READY while mandatory evaluation gates remain unresolved. This evidence increment may be reviewed/merged independently without marking92Done or weakening acceptance.
