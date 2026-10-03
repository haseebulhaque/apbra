# APBRA MVP-1 web application

## APBRA-172 sign-in and membership boundary

The sign-in screen gets qualified provider labels and the local/test identity-selector capability from `GET /api/auth/providers`. Browser hostname, storage, query strings and UI route visibility are not security controls. Hosted mode supplies only deployment-qualified provider labels and has no deterministic selector. A configured Entra External ID email or OTP user flow must be labelled for that actual experience; this UI does not claim workforce Microsoft federation merely because the underlying service is Microsoft.

The browser follows a server-owned authorization-code/PKCE redirect and receives an HttpOnly APBRA session cookie after the server callback. It never stores an external ID/access/refresh token or receives the provider subject in `/api/auth/session`. Existing active membership enters the workspace; multiple active memberships require explicit server-checked selection. An exact invitation remains separately accepted through its original single-use link. APBRA-151 lets an authenticated identity with no active membership or eligible invitation create its first company. Inactive membership cannot use protected resources. Sign out revokes the APBRA session; it does not promise global identity-provider logout.

Browser, API and PostgreSQL tests exercise deterministic OIDC metadata, signing keys, rotation, binding and negative authority cases. They do not establish a live Entra External ID login, real MFA, customer federation or hosted readiness. APBRA-173 deployment remains separate.

## Current APBRA-174 protected experience

The active invited-case workspace permits zero or optional model-generated clarification questions. Optional unanswered questions do not block an otherwise ready acceptance; users can explicitly Clarify/Enhance within the versioned tenant policy (initially two rounds per cycle and ten rounds overall). The accepted interpretation shows supported scope and any omissions/limitations. Material input or settings changes stale acceptance; mandatory blockers still require a supported correction or authorized expert route.

An Owner/Admin settings panel exposes current validated categories, warnings, credential status masked as `***`, edit, version history and restore. A credential replacement goes to the protected server endpoint and never returns plaintext. Member and foreign/revoked actors do not get this administration surface or API authority. Provider/model selection is explicit, with no browser-held key or default. The panel stacks at narrow widths rather than overflowing the viewport.

Final protected candidate ZIPs include `Delivery-Guide.md`, bound to the exact request, accepted meaning, tenant settings, design, generation attempt and candidate digest. The guide records supported/omitted scope, measures, assumptions, standards and handover without claiming deployment. The browser's older lazy PDF described below is historical prototype behavior, not this ZIP artifact.

APBRA-164 extends the APBRA-163 durable case journey from exact confirmation to protected report generation, immutable attempt history and validated candidate download. The browser derives the signed-in actor from `/api/auth/session`; it never supplies authoritative company, membership, role, private-case permission, confirmed semantic claims, validation status or artifact identity.

An active invited member can create a case without a project or file, list only authorized cases, resume after a restart, save immutable request versions, add durable messages and protected evidence, inspect a server-derived understanding and explicitly confirm its exact current meaning. A current confirmation can then build a private candidate through the canonical pipeline. Request, conversation or evidence changes make earlier confirmation stale and prevent it from authorizing a new build.

Invitation bearer secrets are accepted only from the URL fragment of an original `/invite#token=...` link, removed from the address immediately, and sent in the body of fixed-path POST requests. A signed-out browser does not persist or forward the token through login; the user must sign in and reopen the original invitation link.

This React/Vite application is a working bounded local/CI business workspace with Power BI candidate generation as its current output adapter. It separates business work from protected tenant administration; it is not a production Cloud, Dedicated or Private deployment.

It is not the complete `APBRA-PRODUCT-2026-09-22` experience. The current UI and the accepted target are distinguished below.

## Accepted portable product UX — future

[Confluence 04.07 v2](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/9568258) accepts APBRA Cloud, Dedicated and qualified Private / On-Premises deployment profiles; air-gapped operation remains future and requires explicit qualification. Azure is a reference/private-preview choice, not a required product host. The current browser/API pair is local/CI evidence only. Customer case content, prompts, evidence, reports, Delivery Guides, Tenant Settings and secrets stay in the selected customer data plane; a future central commercial control plane may hold only minimum deployment/licence metadata. `deployment_id` identifies an installation, whereas `tenant_id` identifies its company security domain.

