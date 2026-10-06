#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
work="$(mktemp -d)"
suffix="$$"
network="apbra-173b-smoke-${suffix}"
postgres="apbra-173b-pg-${suffix}"
api="apbra-173b-api-${suffix}"
image="apbra-173b-smoke:${suffix}"
root_marker="$(mktemp "$root/.apbra-173b-private-marker-XXXXXX")"
nested_marker="$(mktemp "$root/apps/api/src/.env.apbra-173b-private-marker-XXXXXX")"
cleanup() {
  docker rm -f "$api" "$postgres" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
  docker image rm "$image" >/dev/null 2>&1 || true
  rm -f "$root_marker" "$nested_marker"
  rm -rf "$work"
}
trap cleanup EXIT

printf 'synthetic private marker\n' > "$root_marker"
printf 'synthetic private marker\n' > "$nested_marker"
docker build -f apps/api/Dockerfile --target context-audit --output "type=local,dest=$work/context" . >/dev/null
test ! -e "$work/context/context/$(basename "$root_marker")"
test ! -e "$work/context/context/apps/api/src/$(basename "$nested_marker")"
test ! -e "$work/context/context/apps/api/.mypy_cache"
test ! -e "$work/context/context/apps/api/tests"
test ! -e "$work/context/context/apps/web/e2e"
test ! -e "$work/context/context/tests/bootstrap/evaluation"
test -f "$work/context/context/apps/api/src/apbra_api/main.py"
test -f "$work/context/context/apps/web/index.html"
docker build -f apps/api/Dockerfile -t "$image" . >/dev/null
docker run --rm --entrypoint /bin/sh "$image" -ec \
  'test -f /app/web-dist/index.html && test -f /app/web-dist/.vite/manifest.json && test -f /app/runtime/apbra-generation-bridge.mjs && test ! -e /web && test ! -e /tests && test ! -e /app/web-dist/src && test ! -e /app/web-dist/.env'

docker network create "$network" >/dev/null
docker run -d --name "$postgres" --network "$network" --network-alias pg \
  -e POSTGRES_DB=apbra -e POSTGRES_USER=postgres -e POSTGRES_HOST_AUTH_METHOD=trust \
  postgres:17.11-bookworm >/dev/null
ready=0
for _ in $(seq 1 40); do
  if docker exec "$postgres" pg_isready -U postgres -d apbra >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
test "$ready" = 1

common=(--network "$network" -e APBRA_PROFILE=test \
  -e APBRA_DATABASE_URL=postgresql+psycopg://postgres@pg:5432/apbra \
  -e APBRA_SESSION_SECRET=ci-only-hosted-image-smoke-session-material \
  -e APBRA_BOOTSTRAP_ENABLED=false \
  -e APBRA_PUBLIC_ORIGIN=http://127.0.0.1:8000 \
  -e APBRA_API_ORIGIN=http://127.0.0.1:8000)
docker run --rm "${common[@]}" "$image" alembic upgrade head >"$work/migration-a.log" 2>&1 &
first=$!
docker run --rm "${common[@]}" "$image" alembic upgrade head >"$work/migration-b.log" 2>&1 &
second=$!
wait "$first" || { cat "$work/migration-a.log" >&2; exit 1; }
wait "$second" || { cat "$work/migration-b.log" >&2; exit 1; }
before="$(docker exec "$postgres" psql -U postgres -d apbra -Atc 'select version_num from alembic_version')"
docker run -d --name "$api" "${common[@]}" "$image" >/dev/null
ready=0
for _ in $(seq 1 40); do
  if docker exec "$api" python -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status == 200" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
test "$ready" = 1
after="$(docker exec "$postgres" psql -U postgres -d apbra -Atc 'select version_num from alembic_version')"
test "$before" = "$after"
test "$(docker exec "$postgres" psql -U postgres -d apbra -Atc 'select count(*) from companies')" = 0
docker exec -i "$api" python - <<'PY'
import re
import urllib.error
import urllib.request

base = 'http://127.0.0.1:8000'
def request(path, method='GET'):
    try:
        return urllib.request.urlopen(urllib.request.Request(base + path, method=method), timeout=3)
    except urllib.error.HTTPError as error:
        return error

for path in ('/', '/invite'):
    shell = request(path)
    assert shell.status == 200
    assert shell.headers['Cache-Control'] == 'no-cache, must-revalidate'
    html = shell.read().decode()
    asset = re.search(r'/assets/[A-Za-z0-9_.-]+\.(?:js|css)', html)
    assert asset is not None
    built = request(asset.group())
    assert built.status == 200
    assert built.headers['Cache-Control'] == 'public, max-age=31536000, immutable'
    assert request(path, 'HEAD').status == 200
assert request('/api/health').status == 200
missing = request('/api/not-a-route')
assert missing.status == 404 and 'text/html' not in missing.headers.get('content-type', '')
assert request('/api/health', 'POST').status == 405
for path in ('/unknown', '/assets/unknown-AbCd1234.js', '/assets/../private', '/.env', '/src/main.tsx', '/evidence/private'):
    assert request(path).status == 404, path
PY
printf 'PASS: exact hosted image, migration-before-start, static/API/private boundaries\n'
