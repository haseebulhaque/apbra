"""Synthetic native object -> explicit confirmation -> existing protected artifact."""

import hashlib
import json
import zipfile
from io import BytesIO
from uuid import UUID, uuid4

import pytest
import test_native_response_integration as native_fixtures
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_conversations import provider_analysis
from test_foundry_report_runtime import bound_approval
from test_native_response_integration import dispatch

from apbra_api.api import create_app
from apbra_api.foundry_report_runtime import Reservations
from apbra_api.native_response_index import NativeContractBindingRow
from apbra_api.native_response_runtime import native_application_factory

integrated = native_fixtures.integrated
saved_case = native_fixtures.saved_case


def native_body(value):
    return json.dumps(
        {
            "status": "completed",
            "output": [
                {"type": "mcp_list_tools", "status": "completed"},
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(value),
                            "annotations": [
                                {"type": "file_citation", "file_id": "synthetic-standard"}
                            ],
                        }
                    ],
                },
            ],
            "usage": {"input_tokens": 12, "output_tokens": 20, "total_tokens": 32},
        }
    ).encode()


def analysis_fixture():
    # Deliberately transformed test fixture, never production inference.
    return json.loads(
        json.dumps(provider_analysis(ready=True))
        .replace("Metrics.Visits", "synthetic.Amount")
        .replace("Metrics.Campus", "synthetic.Division")
        .replace("Visits", "Amount")
        .replace("Campus", "Division")
    )


def design_fixture():
    return {
        "artifact_kind": "ReportDesign",
        "schema_version": 2,
        "projectName": "SyntheticNativeAmount",
        "overview": "Synthetic native contract test",
        "audience": "Synthetic reviewers",
        "dataModel": {"factTables": ["synthetic"], "dimensionTables": [], "relationships": []},
        "measures": [
            {
                "id": "amount",
                "name": "Total Amount",
                "businessDefinition": "Sum amount",
                "aggregation": "SUM",
                "field": "synthetic.Amount",
                "format": "integer",
                "numeratorMeasureId": "",
                "denominatorMeasureId": "",
            }
        ],
        "pages": [
            {
                "id": "summary",
                "name": "Summary",
                "purpose": "Test only",
                "displayOption": "FitToWidth",
                "width": 1200,
                "height": 700,
                "visuals": [
                    {
                        "id": "division",
                        "type": "bar",
                        "title": "Amount by division",
                        "categoryField": "synthetic.Division",
                        "timeGrain": "NONE",
                        "measureIds": ["amount"],
                        "fields": [],
                        "altText": "Synthetic amount by division",
                        "position": {"x": 12.5, "y": 30.25, "width": 450, "height": 250},
                    }
                ],
            }
        ],
        "filters": [],
        "branding": {"themeName": "Synthetic", "primary": "#005A9C", "accent": "#2D7D9A"},
        "accessibility": ["Synthetic alt text"],
        "standardsApplied": [
            {"citation": "synthetic-standard", "decision": "Synthetic annotation test"}
        ],
        "assumptions": [],
        "warnings": ["Synthetic fixture only"],
        "generationRequirements": [],
    }


def receive_analysis(i):
    i.response.raw = native_body(analysis_fixture())
    response = dispatch(i)
    assert response.status_code == 200, response.text
    receipt = response.json()["native_response"]["receipt_id"]
    assert receipt
    return receipt


def intake(i, receipt, client=None, **updates):
    return (client or i.client).post(
        f"/api/cases/{i.s.case['id']}/native-response-receipts/{receipt}/contract",
        json={
            "expected_context_version": i.payload["expected_context_version"],
            "expected_settings_id": i.payload["expected_settings_id"],
            **updates,
        },
        headers=csrf(i.s.session),
    )


