# APBRA implementation and product baseline

This file separates current implementation evidence, accepted product/architecture intent and historical proposals. They must not be collapsed into one claim.

| Layer | Current authority | Meaning |
| --- | --- | --- |
| Accepted product and identity intent | Current Confluence product/requirements/identity pages, including 10.03 v4 and 02.01 v7 | Target product behavior and architecture; not proof of runtime implementation |
| Verified implementation | GitHub `main` plus exact revision-bound tests/reviews | Bounded local/CI FastAPI/PostgreSQL/React product foundation through the merged MVP packages |
| Historical Capstone evidence | Exact Capstone runs and retained documentation | Bounded historical demonstration evidence only |
| Historical architecture proposals | `APBRA-IMPL-0.1` and retained ADR/proposal pages | Traceability only; not current implementation authority |

## Current verified implementation

At the APBRA-176 documentation base, verified GitHub `main` is `9b1569f2b955aab523f4bacbdcefed2d582ebe0a`, the manual merge of APBRA-176 registration PR #79. The registration itself changes governance only.

The current bounded local/CI product includes:

- React/Vite business-user application surfaces;
- FastAPI and PostgreSQL 17;
- server-derived invited identity, active membership and private-case/resource checks;
- durable request, conversation, evidence, accepted-meaning and generation history;
- protected evidence/candidate storage in the local/CI profile;
- versioned Tenant Settings with Owner/Admin editing/history/restore;
- protected tenant credential references and qualified-provider selection;
- model-led optional clarification and supported partial-scope disclosure;
- qualified provider-driven ReportDesign in the implemented APBRA-171/174 path, with deterministic local substitutes used separately in CI;
- deterministic PBIP/PBIR/TMDL generation/validation, namespace-safety handling and version-bound Delivery Guide output;
- responsive business-user report creation UX.

This evidence does **not** prove Power BI Desktop open/render, publishing, gateway configuration, public self-service signup, live Entra sign-in on current main, production multi-tenancy, managed-secret operations, production backup/recovery, central entitlement runtime or public SaaS readiness.

## Accepted self-service onboarding and identity target

The 2 October 2026 owner decision refines PC26-FR-008 and the MVP-1 direction.

APBRA's identity architecture is provider-neutral. A qualified provider authenticates the person; APBRA binds the external identity using stable validated provider identifiers such as issuer plus subject/object identity and then applies APBRA-owned company membership, capabilities and private-resource grants.

Microsoft Entra External ID is the first qualified live provider planned under APBRA-172. It is not the core identity model and does not make Azure a mandatory deployment dependency. Additional providers such as Google, Apple or other approved OIDC/federation profiles require separate qualification.

The target onboarding journey is:

1. authenticate through an approved provider;
2. resolve an existing active APBRA company membership;
3. otherwise resolve an eligible invitation;
4. otherwise offer **Create Company / Workspace**;
5. create the company and the creator's initial `COMPANY_OWNER` membership in one server-authoritative, auditable and idempotent transaction.

Authentication is not company membership. Company membership is not access to every private report/case. Neither authentication nor membership grants Power BI/Fabric consent, Azure management authority or commercial entitlement. Email/domain/UPN/external-tenant/IdP-group values do not silently create company authority, and equal email addresses from different providers do not silently merge identities.

Verified-domain auto-join, enterprise SSO and SCIM/JIT are later opt-in integration features and may require customer IT/admin involvement. Basic self-service APBRA signup/sign-in must not require APBRA to configure every customer's external directory.

APBRA-151 owns self-service company lifecycle implementation. APBRA-172 owns the provider-neutral SSO/session implementation with Entra External ID first. APBRA-173 owns private hosted-preview qualification. APBRA-176 is documentation reconciliation only.

## Accepted deployment and entitlement direction

APBRA Cloud, APBRA Dedicated and qualified APBRA Private / On-Premises are accepted target deployment profiles. A future air-gapped profile requires explicit qualification. Azure is a reference/private-preview choice, not a mandatory core dependency.

`deployment_id` identifies an installation/licensing lifecycle. `tenant_id` identifies an APBRA company security/governance domain. A central commercial/control plane may hold only minimised deployment/subscription/entitlement metadata; customer users, mappings, Tenant Settings, credentials, evidence, prompts, accepted requirements, reports, guides, audit/history and operational content remain in the selected customer data plane.

Commercial availability follows **Subscription → versioned Entitlements → stable Capabilities**. Effective capability is the intersection of installed/qualified platform support, entitlement, Tenant Settings, user/application permission, resource permission and current security/validation/governance. Paid access cannot bypass authorization, isolation, target validity, deterministic validation or release/deployment authority. Core product logic must not branch on marketing plan names.

## Reporting-platform direction

Power BI PBIP/PBIR/TMDL is the current bounded output adapter. Future APBRA Report Definition (ARD), native rendering/live canvas and other adapters are separate architecture/implementation work. PBIX generation, universal Power BI compatibility and connected publishing are not established by the current implementation.

NO HARDCODING applies to customer/business/deployment/provider/commercial choices. Stable schemas, protocols, security invariants, supported capability contracts and deterministic validation rules may remain fixed software contracts.

## Historical APBRA-IMPL-0.1 proposal

The historical proposal recorded candidate refinements such as Python/FastAPI/Pydantic, PostgreSQL/pgvector, durable orchestration, Azure-hosted provider profiles, bounded PBIP/PBIR/TMDL output and task-bound engineering provenance. Some technologies are now used in the bounded product, but that does not retroactively make the old proposal the current authority or prove every proposed production characteristic.

Original ADR/proposal material remains historical source evidence. A provider, region, service, quota or product name appearing in old prose is not an installed, entitled or verified dependency.

## Decision and evidence gates

Future implementation must still establish fresh Jira scope, current Confluence source/decision versions, exact base/branch/path authority, relevant security/privacy constraints, dependency/provider feasibility, tests, hosted CI, independent exact-head review and Haseeb's manual merge.

Documentation may describe a target; it may not promote that target to Implemented, Tested, Verified or Production Ready. No production deployment, paid upgrade, customer-data processing, Power BI/Fabric consent, Azure management permission or customer-directory authority is granted by this baseline.
