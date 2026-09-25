from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import posixpath
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote
from uuid import UUID, uuid4
from xml.etree.ElementTree import Element

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

MAX_EVIDENCE_BYTES = 5_000_000
MAX_ARCHIVE_ENTRIES = 200
MAX_UNCOMPRESSED_BYTES = 25_000_000
MAX_ROWS = 5_000
MAX_COLUMNS = 256
MAX_CELL_CHARACTERS = 10_000
CELL_REFERENCE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
SUPPORTED_RELATIONSHIP_TYPE_NAMES = {
    "officedocument",
    "core-properties",
    "extended-properties",
    "thumbnail",
    "worksheet",
    "styles",
    "theme",
    "sharedstrings",
    "calcchain",
    "drawing",
    "image",
    "comments",
    "threadedcomment",
    "person",
    "table",
    "hyperlink",
    "pivottable",
    "pivotcachedefinition",
    "pivotcacherecords",
    "metadata",
    "richvaluerel",
}


class EvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedEvidence:
    format: str
    observed_schema: dict[str, Any]


def _value_type(values: list[str]) -> str:
    filled = [value for value in values if value]
    if not filled:
        return "text"
    if all(value.lstrip("-").isdigit() for value in filled):
        return "integer"
    try:
        for value in filled:
            float(value)
        return "decimal"
    except ValueError:
        return "text"


def _table(name: str, rows: list[list[str]]) -> dict[str, Any]:
    if not rows or not any(cell.strip() for cell in rows[0]):
        raise EvidenceError("Evidence must contain a non-empty header row.")
    headers = [cell.strip() for cell in rows[0]]
    if len(headers) > MAX_COLUMNS or any(not header for header in headers):
        raise EvidenceError("Evidence headers are missing or exceed the supported limit.")
    if len(set(headers)) != len(headers):
        raise EvidenceError("Evidence headers must be unique.")
    if any(any(cell.strip() for cell in row[len(headers) :]) for row in rows[1:]):
        raise EvidenceError("Evidence contains populated cells without corresponding headers.")
    data = [row[: len(headers)] + [""] * max(0, len(headers) - len(row)) for row in rows[1:]]
    if len(data) > MAX_ROWS:
        raise EvidenceError("Evidence exceeds the supported row limit.")
    if any(len(cell) > MAX_CELL_CHARACTERS for row in rows for cell in row):
        raise EvidenceError("Evidence contains a cell exceeding the supported limit.")
    return {
        "name": name,
        "rowCount": len(data),
        "columns": [
            {
                "name": header,
                "type": _value_type([row[index] for row in data]),
                "nullable": any(not row[index] for row in data),
                "sampleValues": list(dict.fromkeys(row[index] for row in data if row[index]))[:3],
            }
            for index, header in enumerate(headers)
        ],
    }


def _parse_csv(content: bytes, filename: str) -> ParsedEvidence:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EvidenceError("CSV evidence must be UTF-8 encoded.") from exc
    if "\x00" in text:
        raise EvidenceError("CSV evidence contains unsupported binary content.")
    try:
        rows = [[str(cell) for cell in row] for row in csv.reader(io.StringIO(text), strict=True)]
    except csv.Error as exc:
        raise EvidenceError("CSV evidence is malformed.") from exc
    table_name = Path(filename).stem or "Data"
    return ParsedEvidence(
        "CSV", {"kind": "REQUEST_DATA_STRUCTURE", "tables": [_table(table_name, rows)]}
    )


