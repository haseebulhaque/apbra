from __future__ import annotations

import hashlib
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from io import BytesIO
from pathlib import Path
from threading import Barrier, Event
from uuid import uuid4

import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from apbra_api.api import create_app
from apbra_api.artifacts import LocalArtifactStore
from apbra_api.config import Settings
from apbra_api.domain import GenerationFailed
from apbra_api.generation import (
    GenerationBridge,
    GenerationBridgeFailure,
    _automatic_design_retry_instruction,
)
from apbra_api.model_provider import DeterministicFakeProvider, ProviderProfile
from apbra_api.persistence import ApplicationSession, Database


def confirmed_case(
    client: TestClient, session: dict[str, object], request: str, filename: str, content: bytes
) -> tuple[dict[str, object], dict[str, object]]:
    case = client.post(
        "/api/cases",
        json={"request_text": request},
        headers={**csrf(session), "Idempotency-Key": str(uuid4())},
    ).json()["case"]
    evidence = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": filename, "expected_context_version": 1},
        content=content,
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    contract = confirm_current_case(client, session, case["id"], evidence)
    return case, contract


def confirm_current_case(
    client: TestClient,
    session: dict[str, object],
    case_id: str,
    evidence: dict[str, object],
) -> dict[str, object]:
    interpretation = client.post(
        f"/api/cases/{case_id}/interpretations",
        json={"expected_context_version": evidence["semantic_context_version"]},
        headers=csrf(session),
    ).json()["interpretation"]
    if interpretation["state"] == "NEEDS_CLARIFICATION":
        question = interpretation["questions"][0]
        option = question["suggestions"][0]
        event = client.post(
            f"/api/cases/{case_id}/conversation",
            json={
                "kind": "RAW_ANSWER",
                "payload": {
                    "questionId": question["id"],
                    "interpretationId": interpretation["id"],
                    "rawAnswer": option["label"],
                    "suggestionId": option["id"],
                    "decision": "ACCEPT",
                },
                "expected_context_version": evidence["semantic_context_version"],
                "command_key": str(uuid4()),
            },
            headers=csrf(session),
        ).json()["event"]
        interpretation = client.post(
            f"/api/cases/{case_id}/interpretations",
            json={"expected_context_version": event["semantic_context_version"]},
            headers=csrf(session),
        ).json()["interpretation"]
    assert interpretation["state"] == "READY_FOR_CONFIRMATION"
    contract = client.post(
        f"/api/cases/{case_id}/confirm",
        json={
            "interpretation_id": interpretation["id"],
            "expected_context_version": interpretation["context_version"],
        },
        headers=csrf(session),
    ).json()["confirmed_contract"]
    contract["reviewed_report_design"] = reviewed_synthetic_report_design(contract["contract"])
    contract["reviewed_design_id"] = submit_reviewed_design(
        client, session, case_id, contract
    )
    return contract


def submit_reviewed_design(
    client: TestClient,
    case_session: dict[str, object],
    case_id: str,
    contract: dict[str, object],
) -> str:
    """Synthetic expert intake; the ordinary case actor does not approve a design."""
    with TestClient(client.app) as expert:
        expert_session = sign_in(expert, "uninvited")
        if "actor" not in expert_session:
            with TestClient(client.app) as owner:
                owner_session = sign_in(owner, "owner")
                invitation = owner.post(
                    "/api/invitations",
                    json={"subject": "dev-uninvited", "role": "EXPERT"},
                    headers=csrf(owner_session),
                )
                assert invitation.status_code == 200, invitation.text
                accepted = expert.post(
                    "/api/invitations/accept",
                    json={"token": invitation.json()["token"]},
                    headers=csrf(expert_session),
                )
                assert accepted.status_code == 200, accepted.text
            expert_session = expert.get("/api/auth/session").json()
        membership_id = expert_session["actor"]["membership_id"]
        access = client.get(f"/api/cases/{case_id}/access")
        assert access.status_code == 200, access.text
        if not any(
            item["membership_id"] == membership_id and item["active"]
            for item in access.json()["items"]
        ):
            granted = client.post(
                f"/api/cases/{case_id}/access",
                json={"membership_id": membership_id, "access_level": "EDITOR"},
                headers=csrf(case_session),
            )
            assert granted.status_code == 200, granted.text
        intake = expert.post(
            f"/api/cases/{case_id}/reviewed-designs",
            json={
                "confirmed_contract_id": contract["id"],
                "report_design": contract["reviewed_report_design"],
            },
            headers=csrf(expert_session),
        )
        assert intake.status_code == 201, intake.text
        return str(intake.json()["reviewed_design"]["id"])


