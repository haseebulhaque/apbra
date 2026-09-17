# APBRA-129/130 local requester and requirements snapshot

This React/TypeScript/Vite shell is the first browser surface for the ELVTR Capstone. It consumes the frozen APBRA-90 request/schema directly, displays the three expected clarification topics and keeps edited answers only in browser memory. Refresh discards them. No private or production data should be entered.

## Run locally

Use Node 22.12+ (verified locally with Node 24.19.0), then from this directory:

```sh
npm ci --ignore-scripts
npm test
npm run build
npm run dev
```

Open the printed loopback URL. No global installation, cloud account, API keys or backend is required. Vite is a local development server; do not expose it publicly. Build output is ignored under dist. package-lock.json records exact transitive versions and integrity hashes; install scripts are disabled.

## Honest boundary

The browser supports request entry, frozen synthetic schema selection/inspection, manual clarification inputs and draft preparation. APBRA-130 adds a typed local RequirementsSnapshot after explicit confirmation of the unchanged golden request and all three exact synthetic answers. It preserves copied original inputs, exposes JSON for inspection/replay, and invalidates the snapshot on edits. Unsupported text, RLS requirements or schema/coverage changes fail explicitly. This deterministic fixture adapter makes no provider call or AI inference claim. It does not run integrated knowledge retrieval, generate/validate Power BI, authorize release, or record actual end-to-end evaluation. Those later stages remain NOT_RUN and package download is disabled. Expected fixture answers are explicitly labelled, not presented as AI output. These UI drafts are not authorization or durable evidence.

APBRA-133 through APBRA-136 will integrate real domain/backend behaviour; full APBRA-129 golden-scenario acceptance requires that integration and is pending. No broad APBRA-27 backend or APBRA-133+ item is implemented here. Power BI Desktop, DAX and RLS runtime are NOT_RUN.

## Sources and engineering boundary

Jira APBRA-129/128 and Confluence21.03v2 were read live on2026-09-17. User-authorized Capstone scope admits these exact web paths through a validated APBRA-129 task extension; existing bootstrap and secret controls remain mandatory. The broader proposed product source statuses remain unchanged. Source acceptance checks positively require ACCEPTED or BASELINED for implementation tasks.

React and Vite are MIT-licensed; TypeScript is Apache-2.0. Local tools do not require a paid plan. No purchase, cloud or model service is introduced. Official references: https://vite.dev/guide/ and https://react.dev/versions. Repository license selection remains the owner’s separate decision.

## APBRA-131 curated evidence preview

The independent preview reads all eight rules directly from the frozen APBRA-90 corporate standards fixture. The deterministic adapter accepts only `sales-v1`, returns source path, pack/version, authority and per-rule citations, and accepts no external documents or prompt instructions. Mandatory customer rules outrank generic recommendations subject to security/platform controls and confirmed facts; evidence grants no authorization. No general precedence resolver is implemented. APBRA-132 consumes the exact supported evidence in its DesignPlan.

`verifyCuratedCitations` checks canonical citation membership and mandatory coverage against this fixed catalog. It does not validate consumer source versions or consumed DesignPlan integrity. The adapter records K=8, result count and ordered evidence IDs; no retrieval quality metric is claimed. Unit evaluation verifies provenance against the fixture and golden design assertion IDs, plus missing/forged citations and unsupported scenarios. This is adapter evidence, not a completed DesignPlan evaluation. APBRA-132 binds this evidence into its plan; APBRA-136 will connect the complete flow. The integrated Knowledge and subsequent workflow stages remain not run; no commercial RAG, model, vector service, cloud or production tenant boundary is introduced.

## APBRA-132 DesignPlan

After confirming requirements, choose Create DesignPlan. The deterministic golden-scenario planner consumes a revalidated snapshot and exact curated evidence, with copied source bytes and all citations. It emits tables/relationships, six DAX measure declarations, page/visual/filter intent, theme and explicit no-RLS intent. The strict versioned runtime contract rejects missing/extra fields, altered semantics and stale source bindings; expected-result fixtures are used only by tests. This is not LLM interpretation or DAX runtime validation.

Inspect the plan or Save DesignPlan JSON for persistence outside browser memory. Editing requirements invalidates the current plan; refresh clears active state. Downloaded JSON is an intermediate design, not a Power BI release. APBRA-133 must consume validateDesignPlan before generation; Power BI compatibility and end-to-end evaluation remain NOT_RUN.

## APBRA-133 generated project

After confirming requirements and creating DesignPlan, Generate Power BI candidate creates 40 actual source files and an inspection ZIP. Source edits invalidate the candidate and revoke its download URL. The ZIP is explicitly not a governed release; APBRA-134/135 own validation and release gates.

The only supported input is the exact validated synthetic golden plan. Six tables use embedded synthetic CSV through generated Import M; no external source, credentials or model call. DAX text, five relationships, two pages, nine report visuals, six slicers, three filter fields and initial year2025 are rendered from the plan. M is never executed by the web application. PBIP/PBIR/TMDL are preview formats; extract the whole archive before Desktop use. Desktop open/refresh, DAX numerical results and RLS runtime are NOT_RUN, not implied by schema tests.

Format references (read2026-09-17): [PBIR](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report), [semantic model](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset), [TMDL syntax](https://learn.microsoft.com/en-us/analysis-services/tmdl/tmdl-overview). Public Microsoft JSON schemas are pinned by version in each generated JSON file. Actual validation against17 recursively resolved official schemas passed for23 generated JSON files; ZIP CRC and all40 exact entry bytes independently checked with Python zipfile. This is source-format evidence, not Desktop compatibility. No new dependency, paid service or entitlement required by local rendering; no service publishing configured.
