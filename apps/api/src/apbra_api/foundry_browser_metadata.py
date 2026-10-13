"""Explicit private browser metadata server. No paid runtime credential is granted."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from typing import Any, TextIO
from urllib.parse import urlsplit
from uuid import UUID

from .api import create_app
from .config import Settings, get_settings
from .foundry_agent_details import AgentMetadataAccess, agent_details
from .foundry_owner_metadata import (
    OwnerMetadataPlan,
    _browser_credential,
    _confirm_private,
    _DeviceCredential,
    _Discard,
    _private_sdk_logging,
    _qualification_terminal,
    _quiet_call,
)
from .model_provider import (
    FoundryBearer,
    FoundryMemoryTokenCredential,
    ProviderConfigurationError,
    ProviderProfile,
)
from .persistence import CompanyRow, Database
from .tenant_settings import TenantSettingsSnapshot, current_settings, validate_qualified_profile

_SCOPE = "https://ai.azure.com/.default"
_ERROR = "FOUNDRY_BROWSER_METADATA_UNAVAILABLE"


def _require(value: object) -> None:
    if not value:
        raise ProviderConfigurationError(_ERROR)


def _local_address(settings: Settings) -> tuple[str, int]:
    parsed = urlsplit(settings.api_origin)
    _require(
        parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
        and parsed.port is not None
        and parsed.port > 0
        and not parsed.username
        and not parsed.password
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )
    assert parsed.hostname is not None and parsed.port is not None
    return parsed.hostname, parsed.port


def _serve(app: Any, settings: Settings) -> None:
    import uvicorn

    host, port = _local_address(settings)
    uvicorn.run(
        app, host=host, port=port, workers=1, reload=False, access_log=False, log_config=None
    )


@dataclass(frozen=True)
class BrowserMetadataPlan:
    company_id: UUID
    tenant_id: UUID
    client_id: UUID
    authorization_deadline: float

    def validate(self) -> None:
        _require(
            all(type(value) is UUID for value in (self.company_id, self.tenant_id, self.client_id))
        )
        _require(
            type(self.authorization_deadline) in {int, float}
            and math.isfinite(self.authorization_deadline)
            and self.authorization_deadline > time.time()
        )


def _snapshot(database: Database, settings: Settings, company_id: UUID) -> TenantSettingsSnapshot:
    with database.session() as db:
        company = db.get(CompanyRow, company_id)
        _require(company is not None and company.active is True)
        snapshot = current_settings(db, company_id)
        profile = snapshot.settings.provider_profile
        _require(
            snapshot.company_id == company_id
            and snapshot.secret_reference_id is None
            and profile is not None
            and profile.protocol == "FOUNDRY_AGENT_RESPONSES"
        )
        validate_qualified_profile(profile, settings.qualified_provider_profiles())
        return snapshot


class BrowserMetadataCredential:
    """One company/current-settings memory lease, accepted only by metadata reads."""

    def __init__(
        self,
        snapshot: TenantSettingsSnapshot,
        token: FoundryMemoryTokenCredential,
        unchanged: Callable[[], bool],
    ) -> None:
        self._snapshot = snapshot
        self._profile = snapshot.settings.provider_profile
        _require(self._profile is not None)
        self._token = token
        self._unchanged = unchanged

    def ready(self, company_id: UUID, profile: ProviderProfile) -> bool:
        if company_id != self._snapshot.company_id or profile != self._profile:
            return False
        try:
            valid = self._unchanged() is True and self._token.ready()
        except Exception:
            valid = False
        if not valid:
            self._token.close()
        return valid

    def resolve(self, company_id: UUID, profile: ProviderProfile) -> AgentMetadataAccess:
        _require(self.ready(company_id, profile))

        def bearer() -> FoundryBearer:
            _require(self.ready(company_id, profile))
            acquired = self._token.get_token(_SCOPE)
            result = FoundryBearer(token=acquired.token, expires_at=acquired.expires_on)
            _require(self.ready(company_id, profile))
            return result

        return AgentMetadataAccess(
            company_id=company_id,
            profile_id=profile.profile_id,
            configuration_id=profile.configuration_id,
            credential=bearer,
            agent_version=profile.agent_version,
        )


def run_browser_metadata(
    plan: BrowserMetadataPlan,
    *,
    settings: Settings | None = None,
    credential_factory: Callable[..., _DeviceCredential] | None = None,
    snapshot_loader: Callable[[], TenantSettingsSnapshot] | None = None,
    terminal_factory: Callable[..., AbstractContextManager[TextIO]] | None = None,
    confirm: Callable[[TextIO, OwnerMetadataPlan, str, str], None] | None = None,
    serve: Callable[..., None] | None = None,
    observe: Callable[..., dict[str, object]] | None = None,
) -> None:
    """Owner executes after separate approval; injected seams enable offline checks.

    Explicit identity IDs/deadline are owner authentication inputs. Agent
    endpoint/version/limits come exclusively from the selected saved settings.
    No SDK, account, token, response or credential is exported or persisted.
    """
    token = None
    sdk = None
    database = None
    try:
        plan.validate()
        settings = settings or get_settings()
        _require(not settings.foundry_host_enabled)
        settings.validate_security_profile()
        _local_address(settings)
        # Open and validate the private terminal before any database access.
        terminal_plan = OwnerMetadataPlan(
            tenant_id=str(plan.tenant_id), client_id=str(plan.client_id)
        )
        context = (terminal_factory or _qualification_terminal)(terminal_plan)
        with context as terminal:
            approval = confirm or _confirm_private
            approval(
                terminal,
                terminal_plan,
                "Approve this company-bound metadata-only server. Stop for new Microsoft "
                "consent or permissions. No model generation, token export or paid calls.",
                "CONFIRM PRIVATE METADATA SERVER",
            )
            if snapshot_loader is None:
                database = Database(settings.database_url)

                def load() -> TenantSettingsSnapshot:
                    assert database is not None and settings is not None
                    return _snapshot(database, settings, plan.company_id)

                snapshot_loader = load
            initial = snapshot_loader()
            profile = initial.settings.provider_profile
            _require(
                initial.company_id == plan.company_id
                and initial.secret_reference_id is None
                and profile is not None
                and profile.protocol == "FOUNDRY_AGENT_RESPONSES"
            )
            assert profile is not None
            validate_qualified_profile(profile, settings.qualified_provider_profiles())

            def unchanged() -> bool:
                try:
                    fresh = snapshot_loader()
                    return (
                        time.time() < plan.authorization_deadline
                        and fresh.id == initial.id
                        and fresh.digest == initial.digest
                        and fresh.company_id == initial.company_id
                        and fresh.settings.provider_profile == profile
                        and fresh.secret_reference_id is None
                    )
                except Exception:
                    return False

            _require(unchanged())
            timeout = min(
                profile.request_timeout_seconds, plan.authorization_deadline - time.time()
            )
            _require(timeout > 0)
            sdk = _quiet_call(
                credential_factory or _browser_credential,
                tenant_id=str(plan.tenant_id),
                client_id=str(plan.client_id),
                authority="login.microsoftonline.com",
                additionally_allowed_tenants=[],
                disable_automatic_authentication=True,
                cache_persistence_options=None,
                enable_support_logging=False,
                logging_enable=False,
                timeout=timeout,
                connection_timeout=timeout,
                read_timeout=timeout,
                retry_total=0,
            )
            record = _quiet_call(sdk.authenticate, scopes=[_SCOPE])
            account = (record.tenant_id, record.client_id, record.home_account_id)
            label = getattr(record, "username", None)
            _require(
                account[:2] == (str(plan.tenant_id), str(plan.client_id))
                and type(account[2]) is str
                and re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", account[2])
                and type(label) is str
                and 1 <= len(label) <= 255
                and label.isprintable()
            )
            _require(unchanged())
            assert isinstance(label, str)
            approval(
                terminal, terminal_plan, "Selected existing account: " + label, "CONFIRM ACCOUNT"
            )
            _require(unchanged())
            acquired = _quiet_call(sdk.get_token, _SCOPE)
            _require(
                account == (record.tenant_id, record.client_id, record.home_account_id)
                and unchanged()
            )
            digest = hashlib.sha256(
                json.dumps(
                    {
                        "company": str(plan.company_id),
                        "settings": str(initial.id),
                        "digest": initial.digest,
                        "tenant": str(plan.tenant_id),
                        "client": str(plan.client_id),
                        "deadline": plan.authorization_deadline,
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            token = FoundryMemoryTokenCredential(
                acquired,
                authorization_deadline=plan.authorization_deadline,
                enabled=unchanged,
                binding_digest=digest,
            )
            del acquired, record, account, label
            _quiet_call(sdk.close)
            sdk = None
            credentials = BrowserMetadataCredential(initial, token, unchanged)
            # Same bounded configured GETs and informational projection as admin.
            details = (observe or agent_details)(plan.company_id, profile, credentials)
            _require(details.get("status") == "METADATA_OBSERVED_ONLY" and unchanged())
            del details
            _require(credentials.ready(plan.company_id, profile))
            app = create_app(settings=settings, foundry_metadata_credentials=credentials)
            host, port = _local_address(settings)
            terminal.write(
                f"Metadata-only server ready at http://{host}:{port}; "
                "generation credential not activated. Stop with Ctrl+C.\n"
            )
            terminal.flush()
            # Do not hold SDK_SERIALIZER during serving: metadata worker
            # threads need that lock for their bounded quiet GETs.
            with _private_sdk_logging(), redirect_stdout(_Discard()), redirect_stderr(_Discard()):
                (serve or _serve)(app, settings)
    except BaseException:
        raise ProviderConfigurationError(_ERROR) from None
    finally:
        try:
            if sdk is not None:
                _quiet_call(sdk.close)
        except BaseException:
            raise ProviderConfigurationError(_ERROR) from None
        finally:
            if token is not None:
                token.close()
            if database is not None:
                database.engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Explicit private metadata-only browser server")
    parser.add_argument("--company-id", required=True, type=UUID)
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--client-id", required=True, type=UUID)
    parser.add_argument("--authorization-deadline", required=True, type=float)
    args = parser.parse_args()
    try:
        run_browser_metadata(BrowserMetadataPlan(**vars(args)))
    except BaseException:
        raise SystemExit(_ERROR) from None


if __name__ == "__main__":
    main()
