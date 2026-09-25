from __future__ import annotations

import io
import warnings
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


def test_csv_rejects_populated_cells_without_headers_and_preserves_valid_rows() -> None:
    with pytest.raises(EvidenceError, match="without corresponding headers"):
        parse_evidence(b'Division,Amount\nNorth,12,"unheaded value"\n', "unsafe.csv")

    parsed = parse_evidence(
        b'Division,Description,Amount\nNorth,"quoted, value",12\nSouth,,\nWest\n',
        "valid.csv",
    )
    table = parsed.observed_schema["tables"][0]
    assert table["rowCount"] == 3
    assert table["columns"][1]["sampleValues"] == ["quoted, value"]


def test_xlsx_archive_rejects_traversal_and_external_content() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../escape", "unsafe")
        archive.writestr("xl/workbook.xml", "<workbook/>")
    with pytest.raises(EvidenceError):
        parse_evidence(output.getvalue(), "unsafe.xlsx")


def test_xlsx_missing_workbook_relationships_is_a_controlled_rejection() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
    with pytest.raises(EvidenceError, match="incomplete or malformed"):
        parse_evidence(output.getvalue(), "missing-relationships.xlsx")


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


def workbook_with_shared_strings(*, header_index: str, value_index: str | None) -> bytes:
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
        '<Relationship Id="rId2" Target="sharedStrings.xml" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
        'sharedStrings"/></Relationships>'
    )
    value_element = "" if value_index is None else f"<v>{value_index}</v>"
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData><row r="1"><c r="A1" t="s"><v>{header_index}</v></c></row>'
        f'<row r="2"><c r="A2" t="s">{value_element}</c></row>'
        "</sheetData></worksheet>"
    )
    shared_strings = (
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'count="4" uniqueCount="4"><si><t>Category</t></si><si><t>Region</t></si>'
        '<si><t>North</t></si><si><t>South</t></si></sst>'
    )
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        archive.writestr("xl/sharedStrings.xml", shared_strings)
    return output.getvalue()


def workbook_with_duplicate_shared_strings() -> bytes:
    source_bytes = workbook_with_shared_strings(header_index="0", value_index="2")
    output = io.BytesIO()
    duplicate = (
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'count="2" uniqueCount="2"><si><t>InjectedHeader</t></si>'
        '<si><t>InjectedValue</t></si></sst>'
    )
    with (
        zipfile.ZipFile(io.BytesIO(source_bytes)) as source,
        zipfile.ZipFile(output, "w") as target,
    ):
        for item in source.infolist():
            target.writestr(item, source.read(item.filename))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            target.writestr("xl/sharedStrings.xml", duplicate)
    return output.getvalue()


def workbook_with_duplicate_relationship_ids() -> bytes:
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
        '<Relationship Id="rId1" Target="worksheets/sheet2.xml" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
        "</Relationships>"
    )
    valid_sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row><c t="inlineStr"><is><t>Category</t></is></c></row>'
        '<row><c t="inlineStr"><is><t>North</t></is></c></row></sheetData></worksheet>'
    )
    injected_sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row><c t="inlineStr"><is><t>InjectedHeader</t></is></c></row>'
        '<row><c t="inlineStr"><is><t>InjectedValue</t></is></c></row></sheetData>'
        "</worksheet>"
    )
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", valid_sheet)
        archive.writestr("xl/worksheets/sheet2.xml", injected_sheet)
    return output.getvalue()


@pytest.mark.parametrize(
    ("header_index", "value_index", "expected_header", "expected_value"),
    [("0", "2", "Category", "North"), ("1", "3", "Region", "South")],
)
def test_xlsx_resolves_valid_non_negative_shared_string_indexes(
    header_index: str,
    value_index: str,
    expected_header: str,
    expected_value: str,
) -> None:
    parsed = parse_evidence(
        workbook_with_shared_strings(
            header_index=header_index,
            value_index=value_index,
        ),
        "shared-strings.xlsx",
    )
    column = parsed.observed_schema["tables"][0]["columns"][0]
    assert column["name"] == expected_header
    assert column["sampleValues"] == [expected_value]


