"""One trusted-host native receive, no output contract or conversion.

Callers bind the saved case, current context and finite paid grant before
constructing the archive. Passive inspection never grants receive authority.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

import httpx

from .model_provider import (
    FoundryAccess,
    FoundryAgentResponsesProvider,
    FoundryBearer,
    ProviderCallError,
    ProviderProfile,
    ProviderRequest,
)
from .native_response_archive import (
    MAX_NATIVE_RESPONSE_BYTES,
    NativeResponseArchive,
    NativeResponseReceipt,
)
from .provider_diagnostics import response_diagnostic, transport_diagnostic


@dataclass(frozen=True)
class NativeReceiveResult:
    status: Literal["RECEIVED", "HTTP_ERROR"]
    http_status: int
    provider_status: str
    receipt: NativeResponseReceipt = field(repr=False)
    diagnostic: dict[str, Any] = field(default_factory=dict)
    # RECEIVED means bytes arrived and were preserved, not interpretation success.


def receive_native_response(
    profile: ProviderProfile,
    access: FoundryAccess,
    request: ProviderRequest,
    *,
    company_id: UUID,
    case_id: UUID,
    context_version: int,
    archive: NativeResponseArchive,
    transport: httpx.BaseTransport | None = None,
    image_parts: Sequence[dict[str, str]] = (),
) -> NativeReceiveResult:
    started = time.monotonic()
    # Preserve all existing endpoint/profile/tenant/credential qualification.
    FoundryAgentResponsesProvider(
        profile, access, company_id=company_id, transport=transport
    )
    if (
        archive.scope.company_id != company_id
        or archive.scope.case_id != case_id
        or archive.scope.context_version != context_version
    ):
        raise ProviderCallError("NATIVE_RESPONSE_SCOPE_INVALID")
    content = native_request_content(profile, request, image_parts)
    # Nothing from system_prompt/output_schema/retry_instruction is transmitted.
    body = {
        "input": [{"role": "user", "content": (
            [{"type": "input_text", "text": content}, *image_parts] if image_parts else content
        )}],
        "max_output_tokens": profile.max_output_tokens,
        "stream": False,
        "store": False,
    }
    try:
        bearer = access.credential()
    except Exception:
        raise ProviderCallError("MODEL_CREDENTIAL_UNAVAILABLE") from None
    remaining = profile.time_budget_seconds - (time.monotonic() - started)
    if (
        not isinstance(bearer, FoundryBearer)
        or not bearer.token
        or bearer.audience != "https://ai.azure.com"
        or type(bearer.expires_at) not in {int, float}
        or not math.isfinite(bearer.expires_at)
        or bearer.expires_at <= time.time() + remaining
    ):
        raise ProviderCallError("MODEL_CREDENTIAL_UNAVAILABLE")
    if remaining <= 0:
        raise ProviderCallError("MODEL_TIME_BUDGET_EXCEEDED")
    diagnostic: dict[str, Any] = {}
    try:
        # One POST only: no transient retry, candidate repair or format fallback.
        with httpx.Client(
            transport=transport,
            follow_redirects=False,
            timeout=min(profile.request_timeout_seconds, remaining),
        ) as client:
            with client.stream(
                "POST",
                profile.endpoint,
                headers={
                    "Authorization": f"Bearer {bearer.token}",
                    "Content-Type": "application/json",
                },
                params={"api-version": profile.api_version},
                json=body,
            ) as response:
                diagnostic = response_diagnostic(
                    response.status_code, response.headers, None
                )
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_NATIVE_RESPONSE_BYTES:
                        raise ProviderCallError(
                            "MODEL_OUTPUT_BUDGET_EXCEEDED", diagnostic=diagnostic
                        )
                    if time.monotonic() - started >= profile.time_budget_seconds:
                        raise ProviderCallError(
                            "MODEL_TIME_BUDGET_EXCEEDED", diagnostic=diagnostic
                        )
                    chunks.append(chunk)
                raw = b"".join(chunks)
                try:
                    receipt = archive.preserve(raw)
                except Exception:
                    raise ProviderCallError(
                        "NATIVE_RESPONSE_PRESERVATION_FAILED", diagnostic=diagnostic
                    ) from None
                # Inspect envelope status only. Preserve the exact original bytes;
                # do not parse an interpretation, enforce schema or follow file links.
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeError, RecursionError):
                    payload = None
                diagnostic = response_diagnostic(
                    response.status_code, response.headers, payload
                )
                status = payload.get("status") if type(payload) is dict else None
                observed = (
                    status
                    if isinstance(status, str)
                    and status
                    in {
                        "completed",
                        "failed",
                        "incomplete",
                        "queued",
                        "in_progress",
                        "cancelled",
                    }
                    else "UNKNOWN"
                )
                return NativeReceiveResult(
                    "RECEIVED" if 200 <= response.status_code < 300 else "HTTP_ERROR",
                    response.status_code,
                    observed,
                    receipt,
                    diagnostic,
                )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        safe = transport_diagnostic(exc)
        if diagnostic.get("response_received"):
            safe["response_received"] = True
        raise ProviderCallError(
            "MODEL_PROVIDER_TIMEOUT", diagnostic={**diagnostic, **safe}
        ) from None


def native_request_content(
    profile: ProviderProfile, request: ProviderRequest,
    image_parts: Sequence[dict[str, str]] = (),
) -> str:
    content = json.dumps(
        {"task": request.task, "context": request.context},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if (request.requires_vision or image_parts) and not profile.capabilities.vision:
        raise ProviderCallError("VISION_UNSUPPORTED")
    if bool(image_parts) != request.requires_vision:
        raise ProviderCallError("NATIVE_IMAGE_INPUT_INVALID")
    # Include base64 and content-part framing in the same configured input bound.
    size = len(content) + sum(len(json.dumps(part, separators=(",", ":"))) for part in image_parts)
    if size > profile.max_input_characters:
        raise ProviderCallError("MODEL_INPUT_BUDGET_EXCEEDED")
    for part in image_parts:
        if set(part) != {"type", "image_url"} or part.get("type") != "input_image":
            raise ProviderCallError("NATIVE_IMAGE_INPUT_INVALID")
        value = part.get("image_url", "")
        prefix, separator, encoded = value.partition(",")
        if not separator or prefix not in {"data:image/png;base64", "data:image/jpeg;base64"}:
            raise ProviderCallError("NATIVE_IMAGE_INPUT_INVALID")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ProviderCallError("NATIVE_IMAGE_INPUT_INVALID") from None
        valid = (prefix == "data:image/png;base64" and raw.startswith(b"\x89PNG\r\n\x1a\n")) or (
            prefix == "data:image/jpeg;base64" and raw.startswith(b"\xff\xd8\xff")
            and raw.endswith(b"\xff\xd9")
        )
        if not valid:
            raise ProviderCallError("NATIVE_IMAGE_INPUT_INVALID")
    return content
