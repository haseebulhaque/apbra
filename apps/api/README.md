# APBRA local API — protected case and tenant configuration

APBRA-174 adds immutable per-company Tenant Settings versions. The current version, not deployment environment variables, governs clarification, upload, generation, provider selection, branding, terminology and guide behavior during ordinary operations. Deployment values are a development/test first-version seed only; they do not override an existing tenant. The initial clarification settings are two rounds per cycle and ten rounds overall. Owner/Admin updates and restores create audited new versions with an expected-version concurrency check; members, experts without admin role, foreign-company actors and revoked actors cannot administer them.

The `GET/PUT /api/tenant-settings` and history/restore endpoints expose validated non-secret settings. A separate credential-replacement endpoint writes an encrypted tenant secret and returns only masked status/reference. The deployment-supplied `APBRA_TENANT_SECRET_KEYRING_JSON` defines the local AES-GCM adapter's active key and prior keys for rotation; it must remain outside source control and is not a tenant settings field. A managed secret backend could replace this adapter at the same provider-neutral boundary. A tenant may run without a provider/keyring when automatic generation is disabled. Enabling a provider requires an explicit qualified profile, protected credential and available keyring; a missing/invalid combination fails closed. Replacing or revoking a credential does not reveal plaintext or silently choose another provider.

An accepted interpretation binds the material settings version. Model-generated questions may be optional or absent; user-requested Clarify/Enhance creates durable bounded cycles. An otherwise ready interpretation can be accepted with optional questions unanswered. Supported partial scope and omissions are disclosed, while mandatory blockers stop. Automatic ReportDesign remains untrusted until deterministic validation. Final candidate ZIPs include an exact-version-bound `Delivery-Guide.md`; the guide is not deployment or Desktop-runtime evidence.

This FastAPI service is the local/CI private reporting-case foundation. It uses PostgreSQL 17 for durable state and a provider-neutral APBRA identity/session boundary. The bundled issuer and synthetic identities exist only in the `development` and `test` profiles; the hosted profile cannot enable either the issuer or the bootstrap. APBRA-172 implements an Entra External ID-compatible OIDC profile and deterministic qualification tests; a real External ID sign-in has not yet run.

Authentication establishes an external identity. Every protected operation separately rechecks the active APBRA membership and private-case grant held in PostgreSQL. Client-supplied company or role values are never authorization inputs.

## Local stack

Prerequisites are Docker Desktop with Compose, Node.js 24, and a shell with `openssl`. Run from the repository root. Generate values in the current shell; do not save or commit them.

```sh
export APBRA_POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export APBRA_SESSION_SECRET="$(openssl rand -hex 32)"
docker compose up --build postgres api
```

The API applies the Alembic migration, runs the development bootstrap idempotently, and listens only on `http://127.0.0.1:8000`. Verify both the process and its database dependency:

```sh
curl --fail http://127.0.0.1:8000/api/health
```

Expected response:

```json
{"status":"ok","database":"ok"}
```

The persistent Compose volumes are `apbra_postgres_data`, `apbra_evidence_data`, `apbra_reference_data` and `apbra_artifact_data`. A normal stop/restart retains reports, immutable original and revised requests, requirements, qualified data, reference material, interpretations, confirmed contracts, automatic design attempts, generation attempts and validated candidates:

```sh
docker compose stop
docker compose start
```

`docker compose down` also retains the named volume. Do not add `--volumes` unless deliberately deleting synthetic local data.

## Synthetic identities

The local issuer offers four selectors through the normal authorization-code + PKCE redirect path:

- `owner`: active owner in Acme Synthetic; can issue invitations.
- `member`: active member in Acme Synthetic; has no automatic access to the owner's private cases.
- `uninvited`: authenticated identity without membership; may accept an invitation addressed to its exact subject.
- `foreign`: owner in Beta Synthetic; cannot discover Acme private cases.