def test_native_analysis_requires_separate_confirmation_and_retains_original(integrated):
    i = integrated
    receipt = receive_analysis(i)
    original = i.response.raw
    accepted = intake(i, receipt)
    assert accepted.status_code == 200, accepted.text
    interpretation = accepted.json()["interpretation"]
    assert interpretation["state"] == "READY_FOR_CONFIRMATION"
    state = i.client.get(f"/api/cases/{i.s.case['id']}/acceptance").json()
    assert state["confirmed_contract"] is None
    assert intake(i, receipt).json()["interpretation"]["id"] == interpretation["id"]
    assert len(i.calls) == 1 and len(i.tokens) == 1
    body = json.loads(i.calls[0].content)
    assert "text" not in body and "instructions" not in body and "tools" not in body
    assert (
        i.client.get(
            f"/api/cases/{i.s.case['id']}/native-response-receipts/{receipt}/original"
        ).status_code
        == 404
    )  # Only the established protected download route exists.
    assert (
        i.client.get(f"/api/cases/{i.s.case['id']}/native-response-receipts/{receipt}").content
        == original
    )
    with i.s.database.session() as db:
        row = db.scalar(select(NativeContractBindingRow))
        assert row.task == "REQUIREMENT_ANALYSIS"
        provenance = json.loads(
            db.execute(text("SELECT session_json FROM case_interpretation_versions")).scalar_one()
        )["providerProvenance"]
        assert provenance["sourceReceiptId"] == receipt
        assert provenance["latencyMs"] is None
        assert provenance["grounding"]["observedToolCount"] == 0
        assert provenance["grounding"]["retrievalEvidence"] == "ANNOTATIONS_ONLY"


def test_native_whole_chain_reuses_existing_eligible_design_and_protected_zip(integrated):
    i = integrated
    receipt = receive_analysis(i)
    admitted = intake(i, receipt)
    assert admitted.status_code == 200, admitted.text
    interpretation = admitted.json()["interpretation"]
    confirmed = i.client.post(
        f"/api/cases/{i.s.case['id']}/confirm",
        json={
            "interpretation_id": interpretation["id"],
            "expected_context_version": i.payload["expected_context_version"],
        },
        headers=csrf(i.s.session),
    )
    assert confirmed.status_code == 200, confirmed.text
    contract = confirmed.json()["confirmed_contract"]
    state = i.s.load()
    a = bound_approval(i.s, state)
    gate = Reservations(a, lambda: True, i.s.load)
    factory = native_application_factory(a, gate, create_app)
    client = TestClient(
        factory(settings=i.s.settings, database=i.s.database, foundry_credentials=i.credentials)
    )
    client.cookies.update(i.client.cookies)
    design = design_fixture()
    i.response.raw = native_body(design)
    preflight = client.get(
        f"/api/cases/{i.s.case['id']}/native-response-input",
        params={
            "task": "REPORT_DESIGN",
            "confirmed_contract_id": contract["id"],
        },
    )
    assert preflight.status_code == 200, preflight.text
    assert preflight.json()["receive_available"] is True
    response = client.post(
        i.path,
        json={
            **i.payload,
            "command_key": str(uuid4()),
            "task": "REPORT_DESIGN",
            "confirmed_contract_id": contract["id"],
        },
        headers=csrf(i.s.session),
    )
    assert response.status_code == 200, response.text
    design_receipt = response.json()["native_response"]["receipt_id"]
    result = intake(i, design_receipt, client)
    if result.status_code != 200:
        with i.s.database.session() as db:
            print(
                "SYNTHETIC_DESIGN_DIAGNOSTIC",
                db.execute(
                    text("SELECT safe_failure_code, validation_json FROM automatic_design_attempts")
                ).fetchall(),
            )
    assert result.status_code == 200, result.text
    assert result.json()["design"]["attempt"]["status"] == "ELIGIBLE"
    reviewed = result.json()["design"]["reviewed_design"]
    assert reviewed["origin"] == "AUTO_ELIGIBLE"
    repeated = intake(i, design_receipt, client)
    assert repeated.json()["design"]["reviewed_design"]["id"] == reviewed["id"]
    assert len(i.calls) == 2
    assert all("text" not in json.loads(w.content) for w in i.calls)
    build = client.post(
        f"/api/cases/{i.s.case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": reviewed["id"],
            "command_key": str(uuid4()),
        },
        headers=csrf(i.s.session),
    )
    assert build.status_code in {200, 201}, build.text
    attempt = build.json()["attempt"]
    assert attempt["status"] == "SUCCEEDED", attempt
    download = client.get(f"/api/cases/{i.s.case['id']}/generation/{attempt['id']}/artifact")
    assert download.status_code == 200
    assert hashlib.sha256(download.content).hexdigest() == attempt["artifact"]["content_digest"]
    with zipfile.ZipFile(BytesIO(download.content)) as archive:
        assert archive.testzip() is None
        assert b"12,North" in archive.read("data/synthetic.csv")
        stored = json.loads(archive.read("ReportDesign.json"))
        assert stored["pages"] == design["pages"]
        assert stored["measures"] == design["measures"]
    anonymous = TestClient(create_app(settings=i.s.settings, database=i.s.database))
    assert (
        anonymous.get(
            f"/api/cases/{i.s.case['id']}/generation/{attempt['id']}/artifact"
        ).status_code
        == 401
    )
    assert len(i.calls) == 2  # Intake/confirmation/compiler/download send nothing.


