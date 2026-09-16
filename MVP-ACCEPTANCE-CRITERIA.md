# Evidence-based acceptance

Sources: 02.06, 08.06, Section 21, 14.07 and APBRA-91/92/110. This is a minimum verification map, not a record of passing tests.

## Engineering bootstrap acceptance

B01: branch write and readback succeed without changing main.
B02: required docs, source references, agent cards and one bounded Task Contract exist.
B03: engineering schemas reject missing fields, unknown keys, invalid role/card references and excessive authority.
B04: scope tests reject traversal, restricted paths, empty verification and product files accidentally added under bootstrap-only checks.
B05: a real PR identifies actual actor, Jira scope and known control gaps; no self-approval.
B06: hosted CI results are reported for the exact revision or explicitly left pending/blocked.
B07: actual branch-protection availability is recorded separately from workflow/CODEOWNERS files.

Local and hosted evidence must identify their environment, commands, source manifest and failures. B02-B04 success does not finish APBRA-87's complete future CI implementation.

## Product release acceptance (not yet executed)

| Gate | Required positive result | Required negative result |
| --- | --- | --- |
| Intent/schema | Original input, declared schema, confirmed exact version | Stale confirmation, malformed/oversize schema, foreign object denied |
| Clarification | Material KPI/date/RLS questions, bounded rounds | Missing security/business definition stops generation |
| Grounding | Eligible source versions/citations and deterministic precedence | Poisoned content, foreign tenant, mandatory conflict blocked |
| DesignPlan | Full schema and semantic reference validity | Invented fields, unsupported features and malformed output rejected |
| Generation | Complete supported candidate and manifest | Partial/tampered/secret-containing files cannot progress |
| Validation | Every mandatory applicable check completed | Skipped, crashed or missing required check cannot pass |
| Runtime | Declared Desktop opens/refreshes; numeric and RLS oracles pass | Wrong KPI/filter context and unauthorized row visibility detected |
| Governance | Business-review and trusted-author cases both succeed correctly | Forged roles, self-review when prohibited and stale approvals denied |
| Release | Authorized exact package with usable handover | Pending deployment setup not confused with missing security logic |
| Operations | Bounded recovery/usage and safe telemetry | Retry storm, stale worker, queue saturation and leaks prevented |

No accuracy, cost saving, production SLA or completion percentage is invented. Release requires the declared mandatory executed coverage, not just zero recorded failures. Not Run remains visible. File-generation success is not deployment success.