@pytest.mark.parametrize(
    "invalid_index",
    ["-1", "4", "not-an-integer", "²", "9" * 5_000, "", None],
)
def test_xlsx_rejects_invalid_shared_string_indexes(invalid_index: str | None) -> None:
    with pytest.raises(EvidenceError, match="shared strings are malformed"):
        parse_evidence(
            workbook_with_shared_strings(header_index="0", value_index=invalid_index),
            "invalid-shared-string.xlsx",
        )


def test_xlsx_rejects_duplicate_package_parts() -> None:
    with pytest.raises(EvidenceError, match="archive containment or resource limits failed"):
        parse_evidence(
            workbook_with_duplicate_shared_strings(),
            "duplicate-shared-strings.xlsx",
        )


def test_xlsx_rejects_duplicate_relationship_ids() -> None:
    with pytest.raises(EvidenceError, match="relationships are malformed"):
        parse_evidence(
            workbook_with_duplicate_relationship_ids(),
            "duplicate-relationship-ids.xlsx",
        )


def workbook_with_formula_attribute() -> bytes:
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Amount</t></is></c>'
        '</row><row r="2"><c r="A2"><v>42</v></c></row></sheetData></worksheet>'
    )
    base = workbook_with_sheet(sheet)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base)) as source, zipfile.ZipFile(output, "w") as target:
        for item in source.infolist():
            if item.filename != "xl/_rels/workbook.xml.rels":
                target.writestr(item, source.read(item.filename))
        relationships = source.read("xl/_rels/workbook.xml.rels").decode().replace(
            "</Relationships>",
            '<Relationship Id="rIdPivot" Target="pivotCache/pivotCacheDefinition1.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'pivotCacheDefinition"/></Relationships>',
        )
        target.writestr("xl/_rels/workbook.xml.rels", relationships)
        target.writestr(
            "xl/pivotCache/pivotCacheDefinition1.xml",
            '<pivotCacheDefinition xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main"><cacheFields count="1"><cacheField '
            'name="Calculated" formula="WEBSERVICE(&quot;https://example.invalid/value&quot;)"/>'
            "</cacheFields></pivotCacheDefinition>",
        )
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


def test_xlsx_rejects_populated_position_beyond_header_columns() -> None:
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Amount</t></is></c>'
        '<c r="B1" t="inlineStr"><is><t>Division</t></is></c></row>'
        '<row r="2"><c r="A2"><v>12</v></c>'
        '<c r="C2" t="inlineStr"><is><t>unheaded value</t></is></c></row>'
        "</sheetData></worksheet>"
    )
    with pytest.raises(EvidenceError, match="without corresponding headers"):
        parse_evidence(workbook_with_sheet(sheet), "unsafe.xlsx")


def test_xlsx_rejects_formula_cells_instead_of_trusting_cached_values() -> None:
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Amount</t></is></c>'
        '<c r="B1" t="inlineStr"><is><t>Division</t></is></c></row>'
        '<row r="2"><c r="A2"><f>WEBSERVICE("https://example.invalid/value")</f>'
        '<v>42</v></c><c r="B2" t="inlineStr"><is><t>North</t></is></c></row>'
        "</sheetData></worksheet>"
    )
    with pytest.raises(EvidenceError, match="formulas are unsupported"):
        parse_evidence(workbook_with_sheet(sheet), "formula.xlsx")


def test_xlsx_rejects_defined_name_and_unreferenced_worksheet_formulas() -> None:
    static_sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Amount</t></is></c>'
        '</row><row r="2"><c r="A2"><v>42</v></c></row></sheetData></worksheet>'
    )
    base = workbook_with_sheet(static_sheet)

    defined_name = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base)) as source, zipfile.ZipFile(
        defined_name, "w"
    ) as target:
        for item in source.infolist():
            if item.filename != "xl/workbook.xml":
                target.writestr(item, source.read(item.filename))
        target.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<definedNames><definedName name="ExternalValue">'
            'WEBSERVICE("https://example.invalid/value")</definedName></definedNames>'
            '<sheets><sheet name="Observed" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>",
        )
    with pytest.raises(EvidenceError, match="formulas are unsupported"):
        parse_evidence(defined_name.getvalue(), "defined-name.xlsx")

    orphan = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base)) as source, zipfile.ZipFile(orphan, "w") as target:
        for item in source.infolist():
            target.writestr(item, source.read(item.filename))
        target.writestr(
            "xl/worksheets/orphan.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1"><c r="A1"><f>SUM(40,2)</f><v>42</v></c></row>'
            "</sheetData></worksheet>",
        )
    with pytest.raises(EvidenceError, match="formulas are unsupported"):
        parse_evidence(orphan.getvalue(), "orphan-formula.xlsx")


