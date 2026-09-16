# APBRA-IMPL-0.1 source baseline

Authority: [05.07 v1](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/4653067) and [14.07 v1](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/4751362). Their source status is Proposed. The user selected the direction and authorized this isolated repository bootstrap; these files do not fabricate final approval or verified dependencies.

| ADR | Selected refinement | Outstanding evidence |
| --- | --- | --- |
| 055 | Python 3.13/FastAPI/Pydantic; React/TypeScript/Vite | Actual product lockfiles and builds under APBRA-27 |
| 056 | PostgreSQL 17/pgvector, eligible lexical and exact-vector fusion | Database isolation, retrieval and pool-reuse tests |
| 057 | Persisted jobs/outbox/leases plus bounded LangGraph | Recovery, fencing, idempotency and budget evidence |
| 058 | Azure OpenAI first; synthetic-data environment profiles | Model/embedding deployment, quota, processing, Entra and spend authorization |
| 059 | Narrow Import PBIP/PBIR/TMDL output | Exact Desktop/schema/template and runtime oracle evidence |
| 060 | Task-bound, truthful engineering provenance | Trusted CI, private branch controls and independent review topology |

Read the source for candidate minor versions and full limits. Do not promote a candidate version to an installed dependency merely by copying it into a README. The only resolved packages in this branch are the isolated engineering-check tooling listed in requirements-bootstrap.txt, not the product stack.

Original ADR-001..054 remain intact. Repository source mapping refines paths, not product intent. Any discrepancy is an escalation; the newest document is not automatically the authority.

## Stage gates

G0: record scope/architecture acceptance. G1: product lock/bootstrap verification. G2: actual provider, identity and GitHub control feasibility. G3: Power BI compatibility. G4: implemented tested reviewed features. G5: claim-to-evidence review.

G2/G3 do not stop safe documentation and deterministic engineering-fixture work. They do stop claims of live integration and implementation dependent on invented capabilities. No production deployment, paid upgrade or real customer-data processing is authorized by this bootstrap.
