from __future__ import annotations

import hashlib
import hmac
import os
import stat
from pathlib import Path
from uuid import UUID, uuid4

MAX_ARTIFACT_BYTES = 25_000_000


class ArtifactError(ValueError):
    pass


class LocalArtifactStore:
    """Private, immutable local object storage for validated generated candidates."""

    def __init__(self, root: Path, profile: str) -> None:
        if profile not in {"development", "test"}:
            raise ValueError("The private local artifact adapter is local/CI-only.")
        if root.is_symlink():
            raise ValueError("Artifact root must be a private real directory.")
        self.root = root.resolve()
        working_root = Path.cwd().resolve()
        if self.root == working_root or working_root in self.root.parents:
            raise ValueError("Artifact root must be outside the application tree.")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError("Artifact root must be a private real directory.")
        os.chmod(self.root, 0o700, follow_symlinks=False)

    @staticmethod
    def _parts(storage_key: str) -> tuple[str, str, str, str]:
        parts = tuple(storage_key.split("/"))
        if (
            len(parts) != 4
            or any(not part or part in {".", ".."} for part in parts)
            or not parts[-1].endswith(".zip")
        ):
            raise ArtifactError("Artifact object path is unsafe.")
        return parts[0], parts[1], parts[2], parts[3]

    def _open_directory(self, parts: tuple[str, ...], *, create: bool) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            descriptor = os.open(self.root, flags)
        except OSError as exc:
            raise ArtifactError("Artifact object path is unsafe.") from exc
        try:
            for part in parts:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except OSError as exc:
            os.close(descriptor)
            raise ArtifactError("Artifact object path is unsafe.") from exc

    def write(
        self, company_id: UUID, case_id: UUID, attempt_id: UUID, content: bytes
    ) -> tuple[str, str, int]:
        if not content or len(content) > MAX_ARTIFACT_BYTES:
            raise ArtifactError("Artifact exceeds the supported size limit.")
        digest = hashlib.sha256(content).hexdigest()
        directories = (str(company_id), str(case_id), str(attempt_id))
        directory_descriptor = self._open_directory(directories, create=True)
        key = f"{uuid4().hex}.zip"
        temporary_key = f".{uuid4().hex}.writing"
        try:
            descriptor = os.open(
                temporary_key,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=directory_descriptor,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(
                temporary_key,
                key,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
            os.fsync(directory_descriptor)
        except Exception:
            try:
                os.unlink(temporary_key, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass
            raise
        finally:
            os.close(directory_descriptor)
        return "/".join((*directories, key)), digest, len(content)

    def read(self, storage_key: str, expected_digest: str, expected_size: int) -> bytes:
        company, case, attempt, key = self._parts(storage_key)
        directory_descriptor = self._open_directory((company, case, attempt), create=False)
        try:
            descriptor = os.open(
                key, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory_descriptor
            )
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                raise ArtifactError("Artifact object is unavailable.")
            with os.fdopen(descriptor, "rb") as stream:
                content = stream.read(MAX_ARTIFACT_BYTES + 1)
        except OSError as exc:
            raise ArtifactError("Artifact object is unavailable.") from exc
        finally:
            os.close(directory_descriptor)
        if len(content) > MAX_ARTIFACT_BYTES or len(content) != expected_size:
            raise ArtifactError("Artifact size verification failed.")
        if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), expected_digest):
            raise ArtifactError("Artifact integrity verification failed.")
        return content

    def delete_uncommitted(self, storage_key: str) -> None:
        company, case, attempt, key = self._parts(storage_key)
        directory_descriptor = self._open_directory((company, case, attempt), create=False)
        try:
            object_stat = os.stat(key, dir_fd=directory_descriptor, follow_symlinks=False)
            if not stat.S_ISREG(object_stat.st_mode):
                raise ArtifactError("Artifact object path is unsafe.")
            os.unlink(key, dir_fd=directory_descriptor)
        except FileNotFoundError:
            return
        finally:
            os.close(directory_descriptor)