@pytest.mark.parametrize("change", ["context", "settings", "tenant", "csrf"])
def test_native_intake_rechecks_current_scope(integrated, change):
    i = integrated
    receipt = receive_analysis(i)
    before = len(i.calls)
    if change == "context":
        r = intake(i, receipt, expected_context_version=1000)
        assert r.status_code == 409
    elif change == "settings":
        r = intake(i, receipt, expected_settings_id=str(uuid4()))
        assert r.status_code == 409
    elif change == "tenant":
        stranger = TestClient(create_app(settings=i.s.settings, database=i.s.database))
        session = sign_in(stranger, "foreign")
        r = stranger.post(
            f"/api/cases/{i.s.case['id']}/native-response-receipts/{receipt}/contract",
            json={
                "expected_context_version": 2,
                "expected_settings_id": i.payload["expected_settings_id"],
            },
            headers=csrf(session),
        )
        assert r.status_code in {403, 404}
    else:
        r = i.client.post(
            f"/api/cases/{i.s.case['id']}/native-response-receipts/{receipt}/contract",
            json={
                "expected_context_version": 2,
                "expected_settings_id": i.payload["expected_settings_id"],
            },
        )
        assert r.status_code == 401
    assert len(i.calls) == before


def test_prose_is_informational_and_never_inferred(integrated):
    i = integrated
    response = dispatch(i)
    receipt = response.json()["native_response"]["receipt_id"]
    check = i.client.get(f"/api/cases/{i.s.case['id']}/native-response-receipts/{receipt}/contract")
    assert check.json()["recognized"] is False
    assert intake(i, receipt).json() == {
        "accepted": False, "reason": "INFORMATIONAL_ANSWER_ONLY",
        "diagnostic": check.json()["diagnostic"],
    }
    assert i.client.get(f"/api/cases/{i.s.case['id']}/acceptance").json()["interpretation"] is None
    assert len(i.calls) == 1


def test_native_binding_is_immutable(integrated):
    i = integrated
    receive_analysis(i)
    with pytest.raises(DBAPIError), i.s.database.session() as db:
        db.execute(text("UPDATE native_contract_bindings SET task = 'REPORT_DESIGN'"))
    with pytest.raises(DBAPIError), i.s.database.session() as db:
        db.execute(text("DELETE FROM native_contract_bindings"))


def test_saved_analysis_cannot_be_applied_after_request_change(integrated):
    i = integrated
    receipt = receive_analysis(i)
    current = i.client.get(f"/api/cases/{i.s.case['id']}").json()["case"]
    changed = i.client.put(
        f"/api/cases/{i.s.case['id']}",
        json={
            "request_text": "Synthetic revised request with a distinct meaning",
            "expected_version": current["version"],
        },
        headers=csrf(i.s.session),
    )
    assert changed.status_code == 200, changed.text
    now = changed.json()["case"]["semantic_context_version"]
    assert intake(i, receipt, expected_context_version=now).status_code == 409
    assert i.client.get(f"/api/cases/{i.s.case['id']}/acceptance").json()["interpretation"] is None
    assert len(i.calls) == 1


def test_no_design_stage_or_contract_can_borrow_an_analysis_grant(integrated):
    i = integrated
    denied = dispatch(i, task="REPORT_DESIGN", confirmed_contract_id=str(uuid4()))
    assert denied.status_code == 503
    assert i.calls == [] and i.tokens == []
    assert i.gate.receipt()["attempts_consumed"] == 0


