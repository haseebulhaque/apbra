"""Public messages or complete technical grammar projections; no arbitrary remote text."""

from __future__ import annotations

import re
from http import HTTPStatus
from typing import Any
from uuid import UUID

# Exact public protocol identifiers only. Unknown fields may contain private data.
PUBLIC_CODES = frozenset(
    {
        "BadRequest",
        "Unauthorized",
        "Forbidden",
        "NotFound",
        "Conflict",
        "PermissionDenied",
        "AuthenticationError",
        "AuthorizationFailed",
        "InvalidRequest",
        "InvalidRequestError",
        "ResourceNotFound",
        "DeploymentNotFound",
        "OperationNotSupported",
        "InvalidApiVersionParameter",
        "UnsupportedApiVersion",
        "TooManyRequests",
        "RateLimitExceeded",
        "InternalServerError",
        "ServiceUnavailable",
        "invalid_request_error",
        "authentication_error",
        "permission_error",
        "rate_limit_error",
        "server_error",
        "invalid_api_key",
        "insufficient_permissions",
        "model_not_found",
        "unsupported_parameter",
        "invalid_value",
        "content_filter",
    }
)
# Closed public request-field paths only; never schema property/customer names.
PUBLIC_PARAMETERS = frozenset({
    "input", "input[0]", "input[0].role", "input[0].content", "text", "text.format",
    "text.format.type", "text.format.name", "text.format.strict", "text.format.schema",
    "max_output_tokens", "stream", "store", "api-version",
})
PUBLIC_MESSAGES = frozenset(
    {
        "Invalid parameter",
        "Invalid parameter.",
        "Invalid request.",
        "Access denied.",
        "Unauthorized",
        "Forbidden",
        "Not Found",
        "The requested resource was not found.",
        "Internal server error",
    }
)
# Exact full messages assembled solely from the public wire vocabulary. No
# prefix matching, free-form suffixes, model names or customer schema fields.
PUBLIC_MESSAGES = PUBLIC_MESSAGES | frozenset(
    f"{kind} parameter: '{parameter}'."
    for kind in ("Invalid", "Unknown", "Unsupported")
    for parameter in PUBLIC_PARAMETERS
)
# Whole-message grammars retain technical meaning without admitting arbitrary
# remote prose. Unknown sentences and suffixes stay withheld. Captured dynamic
# model identifiers are discarded, never copied into the explanation.
_FORMATS = ("json_schema", "json_object", "text")
_PARAMETER_PATTERN = "(?:" + "|".join(re.escape(p) for p in sorted(PUBLIC_PARAMETERS)) + ")"
_CONTEXT_PATTERN = (
    "(?:for published agents|for agents|with agent references|with agent_reference|"
    "when using an agent|when invoking a published agent|with Foundry Agents Service)"
)
_MESSAGE_GRAMMARS = (
    ("AGENT_PARAMETER_UNSUPPORTED", re.compile(
        rf"(?:The )?(?P<parameter_quote>['\"]?)(?P<parameter>{_PARAMETER_PATTERN})"
        r"(?P=parameter_quote) parameter "
        r"(?:is not supported|is not allowed|cannot be overridden) "
        rf"(?P<context>{_CONTEXT_PATTERN})\."
        r"(?: (?:Please )?(?:[Cc]onfigure|[Ss]et) the (?:response|output) format "
        r"in the agent definition instead\.)?"
    )),
    ("AGENT_PARAMETER_UNSUPPORTED", re.compile(
        rf"Unsupported parameter: (?P<parameter_quote>['\"])(?P<parameter>{_PARAMETER_PATTERN})"
        r"(?P=parameter_quote) is not supported "
        rf"(?P<context>{_CONTEXT_PATTERN})\."
    )),
    ("MODEL_FORMAT_UNSUPPORTED", re.compile(
        rf"Invalid parameter: (?P<parameter_quote>['\"])(?P<parameter>{_PARAMETER_PATTERN})"
        r"(?P=parameter_quote) of type "
        r"(?P<format_quote>['\"])(?P<format>json_schema|json_object|text)"
        r"(?P=format_quote) is not supported with model version "
        r"(?:`[A-Za-z0-9_.-]{1,120}`|'[A-Za-z0-9_.-]{1,120}'|\"[A-Za-z0-9_.-]{1,120}\")\.?"
    )),
    ("AGENT_FORMAT_UNSUPPORTED", re.compile(
        r"(?:Structured outputs|JSON schema response format) (?:are|is) not supported "
        r"(?:for published agents|with Foundry Agents Service)\."
    )),
)
# Canonical messages are accepted again at persistence/read boundaries. Derive
# provenance from the exact canonical message instead of trusting a supplied ID.
_CANONICAL_MESSAGES: dict[str, str] = {
    "Structured output is not supported by this agent service.": "AGENT_FORMAT_UNSUPPORTED",
}
for _parameter in PUBLIC_PARAMETERS:
    _CANONICAL_MESSAGES[
        f"Parameter '{_parameter}' is not supported for this agent invocation."
    ] = "AGENT_PARAMETER_UNSUPPORTED"
    for _format in _FORMATS:
        _CANONICAL_MESSAGES[
            f"Parameter '{_parameter}' with format '{_format}' "
            "is not supported by the configured model."
        ] = "MODEL_FORMAT_UNSUPPORTED"


