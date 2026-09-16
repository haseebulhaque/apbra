#!/usr/bin/env bash
# APBRA-85/APBRA-127: free MIT-licensed CLI, not the separately licensed Action.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
cd "$root"
if [[ "$(git rev-parse --is-shallow-repository)" != "false" ]]; then
  echo 'Incomplete history: fetch-depth must be 0 before scanning.' >&2
  exit 2
fi
if [[ -e .gitleaks.toml || -e .gitleaksignore ]]; then
  echo 'Unreviewed scanner configuration/ignore file: stop for security review.' >&2
  exit 2
fi
unset GITLEAKS_CONFIG GITLEAKS_CONFIG_TOML || true
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
version='8.30.1'
archive="gitleaks_${version}_linux_x64.tar.gz"
expected='551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb'
curl --fail --silent --show-error --location --retry 2 --max-time 120 \
  "https://github.com/gitleaks/gitleaks/releases/download/v${version}/${archive}" \
  --output "$work/$archive"
printf '%s  %s\n' "$expected" "$work/$archive" | sha256sum --check --status
tar -xzf "$work/$archive" -C "$work" gitleaks
scanner="$work/gitleaks"
"$scanner" version
mkdir -p "$work/selftest" "$work/current"
python - "$work/selftest" <<'PY'
from pathlib import Path
import sys
# Never a usable token: constructed solely for an offline detector self-test.
(Path(sys.argv[1]) / 'fixture.txt').write_text(
    'gh' + 'p_' + 'aB3dE6gH9jK2mN5pQ8sT1vW4yZ7cF0iL3oR6', encoding='utf-8')
PY
set +e
"$scanner" dir "$work/selftest" --redact=100 --no-banner --log-level error \
  --ignore-gitleaks-allow --exit-code 1 >"$work/selftest.log" 2>&1
rc=$?
set -e
if [[ "$rc" -ne 1 ]]; then
  echo 'Detector negative self-test did not detect the synthetic token.' >&2
  exit 2
fi
printf 'Synthetic ordinary fixture\n' > "$work/selftest/fixture.txt"
"$scanner" dir "$work/selftest" --redact=100 --no-banner --log-level error \
  --ignore-gitleaks-allow
# Archive contains the exact tracked HEAD tree, not credentials from .git/config
# or unrelated local environments. History scans every fetched ref, not forks.
git archive HEAD | tar -xf - -C "$work/current"
"$scanner" dir "$work/current" --redact=100 --no-banner --log-level error \
  --ignore-gitleaks-allow --max-decode-depth 2 --max-archive-depth 1
"$scanner" git "$root" --log-opts='--all' --redact=100 --no-banner --log-level error \
  --ignore-gitleaks-allow --max-decode-depth 2 --max-archive-depth 1
printf 'Secret scan PASS: current tracked tree and fetched Git history; '
printf 'commits=%s, tracked_files=%s\n' "$(git rev-list --count --all)" "$(git ls-files | wc -l)"
printf 'No findings in configured detector scope. No native-alert, fork, cache or credential-validity claim.\n'