[Confluence 04.08 v2](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/9535525) defines future Subscription → versioned Entitlements → stable Capabilities. Effective access also requires installed platform support, Tenant Settings, user/application and resource permissions, and current safety/validation/governance. A future UI should explain whether a capability is commercially unavailable, disabled by policy, unauthorized, technically unsupported or failed validation without leaking protected administrative detail. Paid access never grants private-case, publishing or release authority. The present settings panel is not a subscription/entitlement administration system; exact plans, prices and limits remain undecided.

Current candidate output is bounded PBIP/PBIR/TMDL. [Confluence 03.06 v1](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/7864321) and APBRA-165 describe future ARD/native rendering, live canvas and other adapters; they are not current UI behavior. No Desktop-runtime PASS, PBIX generation or connected publishing is inferred. NO HARDCODING keeps tenant/provider/deployment/commercial choices governed; fixed permission and validation contracts remain fixed.

## Historical Capstone user experience

In the earlier browser prototype, business users used **Create Report** and **My Runs**. Business Mode was default: a run accepted a free-text requirement and synthetic CSV/XLSX data, asked bounded material business questions, interpreted natural-language answers, presented a business summary and required explicit confirmation before ConfirmedRequirementContract v2. Advanced/BI Mode accepted optional supported technical preferences without forcing manual report design. In the later protected application, readiness and confirmation use the same deterministic semantic prerequisites and bind the exact interpretation and material input context shown to the user.

The historical prototype allowed administrators to inspect Tenant Settings, AI & Models, Governed Knowledge, Branding & Report Standards, and Guardrails & Generation. Those older controls were local browser settings, unlike the APBRA-174 protected, durable tenant settings panel. Reporting cases and their request versions are durable; the separate historical **My Runs** view remains browser-session-only evidence.

## Accepted product experience — planned

Guided and Advanced experiences will share this reasoning and assurance engine. The target starts with conversation and does not require a file or project. A user may describe a source in business language and may later provide qualified schema/data uploads, screenshots or report/sketch references. The UI must state what each item can establish: a design reference is not data truth, and an accepted assumption cannot prove a missing field, source fact or permission.

The target keeps material business decisions understandable and explicit while leaving ordinary supported BI design to AI. Supported alternatives must disclose retained intent, changed scope, assumptions, omissions, limitations and evidence needs; material rescoping requires acceptance before generation. “No dead ends” means a useful supported alternative or authorized-expert continuation, not guaranteed generation.

Later account UX still covers public company registration, authorized BI-expert takeover, optional projects, controlled collaboration, report/output histories, licensing/seat entitlement and usage visibility. APBRA-162 implements only invite-bound membership and private reporting cases. Company membership, a mode, licence or model key does not itself grant private-source, tenant-management, release or deployment authority.

Qualified tenant provider-profile selection and protected credentials now exist in the local/CI foundation. Additional managed/customer deployment qualification, separately consented Azure provisioning where that reference profile is chosen, connected Power BI delivery and optional advanced data-architecture advice remain future capabilities. The current local administration screens do not prove them. The earlier APBRA-149–158 roadmap list is not implementation evidence for this UI.

## Historical Capstone reasoning and compiler workflow

The following GPT-4.1/Capstone pipeline is historical evidence. The current protected case path is described at the top; its local/CI Package B/C substitutes are deterministic and make no provider call.

```text
requirement + parsed schema
→ GPT-4.1 interpretation
→ bounded iterative clarification + immutable raw provenance
→ human confirmation → ConfirmedRequirementContract v2
→ governed in-app RAG
→ original grounded Report Design
→ deterministic obligation coverage, normalization and integrity
→ bounded correction/layout repair when eligible, with full revalidation
→ deterministic guardrails
→ bounded PBIP/PBIR compiler
→ deterministic validation
→ candidate or truthful safe-stop
```

