"""Owner-operated local recovery; never reads deployment bootstrap implicitly.

Run only after separate owner approval of real maintenance. Generate and retain
replacement material personally in secure local storage, never in chat. Keep a
verified database/protected-file backup and both old/new keyrings. Stop the preview
API, disable terminal recording, and use a private local TTY. This helper accepts
full keyrings through hidden prompts, verifies retained mappings and a distinct
active key, then performs a write/readback dry-run that rolls back. A second exact
confirmation permits atomic commit against that same snapshot. It does not update
configuration, restart services, revoke credentials or make provider calls.

After confirmed commit, personally activate the same tested replacement keyring
in local deployment configuration before restarting the API. Keep old keys for
backup recovery; do not remove them. Verify saved data/references and authentication
without a provider call. Before-commit failure rolls back; a connection failure
at commit can leave outcome uncertain, so inspect non-secret state locally before
restarting or retrying. Restore the coordinated backup/keyring pair only under
separate recovery approval. This is development/test maintenance, not a hosted
production recovery qualification.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import warnings

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from .domain import ConfigurationUnavailable
from .tenant_secrets import AesGcmTenantCredentialStore, rekey_tenant_credentials

_TARGET_ENV = (
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSYSCONFDIR",
    "PGOPTIONS",
    "PGPASSWORD",
    "PGPASSFILE",
)


def qualified_local_target(raw_url: str, profile: str) -> tuple[URL, str]:
    """Reject ambiguous libpq targets before any connection is attempted."""
    url = make_url(raw_url)
    if (
        profile not in {"development", "test"}
        or url.drivername != "postgresql+psycopg"
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.port is None
        or not 1 <= url.port <= 65535
        or url.database is None
        or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,62}", url.database) is None
        or url.query
        or any(os.environ.get(name) for name in _TARGET_ENV)
    ):
        raise ConfigurationUnavailable()
    return url, f"{url.host}:{url.port}/{url.database}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    if sys.argv[1:] not in ([], ["--help"], ["-h"]):
        print("No arguments are accepted except --help; no connection attempted.", file=sys.stderr)
        return 2
    parser.parse_args()  # Never echo unknown arguments that could contain secrets.
    if not (sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty()):
        print(
            "Recovery requires a private interactive TTY; no connection attempted.", file=sys.stderr
        )
        return 2
    engine = None
    try:
        profile = input("Local profile (development/test): ").strip()
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            raw_url = getpass.getpass("Local PostgreSQL URL (hidden): ", stream=sys.stderr)
            url, target = qualified_local_target(raw_url, profile)
            print(f"Selected local target: {target}")
            if input("Confirm exact target: ").strip() != target:
                raise ConfigurationUnavailable()
            if input("Type BACKUP VERIFIED API STOPPED TERMINAL RECORDING OFF: ").strip() != (
                "BACKUP VERIFIED API STOPPED TERMINAL RECORDING OFF"
            ):
                raise ConfigurationUnavailable()
            source = AesGcmTenantCredentialStore.from_bootstrap(
                getpass.getpass("Current keyring JSON (hidden): ", stream=sys.stderr)
            )
            replacement = AesGcmTenantCredentialStore.from_bootstrap(
                getpass.getpass(
                    "Replacement keyring JSON, retaining old keys (hidden): ", stream=sys.stderr
                )
            )
        if source is None or replacement is None:
            raise ConfigurationUnavailable()
        engine = create_engine(url, echo=False, hide_parameters=True)
        with Session(engine) as db:
            result = rekey_tenant_credentials(db, source, replacement)
        print(f"Dry-run verified {result.row_count} credential envelope(s); rolled back.")
        if input(f"Type REKEY {target} to commit; otherwise cancel: ").strip() != f"REKEY {target}":
            print("Cancelled after dry-run; database unchanged.")
            return 0
        with Session(engine) as db:
            committed = rekey_tenant_credentials(
                db,
                source,
                replacement,
                dry_run=False,
                expected_snapshot_digest=result.snapshot_digest,
            )
        print(f"Committed {committed.row_count} envelopes with unchanged reference IDs/history.")
        print("Activate the same replacement keyring locally before restarting API. Keep old keys.")
        return 0
    except (Exception, KeyboardInterrupt):
        # Never render exception text, URLs, keyrings, plaintext or ciphertext.
        print(
            "Recovery stopped. Keep both keyrings and backup; verify transaction outcome locally.",
            file=sys.stderr,
        )
        return 2
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                print("Local connection cleanup failed; verify locally.", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
