# AI-Powered Power BI Report Automation (APBRA)

## Current APBRA-174 implementation boundary

The protected invited-case application now has versioned tenant settings, an Owner/Admin settings surface, and protected tenant credential references. Deployment bootstrap supplies the keyring; tenant settings select a qualified provider profile and enable it only when a usable tenant credential is present. No provider, model, region, credential, or business meaning is chosen by default. A disabled provider leaves intelligent generation unavailable without blocking case access.

Clarification is model-led and may return zero questions. Optional questions do not block acceptance of an otherwise ready interpretation. A user can explicitly Clarify/Enhance with a new bounded cycle; the initial tenant policy is two clarification rounds per cycle and ten rounds overall, with durable counts and exact accepted-version binding. Supported partial scope must disclose omissions and limitations before acceptance; mandatory blockers still fail closed or route to an authorized expert.

The canonical compiler preserves model/column/measure namespace safety without a business-specific name rule. A successful candidate ZIP contains an exact-version-bound `Delivery-Guide.md` alongside the PBIP and ReportDesign artifacts. The guide is handover information, not deployment approval or proof of Power BI Desktop execution. The historical Capstone notes below describe earlier prototype evidence and are not claims about this protected application.

APBRA has a working bounded local/CI protected-case foundation and an earlier Capstone Candidate Ready demonstration. Neither is production-ready. The Capstone is complete/submitted; MVP and product development continue.

`APBRA-PRODUCT-2026-09-22` is the accepted post-Capstone product-intent baseline. It describes what APBRA is intended to become; the current protected local/CI slice above and the historical Capstone flow below have separate evidence boundaries. See [REQUIREMENTS.md](REQUIREMENTS.md) for all eighteen `PC26-FR` requirements and their Jira mappings.

## Accepted self-service onboarding and identity direction — target, not yet implemented

The 2 October 2026 owner decision defines the next onboarding architecture without changing the current local/CI runtime. APBRA authentication is provider-neutral: a qualified external provider authenticates the person, APBRA binds that identity using stable validated provider identifiers such as issuer plus subject, and APBRA then resolves its own company and resource authority. Microsoft Entra External ID is the first qualified live provider for APBRA-172, not a mandatory core dependency. Additional providers such as Google, Apple or other approved OIDC/federation profiles require separate qualification.

The target user journey is **authenticate → resolve existing membership or eligible invitation → otherwise Create Company / Workspace**. Company creation and the creator's initial `COMPANY_OWNER` membership are server-authoritative and transactional. Authentication alone does not grant APBRA company membership, access to every private report/case, Power BI/Fabric consent, Azure management authority or commercial entitlement. Email domain, UPN suffix, external tenant ID and IdP group membership must not silently create APBRA authority. Verified-domain auto-join, enterprise SSO and SCIM/JIT are separate opt-in capabilities and may require customer-admin involvement.

The current local/CI application still uses the bounded invited-membership/development-issuer foundation described below. APBRA-151 owns self-service company lifecycle implementation, APBRA-172 owns the provider-neutral SSO/session implementation, and APBRA-173 owns private hosted-preview qualification. This documentation change proves none of those runtime outcomes.

## Historical Capstone bounded flow

The following pipeline and GPT-4.1 run evidence belong to the completed Capstone. The protected FastAPI/PostgreSQL local/CI case journey described above is the current application foundation; neither the historical model call nor its browser-only settings prove a live provider call or Desktop run on the current revision.

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

In the historical Capstone, business users created reports and inspected session runs while administrators inspected browser-held prototype settings and standards. Authentication, RBAC and real multitenancy were outside that Capstone. The current local/CI application instead has server-derived invited identity, private-case authorization and durable Tenant Settings; hosted production qualification remains open.

## Accepted deployment and entitlement direction — not current runtime support

[Confluence 04.07 v2](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/9568258) and [04.08 v2](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/9535525) define future portable deployment and commercial architecture. APBRA Cloud is an APBRA-managed multi-tenant profile; Dedicated and qualified Private / On-Premises place customer workloads in their agreed boundaries. Air-gapped operation requires later explicit qualification. Azure remains a reference/private-preview deployment choice, not a mandatory core dependency. Identity, storage, networking, model reachability, secrets, recovery, telemetry, updates and target-platform connectivity must be qualified per profile before it is called supported.

A future central control plane may retain only minimum organisation/deployment and commercial lifecycle metadata, such as stable `deployment_id`, subscription/edition, versioned entitlements, licence status/expiry and release channel. Customer users and mappings, Tenant Settings, credentials, evidence and source data, prompts, accepted requirements, reports, guides, customer audit and operational content remain in the selected customer data plane. Subscription validation must not require their upload or give the control plane a content back door. `deployment_id` names an installation; `tenant_id` names a company security/governance domain. One shared Cloud deployment may host multiple tenants; a Dedicated or Private deployment has its separately qualified relationship to tenants.

The future commercial chain is **Subscription → versioned Entitlements → stable Capabilities**. Effective capability is the intersection of installed platform support, subscription entitlement, Tenant Settings, user/application permission, resource permission and current safety/validation/governance. A paid entitlement never bypasses authorization, tenant isolation, private-resource access, target validity or release approval. Product logic should evaluate capability keys, not marketing plan names. Exact plans, prices, quotas, grace periods and billing providers remain undecided; the entitlement engine is not implemented in this local/CI foundation.

## Target product direction — not yet implemented

