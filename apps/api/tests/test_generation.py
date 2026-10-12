from __future__ import annotations

import copy
import hashlib
import json
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from io import BytesIO
from pathlib import Path
from threading import Barrier, Event
from uuid import UUID, uuid4

import httpx
import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_content_storage import MemoryArtifactStore

from apbra_api.api import create_app
from apbra_api.artifacts import ArtifactError, LocalArtifactStore
from apbra_api.config import Settings
from apbra_api.domain import GenerationFailed
from apbra_api.generation import (
    GenerationBridge,
    GenerationBridgeFailure,
    GenerationService,
    _automatic_design_retry_instruction,
    _provider_confirmed_requirements,
    _safe_bridge_diagnostic_detail,
    _safe_failed_validation,
)
from apbra_api.model_provider import (
    DeterministicFakeProvider,
    OpenAICompatibleProvider,
    ProviderCallError,
    ProviderProfile,
    ProviderRequest,
    report_design_schema,
)
from apbra_api.persistence import (
    ApplicationSession,
    AutomaticDesignAttemptRow,
    ConfirmedContractRow,
    Database,
)


def authored_test_geometry(design: dict[str, object]) -> dict[str, object]:
    """Synthetic AI response fixture, never a production geometry fallback."""
    design["schema_version"] = 2
    for page_index, page in enumerate(design["pages"]):
        page.update(displayOption="ActualSizeTopLeft", width=None, height=721.5 + page_index)
        for index, visual in enumerate(page["visuals"]):
            visual["position"] = {
                "x": -10.25 + index * 3, "y": 800.5, "width": 0.5,
                "height": -2.25, "z": 2.5, "tabOrder": index + 0.25,
                "angle": None if index % 2 else 13.75,
            }
    return design