The original AI design is retained. Correction cannot add unconfirmed measures or business meaning. Zero-binding, measure-bound, unknown, ambiguous, unsupported or out-of-capacity designs stop rather than being silently changed. Human Review Required, Unsupported, Out of Scope and technical failure remain distinct.

Changing the request, parsed schema, governed context or interpretation invalidates earlier readiness. Late asynchronous results and duplicate actions cannot confirm or start generation for superseded meaning. A provider interruption preserves the current request, answers and accepted contract where one exists, and exposes a retry for the affected stage without resetting the configured clarification budget. `READY_FOR_CONFIRMATION` proves only that the displayed business meaning is eligible for acceptance; it does not guarantee later Report Design coverage, compilation, runtime compatibility or deployment.

## Run locally

Start the local API and PostgreSQL services as described in the repository README. Copy `.env.example` to ignored `.env.local`; `APBRA_API_URL` is a non-secret local proxy target. Qualified tenant model-provider configuration remains server-side and is not required for case persistence tests. The browser never displays an API key.

```sh
npm ci
npm test
npm run build
npm run dev
```

Vite normally serves `http://127.0.0.1:5173/`. Packages B and C make no paid or live model call. The clearly labelled deterministic local interpretation can proceed directly when the request identifies one observed numeric business measure and one observed comparison category. The Package C adapter maps the resulting typed, confirmed obligations into the existing ReportDesign contract, then runs the existing governed retrieval, normalization, guardrails, compiler and candidate validation. These substitutes prove persistence and control mechanics; successful renamed-field examples do not prove arbitrary business requirements are understood or professionally designed by AI. A qualified real-provider path exists, but these deterministic local/CI substitutes do not establish real-model semantic quality; live provider/model evaluation remains pending.

For a short manual checkpoint, sign in as `member`, create a case without a file, save a message, and add a synthetic CSV or XLSX containing one numeric and one category field. Choose **Prepare understanding**; answer any material clarification, review the labelled local deterministic understanding, and confirm it. Choose **Build report**, inspect the successful version in generation history and download the validated candidate ZIP. Refresh or restart the API and reopen the case to verify the history and download remain. **Build another version** creates a new immutable attempt. Editing the request or adding current-version evidence makes the earlier meaning stale and requires preparation and confirmation before another build.

### Isolated browser tests

Playwright never reuses the manual preview on ports 5173/8000. It starts a test-only web/API pair on ports 15173/18000 and requires a separate disposable PostgreSQL database. Each run downgrades and reapplies migrations only in that explicitly named browser-test database, so never point `APBRA_E2E_DATABASE_URL` at preview or backend-test data. The URL must explicitly name loopback host, port and database and cannot contain connection query options; target-changing libpq environment variables are rejected before either test server starts.

Create the isolated database once inside the committed Compose PostgreSQL service, supply a locally generated test-session value, then run the suite. These commands reuse the already-required local `APBRA_POSTGRES_PASSWORD` environment variable without printing it:

```sh
docker compose exec postgres createdb -U apbra apbra_e2e
export APBRA_E2E_DATABASE_URL="postgresql+psycopg://apbra:${APBRA_POSTGRES_PASSWORD}@127.0.0.1:54321/apbra_e2e"
export APBRA_E2E_SESSION_SECRET="$(openssl rand -hex 32)"
npm run test:e2e
```

Test traces are written outside the repository under `/tmp/apbra-164-playwright-output` by default. Test evidence and generated artifacts also use dedicated `/tmp/apbra-164-e2e-*` roots. Set `APBRA_E2E_OUTPUT_DIR` to another disposable location when needed. These tests may reset only the isolated E2E database; they do not stop, reuse or alter the manual preview database or storage.

## Historical Capstone AI and governed knowledge

The Capstone chat adapter used GPT-4.1 through an Azure AI Foundry/Azure OpenAI-compatible endpoint; its live evidence observed `gpt-4.1-2025-04-14`. Five fictional Markdown standards under `knowledge/` form a 20-chunk heading-aware governed corpus. `text-embedding-3-small` produces 1,536-dimensional embeddings, and an in-memory exact cosine index returns configurable top-k citations.

