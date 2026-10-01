# APBRA local API — APBRA-162 foundation through APBRA-164 Package C

This FastAPI service is the local/CI invited-identity and private reporting-case foundation. It uses PostgreSQL 17 for durable state and an OIDC-compatible browser redirect boundary. The bundled issuer and synthetic identities exist only in the `development` and `test` profiles; the hosted profile cannot enable either the issuer or the bootstrap.

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

The browser UI exposes these selectors only on loopback hosts. They do not inject an actor into API requests; the API validates the redirect transaction and provider response, creates a protected APBRA session, and resolves current membership on every protected request.

## OIDC response-issuer policy

Development and test use `APBRA_OIDC_RESPONSE_ISSUER_POLICY=required`: the callback must contain exactly one non-empty `iss` value matching the transaction-bound issuer. A hosted provider can be qualified offline with `single_issuer_compatibility` only when that deployment is configured for one exact trusted upstream issuer and trusted provider metadata does not advertise or require the RFC 9207 authorization-response issuer parameter. This is an explicit provider profile, not an automatic consequence of using the hosted application profile.

Every login transaction is bound to the initiating browser, issuer, client ID, redirect URI, nonce, PKCE verifier, endpoints, trusted key set and response-issuer policy. A relevant configuration change invalidates the transaction. Any callback `iss` that is present must still be unique, non-empty and an exact match. Signed ID-token algorithm, issuer, audience/applicable authorized party, nonce, expiry and subject validation remains mandatory in both policies.

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

All runtime limits and policies are explicit configuration. `APBRA_UPLOAD_POLICY_JSON`, `APBRA_CLARIFICATION_POLICY_JSON`, `APBRA_GENERATION_POLICY_JSON`, both bridge timeouts, bridge paths and the three storage roots must be present. Compose passes these values through from the operator's environment and does not choose product policy. Automatic intelligent analysis/design runs only when `APBRA_AUTOMATIC_GENERATION_ENABLED=true` and one exact accepted `APBRA_MODEL_PROVIDER_PROFILE_JSON` plus `APBRA_MODEL_PROVIDER_API_KEY` are supplied outside source control; those provider variables may be absent when automatic generation is explicitly disabled. Enabling automatic generation without a valid qualified profile and credential fails startup configuration validation. If the provider is disabled or a later provider call fails, the runtime reports intelligent analysis as unavailable; it never substitutes the deterministic test simulator or invented business meaning. `APBRA_TEST_SEMANTIC_SIMULATOR_ENABLED` is accepted only with `APBRA_PROFILE=test` for controlled test harnesses. APBRA never selects a model, deployment, endpoint, region, quota or fallback implicitly. The current compiler accepts at most six visuals per page and only `DAY`, `MONTH`, `QUARTER`, and `YEAR` trend grains; configured policy may be narrower but cannot exceed those validated capabilities.

Before enabling a real provider, verify the selected account's current official entitlement, structured-output support, quota, region, permissions and pricing. Enabling it may incur external-provider charges; the repository does not authorize purchases or paid capacity. A configuration change does not prove model quality, service availability, Power BI Desktop PASS, publishing, gateway credentials or successful deployment.
