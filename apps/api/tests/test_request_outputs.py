"""Synthetic opaque output custody tests; no report compiler, provider or owner data."""
import base64
import hashlib
import io
import json
import zipfile
from uuid import UUID, uuid4

import pytest
from conftest import csrf, disposable_alembic_config, sign_in
from sqlalchemy import MetaData, Table, inspect, select, text
from sqlalchemy.exc import DBAPIError

from alembic import command
from apbra_api.artifacts import MAX_ARTIFACT_BYTES
from apbra_api.evidence import LocalEvidenceStore
from apbra_api.native_response_archive import NativeResponseArchive, NativeResponseScope
from apbra_api.native_response_index import DatabaseNativeResponseIndex, NativeReceiveCommandRow
from apbra_api.persistence import CaseRow, MembershipRow, RequestOutputRow
from apbra_api.tenant_settings import current_settings


@pytest.fixture
def own_case(client):
    session = sign_in(client)
    result = client.post('/api/cases', headers={**csrf(session), 'Idempotency-Key': str(uuid4())},
                         json={'request_text': 'Synthetic direct output custody'})
    assert result.status_code == 201
    return result.json()['case'], session


def upload(client, own_case, content=b'Incomplete arbitrary output', **overrides):
    case, session = own_case
    params = {'filename': 'Synthetic.pbip.zip', 'expected_context_version': 1,
              'command_key': str(uuid4()), **overrides}
    return client.post(f"/api/cases/{case['id']}/outputs", params=params,
                       content=content, headers={**csrf(session),
                                                 'Content-Type': 'application/octet-stream'})


def download_path(case, row):
    return f"/api/cases/{case['id']}/outputs/{row['id']}/download"


def test_incomplete_opaque_output_is_saved_and_delivered_without_content_gate(
    client, own_case, database, monkeypatch,
):
    import apbra_api.generation as generation

    def forbidden(*args, **kwargs):
        raise AssertionError('Direct output must not call a compiler or provider')

    monkeypatch.setattr(generation.GenerationBridge, 'generate', forbidden)
    monkeypatch.setattr(generation.GenerationBridge, 'validate_design', forbidden)
    opaque = b'This is deliberately not a ZIP, PBIP, model or report.\x00\xff'
    result = upload(client, own_case, opaque)
    assert result.status_code == 200, result.text
    row = result.json()['output']
    assert row['content_verification'] == 'NOT_RUN'
    assert row['request_version_id'] == own_case[0]['current_request_version_id']
    delivered = client.get(download_path(own_case[0], row))
    assert delivered.status_code == 200 and delivered.content == opaque
    assert delivered.headers['cache-control'] == 'no-store'
    assert delivered.headers['x-content-type-options'] == 'nosniff'
    assert delivered.headers['content-type'] == 'application/octet-stream'
    assert row['sha256'] == hashlib.sha256(opaque).hexdigest()
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM generation_attempts')) == 0
        assert db.scalar(text('SELECT count(*) FROM request_outputs')) == 1
        assert db.scalar(text("SELECT count(*) FROM audit_events "
                              "WHERE event_type='REQUEST_OUTPUT_SAVED'")) == 1
        saved_details = db.scalar(text("SELECT details_json FROM audit_events "
                                       "WHERE event_type='REQUEST_OUTPUT_SAVED'"))
        assert json.loads(saved_details)['outcome'] == 'SUCCEEDED'
    history = client.get('/api/tenant-settings/audit-events',
                         headers={'X-Expected-Membership-Id':
                                  client.get('/api/auth/session').json()['actor']['membership_id']},
                         params={'module': 'Reports', 'operation': 'REQUEST_OUTPUT_SAVED',
                                 'outcome': 'SUCCEEDED'})
    assert history.status_code == 200
    saved_events = history.json()['items']
    assert len(saved_events) == 1
    assert saved_events[0]['target_id'] == row['id']
    assert saved_events[0]['module'] == 'Reports'
    assert saved_events[0]['outcome'] == 'SUCCEEDED'


def test_original_zip_including_uninterpreted_paths_is_not_extracted_or_rewritten(client, own_case):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('../uninterpreted-model-file.txt', 'Opaque archive; never extract here')
        archive.writestr('Only.pbip', '{}')
        archive.comment = b'Original model archive metadata'
    raw = output.getvalue()
    result = upload(client, own_case, raw)
    assert result.status_code == 200
    assert client.get(download_path(own_case[0], result.json()['output'])).content == raw


