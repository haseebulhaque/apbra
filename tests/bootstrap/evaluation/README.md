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

Per-metric rate uses its declared applicable subset; first-pass validation uses the first attempt, repair uses final outcome. Recall@K is intersection of unique expected IDs and ordered top-K returned IDs / unique expected IDs across all recorded retrieval attempts; duplicates cannot inflate recall. Citation integrity and precedence use explicit deterministic rubrics. Business runtime, authorisation and file-validity results cannot rely on an LLM-only assessor. Named human rubric assessments must identify evaluator/scale in rubric_evidence; never label an LLM-only result human evaluation.

APBRA-90 numeric.expectations.json is the independent business oracle: monetary absolute tolerance 0.005 AUD; AOV uses exact sales/orders fractions; YoY uses exact (current-prior)/prior fractions, compare with declared decimal tolerance 1e-9; missing prior year is unavailable, not zero. These are expected values, not DAX runtime results. Independent oracle review and actual runtime remain required.

## Measurements and lineage

Every executed record includes actual/expected (registry), assessor and method, rubric evidence for pass, safe repository-relative evidence references, elapsed milliseconds, execution ID, nullable candidate/review/release IDs, usage and cost or explicit unavailable reasons. Adapters must measure elapsed time with a monotonic clock; the harness never invents measurements. Missing provider versions remain null with a reason: model/deployment/profile, prompt/schema, embedding/index/source, generator/validator/compatibility.

Latency reports sample size, min/max/mean/population SD and nearest-rank p95 across all attempts including failures/retries. Cost retains every known attempt grouped by currency/rate version/kind/basis; unknown costs are counted separately, so known totals are partial when any are missing. Cost per successful release includes failed/retried effort and is null without a successful E2E release. Estimates are labelled, never invoices. Usage raw units remain in records; do not add unlike units or different currencies. No production accuracy/cost extrapolation from this small synthetic set.

Evidence paths permit tests/ and artifacts/ only; no external/signed URLs, raw provider response or credentials. Adapters are responsible for sanitizing actual/rubric text and linked content before public export. References do not prove artifact existence or runtime results; independent review verifies them. Summary exports derive solely from the raw inventory/attempts; no manually entered slide percentages.

## Verification

Existing engineering CI discovers tests/bootstrap/test_evaluation.py. Run CI policy, bootstrap, all bootstrap unittests and pip check. Linux-only secret scanner runs hosted, not on macOS. Fresh independent review on exact commit and passing hosted checks precede Haseeb's manual merge. Real suite execution remains pending APBRA-128 components; no APBRA-92/93/94 execution is claimed.