`GET /api/auth/providers` advertises safe labels and these selectors only when the server runs in development/test. Browser hostname is not the control. Selectors do not inject an actor into API requests; the API validates the redirect transaction and provider response, creates a protected APBRA session, and resolves current membership on every protected request.

## Qualified hosted identity profile

Deployment-owned `APBRA_OIDC_PROFILES_JSON` is an exact list of qualified profiles. Each entry has a stable `profile_id`, truthful `display_label`, `provider_kind` (`ENTRA_EXTERNAL_ID` in this first package), exact `issuer`, HTTPS `discovery_url`, application `client_id`, minimal `scopes` (`openid`, `profile`, optionally `email`), `enabled`, optional server-side `credential_env` reference and any separately qualified additional HTTPS endpoint origins. A Company Owner, Tenant Settings value, browser parameter, token header or invitation cannot add an issuer or JWKS trust root. The old standalone `APBRA_OIDC_ISSUER`/static `APBRA_OIDC_JWKS_JSON` fields do not qualify a hosted profile and cannot start hosted mode by themselves.

Use the actual External ID external-tenant authority and discovery document, not an invented generic Microsoft issuer. The server checks exact metadata issuer, allowed authorization/token/JWKS endpoints, RS256 keys and bounded metadata/key caches; an unknown key triggers one trusted refresh. It sends authorization code plus PKCE S256, state and nonce, and validates the signed ID token before binding `profile_id` + issuer + subject. Never use email, UPN, domain, Entra tenant or IdP group as membership authority. No Graph, Power BI/Fabric or Azure Resource Manager scopes are requested for basic login. A protected deployment credential may be injected into the referenced environment variable outside source control; do not put a real secret in this repository or in the profile JSON. Certificate/private-key client authentication and managed-secret operations need separate qualification if required by the chosen live deployment.

`GET /api/auth/login?profile_id=...` selects only an enabled server-qualified profile. `GET /api/auth/callback` consumes its browser-bound one-use transaction and establishes a new opaque APBRA session; provider tokens are neither returned to browser code nor retained. `GET /api/auth/session` returns only safe APBRA identity, CSRF, membership and company-selection state, with no provider subject. `POST /api/auth/select-company` accepts only an existing active membership of the authenticated identity. `POST /api/auth/logout` revokes the local APBRA session and clears the HttpOnly cookie; it does not guarantee sign-out from the external provider or revoke that provider's browser session. Mutating APIs require the session-bound CSRF token and protected operations recheck current membership and exact private-resource grants. A no-membership session reports `COMPANY_CREATION_AVAILABLE`; APBRA-151 company creation and first-owner bootstrap are not implemented here.

The migration labels older identities and sessions `legacy-unqualified` without guessing an Entra mapping. Only the exact local/test issuer may reuse a legacy identity during deterministic bootstrap compatibility. Existing session rows expire under their existing TTL and continue to require current identity, membership and resource checks; there is no blanket session-revocation migration. Live Entra configuration, credentials, actual user flow, hosted infrastructure and provider runtime behavior remain unverified until separately approved and exercised.

## OIDC response-issuer policy

Development and test use `APBRA_OIDC_RESPONSE_ISSUER_POLICY=required`: the callback must contain exactly one non-empty `iss` value matching the transaction-bound issuer. A hosted provider can be qualified offline with `single_issuer_compatibility` only when that deployment is configured for one exact trusted upstream issuer and trusted provider metadata does not advertise or require the RFC 9207 authorization-response issuer parameter. This is an explicit provider profile, not an automatic consequence of using the hosted application profile.

Every login transaction is bound to the initiating browser, qualified profile, issuer, client ID, redirect URI, nonce, PKCE verifier, trusted discovery configuration and response-issuer policy. A relevant configuration change invalidates the transaction. Any callback `iss` that is present must still be unique, non-empty and an exact match. Signed ID-token algorithm, issuer, audience/applicable authorized party, nonce, expiry and subject validation remains mandatory in both policies. Compatibility mode is accepted only when exactly one qualified profile is enabled.