APBRA is intended to grow into a portable report-generation product without becoming a collection of domain-specific report templates. APBRA Cloud is one accepted deployment profile, alongside Dedicated and qualified Private / On-Premises profiles; a future air-gapped profile requires explicit qualification. None of those profile names proves a deployed, supported runtime today. Guided and Advanced experiences will share one engine. Conversation-first intake will not require an upload or project; qualified schema/data uploads, plain-language source descriptions, screenshots and report/sketch references may contribute evidence with explicit limitations. Material rescoping will require visible acceptance, while ordinary supported BI design remains the AI Report Architect's responsibility.

The accepted target also includes authorized BI-expert continuation of the same case; company registration and membership; optional projects, collaboration and linked requirement/report history; commercial entitlements and usage visibility without an invented price model; tenant branding, terminology and governed standards; qualified APBRA-managed and customer-managed model profiles; and separately consented customer Azure provisioning where that reference deployment profile is selected and separately authorized. Azure is not a mandatory core product dependency.

Bounded Power BI PBIP/PBIR/TMDL candidate generation is the current output adapter. Confluence 03.06 v1 and APBRA-165 describe a future versioned APBRA Report Definition (ARD), native rendering and other adapters; none is implemented by this documentation change. PBIX generation is not claimed. PBIP delivery and deployment guidance remain the first delivery boundary. Connected-source discovery, Power BI/Fabric publishing, connections, gateways, refresh and applicable security configuration are separately qualified future capabilities. Optional advanced data-architecture advice and reviewable scripts remain separate from ordinary report generation and never authorize automatic source-schema changes. Privacy, guardrails, evaluation, red teaming, tracing, reliability and cost control are cross-cutting product obligations.

“No dead ends” means truthful supported alternatives or meaningful expert continuation. It does not guarantee generation, turn an unsupported request into a success, or relabel technical failure. APBRA-147 is now closed as a bounded delivered/superseded slice; APBRA-149–158 remain roadmap/planning items unless current Jira and exact implementation evidence say otherwise.

## Run locally

APBRA-164 extends the local/CI invite-only foundation with protected generation, durable attempt history and private validated candidate artifacts after APBRA-163 conversation, evidence and exact confirmation. It uses FastAPI, PostgreSQL 17, separate private local evidence and artifact volumes, the canonical TypeScript semantic/generation pipeline, and a development-only OIDC issuer. Use synthetic data only. Generate local secrets in the shell and keep them out of files, logs and commits.

```sh
export APBRA_POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export APBRA_SESSION_SECRET="$(openssl rand -hex 32)"
docker compose up --build postgres api
```

In another shell:

```sh
npm --prefix apps/web ci --ignore-scripts
npm --prefix apps/web run dev
```

Open `http://127.0.0.1:5173/`; the API health endpoint is `http://127.0.0.1:8000/api/health`. The local identity choices exercise the OIDC redirect and server-side APBRA authorization path. Creating a case requires neither a project nor a file. PostgreSQL retains requests, conversation, evidence provenance, interpretations, confirmed contracts and generation history across restarts; the private volumes retain qualified evidence and validated candidate bytes. The Package B interpretation and Package C ReportDesign adapter are explicitly deterministic simulations and make no model call. They exercise the governed lifecycle but do not establish general AI understanding or AI design quality.

See [the API runbook](apps/api/README.md) and [web application guide](apps/web/README.md) for the bounded preview, synthetic identities, restart behaviour and limitations. Do not use `docker compose down --volumes` unless deliberately deleting synthetic local data. Qualified model-provider configuration and protected credentials remain server-side and are not required for case persistence. AI-dependent stages fail visibly when no qualified, enabled provider is available; the deterministic local/CI substitutes make no real model call.

## Historical Capstone evidence

The canonical successful run is `8042cc44-620f-4457-828d-0770749a653f`. After clarification and human confirmation, it generated `SalesPerformance`: `Total Sales = SUM(Sales_Data.Revenue)`, an Executive Summary, a Total Sales card, Total Sales by Region bar chart and Region slicer. Governed citations were `CB-001`, `PM-002`, `RD-004`, `RD-001`; compiler and deterministic candidate validation passed; final state was Candidate Ready.

No durable run-specific candidate digest or exact-candidate Power BI Desktop PASS is recorded. Generation and deterministic validation PASS are the highest verified claims. Run `0927fd18-1c61-4610-8167-de86933a1de1` is the complex fail-closed example: confirmed monthly intent was rejected at `REPORT_DESIGN_COVERAGE_INVALID` and produced no candidate. `d6884abb-f587-4caa-bc1c-d0cfb2bcb1fa` remains historical ServiceNow evidence, not the current baseline.

## Product boundary

APBRA does not claim universal Power BI generation or production readiness. The bounded compiler supports common cards, charts, tables and slicers within an explicit layout/model contract. DAY, MONTH, QUARTER and YEAR trend grains have genuine representations; WEEK, fiscal/custom calendars and locale-specific policies remain unsupported. Unsupported or unsafe designs stop rather than being approximated.

APBRA-162 provides the bounded local/CI identity, membership and private-case authorization foundation; APBRA-164 adds private local/CI validated artifact storage, not a hosted artifact service. Live Entra qualification, hosted tenant isolation and operations, durable knowledge ingestion and indexing, managed configuration, broader Power BI compatibility, tenant publishing, gateway and credential orchestration, reviewer workflow, load and resilience engineering, SLOs/monitoring, broader evaluation, privacy/compliance operations and commercial operations remain gaps.

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
