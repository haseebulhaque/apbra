# APBRA bounded MVP architecture

## Current protected APBRA-174 slice

The durable FastAPI/PostgreSQL application is distinct from the historical browser-only Capstone described below. An active tenant resolves an immutable current settings version at the server boundary; Owner/Admin edits and restores create new versions, audit the actor, and use optimistic concurrency. Fixed compiler/security invariants remain code contracts. Provider credentials are encrypted behind a provider-neutral secret-store interface using a deployment-supplied keyring and are never returned by settings reads. A missing credential cannot activate intelligent generation.

The current case flow permits a model to ask zero or optional questions, retains answers and explicit Clarify/Enhance cycles, and binds acceptance to the exact interpretation, request, evidence, and settings version. The seeded clarification ceiling is two rounds per cycle and ten rounds overall; those numbers are tenant policy, not implicit model behavior. Supported partial scope is labelled with omissions and limitations; mandatory unsupported meaning is not reinterpreted as success. Existing authorized-expert continuation remains distinct from ordinary member acceptance.

Automatic design remains an untrusted model proposal followed by deterministic validation. The compiler's six-slot grid is an implementation invariant. A generic measure/column collision is resolved by a technical measure-only table and exact binding rewrite, with unchanged measure names and formulas. Final candidate generation emits a `Delivery-Guide.md` bound to the report design, settings, request, validation and attempt digests. A validation-only bridge pass does not pretend a final artifact/guide exists. Candidate download is not release approval or successful deployment.

The current protected local/CI foundation includes merged protected-case identity, private-case, durable-evidence and generation work through APBRA-174, including Tenant Settings and qualified-provider controls. Sections explicitly labelled historical preserve the earlier APBRA-145 Capstone compiler and model-call evidence. Accepted future architecture is not proof of a deployed capability.

## Implemented local/CI onboarding and identity architecture

The target identity boundary is provider-neutral. A qualified external identity provider performs authentication; APBRA converts the validated identity into an `ExternalIdentityBinding` using stable provider identifiers such as issuer plus subject/object identity and then evaluates APBRA-owned company membership, capabilities and private-resource grants. Microsoft Entra External ID is the first profile planned for live qualification after APBRA-172, while Google, Apple and other qualified OIDC/federation providers may use the same adapter seam later. Core domain logic must not depend on Microsoft-specific claims or Azure hosting.

A newly authenticated person follows one of three server-authoritative paths: resume an existing active membership, accept an eligible invitation, or create a new APBRA company/workspace. Self-service company creation atomically creates the company and the creator's initial `COMPANY_OWNER` membership. An external tenant, email/UPN domain or IdP group is never itself an APBRA company or role. Account linking across providers requires an explicit verified flow; equal email addresses do not silently merge security identities.

Authority remains deliberately layered: **authentication ≠ company membership ≠ exact private-resource access ≠ Power BI/Fabric consent ≠ Azure management authority ≠ commercial entitlement**. Enterprise-managed SSO, verified-domain joining and SCIM/JIT may be added later as company policy integrations and can require customer-administrator action, but basic self-service signup/sign-in must not require APBRA to configure each customer's directory.

Confluence 10.03 v7 and 02.01 v9 retain these authority rules. Merged APBRA-151/172 implement first-company creation, initial owner, multi-company invitations, bounded membership/profile lifecycle and provider-neutral OIDC/application sessions in local/CI. Live Entra, public signup and hosted multi-user qualification remain open under APBRA-173 and later gates.

> **Historical Capstone boundary:** GPT-4.1 proposed meaning and design; the human confirmed material meaning; deterministic software validated safety and preservation. The current protected application keeps those authority boundaries without mandating a particular model.

## Accepted deployment, data-plane and entitlement architecture — future