def test_design_object_in_analysis_response_remains_information(integrated):
    i = integrated
    i.response.raw = native_body(design_fixture())
    receipt = dispatch(i).json()["native_response"]["receipt_id"]
    assert intake(i, receipt).json()["accepted"] is False
    assert i.client.get(f"/api/cases/{i.s.case['id']}/acceptance").json()["interpretation"] is None
    assert len(i.calls) == 1


def test_legacy_receipt_without_binding_is_readable_but_never_eligible(integrated):
    from apbra_api.evidence import LocalEvidenceStore
    from apbra_api.native_response_archive import NativeResponseArchive, NativeResponseScope
    from apbra_api.native_response_index import DatabaseNativeResponseIndex, NativeReceiveCommandRow

    i = integrated
    operation = uuid4()
    with i.s.database.session() as db:
        db.add(
            NativeReceiveCommandRow(
                id=operation,
                company_id=i.s.company,
                case_id=UUID(i.s.case["id"]),
                actor_membership_id=UUID(i.s.session["actor"]["membership_id"]),
                context_version=i.payload["expected_context_version"],
                settings_id=UUID(i.payload["expected_settings_id"]),
                command_key=uuid4(),
                state="RECEIVED",
                http_status=200,
                provider_status="completed",
            )
        )
    raw = native_body(analysis_fixture())
    archived = NativeResponseArchive(
        NativeResponseScope(
            i.s.company, UUID(i.s.case["id"]), i.payload["expected_context_version"], operation
        ),
        LocalEvidenceStore(i.s.settings.evidence_root, i.s.settings.profile),
        DatabaseNativeResponseIndex(i.s.database),
    ).preserve(raw)
    assert intake(i, str(archived.id)).json()["accepted"] is False
    original = i.client.get(f"/api/cases/{i.s.case['id']}/native-response-receipts/{archived.id}")
    assert original.content == raw
    assert len(i.calls) == 0


def test_ambiguous_duplicate_native_contract_keys_remain_information(integrated):
    i = integrated
    body = json.loads(native_body(analysis_fixture()))
    body["output"][1]["content"][0]["text"] = (
        '{"state":"READY_FOR_CONFIRMATION","state":"NEEDS_CLARIFICATION"}'
    )
    i.response.raw = json.dumps(body).encode()
    receipt = dispatch(i).json()["native_response"]["receipt_id"]
    assert intake(i, receipt).json()["accepted"] is False
    assert len(i.calls) == 1


@pytest.mark.parametrize(
    "shape",
    [
        "output-null",
        "content-null",
        "text-object",
        "output-type-object",
        "state-object",
        "citation-object",
        "tool-status-object",
        "tool-status-list",
    ],
)
def test_malformed_archived_assistant_shapes_are_informational_not_http500(integrated, shape):
    i = integrated
    body = json.loads(native_body(analysis_fixture()))
    if shape == "output-null":
        body["output"] = None
    elif shape == "content-null":
        body["output"][1]["content"] = None
    elif shape == "text-object":
        body["output"][1]["content"][0]["text"] = {}
    elif shape == "output-type-object":
        body["output"][1]["type"] = {}
    elif shape == "state-object":
        body["output"][1]["content"][0]["text"] = json.dumps({"state": {}})
    elif shape in {"tool-status-object", "tool-status-list"}:
        body["output"][0]["status"] = {} if shape == "tool-status-object" else []
    else:
        value = analysis_fixture()
        value["standardsApplied"] = [{"citation": {}, "decision": "Synthetic malformed"}]
        body["output"][1]["content"][0]["text"] = json.dumps(value)
    i.response.raw = json.dumps(body).encode()
    received = dispatch(i)
    assert received.status_code == 200, received.text
    receipt = received.json()["native_response"]["receipt_id"]
    prefix = f"/api/cases/{i.s.case['id']}/native-response-receipts/{receipt}"
    check = i.client.get(prefix + "/contract")
    assert check.status_code == 200 and check.json()["recognized"] is False
    admitted = intake(i, receipt)
    assert admitted.status_code == 200
    assert admitted.json() == {
        "accepted": False, "reason": "INFORMATIONAL_ANSWER_ONLY",
        "diagnostic": check.json()["diagnostic"],
    }
    assert i.client.get(prefix).content == i.response.raw
    view = i.client.get(prefix + "/view")
    assert view.status_code == 200
    expected_texts = (
        [body["output"][1]["content"][0]["text"]]
        if shape in {"state-object", "citation-object", "tool-status-object", "tool-status-list"}
        else []
    )
    assert view.json()["texts"] == expected_texts
    assert i.client.get(f"/api/cases/{i.s.case['id']}/acceptance").json()["interpretation"] is None
    status = i.client.get(
        f"/api/cases/{i.s.case['id']}/native-response-checks/"
        + received.json()["native_response"]["operation_id"]
    )
    before = received.json()["native_response"]["diagnostic"]
    assert status.json()["native_response"]["diagnostic"] == before
    assert len(i.calls) == len(i.tokens) == 1