@pytest.mark.parametrize("formula_element", ["formula", "formula1", "formula2"])
def test_xlsx_rejects_validation_and_conditional_formula_forms(
    formula_element: str,
) -> None:
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Amount</t></is></c>'
        '</row><row r="2"><c r="A2"><v>42</v></c></row></sheetData>'
        '<dataValidations count="1"><dataValidation type="custom" sqref="A2">'
        f'<{formula_element}>WEBSERVICE("https://example.invalid/value")'
        f'</{formula_element}>'
        '</dataValidation></dataValidations></worksheet>'
    )
    with pytest.raises(EvidenceError, match="formulas are unsupported"):
        parse_evidence(workbook_with_sheet(sheet), f"{formula_element}.xlsx")


def test_xlsx_rejects_formula_bearing_attributes_in_reachable_parts() -> None:
    with pytest.raises(EvidenceError, match="formulas are unsupported"):
        parse_evidence(workbook_with_formula_attribute(), "pivot-formula.xlsx")


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


def test_rejected_unheaded_upload_preserves_existing_valid_evidence(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    case = client.post(
        "/api/cases",
        json={"request_text": "Inspect a bounded evidence write."},
        headers={**csrf(session), "Idempotency-Key": "unheaded-upload-case"},
    ).json()["case"]
    valid = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "valid.csv", "expected_context_version": 1},
        content=b"Category,Value\nOne,1\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert valid.status_code == 200
    context_version = valid.json()["evidence"]["semantic_context_version"]

    rejected = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "unsafe.csv", "expected_context_version": context_version},
        content=b"Category,Value\nTwo,2,unheaded\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "EVIDENCE_INVALID"

    malformed_workbook = io.BytesIO()
    with zipfile.ZipFile(malformed_workbook, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
    malformed = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={
            "filename": "missing-relationships.xlsx",
            "expected_context_version": context_version,
        },
        content=malformed_workbook.getvalue(),
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "EVIDENCE_INVALID"

    formula_sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Amount</t></is></c>'
        '<c r="B1" t="inlineStr"><is><t>Division</t></is></c></row>'
        '<row r="2"><c r="A2"><f>SUM(40,2)</f><v>42</v></c>'
        '<c r="B2" t="inlineStr"><is><t>North</t></is></c></row>'
        "</sheetData></worksheet>"
    )
    formula = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "formula.xlsx", "expected_context_version": context_version},
        content=workbook_with_sheet(formula_sheet),
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert formula.status_code == 422
    assert formula.json()["error"]["code"] == "EVIDENCE_INVALID"

    static_workbook = workbook_with_sheet(
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Amount</t></is></c>'
        '</row><row r="2"><c r="A2"><v>42</v></c></row></sheetData></worksheet>'
    )
    defined_name_workbook = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(static_workbook)) as source, zipfile.ZipFile(
        defined_name_workbook, "w"
    ) as target:
        for item in source.infolist():
            if item.filename != "xl/workbook.xml":
                target.writestr(item, source.read(item.filename))
        target.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<definedNames><definedName name="ExternalValue">'
            'WEBSERVICE("https://example.invalid/value")</definedName></definedNames>'
            '<sheets><sheet name="Observed" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>",
        )
    defined_name = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "defined-name.xlsx", "expected_context_version": context_version},
        content=defined_name_workbook.getvalue(),
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert defined_name.status_code == 422
    assert defined_name.json()["error"]["code"] == "EVIDENCE_INVALID"

    validation_sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Amount</t></is></c>'
        '</row><row r="2"><c r="A2"><v>42</v></c></row></sheetData>'
        '<dataValidations count="1"><dataValidation type="custom" sqref="A2">'
        '<formula1>WEBSERVICE("https://example.invalid/value")</formula1>'
        '</dataValidation></dataValidations></worksheet>'
    )
    validation_formula = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "validation-formula.xlsx", "expected_context_version": context_version},
        content=workbook_with_sheet(validation_sheet),
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert validation_formula.status_code == 422
    assert validation_formula.json()["error"]["code"] == "EVIDENCE_INVALID"
    attribute_formula = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "pivot-formula.xlsx", "expected_context_version": context_version},
        content=workbook_with_formula_attribute(),
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert attribute_formula.status_code == 422
    assert attribute_formula.json()["error"]["code"] == "EVIDENCE_INVALID"
    listed = client.get(f"/api/cases/{case['id']}/evidence")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [
        valid.json()["evidence"]["id"]
    ]
    assert client.get(f"/api/cases/{case['id']}").json()["case"][
        "semantic_context_version"
    ] == context_version


