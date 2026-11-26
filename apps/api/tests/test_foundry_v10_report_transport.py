"""Exercise the saved-version transport using synthetic HTTP and the released private archive."""

import hashlib
import json
import time
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest

from apbra_api.evidence import LocalEvidenceStore, parse_evidence
from apbra_api.foundry_artifacts import GeneratedFile
from apbra_api.foundry_v10_report_transport import V10Operation, V10ReportTransport, json_digest
from apbra_api.model_provider import (
    FoundryAccess,
    FoundryBearer,
    ProviderCallError,
    ProviderProfile,
    ProviderRequest,
    requirement_analysis_schema,
)
from apbra_api.native_contracts import digest
from apbra_api.native_response_archive import NativeResponseArchive, NativeResponseScope

PROJECT = "https://synthetic.services.ai.azure.com/api/projects/demo"
AGENT = "synthetic-report-agent"
AGENT_REF = {"type": "agent_reference", "name": AGENT, "version": "10"}
FILE = GeneratedFile("cntr_demo", "cfile_demo", "report.pbip.zip")
CONTAINER_URL = f"{PROJECT}/openai/v1/containers/{FILE.container_id}"
FILE_URL = f"{CONTAINER_URL}/files/{FILE.file_id}"
REPORT_BYTES = b"\x00\xffOpaque synthetic file bytes; no claim of a compiled report.\n"
GOAL = "Show monthly synthetic completed work orders grouped by type."
CSV = (
    "month,work_order_type,completed\n"
    "2026-08,Electrical,4\n2026-08,Mechanical,7\n"
    "2026-09,Electrical,6\n2026-09,Mechanical,3\n"
    "2026-10,Electrical,5\n2026-10,Mechanical,8\n"
)
SOURCE_DIGEST = hashlib.sha256(CSV.encode()).hexdigest()


def profile():
    return ProviderProfile.model_validate(
        {
            "profile_id": "demo-profile",
            "configuration_id": "demo-configuration",
            "protocol": "FOUNDRY_AGENT_RESPONSES",
            "endpoint": f"{PROJECT}/agents/{AGENT}/endpoint/protocols/openai/responses",
            "api_version": "v1",
            "model_or_deployment": AGENT,
            "prompt_version": "test",
            "region": "australiaeast",
            "capabilities": {"structured_output": True, "vision": False},
            "max_calls_per_operation": 1,
            "retry_limit": 0,
            "max_input_characters": 200_000,
            "max_output_tokens": 8_000,
            "time_budget_seconds": 90,
            "request_timeout_seconds": 10,
        }
    )


class ReceiptIndex:
    def __init__(self):
        self.receipts = {}

    def commit(self, receipt):
        self.receipts[receipt.id] = receipt

    def load(self, scope, reference):
        receipt = self.receipts[reference]
        assert receipt.scope == scope
        return receipt


class Authority:
    """Stand in for the case-specific, durable admission owned by the signed-in host."""

    def __init__(self):
        self.active = True
        self.claimed = set()
        self.exclusive = True
        self.writer_checks = []

    def current(self, operation):
        return self.active

    def claim(self, operation):
        key = operation.scope.operation_id
        if not self.active or key in self.claimed:
            return False
        self.claimed.add(key)
        return True

    def exclusive_writer(self, operation, response_id, reference):
        self.writer_checks.append((operation, response_id, reference))
        return self.exclusive and self.current(operation)


def service_response(purpose):
    report = purpose == "FULL_REPORT_ARTIFACT"
    output = []
    annotations = []
    if report:
        output.append(
            {
                "type": "code_interpreter_call",
                "id": "call_package",
                "status": "completed",
                "container_id": FILE.container_id,
            }
        )
        annotations.append(
            {
                "type": "container_file_citation",
                "container_id": FILE.container_id,
                "file_id": FILE.file_id,
                "filename": FILE.filename,
                "start_index": 0,
                "end_index": 1,
            }
        )
    text = "An attached package." if report else '{"state":"NEEDS_CLARIFICATION"}'
    output.append(
        {
            "type": "message",
            "role": "assistant",
            "id": "msg_demo",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": annotations}],
        }
    )
    return {
        "object": "response",
        "id": "resp_demo",
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "agent_reference": AGENT_REF.copy(),
        "created_at": 101,
        "completed_at": 103,
        "output": output,
        "store": False,
    }


