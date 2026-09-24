from __future__ import annotations

import io
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient

from apbra_api.config import Settings
from apbra_api.evidence import EvidenceError, LocalEvidenceStore, parse_evidence
from apbra_api.persistence import ApplicationSession


def test_csv_schema_is_observed_without_inventing_rows() -> None:
    parsed = parse_evidence(b"Division,Amount\nNorth,12.5\nSouth,7\n", "ledger.csv")
    assert parsed.format == "CSV"
    assert parsed.observed_schema["tables"][0]["rowCount"] == 2
    assert [column["name"] for column in parsed.observed_schema["tables"][0]["columns"]] == [
        "Division",
        "Amount",
    ]


def test_xlsx_archive_rejects_traversal_and_external_content() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../escape", "unsafe")
        archive.writestr("xl/workbook.xml", "<workbook/>")
    with pytest.raises(EvidenceError):
        parse_evidence(output.getvalue(), "unsafe.xlsx")


def test_supported_xlsx_schema_is_observed() -> None:
    output = io.BytesIO()
    workbook = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Observations" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
        "</Relationships>"
    )
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row><c t="inlineStr"><is><t>Campus</t></is></c>'
        '<c t="inlineStr"><is><t>Visits</t></is></c></row><row>'
        '<c t="inlineStr"><is><t>North</t></is></c><c><v>12</v></c></row>'
        "</sheetData></worksheet>"
    )
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    parsed = parse_evidence(output.getvalue(), "attendance.xlsx")
    assert parsed.format == "XLSX"
    assert parsed.observed_schema["tables"][0]["name"] == "Observations"
    assert [item["name"] for item in parsed.observed_schema["tables"][0]["columns"]] == [
        "Campus",
        "Visits",
    ]


def test_xlsx_rejects_xml_declarations_after_a_long_prefix() -> None:
    output = io.BytesIO()
    workbook = (
        " " * 5000
        + '<!DOCTYPE workbook [<!ENTITY injected "InjectedSheet">]>'
        + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        + 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        + '<sheets><sheet name="&injected;" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", "<Relationships/>")
    with pytest.raises(EvidenceError, match="declarations"):
        parse_evidence(output.getvalue(), "padded-declaration.xlsx")


def test_xlsx_rejects_utf16_dtd_and_entity_declarations() -> None:
    output = io.BytesIO()
    workbook = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE workbook [<!ENTITY injected "InjectedSheet">]>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="&injected;" sheetId="1" r:id="rId1"/></sheets></workbook>'
    ).encode("utf-16")
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", "<Relationships/>")
    with pytest.raises(EvidenceError, match="declarations"):
        parse_evidence(output.getvalue(), "utf16-declaration.xlsx")


@pytest.mark.parametrize(
    ("target_mode", "target"),
    [("External", "https://example.invalid/data.xlsx"), ("", "file:///tmp/private.xlsx")],
)
def test_xlsx_rejects_any_external_relationship(target_mode: str, target: str) -> None:
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row><c t="inlineStr"><is><t>Value</t></is></c></row></sheetData>'
        "</worksheet>"
    )
    source_bytes = workbook_with_sheet(sheet)
    output = io.BytesIO()
    external_relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="external" Target="{target}" TargetMode="{target_mode}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink"/>'
        "</Relationships>"
    )
    with (
        zipfile.ZipFile(io.BytesIO(source_bytes)) as source,
        zipfile.ZipFile(output, "w") as target_zip,
    ):
        for item in source.infolist():
            target_zip.writestr(item, source.read(item.filename))
        target_zip.writestr("xl/worksheets/_rels/sheet1.xml.rels", external_relationships)
    with pytest.raises(EvidenceError, match="external, or unsupported workbook relationships"):
        parse_evidence(output.getvalue(), "external-relationship.xlsx")