def reviewed_synthetic_report_design(snapshot: dict[str, object]) -> dict[str, object]:
    """Explicit test-only design input; production never infers a layout from obligations."""
    obligations = snapshot["obligations"]
    assert isinstance(obligations, list)
    measures = {measure["id"]: measure for item in obligations for measure in item["measures"]}
    by_name = {measure["name"]: measure["id"] for measure in measures.values()}
    pages = []
    for page_index, page in enumerate(snapshot["pages"]):
        visuals = []
        for index, item in enumerate(obligations):
            if not item["required"] or page["name"] not in item["pageNames"]:
                continue
            fields = item["fields"]
            measure_ids = [by_name[name] for name in item["measureNames"]]
            title = " by ".join(
                [*item["measureNames"], *(field.split(".")[-1] for field in fields)]
            )
            for repeat in range(max(1, item["minimumRepresentations"])):
                kind = item["kind"]
                visual = {
                    "id": f"reviewed-{page_index}-{index}-{repeat}",
                    "type": {"FILTER": "slicer", "TREND": "line", "KPI": "card"}.get(kind, "bar"),
                    "title": title or "Reviewed synthetic visual",
                    "categoryField": fields[0]
                    if kind in {"TREND", "BREAKDOWN", "LIFECYCLE"}
                    else "",
                    "timeGrain": item["timeGrain"] if kind == "TREND" else "NONE",
                    "measureIds": [] if kind == "FILTER" else measure_ids,
                    "fields": fields[:1]
                    if kind == "FILTER"
                    else fields[1:]
                    if kind in {"BREAKDOWN", "LIFECYCLE"}
                    else [],
                    "altText": f"Reviewed synthetic presentation of {title}.",
                }
                visuals.append(visual)
        pages.append(
            {
                "id": f"reviewed-page-{page_index}",
                "name": page["name"],
                "purpose": "Synthetic test validation",
                "visuals": visuals,
            }
        )
    schema = snapshot["provenance"]["dataStructure"]
    table_names = [table["name"] for table in schema["tables"]]
    fact_names = {
        measure["field"].split(".")[0] for measure in measures.values() if measure["field"]
    }
    return {
        "artifact_kind": "ReportDesign",
        "schema_version": 1,
        "projectName": "ReviewedSyntheticCandidate",
        "overview": snapshot["objective"],
        "audience": snapshot["audience"],
        "dataModel": {
            "factTables": [name for name in table_names if name in fact_names],
            "dimensionTables": [name for name in table_names if name not in fact_names],
            "relationships": schema["relationships"],
        },
        "measures": list(measures.values()),
        "pages": pages,
        "filters": sorted(
            {field for item in obligations if item["kind"] == "FILTER" for field in item["fields"]}
        ),
        "branding": {"themeName": "Reviewed Synthetic", "primary": "#005A9C", "accent": "#2D7D9A"},
        "accessibility": ["Every test visual has a text alternative."],
        "standardsApplied": [
            {
                "citation": "local-knowledge:report-design-standards.md@1.0.0#RD-001",
                "decision": "Reviewed synthetic visual choice for validation only.",
            }
        ],
        "assumptions": [],
        "warnings": ["LOCAL_DETERMINISTIC_NO_MODEL_CALL: synthetic reviewed test design."],
        "generationRequirements": ["Validate the supplied design through the canonical pipeline."],
    }


def automatic_test_provider(responses: list[dict[str, object]]) -> DeterministicFakeProvider:
    call_limit = max(1, len(responses))
    return DeterministicFakeProvider(
        ProviderProfile.model_validate(
            {
                "profile_id": "qualified-test-profile",
                "protocol": "OPENAI_CHAT_COMPATIBLE",
                "endpoint": "https://provider.invalid/v1/chat/completions",
                "model_or_deployment": "qualified-test-model",
                "api_version": "test-version",
                "region": "test-region",
                "prompt_version": "report-design-v1",
                "configuration_id": "accepted-test-configuration",
                "capabilities": {"structured_output": True, "vision": False},
                "max_calls_per_operation": call_limit,
                "max_input_characters": 200_000,
                "max_output_tokens": 8_000,
                "time_budget_seconds": 30,
                "request_timeout_seconds": 10,
                "retry_limit": call_limit - 1,
            }
        ),
        responses,
    )