class Scenario:
    def __init__(self, tmp_path, purpose="FULL_REPORT_ARTIFACT"):
        self.profile = profile()
        self.scope = NativeResponseScope(uuid4(), uuid4(), 1, uuid4())
        self.index = ReceiptIndex()
        self.archive = NativeResponseArchive(
            self.scope, LocalEvidenceStore(tmp_path, "test"), self.index
        )
        self.authority = Authority()
        self.send_bearer = Mock(return_value=FoundryBearer("synthetic-send", time.time() + 600))
        self.read_bearer = Mock(return_value=FoundryBearer("synthetic-read", time.time() + 600))
        self.send_access = FoundryAccess(
            self.scope.company_id,
            self.profile.profile_id,
            self.profile.configuration_id,
            self.send_bearer,
            "synthetic-knowledge",
            "TENANT_PRIVATE",
            agent_version="10",
        )
        self.read_access = replace(self.send_access, credential=self.read_bearer)
        source_id, version = uuid4(), uuid4()
        source = {
            "id": str(source_id),
            "requestVersionId": str(version),
            "filename": "synthetic-maintenance.csv",
            "mediaType": "text/csv",
            "transport": "INLINE_UTF8_SOURCE",
            "byteCount": len(CSV.encode()),
            "sourceText": CSV,
            "contentDigest": SOURCE_DIGEST,
        }
        context = {
            "dataStructure": parse_evidence(CSV.encode(), source["filename"]).observed_schema,
            "caseFiles": [source],
            "fileDelivery": {
                "sampled": False,
                "serviceFileUploaded": False,
                "processingVerified": False,
            },
            "generationPolicy": {"supportedTrendGrains": ["MONTH"]},
        }
        if purpose == "FULL_REPORT_ARTIFACT":
            task = "REPORT_DESIGN"
            context.update(
                confirmedRequirements={"objective": GOAL, "dataLabel": "Synthetic"},
                referenceMaterial=[],
                rendererCapabilities={"supportedTrendGrains": []},
            )
        else:
            task = "REQUIREMENT_ANALYSIS"
            context["fileDelivery"]["transport"] = "INLINE_UTF8_SOURCE"
            context.update(
                materialContext={"originalRequest": GOAL},
                priorAgentAnswers=[],
                clarificationState={},
                clarificationPolicy={},
            )
        self.request = ProviderRequest(
            task=task, system_prompt="", output_schema={}, context=context
        )
        self.operation = V10Operation(
            scope=self.scope,
            purpose=purpose,
            project_url=PROJECT,
            agent_name=AGENT,
            profile_sha256=json_digest(self.profile.model_dump(mode="json")),
            context_sha256=json_digest(context),
            source_id=source_id,
            request_version_id=version,
            source_digest=SOURCE_DIGEST,
            knowledge_binding=self.send_access.knowledge_binding,
            knowledge_scope=self.send_access.knowledge_scope,
            goal=GOAL,
            output_filename=FILE.filename,
            trend_grains=("MONTH",),
        )
        self.receiver = V10ReportTransport(self.operation, self.authority)
        self.response = service_response(purpose)
        self.container = {"object": "container", "id": FILE.container_id, "created_at": 101}
        self.file = {
            "object": "container.file",
            "id": FILE.file_id,
            "container_id": FILE.container_id,
            "created_at": 103,
            "source": "assistant",
            "path": f"/mnt/data/{FILE.filename}",
            "bytes": len(REPORT_BYTES),
        }
        self.requests = []
        self.service = httpx.MockTransport(self.handle)
        self.raw_response = None
        self.status = 200

    def handle(self, request):
        self.requests.append(request)
        url = str(request.url)
        if request.method == "POST":
            assert url == f"{PROJECT}/openai/v1/responses"
            assert request.headers["Authorization"] == "Bearer synthetic-send"
            data = self.raw_response if self.raw_response is not None else self.original()
            return httpx.Response(self.status, stream=httpx.ByteStream(data))
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer synthetic-read"
        if url == CONTAINER_URL:
            body = json.dumps(self.container).encode()
        elif url == FILE_URL:
            body = json.dumps(self.file).encode()
        else:
            assert url == FILE_URL + "/content"
            body = REPORT_BYTES
        return httpx.Response(200, stream=httpx.ByteStream(body))

    def original(self):
        return json.dumps(self.response, indent=2).encode()

    def send(self, **options):
        arguments = {
            "company_id": self.scope.company_id,
            "case_id": self.scope.case_id,
            "context_version": self.scope.context_version,
            "archive": self.archive,
            "image_parts": (),
            "file_parts": (),
            "transport": self.service,
        }
        arguments.update(options)
        return self.receiver(self.profile, self.send_access, self.request, **arguments)

    def read(self, receipt_id, **options):
        arguments = {"receipt_id": receipt_id, "archive": self.archive, "transport": self.service}
        arguments.update(options)
        return self.receiver.read_report(self.profile, self.read_access, **arguments)

    def rebind(self):
        self.operation = replace(self.operation, context_sha256=json_digest(self.request.context))
        self.receiver = V10ReportTransport(self.operation, self.authority)