@pytest.mark.parametrize(
    "relationship_type",
    [
        "oleObject",
        "activeXControl",
        "vbaProject",
        "externalLink",
        "connections",
        "queryTable",
        "control",
        "ctrlProp",
        "package",
        "unknownFutureActiveType",
    ],
)
def test_xlsx_rejects_active_relationship_types_with_innocent_targets(
    relationship_type: str,
) -> None:
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row><c t="inlineStr"><is><t>Value</t></is></c></row></sheetData>'
        "</worksheet>"
    )
    source_bytes = workbook_with_sheet(sheet)
    output = io.BytesIO()
    active_relationship = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="disguised" Target="styles.xml" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{relationship_type}"/>'
        "</Relationships>"
    )
    with (
        zipfile.ZipFile(io.BytesIO(source_bytes)) as source,
        zipfile.ZipFile(output, "w") as target_zip,
    ):
        for item in source.infolist():
            target_zip.writestr(item, source.read(item.filename))
        target_zip.writestr("xl/worksheets/_rels/sheet1.xml.rels", active_relationship)
    with pytest.raises(EvidenceError, match="Active, executable, external, or unsupported"):
        parse_evidence(output.getvalue(), "disguised-active-relationship.xlsx")


@pytest.mark.parametrize(
    "unsafe_target",
    [
        r"\\server\share\book.xlsx",
        r"\absolute\book.xlsx",
        "/xl/styles.xml",
        "../../../outside.xml",
        "styles.xml?override=outside.xml",
        "%2Fxl%2Fstyles.xml",
    ],
)
def test_xlsx_rejects_uncontained_supported_relationship_targets(
    unsafe_target: str,
) -> None:
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row><c t="inlineStr"><is><t>Value</t></is></c></row></sheetData>'
        "</worksheet>"
    )
    source_bytes = workbook_with_sheet(sheet)
    output = io.BytesIO()
    relationship = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="unsafe" Target="{unsafe_target}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"/>'
        "</Relationships>"
    )
    with (
        zipfile.ZipFile(io.BytesIO(source_bytes)) as source,
        zipfile.ZipFile(output, "w") as target_zip,
    ):
        for item in source.infolist():
            target_zip.writestr(item, source.read(item.filename))
        target_zip.writestr("xl/styles.xml", "<styleSheet/>")
        target_zip.writestr("xl/worksheets/_rels/sheet1.xml.rels", relationship)
    with pytest.raises(EvidenceError, match="not package-contained"):
        parse_evidence(output.getvalue(), "uncontained-relationship.xlsx")


def test_xlsx_allows_contained_parent_relative_passive_relationship() -> None:
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row><c t="inlineStr"><is><t>Value</t></is></c></row></sheetData>'
        "</worksheet>"
    )
    source_bytes = workbook_with_sheet(sheet)
    output = io.BytesIO()
    relationship = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="drawing" Target="../drawings/drawing1.xml" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"/>'
        "</Relationships>"
    )
    with (
        zipfile.ZipFile(io.BytesIO(source_bytes)) as source,
        zipfile.ZipFile(output, "w") as target_zip,
    ):
        for item in source.infolist():
            target_zip.writestr(item, source.read(item.filename))
        target_zip.writestr("xl/drawings/drawing1.xml", "<drawing/>")
        target_zip.writestr("xl/worksheets/_rels/sheet1.xml.rels", relationship)
    assert parse_evidence(output.getvalue(), "contained-relationship.xlsx").format == "XLSX"


@pytest.mark.parametrize(
    "active_part",
    [
        "xl/embeddings/oleObject1.bin",
        "xl/activeX/activeX1.xml",
        "xl/ctrlProps/ctrlProp1.xml",
        "customUI/customUI.xml",
    ],
)
def test_xlsx_rejects_embedded_or_active_package_parts(active_part: str) -> None:
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row><c t="inlineStr"><is><t>Value</t></is></c></row></sheetData>'
        "</worksheet>"
    )
    workbook = io.BytesIO(workbook_with_sheet(sheet))
    output = io.BytesIO()
    with zipfile.ZipFile(workbook) as source, zipfile.ZipFile(output, "w") as target:
        for item in source.infolist():
            target.writestr(item, source.read(item.filename))
        target.writestr(active_part, b"active content")
    with pytest.raises(EvidenceError, match="executable content"):
        parse_evidence(output.getvalue(), "active-content.xlsx")


