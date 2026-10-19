"""Offline failure capture and hostile diagnostic boundary regression checks."""

import json

import httpx
import pytest
from test_model_provider import foundry_adapter, request

from apbra_api.application import AnalysisAttemptFailed
from apbra_api.model_provider import ProviderCallError
from apbra_api.observability import _audit_details, _safe_diagnostic, diagnostic_json
from apbra_api.provider_diagnostics import response_diagnostic, safe_provider_diagnostic

REQUEST_ID = "cd493a40-07f1-43bf-94e8-c144b31fa603"
PRIVATE = "PRIVATE-REPORT-CREDENTIAL-CANARY"


@pytest.mark.parametrize(
    "status,code",
    [(400, "InvalidRequest"), (401, "Unauthorized"), (403, "PermissionDenied"), (404, "NotFound")],
)
def test_failed_response_facts_survive_application_persistence_and_admin_projection(status, code):
    calls = []

    def handler(wire):
        calls.append(1)
        return httpx.Response(
            status,
            headers={"apim-request-id": REQUEST_ID, "Authorization": PRIVATE},
            json={
                "error": {
                    "code": code,
                    "type": "invalid_request_error",
                    "message": f"Private input {PRIVATE}",
                },
                "usage": {"input_tokens": 7, "output_tokens": 0, "total_tokens": 7},
            },
        )

    with pytest.raises(ProviderCallError) as failure:
        foundry_adapter(handler, profile_overrides={"retry_limit": 0}).structured(request())
    caught = failure.value
    assert calls == [1]
    assert caught.code == "MODEL_PROVIDER_REJECTED"
    assert caught.observation.call_count == 1
    assert caught.observation.usage["prompt_tokens"] == 7
    error = AnalysisAttemptFailed(
        "PROVIDER_CALL", caught.code, caught.observation, provider_diagnostic=caught.diagnostic
    )
    raw, truncated = diagnostic_json(error)
    admin = _safe_diagnostic(raw, truncated)
    provider = admin["diagnostic"]["provider"]
    assert provider["http_status"] == status
    assert provider["request_id"] == REQUEST_ID
    assert provider["provider_code"] == code
    assert provider["provider_type"] == "invalid_request_error"
    assert provider["provider_message_redacted"] is True
    assert provider["response_received"] is True
    assert PRIVATE not in json.dumps([error.audit_details, admin])
    audit = _audit_details(json.dumps(error.audit_details))
    assert audit["error_code"] == "MODEL_PROVIDER_REJECTED"
    assert audit["call_count"] == 1
    assert "provider_diagnostic" not in audit  # Technical data uses the admin error-detail route.


def test_transport_failure_retains_type_without_message_or_false_azure_acknowledgement():
    def handler(wire):
        raise httpx.ReadTimeout(PRIVATE, request=wire) from httpx.ConnectError(PRIVATE)

    with pytest.raises(ProviderCallError) as failure:
        foundry_adapter(handler, profile_overrides={"retry_limit": 0}).structured(request())
    diagnostic = failure.value.diagnostic
    assert diagnostic["exception_type"] == "ReadTimeout"
    assert diagnostic["cause_type"] == "ConnectError"
    assert diagnostic["response_received"] is False
    assert "http_status" not in diagnostic
    assert failure.value.observation.call_count == 1
    assert PRIVATE not in json.dumps(diagnostic)


def test_unknown_remote_fields_never_become_persisted_or_readable_content():
    value = {
        "http_status": True,
        "http_reason": PRIVATE,
        "request_id": PRIVATE,
        "provider_code": PRIVATE,
        "provider_type": PRIVATE,
        "provider_message": PRIVATE,
        "exception_type": PRIVATE,
        "cause_type": PRIVATE,
        "Authorization": PRIVATE,
        "response_received": "true",
    }
    assert safe_provider_diagnostic(value) == {}
    assert (
        _audit_details(
            json.dumps({"provider_diagnostic": value, "error_code": PRIVATE, "stage": PRIVATE})
        )
        == {}
    )
    raw = json.dumps({"exception_type": "AnalysisAttemptFailed", "frames": [], "provider": value})
    assert _safe_diagnostic(raw, False) == {
        "diagnostic": {"exception_type": "AnalysisAttemptFailed", "frames": []},
        "truncated": False,
    }


def test_malformed_payload_and_headers_keep_http_fact_without_raw_bytes():
    value = response_diagnostic(
        402,
        {"x-ms-request-id": PRIVATE},
        {"error": {"code": {"private": PRIVATE}, "message": [PRIVATE]}},
    )
    assert value["http_status"] == 402
    assert value["provider_message_redacted"] is True
    assert PRIVATE not in json.dumps(value)
    assert "request_id" not in value