@pytest.mark.parametrize("purpose", ["REQUIREMENT_ANALYSIS", "FULL_REPORT_ARTIFACT"])
def test_exact_project_request_sends_complete_admitted_input_once(tmp_path, purpose):
    run = Scenario(tmp_path, purpose)
    result = run.send()
    assert result.status == "RECEIVED" and result.provider_status == "completed"
    assert run.archive.read(result.receipt.id) == run.original()
    assert result.receipt.digest == hashlib.sha256(run.original()).hexdigest()
    assert len(run.requests) == 1
    body = json.loads(run.requests[0].content)
    assert body["agent_reference"] == AGENT_REF
    assert body["store"] is False and body["stream"] is False
    assert body["max_output_tokens"] == 8_000
    assert not (
        {"tools", "instructions", "model", "previous_response_id", "conversation"} & body.keys()
    )
    assert len(body["input"]) == 1 and body["input"][0]["role"] == "user"
    message = json.loads(body["input"][0]["content"])
    assert message["context"]["caseFiles"] == run.request.context["caseFiles"]
    assert message["context"]["caseFiles"][0]["sourceText"].encode() == CSV.encode()
    assert GOAL in body["input"][0]["content"]
    assert str(run.scope.operation_id) not in body["input"][0]["content"]
    if purpose == "REQUIREMENT_ANALYSIS":
        assert body["tool_choice"] == "none"
        assert message["context"]["responseContract"] == requirement_analysis_schema(("MONTH",))
    else:
        assert body["tool_choice"] == {"type": "code_interpreter"}
        assert body["max_tool_calls"] == 2
        assert (
            message["context"]["confirmedRequirements"]
            == run.request.context["confirmedRequirements"]
        )
    with pytest.raises(ProviderCallError):
        run.send()
    assert len(run.requests) == 1
    run.send_bearer.assert_called_once_with()
    run.read_bearer.assert_not_called()