@pytest.mark.parametrize(
    ("business_request", "filename", "content"),
    [
        (
            "Show total appointment duration by clinic.",
            "appointments.csv",
            b"Clinic,Duration\nNorth,20\nSouth,35\n",
        ),
        (
            "Summarise attendance count by campus.",
            "attendance.csv",
            b"Campus,Attendance\nCity,120\nRural,95\n",
        ),
        (
            "Compare inventory units by storage zone.",
            "inventory.csv",
            b"Zone,Units\nA,40\nB,67\n",
        ),
    ],
)
def test_three_unrelated_domains_use_one_protected_generation_path(
    client: TestClient, business_request: str, filename: str, content: bytes
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(client, session, business_request, filename, content)
    command = str(uuid4())
    response = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": command,
        },
        headers=csrf(session),
    )
    assert response.status_code == 201, response.text
    attempt = response.json()["attempt"]
    assert attempt["status"] == "SUCCEEDED"
    assert attempt["validation"]["status"] == "PASS"
    assert attempt["provenance"]["mode"] == "LOCAL_DETERMINISTIC_NO_MODEL_CALL"
    download = client.get(f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact")
    assert download.status_code == 200
    assert hashlib.sha256(download.content).hexdigest() == attempt["artifact"]["content_digest"]
    assert download.headers["x-content-sha256"] == attempt["artifact"]["content_digest"]
    assert download.headers["cache-control"] == "private, no-store"
    with zipfile.ZipFile(BytesIO(download.content)) as archive:
        assert any(name.endswith(".pbip") for name in archive.namelist())
        assert "ReportDesign.json" in archive.namelist()


def test_automatic_design_is_untrusted_until_canonical_validation_and_can_build(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Compare resolved and unresolved requests by service team.",
        "requests.csv",
        b"Team,Resolved,Unresolved\nA,7,2\nB,5,4\n",
    )
    provider = automatic_test_provider(
        [{"untrusted": "not a report design"}, contract["reviewed_report_design"]]
    )
    with TestClient(
        create_app(settings=settings, database=database, model_provider=provider)
    ) as automatic_client:
        automatic_client.cookies.update(client.cookies)
        proposed = automatic_client.post(
            f"/api/cases/{case['id']}/automatic-designs",
            json={
                "confirmed_contract_id": contract["id"],
                "command_key": str(uuid4()),
            },
            headers=csrf(session),
        )
        assert proposed.status_code == 201, proposed.text
        result = proposed.json()
        assert result["attempt"]["status"] == "ELIGIBLE"
        assert result["attempt"]["validation"]["status"] == "PASS"
        assert result["attempt"]["provider_profile_id"] == "qualified-test-profile"
        assert result["attempt"]["usage"]["total_tokens"] == 60
        assert result["attempt"]["usage"]["call_count"] == 2
        assert result["reviewed_design"]["origin"] == "AUTO_ELIGIBLE"
        assert "report_design" not in result["reviewed_design"]
        assert provider.requests[0].task == "REPORT_DESIGN"
        assert "credential" not in provider.requests[0].context
        assert provider.requests[0].context["governedKnowledge"]
        checklist = provider.requests[0].context["coverageChecklist"]
        assert checklist["obligations"]
        assert checklist["dimensions"]
        assert all(set(item) == {"index"} for item in checklist["dimensions"])
        assert all(
            set(item)
            == {
                "index",
                "kind",
                "required",
                "minimumRepresentations",
                "measureCount",
                "fieldCount",
                "pageCount",
            }
            for item in checklist["obligations"]
        )
        prompt = provider.requests[0].system_prompt
        assert "exact complete canonical measure objects" in prompt
        assert "every confirmed required page exactly once" in prompt
        assert "Never create a slicer for a field already listed" in prompt
        assert "four general visual slots followed by two card-only slots" in prompt
        assert not any(
            fixture_term in prompt.lower()
            for fixture_term in ("retail", "store", "product", "sales")
        )
        assert automatic_client.get(f"/api/cases/{case['id']}").json()["case"][
            "report_title"
        ] == contract["reviewed_report_design"]["projectName"]

        built = automatic_client.post(
            f"/api/cases/{case['id']}/generation",
            json={
                "confirmed_contract_id": contract["id"],
                "reviewed_design_id": result["reviewed_design"]["id"],
                "command_key": str(uuid4()),
            },
            headers=csrf(session),
        )
        assert built.status_code == 201, built.text
        assert built.json()["attempt"]["status"] == "SUCCEEDED"


def test_invalid_automatic_design_is_failed_safely_without_losing_requirements(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Show qualified request totals by service team.",
        "requests.csv",
        b"Team,Requests\nA,7\nB,5\n",
    )
    provider = automatic_test_provider([{"untrusted": "not a report design"}])
    with TestClient(
        create_app(settings=settings, database=database, model_provider=provider)
    ) as automatic_client:
        automatic_client.cookies.update(client.cookies)
        rejected = automatic_client.post(
            f"/api/cases/{case['id']}/automatic-designs",
            json={
                "confirmed_contract_id": contract["id"],
                "command_key": str(uuid4()),
            },
            headers=csrf(session),
        )
        assert rejected.status_code == 409
        assert "untrusted" not in rejected.text
        history = automatic_client.get(
            f"/api/cases/{case['id']}/automatic-designs",
            params={"confirmed_contract_id": contract["id"]},
        )
        assert history.status_code == 200
        assert history.json()["items"][0]["status"] == "FAILED"
        assert history.json()["items"][0]["failure"]["code"]
        assert automatic_client.get(f"/api/cases/{case['id']}/acceptance").json()[
            "confirmed_contract"
        ]["current"] is True


@pytest.mark.parametrize("selector", ["member", "owner"])
def test_reviewed_design_intake_is_expert_only_and_business_response_is_non_raw(
    client: TestClient, database: Database, selector: str
) -> None:
    session = sign_in(client, selector)
    case, contract = confirmed_case(
        client, session, "Compare approved requests by group.", "requests.csv",
        b"Group,Approved\nA,4\nB,7\n",
    )
    listed = client.get(
        f"/api/cases/{case['id']}/reviewed-designs",
        params={"confirmed_contract_id": contract["id"]},
    )
    assert listed.status_code == 200
    assert listed.json()["can_build"] is True
    assert listed.json()["can_submit"] is False
    assert len(listed.json()["items"]) == 1
    reviewed = listed.json()["items"][0]
    assert reviewed["id"] == contract["reviewed_design_id"]
    assert reviewed["summary"]["page_count"] >= 1
    assert "report_design" not in reviewed
    assert "design_json" not in reviewed
    assert "approved" not in reviewed
    assert "reviewed_report_design" not in listed.text
    denied = client.post(
        f"/api/cases/{case['id']}/reviewed-designs",
        json={
            "confirmed_contract_id": contract["id"],
            "report_design": contract["reviewed_report_design"],
        },
        headers=csrf(session),
    )
    assert denied.status_code == 404
    client_assertion = client.post(
        f"/api/cases/{case['id']}/reviewed-designs",
        json={
            "confirmed_contract_id": contract["id"],
            "report_design": contract["reviewed_report_design"],
            "approved": True,
        },
        headers=csrf(session),
    )
    assert client_assertion.status_code == 422
    with database.session() as db:
        recorded = db.execute(
            text(
                "SELECT reviewer_membership_id, reviewer_identity_id, reviewer_role, "
                "binding_digest, content_digest, reviewed_at "
                "FROM reviewed_report_designs WHERE id=:id"
            ),
            {"id": reviewed["id"]},
        ).one()
    assert recorded.reviewer_role == "EXPERT"
    assert recorded.reviewer_membership_id is not None
    assert recorded.reviewer_identity_id is not None
    assert len(recorded.binding_digest) == len(recorded.content_digest) == 64
    assert recorded.reviewed_at is not None


def test_reviewed_design_is_immutable_and_digest_tamper_fails_closed(
    client: TestClient, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client, session, "Compare verified checks by unit.", "checks.csv",
        b"Unit,Verified\nNorth,5\nSouth,8\n",
    )
    design_id = contract["reviewed_design_id"]
    with database.session() as db:
        with pytest.raises(DBAPIError, match="reviewed report design is immutable"):
            db.execute(
                text("UPDATE reviewed_report_designs SET design_json='{}' WHERE id=:id"),
                {"id": design_id},
            )
        db.rollback()
        with pytest.raises(DBAPIError, match="reviewed report design is immutable"):
            db.execute(
                text("DELETE FROM reviewed_report_designs WHERE id=:id"),
                {"id": design_id},
            )
        db.rollback()
        db.execute(
            text(
                "ALTER TABLE reviewed_report_designs DISABLE TRIGGER "
                "trg_reviewed_design_immutable"
            )
        )
        db.execute(
            text("UPDATE reviewed_report_designs SET design_json='{}' WHERE id=:id"),
            {"id": design_id},
        )
        db.execute(
            text(
                "ALTER TABLE reviewed_report_designs ENABLE TRIGGER "
                "trg_reviewed_design_immutable"
            )
        )
    listed = client.get(
        f"/api/cases/{case['id']}/reviewed-designs",
        params={"confirmed_contract_id": contract["id"]},
    )
    assert listed.status_code == 200
    assert listed.json()["items"] == []
    blocked = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": design_id,
            "command_key": str(uuid4()),
        },
        headers=csrf(session),
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "TRUSTED_REPORT_DESIGN_REQUIRED"
    assert client.get(f"/api/cases/{case['id']}/generation").json()["items"] == []


