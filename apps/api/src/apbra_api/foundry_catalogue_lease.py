"""Owner-confirmed, temporary directory-only lease. No sign-in or default issuer.

The trusted private host binds a confirmed SDK account to one existing local
owner identity. This is not shared multi-user federation or an email mapping.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from uuid import UUID

from .foundry_admin_reads import ReadAccess, ReadRequest
from .model_provider import FoundryBearer, FoundryMemoryTokenCredential, ProviderProfile

if TYPE_CHECKING:
    from .persistence import Database

ERROR = "FOUNDRY_CATALOGUE_LEASE_UNAVAILABLE"


class CatalogueLeaseError(ValueError):
    """Fixed nonsecret failure; no provider or credential value propagated."""


def require(value: object) -> None:
    if value is not True:
        raise CatalogueLeaseError(ERROR)


@dataclass(frozen=True, repr=False)
class CataloguePlan:
    company_id: UUID
    identity_id: UUID
    membership_id: UUID
    settings_id: UUID
    settings_digest: str
    tenant_id: UUID
    client_id: UUID
    profile: ProviderProfile = field(repr=False)
    authorization_deadline: float
    page_requests: int

    def validate(self) -> None:
        require(
            all(
                type(value) is UUID
                for value in (
                    self.company_id,
                    self.identity_id,
                    self.membership_id,
                    self.settings_id,
                    self.tenant_id,
                    self.client_id,
                )
            )
        )
        require(
            type(self.settings_digest) is str
            and re.fullmatch(r"[a-f0-9]{64}", self.settings_digest) is not None
        )
        require(
            type(self.authorization_deadline) in (int, float)
            and math.isfinite(self.authorization_deadline)
            and self.authorization_deadline > time.time()
        )
        require(type(self.page_requests) is int and self.page_requests > 0)
        require(
            type(self.profile) is ProviderProfile
            and self.profile.protocol == "FOUNDRY_AGENT_RESPONSES"
            and self.profile.api_version == "v1"
        )
        parsed = urlsplit(self.profile.endpoint)
        require(
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and parsed.port in (None, 443)
            and re.fullmatch(
                r"/api/projects/[A-Za-z0-9_-]+/agents/[A-Za-z0-9-]+/endpoint/protocols/openai/responses",
                parsed.path,
            )
            is not None
        )

    def wire(self) -> dict[str, object]:
        self.validate()
        return {
            "company_id": str(self.company_id),
            "identity_id": str(self.identity_id),
            "membership_id": str(self.membership_id),
            "settings_id": str(self.settings_id),
            "settings_digest": self.settings_digest,
            "tenant_id": str(self.tenant_id),
            "client_id": str(self.client_id),
            "profile": self.profile.model_dump(mode="json"),
            "authorization_deadline": self.authorization_deadline,
            "page_requests": self.page_requests,
        }

    def matches(self, request: ReadRequest) -> bool:
        return (
            type(request) is ReadRequest
            and (
                request.company_id,
                request.identity_id,
                request.membership_id,
                request.settings_id,
                request.profile_id,
                request.configuration_id,
                request.endpoint,
                request.agent_version,
                request.operation,
                request.vector_store_id,
            )
            == (
                self.company_id,
                self.identity_id,
                self.membership_id,
                self.settings_id,
                self.profile.profile_id,
                self.profile.configuration_id,
                self.profile.endpoint,
                self.profile.agent_version,
                "LIST_AGENTS",
                None,
            )
            and type(request.limit) is int
            and request.limit in (10, 25, 50, 100)
            and (
                request.after is None
                or type(request.after) is str
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}", request.after) is not None
            )
        )


def approval_payload(plan: CataloguePlan, nonce: str, account: str) -> dict[str, object]:
    require(type(plan) is CataloguePlan)
    require(type(nonce) is str and re.fullmatch(r"[a-f0-9]{64}", nonce) is not None)
    require(type(account) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", account) is not None)
    return {"v": 1, "nonce": nonce, "catalogue": plan.wire(), "account": account}


def validate_approval(value: object, plan: CataloguePlan, nonce: str) -> str:
    require(type(value) is dict and set(value) == {"v", "nonce", "catalogue", "account"})
    assert isinstance(value, dict)
    expected = approval_payload(plan, nonce, value["account"])
    # Canonical byte comparison distinguishes bool/int and rejects extra nested fields.
    require(
        json.dumps(value, sort_keys=True, separators=(",", ":"))
        == json.dumps(expected, sort_keys=True, separators=(",", ":"))
    )
    return str(value["account"])


def owner_is_current(database: Database, plan: CataloguePlan) -> bool:
    """Server-derived active membership and immutable settings; never email matching."""
    from .persistence import ApplicationSession
    from .tenant_settings import current_settings

    try:
        plan.validate()
        with database.session() as db:
            if not isinstance(db, ApplicationSession):
                return False
            actor = db.active_actor(plan.membership_id, plan.identity_id)
            if (
                actor is None
                or actor.company_id != plan.company_id
                or actor.role not in {"COMPANY_OWNER", "COMPANY_ADMIN"}
            ):
                return False
            snapshot = current_settings(db, plan.company_id)
            return (
                snapshot.id == plan.settings_id
                and snapshot.digest == plan.settings_digest
                and snapshot.settings.provider_profile == plan.profile
                and snapshot.secret_reference_id is None
            )
    except Exception:
        return False


class CatalogueCredentials:
    """Exact caller directory reads only; no metadata/report credential interface.

    current must recheck the active owner membership AND immutable tenant
    settings. The receiver owns that database check and channel lifetime.
    """

    def __init__(
        self,
        plan: CataloguePlan,
        account: str,
        token: FoundryMemoryTokenCredential,
        current: Callable[[], bool],
    ) -> None:
        plan.validate()
        require(
            type(account) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", account) is not None
        )
        require(type(token) is FoundryMemoryTokenCredential and callable(current))
        self._plan, self._token, self._current = plan, token, current
        self._lock = threading.RLock()
        self._remaining = plan.page_requests
        self._closed = False
        self._issued: dict[int, ReadAccess] = {}
        self._used: set[int] = set()

    def __repr__(self) -> str:
        return "CatalogueCredentials(<temporary owner directory lease>)"

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._issued.clear()
            self._used.clear()
            self._token.close()

    def _active(self) -> bool:
        try:
            active = (
                not self._closed
                and time.time() < self._plan.authorization_deadline
                and self._current() is True
                and self._token.ready()
            )
        except Exception:
            active = False
        if not active:
            self.close()
        return active

    def resolve(self, request: ReadRequest) -> ReadAccess | None:
        with self._lock:
            if not self._plan.matches(request) or not self._active() or self._remaining < 1:
                return None
            self._remaining -= 1  # Never refund failed/uncertain attempted reads.
            access = ReadAccess(
                request, self._plan.authorization_deadline, lambda: self._bearer(request, access)
            )
            self._issued[id(access)] = access
            return access

    def ready(self, request: ReadRequest, access: ReadAccess) -> bool:
        with self._lock:
            return (
                type(access) is ReadAccess
                and self._issued.get(id(access)) is access
                and access.request == request
                and self._plan.matches(request)
                and self._active()
            )

    def _bearer(self, request: ReadRequest, access: ReadAccess) -> FoundryBearer:
        with self._lock:
            require(self.ready(request, access) and id(access) not in self._used)
            self._used.add(id(access))
            acquired = self._token.get_token("https://ai.azure.com/.default")
            require(self.ready(request, access))
            return FoundryBearer(acquired.token, acquired.expires_on)
