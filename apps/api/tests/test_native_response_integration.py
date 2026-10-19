"""Synthetic saved-case native check, durable PostgreSQL and private attachment ACL."""

import json
import time
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import test_foundry_report_runtime as runtime_fixtures
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import func, select, table, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_foundry_report_runtime import approval, new_settings

import apbra_api.native_response_api as native
from apbra_api.api import create_app
from apbra_api.foundry_report_runtime import ReportApproval, Reservations
from apbra_api.model_provider import FoundryAccess, FoundryBearer
from apbra_api.native_response_archive import NativeResponseScope
from apbra_api.native_response_index import DatabaseNativeResponseIndex, NativeResponseReceiptRow
from apbra_api.native_response_probe import receive_native_response
from apbra_api.native_response_runtime import native_application_factory

saved_case = runtime_fixtures.saved

PRIVATE = "SYNTHETIC-NATIVE-PRIVATE-CANARY"
RAW = json.dumps(
    {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "Native prose " + PRIVATE},
                    {
                        "type": "output_file",
                        "url": "https://private.invalid/file?secret=" + PRIVATE,
                    },
                ],
            }
        ],
    },
    indent=2,
).encode()


@pytest.fixture
def integrated(saved_case, monkeypatch, request):
    s = saved_case
    vision = getattr(request, "param", False)
    s.profile = s.profile.model_copy(update={
        "max_input_characters": 100000,
        "capabilities": s.profile.capabilities.model_copy(update={"vision": bool(vision)}),
    })
    if vision:
        from test_reference_material import PNG
        added = s.client.post(
            f"/api/cases/{s.case['id']}/reference-material",
            params={"filename": "synthetic.png", "expected_context_version": 2},
            content=PNG,
            headers={**csrf(s.session), "Content-Type": "application/octet-stream"},
        )
        assert added.status_code == 200, added.text

    with s.database.session() as db:
        new_settings(
            db, s.company, {"provider_profile": s.profile, "automatic_generation_enabled": True}
        )
    s.settings.qualified_provider_profiles_json = json.dumps([s.profile.model_dump()])
    state = s.load()
    data = approval(stages=("REQUIREMENT_ANALYSIS",)).model_dump()
    data["binding"].update(company_id=s.company, provider_profile=s.profile)
    data.update(
        case_id=state.case_id,
        settings_id=state.settings_id,
        settings_digest=state.settings_digest,
        request_version_id=state.request_version_id,
        semantic_context_version=state.semantic_context_version,
        input_digest=state.input_digest,
    )
    a = ReportApproval.model_validate(data)
    gate = Reservations(a, lambda: True, s.load)
    calls, tokens = [], []

    class Credentials:
        def ready(self, company, profile):
            return company == s.company and profile == s.profile

        def resolve(self, company, profile):
            def bearer():
                tokens.append(1)
                return FoundryBearer("synthetic-token", time.time() + 600)

            return FoundryAccess(
                company,
                profile.profile_id,
                profile.configuration_id,
                bearer,
                "synthetic-kb",
                "SHARED_STANDARDS",
                qualification="LIVE_METADATA_VERIFIED",
            )

    response = SimpleNamespace(status=200, raw=RAW, error=None)

    def handler(wire):
        calls.append(wire)
        if response.error:
            raise response.error
        return httpx.Response(response.status, content=response.raw)

    def receive(*args, **kwargs):
        return receive_native_response(*args, **kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(native, "receive_native_response", receive)
    factory = native_application_factory(a, gate, create_app)
    client = TestClient(
        factory(settings=s.settings, database=s.database, foundry_credentials=Credentials())
    )
    client.cookies.update(s.client.cookies)
    return SimpleNamespace(
        s=s,
        client=client,
        gate=gate,
        calls=calls,
        tokens=tokens,
        response=response,
        credentials=Credentials(),
        path=f"/api/cases/{s.case['id']}/native-response-checks",
        payload={
            "command_key": str(uuid4()),
            "expected_settings_id": str(state.settings_id),
            "expected_context_version": state.semantic_context_version,
        },
    )


def dispatch(i, **overrides):
    return i.client.post(i.path, json={**i.payload, **overrides}, headers=csrf(i.s.session))


def test_normal_workflow_readiness_never_claims_bearer_and_consumption_disables_send(integrated):
    i = integrated
    path = f"/api/cases/{i.s.case['id']}/native-response-input"
    first = i.client.get(path).json()
    assert first['ready'] is True and first['receive_available'] is True
    UUID(first['connection_id'])
    assert first['receive_reason'] == 'AUTHORIZED_SINGLE_RESPONSE_READY'
    assert i.client.get(path).json()['connection_id'] == first['connection_id']
    assert not i.tokens and not i.calls
    assert i.gate.receipt()['attempts_consumed'] == 0
    assert dispatch(i).status_code == 200
    final = i.client.get(path).json()
    assert final['ready'] is True and final['receive_available'] is False
    assert final['connection_id'] is None
    assert len(i.tokens) == len(i.calls) == 1


def test_normal_workflow_passive_and_revoked_connections_are_read_only(integrated):
    i = integrated
    path = f"/api/cases/{i.s.case['id']}/native-response-input"
    passive = TestClient(create_app(settings=i.s.settings, database=i.s.database,
                                    foundry_credentials=i.credentials))
    passive.cookies.update(i.client.cookies)
    value = passive.get(path).json()
    assert value['ready'] is True and value['receive_available'] is False
    assert value['connection_id'] is None
    i.gate.valid = lambda: False
    assert i.client.get(path).json()['receive_available'] is False
    assert not i.tokens and not i.calls
    assert i.gate.receipt()['attempts_consumed'] == 0


@pytest.mark.parametrize('identity', ['anonymous', 'foreign', 'member'])
def test_normal_workflow_readiness_preserves_case_and_role_access(integrated, identity):
    i = integrated
    if identity == 'anonymous':
        i.client.cookies.clear()
    else:
        sign_in(i.client, identity)
    result = i.client.get(f"/api/cases/{i.s.case['id']}/native-response-input")
    assert result.status_code in {401, 403, 404}
    assert 'connection_id' not in result.json()
    assert not i.tokens and not i.calls


def report_counts(db):
    return [
        db.scalar(select(func.count()).select_from(table(name)))
        for name in (
            "case_interpretation_versions",
            "confirmed_requirement_contracts",
            "automatic_design_attempts",
            "reviewed_report_designs",
            "generation_attempts",
            "generated_artifacts",
        )
    ]


def test_exact_native_body_survives_restart_and_does_not_change_report_history(integrated):
    i = integrated
    with i.s.database.session() as db:
        before = report_counts(db)
    result = dispatch(i)
    assert result.status_code == 200, result.text
    item = result.json()["native_response"]
    assert item["state"] == "RECEIVED" and item["bytes"] == len(RAW)
    assert item["http_status"] == 200 and item["provider_status"] == "completed"
    assert PRIVATE not in result.text and "storage_key" not in result.text
    assert len(i.calls) == len(i.tokens) == 1
    body = json.loads(i.calls[0].content)
    assert set(body) == {"input", "max_output_tokens", "stream", "store"}
    context = json.loads(body["input"][0]["content"])["context"]
    assert (
        context["materialContext"]["requestText"] == "Create a report of total amount by division."
    )
    assert context["dataStructure"]["tables"]
    replay = dispatch(i)
    assert replay.json() == result.json() and len(i.calls) == 1
    # A new command also cannot obtain another credential from the finite gate.
    another = dispatch(i, command_key=str(uuid4()))
    assert another.status_code == 503
    assert len(i.calls) == len(i.tokens) == 1
    url = f"/api/cases/{i.s.case['id']}/native-response-receipts/{item['receipt_id']}"
    restart = TestClient(
        create_app(settings=i.s.settings, database=i.s.database, native_receive_enabled=True)
    )
    restart.cookies.update(i.client.cookies)
    received = restart.get(url)
    assert received.status_code == 200 and received.content == RAW
    assert received.headers["cache-control"] == "no-store"
    assert received.headers["x-content-type-options"] == "nosniff"
    assert received.headers["content-disposition"].startswith("attachment;")
    status = restart.get(i.path + "/" + item["operation_id"])
    assert status.json() == result.json()
    with i.s.database.session() as db:
        assert report_counts(db) == before
    assert i.gate.receipt()["attempts_consumed"] == 1


@pytest.mark.parametrize("status", [400, 429, 500])
def test_http_error_body_is_preserved_and_not_retried(integrated, status):
    i = integrated
    i.response.status = status
    i.response.raw = json.dumps({"error": {"message": PRIVATE, "param": "text"}}).encode()
    response = dispatch(i)
    item = response.json()["native_response"]
    assert item["state"] == "HTTP_ERROR" and PRIVATE not in response.text
    assert item["http_status"] == status
    assert item["diagnostic"]["response_received"] is True
    assert dispatch(i).json() == response.json() and len(i.calls) == 1
    original = i.client.get(
        f"/api/cases/{i.s.case['id']}/native-response-receipts/{item['receipt_id']}"
    )
    assert original.content == i.response.raw


def test_transport_uncertain_is_durable_and_refresh_cannot_retry(integrated):
    i = integrated
    i.response.error = httpx.ReadTimeout(PRIVATE)
    response = dispatch(i)
    assert response.json()["native_response"]["state"] == "UNCERTAIN"
    assert response.json()["native_response"]["receipt_id"] is None
    assert PRIVATE not in response.text
    assert dispatch(i).json() == response.json() and len(i.calls) == 1


@pytest.mark.parametrize("fault", ["csrf", "context", "settings", "foreign", "viewer", "anonymous"])
def test_authority_and_context_fail_before_bearer_or_post(integrated, fault):
    i = integrated
    payload = dict(i.payload)
    headers = csrf(i.s.session)
    if fault == "csrf":
        headers = {}
    elif fault == "context":
        payload["expected_context_version"] += 1
    elif fault == "settings":
        payload["expected_settings_id"] = str(uuid4())
    elif fault == "anonymous":
        i.client.cookies.clear()
    else:
        actor = sign_in(i.client, "foreign" if fault == "foreign" else "member")
        headers = csrf(actor)
    response = i.client.post(i.path, json=payload, headers=headers)
    assert response.status_code in {401, 403, 404, 409}
    assert not i.calls and not i.tokens
    assert i.gate.receipt()["attempts_consumed"] == 0


def test_private_download_rechecks_membership_and_case_scope(integrated):
    i = integrated
    item = dispatch(i).json()["native_response"]
    url = f"/api/cases/{i.s.case['id']}/native-response-receipts/{item['receipt_id']}"
    sign_in(i.client, "foreign")
    assert i.client.get(url).status_code in {403, 404}
    i.client.cookies.clear()
    assert i.client.get(url).status_code == 401


def test_database_index_denies_cross_scope_and_receipt_is_immutable(integrated):
    i = integrated
    item = dispatch(i).json()["native_response"]
    scope = NativeResponseScope(
        i.s.company,
        UUID(i.s.case["id"]),
        i.payload["expected_context_version"],
        UUID(item["operation_id"]),
    )
    index = DatabaseNativeResponseIndex(i.s.database)
    assert index.load(scope, UUID(item["receipt_id"])).size == len(RAW)
    with pytest.raises(ValueError, match="NATIVE_RESPONSE_NOT_FOUND"):
        index.load(replace(scope, company_id=uuid4()), UUID(item["receipt_id"]))
    with pytest.raises(DBAPIError):
        with i.s.database.session() as db:
            row = db.get(NativeResponseReceiptRow, UUID(item["receipt_id"]))
            row.storage_key = "synthetic-tamper"
    with pytest.raises(IntegrityError):
        with i.s.database.session() as db:
            original = index.load(scope, UUID(item["receipt_id"]))
            db.add(
                NativeResponseReceiptRow(
                    id=uuid4(),
                    operation_id=scope.operation_id,
                    company_id=uuid4(),
                    case_id=scope.case_id,
                    context_version=scope.context_version,
                    digest=original.digest,
                    size=original.size,
                    storage_key=original.storage_key,
                )
            )


def test_default_app_exposes_read_routes_but_cannot_dispatch(integrated):
    i = integrated
    app = create_app(settings=i.s.settings, database=i.s.database)
    client = TestClient(app)
    client.cookies.update(i.client.cookies)
    url = f"/api/cases/{i.s.case['id']}/native-response-receipts"
    assert client.get(url).json() == {"items": []}
    response = client.post(i.path, json=i.payload, headers=csrf(i.s.session))
    assert response.status_code == 503
    assert not i.calls and not i.tokens
    assert i.gate.receipt()["attempts_consumed"] == 0


def test_empty_additive_migration_rolls_back_without_losing_existing_data(settings, database):
    from conftest import disposable_alembic_config

    from alembic import command

    config = disposable_alembic_config(settings.database_url)
    with database.session() as db:
        companies = db.scalar(text("SELECT count(*) FROM companies"))
    command.downgrade(config, "20261015_11")
    with database.session() as db:
        assert db.scalar(text("SELECT count(*) FROM companies")) == companies
        assert db.scalar(text("SELECT to_regclass('native_response_receipts')")) is None
    command.upgrade(config, "head")
    with database.session() as db:
        assert db.scalar(text("SELECT count(*) FROM companies")) == companies
        assert db.scalar(text("SELECT count(*) FROM native_response_receipts")) == 0


def test_migration_refuses_to_discard_retained_native_history(integrated):
    from conftest import disposable_alembic_config

    from alembic import command

    i = integrated
    item = dispatch(i).json()["native_response"]
    with pytest.raises(
        RuntimeError, match="Cannot downgrade retained native-(response history|contract bindings)"
    ):
        command.downgrade(disposable_alembic_config(i.s.settings.database_url), "20261015_11")
    original = i.client.get(
        f"/api/cases/{i.s.case['id']}/native-response-receipts/{item['receipt_id']}"
    )
    assert original.content == RAW


def test_other_report_route_cannot_claim_native_grant(integrated):
    i = integrated
    response = i.client.post(
        f"/api/cases/{i.s.case['id']}/interpretations",
        json={"expected_context_version": i.payload["expected_context_version"]},
        headers=csrf(i.s.session),
    )
    assert response.status_code == 409
    assert not i.calls and not i.tokens
    assert i.gate.receipt()["attempts_consumed"] == 0
    assert dispatch(i).json()["native_response"]["state"] == "RECEIVED"
    assert len(i.calls) == 1


@pytest.mark.parametrize(
    "attempts,stages",
    [
        (2, ("REQUIREMENT_ANALYSIS",)),
        (2, ("REPORT_DESIGN",)),
        (1, ("REQUIREMENT_ANALYSIS", "REPORT_DESIGN")),
    ],
)
def test_native_factory_rejects_broader_grants(attempts, stages):
    from apbra_api.model_provider import ProviderConfigurationError

    a = approval(attempts=attempts, stages=stages)
    gate = Reservations(a, lambda: True, lambda: None)
    with pytest.raises(ProviderConfigurationError):
        native_application_factory(a, gate, create_app)


def test_passive_inspection_with_ordinary_credentials_cannot_dispatch(integrated):
    i = integrated
    passive = TestClient(
        create_app(
            settings=i.s.settings,
            database=i.s.database,
            native_receive_enabled=True,
            foundry_credentials=i.credentials,
        )
    )
    passive.cookies.update(i.client.cookies)
    denied = passive.post(i.path, json=i.payload, headers=csrf(i.s.session))
    assert denied.status_code == 503 and not i.calls and not i.tokens
    assert i.gate.receipt()["attempts_consumed"] == 0
    item = dispatch(i).json()["native_response"]
    # The same passive app can still inspect exact bytes without invocation authority.
    original = passive.get(
        f"/api/cases/{i.s.case['id']}/native-response-receipts/{item['receipt_id']}"
    )
    assert original.status_code == 200 and original.content == RAW


def test_complete_source_is_wired_to_exact_existing_route_and_preflight_is_private(integrated):
    i = integrated
    availability = i.client.get(f"/api/cases/{i.s.case['id']}/native-response-input")
    assert availability.status_code == 200, availability.text
    assert availability.headers['cache-control'] == 'no-store'
    assert availability.json()['ready'] is True
    assert 'sourceText' not in availability.text and 'storage_key' not in availability.text
    assert not i.tokens and not i.calls
    assert dispatch(i).status_code == 200
    wire = i.calls[0]
    body = json.loads(wire.content)
    context = json.loads(body['input'][0]['content'])['context']
    source = context['caseFiles'][0]
    assert source['sourceText'].encode('utf-8') == b'Amount,Division\n12,North\n9,South\n'
    assert context['fileDelivery']['sampled'] is False
    assert context['fileDelivery']['serviceFileUploaded'] is False
    assert context['fileDelivery']['processingVerified'] is False
    assert str(wire.url).split('?')[0] == i.s.profile.endpoint
    assert body['store'] is False and 'tools' not in body and 'instructions' not in body
    assert availability.json()['input_characters'] == len(body['input'][0]['content'])


def test_full_request_limit_failure_precedes_admission_and_paid_slot(integrated, monkeypatch):
    from apbra_api.model_provider import ProviderCallError
    from apbra_api.native_response_index import NativeReceiveCommandRow
    i = integrated

    def oversized(*args):
        raise ProviderCallError('MODEL_INPUT_BUDGET_EXCEEDED')

    monkeypatch.setattr(native, 'native_request_content', oversized)
    manifest = i.client.get(f"/api/cases/{i.s.case['id']}/native-response-input").json()
    assert not manifest['ready'] and manifest['reason'] == 'MODEL_INPUT_BUDGET_EXCEEDED'
    response = dispatch(i)
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'NATIVE_CASE_FILES_UNAVAILABLE'
    with i.s.database.session() as db:
        assert db.scalar(select(func.count()).select_from(NativeReceiveCommandRow)) == 0
    assert not i.calls and not i.tokens and i.gate.receipt()['attempts_consumed'] == 0


@pytest.mark.parametrize("kind", ["xlsx", "image"])
def test_unsupported_file_is_visible_and_never_silently_reduced_to_schema(integrated, kind):
    from test_evidence import workbook_with_sheet
    from test_reference_material import PNG

    i = integrated
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Data</t></is></c></row>'
        '<row r="2"><c r="A2"><v>12</v></c></row></sheetData></worksheet>'
    )
    raw = workbook_with_sheet(sheet) if kind == "xlsx" else PNG
    filename = "synthetic.xlsx" if kind == "xlsx" else "support.png"
    route = "evidence" if kind == "xlsx" else "reference-material"
    added = i.client.post(
        f"/api/cases/{i.s.case['id']}/{route}",
        params={"filename": filename,
                "expected_context_version": i.payload['expected_context_version']},
        content=raw, headers={**csrf(i.s.session), "Content-Type": "application/octet-stream"},
    )
    assert added.status_code == 200, added.text
    response = i.client.get(f"/api/cases/{i.s.case['id']}/native-response-input")
    assert response.status_code == 200, response.text
    manifest = response.json()
    assert not manifest['ready']
    unsupported = next(file for file in manifest['files'] if file['filename'] == filename)
    assert unsupported['reason'] == (
        'APBRA_WORKBOOK_ROUTE_NOT_IMPLEMENTED' if kind == 'xlsx'
        else 'TENANT_VISION_CAPABILITY_DISABLED'
    )
    assert not i.calls and not i.tokens and i.gate.receipt()['attempts_consumed'] == 0