@pytest.mark.parametrize(
    "membership_change", ["active=false", "role='COMPANY_ADMIN'"]
)
def test_revoked_expert_cannot_leave_a_design_build_eligible(
    client: TestClient, database: Database, membership_change: str
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client, session, "Show accepted units by location.", "units.csv",
        b"Location,Accepted\nA,3\nB,6\n",
    )
    with database.session() as db:
        reviewer_id = db.scalar(
            text("SELECT reviewer_membership_id FROM reviewed_report_designs WHERE id=:id"),
            {"id": contract["reviewed_design_id"]},
        )
        statement = (
            "UPDATE memberships SET active=false WHERE id=:id"
            if membership_change == "active=false"
            else "UPDATE memberships SET role='COMPANY_ADMIN' WHERE id=:id"
        )
        db.execute(text(statement), {"id": reviewer_id})
    blocked = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": str(uuid4()),
        },
        headers=csrf(session),
    )
    assert blocked.status_code == 422
    assert client.get(
        f"/api/cases/{case['id']}/reviewed-designs",
        params={"confirmed_contract_id": contract["id"]},
    ).json()["items"] == []


def test_reviewed_design_requires_current_private_case_access_for_reviewer(
    client: TestClient, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client, session, "Show approved items by group.", "items.csv",
        b"Group,Approved\nA,3\nB,5\n",
    )
    with database.session() as db:
        reviewer_id = db.scalar(
            text("SELECT reviewer_membership_id FROM reviewed_report_designs WHERE id=:id"),
            {"id": contract["reviewed_design_id"]},
        )
    revoke = client.post(
        f"/api/cases/{case['id']}/access/{reviewer_id}/revoke",
        headers=csrf(session),
    )
    assert revoke.status_code == 200, revoke.text
    assert client.get(
        f"/api/cases/{case['id']}/reviewed-designs",
        params={"confirmed_contract_id": contract["id"]},
    ).json()["items"] == []
    blocked = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": str(uuid4()),
        },
        headers=csrf(session),
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "TRUSTED_REPORT_DESIGN_REQUIRED"


def test_reviewed_design_submission_capability_requires_expert_edit_access(
    client: TestClient, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client, session, "Show approved items by group.", "items.csv",
        b"Group,Approved\nA,3\nB,5\n",
    )
    with database.session() as db:
        reviewer_id = db.scalar(
            text("SELECT reviewer_membership_id FROM reviewed_report_designs WHERE id=:id"),
            {"id": contract["reviewed_design_id"]},
        )
    with TestClient(client.app) as expert:
        expert_session = sign_in(expert, "uninvited")
        assert expert_session["actor"]["role"] == "EXPERT"
        listed = expert.get(
            f"/api/cases/{case['id']}/reviewed-designs",
            params={"confirmed_contract_id": contract["id"]},
        )
        assert listed.status_code == 200
        assert listed.json()["can_build"] is True
        assert listed.json()["can_submit"] is True
        revoked = client.post(
            f"/api/cases/{case['id']}/access/{reviewer_id}/revoke",
            headers=csrf(session),
        )
        assert revoked.status_code == 200
        granted = client.post(
            f"/api/cases/{case['id']}/access",
            json={"membership_id": str(reviewer_id), "access_level": "VIEWER"},
            headers=csrf(session),
        )
        assert granted.status_code == 200
        viewer_listing = expert.get(
            f"/api/cases/{case['id']}/reviewed-designs",
            params={"confirmed_contract_id": contract["id"]},
        )
        assert viewer_listing.status_code == 200
        assert viewer_listing.json()["can_build"] is False
        assert viewer_listing.json()["can_submit"] is False
        denied = expert.post(
            f"/api/cases/{case['id']}/reviewed-designs",
            json={
                "confirmed_contract_id": contract["id"],
                "report_design": contract["reviewed_report_design"],
            },
            headers=csrf(expert_session),
        )
        assert denied.status_code == 404


def test_viewer_can_inspect_eligible_plan_but_cannot_build_or_cancel(
    client: TestClient,
) -> None:
    owner_session = sign_in(client, "owner")
    case, contract = confirmed_case(
        client, owner_session, "Compare approved cases by group.", "cases.csv",
        b"Group,Approved\nA,3\nB,5\n",
    )
    with TestClient(client.app) as viewer:
        viewer_session = sign_in(viewer, "member")
        granted = client.post(
            f"/api/cases/{case['id']}/access",
            json={
                "membership_id": viewer_session["actor"]["membership_id"],
                "access_level": "VIEWER",
            },
            headers=csrf(owner_session),
        )
        assert granted.status_code == 200, granted.text
        listed = viewer.get(
            f"/api/cases/{case['id']}/reviewed-designs",
            params={"confirmed_contract_id": contract["id"]},
        )
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 1
        assert listed.json()["can_build"] is False
        assert listed.json()["can_submit"] is False
        denied = viewer.post(
            f"/api/cases/{case['id']}/generation",
            json={
                "confirmed_contract_id": contract["id"],
                "reviewed_design_id": contract["reviewed_design_id"],
                "command_key": str(uuid4()),
            },
            headers=csrf(viewer_session),
        )
        assert denied.status_code == 404
        generated = client.post(
            f"/api/cases/{case['id']}/generation",
            json={
                "confirmed_contract_id": contract["id"],
                "reviewed_design_id": contract["reviewed_design_id"],
                "command_key": str(uuid4()),
            },
            headers=csrf(owner_session),
        )
        assert generated.status_code == 201, generated.text
        cancelled = viewer.post(
            f"/api/cases/{case['id']}/generation/{generated.json()['attempt']['id']}/cancel",
            headers=csrf(viewer_session),
        )
        assert cancelled.status_code == 404


