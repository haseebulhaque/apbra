# MVP requirement-to-delivery map

Source basis: Confluence Section 02, 14.07 v1 and the current Jira backlog. This is a scoped implementation index, not a full export of every Confluence requirement or a claim of complete test coverage.

| Requirement family | Required behavior | Jira ownership | Required evidence |
| --- | --- | --- | --- |
| FR-001..012; DATA-003 | Preserve original intent, structured draft, clarification and status | APBRA-13/31/34/102 | Contract, authorization, history and stale-confirmation tests |
| FR-020..025 | Declared schema; distinguish confirmed from inferred fields/relationships | APBRA-28/29/30 | JSON/CSV parser and malformed/limit fixtures |
| FR-030..035; AIR-003..005 | Versioned, grounded structured DesignPlan before files | APBRA-43/46/49 | Schema, reference, provenance and refusal tests |
| RAGR-020..028; RAGR-040..044 | Tenant-safe governed evidence and explicit precedence | APBRA-35/38/41/42 | Retrieval, conflict, citation and injection cases |
| PBI-GEN-001..011 | Versioned compatibility and supported generator subset | APBRA-50/51/54/57/58/107 | File, source loading and compatibility fixtures |
| FR-050..055; PBI-VAL-001..009 | Complete independent validation; no self-certification | APBRA-59/60/63/64/110 | Golden, adversarial, missing-rule and actual runtime evidence |
| FR-060..068; HITL-001..005 | Server-authoritative routing; trusted path never bypasses validation | APBRA-65/68/71/72 | Role, stale decision and both-route tests |
| FR-070..075; DATA-021 | Exact-candidate secure package and deployment guidance | APBRA-73/74/75/76 | Eligibility, archive/tamper, download and walkthrough evidence |
| SEC/IAM/TEN/AUD | Server-side identity, isolation, secret exclusion and accountability | APBRA-77..80/104/114 | Cross-tenant, crash-window, redaction and deletion tests |
| NFR-REL/PERF/OBS/COST | Durable work, limits, recovery and attributable usage | APBRA-81..84/99/117/119/122 | Failure injection, workload-labelled measurements and traces |
| NFR-MNT; Section 22 | Bounded engineering, reviewed changes and real provenance | APBRA-18/85..89/125..127 | Exact-revision code/check/review records |

Ranges denote source families, not invented requirement numbers. Read the source page to obtain individual requirements. All product evidence above remains planned until linked real results exist.

## First release scope

Guided form/text, the APBRA JSON schema, optional synthetic CSV and curated Markdown/text are selected for 0.1. Broad Excel, DDL, PBIX and external connector ingestion are later adapters. Both business and trusted-developer routes remain required. One sales scenario is the golden case; a ServiceNow funnel is not silently substituted.

## Reporting rules

Use Epic -> Story/Task/Bug -> Sub-task. MVP spans the release, not one enormous sprint. Parent and Sub-task effort is not additive. Documentation completion can finish a specification task, never its unimplemented product capability. No synthetic Bugs are created to populate a board.

## Source freshness

Before dispatch, compare live Jira and Confluence revisions with the source register and task inputs. Offline bootstrap validation checks internal consistency only; it cannot certify remote freshness or owner acceptance. Inaccessible or changed mandatory sources require a refreshed context package.
