"""Opaque request outputs: preserve bytes, enforce access, never judge report content."""

import base64
import binascii
import hashlib
import io
import json
import zipfile
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Annotated, Any, cast
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import Cookie, Depends, FastAPI, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import literal, select, tuple_
from sqlalchemy.exc import IntegrityError

from .artifacts import MAX_ARTIFACT_BYTES, read_verified_artifact
from .auth_boundary import SESSION_COOKIE
from .authorization import authorized_case_access, resolve_actor
from .content_storage import ArtifactObjectStore, EvidenceObjectStore, cleanup_uncommitted_artifact
from .domain import (
    ApplicationError,
    ConfigurationUnavailable,
    Conflict,
    Forbidden,
    ProtectedResourceNotFound,
    StaleVersion,
)
from .foundry_artifacts import (
    ArtifactConnectionChanged,
    ArtifactTransportUnavailable,
    generated_files,
    retrieve_file,
)
from .model_provider import FoundryAccess, ProviderProfile
from .native_response_archive import NativeResponseArchive, NativeResponseScope
from .native_response_index import (
    DatabaseNativeResponseIndex,
    NativeReceiveCommandRow,
    NativeResponseReceiptRow,
)
from .persistence import ApplicationSession as Session
from .persistence import Database, RequestOutputRow
from .tenant_settings import current_settings, settings_version


class OutputInputError(ApplicationError):
    status_code = 422
    code = 'OUTPUT_INPUT_INVALID'
    public_message = 'Choose a bounded output with a safe file name or file-tree paths.'


class OutputBytesUnavailable(OutputInputError):
    code = 'OUTPUT_BYTES_UNAVAILABLE'
    public_message = (
        'No assistant text or file-tree bytes are available in this answer. '
        'Use Show generated files or import the generated file. '
        'The original response remains in its protected receipt.'
    )


class OutputTooLarge(OutputInputError):
    status_code = 413
    code = 'OUTPUT_TOO_LARGE'
    public_message = 'The output exceeds the supported artifact byte limit.'


def safe_filename(name: str) -> str:
    try:
        name.encode('utf-8')
    except UnicodeEncodeError:
        raise OutputInputError() from None
    if (not name or len(name) > 255 or name in {'.', '..'}
            or any(ord(c) < 32 or ord(c) == 127 or c in '/\\:"<>|?*' for c in name)
            or name.endswith((' ', '.'))):
        raise OutputInputError()
    return name


def tree_path(name: str) -> str:
    if (not name or name.startswith('/') or '\\' in name
            or any(not part or part in {'.', '..'} for part in name.split('/'))):
        raise OutputInputError()
    for part in name.split('/'):
        safe_filename(part)
    return name


def native_output(raw: bytes) -> tuple[bytes, str, str]:
    """Frame supplied files only; fall back to original bytes, never repair a report."""
    try:
        envelope = json.loads(raw)
        texts = [part['text'] for message in envelope.get('output', [])
                 if isinstance(message, dict) and message.get('role') == 'assistant'
                 for part in message.get('content', [])
                 if isinstance(part, dict) and part.get('type') == 'output_text'
                 and isinstance(part.get('text'), str)]
    except (ValueError, TypeError, AttributeError, RecursionError) as exc:
        raise OutputInputError() from exc
    if not texts:
        # File pointers are not file bytes; do not fetch or expose the provider/tool envelope.
        raise OutputBytesUnavailable()
    if len(texts) > 1:
        # JSON retains part boundaries and every text value, without provider/tool metadata.
        return json.dumps(texts, ensure_ascii=True).encode(), 'model-output.json', 'NATIVE_OUTPUT'
    try:
        original = texts[0].encode('utf-8')
    except UnicodeEncodeError:
        return json.dumps(texts, ensure_ascii=True).encode(), 'model-output.json', 'NATIVE_OUTPUT'
    try:
        def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError('Ambiguous file tree')
                result[key] = item
            return result

        value = json.loads(texts[0], object_pairs_hook=unique_keys)
    except (ValueError, RecursionError):
        return original, 'model-output.txt', 'NATIVE_OUTPUT'
    # Framing must not discard sibling instructions or any other model-authored value.
    files = value.get('files') if isinstance(value, dict) and set(value) == {'files'} else None
    if not isinstance(files, dict) or not files:
        return original, 'model-output.txt', 'NATIVE_OUTPUT'
    try:
        return frame_tree(files)
    except (OutputInputError, UnicodeEncodeError):
        return original, 'model-output.txt', 'NATIVE_OUTPUT'


