# APBRA-129 local requester shell

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

The browser supports request entry, frozen synthetic schema selection/inspection, manual clarification inputs and draft preparation. It does not infer answers, create an authoritative RequirementsSnapshot, run integrated knowledge retrieval, generate/validate Power BI, authorize release, or record actual end-to-end evaluation. Those stages remain NOT_RUN and package download is disabled. Expected fixture answers are explicitly labelled, not presented as AI output. These UI drafts are not authorization or durable evidence.

APBRA-130 through APBRA-136 will integrate real domain/backend behaviour; full APBRA-129 golden-scenario acceptance requires that integration and is pending. No APBRA-27 or subsequent item is implemented here. Power BI Desktop, DAX and RLS runtime are NOT_RUN.

## Sources and engineering boundary

Jira APBRA-129/128 and Confluence21.03v2 were read live on2026-09-17. User-authorized Capstone scope admits these exact web paths through a validated APBRA-129 task extension; existing bootstrap and secret controls remain mandatory. The broader proposed product source statuses remain unchanged. Source acceptance checks positively require ACCEPTED or BASELINED for implementation tasks.

React and Vite are MIT-licensed; TypeScript is Apache-2.0. Local tools do not require a paid plan. No purchase, cloud or model service is introduced. Official references: https://vite.dev/guide/ and https://react.dev/versions. Repository license selection remains the owner’s separate decision.

## APBRA-131 curated evidence preview

The independent preview reads all eight rules directly from the frozen APBRA-90 corporate standards fixture. The deterministic adapter accepts only `sales-v1`, returns source path, pack/version, authority and per-rule citations, and accepts no external documents or prompt instructions. Mandatory customer rules outrank generic recommendations subject to security/platform controls and confirmed facts; evidence grants no authorization. No precedence resolver or DesignPlan is implemented.

`verifyCuratedCitations` checks canonical citation membership and mandatory coverage against this fixed catalog. It does not validate consumer source versions or consumed DesignPlan integrity. The adapter records K=8, result count and ordered evidence IDs; no retrieval quality metric is claimed. Unit evaluation verifies provenance against the fixture and golden design assertion IDs, plus missing/forged citations and unsupported scenarios. This is adapter evidence, not a completed DesignPlan evaluation. Future APBRA-132/136 integration must consume and bind this evidence to actual outputs. Workflow stages remain not run; no commercial RAG, model, vector service, cloud or production tenant boundary is introduced.