def _xml(data: bytes) -> Element:
    try:
        # Input size is archive-bounded; the parser rejects DTDs, entities, and
        # external references independently of the XML byte encoding.
        return ElementTree.fromstring(
            data, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except DefusedXmlException as exc:
        raise EvidenceError("Spreadsheet XML declarations are not supported.") from exc
    except ElementTree.ParseError as exc:
        raise EvidenceError("Spreadsheet XML is malformed.") from exc


def _relationship_target(
    relationship_name: str,
    target: str,
    relationship_type_name: str,
    archive_names: set[str],
) -> str | None:
    relationship_path = PurePosixPath(relationship_name)
    parts = relationship_path.parts
    if (
        len(parts) < 2
        or parts[-2] != "_rels"
        or not parts[-1].lower().endswith(".rels")
    ):
        raise EvidenceError("Workbook relationship location is malformed.")
    path_part, separator, fragment = target.partition("#")
    if not path_part:
        if relationship_type_name == "hyperlink" and separator and fragment:
            return None
        raise EvidenceError("Workbook relationship target is malformed.")
    decoded = unquote(path_part)
    if (
        "\\" in decoded
        or decoded.startswith("/")
        or URI_SCHEME.match(decoded)
        or "?" in decoded
    ):
        raise EvidenceError("Workbook relationship target is not package-contained.")
    base = PurePosixPath(*parts[:-2]).as_posix()
    if base == ".":
        base = ""
    resolved = posixpath.normpath(posixpath.join(base, decoded))
    if resolved in {"", ".", ".."} or resolved.startswith("../") or resolved not in archive_names:
        raise EvidenceError("Workbook relationship target is not package-contained.")
    return resolved


def _cell_coordinate(reference: str) -> tuple[int, int]:
    match = CELL_REFERENCE.fullmatch(reference)
    if match is None:
        raise EvidenceError("Workbook cell coordinates are malformed.")
    column = 0
    for letter in match.group(1):
        column = column * 26 + (ord(letter) - ord("A") + 1)
        if column > MAX_COLUMNS:
            raise EvidenceError("Workbook cell coordinates exceed the supported column limit.")
    return column - 1, int(match.group(2))


def _parse_xlsx(content: bytes) -> ParsedEvidence:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise EvidenceError("XLSX evidence is not a valid workbook.") from exc
    with archive:
        infos = archive.infolist()
        names = {item.filename for item in infos}
        if (
            len(infos) > MAX_ARCHIVE_ENTRIES
            or sum(item.file_size for item in infos) > MAX_UNCOMPRESSED_BYTES
            or any(
                item.filename.startswith("/")
                or ".." in Path(item.filename).parts
                or stat.S_ISLNK(item.external_attr >> 16)
                for item in infos
            )
        ):
            raise EvidenceError("Workbook archive containment or resource limits failed.")
        forbidden = {
            name
            for name in names
            if name.lower().endswith(
                (
                    ".bin",
                    ".exe",
                    ".dll",
                    ".com",
                    ".scr",
                    ".js",
                    ".vbs",
                    ".ps1",
                    ".bat",
                    ".cmd",
                )
            )
            or name.lower().startswith(
                (
                    "xl/externallinks/",
                    "xl/embeddings/",
                    "xl/activex/",
                    "xl/ctrlprops/",
                    "customui/",
                )
            )
        }
        if forbidden:
            raise EvidenceError(
                "Macros, executable content, or external workbook links are unsupported."
            )
        required_parts = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
        if not required_parts.issubset(names):
            raise EvidenceError("Workbook structure is incomplete or malformed.")

        formula_parts = {
            name
            for name in names
            if name.lower().endswith(".xml") and name.lower().startswith("xl/")
        }
        formula_element_names = {
            "f",
            "formula",
            "formula1",
            "formula2",
            "definedname",
            "calculatedcolumnformula",
            "totalsrowformula",
        }
        for formula_part in sorted(formula_parts):
            formula_root = _xml(archive.read(formula_part))
            if any(
                node.tag.rsplit("}", 1)[-1].lower() in formula_element_names
                or any(
                    attribute.rsplit("}", 1)[-1].lower() in formula_element_names
                    for attribute in node.attrib
                )
                for node in formula_root.iter()
            ):
                raise EvidenceError(
                    "Workbook formulas are unsupported as observed evidence."
                )

        for relationship_name in (name for name in names if name.lower().endswith(".rels")):
            relationship_root = _xml(archive.read(relationship_name))
            for relationship in relationship_root.findall("{*}Relationship"):
                target = relationship.attrib.get("Target", "").strip()
                target_mode = relationship.attrib.get("TargetMode", "").strip().lower()
                relationship_type = relationship.attrib.get("Type", "").strip().lower()
                relationship_type_name = relationship_type.rsplit("/", 1)[-1]
                if (
                    target_mode == "external"
                    or relationship_type_name not in SUPPORTED_RELATIONSHIP_TYPE_NAMES
                ):
                    raise EvidenceError(
                        "Active, executable, external, or unsupported workbook relationships "
                        "are not eligible evidence."
                    )
                _relationship_target(
                    relationship_name, target, relationship_type_name, names
                )

        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = _xml(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in root.findall("{*}si")]

        workbook = _xml(archive.read("xl/workbook.xml"))
        relationships = _xml(archive.read("xl/_rels/workbook.xml.rels"))
        targets: dict[str, str] = {}
        for item in relationships.findall("{*}Relationship"):
            relationship_type = item.attrib.get("Type", "")
            if relationship_type.endswith("/worksheet"):
                targets[item.attrib.get("Id", "")] = item.attrib.get("Target", "")
        tables: list[dict[str, Any]] = []
        for sheet in workbook.findall(".//{*}sheet"):
            relation = sheet.attrib.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", ""
            )
            target = targets.get(relation, "")
            if (
                not target
                or target.startswith(("/", "http:", "https:"))
                or ".." in Path(target).parts
            ):
                raise EvidenceError("Workbook sheet relationships are unsafe or malformed.")
            path = target if target.startswith("xl/") else f"xl/{target.lstrip('/')}"
            if path not in names:
                raise EvidenceError("Workbook sheet data is missing.")
            root = _xml(archive.read(path))
            rows: list[list[str]] = []
            previous_row_number = 0
            for sequential_row_number, row_node in enumerate(
                root.findall(".//{*}sheetData/{*}row"), start=1
            ):
                cells = row_node.findall("{*}c")
                references = [cell.attrib.get("r") for cell in cells]
                if any(reference is None for reference in references) and any(
                    reference is not None for reference in references
                ):
                    raise EvidenceError(
                        "Workbook rows cannot mix positioned and unpositioned cells."
                    )
                declared_row = row_node.attrib.get("r")
                if declared_row is not None and (
                    not declared_row.isdigit() or int(declared_row) < 1
                ):
                    raise EvidenceError("Workbook row coordinates are malformed.")
                row_number = (
                    int(declared_row) if declared_row is not None else sequential_row_number
                )
                if declared_row is None and references and references[0] is not None:
                    _first_column, row_number = _cell_coordinate(references[0])
                row: list[str] = []
                previous_column = -1
                for cell, reference in zip(cells, references, strict=True):
                    if reference is None:
                        column_index = previous_column + 1
                    else:
                        column_index, cell_row_number = _cell_coordinate(reference)
                        if cell_row_number != row_number:
                            raise EvidenceError("Workbook cell and row coordinates disagree.")
                    if column_index <= previous_column:
                        raise EvidenceError(
                            "Workbook cell coordinates are duplicated or out of order."
                        )
                    row.extend([""] * (column_index - len(row)))
                    value_node = cell.find("{*}v")
                    value = "" if value_node is None or value_node.text is None else value_node.text
                    if cell.attrib.get("t") == "s":
                        if not value or not value.isascii() or not value.isdigit():
                            raise EvidenceError("Workbook shared strings are malformed.")
                        normalized_index = value.lstrip("0") or "0"
                        maximum_index = str(len(shared) - 1)
                        if (
                            not shared
                            or len(normalized_index) > len(maximum_index)
                            or (
                                len(normalized_index) == len(maximum_index)
                                and normalized_index > maximum_index
                            )
                        ):
                            raise EvidenceError("Workbook shared strings are malformed.")
                        value = shared[int(normalized_index)]
                    elif cell.attrib.get("t") == "inlineStr":
                        value = "".join(cell.itertext())
                    row.append(value)
                    previous_column = column_index
                if row_number <= previous_row_number:
                    raise EvidenceError("Workbook row coordinates are duplicated or out of order.")
                previous_row_number = row_number
                rows.append(row)
                if len(rows) > MAX_ROWS + 1:
                    raise EvidenceError("Evidence exceeds the supported row limit.")
            if rows:
                tables.append(_table(sheet.attrib.get("name", "Sheet"), rows))
        if not tables:
            raise EvidenceError("Workbook contains no supported worksheet data.")
        return ParsedEvidence("XLSX", {"kind": "REQUEST_DATA_STRUCTURE", "tables": tables})