def test_passive_saved_answer_view_and_original_are_separate_read_only_results(integrated):
    i = integrated
    i.response.raw = json.dumps({'status':'completed','output':[
        {'type':'mcp_call','output':PRIVATE+'tool-private'},
        {'type':'message','role':'user','content':[{'type':'output_text','text':'not-assistant'}]},
        {'type':'message','role':'assistant','content':[
            {'type':'output_text','text':'# Original\n<script>bad()</script>\n  spacing  '},
            {'type':'output_file','url':'https://secret.invalid?token='+PRIVATE},
            {'type':'output_text','text':'Second exact segment'},
        ]},
    ]}, indent=2).encode()
    item = dispatch(i).json()['native_response']
    passive = TestClient(create_app(settings=i.s.settings, database=i.s.database))
    passive.cookies.update(i.client.cookies)
    prefix = f"/api/cases/{i.s.case['id']}/native-response-receipts"
    with i.s.database.session() as db:
        before = report_counts(db)
    listed = passive.get(prefix)
    assert listed.status_code == 200 and listed.headers['cache-control'] == 'no-store'
    assert listed.json()['items'][0]['receipt_id'] == item['receipt_id']
    url = prefix+'/'+item['receipt_id']
    view = passive.get(url+'/view')
    assert view.status_code == 200 and view.headers['cache-control'] == 'no-store'
    assert view.json()['texts'] == ['# Original\n<script>bad()</script>\n  spacing  ',
                                    'Second exact segment']
    assert PRIVATE not in view.text and 'not-assistant' not in view.text
    assert passive.get(url).content == i.response.raw
    assert len(i.calls) == len(i.tokens) == 1
    with i.s.database.session() as db:
        assert report_counts(db) == before
    sign_in(passive, 'foreign')
    for path in (prefix, url, url+'/view', prefix.replace('receipts','input')):
        assert passive.get(path).status_code in {403,404}
    passive.cookies.clear()
    assert passive.get(url+'/view').status_code == 401