def _project_message(value: object) -> tuple[str | None, str | None, bool]:
    if type(value) is not str or not value or len(value) > 2048:
        return None, None, value is not None
    # No Unicode normalization, multiline matching or partial-prefix acceptance.
    if not value.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        return None, None, True
    if value in PUBLIC_MESSAGES:
        return value, None, False
    if value in _CANONICAL_MESSAGES:
        return value, _CANONICAL_MESSAGES[value], False
    for template, pattern in _MESSAGE_GRAMMARS:
        matched = pattern.fullmatch(value)
        if matched is None:
            continue
        groups = matched.groupdict()
        if template == "AGENT_PARAMETER_UNSUPPORTED":
            return (
                f"Parameter '{groups['parameter']}' is not supported for this agent invocation.",
                template, False,
            )
        if template == "MODEL_FORMAT_UNSUPPORTED":
            return (
                f"Parameter '{groups['parameter']}' with format '{groups['format']}' "
                "is not supported by the configured model.", template, True,
            )
        return "Structured output is not supported by this agent service.", template, False
    return None, None, True


TRANSPORT_TYPES = frozenset(
    {
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "ConnectError",
        "ReadError",
        "WriteError",
        "CloseError",
        "RemoteProtocolError",
        "LocalProtocolError",
        "ProxyError",
        "UnsupportedProtocol",
        "TimeoutException",
        "TransportError",
    }
)


def safe_provider_diagnostic(value: object) -> dict[str, Any]:
    """Revalidate persisted/untrusted diagnostics at both write and read boundaries."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    status = value.get("http_status")
    if type(status) is int and 100 <= status <= 599:
        result["http_status"] = status
        try:
            result["http_reason"] = HTTPStatus(status).phrase
        except ValueError:
            result["http_reason"] = "Unregistered HTTP status"
    for key in ("provider_code", "provider_type"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate in PUBLIC_CODES:
            result[key] = candidate
    for key in ("provider_param", "provider_target"):
        candidate = value.get(key)
        if type(candidate) is str and candidate in PUBLIC_PARAMETERS:
            result[key] = candidate
    identifier = value.get("request_id")
    if isinstance(identifier, str) and len(identifier) <= 36:
        try:
            result["request_id"] = str(UUID(identifier))
        except ValueError:
            pass
    message, template, withheld = _project_message(value.get("provider_message"))
    if message is not None:
        result["provider_message"] = message
        if template is not None:
            result["provider_message_template"] = template
    if message is not None or (
        value.get("provider_message") is not None
        and type(value.get("provider_message_redacted")) is bool
    ):
        result["provider_message_redacted"] = (
            withheld or value.get("provider_message_redacted") is True
        )
    for key in (
        "transport_attempted", "response_received", "provider_message_redacted",
        "provider_code_redacted", "provider_type_redacted", "provider_param_redacted",
        "provider_target_redacted",
    ):
        if type(value.get(key)) is bool and key not in result:
            result[key] = value[key]
    for key in ("exception_type", "cause_type"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate in TRANSPORT_TYPES:
            result[key] = candidate
    return result


def response_diagnostic(status: int, headers: Any, payload: object) -> dict[str, Any]:
    error = payload.get("error") if isinstance(payload, dict) else None
    error = error if isinstance(error, dict) else {}
    message = error.get("message")
    _safe_message, _template, withheld = _project_message(message)
    values = {
        "http_status": status,
        "transport_attempted": True,
        "response_received": True,
        "provider_code": error.get("code"),
        "provider_type": error.get("type"),
        "provider_message": message,
        "provider_message_redacted": withheld,
    }
    # Preserve structured public identifiers, never parse diagnostic message text.
    for wire, safe, allowed in (
        ("code", "provider_code", PUBLIC_CODES),
        ("type", "provider_type", PUBLIC_CODES),
        ("param", "provider_param", PUBLIC_PARAMETERS),
        ("target", "provider_target", PUBLIC_PARAMETERS),
    ):
        candidate = error.get(wire)
        values[safe] = candidate
        values[safe + "_redacted"] = candidate is not None and (
            type(candidate) is not str or candidate not in allowed
        )
    for key in ("apim-request-id", "x-ms-request-id", "x-request-id", "request-id"):
        identifier = headers.get(key)
        if isinstance(identifier, str) and len(identifier) <= 36:
            try:
                values["request_id"] = str(UUID(identifier))
                break
            except ValueError:
                pass
    return safe_provider_diagnostic(values)


def transport_diagnostic(error: Exception) -> dict[str, Any]:
    return safe_provider_diagnostic(
        {
            "transport_attempted": True,
            "response_received": False,
            "exception_type": type(error).__name__,
            "cause_type": type(error.__cause__).__name__ if error.__cause__ else None,
        }
    )
