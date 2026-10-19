"""Synthetic generated-file transport. No live Azure, provider call or owner data."""

import json
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import httpx
import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_foundry_report_runtime import new_settings

from apbra_api.api import create_app
from apbra_api.foundry_artifacts import (
    ArtifactTransportUnavailable,
    GeneratedFile,
    generated_files,
    project_file_url,
    retrieve_file,
)
from apbra_api.foundry_report_runtime import ReservedCredentials
from apbra_api.model_provider import (
    FoundryAccess,
    FoundryBearer,
    ProviderConfigurationError,
    ProviderProfile,
)


@pytest.fixture
def profile():
    return ProviderProfile(
        profile_id="synthetic-files",
        protocol="FOUNDRY_AGENT_RESPONSES",
        endpoint="https://synthetic.services.ai.azure.com/api/projects/project-one/agents/agent-one/endpoint/protocols/openai/responses",
        model_or_deployment="synthetic",
        api_version="v1",
        region="synthetic",
        prompt_version="synthetic",
        configuration_id="synthetic-configuration",
        capabilities={"structured_output": True, "vision": False},
        max_calls_per_operation=1,
        max_input_characters=1000,
        max_output_tokens=128,
        time_budget_seconds=5,
        request_timeout_seconds=5,
        retry_limit=0,
    )


@pytest.fixture
def access(profile):
    return FoundryAccess(
        company_id=uuid4(),
        profile_id=profile.profile_id,
        configuration_id=profile.configuration_id,
        credential=lambda: FoundryBearer("synthetic-artifact-bearer", time.time() + 60),
        knowledge_binding="synthetic",
        knowledge_scope="TENANT_PRIVATE",
    )


REFERENCE = GeneratedFile("cntr_synthetic", "cfile_synthetic", "Generated.zip")


def envelope(annotations):
    return {
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Original model text with no application instructions.",
                        "annotations": annotations,
                    }
                ],
            }
        ]
    }


def annotation(**updates):
    return {
        "type": "container_file_citation",
        "container_id": REFERENCE.container_id,
        "file_id": REFERENCE.file_id,
        "filename": REFERENCE.filename,
        **updates,
    }


def test_documented_annotation_shape_only_and_no_arbitrary_url_or_source_citation():
    raw = json.dumps(
        envelope(
            [
                annotation(),
                annotation(),
                {"type": "file_citation", "file_id": "source-not-generated"},
                {"type": "output_file", "url": "https://arbitrary.invalid/private"},
                annotation(container_id="../escape"),
                annotation(file_id="https://other.invalid/file"),
            ]
        )
    ).encode()
    assert generated_files(raw) == (REFERENCE,)
    assert generated_files(b"not JSON") == ()
    assert generated_files(json.dumps({"output": None}).encode()) == ()
    assert (
        generated_files(
            json.dumps(
                {
                    "output": [
                        {
                            "role": "user",
                            "content": [{"type": "output_text", "annotations": [annotation()]}],
                        }
                    ]
                }
            ).encode()
        )
        == ()
    )


def test_exact_project_route_uses_no_agent_endpoint_or_model_url(profile):
    assert project_file_url(profile, REFERENCE) == (
        "https://synthetic.services.ai.azure.com/api/projects/project-one/openai/v1/"
        "containers/cntr_synthetic/files/cfile_synthetic/content"
    )
    with pytest.raises(ArtifactTransportUnavailable):
        project_file_url(profile, replace(REFERENCE, file_id="../escape"))