@pytest.mark.parametrize("carrier", ["message", "output_message"])
@pytest.mark.parametrize("root_attests", [True, False])
def test_unique_report_is_bound_to_actual_receipt_and_returned_bytes(
    tmp_path, carrier, root_attests
):
    run = Scenario(tmp_path)
    output = run.response["output"]
    output.insert(0, dict(output[0], id="call_prepare"))
    output[-1]["type"] = carrier
    annotations = output[-1]["content"][0]["annotations"]
    annotations.append(deepcopy(annotations[0]))
    if not root_attests:
        run.response["agent_reference"] = None
        for item in output:
            item.update(agent_reference=AGENT_REF.copy(), response_id=run.response["id"])
    result = run.send()
    artifact = run.read(result.receipt.id)
    assert artifact.content == REPORT_BYTES
    assert artifact.digest == hashlib.sha256(REPORT_BYTES).hexdigest()
    assert artifact.receipt_id == result.receipt.id and artifact.reference == FILE
    assert artifact.response_id == run.response["id"]
    assert run.archive.read(result.receipt.id) == run.original()
    assert [str(r.url) for r in run.requests[1:]] == [
        CONTAINER_URL,
        FILE_URL,
        FILE_URL + "/content",
    ]
    assert (run.operation, run.response["id"], FILE) in run.authority.writer_checks
    run.send_bearer.assert_called_once_with()
    assert run.read_bearer.called