def test_generation_is_idempotent_preserves_history_and_rejects_stale_confirmation(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Show total hours by team.",
        "work.csv",
        b"Team,Hours\nAlpha,12\nBeta,18\n",
    )
    command = str(uuid4())
    first = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": command,
        },
        headers=csrf(session),
    ).json()["attempt"]
    repeated = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": command,
        },
        headers=csrf(session),
    )
    assert repeated.status_code == 200
    assert repeated.json()["attempt"]["id"] == first["id"]
    conflicting_command = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": command,
            "mode": "REGENERATE",
        },
        headers=csrf(session),
    )
    assert conflicting_command.status_code == 409
    assert conflicting_command.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    regenerated = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": str(uuid4()),
            "mode": "REGENERATE",
        },
        headers=csrf(session),
    ).json()["attempt"]
    assert regenerated["id"] != first["id"]
    assert regenerated["supersedes_attempt_id"] == first["id"]
    history = client.get(f"/api/cases/{case['id']}/generation").json()["items"]
    assert [item["id"] for item in history] == [regenerated["id"], first["id"]]
    updated = client.put(
        f"/api/cases/{case['id']}",
        json={"request_text": "Show a materially changed report.", "expected_version": 1},
        headers=csrf(session),
    )
    assert updated.status_code == 200
    stale = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": str(uuid4()),
        },
        headers=csrf(session),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_VERSION"
    replacement_evidence = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={
            "filename": "revised-work.csv",
            "expected_context_version": updated.json()["case"]["semantic_context_version"],
        },
        content=b"Team,Hours\nGamma,24\nDelta,16\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    ).json()["evidence"]
    replacement_contract = confirm_current_case(client, session, case["id"], replacement_evidence)
    changed = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": replacement_contract["id"],
            "reviewed_design_id": replacement_contract["reviewed_design_id"],
            "command_key": str(uuid4()),
            "mode": "REGENERATE",
        },
        headers=csrf(session),
    )
    assert changed.status_code == 201
    assert changed.json()["attempt"]["supersedes_attempt_id"] == regenerated["id"]


def test_regeneration_can_select_another_reviewed_design_without_rewriting_history(
    client: TestClient, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client, session, "Compare verified units by team.", "units.csv",
        b"Team,Verified\nNorth,4\nSouth,7\n",
    )
    first_design = contract["reviewed_design_id"]
    second_design = submit_reviewed_design(client, session, case["id"], contract)
    assert second_design != first_design
    first = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": first_design,
            "command_key": str(uuid4()),
        },
        headers=csrf(session),
    )
    assert first.status_code == 201, first.text
    regenerated = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": second_design,
            "command_key": str(uuid4()),
            "mode": "REGENERATE",
        },
        headers=csrf(session),
    )
    assert regenerated.status_code == 201, regenerated.text
    history = client.get(f"/api/cases/{case['id']}/generation").json()["items"]
    assert [item["reviewed_design_id"] for item in history] == [second_design, first_design]
    assert history[0]["supersedes_attempt_id"] == history[1]["id"]
    assert all(item["artifact"] is not None for item in history)
    with database.session() as db:
        with pytest.raises(DBAPIError, match="immutable"):
            db.execute(
                text("UPDATE generation_attempts SET reviewed_design_id=:new WHERE id=:id"),
                {"new": second_design, "id": history[1]["id"]},
            )
        db.rollback()


def test_missing_reviewed_design_fails_before_attempt_and_cannot_consume_command(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Show completed checks by group.",
        "checks.csv",
        b"Group,Completed\nA,3\nB,5\n",
    )
    command = str(uuid4())
    missing = client.post(
        f"/api/cases/{case['id']}/generation",
        json={"confirmed_contract_id": contract["id"], "command_key": command},
        headers=csrf(session),
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "TRUSTED_REPORT_DESIGN_REQUIRED"
    assert client.get(f"/api/cases/{case['id']}/generation").json()["items"] == []
    built = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "command_key": command,
            "reviewed_design_id": contract["reviewed_design_id"],
        },
        headers=csrf(session),
    )
    assert built.status_code == 201
    assert built.json()["attempt"]["status"] == "SUCCEEDED"
    assert built.json()["attempt"]["reviewed_design_id"] == contract["reviewed_design_id"]
    raw_browser_command = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "command_key": str(uuid4()),
            "report_design": contract["reviewed_report_design"],
        },
        headers=csrf(session),
    )
    assert raw_browser_command.status_code == 422
    assert raw_browser_command.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"
    history = client.get(f"/api/cases/{case['id']}/generation").json()["items"]
    assert [item["id"] for item in history] == [built.json()["attempt"]["id"]]


def test_pipeline_failure_is_durable_and_never_downloadable(
    client: TestClient, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Show total cost by category.",
        "costs.csv",
        b"Category,Cost\nA,10\nB,20\n",
    )

    def fail(_self: GenerationBridge, _payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("synthetic bridge failure")

    monkeypatch.setattr(GenerationBridge, "generate", fail)
    response = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": str(uuid4()),
        },
        headers=csrf(session),
    )
    assert response.status_code == 201
    attempt = response.json()["attempt"]
    assert attempt["status"] == "FAILED"
    assert attempt["artifact"] is None
    assert (
        client.get(f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact").status_code
        == 404
    )
    with database.session() as db:
        audit_events = list(
            db.scalars(
                text(
                    "SELECT event_type FROM audit_events "
                    "WHERE resource_type='GENERATION_ATTEMPT' AND resource_id=:attempt_id "
                    "ORDER BY created_at, event_type"
                ),
                {"attempt_id": attempt["id"]},
            )
        )
    assert audit_events == ["GENERATION_STARTED", "GENERATION_FAILED"]


def test_equivalent_concurrent_commands_collapse_to_one_durable_attempt(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Compare completed work by department.",
        "work.csv",
        b"Department,Completed\nOperations,14\nFinance,9\n",
    )
    command = str(uuid4())
    barrier = Barrier(2)
    candidates = [TestClient(create_app(settings=settings, database=database)) for _ in range(2)]
    for candidate in candidates:
        candidate.cookies.update(client.cookies)

    def build(candidate: TestClient) -> tuple[int, str]:
        barrier.wait()
        response = candidate.post(
            f"/api/cases/{case['id']}/generation",
            json={
                "confirmed_contract_id": contract["id"],
                "reviewed_design_id": contract["reviewed_design_id"],
                "command_key": command,
            },
            headers=csrf(session),
        )
        return response.status_code, response.json()["attempt"]["id"]

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(build, candidates))
    finally:
        for candidate in candidates:
            candidate.close()

    assert sorted(status for status, _identifier in results) == [200, 201]
    assert len({identifier for _status, identifier in results}) == 1
    history = client.get(f"/api/cases/{case['id']}/generation").json()["items"]
    assert len(history) == 1
    assert history[0]["status"] == "SUCCEEDED"