def test_original_8358512_synthetic_bytes_download_once_unchanged(profile, access):
    content = b"\x00\xff" * 4_179_256
    calls = []

    def get(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer synthetic-artifact-bearer"
        assert not request.url.query and not request.content
        return httpx.Response(200, stream=httpx.ByteStream(content))

    result = retrieve_file(
        profile, access, REFERENCE, lambda: True, transport=httpx.MockTransport(get)
    )
    assert result == content and len(calls) == 1
    assert str(calls[0].url) == project_file_url(profile, REFERENCE)


@pytest.mark.parametrize("status", [301, 302, 307, 401, 403, 404, 410, 429, 500, 503])
def test_error_redirect_never_retried_or_followed_and_private_details_not_exposed(
    profile,
    access,
    status,
):
    calls = []

    def get(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"Location": "https://private.invalid/token"},
            content=b"synthetic-provider-private-canary",
        )

    with pytest.raises(ArtifactTransportUnavailable) as caught:
        retrieve_file(profile, access, REFERENCE, lambda: True, transport=httpx.MockTransport(get))
    assert len(calls) == 1
    assert "canary" not in str(caught.value) and "private.invalid" not in str(caught.value)


@pytest.mark.parametrize("kind", ["empty", "too-large", "truncated", "expired", "revoked"])
def test_transport_bounds_and_lease_are_not_content_acceptance_checks(profile, access, kind):
    from apbra_api.artifacts import MAX_ARTIFACT_BYTES

    content = b"x"
    headers = {}

    def ready():
        return kind != "revoked"

    if kind == "empty":
        content = b""
    if kind == "too-large":
        content = b"x" * (MAX_ARTIFACT_BYTES + 1)
    if kind == "truncated":
        headers = {"Content-Length": "2"}
    if kind == "expired":
        access = replace(access, credential=lambda: FoundryBearer("synthetic", time.time() - 1))
    with pytest.raises(ArtifactTransportUnavailable):
        retrieve_file(
            profile,
            access,
            REFERENCE,
            ready,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, stream=httpx.ByteStream(content), headers=headers)
            ),
        )


def test_readonly_credential_preserves_lease_and_never_claims_or_refunds_paid_slot(profile, access):
    credentials = SimpleNamespace(ready=Mock(return_value=True), resolve=Mock(return_value=access))
    reservations = SimpleNamespace(
        connected=Mock(return_value=True),
        claim=Mock(side_effect=RuntimeError("paid slot boundary")),
        approval=SimpleNamespace(
            case_id=UUID(int=1),
            binding=SimpleNamespace(company_id=access.company_id, provider_profile=profile),
        ),
    )
    wrapped = ReservedCredentials(credentials, reservations)
    assert (
        wrapped.resolve_readonly(access.company_id, profile, case_id=UUID(int=1)).credential().token
    )
    reservations.claim.assert_not_called()
    with pytest.raises(RuntimeError, match="paid slot boundary"):
        wrapped.resolve(access.company_id, profile).credential()
    assert reservations.claim.call_count == 1
    reservations.connected.return_value = False
    with pytest.raises(ProviderConfigurationError):
        wrapped.resolve_readonly(access.company_id, profile, case_id=UUID(int=1))


@pytest.fixture
def artifact_case(client):
    session = sign_in(client)
    result = client.post(
        "/api/cases",
        headers={**csrf(session), "Idempotency-Key": str(uuid4())},
        json={"request_text": "Synthetic native file delivery"},
    )
    assert result.status_code == 201
    return result.json()["case"], session


