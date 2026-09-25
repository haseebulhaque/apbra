# APBRA local API — APBRA-162 foundation + APBRA-163 Package B

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

The persistent Compose volumes are `apbra_postgres_data` and `apbra_evidence_data`. A normal stop/restart retains cases, request versions, conversation, qualified evidence, interpretations and confirmed contracts:

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
uv --directory apps/api run --frozen alembic upgrade head
uv --directory apps/api run --frozen pytest
```

APBRA-163 adds only private local/CI CSV/XLSX evidence storage and durable business acceptance. Its local deterministic interpretation uses the canonical TypeScript semantic engine and is clearly labelled as no-model simulation. The substitute exercises a deliberately narrow field-selection and SUM-by-category comparison path so persistence, evidence handling and exact acceptance can be tested; renamed or unrelated examples do not establish general-purpose semantic interpretation. Real AI integration and semantic-quality evaluation remain pending. It does not add report-generation orchestration, candidate downloads, projects, expert takeover, billing, live Entra qualification, Azure provisioning, or hosted deployment.