@pytest.mark.parametrize(
    "defect",
    [
        "revoked",
        "wrong_case",
        "wrong_org",
        "stale_context",
        "wrong_version",
        "foreign_send_access",
        "foreign_knowledge",
        "image",
        "file",
        "foreign_project",
        "foreign_agent",
        "profile_change",
        "context_change",
        "changed_csv",
        "source_digest",
        "source_version",
        "source_id",
        "duplicate_source",
        "sampled",
        "unconfirmed",
        "wrong_stage",
    ],
)
def test_reject_before_claim_bearer_or_network(tmp_path, defect):
    run = Scenario(tmp_path)
    options = {}
    if defect == "revoked":
        run.authority.active = False
    elif defect in {"wrong_case", "wrong_org", "stale_context"}:
        options[
            {
                "wrong_case": "case_id",
                "wrong_org": "company_id",
                "stale_context": "context_version",
            }[defect]
        ] = 2 if defect == "stale_context" else uuid4()
    elif defect in {"wrong_version", "foreign_send_access"}:
        key = "agent_version" if defect == "wrong_version" else "company_id"
        run.send_access = replace(
            run.send_access, **{key: "7" if defect == "wrong_version" else uuid4()}
        )
    elif defect == "foreign_knowledge":
        run.send_access = replace(run.send_access, knowledge_binding="other-knowledge")
    elif defect in {"image", "file"}:
        options["image_parts" if defect == "image" else "file_parts"] = [{"type": "input_text"}]
    elif defect in {"foreign_project", "foreign_agent"}:
        changed = (
            {"project_url": PROJECT + "-other"}
            if defect == "foreign_project"
            else {"agent_name": AGENT + "-other"}
        )
        run.operation = replace(run.operation, **changed)
        run.receiver = V10ReportTransport(run.operation, run.authority)
    elif defect == "profile_change":
        run.profile = run.profile.model_copy(update={"prompt_version": "changed"})
    elif defect == "context_change":
        run.request.context["confirmedRequirements"]["objective"] = "Another business request"
    elif defect == "wrong_stage":
        run.request = replace(run.request, task="REQUIREMENT_ANALYSIS")
    else:
        context = run.request.context
        source = context["caseFiles"][0]
        if defect == "changed_csv":
            source["sourceText"] = CSV.replace("Mechanical,8", "Mechanical,9")
        elif defect == "source_digest":
            source["contentDigest"] = "0" * 64
        elif defect == "source_version":
            source["requestVersionId"] = str(uuid4())
        elif defect == "source_id":
            source["id"] = str(uuid4())
        elif defect == "duplicate_source":
            context["caseFiles"].append(deepcopy(source))
        elif defect == "sampled":
            context["fileDelivery"]["sampled"] = True
        elif defect == "unconfirmed":
            context["confirmedRequirements"] = {}
        # Even a current snapshot digest cannot authorise an out-of-scope data source.
        run.rebind()
    with pytest.raises(ProviderCallError):
        run.send(**options)
    assert not run.authority.claimed and not run.requests
    run.send_bearer.assert_not_called()


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_version",
        "missing_reference",
        "unattributed",
        "foreign_item",
        "foreign_response",
        "wrong_role",
        "tool_failed",
        "no_interpreter",
        "citation_before_producer",
        "other_tool",
        "duplicate_output_id",
        "wrong_container",
        "ambiguous_file",
        "competing_zip",
        "renamed_primary_id",
        "model_link",
        "multiple_containers",
        "reused_context",
        "too_many_tool_calls",
        "duplicate_json_keys",
    ],
)
def test_ambiguous_or_failed_provenance_retained_without_file_access(tmp_path, fault):
    run = Scenario(tmp_path)
    response = run.response
    output = response["output"]
    call, message = output
    part = message["content"][0]
    citation = part["annotations"][0]
    if fault == "wrong_version":
        response["agent_reference"]["version"] = "7"
    elif fault == "missing_reference":
        del response["agent_reference"]
        for item in output:
            item.update(agent_reference=AGENT_REF.copy(), response_id=response["id"])
    elif fault == "unattributed":
        response["agent_reference"] = None
    elif fault == "foreign_item":
        call["agent_reference"] = dict(AGENT_REF, name="foreign-agent")
    elif fault == "foreign_response":
        message["response_id"] = "resp_different"
    elif fault == "wrong_role":
        message["role"] = "user"
    elif fault == "tool_failed":
        call["status"] = "failed"
    elif fault == "no_interpreter":
        output.remove(call)
    elif fault == "citation_before_producer":
        response["output"] = [message, call]
    elif fault == "other_tool":
        output.insert(0, {"type": "file_search_call", "id": "search_other", "status": "completed"})
    elif fault == "duplicate_output_id":
        message["id"] = call["id"]
    elif fault == "wrong_container":
        citation["container_id"] = "cntr_other"
    elif fault == "ambiguous_file":
        part["annotations"].append(dict(citation, file_id="cfile_other"))
    elif fault == "competing_zip":
        part["annotations"].append(dict(citation, file_id="cfile_two", filename="two.pbip.zip"))
    elif fault == "renamed_primary_id":
        part["annotations"].append(dict(citation, filename="overview.png"))
    elif fault == "model_link":
        part.update(text=f"Report from {FILE_URL}/content", annotations=[])
    elif fault == "multiple_containers":
        output.insert(0, dict(call, id="call_other", container_id="cntr_other"))
    elif fault == "reused_context":
        response["previous_response_id"] = "resp_previous"
    elif fault == "too_many_tool_calls":
        output[0:0] = [dict(call, id="call_prepare"), dict(call, id="call_again")]
    elif fault == "duplicate_json_keys":
        run.raw_response = run.original().replace(
            b'"version": "10"', b'"version": "7", "version": "10"'
        )
    data = run.raw_response or run.original()
    result = run.send()
    assert result.status == "RECEIVED" and run.archive.read(result.receipt.id) == data
    with pytest.raises(ProviderCallError):
        run.read(result.receipt.id)
    assert len(run.requests) == 1
    run.read_bearer.assert_not_called()


