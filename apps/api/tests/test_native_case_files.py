"""Synthetic source transport only: no customer files, paid calls or new tools."""

import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest

from apbra_api.domain import SemanticValidationFailed
from apbra_api.native_case_files import prepare_case_files


@pytest.fixture
def source():
    case = SimpleNamespace(id=uuid4(), company_id=uuid4(), current_request_version_id=uuid4())
    raw = ('\ufeffName,Value,Note\r\n' + ''.join(
        f'Row{n},{n},"<script>untrusted {n}</script>, café"\r\n' for n in range(40)
    )).encode('utf-8')
    row = SimpleNamespace(
        id=uuid4(), company_id=case.company_id, case_id=case.id,
        request_version_id=case.current_request_version_id, filename='source.csv', format='CSV',
        storage_key='private-not-for-model', content_digest=hashlib.sha256(raw).hexdigest(),
    )
    reads = []

    class Objects:
        content = raw

        def read(self, key, digest):
            reads.append((key, digest))
            return self.content

    objects = Objects()
    store = SimpleNamespace(evidence_items=lambda _: [row], reference_materials=lambda _: [])
    return SimpleNamespace(case=case, raw=raw, row=row, objects=objects, store=store, reads=reads)


def prepare(s, **kwargs):
    return prepare_case_files(s.store, s.case, s.objects, s.objects,
                              max_file_bytes=kwargs.get('max_file_bytes', 5_000_000))


def test_every_source_byte_round_trips_bom_quotes_unicode_newlines_and_last_row(source):
    s = source
    bundle = prepare(s)
    assert bundle.ready and len(bundle.sources) == 1
    item = bundle.sources[0]
    assert item['sourceText'].encode('utf-8') == s.raw
    assert 'Row39' in item['sourceText']
    assert item['byteCount'] == len(s.raw)
    assert hashlib.sha256(item['sourceText'].encode('utf-8')).hexdigest() == item['contentDigest']
    assert 'private-not-for-model' not in repr(bundle.manifest)
    assert 'sourceText' not in repr(bundle)
    assert bundle.manifest[0]['serviceFileUploaded'] is False
    assert bundle.manifest[0]['processingVerified'] is False


@pytest.mark.parametrize('kind', ['xlsx', 'image', 'oversized', 'corrupted', 'non-utf8'])
def test_unsupported_unavailable_or_oversized_never_returns_partial_sources(source, kind):
    s = source
    if kind == 'xlsx':
        s.row.format = 'XLSX'
        s.row.filename = 'original.xlsx'
    elif kind == 'image':
        image = SimpleNamespace(**vars(s.row))
        image.id = uuid4()
        image.filename = 'support.png'
        s.store.reference_materials = lambda _: [image]
    elif kind in {'corrupted', 'non-utf8'}:
        s.objects.content = b'changed' if kind == 'corrupted' else b'\xff'
        if kind == 'non-utf8':
            s.row.content_digest = hashlib.sha256(s.objects.content).hexdigest()
    bundle = prepare(s, max_file_bytes=1 if kind == 'oversized' else 5_000_000)
    assert not bundle.ready and bundle.sources == []
    assert any(item['status'] == 'UNAVAILABLE' for item in bundle.manifest)
    assert s.objects.content  # original source remains in storage


@pytest.mark.parametrize('field', ['company_id', 'case_id'])
def test_bad_persistence_scope_fails_before_storage_read(source, field):
    s = source
    setattr(s.row, field, uuid4())
    with pytest.raises(SemanticValidationFailed):
        prepare(s)
    assert not s.reads


def test_old_request_and_no_current_files_are_explicitly_not_ready(source):
    s = source
    s.row.request_version_id = uuid4()
    bundle = prepare(s)
    assert not bundle.ready and bundle.sources == [] and bundle.manifest == []
    assert not s.reads


@pytest.mark.parametrize("media,raw", [
    ("image/png", b"\x89PNG\r\n\x1a\nsynthetic-image"),
    ("image/jpeg", b"\xff\xd8\xffsynthetic-image\xff\xd9"),
])
def test_original_images_are_inline_bytes_only_when_settings_permits_vision(source, media, raw):
    import base64

    s = source
    image = SimpleNamespace(**vars(s.row))
    image.id = uuid4()
    image.media_type = media
    image.filename = "synthetic.png" if media == "image/png" else "synthetic.jpg"
    image.content_digest = hashlib.sha256(raw).hexdigest()
    image.storage_key = "image-private-key"
    s.store.reference_materials = lambda _: [image]

    class Images:
        def read(self, key, digest):
            return raw

    denied = prepare_case_files(s.store, s.case, s.objects, Images(), max_file_bytes=5_000_000)
    assert not denied.ready and denied.sources == [] and denied.image_parts == []
    assert denied.manifest[1]['reason'] == 'TENANT_VISION_CAPABILITY_DISABLED'
    ready = prepare_case_files(s.store, s.case, s.objects, Images(),
                               max_file_bytes=5_000_000, vision_enabled=True)
    assert ready.ready and len(ready.image_parts) == 1
    part = ready.image_parts[0]
    assert part['type'] == 'input_image'
    prefix, encoded = part['image_url'].split(',', 1)
    assert prefix == f'data:{media};base64'
    assert base64.b64decode(encoded, validate=True) == raw
    assert ready.sources[1]['contentDigest'] == image.content_digest
    assert ready.sources[1]['imageContentIndex'] == 1
    assert 'image-private-key' not in repr(ready)


@pytest.mark.parametrize("fault", ["disabled", "oversized", "remote", "malformed", "mismatch"])
def test_native_image_serializer_rejects_invalid_or_overbudget_input_before_dispatch(fault):
    from test_foundry_report_runtime import approval

    from apbra_api.model_provider import ProviderCallError, ProviderRequest
    from apbra_api.native_response_probe import native_request_content

    profile = approval().binding.provider_profile
    profile = profile.model_copy(update={
        'max_input_characters': 10000,
        'capabilities': profile.capabilities.model_copy(update={'vision': fault != 'disabled'}),
    })
    part = {'type':'input_image', 'image_url':'data:image/png;base64,iVBORw0KGgpzeW50aGV0aWM='}
    if fault == 'oversized':
        profile = profile.model_copy(update={'max_input_characters':1})
    elif fault == 'remote':
        part['image_url'] = 'https://private.invalid/file?token=do-not-fetch'
    elif fault == 'malformed':
        part['image_url'] = 'data:image/png;base64,invalid@@'
    request = ProviderRequest(task='REQUIREMENT_ANALYSIS',system_prompt='',output_schema={},
                              context={},requires_vision=fault != 'mismatch')
    with pytest.raises(ProviderCallError):
        native_request_content(profile, request, [part])