def test_cancel_fences_late_pipeline_result_and_retry_creates_new_attempt(
    client: TestClient,
    settings: Settings,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Show processed claims by queue.",
        "claims.csv",
        b"Queue,Processed\nStandard,21\nPriority,8\n",
    )
    entered, release = Event(), Event()
    original = GenerationBridge.generate

    def wait_then_generate(
        bridge: GenerationBridge, payload: dict[str, object]
    ) -> dict[str, object]:
        entered.set()
        assert release.wait(timeout=10)
        return original(bridge, payload)

    monkeypatch.setattr(GenerationBridge, "generate", wait_then_generate)
    candidate = TestClient(create_app(settings=settings, database=database))
    candidate.cookies.update(client.cookies)

    def build():
        return candidate.post(
            f"/api/cases/{case['id']}/generation",
            json={
                "confirmed_contract_id": contract["id"],
                "reviewed_design_id": contract["reviewed_design_id"],
                "command_key": str(uuid4()),
            },
            headers=csrf(session),
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(build)
            assert entered.wait(timeout=10)
            running = client.get(f"/api/cases/{case['id']}/generation").json()["items"][0]
            cancelled = client.post(
                f"/api/cases/{case['id']}/generation/{running['id']}/cancel",
                headers=csrf(session),
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["attempt"]["status"] == "CANCELLED"
            release.set()
            completed = future.result(timeout=15)
    finally:
        release.set()
        candidate.close()

    assert completed.status_code == 201
    assert completed.json()["attempt"]["status"] == "CANCELLED"
    assert completed.json()["attempt"]["artifact"] is None
    monkeypatch.setattr(GenerationBridge, "generate", original)
    alternate_design = submit_reviewed_design(client, session, case["id"], contract)
    wrong_retry = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": alternate_design,
            "command_key": str(uuid4()),
            "mode": "RETRY",
            "source_attempt_id": completed.json()["attempt"]["id"],
        },
        headers=csrf(session),
    )
    assert wrong_retry.status_code == 409
    retry = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": str(uuid4()),
            "mode": "RETRY",
            "source_attempt_id": completed.json()["attempt"]["id"],
        },
        headers=csrf(session),
    )
    assert retry.status_code == 201
    assert retry.json()["attempt"]["status"] == "SUCCEEDED"
    assert retry.json()["attempt"]["retry_of_attempt_id"] == completed.json()["attempt"]["id"]


def test_history_and_artifact_survive_restart_but_remain_company_private(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Summarise approved applications by region.",
        "applications.csv",
        b"Region,Approved\nEast,17\nWest,22\n",
    )
    attempt = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": str(uuid4()),
        },
        headers=csrf(session),
    ).json()["attempt"]

    restarted_database = Database(settings.database_url)
    history_only_settings = settings.model_copy(
        update={"generation_bridge_path": Path("/nonexistent/generation-bridge.mjs")}
    )
    with TestClient(
        create_app(settings=history_only_settings, database=restarted_database)
    ) as restarted:
        restarted.cookies.update(client.cookies)
        history = restarted.get(f"/api/cases/{case['id']}/generation")
        assert history.status_code == 200
        assert history.json()["items"][0]["id"] == attempt["id"]
        artifact = restarted.get(f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact")
        assert artifact.status_code == 200
        assert hashlib.sha256(artifact.content).hexdigest() == attempt["artifact"]["content_digest"]
        unavailable = restarted.post(
            f"/api/cases/{case['id']}/generation",
            json={
                "confirmed_contract_id": contract["id"],
                "reviewed_design_id": contract["reviewed_design_id"],
                "command_key": str(uuid4()),
                "mode": "REGENERATE",
            },
            headers=csrf(session),
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "CONFIGURATION_UNAVAILABLE"
    restarted_database.engine.dispose()

    foreign = TestClient(create_app(settings=settings, database=database))
    try:
        sign_in(foreign, "foreign")
        assert foreign.get(f"/api/cases/{case['id']}/generation").status_code == 404
        assert (
            foreign.get(f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact").status_code
            == 404
        )
    finally:
        foreign.close()


def test_artifact_integrity_failure_is_fail_closed(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Show resolved tickets by service.",
        "tickets.csv",
        b"Service,Resolved\nNetwork,11\nDevices,7\n",
    )
    attempt = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": str(uuid4()),
        },
        headers=csrf(session),
    ).json()["attempt"]
    with database.session() as db:
        storage_key = db.scalar(
            text("SELECT storage_key FROM generated_artifacts WHERE id=:artifact_id"),
            {"artifact_id": attempt["artifact"]["id"]},
        )
    assert isinstance(storage_key, str)
    settings.artifact_root.joinpath(*storage_key.split("/")).write_bytes(b"tampered")
    response = client.get(f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ARTIFACT_NOT_FOUND"


def test_terminal_attempt_and_artifact_history_are_database_immutable(
    client: TestClient, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Compare dispatched orders by route.",
        "dispatch.csv",
        b"Route,Dispatched\nNorth,19\nSouth,23\n",
    )
    attempt = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": str(uuid4()),
        },
        headers=csrf(session),
    ).json()["attempt"]
    with database.session() as db:
        with pytest.raises(DBAPIError, match="terminal generation attempt is immutable"):
            db.execute(
                text("UPDATE generation_attempts SET status='FAILED' WHERE id=:id"),
                {"id": attempt["id"]},
            )
        db.rollback()
        with pytest.raises(DBAPIError, match="generated artifact is immutable"):
            db.execute(
                text("UPDATE generated_artifacts SET filename='changed.zip' WHERE id=:id"),
                {"id": attempt["artifact"]["id"]},
            )
        db.rollback()