@pytest.mark.parametrize('raw', [b'not-json', b'{"output":null}', b'{"output":[null,4,{}]}'])
def test_unreadable_response_has_original_download_without_invented_answer(integrated, raw):
    i = integrated
    i.response.raw = raw
    item = dispatch(i).json()['native_response']
    url = f"/api/cases/{i.s.case['id']}/native-response-receipts/{item['receipt_id']}"
    assert i.client.get(url+'/view').json()['texts'] == []
    assert i.client.get(url).content == raw


@pytest.mark.parametrize("integrated", [True], indirect=True)
def test_inline_image_uses_original_bytes_and_exact_route_without_tool_override(integrated):
    import base64
    import hashlib

    from test_reference_material import PNG

    i = integrated
    availability = i.client.get(f"/api/cases/{i.s.case['id']}/native-response-input").json()
    assert availability['ready']
    image = next(file for file in availability['files'] if file['kind'] == 'SUPPORTING')
    assert image['transport'] == 'INLINE_ORIGINAL_IMAGE'
    assert image['serviceFileUploaded'] is False and image['processingVerified'] is False
    assert 'data:image' not in json.dumps(availability) and not i.tokens
    response = dispatch(i)
    assert response.status_code == 200, response.text
    body = json.loads(i.calls[0].content)
    parts = body['input'][0]['content']
    assert parts[0]['type'] == 'input_text' and parts[1]['type'] == 'input_image'
    data = base64.b64decode(parts[1]['image_url'].split(',', 1)[1], validate=True)
    assert data == PNG and hashlib.sha256(data).hexdigest() == image['contentDigest']
    assert set(body) == {'input','max_output_tokens','stream','store'}
    assert str(i.calls[0].url).split('?')[0] == i.s.profile.endpoint
    assert len(i.calls) == len(i.tokens) == 1
