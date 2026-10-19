"Fresh technical explanation persistence and admin readback, synthetic database only."

import json
from uuid import UUID

import pytest
from conftest import sign_in

from apbra_api.application import AnalysisAttemptFailed
from apbra_api.provider_diagnostics import response_diagnostic

PRIVATE = "PRIVATE-REPORT-CREDENTIAL-CANARY"


@pytest.mark.parametrize(
    "message,template",
    [
        (
            "The text parameter is not supported for published agents.",
            "AGENT_PARAMETER_UNSUPPORTED",
        ),
        (
            (
                "Invalid parameter: 'text.format' of type 'json_schema' is not sup"
                "ported with model version '"
            )
            + PRIVATE
            + "'.",
            "MODEL_FORMAT_UNSUPPORTED",
        ),
        (
            "Structured outputs are not supported with Foundry Agents Service.",
            "AGENT_FORMAT_UNSUPPORTED",
        ),
    ],
)
def test_new_technical_message_survives_real_postgresql_and_authorized_readback(
    client, database, message, template
):
    owner = sign_in(client, "owner")
    facts = response_diagnostic(
        400, {}, {"error": {"type": "invalid_request_error", "param": "text", "message": message}}
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
    response = client.get(
        f"/api/tenant-settings/errors/{reference}",
        headers={"X-Expected-Membership-Id": owner["actor"]["membership_id"]},
    )
    assert response.status_code == 200
    provider = response.json()["technical"]["diagnostic"]["provider"]
    assert provider["provider_message_template"] == template
    assert provider["provider_message"]
    assert provider["provider_param"] == "text"
    assert PRIVATE not in response.text
    with database.session() as db:
        from sqlalchemy import select

        from apbra_api.persistence import SystemErrorDiagnosticRow

        stored = db.scalar(
            select(SystemErrorDiagnosticRow).where(SystemErrorDiagnosticRow.error_id == reference)
        )
        assert PRIVATE not in stored.technical_json
        assert (
            json.loads(stored.technical_json)["provider"]["provider_message"]
            == provider["provider_message"]
        )
