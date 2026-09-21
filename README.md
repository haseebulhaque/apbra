# AI-Powered Power BI Report Automation (APBRA)

APBRA is a working bounded MVP/prototype with a demonstrated Candidate Ready happy path. It is not production-ready. The Capstone is complete/submitted; MVP and product development continue.

## Implemented bounded MVP flow

```text
Requirement + schema
→ GPT-4.1 interpretation
→ bounded iterative clarification in Business Mode (default) or Advanced/BI Mode
→ explicit human confirmation of material business meaning
→ ConfirmedRequirementContract v2
→ governed in-app RAG
→ original AI Report Design
→ deterministic obligation coverage, normalization and strict integrity validation
→ one bounded ReportDesign correction and complete revalidation when eligible
→ bounded layout repair when eligible
→ deterministic guardrails
→ bounded PBIP/PBIR compiler
→ deterministic candidate validation
→ Candidate Ready / Human Review Required / Unsupported / Out of Scope / Blocked
```

GPT-4.1 reasons under ambiguity and makes ordinary supported BI design choices. The human confirms material business meaning. The typed contract freezes that meaning. Deterministic software owns semantic preservation, supported capability, safety, compilation and artifact validation. Raw answers remain provenance and are not deterministically reinterpreted downstream.

The business workspace and administration plane are distinct. Business users create reports and inspect session runs. Administrators inspect prototype tenant settings, AI models, governed knowledge, branding and generation policies. Authentication, RBAC and real multitenancy are outside the Capstone.

## Run locally

Use synthetic data only. Copy `apps/web/.env.example` to the ignored `apps/web/.env.local` and populate the existing Azure AI Foundry configuration without committing credentials.

```sh
cd apps/web
npm ci
npm test
npm run build
npm run dev
```

The default Vite URL is `http://127.0.0.1:5173/`. Foundry-dependent stages fail visibly when the configured endpoint is unavailable.

## Current evidence

The canonical successful run is `8042cc44-620f-4457-828d-0770749a653f`. After clarification and human confirmation, it generated `SalesPerformance`: `Total Sales = SUM(Sales_Data.Revenue)`, an Executive Summary, a Total Sales card, Total Sales by Region bar chart and Region slicer. Governed citations were `CB-001`, `PM-002`, `RD-004`, `RD-001`; compiler and deterministic candidate validation passed; final state was Candidate Ready.

No durable run-specific candidate digest or exact-candidate Power BI Desktop PASS is recorded. Generation and deterministic validation PASS are the highest verified claims. Run `0927fd18-1c61-4610-8167-de86933a1de1` is the complex fail-closed example: confirmed monthly intent was rejected at `REPORT_DESIGN_COVERAGE_INVALID` and produced no candidate. `d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa` remains historical ServiceNow evidence, not the current baseline.

## Product boundary

APBRA does not claim universal Power BI generation or production readiness. The bounded compiler supports common cards, charts, tables and slicers within an explicit layout/model contract. DAY, MONTH, QUARTER and YEAR trend grains have genuine representations; WEEK, fiscal/custom calendars and locale-specific policies remain unsupported. Unsupported or unsafe designs stop rather than being approximated.

Production gaps include identity/RBAC, tenant isolation, durable knowledge ingestion and indexing, secure managed configuration, broader Power BI compatibility, tenant publishing, gateway and credential orchestration, reviewer workflow, load and resilience engineering, SLOs/monitoring, broader evaluation, privacy/compliance operations and commercial operations.

The successful flow can generate the lazy-loaded `Report-Deployment-Guide.pdf`. The guide contains handover and deployment instructions; its generation does not mean the report was deployed. APBRA does not autonomously publish to production.

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Requirements and delivery evidence](REQUIREMENTS.md)
- [AI and governed RAG](AI-RAG-SPEC.md)
- [Power BI generation contract](POWERBI-GENERATION-SPEC.md)
- [MVP acceptance status](MVP-ACCEPTANCE-CRITERIA.md)
- [Web application](apps/web/README.md)
- [Capstone evidence index](docs/engineering/capstone-evidence.md)
- [Current engineering handoff](docs/engineering/codex-handoff.md)
- [Security policy](SECURITY.md)

Confluence owns architecture and requirements, Jira owns delivery intent, and GitHub owns code and durable engineering evidence. The repository remains public by owner decision. Do not publish credentials, customer data, private transcripts or secret-bearing URLs.

## License

Public visibility is intentional; no open-source license has been selected.