def test_generation_bridge_rejects_unsafe_executables_timeout_and_malformed_output(
    tmp_path: Path,
) -> None:
    node = Path(shutil.which("node") or "/nonexistent/node")
    valid = tmp_path / "bridge.mjs"
    valid.write_text(
        "process.stdout.write(JSON.stringify({ok:true,value:{files:{'../escape':'x'},"
        "validation:{status:'PASS'}}}))",
        encoding="utf-8",
    )
    symlink = tmp_path / "bridge-link.mjs"
    symlink.symlink_to(valid)
    with pytest.raises(ValueError, match="fixed regular file"):
        GenerationBridge(symlink, node_executable=node, timeout_seconds=1)

    node_link = tmp_path / "node-link"
    node_link.symlink_to(node)
    linked_runtime = GenerationBridge(valid, node_executable=node_link, timeout_seconds=1)
    assert linked_runtime.node_executable == node.resolve(strict=True)
    broken_runtime = tmp_path / "broken-node"
    broken_runtime.symlink_to(tmp_path / "missing-node")
    for invalid in (broken_runtime, tmp_path, tmp_path / "missing-node"):
        with pytest.raises(ValueError, match="executable regular file"):
            GenerationBridge(valid, node_executable=invalid, timeout_seconds=1)
    not_executable = tmp_path / "not-executable"
    not_executable.write_text("node", encoding="utf-8")
    not_executable.chmod(0o600)
    with pytest.raises(ValueError, match="executable regular file"):
        GenerationBridge(valid, node_executable=not_executable, timeout_seconds=1)

    bridge = GenerationBridge(valid, node_executable=node, timeout_seconds=1)
    marker = tmp_path / "must-not-exist"
    with pytest.raises(GenerationFailed):
        bridge.generate({"untrusted": f"$(touch {marker})"})
    assert not marker.exists()

    valid.write_text("setTimeout(()=>{}, 5000)", encoding="utf-8")
    with pytest.raises(GenerationFailed):
        bridge.generate({"bounded": True})
    with pytest.raises(GenerationFailed):
        GenerationBridge(valid, node_executable=node, timeout_seconds=1).generate({"bounded": True})

    oversized = tmp_path / "oversized.mjs"
    oversized.write_text("process.stdout.write('x'.repeat(20000001))", encoding="utf-8")
    with pytest.raises(GenerationFailed):
        GenerationBridge(oversized, node_executable=node, timeout_seconds=5).generate(
            {"binding": {}, "execution": {}}
        )

    mismatched = tmp_path / "mismatched.mjs"
    mismatched.write_text(
        "process.stdout.write(JSON.stringify({ok:true,value:{files:{'safe.txt':'x'},"
        "validation:{status:'PASS'},provenance:{binding:{caseId:'wrong'},"
        "execution:{inputDigest:'wrong'}}}}))",
        encoding="utf-8",
    )
    with pytest.raises(GenerationFailed):
        GenerationBridge(mismatched, node_executable=node, timeout_seconds=2).generate(
            {"binding": {"caseId": "expected"}, "execution": {"inputDigest": "expected"}}
        )

    diagnostic = tmp_path / "diagnostic.mjs"
    diagnostic.write_text(
        "process.stdout.write(JSON.stringify({ok:false,error:{"
        "code:'REPORT_DESIGN_SEMANTICS_FAILED',"
        "message:'REPORT_DESIGN_SEMANTICS_FAILED: REQUIRED_BREAKDOWN_UNCOVERED'}}));"
        "process.exitCode=1",
        encoding="utf-8",
    )
    with pytest.raises(GenerationBridgeFailure) as captured:
        GenerationBridge(diagnostic, node_executable=node, timeout_seconds=2).generate(
            {"binding": {}, "execution": {}}
        )
    assert captured.value.diagnostic_code == "REPORT_DESIGN_SEMANTICS_FAILED"
    assert captured.value.diagnostic_message.endswith("REQUIRED_BREAKDOWN_UNCOVERED")


def test_layout_retry_is_order_only_and_other_rejections_remain_generic() -> None:
    layout = _automatic_design_retry_instruction(
        GenerationBridgeFailure(
            "REPORT_DESIGN_NORMALIZATION_FAILED",
            "REPORT_DESIGN_NORMALIZATION_FAILED: LAYOUT_CAPACITY_EXCEEDED",
        ),
        max_visuals_per_page=6,
    )
    assert "changing only the order" in layout
    assert "do not add, remove, move between pages" in layout
    assert "validated 6-visual page limit" in layout
    assert "physical slots reported as in bounds" in layout
    semantic = _automatic_design_retry_instruction(
        GenerationBridgeFailure(
            "REPORT_DESIGN_SEMANTICS_FAILED",
            "REPORT_DESIGN_SEMANTICS_FAILED: REQUIRED_BREAKDOWN_UNCOVERED",
        ),
        max_visuals_per_page=6,
    )
    assert "changing only the order" not in semantic
    assert "zero-based index" in semantic
    assert "do not trade one covered requirement for another" in semantic
    unknown_detail = "credential=must-not-be-forwarded"
    unknown = _automatic_design_retry_instruction(
        GenerationBridgeFailure("GENERATION_PIPELINE_FAILED", unknown_detail),
        max_visuals_per_page=6,
    )
    assert "GENERATION_PIPELINE_FAILED" in unknown
    assert unknown_detail not in unknown