def test_cause_stack_survives_without_exception_values():
    try:
        try:
            raise ProviderCallError("MODEL_PROVIDER_REJECTED")
        except ProviderCallError as cause:
            raise AnalysisAttemptFailed("PROVIDER_CALL", cause.code, None) from cause
    except AnalysisAttemptFailed as error:
        raw, truncated = diagnostic_json(error)
    detail = _safe_diagnostic(raw, truncated)["diagnostic"]
    assert detail["causes"][0]["exception_type"] == "ProviderCallError"
    assert (
        detail["causes"][0]["frames"][-1]["function"]
        == "test_cause_stack_survives_without_exception_values"
    )
    assert "MODEL_PROVIDER_REJECTED" not in raw


def test_new_provider_facts_survive_postgresql_and_authorized_error_api(client, database):
    from uuid import UUID

    from conftest import sign_in

    owner = sign_in(client, "owner")
    facts = response_diagnostic(
        403,
        {"apim-request-id": REQUEST_ID},
        {"error": {
            "code": "PermissionDenied", "param": "text.format",
            "target": "max_output_tokens", "message": PRIVATE,
        }},
    )
    with database.session() as db:
        actor = db.active_actor(
            UUID(owner["actor"]["membership_id"]), UUID(owner["actor"]["identity_id"])
        )
        error = AnalysisAttemptFailed(
            "PROVIDER_CALL", "MODEL_PROVIDER_REJECTED", None, provider_diagnostic=facts
        )
        reference = db.record_system_error(actor, None, "CREATE_INTERPRETATION", error)
        db.commit()
    headers = {"X-Expected-Membership-Id": owner["actor"]["membership_id"]}
    response = client.get(f"/api/tenant-settings/errors/{reference}", headers=headers)
    assert response.status_code == 200
    assert response.json()["technical"]["diagnostic"]["provider"]["http_status"] == 403
    assert response.json()["technical"]["diagnostic"]["provider"]["request_id"] == REQUEST_ID
    assert response.json()["technical"]["diagnostic"]["provider"]["provider_param"] == "text.format"
    provider = response.json()["technical"]["diagnostic"]["provider"]
    assert provider["provider_target"] == "max_output_tokens"
    assert PRIVATE not in response.text


def test_response_headers_survive_failed_body_read_without_claiming_no_response():
    class FailedBody(httpx.SyncByteStream):
        def __iter__(self):
            raise httpx.ReadError(PRIVATE)
            yield b""

    def handler(wire):
        return httpx.Response(403, headers={"x-ms-request-id": REQUEST_ID}, stream=FailedBody())

    with pytest.raises(ProviderCallError) as failure:
        foundry_adapter(handler, profile_overrides={"retry_limit": 0}).structured(request())
    assert failure.value.diagnostic["response_received"] is True
    assert failure.value.diagnostic["http_status"] == 403
    assert failure.value.diagnostic["request_id"] == REQUEST_ID
    assert failure.value.diagnostic["exception_type"] == "ReadError"
    assert PRIVATE not in json.dumps(failure.value.diagnostic)


def test_bounded_cause_stack_marks_truncation():
    def recurse(depth):
        if depth:
            return recurse(depth - 1)
        raise ProviderCallError("MODEL_PROVIDER_REJECTED")

    try:
        try:
            recurse(8)
        except ProviderCallError as cause:
            raise AnalysisAttemptFailed("PROVIDER_CALL", cause.code, None) from cause
    except AnalysisAttemptFailed as error:
        raw, truncated = diagnostic_json(error)
    assert truncated is True
    assert len(json.loads(raw)["causes"][0]["frames"]) == 3
    assert len(raw.encode()) <= 4096


def test_direct_provider_error_keeps_facts_for_design_and_generation_paths():
    facts = response_diagnostic(
        400,
        {"x-ms-request-id": REQUEST_ID},
        {"error": {"code": "InvalidRequest", "message": PRIVATE}},
    )
    error = ProviderCallError("MODEL_PROVIDER_REJECTED", diagnostic=facts)
    raw, truncated = diagnostic_json(error)
    detail = _safe_diagnostic(raw, truncated)
    assert detail["diagnostic"]["provider"]["http_status"] == 400
    assert detail["diagnostic"]["provider"]["request_id"] == REQUEST_ID
    assert PRIVATE not in raw


