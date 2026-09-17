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

The browser supports request entry, frozen synthetic schema selection/inspection, manual clarification inputs and draft preparation. APBRA-130 adds a typed local RequirementsSnapshot after explicit confirmation of the unchanged golden request and all three exact synthetic answers. It preserves copied original inputs, exposes JSON for inspection/replay, and invalidates the snapshot on edits. Unsupported text, RLS requirements or schema/coverage changes fail explicitly. This deterministic fixture adapter makes no provider call or AI inference claim. It does not retrieve knowledge, generate/validate Power BI, authorize release, or record actual end-to-end evaluation. Those later stages remain NOT_RUN and package download is disabled. Expected fixture answers are explicitly labelled, not presented as AI output. These UI drafts are not authorization or durable evidence.

APBRA-131 through APBRA-136 will integrate real domain/backend behaviour; full APBRA-129 golden-scenario acceptance requires that integration and is pending. No broad APBRA-27 backend or APBRA-131+ item is implemented here. Power BI Desktop, DAX and RLS runtime are NOT_RUN.

## Sources and engineering boundary

Jira APBRA-129/128 and Confluence21.03v2 were read live on2026-09-17. User-authorized Capstone scope admits these exact web paths through a validated APBRA-129 task extension; existing bootstrap and secret controls remain mandatory. The broader proposed product source statuses remain unchanged. Source acceptance checks positively require ACCEPTED or BASELINED for implementation tasks.

React and Vite are MIT-licensed; TypeScript is Apache-2.0. Local tools do not require a paid plan. No purchase, cloud or model service is introduced. Official references: https://vite.dev/guide/ and https://react.dev/versions. Repository license selection remains the owner’s separate decision.