def test_idempotency_preserves_first_output_and_rejects_changed_bytes(client, own_case, database):
    key = str(uuid4())
    first = upload(client, own_case, b'Original', command_key=key)
    repeat = upload(client, own_case, b'Original', command_key=key)
    assert repeat.status_code == 200 and repeat.json()['replayed'] is True
    assert repeat.json()['output'] == first.json()['output']
    changed = upload(client, own_case, b'Changed', command_key=key)
    assert changed.status_code == 409
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM request_outputs')) == 1


@pytest.mark.parametrize('filename', ['../output.zip', '/absolute.zip', 'a\\b.zip',
                                     'x\r\nHeader.zip', 'x:stream.zip', 'trailing.'])
def test_unsafe_download_filename_rejected_without_writes(client, own_case, database, filename):
    assert upload(client, own_case, filename=filename).status_code == 422
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM request_outputs')) == 0


def test_existing_artifact_byte_limit_is_enforced(client, own_case, database):
    assert upload(client, own_case, b'x' * (MAX_ARTIFACT_BYTES + 1)).status_code == 413
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM request_outputs')) == 0


def test_private_foreign_anonymous_and_revoked_access_stay_protected(
    client, own_case, database,
):
    case, _ = own_case
    saved = upload(client, own_case).json()['output']
    path = download_path(case, saved)
    for identity in ['member', 'foreign']:
        client.cookies.clear()
        other = sign_in(client, identity)
        assert client.get(path).status_code == 404
        assert client.post(f"/api/cases/{case['id']}/outputs",
                           params={'filename': 'x.bin', 'expected_context_version': 1,
                                   'command_key': str(uuid4())}, content=b'x',
                           headers=csrf(other)).status_code == 404
    client.cookies.clear()
    session = sign_in(client)
    assert client.post(f"/api/cases/{case['id']}/outputs",
                       params={'filename': 'x.bin', 'expected_context_version': 1,
                               'command_key': str(uuid4())}, content=b'x').status_code == 401
    with database.session() as db:
        membership = db.get(MembershipRow, UUID(session['actor']['membership_id']))
        membership.active = False
        db.commit()
    assert client.get(path).status_code == 401
    client.cookies.clear()
    assert client.get(path).status_code == 401


def test_normal_member_can_save_own_output_without_admin_or_provider(client):
    session = sign_in(client, 'member')
    case = client.post('/api/cases', headers={**csrf(session), 'Idempotency-Key': str(uuid4())},
                       json={'request_text': 'Synthetic member output'}).json()['case']
    assert upload(client, (case, session)).status_code == 200


def test_output_remains_bound_to_original_request_and_readable_after_context_changes(
    client, own_case, database,
):
    case, _ = own_case
    saved = upload(client, own_case).json()['output']
    with database.session() as db:
        db.get(CaseRow, UUID(case['id'])).semantic_context_version = 2
        db.commit()
    assert upload(client, own_case).status_code == 409
    assert client.get(download_path(case, saved)).status_code == 200
    listed = client.get(f"/api/cases/{case['id']}/outputs").json()['items']
    assert listed == [saved] and saved['context_version'] == 1


def native_receipt(own_case, database, settings, value):
    case, session = own_case
    company, case_id = UUID(case['company_id']), UUID(case['id'])
    operation = uuid4()
    with database.session() as db:
        snapshot = current_settings(db, company)
        db.add(NativeReceiveCommandRow(
            id=operation, company_id=company, case_id=case_id,
            actor_membership_id=UUID(session['actor']['membership_id']), context_version=1,
            settings_id=snapshot.id, command_key=uuid4(), state='RECEIVED',
            http_status=200, provider_status='completed',
        ))
        db.commit()
    raw = json.dumps({'output': [{'type': 'message', 'role': 'assistant', 'content': [
        {'type': 'output_text', 'text': json.dumps(value)},
    ]}]}).encode()
    store = LocalEvidenceStore(settings.evidence_root, 'test')
    archive = NativeResponseArchive(NativeResponseScope(company, case_id, 1, operation),
                                    store, DatabaseNativeResponseIndex(database))
    receipt = archive.preserve(raw)
    return receipt, archive, raw