This is APBRA's in-app retrieval implementation, not the historical S08 Foundry Knowledge store. Uploaded report schemas remain request-specific context and are not indexed as tenant knowledge.

## Compiler, validation and downloads

The bounded compiler supports common cards, bar/column/line charts, tables, slicers, supported measures, simple relationships, multiple pages and tenant theme colours. DAY, MONTH, QUARTER and YEAR trends have genuine representations; WEEK remains unsupported. It does not execute arbitrary model-authored DAX/M/SQL or publish to Power BI.

Strict integrity checks cover measure identity and operands, dependency cycles, visual references and visual cardinality. Pages use a 1,280 × 720 bounded grid; a layout without deterministic capacity stops before compilation.

The current protected local/CI candidate ZIP contains bounded Power BI project content and an exact-version-bound `Delivery-Guide.md`. Historical Capstone runs separately exposed a generated project candidate and lazy-loaded `Report-Deployment-Guide.pdf`. Neither guide nor candidate means Desktop validation, approval or deployment occurred. Production publishing, credentials and gateway configuration remain manual/future capabilities.

## Technical evidence and claim boundary

Expandable technical evidence records run ID, model, latency/tokens, embedding calls, retrieval/citations, original and normalized visual counts, normalization actions, integrity findings, guardrails, compiler, validation and final status.

Implemented locally/CI does not mean production ready. The current protected credential adapter is not hosted managed-secret qualification. Live Entra qualification, hosted multitenancy, durable knowledge ingestion/indexing, managed secret operations, broad compatibility, publishing, reviewer workflow, resilience, monitoring and compliance operations remain future work.

## APBRA-151 first-company onboarding and bounded account lifecycle

The local/CI preview still uses its bounded development identity flow. The implemented sign-in surface now presents only server-supplied qualified profiles, with an Entra External ID-compatible OIDC adapter first under APBRA-172. Real External ID tenant setup and live sign-in qualification have not occurred. Other providers require separate qualification.

After successful provider authentication, the browser does not decide membership or role. The server resolves an existing APBRA membership; an exact invitation can be accepted separately. An identity without either may enter only a company display name and submit **Create Company / Workspace**. The request carries an idempotency key and CSRF token; the server derives the creator from the APBRA session, atomically creates the company, initial `COMPANY_OWNER` membership, Tenant Settings version 1 and audit provenance, and binds the session to the new membership. A lost response can be retried with the same key and name without creating a second company. The browser refreshes its session before showing company authority. Equal email/domain/tenant/group values and a matching display name never prove company ownership or grant access.

Initial Tenant Settings come from the owner-approved **Private Preview Onboarding Tenant Settings Template v1** in [APBRA-151 Jira comment 10406](https://arkitektz.atlassian.net/browse/APBRA-151). The local/test `seed_settings()` fixture and bootstrap environment policy do not supply customer defaults. Automatic model generation begins disabled with no provider profile or credential; the existing Owner/Admin settings controls handle later authorised changes. The template is a bounded private-preview policy, not a universal deployment or commercial plan rule.

The company access panel keeps membership and private-report permissions separate. Owners may change bounded Member/Company Admin roles, while admins cannot alter Company Owner authority and no action may leave a company without an active owner. A signed-in user may edit a safe display name in **My profile**; that does not change the provider-qualified identity binding, company role or resource grants. The server enforces these rules even when the UI hides an action.

The web experience distinguishes **Sign in**, **Join invited company**, and **Create company/workspace**. Enterprise-managed sign-in, Power BI/Fabric connection consent and Azure management consent remain separate journeys. Verified-domain join, SCIM/JIT and additional social providers are later qualified capabilities, not hidden behavior in the current local selector. Browser tests use deterministic identities; they do not qualify public signup, live Entra, production federation or cloud hosting.

No browser state, route visibility or provider claim is the authorization boundary; every protected operation rechecks current server-side APBRA membership/capability/resource authority.