[Confluence 04.07 v2](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/9568258) accepts APBRA Cloud (shared APBRA-managed multi-tenant), APBRA Dedicated (isolated customer cloud/account or hosted environment under an agreed operator model), and qualified APBRA Private / On-Premises (inside the customer boundary). Air-gapped operation is a further profile only after explicit qualification. These are target deployment models, not current production deployments. Azure is the reference/private-preview deployment profile; the core product must not depend on Azure Container Apps, Key Vault, Azure OpenAI, Azure PostgreSQL or Azure-only identity. Provider-neutral adapters preserve configurable deployment choices while fixed security, protocol and validation contracts remain fixed.

A future central control plane carries minimum commercial and deployment lifecycle metadata: organisation/deployment catalogue, stable `deployment_id`, subscription/edition, versioned entitlements, licence status/expiry, release channel and appropriately minimised safe deployment/licence metadata. The selected **customer data plane** owns customer users/mappings, Tenant Settings, protected secrets, evidence/source data, prompts/conversation, accepted requirements, generated reports/artifacts/Delivery Guides, audit/history and operational customer content. Subscription validation cannot require that content or give the central plane direct access to it. Telemetry, support access and network egress need separate qualification. Local/CI PostgreSQL and the APBRA-173A portable protected-content storage contract with secure local/alternate adapters demonstrate bounded persistence and portability mechanics; they are not a production customer-hosted or central licensing service.

`deployment_id` identifies an installation and licence lifecycle; `tenant_id` identifies a company security and governance domain. One Cloud deployment may contain many tenants, while Dedicated/Private installations may have one or an explicitly configured set. Tenant isolation applies even in a single-customer installation. Clone, restore and disaster-recovery identity semantics remain future design work.

[Confluence 04.08 v2](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/9535525) defines **Subscription → versioned Entitlements → stable Capabilities**. Effective capability is the intersection of installed/qualified platform support, subscription entitlement, Tenant Settings, user/application permission, resource permission and current security/validation/governance. Entitlement controls commercial availability, never authorization, private-resource access, target validity, mandatory validation or release approval. A future server-authoritative resolver should ask for capability keys rather than branch on marketing plan names. Connected and offline signed-entitlement paths, commercial packages, prices, quotas and grace rules require separate governance; no entitlement engine or billing integration is claimed here.

The current Power BI PBIP/PBIR/TMDL compiler is a bounded output adapter. [Confluence 03.06 v1](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/7864321) and APBRA-165 place a versioned APBRA Report Definition (ARD) between design intent and future native rendering/adapters. ARD, native canvas, other platform outputs and connected publishing are not implemented by this architecture statement. PBIX support is not inferred from PBIP generation.

## Historical Capstone application planes

The earlier React/Vite prototype had two clearly separated areas:

- **Business workspace:** Create Report and My Runs.
- **Administration:** Tenant Settings, AI & Models, Governed Knowledge, Branding & Report Standards, and Guardrails & Generation.

The separation represents the intended responsibility boundary. The Capstone does not implement authentication, RBAC, durable tenants or a production administration service.

## Accepted target architecture — planned, not implemented

The product target keeps a single reasoning and assurance engine behind Guided and Advanced experiences. Intake becomes conversation-first and may begin without a file or project. Plain-language source descriptions, qualified schema/data uploads, screenshots and report/sketch references are distinct evidence classes: visual evidence can inform questions and design, but cannot prove an absent field, source fact, permission or measure definition.

The case becomes the durable unit of continuation. It may later be assigned to an authorized BI expert without losing the conversation, evidence, accepted decisions or deterministic findings. Optional projects, collaboration and linked requirement/report/candidate/deployment histories sit around that case. Company registration, membership, sign-in profiles, subscriptions and usage visibility are product controls; they do not automatically grant access to customer tenants, private sources, trusted-author status or external management operations.