def workbook_with_sheet(sheet: str) -> bytes:
    output = io.BytesIO()
    workbook = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Observed" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def test_xlsx_sparse_cells_preserve_their_declared_columns() -> None:
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Amount</t></is></c>'
        '<c r="B1" t="inlineStr"><is><t>Division</t></is></c></row>'
        '<row r="2"><c r="B2" t="inlineStr"><is><t>North</t></is></c></row>'
        '<row r="3"><c r="A3"><v>12</v></c>'
        '<c r="B3" t="inlineStr"><is><t>South</t></is></c></row>'
        "</sheetData></worksheet>"
    )
    parsed = parse_evidence(workbook_with_sheet(sheet), "sparse.xlsx")
    columns = parsed.observed_schema["tables"][0]["columns"]
    assert columns[0]["name"] == "Amount"
    assert columns[0]["type"] == "integer"
    assert columns[0]["sampleValues"] == ["12"]
    assert columns[1]["name"] == "Division"
    assert columns[1]["sampleValues"] == ["North", "South"]


@pytest.mark.parametrize(
    "cells",
    [
        '<c r="B1"><v>1</v></c><c r="A1"><v>2</v></c>',
        '<c r="A1"><v>1</v></c><c r="A1"><v>2</v></c>',
        '<c r="A1"><v>1</v></c><c><v>2</v></c>',
        '<c r="A2"><v>1</v></c>',
        '<c r="IW1"><v>1</v></c>',
        '<c r="1A"><v>1</v></c>',
    ],
)
def test_xlsx_rejects_ambiguous_or_invalid_cell_coordinates(cells: str) -> None:
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData><row r="1">{cells}</row></sheetData></worksheet>'
    )
    with pytest.raises(EvidenceError):
        parse_evidence(workbook_with_sheet(sheet), "invalid-coordinates.xlsx")


def test_local_store_is_private_and_integrity_bound(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "objects", "test")
    key, digest = store.write(uuid4(), uuid4(), b"bounded evidence")
    assert store.read(key, digest) == b"bounded evidence"
    target = store.root / key
    target.write_bytes(b"tampered")
    with pytest.raises(EvidenceError):
        store.read(key, digest)


def test_local_store_rejects_symlink_root(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="private real directory"):
        LocalEvidenceStore(linked, "test")


def test_local_store_rejects_symlink_objects_and_intermediate_directories(
    tmp_path: Path,
) -> None:
    store = LocalEvidenceStore(tmp_path / "objects", "test")
    company_id, case_id = uuid4(), uuid4()
    key, digest = store.write(company_id, case_id, b"bounded evidence")
    target = store.root / key
    linked_key = f"{company_id}/{case_id}/linked.bin"
    (store.root / linked_key).symlink_to(target.name)
    with pytest.raises(EvidenceError, match="unavailable"):
        store.read(linked_key, digest)
    with pytest.raises(EvidenceError, match="unsafe"):
        store.delete(linked_key)

    linked_company = uuid4()
    alternate = store.root / "alternate"
    alternate.mkdir()
    (store.root / str(linked_company)).symlink_to(alternate, target_is_directory=True)
    with pytest.raises(EvidenceError, match="unsafe"):
        store.write(linked_company, uuid4(), b"must not follow a directory link")


def test_failed_evidence_record_does_not_leave_an_eligible_orphan(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = sign_in(client, "member")
    case = client.post(
        "/api/cases",
        json={"request_text": "Inspect a bounded evidence write."},
        headers={**csrf(session), "Idempotency-Key": "orphan-cleanup-case"},
    ).json()["case"]
    before = {path for path in settings.evidence_root.rglob("*.bin")}

    def fail_record(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("simulated persistence failure")

    monkeypatch.setattr(ApplicationSession, "add_evidence", fail_record)
    with pytest.raises(RuntimeError, match="simulated persistence failure"):
        client.post(
            f"/api/cases/{case['id']}/evidence",
            params={"filename": "bounded.csv", "expected_context_version": 1},
            content=b"Category,Value\nOne,1\n",
            headers={**csrf(session), "Content-Type": "application/octet-stream"},
        )
    assert {path for path in settings.evidence_root.rglob("*.bin")} == before


def test_upload_stream_rejects_actual_bytes_beyond_limit_despite_small_header(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    case = client.post(
        "/api/cases",
        json={"request_text": "Inspect bounded streamed evidence."},
        headers={**csrf(session), "Idempotency-Key": "bounded-stream-case"},
    ).json()["case"]
    oversized = b"A" * 5_000_001
    response = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "oversized.csv", "expected_context_version": 1},
        content=oversized,
        headers={
            **csrf(session),
            "Content-Type": "application/octet-stream",
            "Content-Length": "1",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EVIDENCE_INVALID"
