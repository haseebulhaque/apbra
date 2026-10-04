from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from .authorization import authorized_case_access
from .config import UploadPolicy
from .content_storage import EvidenceObjectStore, cleanup_uncommitted_evidence
from .domain import (
    Actor,
    ApplicationPersistence,
    ConfigurationUnavailable,
    EvidenceInvalid,
    StaleVersion,
)
from .evidence import EvidenceError, read_verified_evidence


def qualified_image(content: bytes, filename: str, policy: UploadPolicy) -> str:
    extension = Path(filename).suffix.upper().lstrip(".")
    if extension not in set(policy.reference_extensions):
        raise EvidenceInvalid()
    png = content.startswith(b"\x89PNG\r\n\x1a\n")
    jpeg = content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9")
    if png and extension == "PNG":
        return "image/png"
    if jpeg and extension in {"JPG", "JPEG"}:
        return "image/jpeg"
    raise EvidenceInvalid()


class ReferenceMaterialService:
    """Retains private image references without claiming semantic interpretation."""

    def __init__(self, objects: EvidenceObjectStore, policy: UploadPolicy) -> None:
        self.objects = objects
        self.policy = policy

    @staticmethod
    def _json(row: Any) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "request_version_id": str(row.request_version_id),
            "filename": row.filename,
            "media_type": row.media_type,
            "content_digest": row.content_digest,
            "interpretation_state": row.interpretation_state,
            "capability_profile_id": row.capability_profile_id,
            "created_at": row.created_at.isoformat(),
        }

    def list(self, db: object, actor: Actor, case_id: UUID) -> list[dict[str, Any]]:
        store = cast(ApplicationPersistence, db)
        case, _ = authorized_case_access(store, actor, case_id)
        result: list[dict[str, Any]] = []
        for row in store.reference_materials(case_id):
            if row.request_version_id != case.current_request_version_id:
                continue
            try:
                read_verified_evidence(self.objects, row.storage_key, row.content_digest)
            except EvidenceError:
                continue
            result.append(self._json(row))
        return result

    def add(
        self,
        db: object,
        actor: Actor,
        case_id: UUID,
        *,
        filename: str,
        content: bytes,
        expected_context_version: int,
    ) -> tuple[dict[str, Any], str | None]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(store, actor, case_id, require_edit=True)
        case = store.locked_case(case_id)
        if case is None or case.semantic_context_version != expected_context_version:
            raise StaleVersion()
        current = [
            item
            for item in store.reference_materials(case_id)
            if item.request_version_id == case.current_request_version_id
        ]
        if len(current) >= self.policy.max_reference_items_per_report:
            raise EvidenceInvalid()
        media_type = qualified_image(content, filename, self.policy)
        digest = hashlib.sha256(content).hexdigest()
        duplicate = store.reference_by_digest(
            case_id, case.current_request_version_id, digest
        )
        if duplicate is not None:
            try:
                read_verified_evidence(
                    self.objects, duplicate.storage_key, duplicate.content_digest
                )
            except EvidenceError:
                self.objects.restore(
                    actor.company_id, case_id, duplicate.storage_key, content,
                    duplicate.content_digest,
                )
                read_verified_evidence(
                    self.objects, duplicate.storage_key, duplicate.content_digest
                )
            result = self._json(duplicate)
            result["semantic_context_version"] = case.semantic_context_version
            return result, None
        storage_key, stored_digest = self.objects.write(actor.company_id, case_id, content)
        if not hmac.compare_digest(digest, stored_digest):
            cleanup_uncommitted_evidence(self.objects, storage_key)
            raise ConfigurationUnavailable()
        try:
            if not hmac.compare_digest(
                read_verified_evidence(self.objects, storage_key, digest), content
            ):
                raise ConfigurationUnavailable()
            row = store.add_reference_material(
                actor,
                case_id,
                case.current_request_version_id,
                filename,
                media_type,
                stored_digest,
                storage_key,
                "NOT_INTERPRETED",
                None,
            )
            store.advance_semantic_context(case)
            store.add_audit(actor, "REFERENCE_MATERIAL_ADDED", "REPORTING_CASE", case_id)
        except Exception:
            cleanup_uncommitted_evidence(self.objects, storage_key)
            raise
        result = self._json(row)
        result["semantic_context_version"] = case.semantic_context_version
        return result, storage_key