Versioned, validated, permissioned Tenant Settings already cover bounded provider/model selection and protected credential references. Broader branding, terminology, report layout/theme and governed standards remain phased configuration direction. APBRA-managed and customer-managed model profiles—including separately approved private/local options—must be qualified. Customer Azure provisioning, where an Azure reference deployment is chosen, is a separate, explicit-consent management operation; possession of an inference key is not provisioning authority or evidence that Azure is universal.

PBIP delivery and deployment guidance remain the first delivery boundary. Connected-source discovery, Power BI/Fabric publishing, connections, gateways, refresh and applicable security configuration require separately qualified permissions and evidence. Optional data-architecture assessment and reviewable scripts are a separate advanced capability and must never modify a source schema automatically.

The target architecture adds hosted/production qualification of identity and tenant isolation, durable knowledge lifecycle, controlled sharing/review/release, observability, evaluation/red teaming, reliability and FinOps. Local/CI identity, private-case persistence and validated candidate history already exist in bounded form. It does not select a replacement stack, provider, region, commercial price, SLA or numerical limit. APBRA-149–158 describe planning slices; they are not proof that these services exist.

## Historical Capstone processing pipeline

The following Azure AI Foundry run and corpus describe earlier Capstone execution, not a required provider for the current protected application. Current local/CI tests use deterministic substitutes unless an explicitly qualified tenant provider and credential are enabled.

```text
Requirement + request-specific CSV/XLSX schema
→ Azure AI Foundry GPT-4.1 interpretation
→ bounded iterative clarification with immutable raw-answer provenance
→ READY_FOR_CONFIRMATION and explicit human confirmation
→ ConfirmedRequirementContract v2
→ APBRA in-app governed retrieval
→ original AI Report Design
→ deterministic obligation coverage, normalization and integrity validation
→ one bounded structured correction and complete revalidation when eligible
→ bounded layout repair when eligible
→ deterministic guardrails
→ bounded PBIP/PBIR compiler
→ deterministic candidate validation
→ terminal status
```

Terminal statuses include Candidate Ready, Human Review Required, Unsupported, Out of Scope and Blocked. Technical provider/infrastructure failure remains separate. Generation does not start after a semantic, coverage, integrity, capability or policy safe-stop.

### Historical AI boundary

The Capstone adapter used an Azure AI Foundry/Azure OpenAI-compatible endpoint. Live evidence observed `gpt-4.1-2025-04-14`; embeddings use `text-embedding-3-small` with 1,536 dimensions. GPT detects material ambiguity, interprets natural-language answers and proposes confirmed meaning and a grounded ReportDesign. Business Mode is default; Advanced/BI Mode accepts optional technical preferences. GPT chooses ordinary supported BI presentation but cannot approve guardrails, establish measure correctness, select release authority or certify candidate validity.

### Confirmation boundary

Raw requirements, questions and answers remain immutable provenance. Only human-confirmed structured meaning enters ConfirmedRequirementContract v2. Deterministic TypeScript does not infer business meaning from arbitrary prose. Coverage later proves exact typed obligations, business-question mappings, measures, fields, page scope and time semantics remain represented.

An accepted assumption is a visible business decision, not evidence for an absent field, unknown source fact, missing permission or unsupported capability. Any material rescope must return to explicit acceptance and retain the earlier confirmation as provenance.

### Request schema boundary

CSV/XLSX structure is request-specific context, not tenant knowledge. Parsing extracts bounded table, sheet, column, type, limited sample and explicitly discoverable relationship metadata. Workbook bytes and unnecessary raw business data are not placed in the governed corpus.

## Historical Capstone governed in-app RAG

Five fictional APBRA organisational standards are chunked using headings and bounded token-aware windows. The Capstone corpus contained 20 chunks. `text-embedding-3-small` embeds the corpus and runtime query; an in-memory exact cosine comparison selects configurable top-k results with source, version, heading, chunk and citation provenance.