@pytest.mark.parametrize(
    ("failure_kind", "overview"),
    [
        ("", "An imperfect first draft"), ("", ""), ("", "   "),
        ("UNKNOWN_FIELD", ""), ("TIME_GRAIN_FIELD", ""), ("", "Shared-name draft"),
        ("", "AI-chosen pages"), ("", "AI-chosen alternative"),
        ("", "Six standard visuals"), ("", "Model-reordered mixed visuals"),
        ("", "Former layout order"), ("", "Large exact geometry"),
        ("LAYOUT_LIMIT", ""), ("LAYOUT_CAPACITY", ""),
    ],
)
@pytest.mark.parametrize("foundry", [False, True])
def test_editable_draft_whole_chain_preserves_context_and_protected_download(
    settings: Settings, database: Database, failure_kind: str, overview: str, foundry: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_conversations import provider_analysis

    analysis = provider_analysis(ready=True)
    interpretation = analysis["interpretation"]
    assert isinstance(interpretation, dict)
    interpretation.update(
        coverageRequirements=[],
        businessQuestionCoverage=[],
        ambiguities=["Draft business coverage remains incomplete"],
        kpis=["Visits", "Business KPI still to refine"],
    )
    analysis["unresolvedAmbiguities"] = ["Draft business coverage remains incomplete"]
    design = {
        "artifact_kind": "ReportDesign",
        "schema_version": 1,
        "projectName": "EditableDraft",
        "overview": overview,
        "audience": "Business managers",
        "dataModel": {"factTables": ["Metrics"], "dimensionTables": [], "relationships": []},
        "measures": [
            {
                "id": "draft-visits",
                "name": "Visits" if overview == "Shared-name draft" else "Draft Visits",
                "businessDefinition": "Draft aggregation chosen by the model",
                "aggregation": "SUM",
                "field": "Metrics.Missing" if failure_kind == "UNKNOWN_FIELD" else "Metrics.Visits",
                "numeratorMeasureId": "",
                "denominatorMeasureId": "",
                "format": "integer",
            }
        ],
        "pages": [
            {
                "id": "draft-page",
                "name": "Model Draft",
                "purpose": "Initial draft",
                "visuals": [
                    {
                        "id": "draft-card",
                        "type": "line" if failure_kind == "TIME_GRAIN_FIELD" else "card",
                        "title": "Draft Visits",
                        "categoryField": (
                            "Metrics.Visits" if failure_kind == "TIME_GRAIN_FIELD" else ""
                        ),
                        "timeGrain": "MONTH" if failure_kind == "TIME_GRAIN_FIELD" else "NONE",
                        "measureIds": ["draft-visits"],
                        "fields": [],
                        "altText": "",
                    }
                ],
            }
        ],
        "filters": [],
        "branding": {"themeName": "Tenant", "primary": "#005A9C", "accent": "#2D7D9A"},
        "accessibility": [],
        "standardsApplied": [],
        "assumptions": [],
        "warnings": ["Business coverage requires user inspection"],
        "generationRequirements": [],
    }
    model_layout = overview in {"AI-chosen pages", "AI-chosen alternative"}
    single_page_layout = overview in {
        "Six standard visuals", "Model-reordered mixed visuals", "Former layout order"
    }
    if model_layout or single_page_layout or failure_kind in {
        "LAYOUT_LIMIT", "LAYOUT_CAPACITY"
    }:
        source = design["pages"][0]
        source["visuals"] = [
            {**copy.deepcopy(source["visuals"][0]), "id": f"chart-{index}",
             "type": "bar", "categoryField": "Metrics.Campus", "timeGrain": "NONE"}
            for index in range(5)
        ] + [{"id": "campus-slicer", "type": "slicer", "title": "Campus", "altText": "Campus",
              "categoryField": "", "timeGrain": "NONE", "measureIds": [],
              "fields": ["Metrics.Campus"]}]
        if model_layout:
            all_visuals = source["visuals"]
            source["visuals"] = all_visuals[:4]
            design["pages"].append({**copy.deepcopy(source), "id": "ai-second-page",
                                    "name": "AI additional analysis", "visuals": all_visuals[4:]})
            if overview == "AI-chosen alternative":
                design["pages"].reverse()
                design["pages"][0]["visuals"].reverse()
        if overview == "Six standard visuals":
            source["visuals"][-1] = {
                **copy.deepcopy(source["visuals"][0]), "id": "sixth-standard-chart"
            }
        if overview == "Model-reordered mixed visuals":
            templates = {}
            for kind in ("card", "bar", "column", "line", "table", "slicer"):
                visual = {**copy.deepcopy(source["visuals"][0]), "id": f"mixed-{kind}",
                          "type": kind, "title": f"AI {kind}"}
                if kind in {"card", "table", "slicer"}:
                    visual["categoryField"] = ""
                if kind in {"table", "slicer"}:
                    visual["fields"] = ["Metrics.Campus"]
                if kind == "slicer":
                    visual["measureIds"] = []
                templates[kind] = visual
            source["visuals"] = [templates[kind] for kind in (
                "slicer", "card", "table", "column", "bar", "line"
            )]
        if overview == "Former layout order":
            source["visuals"] = [copy.deepcopy(design["pages"][0]["visuals"][0]) for _ in range(6)]
            for index, visual in enumerate(source["visuals"]):
                visual["id"] = f"ordered-{index}"
                if index < 2:
                    visual.update(type="card", categoryField="")
        if failure_kind == "LAYOUT_LIMIT":
            design["pages"] = [{**copy.deepcopy(source), "id": f"page-{index}"}
                               for index in range(4)]
        if failure_kind == "LAYOUT_CAPACITY":
            source["visuals"].append({
                **copy.deepcopy(source["visuals"][0]), "id": "seventh-overflow-chart"
            })
    if overview == "Grounded draft":
        reference = "provider:" + hashlib.sha256(json.dumps([
            "synthetic-shared-standards", "file_citation", "file-synthetic-standard",
        ], separators=(",", ":")).encode()).hexdigest()
        design["standardsApplied"] = [
            {"citation": reference, "decision": "Synthetic applied standard"}
        ]
    authored_test_geometry(design)
    if overview == "Large exact geometry":
        design["pages"][0]["width"] = 2**60
        design["pages"][0]["visuals"][0]["position"].update(x=2**60, z=2**60)
    original_design = copy.deepcopy(design)
    provider = automatic_test_provider([analysis, design])
    provider.profile = provider.profile.model_copy(
        update={"max_calls_per_operation": 1, "retry_limit": 0}
    )
    wire_calls: list[dict[str, object]] = []
    foundry_credentials = None
    if foundry:
        from test_model_provider import foundry_adapter, responses_payload

        queued = [analysis, design]

        def handler(wire: httpx.Request) -> httpx.Response:
            body = json.loads(wire.content)
            wire_calls.append(body)
            assert "instructions" not in body and "model" not in body and "tools" not in body
            assert all(message["role"] != "system" for message in body["input"])
            value = copy.deepcopy(queued.pop(0))
            if (overview == "Grounded draft"
                    and wire_calls[-1]["text"]["format"]["name"] == "report_design"):

                value["standardsApplied"][0]["citation"] = "file-synthetic-standard"
                output = responses_payload(value, [{
                    "type": "file_citation", "file_id": "file-synthetic-standard",
                    "filename": "synthetic-standard.md", "index": 0,
                }])
                output["output"].insert(0, {"type": "mcp_call", "status": "completed",
                                            "output": "PRIVATE RAW TOOL CONTENT"})
                return httpx.Response(200, json=output)
            return httpx.Response(200, json=responses_payload(value))

        provider = foundry_adapter(handler, profile_overrides={
            "max_input_characters": 200_000, "max_calls_per_operation": 1, "retry_limit": 0,
        })
        provider.requests = []
        original_structured = provider.structured

        def recording_structured(candidate: ProviderRequest):
            provider.requests.append(candidate)
            return original_structured(candidate)

        provider.structured = recording_structured
        from dataclasses import replace

        import apbra_api.api as api_module

        class Credentials:
            def ready(self, company_id, qualified):
                return qualified.profile_id == provider.profile.profile_id

            def resolve(self, company_id, qualified):
                assert qualified.protocol == "FOUNDRY_AGENT_RESPONSES"
                return replace(provider._access, company_id=company_id)

        def selected_adapter(qualified, access, *, company_id):
            assert access.company_id == company_id
            assert qualified.model_dump() == provider.profile.model_dump()
            provider._access = access
            return provider

        foundry_credentials = Credentials()
        monkeypatch.setattr(api_module, "FoundryAgentResponsesProvider", selected_adapter)
        settings = settings.model_copy(update={
            "test_semantic_simulator_enabled": False,
            "qualified_provider_profiles_json": json.dumps([provider.profile.model_dump()]),
        })
    with TestClient(
        create_app(settings=settings, database=database,
                   model_provider=None if foundry else provider,
                   foundry_credentials=foundry_credentials)
    ) as runtime:
        if foundry or failure_kind == "LAYOUT_LIMIT":
            owner = sign_in(runtime, "owner")
            current = runtime.get("/api/tenant-settings").json()
            active = copy.deepcopy(current["settings"])
            if foundry:
                active.update(automatic_generation_enabled=True,
                              provider_profile=provider.profile.model_dump())
            if failure_kind == "LAYOUT_LIMIT":
                active["generation_policy"]["governance"]["maxVisualsPerPage"] = 4
            enabled = runtime.put("/api/tenant-settings", headers=csrf(owner),
                                  json={"settings": active, "expected_version": current["version"]})
            assert enabled.status_code == 200, enabled.text
            if foundry:
                assert enabled.json()["credential"]["authMode"] == "ENTRA"
                assert enabled.json()["credential"]["canReplace"] is False
        session = sign_in(runtime, "member")
        request = (
            "Compare visits by campus and explain the additional business KPI; "
            "retain all this context."
        )
        case = runtime.post(
            "/api/cases",
            json={"request_text": request},
            headers={**csrf(session), "Idempotency-Key": str(uuid4())},
        ).json()["case"]
        csv = b"Campus,Visits\nNorth,12\nSouth,9\n"
        evidence = runtime.post(
            f"/api/cases/{case['id']}/evidence",
            params={"filename": "Metrics.csv", "expected_context_version": 1},
            content=csv,
            headers={**csrf(session), "Content-Type": "application/octet-stream"},
        ).json()["evidence"]
        understood = runtime.post(
            f"/api/cases/{case['id']}/interpretations",
            json={"expected_context_version": evidence["semantic_context_version"]},
            headers=csrf(session),
        )
        assert understood.status_code == 200, understood.text
        visible = understood.json()["interpretation"]
        assert visible["state"] == "READY_FOR_CONFIRMATION"
        confirmed = runtime.post(
            f"/api/cases/{case['id']}/confirm",
            json={
                "interpretation_id": visible["id"],
                "expected_context_version": visible["context_version"],
            },
            headers=csrf(session),
        )
        assert confirmed.status_code == 200, confirmed.text
        contract = confirmed.json()["confirmed_contract"]
        assert contract["contract"]["provenance"]["requirement"] == request
        before = copy.deepcopy(contract)
        proposed = runtime.post(
            f"/api/cases/{case['id']}/automatic-designs",
            json={"confirmed_contract_id": contract["id"], "command_key": str(uuid4())},
            headers=csrf(session),
        )
        if failure_kind in {"UNKNOWN_FIELD", "TIME_GRAIN_FIELD"}:
            assert proposed.status_code == 409, proposed.text
            history = runtime.get(
                f"/api/cases/{case['id']}/automatic-designs",
                params={"confirmed_contract_id": contract["id"]},
            ).json()
            failed = history["items"][0]
            assert failed["status"] == "FAILED"
            if failure_kind == "UNKNOWN_FIELD":
                assert failed["validation"]["category"] == "REPORT_DESIGN_MEASURE_INTEGRITY"
                expected = {
                    "code": "UNKNOWN_MEASURE_FIELD", "path": "/reportDesign/measures/0/field"
                }
            elif failure_kind == "TIME_GRAIN_FIELD":
                assert failed["validation"]["category"] == "INVALID_TIME_GRAIN_FIELD"
                expected = {"code": "INVALID_TIME_GRAIN_FIELD", "path": "/reportDesign"}
            else:
                assert failed["validation"]["category"] == "REPORT_DESIGN_NORMALIZATION_FAILED"
                assert "LAYOUT_CAPACITY_EXCEEDED" in failed["validation"]["structural_detail"]
                return
            assert json.loads(failed["validation"]["structural_detail"])["findings"] == [expected]
            assert "Metrics.Missing" not in json.dumps(history)
            assert "Draft Visits" not in json.dumps(history)
            return
        assert proposed.status_code == 201, proposed.text
        result = proposed.json()
        assert result["attempt"]["status"] == "ELIGIBLE"
        capabilities = provider.requests[-1].context["rendererCapabilities"]
        assert capabilities["source"] == "ACTIVE_COMPILER"
        assert capabilities["designVersion"] == 2
        assert capabilities["geometryBinding"] == "AI_AUTHORED_EXACT"
        assert "slots" not in capabilities and "pageBounds" not in capabilities
        assert capabilities["knowledgeScope"] == (
            "PROVIDER_MANAGED_OBSERVED_REFERENCES" if foundry else
            "BUNDLED_DOCUMENTS_ONLY_NO_PROVIDER_MANAGED_TENANT_RAG"
        )
        assert "will not supply coordinates, resize, reorder" in provider.requests[-1].system_prompt
        with database.session() as db:
            stored = json.loads(db.scalar(text(
                "SELECT design_json FROM reviewed_report_designs WHERE id=:id"
            ), {"id": result["reviewed_design"]["id"]}))
        assert stored == original_design
        built = runtime.post(
            f"/api/cases/{case['id']}/generation",
            json={
                "confirmed_contract_id": contract["id"],
                "reviewed_design_id": result["reviewed_design"]["id"],
                "command_key": str(uuid4()),
            },
            headers=csrf(session),
        )
        assert built.status_code == 201, built.text
        attempt = built.json()["attempt"]
        assert attempt["status"] == "SUCCEEDED"
        assert attempt["validation"]["stages"]["businessQuality"] == "NOT_CERTIFIED"
        assert attempt["validation"]["runtime"] == {
            "providerCalls": 0, "powerBiDesktop": "NOT_RUN", "dax": "NOT_RUN",
            "rls": "NOT_RUN", "deployment": "NOT_RUN",
        }
        path = f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact"
        download = runtime.get(path)
        assert download.status_code == 200
        assert hashlib.sha256(download.content).hexdigest() == attempt["artifact"]["content_digest"]
        with zipfile.ZipFile(BytesIO(download.content)) as archive:
            assert any(name.endswith(".pbip") for name in archive.namelist())
            assert json.loads(archive.read("ReportDesign.json")) == original_design
            assert "Physical layout pagination" not in archive.read("Delivery-Guide.md").decode()
            # Validate physical files in the model's page and visual order, not
            # just the source JSON retained alongside the compiled candidate.
            pages_root = f"{original_design['projectName']}.Report/definition/pages"
            page_order = json.loads(archive.read(f"{pages_root}/pages.json"))["pageOrder"]
            assert len(page_order) == len(original_design["pages"])
            measure_bindings = {}
            table_root = f"{original_design['projectName']}.SemanticModel/definition/tables/"
            for measure in original_design["measures"]:
                table, column = measure["field"].split(".")
                expression = f"{measure['aggregation']}({table}[{column}])"
                quoted_name = "'" + measure["name"].replace("'", "''") + "'"
                declarations = []
                for name in archive.namelist():
                    if name.startswith(table_root) and name.endswith(".tmdl"):
                        lines = archive.read(name).decode().splitlines()
                        if any(f"\tmeasure {label} = {expression}" in lines
                               for label in (measure["name"], quoted_name)):
                            declarations.append(Path(name).stem)
                assert len(declarations) == 1
                home = declarations[0]
                if overview == "Shared-name draft":
                    assert home.startswith("__APBRA_Measures_")
                    assert "\tcolumn Visits" in archive.read(
                        table_root + "Metrics.tmdl"
                    ).decode().splitlines()
                else:
                    assert home == "Metrics"
                measure_bindings[measure["id"]] = f"{home}.{measure['name']}"
            compiled_types = {"card": "cardVisual", "bar": "barChart", "column": "columnChart",
                              "line": "lineChart", "table": "tableEx", "slicer": "slicer"}
            for page_id, planned_page in zip(page_order, original_design["pages"], strict=True):
                prefix = f"{pages_root}/{page_id}"
                physical_page = json.loads(archive.read(f"{prefix}/page.json"))
                assert physical_page["displayName"] == planned_page["name"]
                assert physical_page["displayOption"] == planned_page["displayOption"]
                for dimension in ("width", "height"):
                    if planned_page.get(dimension) is None:
                        assert dimension not in physical_page
                    else:
                        assert physical_page[dimension] == planned_page[dimension]
                visual_files = [json.loads(archive.read(name)) for name in archive.namelist()
                                if name.startswith(prefix + "/visuals/")
                                and name.endswith("/visual.json")]
                ordered_visuals = sorted(
                    visual_files, key=lambda item: item["position"]["tabOrder"]
                )
                assert len(ordered_visuals) == len(planned_page["visuals"])
                for _index, (physical, planned) in enumerate(zip(
                    ordered_visuals, planned_page["visuals"], strict=True
                )):
                    kind = planned["type"]
                    assert physical["position"] == {
                        key: value for key, value in planned["position"].items()
                        if value is not None
                    }
                    assert physical["visual"]["visualType"] == compiled_types[kind]
                    measures = [measure_bindings[item] for item in planned["measureIds"]]
                    if kind == "card":
                        expected_roles = {"Data": measures}
                    elif kind in {"bar", "column", "line"}:
                        expected_roles = {"Category": [planned["categoryField"]], "Y": measures}
                    else:
                        expected_roles = {"Values": planned["fields"] + measures}
                    query = physical["visual"]["query"]["queryState"]
                    assert {role: [item["queryRef"] for item in value["projections"]]
                            for role, value in query.items()} == expected_roles
                for index, physical in enumerate(ordered_visuals):
                    left = physical["position"]
                    for other in ordered_visuals[index + 1:]:
                        right = other["position"]
                        assert not (
                            left["x"] < right["x"] + right["width"]
                            and right["x"] < left["x"] + left["width"]
                            and left["y"] < right["y"] + right["height"]
                            and right["y"] < left["y"] + left["height"]
                        )

            assert b"editable first draft" in archive.read("Delivery-Guide.md")
            if foundry:
                assert b"Provider-managed grounding" in archive.read("Delivery-Guide.md")
                assert b"OFFLINE_FIXTURE" in archive.read("Delivery-Guide.md")
                expected_references = [reference] if overview == "Grounded draft" else []
                evidence = (b"OBSERVED_TOOL_TRACE" if overview == "Grounded draft"
                            else b"NO_OBSERVED_RETRIEVAL")
                assert evidence in archive.read("Delivery-Guide.md")
                assert (
                    attempt["provenance"]["providerGrounding"]["references"] == expected_references
                )
                assert b"PRIVATE RAW TOOL CONTENT" not in download.content
                assert attempt["validation"]["pipelineProvenance"]["retrieval"]["strategy"] == (
                    "PROVIDER_MANAGED_OBSERVED_REFERENCES"
                )
        with TestClient(runtime.app) as outsider:
            sign_in(outsider, "foreign")
            assert outsider.get(path).status_code in {403, 404}
        assert contract == before
        persisted = runtime.get(f"/api/cases/{case['id']}").json()["case"]
        assert persisted["current_request"]["request_text"] == request
        saved_evidence = runtime.get(f"/api/cases/{case['id']}/evidence").json()["items"]
        assert saved_evidence[0]["content_digest"] == hashlib.sha256(csv).hexdigest()
        assert provider.requests[1].context["confirmedRequirements"] == (
            _provider_confirmed_requirements(contract["contract"])
        )
        stored = runtime.get(f"/api/cases/{case['id']}/acceptance").json()
        assert stored["confirmed_contract"]["contract"] == before["contract"]
        assert len(provider.requests) == 2
        if foundry:
            assert len(wire_calls) == 2
            assert provider.requests[1].context["governedKnowledge"] == []
            assert result["attempt"]["validation"]["providerGrounding"]["references"] == (
                [reference] if overview == "Grounded draft" else []
            )


def synthetic_large_confirmation() -> dict[str, object]:
    request = "Unique request detail retained. " * 1_600
    session = {
        "sessionId": "synthetic-session",
        "originalRequest": request,
        "contextBinding": json.dumps({"request": request, "history": ["Unique prior answer"]}),
        "mode": "GUIDED",
        "limits": {"maxRounds": 3},
        "rounds": [],
        "corrections": [],
        "designConflicts": [],
        "currentInterpretation": {"objective": "Unique objective"},
        "unresolvedAmbiguities": ["Unique assumption"],
        "confirmationSummary": {"objective": "Unique visible confirmation"},
        "analyses": [{"interpretation": {"objective": "Unique objective"}}],
    }
    binding = {key: value for key, value in session.items() if key != "analyses"}
    binding["lastAnalysis"] = session["analyses"][-1]
    session["readinessBinding"] = json.dumps(binding, sort_keys=True)
    return {"provenance": {"clarificationSession": session}, "objective": "Unique report goal"}


def packaging_request(contract: dict[str, object]) -> ProviderRequest:
    return ProviderRequest(
        task="REPORT_DESIGN",
        system_prompt="Preserve the complete confirmed context.",
        context={
            "confirmedRequirements": contract,
            "dataStructure": {
                "tables": [
                    {
                        "name": "UniqueEvidence",
                        "rows": [
                            [str(index), "Unique evidence value retained", "Other source value"]
                            for index in range(620)
                        ],
                    }
                ]
            },
            "governedKnowledge": [{"citation": "synthetic", "text": "Unique convention"}],
        },
        output_schema=report_design_schema(
            max_visuals_per_page=6, supported_trend_grains=["DAY", "MONTH", "QUARTER", "YEAR"]
        ),
    )


def test_provider_packaging_removes_only_duplicate_receipt_without_mutation() -> None:
    original = synthetic_large_confirmation()
    before = copy.deepcopy(original)
    provider = OpenAICompatibleProvider(automatic_test_provider([{}]).profile, "offline-secret")
    raw = packaging_request(original)
    with pytest.raises(ProviderCallError, match="MODEL_INPUT_BUDGET_EXCEEDED"):
        provider._request_body(raw)
    compact = _provider_confirmed_requirements(original)
    expected = copy.deepcopy(before)
    del expected["provenance"]["clarificationSession"]["readinessBinding"]
    assert compact == expected
    assert original == before
    request = packaging_request(compact)
    body = provider._request_body(request)
    assert len(json.dumps(body, separators=(",", ":"))) < 200_000
    assert provider.profile.max_input_characters == 200_000
    assert request.context["dataStructure"] == raw.context["dataStructure"]
    compact["provenance"]["clarificationSession"]["analyses"][0]["interpretation"]["objective"] = (
        "changed copy"
    )
    assert original == before


@pytest.mark.parametrize(
    "difference", ["unique_field", "changed_field", "malformed", "missing_history"]
)
def test_provider_packaging_preserves_unverified_receipt(difference: str) -> None:
    contract = synthetic_large_confirmation()
    session = contract["provenance"]["clarificationSession"]
    if difference == "malformed":
        session["readinessBinding"] = "not JSON"
    elif difference == "missing_history":
        session["analyses"] = []
    else:
        binding = json.loads(session["readinessBinding"])
        binding["unique_business_fact" if difference == "unique_field" else "originalRequest"] = (
            "Unique content"
        )
        session["readinessBinding"] = json.dumps(binding)
    assert _provider_confirmed_requirements(contract) == contract


def test_unique_oversized_context_still_fails_before_transport() -> None:
    contract = synthetic_large_confirmation()
    contract["uniqueBusinessContext"] = "Unshared business detail " * 12_000
    observed: list[httpx.Request] = []
    provider = OpenAICompatibleProvider(
        automatic_test_provider([{}]).profile,
        "offline-secret",
        transport=httpx.MockTransport(
            lambda request: observed.append(request) or httpx.Response(500)
        ),
    )
    with pytest.raises(ProviderCallError, match="MODEL_INPUT_BUDGET_EXCEEDED") as captured:
        provider.structured(packaging_request(_provider_confirmed_requirements(contract)))
    assert captured.value.observation.call_count == 0
    assert observed == []
    assert contract["uniqueBusinessContext"].startswith("Unshared business detail")


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


def test_design_input_limit_is_reported_as_preflight_without_model_call(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Keep this complete synthetic requirement.",
        "Metrics.csv",
        b"Group,Visits\nA,7\nB,5\n",
    )
    observed: list[httpx.Request] = []
    profile = automatic_test_provider([{}]).profile.model_copy(
        update={"max_input_characters": 1_000}
    )
    provider = OpenAICompatibleProvider(
        profile,
        "offline-secret",
        transport=httpx.MockTransport(
            lambda request: observed.append(request) or httpx.Response(500)
        ),
    )
    with TestClient(
        create_app(settings=settings, database=database, model_provider=provider)
    ) as runtime:
        runtime.cookies.update(client.cookies)
        result = runtime.post(
            f"/api/cases/{case['id']}/automatic-designs",
            json={"confirmed_contract_id": contract["id"], "command_key": str(uuid4())},
            headers=csrf(session),
        )
        assert result.status_code == 409
        history = runtime.get(
            f"/api/cases/{case['id']}/automatic-designs",
            params={"confirmed_contract_id": contract["id"]},
        ).json()["items"]
        assert history[0]["failure"]["code"] == "MODEL_INPUT_BUDGET_EXCEEDED"
        assert "before a model call" in history[0]["failure"]["message"]
        assert history[0]["usage"]["call_count"] == 0
        assert observed == []
        saved = runtime.get(f"/api/cases/{case['id']}/acceptance").json()
        assert saved["confirmed_contract"]["contract"] == contract["contract"]


def test_server_rejects_tampered_confirmation_before_provider_packaging(
    client: TestClient, settings: Settings, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client, session, "Keep the exact visible synthetic confirmation.", "Metrics.csv",
        b"Group,Visits\nA,7\nB,5\n",
    )
    with pytest.raises(DBAPIError, match="immutable"), database.session() as db:
        stored = db.get(ConfirmedContractRow, UUID(contract["id"]))
        payload = json.loads(stored.contract_json)
        payload["provenance"]["clarificationSession"]["readinessBinding"] = "tampered"
        stored.contract_json = json.dumps(payload)
        db.flush()
    original_payload = GenerationService._current_payload

    def corrupted_payload(self, *args, **kwargs):
        value, *rest = original_payload(self, *args, **kwargs)
        value = copy.deepcopy(value)
        value["contract"]["provenance"]["clarificationSession"]["readinessBinding"] = "tampered"
        return value, *rest

    monkeypatch.setattr(GenerationService, "_current_payload", corrupted_payload)
    provider = automatic_test_provider([{}])
    with TestClient(
        create_app(settings=settings, database=database, model_provider=provider)
    ) as runtime:
        runtime.cookies.update(client.cookies)
        result = runtime.post(
            f"/api/cases/{case['id']}/automatic-designs",
            json={"confirmed_contract_id": contract["id"], "command_key": str(uuid4())},
            headers=csrf(session),
        )
        assert result.status_code == 409
        assert provider.requests == []
        history = runtime.get(
            f"/api/cases/{case['id']}/automatic-designs",
            params={"confirmed_contract_id": contract["id"]},
        ).json()["items"]
        assert history[0]["status"] == "FAILED"
        assert history[0]["validation"]["category"] == "CONFIRMED_REQUIREMENT_CONTRACT_INVALID"
        assert history[0]["validation"]["status"] == "FAILED"


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
    return authored_test_geometry({
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
    })


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
    assert attempt["status"] == "SUCCEEDED", attempt["failure"]
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
        guide = archive.read("Delivery-Guide.md")
        assert hashlib.sha256(guide).hexdigest() == attempt["artifact"]["guide_digest"]
        text = guide.decode("utf-8")
        assert attempt["id"] in text
        assert contract["id"] in text
        assert "Generation is not deployment approval" in text


def test_unsafe_unused_csv_header_cannot_yield_a_protected_pass_artifact(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    header = 'Unused", each 1), Injected = 1 //'
    content = b'Category,Cost,"Unused"", each 1), Injected = 1 //"\nA,10,x\nB,20,y\n'
    case, contract = confirmed_case(
        client, session, "Show total cost by category.", "costs.csv", content
    )
    response = client.post(
        f"/api/cases/{case['id']}/generation",
        json={
            "confirmed_contract_id": contract["id"],
            "reviewed_design_id": contract["reviewed_design_id"],
            "command_key": str(uuid4()),
        },
        headers=csrf(session),
    )
    assert response.status_code == 201, response.text
    attempt = response.json()["attempt"]
    assert attempt["status"] == "FAILED"
    assert attempt["artifact"] is None
    artifact = client.get(f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact")
    assert artifact.status_code == 404
    history = client.get(f"/api/cases/{case['id']}/generation").json()["items"]
    assert history[0]["id"] == attempt["id"]
    assert header not in response.text
    assert header in [
        column["name"]
        for table in contract["contract"]["provenance"]["dataStructure"]["tables"]
        for column in table["columns"]
    ]


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
        assert "editable first-draft" in prompt
        assert "are not software delivery gates" in prompt
        assert "Measures and pages may differ" in prompt
        assert "rendererCapabilities" in prompt
        assert "You author every measure" in prompt
        assert "four general slots plus two card" not in prompt
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
    provider = automatic_test_provider(
        [
            {"untrusted": "first rejected report design"},
            {"untrusted": "second rejected report design"},
        ]
    )
    command_key = str(uuid4())
    with TestClient(
        create_app(settings=settings, database=database, model_provider=provider)
    ) as automatic_client:
        automatic_client.cookies.update(client.cookies)
        rejected = automatic_client.post(
            f"/api/cases/{case['id']}/automatic-designs",
            json={
                "confirmed_contract_id": contract["id"],
                "command_key": command_key,
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
        failed = history.json()["items"][0]
        assert failed["status"] == "FAILED"
        assert failed["provider_profile_id"] == "qualified-test-profile"
        assert failed["model_or_deployment"] == "qualified-test-model"
        assert failed["prompt_version"] == "report-design-v1"
        assert failed["configuration_id"] == "accepted-test-configuration"
        assert failed["capability_profile"] == {
            "structured_output": True,
            "vision": False,
        }
        assert failed["usage"] == {
            "call_count": 2,
            "completion_tokens": 40,
            "latency_ms": 2,
            "prompt_tokens": 20,
            "total_tokens": 60,
        }
        assert failed["validation"]["category"] == "REPORT_DESIGN_INVALID"
        assert failed["validation"]["detail_status"] == "RECORDED"
        assert failed["validation"]["stage"] == "REPORT_DESIGN_DETERMINISTIC_VALIDATION"
        assert failed["validation"]["status"] == "FAILED"
        assert json.loads(failed["validation"]["structural_detail"]) == {
            "stage": "REPORT_DESIGN",
            "findings": [{"code": "REPORT_DESIGN_INVALID", "path": "/reportDesign"}],
            "truncated": False,
        }
        assert failed["failure"]["code"] == "MODEL_CANDIDATE_REJECTED"
        assert "first rejected" not in history.text
        assert "second rejected" not in history.text
        with database.session() as db:
            persisted = db.scalar(
                select(AutomaticDesignAttemptRow).where(
                    AutomaticDesignAttemptRow.command_key == command_key
                )
            )
            assert persisted is not None
            assert persisted.candidate_digest is not None
            assert len(persisted.candidate_digest) == 64
        assert (
            automatic_client.get(f"/api/cases/{case['id']}/acceptance").json()[
                "confirmed_contract"
            ]["current"]
            is True
        )
        designs = automatic_client.get(
            f"/api/cases/{case['id']}/reviewed-designs",
            params={"confirmed_contract_id": contract["id"]},
        )
        assert designs.status_code == 200
        assert all(item["origin"] != "AUTO_ELIGIBLE" for item in designs.json()["items"])

    restarted_database = Database(settings.database_url)
    with TestClient(
        create_app(settings=settings, database=restarted_database, model_provider=provider)
    ) as restarted:
        restarted.cookies.update(client.cookies)
        durable = restarted.get(
            f"/api/cases/{case['id']}/automatic-designs",
            params={"confirmed_contract_id": contract["id"]},
        )
        assert durable.status_code == 200
        assert durable.json()["items"][0]["usage"]["call_count"] == 2
        assert durable.json()["items"][0]["validation"]["status"] == "FAILED"
    restarted_database.engine.dispose()

    foreign = TestClient(create_app(settings=settings, database=database, model_provider=provider))
    try:
        sign_in(foreign, "foreign")
        assert (
            foreign.get(
                f"/api/cases/{case['id']}/automatic-designs",
                params={"confirmed_contract_id": contract["id"]},
            ).status_code
            == 404
        )
    finally:
        foreign.close()

    with database.session() as db:
        db.execute(
            text("UPDATE memberships SET active=false WHERE id=:id"),
            {"id": session["actor"]["membership_id"]},  # type: ignore[index]
        )
    assert client.get(
        f"/api/cases/{case['id']}/automatic-designs",
        params={"confirmed_contract_id": contract["id"]},
    ).status_code in {401, 404}


def test_provider_failure_after_real_call_persists_safe_observation_only(
    client: TestClient, settings: Settings, database: Database
) -> None:
    session = sign_in(client, "member")
    case, contract = confirmed_case(
        client,
        session,
        "Summarise qualified request counts by service group.",
        "requests.csv",
        b"Group,Requests\nA,7\nB,5\n",
    )
    test_profile = automatic_test_provider([{}]).profile
    provider = OpenAICompatibleProvider(
        test_profile,
        "server-secret",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(403, text="credential=server-secret hidden-body")
        ),
    )
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
        assert "server-secret" not in rejected.text
        assert "hidden-body" not in rejected.text
        history = automatic_client.get(
            f"/api/cases/{case['id']}/automatic-designs",
            params={"confirmed_contract_id": contract["id"]},
        )
        assert history.status_code == 200
        failed = history.json()["items"][0]
        assert failed["status"] == "FAILED"
        assert failed["provider_profile_id"] == "qualified-test-profile"
        assert failed["model_or_deployment"] == "qualified-test-model"
        assert failed["usage"] == {
            "call_count": 1,
            "completion_tokens": None,
            "latency_ms": failed["usage"]["latency_ms"],
            "prompt_tokens": None,
            "total_tokens": None,
        }
        assert failed["usage"]["latency_ms"] >= 0
        assert failed["validation"] is None
        assert failed["failure"]["code"] == "MODEL_PROVIDER_REJECTED"
        assert "server-secret" not in history.text
        assert "hidden-body" not in history.text


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


def test_portable_artifact_adapter_preserves_generation_download_and_isolation(
    settings: Settings, database: Database
) -> None:
    backing: dict[str, bytes] = {}

    class SharedArtifacts:
        def write(
            self, company_id: UUID, case_id: UUID, attempt_id: UUID, content: bytes
        ) -> tuple[str, str, int]:
            key = f"{company_id}/{case_id}/{attempt_id}/{uuid4().hex}.zip"
            assert key not in backing
            backing[key] = content
            return key, hashlib.sha256(content).hexdigest(), len(content)

        def read(self, storage_key: str, expected_digest: str, expected_size: int) -> bytes:
            content = backing.get(storage_key)
            if content is None or len(content) != expected_size:
                raise ArtifactError("Artifact object is unavailable.")
            if hashlib.sha256(content).hexdigest() != expected_digest:
                raise ArtifactError("Artifact integrity verification failed.")
            return content

        def delete_uncommitted(self, storage_key: str) -> None:
            backing.pop(storage_key, None)

    with TestClient(
        create_app(settings=settings, database=database, artifact_objects=SharedArtifacts())
    ) as client:
        session = sign_in(client, "member")
        case, contract = confirmed_case(
            client,
            session,
            "Compare synthetic orders by zone.",
            "synthetic.csv",
            b"Zone,Orders\nNorth,4\nSouth,6\n",
        )
        result = client.post(
            f"/api/cases/{case['id']}/generation",
            json={
                "confirmed_contract_id": contract["id"],
                "reviewed_design_id": contract["reviewed_design_id"],
                "command_key": str(uuid4()),
            },
            headers=csrf(session),
        )
        assert result.status_code == 201, result.text
        attempt = result.json()["attempt"]
        assert attempt["status"] == "SUCCEEDED"
        assert len(backing) == 1

    with TestClient(
        create_app(settings=settings, database=database, artifact_objects=SharedArtifacts())
    ) as restarted:
        sign_in(restarted, "member")
        path = f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact"
        download = restarted.get(path)
        assert download.status_code == 200
        assert hashlib.sha256(download.content).hexdigest() == attempt["artifact"]["content_digest"]
        with TestClient(restarted.app) as foreign:
            sign_in(foreign, "foreign")
            assert foreign.get(path).status_code == 404
        key = next(iter(backing))
        backing[key] = b"altered"
        assert restarted.get(path).status_code == 404
        backing.pop(key)
        assert restarted.get(path).status_code == 404


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


@pytest.mark.parametrize(
    "unsafe",
    [
        {"stage": "private credential", "findings": [], "truncated": False},
        {"stage": [], "findings": [], "truncated": False},
        {"stage": "COMPILER", "findings": [], "truncated": False, "raw": "private"},
        {"stage": "REPORT_DESIGN", "findings": [], "truncated": "false"},
        {"stage": "REPORT_DESIGN", "findings": "private", "truncated": False},
        {
            "stage": "REPORT_DESIGN",
            "findings": [{"code": "PRIVATE", "path": "/reportDesign"}],
            "truncated": False,
        },
        {
            "stage": "REPORT_DESIGN",
            "findings": [{"code": "UNKNOWN_MEASURE_FIELD", "path": "/reportDesign/private-field"}],
            "truncated": False,
        },
        {
            "stage": "REPORT_DESIGN",
            "findings": [
                {"code": "UNKNOWN_MEASURE_FIELD", "path": "/reportDesign/measures/1000000/field"}
            ],
            "truncated": False,
        },
        {
            "stage": "REPORT_DESIGN",
            "findings": [
                {"code": "UNKNOWN_MEASURE_FIELD", "path": "/reportDesign", "reason": "private"}
            ],
            "truncated": False,
        },
        {
            "stage": "REPORT_DESIGN",
            "findings": [{"code": "UNKNOWN_MEASURE_FIELD", "path": "/reportDesign"}] * 4,
            "truncated": False,
        },
    ],
)
def test_structured_bridge_details_reject_private_or_malformed_payloads(unsafe: dict) -> None:
    failure = GenerationBridgeFailure("REPORT_DESIGN_MEASURE_INTEGRITY", json.dumps(unsafe))
    assert _safe_bridge_diagnostic_detail(failure) is None
    assert _safe_failed_validation(failure)["detail_status"] == "WITHHELD"


@pytest.mark.parametrize(
    "path",
    ["/reportDesign/measures", "/reportDesign/measures/2", "/reportDesign/pages/0/visuals/1"],
)
def test_structured_bridge_details_allow_conservative_parent_paths(path: str) -> None:
    detail = {
        "stage": "REPORT_DESIGN",
        "findings": [{"code": "UNRESOLVED_MEASURE_OPERAND", "path": path}],
        "truncated": True,
    }
    failure = GenerationBridgeFailure("REPORT_DESIGN_MEASURE_INTEGRITY", json.dumps(detail))
    assert json.loads(_safe_bridge_diagnostic_detail(failure)) == detail


def test_structured_bridge_details_preserve_only_safe_invariant_paths() -> None:
    detail = {
        "stage": "REPORT_DESIGN",
        "findings": [{"code": "UNKNOWN_MEASURE_FIELD", "path": "/reportDesign/measures/0/field"}],
        "truncated": False,
    }
    failure = GenerationBridgeFailure("REPORT_DESIGN_MEASURE_INTEGRITY", json.dumps(detail))
    assert json.loads(_safe_bridge_diagnostic_detail(failure)) == detail
    for message in ("private provider payload", '{"stage":'):
        assert (
            _safe_bridge_diagnostic_detail(
                GenerationBridgeFailure("REPORT_DESIGN_INVALID", message)
            )
            is None
        )
    compiler = GenerationBridgeFailure(
        "GENERATION_PIPELINE_FAILED",
        json.dumps({"stage": "COMPILER", "findings": [], "truncated": False}),
    )
    assert json.loads(_safe_bridge_diagnostic_detail(compiler))["stage"] == "COMPILER"


def test_layout_retry_is_ai_authored_and_other_rejections_remain_generic() -> None:
    layout = _automatic_design_retry_instruction(
        GenerationBridgeFailure(
            "REPORT_DESIGN_NORMALIZATION_FAILED",
            "REPORT_DESIGN_NORMALIZATION_FAILED: LAYOUT_CAPACITY_EXCEEDED",
        ),
        max_visuals_per_page=6,
    )
    assert "fixed slots" not in layout
    assert "tenant page limit" not in layout
    assert "fully revalidated" in layout
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


@pytest.mark.parametrize("adapter", ["local", "alternate"])
def test_lost_artifact_commit_acknowledgment_preserves_successful_bytes(
    settings: Settings,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    adapter: str,
) -> None:
    backing: dict[str, bytes] = {}
    objects = (
        LocalArtifactStore(settings.artifact_root, "test")
        if adapter == "local"
        else MemoryArtifactStore(backing)
    )
    with TestClient(
        create_app(settings=settings, database=database, artifact_objects=objects)
    ) as client:
        session = sign_in(client, "member")
        case, contract = confirmed_case(
            client,
            session,
            "Compare synthetic balances by group.",
            "balances.csv",
            b"Group,Balance\nCurrent,31\nReserve,12\n",
        )
        original_add = ApplicationSession.add_generated_artifact
        original_commit = ApplicationSession.commit

        def mark_artifact(self: ApplicationSession, *args: object, **kwargs: object) -> object:
            result = original_add(self, *args, **kwargs)
            self.info["synthetic_artifact_commit"] = True
            return result

        def commit_with_lost_ack(self: ApplicationSession) -> None:
            original_commit(self)
            if self.info.pop("synthetic_artifact_commit", False):
                raise RuntimeError("synthetic lost artifact commit acknowledgment")

        with monkeypatch.context() as scoped:
            scoped.setattr(ApplicationSession, "add_generated_artifact", mark_artifact)
            scoped.setattr(ApplicationSession, "commit", commit_with_lost_ack)
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
        assert attempt["status"] == "SUCCEEDED"
        assert attempt["artifact"] is not None
        download = client.get(
            f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact"
        )
        assert download.status_code == 200
        assert hashlib.sha256(download.content).hexdigest() == attempt["artifact"]["content_digest"]


def test_foundry_observed_reference_flows_through_confirmation_design_guide_and_protected_download(
    settings: Settings, database: Database, monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_editable_draft_whole_chain_preserves_context_and_protected_download(
        settings, database, "", "Grounded draft", True, monkeypatch,
    )


@pytest.mark.parametrize("cache", ["command", "equivalent", "none", "conflict"])
def test_legacy_build_replays_original_artifact_before_new_geometry_gate(
    monkeypatch: pytest.MonkeyPatch, cache: str,
) -> None:
    from types import SimpleNamespace

    import apbra_api.generation as generation_module
    from apbra_api.domain import IdempotencyConflict
    from apbra_api.generation import AIAuthoredGeometryRequired, canonical_digest

    design_id = uuid4()
    design = {"artifact_kind": "ReportDesign", "schema_version": 1, "pages": []}
    payload = {"binding": {"synthetic": "current-protected-binding"}}
    semantic = canonical_digest({**payload, "reportDesign": design})
    historical_input = canonical_digest({"semanticInputDigest": semantic,
        "reviewedDesignId": str(design_id), "pipelineExecutableDigest": "old-pipeline"})
    saved = SimpleNamespace(id=uuid4(), input_digest=historical_input,
        provenance_json=json.dumps({"pipelineExecutableDigest": "old-pipeline"}),
        command_payload_digest=canonical_digest({"inputDigest": historical_input,
            "mode": "BUILD", "sourceAttemptId": None}))
    if cache == "conflict":
        saved.command_payload_digest = "changed-command"
    store = SimpleNamespace(
        generation_attempt_by_command=lambda *args: saved if cache in {"command", "conflict"}
        else None,
        equivalent_generation_attempt=lambda *args: None,
        generation_attempts=lambda *args: [saved] if cache == "equivalent" else [],
    )
    service = GenerationService(SimpleNamespace(pipeline_digest="new-pipeline"), None, None)
    monkeypatch.setattr(service, "_current_payload", lambda *args: (
        copy.deepcopy(payload), "semantic", "evidence", None, None))
    monkeypatch.setattr(service, "_eligible_design", lambda *args: (
        SimpleNamespace(id=design_id, origin="EXPERT_REVIEWED"), design))
    monkeypatch.setattr(generation_module, "attempt_json", lambda *args: {"id": str(saved.id)})
    def call() -> tuple[dict[str, object], bool]:
        return service.start(store, None, uuid4(), contract_id=uuid4(),
            command_key="synthetic-original-command", reviewed_design_id=design_id)
    if cache == "none":
        with pytest.raises(AIAuthoredGeometryRequired):
            call()
    elif cache == "conflict":
        with pytest.raises(IdempotencyConflict):
            call()
    else:
        assert call() == ({"id": str(saved.id)}, False)
    assert design == {"artifact_kind": "ReportDesign", "schema_version": 1, "pages": []}


@pytest.mark.parametrize(
    "invalid", ["legacy", "unknown-version", "boolean-position", "no-position",
                "precision-position", "precision-page"],
)
def test_new_design_intake_rejects_legacy_or_invalid_geometry_without_saved_version_changes(
    client: TestClient, database: Database, invalid: str,
) -> None:
    member = sign_in(client, "member")
    case, contract = confirmed_case(client, member, "Show duration by team.", "duration.csv",
        b"Team,Duration\nA,2\nB,5\n")
    design = copy.deepcopy(contract["reviewed_report_design"])
    if invalid == "legacy":
        design["schema_version"] = 1
    elif invalid == "unknown-version":
        design["schema_version"] = 3
    elif invalid == "boolean-position":
        design["pages"][0]["visuals"][0]["position"]["x"] = True
    elif invalid == "precision-position":
        design["pages"][0]["visuals"][0]["position"]["angle"] = 9007199254740993
    elif invalid == "precision-page":
        design["pages"][0]["height"] = 9007199254740993
    else:
        del design["pages"][0]["visuals"][0]["position"]
    with database.session() as db:
        before = db.execute(text("SELECT id, design_json, content_digest "
            "FROM reviewed_report_designs"
            " WHERE case_id=:id ORDER BY id"), {"id": case["id"]}).all()
    with TestClient(client.app) as expert:
        session = sign_in(expert, "uninvited")
        response = expert.post(f"/api/cases/{case['id']}/reviewed-designs", headers=csrf(session),
            json={"confirmed_contract_id": contract["id"], "report_design": design})
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == (
            "AI_AUTHORED_GEOMETRY_REQUIRED" if invalid == "legacy"
            else "REPORT_DESIGN_GEOMETRY_UNREPRESENTABLE" if invalid.startswith("precision-")
            else "TRUSTED_REPORT_DESIGN_REQUIRED")
    with database.session() as db:
        after = db.execute(text("SELECT id, design_json, content_digest "
            "FROM reviewed_report_designs"
            " WHERE case_id=:id ORDER BY id"), {"id": case["id"]}).all()
    assert after == before


def raw_intake_source(contract: dict[str, object], where: str, token: str) -> str:
    design = copy.deepcopy(contract["reviewed_report_design"])
    design["overview"] = "RAW_PRIVATE_CANARY"
    target = design["pages"][0] if where.startswith("page.") else (
        design["pages"][0]["visuals"][0]["position"])
    target[where.split(".")[-1]] = "RAW_GEOMETRY_LITERAL"
    return json.dumps({"confirmed_contract_id": contract["id"], "report_design": design}).replace(
        '"RAW_GEOMETRY_LITERAL"', token)


def intake_storage_snapshot(database: Database) -> tuple[list[object], dict[str, int]]:
    with database.session() as db:
        designs = list(db.execute(text(
            "SELECT id, design_json, content_digest FROM reviewed_report_designs ORDER BY id"
        )).all())
        counts = dict(db.execute(text(
            "SELECT (SELECT count(*) FROM reviewed_report_designs) AS designs, "
            "(SELECT count(*) FROM generation_attempts) AS generations, "
            "(SELECT count(*) FROM automatic_design_attempts) AS proposals, "
            "(SELECT count(*) FROM audit_events) AS audits"
        )).one()._mapping)
    return designs, counts


@pytest.mark.parametrize("where", ["page.width", "page.height", "x", "y", "width", "height",
                                  "z", "tabOrder", "angle"])
@pytest.mark.parametrize("token", ["9007199254740993", "9007199254740993.0",
                                   "9.007199254740993e15", "1.0000000000000001"])
def test_expert_raw_http_geometry_precision_is_rejected_before_any_intake_write(
    client: TestClient, database: Database, where: str, token: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    member = sign_in(client, "member")
    case, contract = confirmed_case(client, member, "Show hours by team.", "raw-hours.csv",
        b"Team,Hours\nA,2\nB,5\n")
    with TestClient(client.app) as expert:
        session = sign_in(expert, "uninvited")
        before = intake_storage_snapshot(database)
        result = expert.post(f"/api/cases/{case['id']}/reviewed-designs",
            headers={**csrf(session), "Content-Type": "application/json"},
            content=raw_intake_source(contract, where, token))
        assert result.status_code == 422, result.text
        assert result.json()["error"]["code"] == "REPORT_DESIGN_GEOMETRY_UNREPRESENTABLE"
        assert "RAW_PRIVATE_CANARY" not in result.text + caplog.text
        assert token not in result.text + caplog.text
        assert intake_storage_snapshot(database) == before


@pytest.mark.parametrize(
    "denied", ["member", "foreign", "revoked-access", "revoked-membership", "csrf", "anonymous"],
)
def test_raw_geometry_check_preserves_auth_csrf_and_case_acl_error_priority(
    client: TestClient, database: Database, denied: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import apbra_api.generation as generation_module
    member = sign_in(client, "member")
    case, contract = confirmed_case(client, member, "Show hours by team.", "priority.csv",
        b"Team,Hours\nA,2\nB,5\n")
    raw = raw_intake_source(contract, "x", "1.0000000000000001")
    calls = []

    def forbidden_raw_check(*args: object) -> None:
        calls.append(True)
        raise AssertionError("Raw geometry must not be checked before authorization")

    monkeypatch.setattr(
        generation_module, "validate_report_design_raw_ingress", forbidden_raw_check,
    )
    with TestClient(client.app) as requester:
        session = None if denied == "anonymous" else sign_in(requester,
            denied if denied in {"member", "foreign"} else "uninvited")
        if denied == "revoked-access":
            revoke = client.post(
                f"/api/cases/{case['id']}/access/{session['actor']['membership_id']}/revoke",
                headers=csrf(member))
            assert revoke.status_code == 200, revoke.text
        if denied == "revoked-membership":
            with database.session() as db:
                db.execute(text("UPDATE memberships SET active=false WHERE id=:id"),
                    {"id": session["actor"]["membership_id"]})
        headers = {"Content-Type": "application/json"}
        if session is not None and denied != "csrf":
            headers.update(csrf(session))
        before = intake_storage_snapshot(database)
        response = requester.post(f"/api/cases/{case['id']}/reviewed-designs",
            headers=headers, content=raw)
        expected = {401, 404} if denied == "revoked-membership" else {
            401 if denied in {"csrf", "anonymous"} else 404,
        }
        assert response.status_code in expected
        assert response.json()["error"]["code"] != "REPORT_DESIGN_GEOMETRY_UNREPRESENTABLE"
        assert calls == []
        assert intake_storage_snapshot(database) == before


@pytest.mark.parametrize("token", ["1152921504606846976", "1152921504606846976.0",
                                   "1.152921504606846976e18"])
def test_expert_raw_exact_large_geometry_survives_saved_source_and_protected_pbip(
    client: TestClient, database: Database, token: str,
) -> None:
    from decimal import Decimal
    member = sign_in(client, "member")
    case, contract = confirmed_case(client, member, "Show hours by team.", "exactraw.csv",
        b"Team,Hours\nA,2\nB,5\n")
    design = copy.deepcopy(contract["reviewed_report_design"])
    for key in ("width", "height"):
        design["pages"][0][key] = "RAW_GEOMETRY_LITERAL"
    for key in ("x", "y", "width", "height", "z", "tabOrder", "angle"):
        design["pages"][0]["visuals"][0]["position"][key] = "RAW_GEOMETRY_LITERAL"
    raw = json.dumps({"confirmed_contract_id": contract["id"], "report_design": design}).replace(
        '"RAW_GEOMETRY_LITERAL"', token)
    before, _ = intake_storage_snapshot(database)
    with TestClient(client.app) as expert:
        session = sign_in(expert, "uninvited")
        response = expert.post(f"/api/cases/{case['id']}/reviewed-designs",
            headers={**csrf(session), "Content-Type": "application/json"}, content=raw)
        assert response.status_code == 201, response.text
        plan_id = response.json()["reviewed_design"]["id"]
    with database.session() as db:
        saved_text = db.scalar(text("SELECT design_json FROM reviewed_report_designs WHERE id=:id"),
            {"id": plan_id})
    saved = json.loads(saved_text, parse_float=Decimal)
    assert saved["pages"][0]["width"] == 2**60
    assert saved["pages"][0]["height"] == 2**60
    assert all(value == 2**60 for value in saved["pages"][0]["visuals"][0]["position"].values())
    after, _ = intake_storage_snapshot(database)
    assert all(item in after for item in before)
    generated = client.post(f"/api/cases/{case['id']}/generation", headers=csrf(member),
        json={"confirmed_contract_id": contract["id"], "reviewed_design_id": plan_id,
              "command_key": str(uuid4())})
    assert generated.status_code == 201, generated.text
    attempt = generated.json()["attempt"]
    assert attempt["status"] == "SUCCEEDED", {
        "failure": attempt.get("failure"), "validation": attempt.get("validation"),
    }
    artifact = client.get(f"/api/cases/{case['id']}/generation/{attempt['id']}/artifact")
    assert artifact.status_code == 200
    with zipfile.ZipFile(BytesIO(artifact.content)) as archive:
        source = json.loads(archive.read("ReportDesign.json"), parse_float=Decimal)
        assert source == saved
        root = f"{source['projectName']}.Report/definition/pages"
        order = json.loads(archive.read(f"{root}/pages.json"))["pageOrder"]
        physical_page = json.loads(
            archive.read(f"{root}/{order[0]}/page.json"), parse_float=Decimal,
        )
        assert physical_page["width"] == physical_page["height"] == 2**60
        physical_visuals = [json.loads(archive.read(name), parse_float=Decimal)
            for name in archive.namelist() if name.startswith(f"{root}/{order[0]}/visuals/")
            and name.endswith("/visual.json")]
        assert any(all(value == 2**60 for value in visual["position"].values())
                   for visual in physical_visuals)


def test_raw_intake_keeps_sync_work_off_asgi_loop_while_health_remains_available(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import apbra_api.generation as generation_module
    member = sign_in(client, "member")
    case, contract = confirmed_case(client, member, "Show hours by team.", "responsive.csv",
        b"Team,Hours\nA,2\nB,5\n")
    original = generation_module.validate_report_design_raw_ingress
    entered, release = Event(), Event()

    def blocked_raw_check(body: str) -> None:
        entered.set()
        assert release.wait(10)
        original(body)

    monkeypatch.setattr(generation_module, "validate_report_design_raw_ingress", blocked_raw_check)
    with TestClient(client.app) as expert, ThreadPoolExecutor(max_workers=2) as pool:
        session = sign_in(expert, "uninvited")
        submitted = pool.submit(expert.post, f"/api/cases/{case['id']}/reviewed-designs",
            headers={**csrf(session), "Content-Type": "application/json"},
            content=raw_intake_source(contract, "x", "-0.25"))
        try:
            assert entered.wait(5)
            health = pool.submit(expert.get, "/api/health")
            assert health.result(timeout=5).status_code == 200
            assert not submitted.done()
        finally:
            release.set()
        assert submitted.result(timeout=5).status_code == 201


@pytest.mark.parametrize("version", ["2.0000000000000001", "1.9999999999999999"])
def test_raw_http_unknown_version_alias_is_rejected_before_saved_source_write(
    client: TestClient, database: Database, version: str,
) -> None:
    member = sign_in(client, "member")
    case, contract = confirmed_case(client, member, "Show hours by team.", "version-raw.csv",
        b"Team,Hours\nA,2\nB,5\n")
    raw = raw_intake_source(contract, "x", "9007199254740993.0").replace(
        '"schema_version": 2', '"schema_version": ' + version)
    with TestClient(client.app) as expert:
        session = sign_in(expert, "uninvited")
        before = intake_storage_snapshot(database)
        response = expert.post(f"/api/cases/{case['id']}/reviewed-designs",
            headers={**csrf(session), "Content-Type": "application/json"}, content=raw)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "REPORT_DESIGN_GEOMETRY_UNREPRESENTABLE"
        assert intake_storage_snapshot(database) == before