def parse_evidence(content: bytes, filename: str) -> ParsedEvidence:
    if not content or len(content) > MAX_EVIDENCE_BYTES:
        raise EvidenceError("Evidence is empty or exceeds the 5 MB development limit.")
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return _parse_csv(content, filename)
    if suffix == ".xlsx":
        return _parse_xlsx(content)
    raise EvidenceError("Only CSV and XLSX evidence is supported.")


class LocalEvidenceStore:
    def __init__(self, root: Path, profile: str) -> None:
        if profile not in {"development", "test"}:
            raise ValueError("The private local evidence adapter is local/CI-only.")
        if root.is_symlink():
            raise ValueError("Evidence root must be a private real directory.")
        self.root = root.resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError("Evidence root must be a private real directory.")

    @staticmethod
    def _storage_parts(storage_key: str) -> tuple[str, str, str]:
        parts = tuple(storage_key.split("/"))
        if len(parts) != 3 or any(not part or part in {".", ".."} for part in parts):
            raise EvidenceError("Evidence object path is unsafe.")
        return parts[0], parts[1], parts[2]

    def _open_directory(self, parts: tuple[str, ...], *, create: bool) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            descriptor = os.open(self.root, flags)
        except OSError as exc:
            raise EvidenceError("Evidence object path is unsafe.") from exc
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
            raise EvidenceError("Evidence object path is unsafe.") from exc

    def write(self, company_id: UUID, case_id: UUID, content: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(content).hexdigest()
        company = str(company_id)
        case = str(case_id)
        directory_descriptor = self._open_directory((company, case), create=True)
        key = f"{uuid4().hex}.bin"
        try:
            descriptor = os.open(
                key,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=directory_descriptor,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            try:
                os.unlink(key, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass
            raise
        finally:
            os.close(directory_descriptor)
        return f"{company}/{case}/{key}", digest

    def read(self, storage_key: str, expected_digest: str) -> bytes:
        company, case, key = self._storage_parts(storage_key)
        directory_descriptor = self._open_directory((company, case), create=False)
        try:
            descriptor = os.open(
                key, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory_descriptor
            )
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                raise EvidenceError("Evidence object is unavailable.")
            with os.fdopen(descriptor, "rb") as stream:
                content = stream.read(MAX_EVIDENCE_BYTES + 1)
        except OSError as exc:
            raise EvidenceError("Evidence object is unavailable.") from exc
        finally:
            os.close(directory_descriptor)
        if len(content) > MAX_EVIDENCE_BYTES:
            raise EvidenceError("Evidence object exceeds the supported size limit.")
        if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), expected_digest):
            raise EvidenceError("Evidence integrity verification failed.")
        return content

    def restore(self, storage_key: str, content: bytes, expected_digest: str) -> None:
        """Atomically restore the exact immutable object named by an evidence record."""
        if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), expected_digest):
            raise EvidenceError("Evidence recovery bytes do not match the retained identity.")
        company, case, key = self._storage_parts(storage_key)
        directory_descriptor = self._open_directory((company, case), create=False)
        temporary_key = f".{uuid4().hex}.recovering"
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
            try:
                existing = os.stat(key, dir_fd=directory_descriptor, follow_symlinks=False)
                if not stat.S_ISREG(existing.st_mode):
                    raise EvidenceError("Evidence recovery target is unsafe.")
            except FileNotFoundError:
                pass
            os.replace(
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

    def delete(self, storage_key: str) -> None:
        company, case, key = self._storage_parts(storage_key)
        directory_descriptor = self._open_directory((company, case), create=False)
        try:
            object_stat = os.stat(key, dir_fd=directory_descriptor, follow_symlinks=False)
            if not stat.S_ISREG(object_stat.st_mode):
                raise EvidenceError("Evidence object path is unsafe.")
            os.unlink(key, dir_fd=directory_descriptor)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise EvidenceError("Evidence object path is unsafe.") from exc
        finally:
            os.close(directory_descriptor)


def schema_digest(schema: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