The bounded compatibility path has deterministic offline coverage using controlled provider metadata, signed test tokens and a substituted token transport through the real callback. It is not live Microsoft Entra External ID interoperability evidence, and it does not authorize a hosted service, real credentials or cloud spend.

## Backend verification

Use the committed lock and a real PostgreSQL 17 database. SQLite and in-memory persistence are not substitutes for these tests.

Backend tests reset only a dedicated loopback database named `apbra_test`. It must be distinct from both the manual preview database (`apbra`) and the browser database (`apbra_e2e`). Target-changing libpq environment variables and connection query options are rejected before Alembic can connect or run DDL.

```sh
docker compose exec postgres createdb -U apbra apbra_test
export APBRA_TEST_DATABASE_URL="postgresql+psycopg://apbra:${APBRA_POSTGRES_PASSWORD}@127.0.0.1:54321/apbra_test"
uv --directory apps/api lock --check
uv --directory apps/api sync --frozen --python 3.13
uv --directory apps/api run --frozen ruff check .
uv --directory apps/api run --frozen mypy
APBRA_DATABASE_URL="$APBRA_TEST_DATABASE_URL" uv --directory apps/api run --frozen alembic upgrade head
uv --directory apps/api run --frozen pytest
```

APBRA-171 adds a provider-neutral, server-side structured-output boundary for requirement analysis and report-design proposals. The browser never receives provider configuration or credentials. A provider result is untrusted input: APBRA persists an immutable attempt, validates the exact current request, requirements, qualified data and reference digests, runs the canonical TypeScript contract, normalization, semantic-coverage, guardrail, compiler and candidate-validation path, and makes a design build-eligible only after every deterministic check passes. Reference PNG/JPEG files are stored separately from calculation data and remain explicitly `NOT_INTERPRETED` unless a future accepted capability profile and implementation proves otherwise.

Bridge timeouts, bridge paths and storage roots remain explicit deployment/runtime inputs. `APBRA_UPLOAD_POLICY_JSON`, `APBRA_CLARIFICATION_POLICY_JSON` and `APBRA_GENERATION_POLICY_JSON` are required only to seed a first development/test tenant version; subsequent operations use the persisted effective version. Compose passes seed values through from the operator's environment and does not choose product policy. `APBRA_MODEL_PROVIDER_PROFILE_JSON` and `APBRA_MODEL_PROVIDER_API_KEY` are legacy seed inputs when expressly configured, never production defaults; an enabled tenant instead needs its explicit qualified profile and protected tenant credential. The deployment-owned `APBRA_QUALIFIED_PROVIDER_PROFILES_JSON` is an optional JSON array of explicitly qualified provider profiles, not tenant policy or a provider default. Owner/Admin may select only an entry in this catalogue and may lower, but not exceed, its approved operational budgets; profile identity and verified capabilities cannot be self-asserted. A missing catalogue permits disabled generation but no profile selection or enabled seed. Removing/changing an entry makes incompatible active profiles unavailable for new model calls until a qualified profile is selected. If the provider is disabled or a later call fails, intelligent analysis reports unavailable; it never substitutes the deterministic test simulator or invented meaning. `APBRA_TEST_SEMANTIC_SIMULATOR_ENABLED` is accepted only with `APBRA_PROFILE=test` for controlled harnesses. APBRA never selects a model, deployment, endpoint, region, quota or fallback implicitly. The compiler accepts at most six visuals per page and only `DAY`, `MONTH`, `QUARTER`, and `YEAR` trend grains; tenant policy may be narrower but cannot exceed those validated capabilities.

Before enabling a real provider, verify the selected account's current official entitlement, structured-output support, quota, region, permissions and pricing. Enabling it may incur external-provider charges; the repository does not authorize purchases or paid capacity. A configuration change does not prove model quality, service availability, Power BI Desktop PASS, publishing, gateway credentials or successful deployment.
