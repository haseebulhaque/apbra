"""Default startup never discovers or authenticates Azure credentials."""

import argparse
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Protocol, TextIO
from urllib.parse import urlparse

from fastapi import FastAPI

from .api import create_app
from .config import FoundryHostBinding, Settings, get_settings
from .model_provider import (
    FoundryAccessToken,
    FoundryMemoryTokenCredential,
    FoundryTokenCredentialProvider,
    ProviderConfigurationError,
)

_SCOPE = "https://ai.azure.com/.default"


class _AuthenticationRecord(Protocol):
    @property
    def tenant_id(self) -> str: ...
    @property
    def client_id(self) -> str: ...
    @property
    def home_account_id(self) -> str: ...


class _DeviceCredential(Protocol):
    def authenticate(self, *, scopes: list[str]) -> _AuthenticationRecord: ...
    def get_token(self, *scopes: str) -> FoundryAccessToken: ...
    def close(self) -> None: ...


def _device_credential(**kwargs: Any) -> _DeviceCredential:
    # Only the separately approved manual flow reaches this import/construction.
    from azure.identity import DeviceCodeCredential

    return DeviceCodeCredential(**kwargs)


def _authorized(settings: Settings, binding: FoundryHostBinding) -> bool:
    try:
        return settings.foundry_host_binding() == binding
    except Exception:
        return False


def create_runtime_app(
    settings: Settings | None = None, token_credential: FoundryMemoryTokenCredential | None = None
) -> FastAPI:
    settings = settings or get_settings()
    if not settings.foundry_host_enabled:
        if token_credential is not None:
            raise ProviderConfigurationError("FOUNDRY_RUNTIME_IDENTITY_UNAVAILABLE")
        return create_app(settings=settings)
    binding = settings.foundry_host_binding()
    if (
        not isinstance(token_credential, FoundryMemoryTokenCredential)
        or token_credential.binding_digest != binding.binding_digest()
        or not token_credential.ready()
    ):
        raise ProviderConfigurationError("FOUNDRY_RUNTIME_IDENTITY_UNAVAILABLE")
    credential = FoundryTokenCredentialProvider(
        company_id=binding.company_id,
        profile=binding.provider_profile,
        token_credential=token_credential,
        enabled=lambda: _authorized(settings, binding) and token_credential.ready(),
        knowledge_binding=binding.knowledge_binding,
        knowledge_scope=binding.knowledge_scope,
        agent_version=binding.agent_version,
        qualification=binding.qualification,
    )
    return create_app(settings=settings, foundry_credentials=credential)


@contextmanager
def _private_terminal() -> Iterator[TextIO]:
    if not sys.stdin.isatty():
        raise ProviderConfigurationError("FOUNDRY_PRIVATE_TERMINAL_REQUIRED")
    # No challenge is sent to stdout, stderr, application logs or an API.
    with open("/dev/tty", "w", encoding="utf-8") as terminal:
        if not terminal.isatty():
            raise ProviderConfigurationError("FOUNDRY_PRIVATE_TERMINAL_REQUIRED")
        yield terminal


def _serve(application: FastAPI, settings: Settings) -> None:
    import uvicorn

    origin = urlparse(settings.api_origin)
    if origin.hostname not in {"127.0.0.1", "localhost"} or origin.port is None:
        raise ProviderConfigurationError("FOUNDRY_LOCAL_HOST_REQUIRED")
    uvicorn.run(
        application,
        host=origin.hostname,
        port=origin.port,
        workers=1,
        reload=False,
        access_log=False,
        log_config=None,
    )


def run_foundry_device_code(
    settings: Settings | None = None,
    credential_factory: Callable[..., _DeviceCredential] | None = None,
) -> None:
    """Explicit private manual action; offline work does not approve invocation."""
    settings = settings or get_settings()
    binding = settings.foundry_host_binding()
    origin = urlparse(settings.api_origin)
    if origin.hostname not in {"127.0.0.1", "localhost"} or origin.port is None:
        raise ProviderConfigurationError("FOUNDRY_LOCAL_HOST_REQUIRED")
    snapshot: FoundryMemoryTokenCredential | None = None
    try:
        with _private_terminal() as terminal:
            if not terminal.isatty() or not _authorized(settings, binding):
                raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")
            remaining = int(binding.authorization_deadline - time.time())
            if remaining < 1:
                raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")

            def private_prompt(uri: str, code: str, expires: datetime) -> None:
                if (
                    not terminal.isatty()
                    or not _authorized(settings, binding)
                    or expires.timestamp() <= time.time()
                ):
                    raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")
                terminal.write(f"Complete the approved sign-in at {uri} using code {code}.\n")
                terminal.flush()

            sdk = (credential_factory or _device_credential)(
                tenant_id=str(binding.tenant_id),
                client_id=str(binding.client_id),
                authority="login.microsoftonline.com",
                additionally_allowed_tenants=[],
                disable_automatic_authentication=True,
                cache_persistence_options=None,
                enable_support_logging=False,
                logging_enable=False,
                prompt_callback=private_prompt,
                timeout=remaining,
            )
            try:
                if not _authorized(settings, binding):
                    raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")
                record = sdk.authenticate(scopes=[_SCOPE])
                if (
                    not _authorized(settings, binding)
                    or record.tenant_id != str(binding.tenant_id)
                    or record.client_id != str(binding.client_id)
                    or record.home_account_id != binding.home_account_id
                ):
                    raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")
                acquired = sdk.get_token(_SCOPE)
                if not _authorized(settings, binding):
                    raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")
                snapshot = FoundryMemoryTokenCredential(
                    acquired,
                    authorization_deadline=binding.authorization_deadline,
                    enabled=lambda: _authorized(settings, binding),
                    binding_digest=binding.binding_digest(),
                )
                del acquired, record
            finally:
                sdk.close()
                del sdk
        if not _authorized(settings, binding) or not snapshot.ready():
            raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE")
        _serve(create_runtime_app(settings, snapshot), settings)
    except Exception:
        # SDK/terminal/server exceptions can contain private material.
        raise ProviderConfigurationError("FOUNDRY_HOST_UNAVAILABLE") from None
    finally:
        if snapshot is not None:
            snapshot.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Explicit approved local Foundry host")
    parser.add_argument("--foundry-device-code", action="store_true", required=True)
    parser.parse_args()
    try:
        run_foundry_device_code()
    except ProviderConfigurationError:
        raise SystemExit(
            "Foundry host is unavailable. Review its approved configuration."
        ) from None


if __name__ == "__main__":
    main()
else:
    app = create_runtime_app()
