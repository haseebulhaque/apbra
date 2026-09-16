# Power BI generator and assurance boundary

Sources: ADR-020..029, Confluence 08.06 and 14.07 v1. APBRA-50 and APBRA-110 own actual compatibility evidence.

## First profile

One Import-mode model/report, PBIP packaging, enhanced PBIR report definitions and TMDL semantic model. Generate a bounded star schema, declared dates/keys/measures, standard visuals, theme and ordinary navigation from an exact validated DesignPlan. Safe synthetic CSV M templates use typed configuration. No live production connector, arbitrary M/SQL, DirectQuery/Direct Lake, custom visual or autonomous publishing.

The selected first-release ceilings are recorded by 14.07. They are not Power BI limits. Schema-only generation is distinct from a refresh-tested synthetic-data scenario.

## Capability lifecycle

A feature starts PLANNED. SUPPORTED requires a recorded exact Desktop build, schema/template versions, supported external-edit boundaries, generator path, validation coverage and real evidence. Never invent a Desktop build, schema URL, undocumented converter or headless Desktop command.

Linux static tests can parse definitions and resolve references. They do not prove Desktop openability, refresh, numeric DAX results, visual usability or RLS behavior. APBRA-111/112/113 require those distinct results; missing tooling is Not Run, never Not Applicable for a mandatory case.

## Candidate contract

Assembly is atomic. A manifest identifies relative paths, digests, generator/compatibility versions and exact plan/input/evidence identities. Safe filenames, bounded files and no symlinks/traversal are mandatory. Reparse stored bytes independently before validating. Any repair creates a new candidate and full required revalidation.

## Validation vocabulary

Finding severity: BLOCKER, ERROR, WARNING, INFO. Rule result: Pass, Warning, Fail, Not-Applicable. Execution state records completed/error/timed-out/not-run separately. Aggregate technical result: PASS, PASS_WITH_WARNINGS, BLOCKED, INCOMPLETE. Missing mandatory rules and zero-rule accidental passes are forbidden.

## Governance and handover

Business-user release requires an eligible reviewer decision for the exact candidate. A trusted-author route can bypass only the business-user approval gate, not technical validation. Current authorization and policy must be checked at release.

Required RLS logic that is missing/ambiguous blocks release. Known credential, gateway, target workspace, role-member and refresh setup can remain pending deployment actions in the package. A report slicer is not RLS. A role definition is not a deployed group assignment.

The pack contains the candidate, manifest, safe validation/governance evidence, one-page Quick Start, detailed guide and replacement mapping. A .pbip entry file is not a .pbix import. Customer changes produce different bytes and cannot inherit the old digest/approval.