@pytest.fixture
def integration(client, artifact_case, database, settings, profile, access, monkeypatch):
    from apbra_api import request_outputs
    from apbra_api.evidence import LocalEvidenceStore
    from apbra_api.native_response_archive import NativeResponseArchive, NativeResponseScope
    from apbra_api.native_response_index import DatabaseNativeResponseIndex

    case, session = artifact_case
    company = UUID(case["company_id"])
    access = replace(access, company_id=company)
    with database.session() as db:
        new_settings(db, company, {"provider_profile": profile})
    settings.qualified_provider_profiles_json = json.dumps([profile.model_dump()])
    from apbra_api.native_response_index import NativeReceiveCommandRow
    from apbra_api.tenant_settings import current_settings

    operation = uuid4()
    with database.session() as db:
        snapshot = current_settings(db, company)
        db.add(
            NativeReceiveCommandRow(
                id=operation,
                company_id=company,
                case_id=UUID(case["id"]),
                actor_membership_id=UUID(session["actor"]["membership_id"]),
                context_version=1,
                settings_id=snapshot.id,
                command_key=uuid4(),
                state="RECEIVED",
                http_status=200,
                provider_status="completed",
            )
        )
        db.commit()
    archive = NativeResponseArchive(
        NativeResponseScope(company, UUID(case["id"]), 1, operation),
        LocalEvidenceStore(settings.evidence_root, "test"),
        DatabaseNativeResponseIndex(database),
    )
    raw = json.dumps(
        envelope([annotation(), annotation(file_id="cfile_two", filename="Other.txt")]), indent=2
    ).encode()
    receipt = archive.preserve(raw)
    calls = []
    enabled = [True]
    credentials = SimpleNamespace(
        ready=lambda c, p: enabled[0] and c == company and p == profile, resolve=lambda c, p: access
    )
    app = create_app(settings=settings, database=database, foundry_credentials=credentials)
    target = TestClient(app)
    target.cookies.update(client.cookies)
    real = request_outputs.retrieve_file

    def retrieve(p, a, reference, ready):
        def get(request):
            calls.append(request)
            return httpx.Response(
                200, stream=httpx.ByteStream(b"\x00\xffUnverified original model ZIP bytes")
            )

        return real(p, a, reference, ready, transport=httpx.MockTransport(get))

    monkeypatch.setattr(request_outputs, "retrieve_file", retrieve)
    prefix = f"/api/cases/{case['id']}/native-response-receipts/{receipt.id}"
    return SimpleNamespace(
        client=target,
        case=case,
        session=session,
        receipt=receipt,
        archive=archive,
        raw=raw,
        calls=calls,
        enabled=enabled,
        prefix=prefix,
        profile=profile,
    )


def test_file_receipt_route_saves_real_opaque_bytes_replays_without_get_and_keeps_original(
    integration,
):
    s = integration
    listed = s.client.get(s.prefix + "/files")
    assert listed.status_code == 200 and listed.json()["items"][0] == {
        "index": 0,
        "filename": "Generated.zip",
        "savable": True,
    }
    assert not s.calls
    payload = {"expected_context_version": 1, "command_key": str(uuid4())}
    response = s.client.post(s.prefix + "/files/0/output", headers=csrf(s.session), json=payload)
    assert response.status_code == 200, response.text
    output = response.json()["output"]
    assert output["content_verification"] == "NOT_RUN" and output["filename"] == "Generated.zip"
    delivered = s.client.get(f"/api/cases/{s.case['id']}/outputs/{output['id']}/download")
    assert delivered.content == b"\x00\xffUnverified original model ZIP bytes"
    s.enabled[0] = False  # Replaying committed history does not reacquire expired provider bytes.
    replay = s.client.post(s.prefix + "/files/0/output", headers=csrf(s.session), json=payload)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert len(s.calls) == 1 and s.archive.read(s.receipt.id) == s.raw
    conflict = s.client.post(s.prefix + "/files/1/output", headers=csrf(s.session), json=payload)
    assert conflict.status_code == 409 and len(s.calls) == 1


def test_private_file_routes_reject_forged_ids_csrf_foreign_actor_and_unavailable_identity(
    integration,
    database,
):
    s = integration
    payload = {"expected_context_version": 1, "command_key": str(uuid4())}
    assert s.client.post(s.prefix + "/files/0/output", json=payload).status_code == 401
    assert (
        s.client.post(
            s.prefix + "/files/0/output",
            headers=csrf(s.session),
            json={**payload, "file_id": "forged"},
        ).status_code
        == 422
    )
    assert (
        s.client.post(
            s.prefix + "/files/-1/output", headers=csrf(s.session), json=payload
        ).status_code
        == 422
    )
    s.enabled[0] = False
    assert (
        s.client.post(
            s.prefix + "/files/0/output", headers=csrf(s.session), json=payload
        ).status_code
        == 503
    )
    s.client.cookies.clear()
    other = sign_in(s.client, "foreign")
    assert s.client.get(s.prefix + "/files").status_code == 404
    assert (
        s.client.post(s.prefix + "/files/0/output", headers=csrf(other), json=payload).status_code
        == 404
    )
    assert not s.calls
    with database.session() as db:
        assert db.scalar(text("SELECT count(*) FROM request_outputs")) == 0