def frame_tree(files: dict[str, Any]) -> tuple[bytes, str, str]:
    # The existing candidate container bound is framing safety, not visual/report policy.
    if len(files) > 500:
        raise OutputInputError()
    output = io.BytesIO()
    seen: set[str] = set()
    total = 0
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            path = tree_path(name)
            if len(path.encode('utf-8')) > 65535:
                raise OutputInputError()
            folded = path.casefold()
            if folded in seen:
                raise OutputInputError()
            seen.add(folded)
            if isinstance(value, str):
                data = value.encode('utf-8')
            elif (isinstance(value, dict) and set(value) == {'encoding', 'content'}
                  and value['encoding'] == 'base64' and isinstance(value['content'], str)):
                try:
                    data = base64.b64decode(value['content'], validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise OutputInputError() from exc
            else:
                raise OutputInputError()
            total += len(data)
            if total > MAX_ARTIFACT_BYTES:
                raise OutputTooLarge()
            info = zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, data)
    content = output.getvalue()
    if len(content) > MAX_ARTIFACT_BYTES:
        raise OutputTooLarge()
    return content, 'model-project.zip', 'NATIVE_FILE_TREE'


class NativeOutputSave(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_context_version: int = Field(ge=1, strict=True)
    command_key: UUID


class NativeFileSave(NativeOutputSave):
    pass


def save_digest(expected: int, filename: str, origin: str, native_id: UUID | None,
                digest: str, source_binding: str | None = None) -> str:
    parts: list[Any] = [expected, filename, origin, str(native_id), digest]
    if source_binding is not None:
        parts.append(source_binding)
    return hashlib.sha256(json.dumps(parts, separators=(',', ':')).encode()).hexdigest()


def output_json(row: RequestOutputRow) -> dict[str, Any]:
    return {'id': str(row.id), 'case_id': str(row.case_id),
            'request_version_id': str(row.request_version_id),
            'context_version': row.context_version, 'filename': row.filename,
            'origin': row.origin, 'bytes': row.byte_size, 'sha256': row.content_digest,
            'native_receipt_id': str(row.native_receipt_id) if row.native_receipt_id else None,
            'content_verification': 'NOT_RUN', 'created_at': row.created_at.isoformat()}


def register_request_output_routes(
    app: FastAPI, database: Database, *,
    require_csrf: Callable[[str | None, str | None], None],
    objects: ArtifactObjectStore | None, native_objects: EvidenceObjectStore | None,
    artifact_access_for: Callable[[Session, UUID, UUID], tuple[
        ProviderProfile, FoundryAccess, Callable[[], bool]
    ]] | None = None,
) -> None:
    def sessions() -> Iterator[Session]:
        with database.session() as db:
            yield cast(Session, db)

    DB = Annotated[Session, Depends(sessions)]
    CookieToken = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]

    def save(db: Session, token: str | None, case_id: UUID, expected: int,
             command: UUID, content: bytes, filename: str, origin: str,
             native_id: UUID | None = None, source_binding: str | None = None,
             guard: Callable[[Session], None] | None = None) -> dict[str, Any]:
        # Reads before streaming/archive I/O may have retained ORM identity-map rows.
        # Reload authority and the locked case/access pair before deriving any binding.
        db.expire_all()
        actor = resolve_actor(db, token)
        if native_id is not None and not actor.role.can_invite:
            raise Forbidden()
        case, _ = authorized_case_access(db, actor, case_id, require_edit=True, lock=True)
        if case.semantic_context_version != expected:
            raise StaleVersion()
        if guard is not None:
            guard(db)
        if objects is None:
            raise ConfigurationUnavailable()
        safe_filename(filename)
        if not content:
            raise OutputInputError()
        if len(content) > MAX_ARTIFACT_BYTES:
            raise OutputTooLarge()
        digest = hashlib.sha256(content).hexdigest()
        payload_digest = save_digest(expected, filename, origin, native_id, digest, source_binding)
        query = select(RequestOutputRow).where(
            RequestOutputRow.company_id == actor.company_id,
            RequestOutputRow.case_id == case_id,
            RequestOutputRow.actor_membership_id == actor.membership_id,
            RequestOutputRow.command_key == command,
        )
        previous = db.scalar(query)
        if previous is not None:
            if previous.payload_digest != payload_digest:
                raise Conflict()
            return {'output': output_json(previous), 'replayed': True}
        identity = uuid4()
        key, stored_digest, size = objects.write(actor.company_id, case_id, identity, content)
        if (stored_digest != digest or size != len(content)
                or read_verified_artifact(objects, key, digest, size) != content):
            cleanup_uncommitted_artifact(objects, key)
            raise OutputInputError()
        row = RequestOutputRow(
            id=identity, company_id=actor.company_id, case_id=case_id,
            request_version_id=case.current_request_version_id, context_version=expected,
            actor_membership_id=actor.membership_id, command_key=command,
            payload_digest=payload_digest, native_receipt_id=native_id, origin=origin,
            filename=filename, storage_key=key, content_digest=digest, byte_size=size,
            created_at=datetime.now(UTC),
        )
        db.add(row)
        db.add_audit(actor, 'REQUEST_OUTPUT_SAVED', 'REQUEST_OUTPUT', identity,
                     # Storage succeeded; report content verification remains NOT_RUN.
                     json.dumps({'sha256': digest, 'byte_size': size, 'outcome': 'SUCCEEDED'}))
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            cleanup_uncommitted_artifact(objects, key)
            # A concurrent command never overwrites existing bytes/history.
            previous = db.scalar(query)
            if previous is not None and previous.payload_digest == payload_digest:
                return {'output': output_json(previous), 'replayed': True}
            raise Conflict() from None
        # Commit outcome can be ambiguous: retain bytes rather than delete committed history.
        db.commit()
        return {'output': output_json(row), 'replayed': False}

    @app.post('/api/cases/{case_id}/outputs')
    async def upload_output(
        case_id: UUID, request: Request, filename: str, expected_context_version: int,
        command_key: UUID, db: DB, token: CookieToken = None,
        csrf: Annotated[str | None, Header(alias='X-CSRF-Token')] = None,
    ) -> dict[str, Any]:
        require_csrf(token, csrf)
        actor = resolve_actor(db, token)
        authorized_case_access(db, actor, case_id, require_edit=True)
        safe_filename(filename)
        chunks = bytearray()
        async for chunk in request.stream():
            chunks.extend(chunk)
            if len(chunks) > MAX_ARTIFACT_BYTES:
                raise OutputTooLarge()
        return save(db, token, case_id, expected_context_version, command_key,
                    bytes(chunks), filename, 'IMPORTED_OUTPUT')

    @app.post('/api/cases/{case_id}/native-response-receipts/{reference}/output')
    def save_native_output(
        case_id: UUID, reference: UUID, payload: NativeOutputSave, db: DB,
        token: CookieToken = None,
        csrf: Annotated[str | None, Header(alias='X-CSRF-Token')] = None,
    ) -> dict[str, Any]:
        require_csrf(token, csrf)
        actor = resolve_actor(db, token)
        if not actor.role.can_invite:
            raise Forbidden()
        case, _ = authorized_case_access(db, actor, case_id, require_edit=True)
        row = db.scalar(select(NativeResponseReceiptRow).where(
            NativeResponseReceiptRow.id == reference,
            NativeResponseReceiptRow.company_id == actor.company_id,
            NativeResponseReceiptRow.case_id == case_id,
        ))
        if row is None:
            raise ProtectedResourceNotFound()
        if row.context_version != payload.expected_context_version:
            raise StaleVersion()
        if case.semantic_context_version != payload.expected_context_version:
            raise StaleVersion()
        if native_objects is None:
            raise ConfigurationUnavailable()
        raw = NativeResponseArchive(
            NativeResponseScope(actor.company_id, case_id, row.context_version, row.operation_id),
            native_objects, DatabaseNativeResponseIndex(database),
        ).read(reference)
        content, filename, origin = native_output(raw)
        return save(db, token, case_id, payload.expected_context_version,
                    payload.command_key, content, filename, origin, reference)

    def file_receipt(db: Session, token: str | None, case_id: UUID, reference: UUID,
                     expected: int | None = None) -> tuple[NativeResponseReceiptRow, bytes]:
        actor = resolve_actor(db, token)
        if not actor.role.can_invite:
            raise Forbidden()
        case, _ = authorized_case_access(db, actor, case_id, require_edit=expected is not None)
        row = db.scalar(select(NativeResponseReceiptRow).where(
            NativeResponseReceiptRow.id == reference,
            NativeResponseReceiptRow.company_id == actor.company_id,
            NativeResponseReceiptRow.case_id == case_id,
        ))
        if row is None:
            raise ProtectedResourceNotFound()
        if expected is not None and (row.context_version != expected
                                     or case.semantic_context_version != expected):
            raise StaleVersion()
        if native_objects is None:
            raise ConfigurationUnavailable()
        raw = NativeResponseArchive(
            NativeResponseScope(actor.company_id, case_id, row.context_version, row.operation_id),
            native_objects, DatabaseNativeResponseIndex(database),
        ).read(reference)
        return row, raw

    @app.get('/api/cases/{case_id}/native-response-receipts/{reference}/files')
    def list_native_files(case_id: UUID, reference: UUID, db: DB,
                          token: CookieToken = None) -> dict[str, Any]:
        _, raw = file_receipt(db, token, case_id, reference)
        items = []
        for index, file in enumerate(generated_files(raw)):
            try:
                safe_filename(file.filename)
                safe = True
            except OutputInputError:
                safe = False
            items.append({'index': index, 'filename': file.filename, 'savable': safe})
        return {'items': items, 'retrieval_configured': artifact_access_for is not None,
                'content_verification': 'NOT_RUN'}

    @app.post('/api/cases/{case_id}/native-response-receipts/{reference}/files/{index}/output')
    def save_native_file(
        case_id: UUID, reference: UUID, index: int, payload: NativeFileSave, db: DB,
        token: CookieToken = None,
        csrf: Annotated[str | None, Header(alias='X-CSRF-Token')] = None,
    ) -> dict[str, Any]:
        require_csrf(token, csrf)
        row, raw = file_receipt(db, token, case_id, reference, payload.expected_context_version)
        # Archive reads can interleave with committed role/access/request changes.
        db.expire_all()
        actor = resolve_actor(db, token)
        if not actor.role.can_invite:
            raise Forbidden()
        case, _ = authorized_case_access(db, actor, case_id, require_edit=True)
        if case.semantic_context_version != payload.expected_context_version:
            raise StaleVersion()
        files = generated_files(raw)
        if index < 0 or index >= len(files):
            raise OutputBytesUnavailable()
        file = files[index]
        safe_filename(file.filename)
        actor = resolve_actor(db, token)
        previous = db.scalar(select(RequestOutputRow).where(
            RequestOutputRow.company_id == actor.company_id,
            RequestOutputRow.case_id == case_id,
            RequestOutputRow.actor_membership_id == actor.membership_id,
            RequestOutputRow.command_key == payload.command_key,
        ))
        if previous is not None:
            expected_digest = save_digest(payload.expected_context_version, file.filename,
                                          'NATIVE_OUTPUT', reference,
                                          previous.content_digest, file.binding)
            if previous.payload_digest != expected_digest:
                raise Conflict()
            return {'output': output_json(previous), 'replayed': True}
        if artifact_access_for is None:
            raise ConfigurationUnavailable()
        db.expire_all()
        # Current and original immutable Tenant Settings must name the same project/profile.
        command = db.scalar(select(NativeReceiveCommandRow).where(
            NativeReceiveCommandRow.id == row.operation_id,
            NativeReceiveCommandRow.company_id == actor.company_id,
            NativeReceiveCommandRow.case_id == case_id,
        ))
        if command is None:
            raise ProtectedResourceNotFound()
        original = settings_version(db, actor.company_id, command.settings_id)
        profile, access, ready = artifact_access_for(db, actor.company_id, case_id)
        if (access.company_id != actor.company_id
                or original.settings.provider_profile != profile
                or original.secret_reference_id is not None):
            raise ArtifactConnectionChanged()

        def current_connection(db: Session) -> None:
            snapshot = current_settings(db, actor.company_id)
            if (snapshot.settings.provider_profile != profile
                    or snapshot.secret_reference_id is not None):
                raise ArtifactConnectionChanged()
            if ready() is not True:
                raise ArtifactTransportUnavailable()

        current_connection(db)
        content = retrieve_file(profile, access, file, ready)
        return save(db, token, case_id, payload.expected_context_version, payload.command_key,
                    content, file.filename, 'NATIVE_OUTPUT', reference,
                    source_binding=file.binding, guard=current_connection)

    @app.get('/api/cases/{case_id}/outputs')
    def list_outputs(case_id: UUID, db: DB, token: CookieToken = None,
                     before: UUID | None = None) -> dict[str, Any]:
        actor = resolve_actor(db, token)
        authorized_case_access(db, actor, case_id)
        query = select(RequestOutputRow).where(
            RequestOutputRow.case_id == case_id, RequestOutputRow.company_id == actor.company_id
        )
        if before is not None:
            cursor = db.scalar(query.where(RequestOutputRow.id == before))
            if cursor is None:
                raise ProtectedResourceNotFound()
            query = query.where(tuple_(RequestOutputRow.created_at, RequestOutputRow.id)
                                < tuple_(literal(cursor.created_at), literal(cursor.id)))
        rows = list(db.scalars(query.order_by(
            RequestOutputRow.created_at.desc(), RequestOutputRow.id.desc()
        ).limit(101)))
        items = rows[:100]
        return {'items': [output_json(row) for row in items],
                'has_more': len(rows) > 100,
                'next_cursor': str(items[-1].id) if len(rows) > 100 else None,
                'maximum_bytes': MAX_ARTIFACT_BYTES}

    @app.get('/api/cases/{case_id}/outputs/{output_id}/download')
    def download_output(
        case_id: UUID, output_id: UUID, db: DB, token: CookieToken = None,
    ) -> Response:
        actor = resolve_actor(db, token)
        authorized_case_access(db, actor, case_id)
        row = db.scalar(select(RequestOutputRow).where(
            RequestOutputRow.id == output_id, RequestOutputRow.case_id == case_id,
            RequestOutputRow.company_id == actor.company_id,
        ))
        if row is None:
            raise ProtectedResourceNotFound()
        if objects is None:
            raise ConfigurationUnavailable()
        content = read_verified_artifact(
            objects, row.storage_key, row.content_digest, row.byte_size
        )
        return Response(content, media_type='application/octet-stream', headers={
            'Content-Disposition': "attachment; filename*=UTF-8''" + quote(row.filename, safe=''),
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        })
