# APBRA-90 synthetic sales fixture v1.0.0

This pack freezes Capstone inputs and expected semantics, not generated application output.
All rows and corporate rules are fictional. No customer files, personal names, addresses,
credentials, external services or random/time-dependent generation are used.

## Task boundary and provenance

Jira APBRA-90; implementation authority: Haseeb's explicit APBRA-90 instruction.
Execution APBRA90-20260917-fixtures; logical role APBRA-PBI card 0.1; actual actor
Codex, authenticated GitHub principal haseebulhaque. Base:
ffd4aca613debf5a6504afc59cc98187b0cbe9ff.
Branch: agent/APBRA-PBI/APBRA-90-golden-fixtures.
Allowed: this directory and tests/bootstrap/test_sales_fixtures.py.
Restricted: application/packages/workers, CI controls, dependencies, APBRA-129+.
Shared policy and AGENTS.md apply. Fresh APBRA-QA/PBI/AI review remains required.
No independent review or owner merge approval is asserted.

Sources read on 2026-09-17: Jira APBRA-90 (updated 2026-09-16 11:27:59 +1000),
APBRA-128 (2026-09-16 23:38:35 +1000), APBRA-92 and APBRA-110.
Confluence 21.01 (4064008), 21.02 (4064028), 21.04 (4031167), all version 2.
These references establish scope; private source bodies are not exported here.
APBRA-128 owns later executable integration; APBRA-91/92/110 own evaluation/runtime
evidence. This fixture task neither starts those items nor inherits production scope.

## Consumption

- schema.json defines CSV columns, types, keys, relationships, currency and null policy.
- schema.sql is SQLite-compatible fixture DDL, not an application database migration.
- Six UTF-8 CSVs have LF newlines, stable row order and header names matching metadata.
- request.json preserves the original request and three expected clarification answers.
- requirements.expected.json is the expected confirmed intent, not actual user confirmation.
- standards.json exposes versioned, stable citation IDs for later curated retrieval.
- design.expected.json lists semantic assertions, not exact AI wording or production API types.
- cases.json defines input variations and expected safe outcomes; all executions are Not Run.
- numeric.expectations.json provides independent hand-calculated fixture sanity totals.
- manifest.json hashes all other fixture files. Any intentional fixture edit requires a new
  version and refreshed hashes; consumers must record the version/hash they actually use.

## Frozen decisions

The dataset is a deliberately sparse but complete synthetic ledger for 2024 and 2025;
days without rows mean no sales, not missing data. DimDate includes every day, including
2024-02-29. Order IDs repeat across line items, so Orders must be distinct count.
DiscountAmount and CostAmount are line totals; SalesAmount = Quantity * UnitPrice -
DiscountAmount. Money is AUD with two decimal places. Baseline has no null values.
Golden answers choose net SalesAmount, full-year 2025 versus 2024, Region slicer only.
The default comparison is 2025; the dataset's first year has no supplied prior year.
Unavailable prior coverage and zero denominators yield blank, never invented growth.
No RLS role is supplied or claimed. The negative cases are recipes, not measured failures.

## Verification and limits

Run: .venv/bin/python -m unittest discover -s tests/bootstrap -v
The existing discovery includes fixture tests; no dependency or CI changes are needed.
Checks cover hashes, CSV/DDL/metadata integrity, referential/monetary consistency,
calendar coverage, distinct-order totals, semantic bindings, citations and corrupt inputs.
No web application, retrieval adapter, AI generator, evaluator or Power BI project is built.
A valid generated candidate cannot exist until the generator is implemented; its explicit
NOT_AVAILABLE status must not be converted into passing runtime or end-to-end evidence.
