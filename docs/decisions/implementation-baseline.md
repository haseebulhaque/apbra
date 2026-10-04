# APBRA implementation and product baseline

This file separates current implementation evidence, accepted product/architecture intent and historical proposals. They must not be collapsed into one claim.

| Layer | Current authority | Meaning |
| --- | --- | --- |
| Accepted product and identity intent | Current Confluence product/requirements/identity pages, including 10.03 v7 and 02.01 v9 | Target product behavior and architecture; implementation claims need revision-bound evidence |
| Verified implementation | GitHub `main` plus exact revision-bound tests/reviews | Bounded local/CI FastAPI/PostgreSQL/React product foundation through the merged MVP packages |
| Historical Capstone evidence | Exact Capstone runs and retained documentation | Bounded historical demonstration evidence only |
| Historical architecture proposals | `APBRA-IMPL-0.1` and retained ADR/proposal pages | Traceability only; not current implementation authority |

## Current verified implementation

At the APBRA-177 documentation implementation base, verified GitHub `main` is `82736070eea8dcdbf9ce8ccc9f5e94489a1be8af`, Haseeb’s manual merge of APBRA-177 registration PR #91. The earlier APBRA-176 base `9b1569f2b955aab523f4bacbdcefed2d582ebe0a` and PR #79 remain historical governance evidence. This documentation implementation changes no runtime behavior.

The current bounded local/CI product includes:

- React/Vite business-user application surfaces;
- FastAPI and PostgreSQL 17;
- provider-neutral OIDC/application sessions with an Entra External ID-compatible first profile, APBRA-151 first-company creation and initial `COMPANY_OWNER`, multi-company invitation acceptance, bounded membership/profile lifecycle and exact private-case/resource checks;
- durable request, conversation, evidence, accepted-meaning and generation history;
- APBRA-173A portable protected-content contract with secure local and deterministic alternate adapter evidence for protected evidence/reference/candidate bytes;
- versioned Tenant Settings with Owner/Admin editing/history/restore;
- protected tenant credential references and qualified-provider selection;
- model-led optional clarification and supported partial-scope disclosure;
- qualified provider-driven ReportDesign in the implemented APBRA-171/174 path, with deterministic local substitutes used separately in CI;
- deterministic PBIP/PBIR/TMDL generation/validation, namespace-safety handling and version-bound Delivery Guide output;
- responsive business-user report creation UX.

This evidence does **not** prove Power BI Desktop open/render, publishing, gateway configuration, public production signup, live Entra sign-in, production multi-tenancy, managed-secret operations, production backup/recovery, central entitlement runtime or public SaaS readiness.

## Implemented local/CI self-service onboarding and open live identity gates

The 2 October 2026 owner decision refines PC26-FR-008 and the MVP-1 direction.

APBRA's identity architecture is provider-neutral. A qualified provider authenticates the person; APBRA binds the external identity using stable validated provider identifiers such as issuer plus subject/object identity and then applies APBRA-owned company membership, capabilities and private-resource grants.

Microsoft Entra External ID is the first live provider planned for qualification after the merged APBRA-172 foundation. It is not the core identity model and does not make Azure a mandatory deployment dependency. Additional providers such as Google, Apple or other approved OIDC/federation profiles require separate qualification.

The bounded local/CI onboarding journey is:

1. authenticate through an approved provider;
2. resolve an existing active APBRA company membership;
3. otherwise resolve an eligible invitation;
4. otherwise offer **Create Company / Workspace**;
5. create the company and the creator's initial `COMPANY_OWNER` membership in one server-authoritative, auditable and idempotent transaction.

Authentication is not company membership. Company membership is not access to every private report/case. Neither authentication nor membership grants Power BI/Fabric consent, Azure management authority or commercial entitlement. Email/domain/UPN/external-tenant/IdP-group values do not silently create company authority, and equal email addresses from different providers do not silently merge identities.

Verified-domain auto-join, enterprise SSO and SCIM/JIT are later opt-in integration features and may require customer IT/admin involvement. Basic self-service APBRA signup/sign-in must not require APBRA to configure every customer's external directory.

APBRA-151 and APBRA-172 are merged bounded implementations; APBRA-173A is the merged portable storage foundation, not hosted Blob or recovery. APBRA-173 owns private hosted-preview qualification. APBRA-177 reconciles repository documentation only.

## Accepted deployment and entitlement direction

APBRA Cloud, APBRA Dedicated and qualified APBRA Private / On-Premises are accepted target deployment profiles. A future air-gapped profile requires explicit qualification. Azure Container Apps/Job and related managed services are the owner-selected reference preview direction, not a mandatory core dependency or deployed service. AWS/other/private profiles require separate qualification.

`deployment_id` identifies an installation/licensing lifecycle. `tenant_id` identifies an APBRA company security/governance domain. A central commercial/control plane may hold only minimised deployment/subscription/entitlement metadata; customer users, mappings, Tenant Settings, credentials, evidence, prompts, accepted requirements, reports, guides, audit/history and operational content remain in the selected customer data plane.

Commercial availability follows **Subscription → versioned Entitlements → stable Capabilities**. Effective capability is the intersection of installed/qualified platform support, entitlement, Tenant Settings, user/application permission, resource permission and current security/validation/governance. Paid access cannot bypass authorization, isolation, target validity, deterministic validation or release/deployment authority. Core product logic must not branch on marketing plan names.

Qualified model/provider choices and protected credential references are bounded, versioned, validated and permissioned Tenant Settings. Broader theme, layout, branding and report standards remain phased configurable product direction; fixed security and compiler contracts remain software invariants.

## Reporting-platform direction

Power BI PBIP/PBIR/TMDL is the current bounded output adapter. Future APBRA Report Definition (ARD), native rendering/live canvas and other adapters are separate architecture/implementation work. PBIX generation, universal Power BI compatibility and connected publishing are not established by the current implementation.

NO HARDCODING applies to customer/business/deployment/provider/commercial choices. Stable schemas, protocols, security invariants, supported capability contracts and deterministic validation rules may remain fixed software contracts.

## Historical APBRA-IMPL-0.1 proposal

The historical proposal recorded candidate refinements such as Python/FastAPI/Pydantic, PostgreSQL/pgvector, durable orchestration, Azure-hosted provider profiles, bounded PBIP/PBIR/TMDL output and task-bound engineering provenance. Some technologies are now used in the bounded product, but that does not retroactively make the old proposal the current authority or prove every proposed production characteristic.

Original ADR/proposal material remains historical source evidence. A provider, region, service, quota or product name appearing in old prose is not an installed, entitled or verified dependency.

## Decision and evidence gates

Future implementation must still establish fresh Jira scope, current Confluence source/decision versions, exact base/branch/path authority, relevant security/privacy constraints, dependency/provider feasibility, tests, hosted CI, independent exact-head review and Haseeb's manual merge.

Documentation may describe a target; it may not promote that target to Implemented, Tested, Verified or Production Ready. No production deployment, paid upgrade, customer-data processing, Power BI/Fabric consent, Azure management permission or customer-directory authority is granted by this baseline.
