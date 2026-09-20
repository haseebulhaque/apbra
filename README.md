# AI-Powered Power BI Report Automation (APBRA)

APBRA is a working, bounded Capstone prototype that turns a business requirement and declared CSV/XLSX schema into a governed Report Design and, when supported, a validated editable Power BI Project (PBIP) candidate.

## Implemented Capstone flow

```text
Requirement + schema
→ GPT-4.1 interpretation
→ dynamic clarifications
→ governed in-app RAG
→ original AI Report Design
→ deterministic Report Design normalization
→ strict integrity validation
→ deterministic guardrails
→ bounded PBIP/PBIR compiler
→ deterministic candidate validation
→ Candidate Ready / Human Review Required / Unsupported / Blocked
```

GPT-4.1 interprets requirements, identifies ambiguity, creates clarification questions and proposes a grounded structured Report Design. Deterministic code owns normalization, reference and measure integrity, compiler compatibility, guardrails, candidate validation and whether generation may proceed.

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

The current live happy path is run `d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa`. It completed interpretation, three dynamic clarifications, governed retrieval, normalization, integrity checks, guardrails, compilation and deterministic validation. The resulting candidate is:

- `ServiceManagementFunnel.d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa.candidate.zip`
- SHA-256 `833dff4ba7de7045e23ff6b42ce1e48e73b33534f1f910e7420753a1c5eab0f3`
- Power BI Desktop validation for this exact candidate: **PENDING**

Historical Desktop evidence remains valid for the earlier `SalesPerformance.candidate.zip` and `ServiceDeskOperations.candidate.zip` candidates; it does not validate the current candidate. See the [Capstone evidence index](docs/engineering/capstone-evidence.md).

## Product boundary

APBRA does not claim universal Power BI generation or production readiness. The bounded compiler supports common cards, charts, tables and slicers within an explicit layout and model contract. Unsupported or unsafe designs stop before compilation.

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
