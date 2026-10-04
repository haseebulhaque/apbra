"""Portable contracts for protected, integrity-bound content bytes.

The database record and the calling service retain resource authority. A storage
key is an opaque locator, never a bearer credential or an authorization input.
Implementations must return exact bytes or fail closed on missing or altered
content. Local filesystem mechanics are deliberately absent from these ports.
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

logger = logging.getLogger("apbra_api.content_storage")


class EvidenceObjectStore(Protocol):
    """Durable evidence and reference material with exact-byte recovery."""

    def write(self, company_id: UUID, case_id: UUID, content: bytes) -> tuple[str, str]: ...

    def read(self, storage_key: str, expected_digest: str) -> bytes: ...

    def restore(
        self,
        company_id: UUID,
        case_id: UUID,
        storage_key: str,
        content: bytes,
        expected_digest: str,
    ) -> None: ...

    def delete(self, storage_key: str) -> None: ...


class ArtifactObjectStore(Protocol):
    """Immutable generated artifact bytes with idempotent uncommitted cleanup."""

    def write(
        self, company_id: UUID, case_id: UUID, attempt_id: UUID, content: bytes
    ) -> tuple[str, str, int]: ...

    def read(self, storage_key: str, expected_digest: str, expected_size: int) -> bytes: ...

    def delete_uncommitted(self, storage_key: str) -> None: ...


def cleanup_uncommitted_evidence(objects: EvidenceObjectStore, storage_key: str) -> None:
    """Best-effort cleanup; a failed delete leaves only unreachable bytes."""
    try:
        objects.delete(storage_key)
    except Exception as exc:
        logger.warning("Uncommitted evidence cleanup failed: type=%s", type(exc).__name__)


def cleanup_uncommitted_artifact(objects: ArtifactObjectStore, storage_key: str) -> None:
    try:
        objects.delete_uncommitted(storage_key)
    except Exception as exc:
        logger.warning("Uncommitted artifact cleanup failed: type=%s", type(exc).__name__)