@pytest.mark.parametrize("mode", ["none", "not-ready", "ready-error", "resolve-error"])
def test_local_confirmation_of_native_analysis_never_requires_provider_credentials(
    integrated, mode
):
    i = integrated
    receipt = receive_analysis(i)
    admitted = intake(i, receipt)
    assert admitted.status_code == 200, admitted.text
    interpretation = admitted.json()["interpretation"]
    calls = []

    class Unavailable:
        def ready(self, *args):
            calls.append("ready")
            if mode == "ready-error":
                raise RuntimeError("SYNTHETIC_UNAVAILABLE")
            return mode == "resolve-error"

        def resolve(self, *args):
            calls.append("resolve")
            raise RuntimeError("SYNTHETIC_UNAVAILABLE")

    client = TestClient(
        create_app(
            settings=i.s.settings,
            database=i.s.database,
            foundry_credentials=None if mode == "none" else Unavailable(),
        )
    )
    client.cookies.update(i.client.cookies)
    result = client.post(
        f"/api/cases/{i.s.case['id']}/confirm",
        json={
            "interpretation_id": interpretation["id"],
            "expected_context_version": i.payload["expected_context_version"],
        },
        headers=csrf(i.s.session),
    )
    assert result.status_code == 200, result.text
    contract = result.json()["confirmed_contract"]
    assert contract["interpretation_id"] == interpretation["id"] and contract["current"]
    assert calls == []  # No credential readiness/resolve/token read is needed to confirm.
    assert len(i.calls) == 1 and len(i.tokens) == 1
    assert (
        client.get(f"/api/cases/{i.s.case['id']}/native-response-receipts/{receipt}").content
        == i.response.raw
    )
    available = client.get(
        f"/api/cases/{i.s.case['id']}/native-response-input",
        params={"task": "REPORT_DESIGN", "confirmed_contract_id": contract["id"]},
    )
    assert available.status_code == 200, available.text
    assert available.json()["receive_available"] is False  # Confirmation grants no paid authority.


@pytest.mark.parametrize("mode", ["csrf", "anonymous", "stale-context", "wrong-interpretation"])
def test_local_confirmation_keeps_protected_checks_without_credentials(integrated, mode):
    i = integrated
    receipt = receive_analysis(i)
    admitted = intake(i, receipt)
    assert admitted.status_code == 200
    interpretation = admitted.json()["interpretation"]
    client = TestClient(create_app(settings=i.s.settings, database=i.s.database))
    if mode != "anonymous":
        client.cookies.update(i.client.cookies)
    payload = {
        "interpretation_id": str(uuid4())
        if mode == "wrong-interpretation"
        else interpretation["id"],
        "expected_context_version": i.payload["expected_context_version"]
        + (1 if mode == "stale-context" else 0),
    }
    result = client.post(
        f"/api/cases/{i.s.case['id']}/confirm",
        json=payload,
        headers={} if mode == "csrf" else csrf(i.s.session),
    )
    assert (
        result.status_code
        == {"csrf": 401, "anonymous": 401, "stale-context": 409, "wrong-interpretation": 409}[mode]
    ), result.text
    assert result.json()["error"]["code"] == (
        "CSRF_INVALID" if mode in {"csrf", "anonymous"} else "STALE_VERSION"
    )
    state = i.client.get(f"/api/cases/{i.s.case['id']}/acceptance").json()
    assert state["confirmed_contract"] is None
    assert len(i.calls) == 1 and len(i.tokens) == 1