@pytest.mark.parametrize(
    "defect",
    [
        "authority",
        "writer",
        "foreign_reader",
        "wrong_version",
        "other_receipt",
        "wrong_operation",
        "different_credential_scope",
    ],
)
def test_case_receipt_and_current_read_authority_precede_metadata(tmp_path, defect):
    run = Scenario(tmp_path)
    result = run.send()
    receipt_id, archive = result.receipt.id, run.archive
    if defect == "authority":
        run.authority.active = False
    elif defect == "writer":
        run.authority.exclusive = False
    elif defect == "foreign_reader":
        run.read_access = replace(run.read_access, company_id=uuid4())
    elif defect == "wrong_version":
        run.read_access = replace(run.read_access, agent_version="7")
    elif defect == "other_receipt":
        receipt_id = uuid4()
    elif defect == "wrong_operation":
        archive = NativeResponseArchive(
            replace(run.scope, operation_id=uuid4()),
            LocalEvidenceStore(tmp_path, "test"),
            run.index,
        )
    elif defect == "different_credential_scope":
        run.read_access = replace(run.read_access, configuration_id="other-config")
    with pytest.raises(ProviderCallError):
        run.read(receipt_id, archive=archive)
    assert len(run.requests) == 1
    run.read_bearer.assert_not_called()


@pytest.mark.parametrize(
    "record,key,value",
    [
        ("container", "created_at", 100),
        ("container", "id", "other"),
        ("file", "id", "other"),
        ("file", "container_id", "other"),
        ("file", "source", "user"),
        ("file", "object", "file"),
        ("file", "created_at", 104),
        ("file", "created_at", True),
        ("file", "path", "/mnt/data/other.pbip.zip"),
        ("file", "bytes", 0),
        ("file", "bytes", 25_000_001),
    ],
)
def test_metadata_mismatch_prevents_content_read(tmp_path, record, key, value):
    run = Scenario(tmp_path)
    result = run.send()
    getattr(run, record)[key] = value
    with pytest.raises(ProviderCallError):
        run.read(result.receipt.id)
    urls = [str(r.url) for r in run.requests[1:]]
    assert CONTAINER_URL in urls and FILE_URL + "/content" not in urls


def test_content_length_must_match_verified_file_metadata(tmp_path):
    run = Scenario(tmp_path)
    result = run.send()
    run.file["bytes"] += 1
    with pytest.raises(ProviderCallError):
        run.read(result.receipt.id)
    assert str(run.requests[-1].url) == FILE_URL + "/content"
    assert run.archive.read(result.receipt.id) == run.original()


@pytest.mark.parametrize("status", [302, 403, 429, 500])
def test_service_errors_retain_exact_receipt_and_never_redirect_or_resend(tmp_path, status):
    run = Scenario(tmp_path)
    run.raw_response = b' {"error":{"code":"Synthetic"}}\n'

    def error_response(request):
        run.requests.append(request)
        return httpx.Response(
            status,
            headers={"Location": "https://elsewhere.invalid/private"},
            stream=httpx.ByteStream(run.raw_response),
        )

    run.service = httpx.MockTransport(error_response)
    result = run.send()
    assert result.status == "HTTP_ERROR" and result.http_status == status
    assert run.archive.read(result.receipt.id) == run.raw_response
    with pytest.raises(ProviderCallError):
        run.send()
    assert len(run.requests) == 1


@pytest.mark.parametrize("reason", ["timeout", "credential", "oversized"])
def test_uncertain_or_failed_admission_is_spent(tmp_path, reason):
    run = Scenario(tmp_path)

    def send_once(request):
        run.requests.append(request)
        if reason == "timeout":
            raise httpx.ReadTimeout("synthetic read failure", request=request)
        return httpx.Response(200, stream=httpx.ByteStream(b"x" * 4_000_001))

    run.service = httpx.MockTransport(send_once)
    if reason == "credential":
        run.send_bearer.side_effect = RuntimeError("synthetic private diagnostic")
    with pytest.raises(ProviderCallError) as failure:
        run.send()
    assert "synthetic private diagnostic" not in str(failure.value)
    # Re-instantiating the transport cannot replenish a claimed durable opportunity.
    run.receiver = V10ReportTransport(run.operation, run.authority)
    with pytest.raises(ProviderCallError):
        run.send()
    assert len(run.requests) == (0 if reason == "credential" else 1)
    run.send_bearer.assert_called_once_with()