This Capstone implementation does **not** use the historical S08 Foundry Knowledge store, and no claim is made that APBRA documents were uploaded there. Production still requires tenant upload, replacement/deletion, extraction, versioning, chunk lifecycle, stale-chunk cleanup, re-indexing, permissions, durable vector infrastructure, tenant isolation and monitoring.

## Original and normalized Report Design

The original AI Report Design is retained as evidence. A separate deterministic normalizer converts safely expressible intent into the strict compiler contract before validation. Examples include splitting independent slicer fields into separate slicers and collapsing an identical field/category duplicate.

Normalization uses stable deterministic IDs, compiler-aligned placement and page-bound checks. One bounded ReportDesign correction may receive exact domain-neutral findings; it cannot alter confirmed measures/business meaning and corrected output is fully revalidated. Bounded layout repair preserves original and repaired designs separately. Unsupported ambiguity or capacity creates a typed finding and stops.

## Strict integrity boundary

Integrity validation enforces canonical unique measure identities, supported aggregations, resolved ratio operands, self-reference prevention, dependency-cycle detection, validity of unused measures, visual measure references and per-type binding cardinality. A slicer must resolve to exactly one field/category binding and zero measures after normalization. The compiler repeats defensive checks before generating files.

## Bounded compiler and layout

The deterministic compiler consumes only the normalized, validated Report Design. Its page contract is 1,280 × 720. The compiler-aligned grid uses columns at x=20 and x=630, and rows at `y = 30 + row × 260`. Cards are 285 × 120; other supported visuals are 580 × 230.

Every visual must satisfy `x ≥ 0`, `y ≥ 0`, `x + width ≤ 1280`, and `y + height ≤ 720`. Existing and expanded visuals both consume capacity. If placement cannot fit, `LAYOUT_CAPACITY_EXCEEDED` records the attempted layout and compilation remains `NOT_STARTED`.

The supported subset includes common KPI cards, bar/column/line charts, tables, slicers, multiple bounded pages, explicit supported measures, simple relationships and tenant theme colours. GPT chooses among supported visual types; deterministic code does not impose universal KPI/card or trend/line preferences.

DAY uses the raw temporal binding. MONTH, QUARTER and YEAR use generated grouping columns based on `Date.StartOfMonth`, `Date.StartOfQuarter` and `Date.StartOfYear`; generated names are collision-checked and candidate validation proves both grouping and visual binding. A raw Date binding cannot falsely prove a non-DAY grain. WEEK, fiscal/custom calendars and locale-specific policies remain unsupported.

Unsupported visuals, arbitrary model-authored DAX/M/SQL, DirectQuery/Direct Lake, write-back, inferred RLS, autonomous publishing and production credential configuration are not silently substituted.

## Validation and handover

Candidate validation checks project/package structure, report/model references, supported visuals, measure and field references, relationships and generated identifiers. Power BI Desktop remains the final runtime proof.

Successful candidates expose a Power BI project archive and lazy-loaded `Report-Deployment-Guide.pdf`. The PDF provides contextual deployment and handover instructions; it is evidence of guide generation, not production deployment.

## Production architecture gap

The current protected application has bounded provider-neutral identity and company lifecycle, private-case authorization, PostgreSQL state, APBRA-173A portable storage with local/alternate adapters and tenant credential encryption in local/CI. Production still needs hosted identity/tenancy qualification, managed secret and storage operations, durable knowledge indexes, orchestration, publishing APIs, gateway/credential workflows, reviewer lifecycle, observability/SLOs, resilience/DR, broader compatibility/evaluation and privacy/compliance operations. The modular-monolith and port/adapter direction remains the intended production decomposition; neither the historical browser prototype nor the local/CI foundation proves those hosted services exist.

The target “no dead ends” behaviour is truthful recovery: a supported alternative that makes every material change visible, or continuation by an authorized expert. It is not guaranteed generation and cannot convert a provider failure, unsupported capability or missing authority into success. Expert assistance, business acceptance, candidate inspection, release approval and successful deployment remain separate lifecycle events.