def test_reserved_readonly_rejects_different_case_without_token(profile, access):
    credentials = SimpleNamespace(ready=Mock(return_value=True), resolve=Mock(return_value=access))
    reservations = SimpleNamespace(
        connected=Mock(return_value=True),
        claim=Mock(),
        approval=SimpleNamespace(
            case_id=uuid4(),
            binding=SimpleNamespace(company_id=access.company_id, provider_profile=profile),
        ),
    )
    with pytest.raises(ProviderConfigurationError):
        ReservedCredentials(credentials, reservations).resolve_readonly(
            access.company_id, profile, case_id=uuid4()
        )
    credentials.resolve.assert_not_called()
    reservations.claim.assert_not_called()


def test_encoded_content_rejected_before_reading_or_decompression(profile, access):
    reads = []

    class NeverRead(httpx.SyncByteStream):
        def __iter__(self):
            reads.append(True)
            raise AssertionError("Encoded stream must not be read or decompressed")
            yield b""

    def get(request):
        assert request.headers["Accept-Encoding"] == "identity"
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=NeverRead())

    with pytest.raises(ArtifactTransportUnavailable):
        retrieve_file(profile, access, REFERENCE, lambda: True, transport=httpx.MockTransport(get))

    assert not reads


def test_unencodable_filename_is_not_promoted_to_api_descriptor():
    from apbra_api.request_outputs import OutputInputError, safe_filename

    assert generated_files(json.dumps(envelope([annotation(filename="\ud800")])).encode()) == ()
    with pytest.raises(OutputInputError):
        safe_filename("\ud800")


@pytest.mark.parametrize(
    ("change", "status"),
    [("context", 409), ("access", 404), ("role", 403), ("profile", 409), ("lease", 502)],
)
def test_file_fetch_rechecks_authority_settings_and_lease_before_saving(
    integration,
    database,
    monkeypatch,
    change,
    status,
):
    from sqlalchemy import select

    from apbra_api import request_outputs
    from apbra_api.persistence import CaseAccessRow, CaseRow, MembershipRow

    s = integration
    original = request_outputs.retrieve_file

    def interleaved(p, a, file, ready):
        content = original(p, a, file, ready)
        if change == "lease":
            s.enabled[0] = False
        else:
            with database.session() as db:
                if change == "context":
                    db.get(CaseRow, UUID(s.case["id"])).semantic_context_version = 2
                elif change == "access":
                    row = db.scalar(
                        select(CaseAccessRow).where(
                            CaseAccessRow.case_id == UUID(s.case["id"]),
                            CaseAccessRow.membership_id
                            == UUID(s.session["actor"]["membership_id"]),
                        )
                    )
                    row.access_level = "VIEWER"
                elif change == "role":
                    db.get(MembershipRow, UUID(s.session["actor"]["membership_id"])).role = "MEMBER"
                else:
                    new_settings(
                        db,
                        UUID(s.case["company_id"]),
                        {
                            "provider_profile": s.profile.model_copy(
                                update={"configuration_id": "changed-configuration"}
                            )
                        },
                    )
                db.commit()
        return content

    monkeypatch.setattr(request_outputs, "retrieve_file", interleaved)
    response = s.client.post(
        s.prefix + "/files/0/output",
        headers=csrf(s.session),
        json={"expected_context_version": 1, "command_key": str(uuid4())},
    )
    assert response.status_code == status, response.text
    assert len(s.calls) == 1
    with database.session() as db:
        assert db.scalar(text("SELECT count(*) FROM request_outputs")) == 0
