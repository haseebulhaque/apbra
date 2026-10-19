"""Private exact-byte native receipts; no conversion or business inference.

The application must supply a server-authorized case binding and a durable index.
This module does not create resource authority or fetch returned URLs/files.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID, uuid4

from .content_storage import EvidenceObjectStore

# The existing provider transport bound, not a new product allowance.
MAX_NATIVE_RESPONSE_BYTES = 4_000_000


@dataclass(frozen=True)
class NativeResponseScope:
    company_id: UUID
    case_id: UUID
    context_version: int
    operation_id: UUID


@dataclass(frozen=True)
class NativeResponseReceipt:
    id: UUID
    scope: NativeResponseScope
    digest: str
    size: int
    storage_key: str = field(repr=False)


class NativeResponseIndex(Protocol):
    def load(
        self, scope: NativeResponseScope, reference: UUID
    ) -> NativeResponseReceipt: ...

    def commit(self, receipt: NativeResponseReceipt) -> None:
        """Durably bind private bytes to the authorized case; return after commit."""
        ...


class NativeResponsePreservationFailed(RuntimeError):
    def __init__(self) -> None:
        super().__init__("NATIVE_RESPONSE_PRESERVATION_FAILED")


class NativeResponseArchive:
    """Uses existing protected storage; durable index implementation is required."""

    def __init__(
        self,
        scope: NativeResponseScope,
        objects: EvidenceObjectStore,
        index: NativeResponseIndex,
    ) -> None:
        if type(scope.context_version) is not int or scope.context_version < 1:
            raise ValueError("NATIVE_RESPONSE_SCOPE_INVALID")
        self.scope, self._objects, self._index = scope, objects, index

    def preserve(self, raw: bytes) -> NativeResponseReceipt:
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_NATIVE_RESPONSE_BYTES:
            raise NativeResponsePreservationFailed()
        try:
            key, digest = self._objects.write(
                self.scope.company_id, self.scope.case_id, raw
            )
            if digest != hashlib.sha256(raw).hexdigest():
                raise ValueError("NATIVE_RESPONSE_DIGEST_INVALID")
            receipt = NativeResponseReceipt(uuid4(), self.scope, digest, len(raw), key)
            self._index.commit(receipt)
            return receipt
        except Exception:
            # Do not log private content, paths, exception values or erase original bytes.
            raise NativeResponsePreservationFailed() from None

    def read(self, reference: UUID) -> bytes:
        try:
            receipt = self._index.load(self.scope, reference)
            if receipt.scope != self.scope or receipt.id != reference:
                raise NativeResponsePreservationFailed()
            raw = self._objects.read(receipt.storage_key, receipt.digest)
            if (
                len(raw) != receipt.size
                or hashlib.sha256(raw).hexdigest() != receipt.digest
            ):
                raise ValueError("NATIVE_RESPONSE_INTEGRITY_INVALID")
            return raw
        except Exception:
            raise NativeResponsePreservationFailed() from None
