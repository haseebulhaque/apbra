"""Portable content contract and protected application injection regressions."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import text

from apbra_api.api import create_app
from apbra_api.artifacts import ArtifactError, LocalArtifactStore, read_verified_artifact
from apbra_api.config import Settings
from apbra_api.content_storage import (
    ArtifactObjectStore,
    EvidenceObjectStore,
    cleanup_uncommitted_artifact,
    cleanup_uncommitted_evidence,
)
from apbra_api.evidence import EvidenceError, LocalEvidenceStore, read_verified_evidence
from apbra_api.persistence import ApplicationSession, Database


@pytest.mark.parametrize("object_class", ["evidence", "reference"])
@pytest.mark.parametrize("adapter", ["local", "alternate"])
@pytest.mark.parametrize("failure", ["precommit", "committed_without_ack"])
def test_upload_commit_outcome_preserves_only_potentially_committed_bytes(
    settings: Settings,
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    object_class: str,
    adapter: str,
    failure: str,
) -> None:
    backing: dict[str, bytes] = {}
    objects: EvidenceObjectStore = (
        LocalEvidenceStore(tmp_path / object_class, "test")
        if adapter == "local"
        else MemoryEvidenceStore(backing)
    )
    injected = (
        {"evidence_objects": objects}
        if object_class == "evidence"
        else {"reference_objects": objects}
    )
    content = (
        b"kind,value\nA,1\n"
        if object_class == "evidence"
        else b"\x89PNG\r\n\x1a\nsynthetic-reference"
    )
    endpoint = "evidence" if object_class == "evidence" else "reference-material"
    filename = "synthetic.csv" if object_class == "evidence" else "synthetic.png"
    add_name = "add_evidence" if object_class == "evidence" else "add_reference_material"

    with TestClient(create_app(settings=settings, database=database, **injected)) as client:
        session = sign_in(client, "owner")
        created = client.post(
            "/api/cases",
            json={"request_text": "Inspect synthetic activity."},
            headers={**csrf(session), "Idempotency-Key": str(uuid4())},
        )
        assert created.status_code == 201
        case_id = created.json()["case"]["id"]
        original_add = getattr(ApplicationSession, add_name)
        original_commit = ApplicationSession.commit

        def add_with_failure(self: ApplicationSession, *args: object, **kwargs: object) -> object:
            if failure == "precommit":
                raise RuntimeError("synthetic metadata failure")
            result = original_add(self, *args, **kwargs)
            self.info["synthetic_upload_commit"] = True
            return result

        def commit_with_lost_ack(self: ApplicationSession) -> None:
            original_commit(self)
            if self.info.pop("synthetic_upload_commit", False):
                raise RuntimeError("synthetic lost commit acknowledgment")

        with monkeypatch.context() as scoped:
            scoped.setattr(ApplicationSession, add_name, add_with_failure)
            if failure == "committed_without_ack":
                scoped.setattr(ApplicationSession, "commit", commit_with_lost_ack)
            with pytest.raises(RuntimeError, match="synthetic"):
                client.post(
                    f"/api/cases/{case_id}/{endpoint}",
                    params={"filename": filename, "expected_context_version": 1},
                    content=content,
                    headers={**csrf(session), "Content-Type": "application/octet-stream"},
                )

        with database.session() as db:
            query = (
                text(
                    "SELECT storage_key, content_digest FROM case_evidence_versions "
                    "WHERE case_id=:id"
                )
                if object_class == "evidence"
                else text(
                    "SELECT storage_key, content_digest FROM case_reference_materials "
                    "WHERE case_id=:id"
                )
            )
            rows = db.execute(query, {"id": case_id}).all()
        if failure == "precommit":
            assert rows == []
            if adapter == "alternate":
                assert not backing
            else:
                assert isinstance(objects, LocalEvidenceStore)
                assert not list(objects.root.rglob("*.bin"))
        else:
            assert len(rows) == 1
            key, digest = rows[0]
            assert read_verified_evidence(objects, key, digest) == content
            listed = client.get(f"/api/cases/{case_id}/{endpoint}")
            assert listed.status_code == 200 and len(listed.json()["items"]) == 1


class MemoryEvidenceStore:
    """Test adapter whose backing survives new adapter and application instances."""

    def __init__(self, backing: dict[str, bytes]) -> None:
        self.backing = backing

    def write(self, company_id: UUID, case_id: UUID, content: bytes) -> tuple[str, str]:
        key = f"{company_id}/{case_id}/{uuid4().hex}.bin"
        assert key not in self.backing
        self.backing[key] = content
        return key, hashlib.sha256(content).hexdigest()

    def read(self, storage_key: str, expected_digest: str) -> bytes:
        content = self.backing.get(storage_key)
        if content is None:
            raise EvidenceError("Evidence object is unavailable.")
        if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), expected_digest):
            raise EvidenceError("Evidence integrity verification failed.")
        return content

    def restore(
        self,
        company_id: UUID,
        case_id: UUID,
        storage_key: str,
        content: bytes,
        expected_digest: str,
    ) -> None:
        if not storage_key.startswith(f"{company_id}/{case_id}/"):
            raise EvidenceError("Evidence recovery target does not match the case.")
        if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), expected_digest):
            raise EvidenceError("Evidence recovery identity mismatch.")
        self.backing[storage_key] = content

    def delete(self, storage_key: str) -> None:
        self.backing.pop(storage_key, None)


class MemoryArtifactStore:
    def __init__(self, backing: dict[str, bytes]) -> None:
        self.backing = backing

    def write(
        self, company_id: UUID, case_id: UUID, attempt_id: UUID, content: bytes
    ) -> tuple[str, str, int]:
        key = f"{company_id}/{case_id}/{attempt_id}/{uuid4().hex}.zip"
        assert key not in self.backing
        self.backing[key] = content
        return key, hashlib.sha256(content).hexdigest(), len(content)

    def read(self, storage_key: str, expected_digest: str, expected_size: int) -> bytes:
        content = self.backing.get(storage_key)
        if content is None or len(content) != expected_size:
            raise ArtifactError("Artifact object is unavailable.")
        if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), expected_digest):
            raise ArtifactError("Artifact integrity verification failed.")
        return content

    def delete_uncommitted(self, storage_key: str) -> None:
        self.backing.pop(storage_key, None)


def test_portable_contract_restarts_integrity_cleanup_and_restore() -> None:
    company_id, case_id, attempt_id = uuid4(), uuid4(), uuid4()
    evidence_backing: dict[str, bytes] = {}
    artifact_backing: dict[str, bytes] = {}
    evidence: EvidenceObjectStore = MemoryEvidenceStore(evidence_backing)
    artifacts: ArtifactObjectStore = MemoryArtifactStore(artifact_backing)
    evidence_key, evidence_digest = evidence.write(company_id, case_id, b"a,b\n1,2\n")
    artifact_key, artifact_digest, artifact_size = artifacts.write(
        company_id, case_id, attempt_id, b"PK\x03\x04synthetic"
    )
    # A separate process may construct new adapters over the same durable backing.
    restarted_evidence: EvidenceObjectStore = MemoryEvidenceStore(evidence_backing)
    restarted_artifacts: ArtifactObjectStore = MemoryArtifactStore(artifact_backing)
    assert (
        read_verified_evidence(restarted_evidence, evidence_key, evidence_digest)
        == b"a,b\n1,2\n"
    )
    assert read_verified_artifact(
        restarted_artifacts, artifact_key, artifact_digest, artifact_size
    ) == b"PK\x03\x04synthetic"
    with pytest.raises(EvidenceError):
        restarted_evidence.restore(company_id, case_id, evidence_key, b"wrong", evidence_digest)
    evidence_backing[evidence_key] = b"tampered"
    with pytest.raises(EvidenceError):
        read_verified_evidence(evidence, evidence_key, evidence_digest)
    restarted_evidence.restore(
        company_id, case_id, evidence_key, b"a,b\n1,2\n", evidence_digest
    )
    assert read_verified_evidence(evidence, evidence_key, evidence_digest) == b"a,b\n1,2\n"
    artifact_backing[artifact_key] = b"tampered"
    with pytest.raises(ArtifactError):
        read_verified_artifact(artifacts, artifact_key, artifact_digest, artifact_size)
    artifacts.delete_uncommitted(artifact_key)
    artifacts.delete_uncommitted(artifact_key)
    evidence.delete(evidence_key)
    evidence.delete(evidence_key)
    assert not evidence_backing and not artifact_backing


def test_secure_local_adapters_satisfy_portable_contract(tmp_path: Path) -> None:
    company_id, case_id, attempt_id = uuid4(), uuid4(), uuid4()
    evidence: EvidenceObjectStore = LocalEvidenceStore(tmp_path / "evidence", "test")
    artifacts: ArtifactObjectStore = LocalArtifactStore(tmp_path / "artifacts", "test")
    key, digest = evidence.write(company_id, case_id, b"a,b\n1,2\n")
    artifact_key, artifact_digest, size = artifacts.write(
        company_id, case_id, attempt_id, b"PK\x03\x04synthetic"
    )
    assert read_verified_evidence(LocalEvidenceStore(tmp_path / "evidence", "test"), key, digest)
    assert read_verified_artifact(
        LocalArtifactStore(tmp_path / "artifacts", "test"), artifact_key, artifact_digest, size
    )
    path = (tmp_path / "evidence").joinpath(*key.split("/"))
    path.write_bytes(b"damaged")
    with pytest.raises(EvidenceError):
        read_verified_evidence(evidence, key, digest)
    with pytest.raises(EvidenceError, match="recovery bytes"):
        evidence.restore(company_id, case_id, key, b"different", digest)
    with pytest.raises(EvidenceError, match="does not match the case"):
        evidence.restore(uuid4(), case_id, key, b"a,b\n1,2\n", digest)
    with pytest.raises(EvidenceError, match="does not match the case"):
        evidence.restore(company_id, uuid4(), key, b"a,b\n1,2\n", digest)
    evidence.restore(company_id, case_id, key, b"a,b\n1,2\n", digest)
    assert read_verified_evidence(evidence, key, digest) == b"a,b\n1,2\n"


def test_application_boundary_rejects_an_adapter_that_returns_wrong_bytes() -> None:
    company_id, case_id, attempt_id = uuid4(), uuid4(), uuid4()

    class LyingEvidence(MemoryEvidenceStore):
        def read(self, storage_key: str, expected_digest: str) -> bytes:
            return b"wrong bytes"

    class LyingArtifact(MemoryArtifactStore):
        def read(self, storage_key: str, expected_digest: str, expected_size: int) -> bytes:
            return b"changed bytes"

    evidence = LyingEvidence({})
    artifact = LyingArtifact({})
    evidence_key, evidence_digest = evidence.write(company_id, case_id, b"original")
    artifact_key, artifact_digest, artifact_size = artifact.write(
        company_id, case_id, attempt_id, b"PK\x03\x04original"
    )
    with pytest.raises(EvidenceError, match="integrity"):
        read_verified_evidence(evidence, evidence_key, evidence_digest)
    with pytest.raises(ArtifactError, match="integrity"):
        read_verified_artifact(artifact, artifact_key, artifact_digest, artifact_size)


def test_local_keys_fail_closed_for_backslash_and_ambiguous_segments(tmp_path: Path) -> None:
    evidence = LocalEvidenceStore(tmp_path / "evidence", "test")
    artifacts = LocalArtifactStore(tmp_path / "artifacts", "test")
    company, case, attempt = uuid4(), uuid4(), uuid4()
    for key in (
        f"{company}/{case}/..\\foreign.bin",
        f"{company}/{case}/../foreign.bin",
        f"{company}/{case}//foreign.bin",
        f"/{company}/{case}/foreign.bin",
    ):
        with pytest.raises(EvidenceError, match="unsafe"):
            evidence.read(key, "0" * 64)
    for key in (
        f"{company}/{case}/{attempt}/..\\foreign.zip",
        f"{company}/{case}/{attempt}/../foreign.zip",
        f"{company}/{case}/{attempt}//foreign.zip",
        f"/{company}/{case}/{attempt}/foreign.zip",
    ):
        with pytest.raises(ArtifactError, match="unsafe"):
            artifacts.read(key, "0" * 64, 1)


def test_uncommitted_cleanup_is_idempotent_and_failure_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_backing: dict[str, bytes] = {}
    artifact_backing: dict[str, bytes] = {}
    evidence = MemoryEvidenceStore(evidence_backing)
    artifacts = MemoryArtifactStore(artifact_backing)
    company_id, case_id, attempt_id = uuid4(), uuid4(), uuid4()
    evidence_key, _ = evidence.write(company_id, case_id, b"synthetic")
    artifact_key, _, _ = artifacts.write(company_id, case_id, attempt_id, b"synthetic")
    cleanup_uncommitted_evidence(evidence, evidence_key)
    cleanup_uncommitted_evidence(evidence, evidence_key)
    cleanup_uncommitted_artifact(artifacts, artifact_key)
    cleanup_uncommitted_artifact(artifacts, artifact_key)
    assert not evidence_backing and not artifact_backing

    class FailingEvidence(MemoryEvidenceStore):
        def delete(self, storage_key: str) -> None:
            raise RuntimeError("synthetic storage internals")

    warnings: list[tuple[str, str]] = []

    def record_warning(message: str, failure_type: str) -> None:
        warnings.append((message, failure_type))

    monkeypatch.setattr("apbra_api.content_storage.logger.warning", record_warning)
    cleanup_uncommitted_evidence(FailingEvidence({}), "opaque")
    assert warnings == [("Uncommitted evidence cleanup failed: type=%s", "RuntimeError")]


def test_injected_adapter_preserves_database_authority_and_restart(
    settings: Settings, database: Database
) -> None:
    evidence_backing: dict[str, bytes] = {}
    reference_backing: dict[str, bytes] = {}
    artifact_backing: dict[str, bytes] = {}

    def app_client() -> TestClient:
        return TestClient(
            create_app(
                settings=settings,
                database=database,
                evidence_objects=MemoryEvidenceStore(evidence_backing),
                reference_objects=MemoryEvidenceStore(reference_backing),
                artifact_objects=MemoryArtifactStore(artifact_backing),
            )
        )

    with app_client() as client:
        owner = sign_in(client, "owner")
        created = client.post(
            "/api/cases",
            json={"request_text": "Compare synthetic activity by period."},
            headers={**csrf(owner), "Idempotency-Key": str(uuid4())},
        )
        assert created.status_code == 201, created.text
        case_id = created.json()["case"]["id"]
        upload = client.post(
            f"/api/cases/{case_id}/evidence",
            params={"filename": "synthetic.csv", "expected_context_version": 1},
            content=b"period,count\n2026-01,2\n",
            headers={**csrf(owner), "Content-Type": "application/octet-stream"},
        )
        assert upload.status_code == 200, upload.text
        reference = client.post(
            f"/api/cases/{case_id}/reference-material",
            params={"filename": "synthetic.png", "expected_context_version": 2},
            content=b"\x89PNG\r\n\x1a\nsynthetic-reference",
            headers={**csrf(owner), "Content-Type": "application/octet-stream"},
        )
        assert reference.status_code == 200, reference.text
    assert len(evidence_backing) == len(reference_backing) == 1

    with app_client() as restarted:
        sign_in(restarted, "owner")
        evidence = restarted.get(f"/api/cases/{case_id}/evidence")
        references = restarted.get(f"/api/cases/{case_id}/reference-material")
        assert evidence.status_code == 200 and len(evidence.json()["items"]) == 1
        assert references.status_code == 200 and len(references.json()["items"]) == 1
        with TestClient(restarted.app) as foreign:
            sign_in(foreign, "foreign")
            assert foreign.get(f"/api/cases/{case_id}/evidence").status_code == 404
            assert foreign.get(f"/api/cases/{case_id}/reference-material").status_code == 404

    evidence_key = next(iter(evidence_backing))
    evidence_backing[evidence_key] = b"tampered"
    with app_client() as compromised:
        sign_in(compromised, "owner")
        assert compromised.get(f"/api/cases/{case_id}/evidence").json()["items"] == []


def test_untrusted_storage_ack_and_failed_metadata_commit_leave_no_eligible_object(
    settings: Settings, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    backing: dict[str, bytes] = {}

    class WrongDigest(MemoryEvidenceStore):
        def write(self, company_id: UUID, case_id: UUID, content: bytes) -> tuple[str, str]:
            key, _ = super().write(company_id, case_id, content)
            return key, "0" * 64

    def start_case(client: TestClient, session: dict[str, object]) -> str:
        created = client.post(
            "/api/cases",
            json={"request_text": "Inspect synthetic activity."},
            headers={**csrf(session), "Idempotency-Key": str(uuid4())},
        )
        assert created.status_code == 201
        return str(created.json()["case"]["id"])

    def upload(client: TestClient, session: dict[str, object], case_id: str) -> object:
        return client.post(
            f"/api/cases/{case_id}/evidence",
            params={"filename": "synthetic.csv", "expected_context_version": 1},
            content=b"kind,value\nA,1\n",
            headers={**csrf(session), "Content-Type": "application/octet-stream"},
        )

    with TestClient(
        create_app(settings=settings, database=database, evidence_objects=WrongDigest(backing))
    ) as client:
        session = sign_in(client, "owner")
        case_id = start_case(client, session)
        response = upload(client, session, case_id)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "CONFIGURATION_UNAVAILABLE"
        assert not backing
        assert client.get(f"/api/cases/{case_id}/evidence").json()["items"] == []

    def fail_record(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("synthetic database failure")

    with TestClient(
        create_app(
            settings=settings, database=database,
            evidence_objects=MemoryEvidenceStore(backing),
        )
    ) as client:
        session = sign_in(client, "owner")
        case_id = start_case(client, session)
        monkeypatch.setattr(ApplicationSession, "add_evidence", fail_record)
        with pytest.raises(RuntimeError, match="synthetic database failure"):
            upload(client, session, case_id)
        assert not backing
