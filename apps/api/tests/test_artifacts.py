from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

import apbra_api.artifacts as artifacts_module
from apbra_api.artifacts import ArtifactError, LocalArtifactStore


def test_artifact_store_atomically_verifies_private_bytes(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts", "test")
    assert store.root.stat().st_mode & 0o077 == 0
    company_id, case_id, attempt_id = uuid4(), uuid4(), uuid4()
    content = b"PK\x03\x04synthetic candidate"
    key, digest, size = store.write(company_id, case_id, attempt_id, content)
    assert store.read(key, digest, size) == content
    path = store.root.joinpath(*key.split("/"))
    assert path.stat().st_mode & 0o077 == 0
    path.write_bytes(b"changed")
    with pytest.raises(ArtifactError, match="size verification|integrity verification"):
        store.read(key, digest, size)


def test_artifact_store_rejects_traversal_symlinks_and_oversized_reads(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts", "test")
    with pytest.raises(ArtifactError, match="unsafe"):
        store.read("../case/attempt/report.zip", "0" * 64, 1)
    company_id, case_id, attempt_id = uuid4(), uuid4(), uuid4()
    company = store.root / str(company_id)
    company.mkdir()
    os.symlink(tmp_path, company / str(case_id))
    with pytest.raises(ArtifactError, match="unsafe"):
        store.write(company_id, case_id, attempt_id, b"candidate")


def test_artifact_store_is_local_only(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="local/CI-only"):
        LocalArtifactStore(tmp_path / "artifacts", "hosted")
    with pytest.raises(ValueError, match="outside the application tree"):
        LocalArtifactStore(Path.cwd() / "artifacts", "test")


def test_artifact_store_rejects_repository_and_application_roots_from_other_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = Path(__file__).resolve().parents[3]
    monkeypatch.chdir(tmp_path)
    for protected in (repository, repository / "apps" / "api", repository / "apps" / "web"):
        with pytest.raises(ValueError, match="outside the application tree"):
            LocalArtifactStore(protected, "test")
        with pytest.raises(ValueError, match="outside the application tree"):
            LocalArtifactStore(protected / "synthetic-artifacts", "test")
    linked_parent = tmp_path / "linked-repository"
    linked_parent.symlink_to(repository, target_is_directory=True)
    with pytest.raises(ValueError, match="outside the application tree"):
        LocalArtifactStore(linked_parent / "apps" / "web" / "synthetic-artifacts", "test")


def test_artifact_store_rejects_flat_container_application_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application_root = tmp_path / "container" / "app"
    module_directory = application_root / "src" / "apbra_api"
    module_directory.mkdir(parents=True)
    monkeypatch.setattr(artifacts_module, "__file__", str(module_directory / "artifacts.py"))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="outside the application tree"):
        LocalArtifactStore(application_root / "runtime" / "generated", "test")


def test_artifact_store_removes_final_object_when_directory_sync_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts", "test")
    original = os.fsync
    calls = 0

    def fail_directory_sync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic directory sync failure")
        original(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_sync)
    with pytest.raises(OSError, match="synthetic directory sync failure"):
        store.write(uuid4(), uuid4(), uuid4(), b"candidate")
    assert not list(store.root.rglob("*.zip"))
    assert not list(store.root.rglob("*.writing"))


def test_artifact_key_collision_never_replaces_committed_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts", "test")
    company_id, case_id, attempt_id = uuid4(), uuid4(), uuid4()
    fixed = uuid4()
    monkeypatch.setattr(artifacts_module, "uuid4", lambda: fixed)
    key, digest, size = store.write(company_id, case_id, attempt_id, b"first candidate")
    with pytest.raises(FileExistsError):
        store.write(company_id, case_id, attempt_id, b"different candidate")
    assert store.read(key, digest, size) == b"first candidate"
    assert not list(store.root.rglob("*.writing"))
