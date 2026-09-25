FROM node:22.22.0-bookworm-slim AS semantic
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --ignore-scripts
COPY apps/web/scripts ./scripts
COPY apps/web/src ./src
RUN APBRA_SEMANTIC_BRIDGE_OUT=/runtime/apbra-semantic-bridge.mjs npm run build:semantic-bridge

FROM python:3.13-slim
WORKDIR /app
COPY --from=semantic /usr/local/bin/node /usr/local/bin/node
COPY --from=semantic /runtime/apbra-semantic-bridge.mjs /app/runtime/apbra-semantic-bridge.mjs
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN pip install --no-cache-dir uv==0.12.3 && uv sync --frozen --no-dev --no-install-project
COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
COPY apps/api/src ./src
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "apbra_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