def test_authority_lost_after_metadata_stops_before_content(tmp_path):
    run = Scenario(tmp_path)
    result = run.send()

    def lose_access(request):
        response = run.handle(request)
        if str(request.url) == FILE_URL:
            run.authority.active = False
        return response

    with pytest.raises(ProviderCallError):
        run.read(result.receipt.id, transport=httpx.MockTransport(lose_access))
    assert [str(r.url) for r in run.requests[1:]] == [CONTAINER_URL, FILE_URL]


def test_expired_original_deadline_cannot_be_renewed_by_read_report(tmp_path, monkeypatch):
    run = Scenario(tmp_path)
    instant = [time.monotonic()]
    monkeypatch.setattr(time, "monotonic", lambda: instant[0])
    result = run.send()
    instant[0] += run.profile.time_budget_seconds + 1
    with pytest.raises(ProviderCallError):
        run.read(result.receipt.id)
    assert len(run.requests) == 1
    run.read_bearer.assert_not_called()


def test_tool_free_analysis_retains_unapproved_tool_attempt_without_qualifying(tmp_path):
    run = Scenario(tmp_path, "REQUIREMENT_ANALYSIS")
    run.response["output"].insert(0, service_response("FULL_REPORT_ARTIFACT")["output"][0])
    result = run.send()
    assert result.status == "RECEIVED" and result.provider_status != "completed"
    assert run.archive.read(result.receipt.id) == run.original()
    with pytest.raises(ProviderCallError):
        run.read(result.receipt.id)
    assert len(run.requests) == 1


def test_snapshot_digest_is_compatible_with_host_canonical_json():
    value = {"z": 1, "a": "café"}
    assert json_digest(value) == digest(value)


@pytest.mark.parametrize("approved,presented", [
    ("TENANT_PRIVATE", "SHARED_STANDARDS"), ("SHARED_STANDARDS", "TENANT_PRIVATE"),
])
def test_knowledge_scope_cannot_change_in_either_direction(tmp_path, approved, presented):
    run = Scenario(tmp_path)
    run.operation = replace(run.operation, knowledge_scope=approved)
    run.receiver = V10ReportTransport(run.operation, run.authority)
    run.send_access = replace(run.send_access, knowledge_scope=presented)
    with pytest.raises(ProviderCallError):
        run.send()
    assert not run.authority.claimed and not run.requests
    run.send_bearer.assert_not_called()


@pytest.mark.parametrize("field,cap", [
    ("max_tool_calls", 9), ("max_tool_calls", None), ("max_tool_calls", True),
    ("max_output_tokens", 16_000), ("max_output_tokens", None),
])
def test_contradictory_service_limits_withhold_file_authority(tmp_path, field, cap):
    run = Scenario(tmp_path)
    run.response[field] = cap
    result = run.send()
    assert result.provider_status == "UNKNOWN"
    assert run.archive.read(result.receipt.id) == run.original()
    with pytest.raises(ProviderCallError):
        run.read(result.receipt.id)
    assert len(run.requests) == 1


def test_configuration_changed_while_obtaining_read_credential(tmp_path):
    run = Scenario(tmp_path)
    result = run.send()

    def changed():
        run.profile.endpoint = run.profile.endpoint.replace("/demo/", "/other/")
        return FoundryBearer("synthetic-read", time.time() + 600)

    run.read_bearer.side_effect = changed
    with pytest.raises(ProviderCallError):
        run.read(result.receipt.id)
    assert len(run.requests) == 1


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Encoding": "gzip"},
        {"Content-Length": "999"},
        {"Content-Length": "invalid"},
    ],
)
def test_truncated_or_encoded_envelope_consumes_the_single_dispatch(tmp_path, headers):
    run = Scenario(tmp_path)

    def broken_response(request):
        run.requests.append(request)
        return httpx.Response(200, headers=headers, stream=httpx.ByteStream(b"{}"))

    with pytest.raises(ProviderCallError):
        run.send(transport=httpx.MockTransport(broken_response))
    with pytest.raises(ProviderCallError):
        run.send()
    assert len(run.requests) == 1 and not run.index.receipts