def test_authorization_revocation_waits_for_eligibility_commit(
    client: TestClient,
    settings: Settings,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Compare verified shipments by depot.",
        "shipments.csv",
        b"Depot,Verified\nNorth,13\nSouth,17\n",
    )
    entered, release = Event(), Event()
    original_write = LocalArtifactStore.write

    def blocked_write(self, company_id, case_id, attempt_id, content):
        entered.set()
        assert release.wait(timeout=10)
        return original_write(self, company_id, case_id, attempt_id, content)

    monkeypatch.setattr(LocalArtifactStore, "write", blocked_write)
    candidate = TestClient(create_app(settings=settings, database=database))
    candidate.cookies.update(client.cookies)

    def revoke() -> None:
        with database.session() as db:
            db.execute(
                text("UPDATE memberships SET active=false WHERE id=:id"),
                {"id": session["actor"]["membership_id"]},
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            build = executor.submit(
                candidate.post,
                f"/api/cases/{case['id']}/generation",
                json={
                    "confirmed_contract_id": contract["id"],
                    "reviewed_design_id": contract["reviewed_design_id"],
                    "command_key": str(uuid4()),
                },
                headers=csrf(session),
            )
            assert entered.wait(timeout=10)
            revocation = executor.submit(revoke)
            with pytest.raises(FutureTimeoutError):
                revocation.result(timeout=0.25)
            release.set()
            response = build.result(timeout=15)
            revocation.result(timeout=10)
    finally:
        release.set()
        candidate.close()
    assert response.json()["attempt"]["status"] == "SUCCEEDED"
    assert client.get(f"/api/cases/{case['id']}/generation").status_code in {401, 404}


def test_nonterminal_identity_and_cross_attempt_artifact_binding_are_rejected(
    client: TestClient,
    settings: Settings,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = sign_in(client, "member")
    first_case, first_contract = confirmed_case(
        client,
        session,
        "Show accepted invoices by ledger.",
        "invoices.csv",
        b"Ledger,Accepted\nA,8\nB,12\n",
    )
    first = client.post(
        f"/api/cases/{first_case['id']}/generation",
        json={
            "confirmed_contract_id": first_contract["id"],
            "reviewed_design_id": first_contract["reviewed_design_id"],
            "command_key": str(uuid4()),
        },
        headers=csrf(session),
    ).json()["attempt"]
    second_case, second_contract = confirmed_case(
        client,
        session,
        "Show reviewed invoices by ledger.",
        "reviewed.csv",
        b"Ledger,Reviewed\nA,9\nB,14\n",
    )
    entered, release = Event(), Event()
    original = GenerationBridge.generate

    def wait_then_generate(bridge: GenerationBridge, payload: dict[str, object]):
        entered.set()
        assert release.wait(timeout=10)
        return original(bridge, payload)

    monkeypatch.setattr(GenerationBridge, "generate", wait_then_generate)
    candidate = TestClient(create_app(settings=settings, database=database))
    candidate.cookies.update(client.cookies)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                candidate.post,
                f"/api/cases/{second_case['id']}/generation",
                json={
                    "confirmed_contract_id": second_contract["id"],
                    "reviewed_design_id": second_contract["reviewed_design_id"],
                    "command_key": str(uuid4()),
                },
                headers=csrf(session),
            )
            assert entered.wait(timeout=10)
            with database.session() as db:
                running_id = db.scalar(
                    text(
                        "SELECT id FROM generation_attempts "
                        "WHERE case_id=:case_id AND status='RUNNING'"
                    ),
                    {"case_id": second_case["id"]},
                )
                with pytest.raises(DBAPIError, match="generation identity is immutable"):
                    db.execute(
                        text(
                            "UPDATE generation_attempts SET "
                            "created_at=created_at + interval '1 second' "
                            "WHERE id=:id"
                        ),
                        {"id": running_id},
                    )
                db.rollback()
                with pytest.raises(DBAPIError):
                    db.execute(
                        text(
                            "UPDATE generation_attempts SET status='SUCCEEDED', "
                            "artifact_id=:artifact_id, validation_json='{}', completed_at=now() "
                            "WHERE id=:id"
                        ),
                        {"id": running_id, "artifact_id": first["artifact"]["id"]},
                    )
                db.rollback()
            release.set()
            response = future.result(timeout=15)
    finally:
        release.set()
        candidate.close()
    assert response.json()["attempt"]["status"] == "SUCCEEDED"


def test_revoked_membership_before_late_result_prevents_artifact_eligibility(
    client: TestClient,
    settings: Settings,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Compare completed deliveries by hub.",
        "deliveries.csv",
        b"Hub,Completed\nEast,15\nWest,19\n",
    )
    entered, release = Event(), Event()
    original = GenerationBridge.generate

    def wait_then_generate(
        bridge: GenerationBridge, payload: dict[str, object]
    ) -> dict[str, object]:
        entered.set()
        assert release.wait(timeout=10)
        return original(bridge, payload)

    monkeypatch.setattr(GenerationBridge, "generate", wait_then_generate)
    candidate = TestClient(create_app(settings=settings, database=database))
    candidate.cookies.update(client.cookies)
    prior_artifacts = set(settings.artifact_root.rglob("*.zip"))
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                candidate.post,
                f"/api/cases/{case['id']}/generation",
                json={
                    "confirmed_contract_id": contract["id"],
                    "reviewed_design_id": contract["reviewed_design_id"],
                    "command_key": str(uuid4()),
                },
                headers=csrf(session),
            )
            assert entered.wait(timeout=10)
            with database.session() as db:
                db.execute(
                    text("UPDATE memberships SET active=false WHERE id=:id"),
                    {"id": session["actor"]["membership_id"]},
                )
            release.set()
            response = future.result(timeout=15)
    finally:
        release.set()
        candidate.close()
    attempt = response.json()["attempt"]
    assert attempt["status"] == "FAILED"
    assert attempt["artifact"] is None
    assert set(settings.artifact_root.rglob("*.zip")) == prior_artifacts


def test_database_failure_after_artifact_write_removes_uncommitted_bytes(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Compare reconciled balances by account group.",
        "balances.csv",
        b"AccountGroup,Balance\nCurrent,31\nReserve,12\n",
    )

    def reject_artifact(*_args, **_kwargs):
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr(ApplicationSession, "add_generated_artifact", reject_artifact)
    prior_artifacts = set(settings.artifact_root.rglob("*.zip"))
    response = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": str(uuid4()),
        },
        headers=csrf(session),
    )
    assert response.status_code == 201
    assert response.json()["attempt"]["status"] == "FAILED"
    assert response.json()["attempt"]["artifact"] is None
    assert set(settings.artifact_root.rglob("*.zip")) == prior_artifacts