def test_native_file_tree_preserves_binary_funnel_and_unrestricted_dax_without_report_design(
    client, own_case, database, settings,
):
    files = {'Motion.pbip': '{}', 'Motion.Report/definition/visuals/funnel/visual.json':
             '{"visualType":"funnel","businessChoice":"entirely model owned"}',
             'Motion.SemanticModel/model.bim': 'Any model-authored TMSL/DAX, unverified',
             'data/Synthetic.xlsx': {'encoding': 'base64',
                                     'content': base64.b64encode(b'\x00\xffSynthetic').decode()}}
    receipt, archive, original = native_receipt(own_case, database, settings, {'files': files})
    case, session = own_case
    result = client.post(f"/api/cases/{case['id']}/native-response-receipts/{receipt.id}/output",
                         headers=csrf(session), json={'expected_context_version': 1,
                                                     'command_key': str(uuid4())})
    assert result.status_code == 200, result.text
    row = result.json()['output']
    assert row['origin'] == 'NATIVE_FILE_TREE' and row['content_verification'] == 'NOT_RUN'
    delivered = client.get(download_path(case, row))
    with zipfile.ZipFile(io.BytesIO(delivered.content)) as output:
        assert set(output.namelist()) == set(files)
        for name, value in files.items():
            assert output.read(name) == (value.encode() if isinstance(value, str)
                                         else base64.b64decode(value['content']))
    assert archive.read(receipt.id) == original


def test_non_project_model_content_is_saved_without_completeness_or_semantic_gate(
    client, own_case, database, settings,
):
    value = {'artifact_kind': 'ReportDesign', 'schema_version': 'unfinished',
             'overview': 'Unsupported business ideas need no application acceptance'}
    receipt, archive, raw = native_receipt(own_case, database, settings, value)
    case, session = own_case
    result = client.post(f"/api/cases/{case['id']}/native-response-receipts/{receipt.id}/output",
                         headers=csrf(session), json={'expected_context_version': 1,
                                                     'command_key': str(uuid4())})
    assert result.status_code == 200, result.text
    row = result.json()['output']
    assert row['origin'] == 'NATIVE_OUTPUT'
    assert client.get(download_path(case, row)).content == json.dumps(value).encode()
    assert archive.read(receipt.id) == raw


def test_new_output_rows_are_immutable_and_populated_downgrade_is_blocked(
    client, own_case, database, settings,
):
    output = upload(client, own_case).json()['output']
    config = disposable_alembic_config(settings.database_url)
    for sql in ['UPDATE request_outputs SET filename=\'changed\'', 'DELETE FROM request_outputs']:
        with pytest.raises(DBAPIError), database.session() as db:
            db.execute(text(sql))
            db.commit()
    with pytest.raises(RuntimeError, match='retained request outputs'):
        command.downgrade(config, '20261017_13')
    with database.session() as db:
        assert db.get(RequestOutputRow, UUID(output['id'])).filename == output['filename']
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == '20261018_14'


def test_empty_additive_migration_preserves_every_legacy_row(client, own_case, database, settings):
    tables = [t for t in inspect(database.engine).get_table_names()
              if t not in {'request_outputs', 'alembic_version'}]

    def snapshot():
        with database.session() as db:
            return {name: sorted(str(tuple(row)) for row in db.execute(select(
                Table(name, MetaData(), autoload_with=database.engine)
            )).all()) for name in tables}

    before = snapshot()
    config = disposable_alembic_config(settings.database_url)
    command.downgrade(config, '20261017_13')
    assert 'request_outputs' not in inspect(database.engine).get_table_names()
    command.upgrade(config, 'head')
    assert snapshot() == before


@pytest.mark.parametrize('answer', [
    '{"files":{"../unsafe.txt":"all original text retained"}}',
    '{"files":{"report.txt":"x"},"instructions":"important original content"}',
    '{"files":{"duplicate.txt":"first","duplicate.txt":"second"}}',
    '{"files":{"binary.bin":{"encoding":"base64","content":"!invalid!"}}}',
    '{"files":{"File.txt":"first","file.txt":"second"}}',
    '{"files":{"file.txt":false}}',
])
def test_unframeable_file_tree_remains_savable_original_assistant_text(answer):
    from apbra_api.request_outputs import native_output

    raw = json.dumps({'output': [{'role': 'assistant', 'content': [
        {'type': 'output_text', 'text': answer},
    ]}]}).encode()
    assert native_output(raw) == (answer.encode(), 'model-output.txt', 'NATIVE_OUTPUT')