def test_rejected_shared_string_upload_preserves_case_history_and_acceptance(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    created = client.post(
        "/api/cases",
        json={"request_text": "Create a report of total amount by division."},
        headers={**csrf(session), "Idempotency-Key": "shared-string-rejection-case"},
    )
    assert created.status_code == 201
    case = created.json()["case"]
    uploaded = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "valid.csv", "expected_context_version": 1},
        content=b"Amount,Division\n12,North\n",
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert uploaded.status_code == 200
    context_version = uploaded.json()["evidence"]["semantic_context_version"]
    interpretation = client.post(
        f"/api/cases/{case['id']}/interpretations",
        json={"expected_context_version": context_version},
        headers=csrf(session),
    )
    assert interpretation.status_code == 200
    interpretation_id = interpretation.json()["interpretation"]["id"]
    confirmed = client.post(
        f"/api/cases/{case['id']}/confirm",
        json={
            "interpretation_id": interpretation_id,
            "expected_context_version": context_version,
        },
        headers=csrf(session),
    )
    assert confirmed.status_code == 200

    before_case = client.get(f"/api/cases/{case['id']}").json()
    before_evidence = client.get(f"/api/cases/{case['id']}/evidence").json()
    before_conversation = client.get(f"/api/cases/{case['id']}/conversation").json()
    before_acceptance = client.get(f"/api/cases/{case['id']}/acceptance").json()

    for suffix, content in (
        (
            "negative",
            workbook_with_shared_strings(header_index="0", value_index="-1"),
        ),
        (
            "oversized",
            workbook_with_shared_strings(header_index="0", value_index="9" * 5_000),
        ),
        (
            "empty",
            workbook_with_shared_strings(header_index="0", value_index=None),
        ),
        ("duplicate-part", workbook_with_duplicate_shared_strings()),
        ("duplicate-relationship", workbook_with_duplicate_relationship_ids()),
    ):
        rejected = client.post(
            f"/api/cases/{case['id']}/evidence",
            params={
                "filename": f"{suffix}-shared-string.xlsx",
                "expected_context_version": context_version,
            },
            content=content,
            headers={**csrf(session), "Content-Type": "application/octet-stream"},
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "EVIDENCE_INVALID"

    assert client.get(f"/api/cases/{case['id']}").json() == before_case
    assert client.get(f"/api/cases/{case['id']}/evidence").json() == before_evidence
    assert client.get(f"/api/cases/{case['id']}/conversation").json() == before_conversation
    assert client.get(f"/api/cases/{case['id']}/acceptance").json() == before_acceptance

    replay = client.post(
        f"/api/cases/{case['id']}/confirm",
        json={
            "interpretation_id": interpretation_id,
            "expected_context_version": context_version,
        },
        headers=csrf(session),
    )
    assert replay.status_code == 200
    assert replay.json()["confirmed_contract"] == confirmed.json()["confirmed_contract"]


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
