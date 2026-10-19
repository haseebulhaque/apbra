"""Complete case-source transport for the existing stateless text endpoint.

CSV text is exact UTF-8 source, not a sample or a service file upload.
PNG/JPEG bytes use inline image content when Tenant Settings permits vision.
Workbook tool access needs a separate, explicitly configured route. Never send
partial bundles or claim that input delivery proves processing.
"""

import base64
from dataclasses import dataclass, field
from typing import Any

from .content_storage import EvidenceObjectStore
from .domain import ApplicationError, ApplicationPersistence, CaseRecord, SemanticValidationFailed
from .evidence import EvidenceError, read_verified_evidence


class NativeInputsUnavailable(ApplicationError):
    status_code = 422
    code = "NATIVE_CASE_FILES_UNAVAILABLE"
    public_message = (
        "Complete case files cannot be sent through the configured route. "
        "Check file availability and the Tenant Settings input limit. No AI call was made."
    )


@dataclass(frozen=True)
class NativeCaseFiles:
    manifest: list[dict[str, Any]]
    sources: list[dict[str, Any]] = field(repr=False)
    image_parts: list[dict[str, str]] = field(default_factory=list, repr=False)

    @property
    def ready(self) -> bool:
        return bool(self.manifest) and all(item["status"] == "READY" for item in self.manifest)


def prepare_case_files(
    store: ApplicationPersistence,
    case: CaseRecord,
    objects: EvidenceObjectStore,
    reference_objects: EvidenceObjectStore | None,
    *,
    max_file_bytes: int,
    vision_enabled: bool = False,
) -> NativeCaseFiles:
    manifest: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    image_parts: list[dict[str, str]] = []
    groups = (
        ("DATA", store.evidence_items(case.id), objects),
        ("SUPPORTING", store.reference_materials(case.id), reference_objects),
    )
    for kind, rows, storage in groups:
        for row in rows:
            # Repository/storage locators never establish authority. Fail closed
            # if a persistence adapter returns a different company or case.
            if getattr(row, "company_id", None) != case.company_id or row.case_id != case.id:
                raise SemanticValidationFailed()
            if row.request_version_id != case.current_request_version_id:
                continue
            item: dict[str, Any] = {
                "id": str(row.id),
                "requestVersionId": str(row.request_version_id),
                "filename": row.filename,
                "kind": kind,
                "contentDigest": row.content_digest,
                "status": "UNAVAILABLE",
                "reason": "ORIGINAL_UNAVAILABLE_OR_CHANGED",
                "transport": "NONE",
                "serviceFileUploaded": False,
                "processingVerified": False,
            }
            manifest.append(item)
            try:
                if storage is None:
                    continue
                content = read_verified_evidence(storage, row.storage_key, row.content_digest)
            except EvidenceError:
                continue
            item["bytes"] = len(content)
            if len(content) > max_file_bytes:
                item["reason"] = "TENANT_FILE_SIZE_LIMIT"
                continue
            if kind == "SUPPORTING":
                media_type = getattr(row, "media_type", None)
                valid = (
                    media_type == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n")
                ) or (
                    media_type == "image/jpeg" and content.startswith(b"\xff\xd8\xff")
                    and content.endswith(b"\xff\xd9")
                )
                if not valid:
                    item["reason"] = "IMAGE_FORMAT_UNSUPPORTED"
                    continue
                if not vision_enabled:
                    item["reason"] = "TENANT_VISION_CAPABILITY_DISABLED"
                    continue
                item.update(status="READY", reason=None, transport="INLINE_ORIGINAL_IMAGE")
                sources.append({
                    "id": str(row.id), "requestVersionId": str(row.request_version_id),
                    "filename": row.filename, "mediaType": media_type,
                    "contentDigest": row.content_digest, "byteCount": len(content),
                    "transport": "INLINE_ORIGINAL_IMAGE", "imageContentIndex": len(image_parts) + 1,
                })
                encoded = base64.b64encode(content).decode("ascii")
                image_parts.append({
                    "type": "input_image",
                    "image_url": f"data:{media_type};base64,{encoded}",
                })
                continue
            if kind != "DATA" or getattr(row, "format", None) != "CSV":
                item["reason"] = "APBRA_WORKBOOK_ROUTE_NOT_IMPLEMENTED"
                continue
            try:
                # Keep BOM, line endings, quoting, every row and every column.
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                item["reason"] = "CSV_UTF8_REQUIRED"
                continue
            if "\x00" in text:
                item["reason"] = "CSV_BINARY_CONTENT_UNSUPPORTED"
                continue
            item.update(status="READY", reason=None, transport="INLINE_UTF8_SOURCE")
            sources.append({
                "id": str(row.id),
                "requestVersionId": str(row.request_version_id),
                "filename": row.filename,
                "mediaType": "text/csv",
                "contentDigest": row.content_digest,
                "byteCount": len(content),
                "transport": "INLINE_UTF8_SOURCE",
                "sourceText": text,
            })
    # No usable subset when one supporting file is unsupported/unavailable.
    if not manifest or any(item["status"] != "READY" for item in manifest):
        sources = []
        image_parts = []
    return NativeCaseFiles(manifest, sources, image_parts)
