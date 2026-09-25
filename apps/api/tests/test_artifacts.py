from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

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