def test_failed_archive_retains_consumed_admission(tmp_path, monkeypatch):
    run = Scenario(tmp_path)
    failure = Mock(side_effect=RuntimeError("private storage internals"))
    monkeypatch.setattr(run.index, "commit", failure)
    with pytest.raises(ProviderCallError) as error:
        run.send()
    assert "private storage" not in str(error.value)
    with pytest.raises(ProviderCallError):
        run.send()
    assert len(run.requests) == 1 and not run.index.receipts


@pytest.mark.parametrize("phase", ["metadata", "content"])
def test_read_redirect_never_forwards_bearer(tmp_path, phase):
    run = Scenario(tmp_path)
    result = run.send()
    target = CONTAINER_URL if phase == "metadata" else FILE_URL + "/content"

    def redirect(request):
        if str(request.url) != target:
            return run.handle(request)
        run.requests.append(request)
        return httpx.Response(
            307,
            headers={"Location": "https://elsewhere.invalid/bytes"},
            stream=httpx.ByteStream(b"redirect"),
        )

    with pytest.raises(ProviderCallError):
        run.read(result.receipt.id, transport=httpx.MockTransport(redirect))
    assert str(run.requests[-1].url) == target
    assert all(str(r.url).startswith(PROJECT + "/") for r in run.requests)
    assert run.archive.read(result.receipt.id) == run.original()


@pytest.mark.parametrize("fault", ["expired", "wrong_audience", "send_credential"])
def test_file_read_must_use_its_own_current_authority(tmp_path, fault):
    run = Scenario(tmp_path)
    result = run.send()
    if fault == "expired":
        run.read_bearer.return_value = FoundryBearer("synthetic-read", time.time() - 1)
    elif fault == "wrong_audience":
        run.read_bearer.return_value = FoundryBearer(
            "synthetic-read", time.time() + 600, audience="https://unrelated.invalid"
        )
    else:
        run.read_access = run.send_access
    with pytest.raises(ProviderCallError):
        run.read(result.receipt.id)
    assert len(run.requests) == 1
    run.send_bearer.assert_called_once_with()


def test_file_read_rechecks_deadline_after_last_chunk(tmp_path, monkeypatch):
    run = Scenario(tmp_path)
    instant = [time.monotonic()]
    monkeypatch.setattr(time, "monotonic", lambda: instant[0])
    result = run.send()

    class ExpiresOnCompletion(httpx.SyncByteStream):
        def __iter__(self):
            yield REPORT_BYTES
            instant[0] += run.profile.time_budget_seconds + 1

    def service(request):
        if str(request.url) == FILE_URL + "/content":
            run.requests.append(request)
            return httpx.Response(200, stream=ExpiresOnCompletion())
        return run.handle(request)

    with pytest.raises(ProviderCallError):
        run.read(result.receipt.id, transport=httpx.MockTransport(service))
    assert str(run.requests[-1].url) == FILE_URL + "/content"
    assert run.archive.read(result.receipt.id) == run.original()


def test_supporting_image_citation_selects_only_the_intended_package(tmp_path):
    run = Scenario(tmp_path)
    annotations = run.response["output"][-1]["content"][0]["annotations"]
    annotations.insert(0, dict(annotations[0], file_id="cfile_preview", filename="preview.png"))
    result = run.send()
    artifact = run.read(result.receipt.id)
    assert artifact.reference == FILE and artifact.content == REPORT_BYTES
    assert [str(request.url) for request in run.requests[1:]] == [
        CONTAINER_URL,
        FILE_URL,
        FILE_URL + "/content",
    ]