def test_saved_design_unverified_claims_admit_with_warning_without_provider_retry(integrated):
    from pathlib import Path

    i = integrated
    analysis = intake(i, receive_analysis(i)).json()['interpretation']
    confirmed = i.client.post(
        f"/api/cases/{i.s.case['id']}/confirm",
        json={'interpretation_id': analysis['id'], 'expected_context_version': 2},
        headers=csrf(i.s.session),
    )
    assert confirmed.status_code == 200
    contract = confirmed.json()['confirmed_contract']
    approval = bound_approval(i.s, i.s.load())
    gate = Reservations(approval, lambda: True, i.s.load)
    client = TestClient(native_application_factory(approval, gate, create_app)(
        settings=i.s.settings, database=i.s.database, foundry_credentials=i.credentials,
    ))
    client.cookies.update(i.client.cookies)
    fixture = Path(__file__).parent / 'fixtures/saved_design_unobserved_citations.json'
    minimized = json.loads(fixture.read_text())
    value = design_fixture()
    value['standardsApplied'] = json.loads(
        minimized['output'][1]['content'][0]['text']
    )['standardsApplied']
    body = json.loads(native_body(value))
    body['output'][1]['content'][0]['annotations'] = []
    original = json.dumps(body).encode()
    i.response.raw = original
    received = client.post(i.path, json={
        **i.payload, 'command_key': str(uuid4()), 'task': 'REPORT_DESIGN',
        'confirmed_contract_id': contract['id'],
    }, headers=csrf(i.s.session))
    assert received.status_code == 200
    receipt = received.json()['native_response']['receipt_id']
    prefix = f"/api/cases/{i.s.case['id']}/native-response-receipts/{receipt}"
    checked = client.get(prefix + '/contract')
    assert checked.status_code == 200
    assert checked.headers['cache-control'] == 'no-store'
    assert checked.json()['diagnostic'] is None
    assert checked.json()['recognized'] is True
    assert checked.json()['warnings'] == [
        {'path': f'/standardsApplied/{index}/citation', 'reason': 'CITATION_NOT_OBSERVED'}
        for index in range(2)
    ]
    assert checked.json()['task'] == 'REPORT_DESIGN'
    assert checked.json()['current'] is True
    assert 'synthetic-unobserved-standard' not in checked.text
    admitted = intake(i, receipt, client)
    assert admitted.status_code == 200, admitted.text
    assert admitted.json()['accepted'] is True
    assert admitted.json()['design']['attempt']['status'] == 'ELIGIBLE'
    reviewed = admitted.json()['design']['reviewed_design']
    build = client.post(f"/api/cases/{i.s.case['id']}/generation", json={
        'confirmed_contract_id': contract['id'], 'reviewed_design_id': reviewed['id'],
        'command_key': str(uuid4()),
    }, headers=csrf(i.s.session))
    assert build.status_code in {200, 201}, build.text
    attempt = build.json()['attempt']
    assert attempt['status'] == 'SUCCEEDED'
    artifact = client.get(f"/api/cases/{i.s.case['id']}/generation/{attempt['id']}/artifact")
    assert artifact.status_code == 200
    with zipfile.ZipFile(BytesIO(artifact.content)) as archive:
        guide = archive.read('Delivery-Guide.md').decode()
        assert 'UNVERIFIED MODEL CLAIM' in guide
        assert 'NO_OBSERVED_RETRIEVAL' in guide
        design = json.loads(archive.read('ReportDesign.json'))
        assert design['standardsApplied'] == value['standardsApplied']
    assert client.get(prefix).content == original
    assert len(i.calls) == 2  # One synthetic analysis and one design; reads/intake never send.
    with i.s.database.session() as db:
        assert db.execute(text('SELECT count(*) FROM automatic_design_attempts')).scalar_one() == 1
    anonymous = TestClient(client.app)
    assert anonymous.get(prefix + '/contract').status_code == 401