@pytest.mark.parametrize('parts', [['first', 'second'], ['\ud800']])
def test_multipart_and_unencodable_assistant_values_saved_losslessly_as_json(parts):
    from apbra_api.request_outputs import native_output

    raw = json.dumps({'output': [{'role': 'assistant', 'content': [
        {'type': 'output_text', 'text': part} for part in parts
    ]}]}).encode()
    content, filename, origin = native_output(raw)
    assert json.loads(content) == parts
    assert filename == 'model-output.json' and origin == 'NATIVE_OUTPUT'


def test_overlong_zip_path_retains_original_text_without_framing_exception():
    from apbra_api.request_outputs import native_output

    answer = json.dumps({'files': {'/'.join(['a' * 255] * 257): 'all content retained'}})
    raw = json.dumps({'output': [{'role': 'assistant', 'content': [
        {'type': 'output_text', 'text': answer}
    ]}]}).encode()
    assert native_output(raw) == (answer.encode(), 'model-output.txt', 'NATIVE_OUTPUT')


def test_attachment_pointer_without_bytes_has_explicit_carrier_error():
    from apbra_api.request_outputs import OutputBytesUnavailable, native_output

    raw = json.dumps({'output': [{'role': 'assistant', 'content': [
        {'type': 'container_file_citation', 'file_id': 'synthetic-pointer-only'}
    ]}], 'metadata': {'private': 'must not be promoted into shared output'}}).encode()
    with pytest.raises(OutputBytesUnavailable):
        native_output(raw)


def test_output_history_pages_without_losing_older_outputs_or_accepting_foreign_cursor(
    client, own_case,
):
    identities = {upload(client, own_case, str(n).encode()).json()['output']['id']
                  for n in range(102)}
    url = f"/api/cases/{own_case[0]['id']}/outputs"
    first = client.get(url).json()
    assert len(first['items']) == 100 and first['has_more'] is True
    second = client.get(url, params={'before': first['next_cursor']}).json()
    assert len(second['items']) == 2 and second['has_more'] is False
    assert second['next_cursor'] is None
    assert {row['id'] for row in first['items'] + second['items']} == identities
    assert client.get(url, params={'before': str(uuid4())}).status_code == 404


@pytest.mark.parametrize(('change', 'status'), [('context', 409), ('access', 404),
                                              ('role', 403), ('membership', 401)])
def test_native_save_rechecks_fresh_authority_and_request_after_archive_read(
    client, own_case, database, settings, monkeypatch, change, status,
):
    from apbra_api.persistence import CaseAccessRow, RequestVersionRow

    receipt, archive, raw = native_receipt(own_case, database, settings, {'files': {'x.txt': 'x'}})
    case, session = own_case
    actor_id = UUID(session['actor']['membership_id'])
    before = set(settings.artifact_root.rglob('*'))
    original_read = NativeResponseArchive.read

    def interleaved_read(self, reference):
        result = original_read(self, reference)
        # A genuinely separate committed transaction changes authority/currentness.
        with database.session() as other:
            current = other.get(CaseRow, UUID(case['id']))
            if change == 'context':
                revision = RequestVersionRow(
                    id=uuid4(), case_id=current.id, company_id=current.company_id, sequence=2,
                    request_text='New saved synthetic request', created_by_membership_id=actor_id,
                )
                other.add(revision)
                other.flush()
                current.current_request_version_id = revision.id
                current.version = 2
                current.semantic_context_version = 2
            elif change == 'access':
                access = other.scalar(select(CaseAccessRow).where(
                    CaseAccessRow.case_id == current.id,
                    CaseAccessRow.membership_id == actor_id,
                ))
                access.access_level = 'VIEWER'
            else:
                membership = other.get(MembershipRow, actor_id)
                if change == 'role':
                    membership.role = 'MEMBER'
                else:
                    membership.active = False
            other.commit()
        return result

    monkeypatch.setattr(NativeResponseArchive, 'read', interleaved_read)
    result = client.post(f"/api/cases/{case['id']}/native-response-receipts/{receipt.id}/output",
                         headers=csrf(session), json={'expected_context_version': 1,
                                                     'command_key': str(uuid4())})
    assert result.status_code == status, result.text
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM request_outputs')) == 0
    assert set(settings.artifact_root.rglob('*')) == before
    assert original_read(archive, receipt.id) == raw