@pytest.mark.parametrize("wire,field", [("param", "provider_param"), ("target", "provider_target")])
@pytest.mark.parametrize("parameter", [
    "input", "input[0].content", "text.format", "text.format.schema",
    "max_output_tokens", "stream", "store", "api-version",
])
def test_public_structured_parameters_survive_diagnostic_boundaries(wire, field, parameter):
    facts = response_diagnostic(400, {}, {"error": {
        "type": "invalid_request_error", wire: parameter, "message": PRIVATE,
    }})
    error = AnalysisAttemptFailed("PROVIDER_CALL", "MODEL_PROVIDER_REJECTED", None,
                                  provider_diagnostic=facts)
    raw, truncated = diagnostic_json(error)
    admin = _safe_diagnostic(raw, truncated)["diagnostic"]["provider"]
    assert admin[field] == parameter
    assert admin[field + "_redacted"] is False
    assert admin["provider_message_redacted"] is True
    assert PRIVATE not in json.dumps([error.audit_details, admin])


@pytest.mark.parametrize("untrusted", [PRIVATE, "text.format.schema.properties." + PRIVATE,
    "input[999999].content", {"name": PRIVATE}, [PRIVATE], 42, True])
def test_unknown_structured_identifiers_are_withheld_with_explicit_flags(untrusted):
    facts = response_diagnostic(400, {}, {"error": {
        "code": untrusted, "type": untrusted, "param": untrusted,
        "target": untrusted, "message": PRIVATE,
    }})
    for field in ("provider_code", "provider_type", "provider_param", "provider_target"):
        assert field not in facts
        assert facts[field + "_redacted"] is True
    assert PRIVATE not in json.dumps(facts)
    assert safe_provider_diagnostic(facts) == facts


def test_no_parameter_is_inferred_from_the_free_text_message_or_fabricated_for_old_records():
    facts = response_diagnostic(400, {}, {"error": {
        "type": "invalid_request_error", "message": "Unsupported parameter: 'store'. " + PRIVATE,
    }})
    assert "provider_param" not in facts and "provider_target" not in facts
    assert facts["provider_message_redacted"] is True
    old = {"http_status": 400, "provider_message_redacted": True,
           "provider_type": "invalid_request_error"}
    safe = safe_provider_diagnostic(old)
    assert "provider_param" not in safe and "provider_target" not in safe
    assert "provider_param_redacted" not in safe  # No invented historical observations.


def test_persisted_untrusted_parameter_fields_are_revalidated_not_reflected():
    raw = json.dumps({"exception_type": "AnalysisAttemptFailed", "frames": [], "provider": {
        "provider_param": PRIVATE, "provider_target": {"secret": PRIVATE},
        "provider_param_redacted": "yes", "provider_target_redacted": True,
    }})
    result = _safe_diagnostic(raw, False)
    assert result["diagnostic"]["provider"] == {"provider_target_redacted": True}
    assert PRIVATE not in json.dumps(result)


@pytest.mark.parametrize("message", [
    "Invalid parameter", "Invalid parameter.", "Invalid request.",
    "Invalid parameter: 'text.format'.", "Unsupported parameter: 'store'.",
    "Unknown parameter: 'max_output_tokens'.",
])
def test_exact_generic_or_public_parameter_messages_are_visible_without_private_values(message):
    facts = response_diagnostic(400, {}, {"error": {
        "type": "invalid_request_error", "message": message,
        "param": "text.format", "target": "max_output_tokens",
    }})
    error = AnalysisAttemptFailed("PROVIDER_CALL", "MODEL_PROVIDER_REJECTED", None,
                                  provider_diagnostic=facts)
    raw, truncated = diagnostic_json(error)
    provider = _safe_diagnostic(raw, truncated)["diagnostic"]["provider"]
    assert provider["provider_message"] == message
    assert provider["provider_message_redacted"] is False
    assert provider["provider_param"] == "text.format"
    assert provider["provider_target"] == "max_output_tokens"


@pytest.mark.parametrize("message", [
    "Invalid parameter. " + PRIVATE,
    "Invalid parameter: 'text.format'. " + PRIVATE,
    "Invalid parameter: '" + PRIVATE + "'.",
    "Invalid parameter: 'text.format.schema.properties." + PRIVATE + "'.",
    "Invalid parameter: 'text.format' of type 'json_schema' is not supported with model " + PRIVATE,
    "Invalid parameter.\nAuthorization: Bearer " + PRIVATE,
])
def test_public_message_prefix_never_permits_private_suffix_or_unknown_parameter(message):
    facts = response_diagnostic(400, {}, {"error": {"message": message}})
    assert "provider_message" not in facts
    assert facts["provider_message_redacted"] is True
    assert PRIVATE not in json.dumps(facts)


def test_recognized_message_never_fabricates_structured_parameter_fields():
    facts = response_diagnostic(400, {}, {"error": {
        "message": "Invalid parameter: 'text.format'.",
    }})
    assert facts["provider_message"] == "Invalid parameter: 'text.format'."
    assert "provider_param" not in facts and "provider_target" not in facts
