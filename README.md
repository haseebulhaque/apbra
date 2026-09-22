# AI-Powered Power BI Report Automation (APBRA)

APBRA is a working bounded MVP/prototype with a demonstrated Candidate Ready happy path. It is not production-ready. The Capstone is complete/submitted; MVP and product development continue.

`APBRA-PRODUCT-2026-09-22` is the accepted post-Capstone product-intent baseline. It describes what APBRA is intended to become; the implemented flow and evidence below describe what exists today. See [REQUIREMENTS.md](REQUIREMENTS.md) for all eighteen `PC26-FR` requirements and their Jira mappings.

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

## Target product direction — not yet implemented

APBRA is intended to grow into a generic SaaS product without becoming a collection of domain-specific report templates. Guided and Advanced experiences will share one engine. Conversation-first intake will not require an upload or project; qualified schema/data uploads, plain-language source descriptions, screenshots and report/sketch references may contribute evidence with explicit limitations. Material rescoping will require visible acceptance, while ordinary supported BI design remains the AI Report Architect's responsibility.

The accepted target also includes authorized BI-expert continuation of the same case; company registration and membership; optional projects, collaboration and linked requirement/report history; commercial entitlements and usage visibility without an invented price model; tenant branding, terminology and governed standards; qualified APBRA-managed and customer-managed model profiles; and separately consented customer Azure provisioning.

PBIP delivery and deployment guidance remain the first delivery boundary. Connected-source discovery, Power BI/Fabric publishing, connections, gateways, refresh and applicable security configuration are separately qualified future capabilities. Optional advanced data-architecture advice and reviewable scripts remain separate from ordinary report generation and never authorize automatic source-schema changes. Privacy, guardrails, evaluation, red teaming, tracing, reliability and cost control are cross-cutting product obligations.

“No dead ends” means truthful supported alternatives or meaningful expert continuation. It does not guarantee generation, turn an unsupported request into a success, or relabel technical failure. APBRA-147 remains on planning hold; APBRA-149 through APBRA-158 are planning items rather than implemented features.

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

Modes, licences, company membership and model keys do not themselves authorize private-resource access, trusted-author status, publishing or external management. Expert assistance, business confirmation, candidate inspection, release approval and successful deployment remain distinct states.

The successful flow can generate the lazy-loaded `Report-Deployment-Guide.pdf`. The guide contains handover and deployment instructions; its generation does not mean the report was deployed. APBRA does not autonomously publish to production.

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Implementation and product baseline](docs/decisions/implementation-baseline.md)
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
