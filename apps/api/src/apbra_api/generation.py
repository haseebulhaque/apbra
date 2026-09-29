from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import selectors
import subprocess
import threading
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from .artifacts import ArtifactError, LocalArtifactStore
from .authorization import authorized_case_access
from .domain import (
    Actor,
    ApplicationPersistence,
    ArtifactUnavailable,
    Conflict,
    GenerationAttemptRecord,
    GenerationFailed,
    GenerationUnavailable,
    IdempotencyConflict,
    ProtectedResourceNotFound,
    ReviewedDesignRequired,
    ReviewedReportDesignRecord,
    Role,
    StaleVersion,
)
from .evidence import (
    EvidenceError,
    LocalEvidenceStore,
    _cell_coordinate,
    _xml,
    parse_evidence,
    schema_digest,
)

MAX_BRIDGE_BYTES = 20_000_000
MAX_BRIDGE_EXECUTABLE_BYTES = 5_000_000
MAX_CANDIDATE_FILES = 500
MAX_CANDIDATE_TEXT = 5_000_000


def canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class GenerationBridge:
    """Bounded no-shell adapter to the canonical TypeScript generation pipeline."""

    def __init__(
        self,
        executable: Path,
        *,
        node_executable: Path,
        timeout_seconds: int,
    ) -> None:
        if not executable.is_file() or executable.is_symlink():
            raise ValueError("The generation bridge must be a fixed regular file.")
        try:
            resolved_node = node_executable.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError(
                "The generation bridge runtime must be an executable regular file."
            ) from exc
        if not resolved_node.is_file() or not os.access(resolved_node, os.X_OK):
            raise ValueError("The generation bridge runtime must be an executable regular file.")
        self.executable = executable.resolve()
        self.node_executable = resolved_node
        self.timeout_seconds = timeout_seconds
        if self.executable.stat().st_size > MAX_BRIDGE_EXECUTABLE_BYTES:
            raise ValueError("The generation bridge exceeds the fixed executable limit.")
        self.pipeline_digest = hashlib.sha256(self.executable.read_bytes()).hexdigest()

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not hmac.compare_digest(
            hashlib.sha256(self.executable.read_bytes()).hexdigest(), self.pipeline_digest
        ):
            raise GenerationFailed()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        if len(encoded) > MAX_BRIDGE_BYTES:
            raise GenerationFailed()
        process: subprocess.Popen[bytes] | None = None
        writer: threading.Thread | None = None
        writer_error: list[BaseException] = []
        try:
            process = subprocess.Popen(  # noqa: S603
                [str(self.node_executable), str(self.executable)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={
                    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                    "NODE_ENV": "production",
                },
            )
            assert process.stdin is not None and process.stdout is not None
            process_stdin = process.stdin

            def write_input() -> None:
                try:
                    process_stdin.write(encoded)
                    process_stdin.close()
                except (BrokenPipeError, OSError, ValueError) as exc:
                    writer_error.append(exc)

            writer = threading.Thread(target=write_input, daemon=True)
            writer.start()
            output = bytearray()
            deadline = time.monotonic() + self.timeout_seconds
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(
                            [str(self.node_executable), str(self.executable)],
                            self.timeout_seconds,
                        )
                    events = selector.select(remaining)
                    if not events:
                        raise subprocess.TimeoutExpired(
                            [str(self.node_executable), str(self.executable)],
                            self.timeout_seconds,
                        )
                    chunk = os.read(process.stdout.fileno(), 65_536)
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > MAX_BRIDGE_BYTES:
                        raise GenerationFailed()
            finally:
                selector.close()
            return_code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except (OSError, subprocess.TimeoutExpired, GenerationFailed) as exc:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            raise GenerationFailed() from exc
        finally:
            if process is not None:
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
                if process.stdout is not None:
                    process.stdout.close()
            if writer is not None:
                writer.join(timeout=1)
        if return_code != 0 or writer_error:
            raise GenerationFailed()
        try:
            response = json.loads(output)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise GenerationFailed() from exc
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise GenerationFailed()
        value = response.get("value")
        if not isinstance(value, dict):
            raise GenerationFailed()
        provenance = value.get("provenance")
        if (
            not isinstance(provenance, dict)
            or canonical_digest(provenance.get("binding"))
            != canonical_digest(payload.get("binding"))
            or canonical_digest(provenance.get("execution"))
            != canonical_digest(payload.get("execution"))
        ):
            raise GenerationFailed()
        files = value.get("files")
        validation = value.get("validation")
        if (
            not isinstance(files, dict)
            or not files
            or len(files) > MAX_CANDIDATE_FILES
            or not isinstance(validation, dict)
            or validation.get("status") != "PASS"
        ):
            raise GenerationFailed()
        for path, content in files.items():
            if (
                not isinstance(path, str)
                or not path
                or path.startswith("/")
                or ".." in Path(path).parts
                or "\\" in path
                or not isinstance(content, str)
                or len(content.encode()) > MAX_CANDIDATE_TEXT
            ):
                raise GenerationFailed()
        return value


def _xlsx_rows(content: bytes) -> list[tuple[str, list[list[str]]]]:
    """Materialize rows only after the shared evidence parser has qualified the bytes."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = {item.filename for item in archive.infolist()}
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            shared_root = _xml(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in shared_root.findall("{*}si")]
        workbook = _xml(archive.read("xl/workbook.xml"))
        relationships = _xml(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            item.attrib.get("Id", ""): item.attrib.get("Target", "")
            for item in relationships.findall("{*}Relationship")
            if item.attrib.get("Type", "").endswith("/worksheet")
        }
        result: list[tuple[str, list[list[str]]]] = []
        for sheet in workbook.findall(".//{*}sheet"):
            relation = sheet.attrib.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", ""
            )
            target = targets[relation]
            path = target if target.startswith("xl/") else f"xl/{target.lstrip('/')}"
            root = _xml(archive.read(path))
            rows: list[list[str]] = []
            for row_node in root.findall(".//{*}sheetData/{*}row"):
                row: list[str] = []
                for index, cell in enumerate(row_node.findall("{*}c")):
                    reference = cell.attrib.get("r")
                    column_index = _cell_coordinate(reference)[0] if reference else index
                    row.extend([""] * (column_index - len(row)))
                    value_node = cell.find("{*}v")
                    value = "" if value_node is None or value_node.text is None else value_node.text
                    if cell.attrib.get("t") == "s":
                        value = shared[int(value)]
                    elif cell.attrib.get("t") == "inlineStr":
                        value = "".join(cell.itertext())
                    row.append(value)
                rows.append(row)
            if rows:
                result.append((sheet.attrib.get("name", "Sheet"), rows))
        return result


def _evidence_tables(
    objects: LocalEvidenceStore, evidence: list[Any]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    tables: list[dict[str, Any]] = []
    bindings: list[dict[str, str]] = []
    names: set[str] = set()
    for row in evidence:
        content = objects.read(row.storage_key, row.content_digest)
        parsed = parse_evidence(content, row.filename)
        schema = json.loads(row.observed_schema_json)
        if (
            not isinstance(schema, dict)
            or parsed.format != row.format
            or not hmac.compare_digest(schema_digest(schema), row.schema_digest)
            or parsed.observed_schema != schema
        ):
            raise EvidenceError("Evidence qualification no longer matches retained bytes.")
        if parsed.format == "CSV":
            text = content.decode("utf-8-sig")
            materialized = [
                (Path(row.filename).stem or "Data", list(csv.reader(io.StringIO(text))))
            ]
        else:
            materialized = _xlsx_rows(content)
        schema_tables = schema.get("tables", [])
        if len(materialized) != len(schema_tables):
            raise EvidenceError("Evidence rows no longer match the qualified schema.")
        for (table_name, rows), table_schema in zip(materialized, schema_tables, strict=True):
            if table_name != table_schema.get("name") or not rows:
                raise EvidenceError("Evidence rows no longer match the qualified schema.")
            if table_name in names:
                raise EvidenceError("Qualified evidence table names must be unique.")
            names.add(table_name)
            headers = rows[0]
            columns = table_schema.get("columns", [])
            if headers != [column.get("name") for column in columns]:
                raise EvidenceError("Evidence headers no longer match the qualified schema.")
            normalized_rows = [
                row_values[: len(headers)] + [""] * max(0, len(headers) - len(row_values))
                for row_values in rows[1:]
            ]
            tables.append(
                {
                    "name": table_name,
                    "sourceName": table_name,
                    "rowCount": len(normalized_rows),
                    "rows": normalized_rows,
                    "columns": [
                        {
                            "name": column["name"],
                            "sourceName": column["name"],
                            "type": column["type"],
                            "nullable": column["nullable"],
                            "sampleValues": column["sampleValues"],
                        }
                        for column in columns
                    ],
                }
            )
        bindings.append(
            {
                "id": str(row.id),
                "contentDigest": row.content_digest,
                "schemaDigest": row.schema_digest,
            }
        )
    return tables, bindings


def _candidate_zip(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, files[path].encode("utf-8"))
    return output.getvalue()


def attempt_json(store: ApplicationPersistence, row: GenerationAttemptRecord) -> dict[str, Any]:
    artifact = store.generated_artifact(row.artifact_id) if row.artifact_id else None
    if artifact is not None and (
        artifact.attempt_id != row.id
        or artifact.case_id != row.case_id
        or artifact.company_id != row.company_id
    ):
        artifact = None
    return {
        "id": str(row.id),
        "case_id": str(row.case_id),
        "confirmed_contract_id": str(row.confirmed_contract_id),
        "reviewed_design_id": str(row.reviewed_design_id) if row.reviewed_design_id else None,
        "interpretation_id": str(row.interpretation_id),
        "request_version_id": str(row.request_version_id),
        "status": row.status,
        "attempt_number": row.attempt_number,
        "retry_of_attempt_id": str(row.retry_of_attempt_id) if row.retry_of_attempt_id else None,
        "supersedes_attempt_id": (
            str(row.supersedes_attempt_id) if row.supersedes_attempt_id else None
        ),
        "provenance": json.loads(row.provenance_json),
        "validation": json.loads(row.validation_json) if row.validation_json else None,
        "failure": (
            {"code": row.failure_code, "message": row.failure_reason} if row.failure_code else None
        ),
        "created_at": row.created_at.isoformat(),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "cancelled_at": row.cancelled_at.isoformat() if row.cancelled_at else None,
        "artifact": (
            {
                "id": str(artifact.id),
                "filename": artifact.filename,
                "content_digest": artifact.content_digest,
                "byte_size": artifact.byte_size,
                "validation_status": artifact.validation_status,
                "created_at": artifact.created_at.isoformat(),
            }
            if artifact is not None
            else None
        ),
    }


class GenerationService:
    def __init__(
        self,
        bridge: GenerationBridge | None,
        evidence_objects: LocalEvidenceStore,
        artifact_objects: LocalArtifactStore,
    ) -> None:
        self.bridge = bridge
        self.evidence_objects = evidence_objects
        self.artifact_objects = artifact_objects

    def _current_payload(
        self,
        store: ApplicationPersistence,
        actor: Actor,
        case_id: UUID,
        contract_id: UUID,
        *,
        lock_access: bool = False,
        require_edit: bool = True,
    ) -> tuple[dict[str, Any], str, str, Any, Any]:
        authorized_case_access(
            store, actor, case_id, require_edit=require_edit, lock=lock_access
        )
        case = store.locked_case(case_id)
        contract = store.confirmed_contract_for_case(case_id, contract_id)
        latest = store.latest_interpretation(case_id)
        if case is None or contract is None or latest is None:
            raise GenerationUnavailable()
        if (
            latest.id != contract.interpretation_id
            or latest.context_version != case.semantic_context_version
            or latest.request_version_id != case.current_request_version_id
        ):
            raise StaleVersion()
        evidence = [
            row
            for row in store.evidence_items(case_id)
            if row.request_version_id == case.current_request_version_id
        ]
        if not evidence:
            raise GenerationUnavailable()
        try:
            tables, bindings = _evidence_tables(self.evidence_objects, evidence)
            contract_value = json.loads(contract.contract_json)
        except (EvidenceError, json.JSONDecodeError) as exc:
            raise GenerationUnavailable() from exc
        data_structure = {
            "kind": "REQUEST_DATA_STRUCTURE",
            "fileName": "qualified-case-evidence",
            "format": "XLSX" if any(row.format == "XLSX" for row in evidence) else "CSV",
            "tables": tables,
            "relationships": [],
            "parsedAt": max(row.created_at for row in evidence).isoformat(),
        }
        evidence_digest = canonical_digest(bindings)
        payload = {
            "contract": contract_value,
            "dataStructure": data_structure,
            "binding": {
                "caseId": str(case.id),
                "requestVersionId": str(case.current_request_version_id),
                "semanticContextVersion": case.semantic_context_version,
                "interpretationId": str(latest.id),
                "confirmedContractId": str(contract.id),
                "evidence": bindings,
            },
        }
        return payload, canonical_digest(payload), evidence_digest, case, contract

    def history(self, db: object, actor: Actor, case_id: UUID) -> list[dict[str, Any]]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(store, actor, case_id)
        return [attempt_json(store, row) for row in store.generation_attempts(case_id)]

    def get(self, db: object, actor: Actor, case_id: UUID, attempt_id: UUID) -> dict[str, Any]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(store, actor, case_id)
        row = store.generation_attempt(case_id, attempt_id)
        if row is None:
            raise GenerationUnavailable()
        return attempt_json(store, row)

    def _eligible_design(
        self,
        store: ApplicationPersistence,
        actor: Actor,
        case_id: UUID,
        contract_id: UUID,
        design_id: UUID,
        payload: dict[str, Any],
        semantic_input_digest: str,
        evidence_digest: str,
        *,
        lock_access: bool = False,
    ) -> tuple[ReviewedReportDesignRecord, dict[str, Any]]:
        row = store.reviewed_design(case_id, design_id)
        if (
            row is None
            or row.company_id != actor.company_id
            or row.case_id != case_id
            or row.confirmed_contract_id != contract_id
            or row.interpretation_id != UUID(payload["binding"]["interpretationId"])
            or row.request_version_id != UUID(payload["binding"]["requestVersionId"])
            or row.semantic_context_version != payload["binding"]["semanticContextVersion"]
            or row.evidence_binding_digest != evidence_digest
            or row.semantic_input_digest != semantic_input_digest
            or not hmac.compare_digest(
                row.binding_digest, canonical_digest(payload["binding"])
            )
            or not hmac.compare_digest(
                row.binding_digest, hashlib.sha256(row.binding_json.encode()).hexdigest()
            )
            or row.reviewer_role != Role.EXPERT.value
        ):
            raise ReviewedDesignRequired()
        reviewer = store.active_actor(
            row.reviewer_membership_id, row.reviewer_identity_id, lock=lock_access
        )
        if (
            reviewer is None
            or reviewer.company_id != actor.company_id
            or reviewer.role != Role.EXPERT
        ):
            raise ReviewedDesignRequired()
        try:
            authorized_case_access(
                store, reviewer, case_id, require_edit=True, lock=lock_access
            )
            design = json.loads(row.design_json)
        except (ProtectedResourceNotFound, json.JSONDecodeError) as exc:
            raise ReviewedDesignRequired() from exc
        if (
            not isinstance(design, dict)
            or not hmac.compare_digest(
                row.content_digest, hashlib.sha256(row.design_json.encode()).hexdigest()
            )
        ):
            raise ReviewedDesignRequired()
        return row, design

    def intake_reviewed_design(
        self,
        db: object,
        actor: Actor,
        case_id: UUID,
        *,
        contract_id: UUID,
        report_design: dict[str, Any],
    ) -> dict[str, Any]:
        store = cast(ApplicationPersistence, db)
        reviewer = store.active_actor(actor.membership_id, actor.identity_id, lock=True)
        if (
            reviewer is None
            or reviewer.company_id != actor.company_id
            or reviewer.role != Role.EXPERT
        ):
            raise ProtectedResourceNotFound()
        payload, semantic_digest, evidence_digest, case, contract = self._current_payload(
            store, reviewer, case_id, contract_id, lock_access=True
        )
        try:
            design_json = json.dumps(
                report_design, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise ReviewedDesignRequired() from exc
        if (
            report_design.get("artifact_kind") != "ReportDesign"
            or report_design.get("schema_version") != 1
            or not isinstance(report_design.get("pages"), list)
            or len(design_json.encode()) > MAX_BRIDGE_BYTES
        ):
            raise ReviewedDesignRequired()
        pages = report_design["pages"]
        visual_count = sum(
            len(page.get("visuals", []))
            for page in pages
            if isinstance(page, dict) and isinstance(page.get("visuals"), list)
        )
        summary = {
            "page_count": len(pages),
            "visual_count": visual_count,
            "description": "Expert-reviewed report plan for the current confirmed request",
        }
        binding_json = json.dumps(payload["binding"], sort_keys=True, separators=(",", ":"))
        row = store.add_reviewed_design(
            reviewer,
            case_id,
            contract.id,
            contract.interpretation_id,
            case.current_request_version_id,
            case.semantic_context_version,
            binding_json,
            hashlib.sha256(binding_json.encode()).hexdigest(),
            semantic_digest,
            evidence_digest,
            design_json,
            hashlib.sha256(design_json.encode()).hexdigest(),
            json.dumps(summary, sort_keys=True, separators=(",", ":")),
        )
        return self._reviewed_design_json(row)

    @staticmethod
    def _reviewed_design_json(row: ReviewedReportDesignRecord) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "confirmed_contract_id": str(row.confirmed_contract_id),
            "summary": json.loads(row.summary_json),
            "reviewed_at": row.reviewed_at.isoformat(),
        }

    def list_reviewed_designs(
        self, db: object, actor: Actor, case_id: UUID, contract_id: UUID
    ) -> list[dict[str, Any]]:
        store = cast(ApplicationPersistence, db)
        payload, semantic_digest, evidence_digest, _, _ = self._current_payload(
            store, actor, case_id, contract_id, require_edit=False
        )
        result = []
        for row in store.reviewed_designs(case_id, contract_id):
            try:
                self._eligible_design(
                    store, actor, case_id, contract_id, row.id,
                    payload, semantic_digest, evidence_digest,
                )
            except ReviewedDesignRequired:
                continue
            result.append(self._reviewed_design_json(row))
        return result

    def start(
        self,
        db: object,
        actor: Actor,
        case_id: UUID,
        *,
        contract_id: UUID,
        command_key: str,
        mode: str = "BUILD",
        source_attempt_id: UUID | None = None,
        reviewed_design_id: UUID | None = None,
    ) -> tuple[dict[str, Any], bool]:
        store = cast(ApplicationPersistence, db)
        if self.bridge is None:
            raise GenerationFailed()
        payload, semantic_input_digest, evidence_digest, case, contract = self._current_payload(
            store, actor, case_id, contract_id
        )
        if reviewed_design_id is None:
            raise ReviewedDesignRequired()
        reviewed, report_design = self._eligible_design(
            store, actor, case_id, contract_id, reviewed_design_id,
            payload, semantic_input_digest, evidence_digest,
        )
        payload["reportDesign"] = report_design
        semantic_input_digest = canonical_digest(payload)
        input_digest = canonical_digest(
            {
                "semanticInputDigest": semantic_input_digest,
                "reviewedDesignId": str(reviewed.id),
                "pipelineExecutableDigest": self.bridge.pipeline_digest,
            }
        )
        payload["execution"] = {
            "inputDigest": input_digest,
            "pipelineExecutableDigest": self.bridge.pipeline_digest,
        }
        command_payload_digest = canonical_digest(
            {
                "inputDigest": input_digest,
                "mode": mode,
                "sourceAttemptId": str(source_attempt_id) if source_attempt_id else None,
            }
        )
        existing_command = store.generation_attempt_by_command(actor, case_id, command_key)
        if existing_command is not None:
            if not hmac.compare_digest(
                existing_command.command_payload_digest, command_payload_digest
            ):
                raise IdempotencyConflict()
            return attempt_json(store, existing_command), False
        prior = store.equivalent_generation_attempt(case_id, input_digest)
        history = store.generation_attempts(case_id)
        latest = history[0] if history else None
        retry_of: UUID | None = None
        supersedes: UUID | None = None
        if mode == "BUILD" and prior is not None:
            return attempt_json(store, prior), False
        if mode == "RETRY":
            source = (
                store.generation_attempt(case_id, source_attempt_id)
                if source_attempt_id is not None
                else None
            )
            if (
                source is None
                or not hmac.compare_digest(source.input_digest, input_digest)
                or source.status not in {"FAILED", "CANCELLED"}
            ):
                raise Conflict()
            retry_of = source.id
        elif mode == "REGENERATE":
            source = (
                store.generation_attempt(case_id, source_attempt_id)
                if source_attempt_id is not None
                else latest
            )
            if source_attempt_id is not None and source is None:
                raise Conflict()
            if source is not None:
                supersedes = source.id
        elif mode != "BUILD":
            raise Conflict()
        if store.active_generation_attempt(case_id) is not None:
            raise Conflict()
        provenance = {
            "mode": "LOCAL_DETERMINISTIC_NO_MODEL_CALL",
            "pipeline": "CANONICAL_TYPESCRIPT_PACKAGE_C",
            "bridgeVersion": "protected-generation-1",
            "pipelineExecutableDigest": self.bridge.pipeline_digest,
            "contractDigest": hashlib.sha256(contract.contract_json.encode()).hexdigest(),
            "commandPayloadDigest": command_payload_digest,
            "inputDigest": input_digest,
            "evidenceBindingDigest": evidence_digest,
            "reviewedDesignId": str(reviewed.id),
            "reviewedDesignDigest": reviewed.content_digest,
            "runtimeEvidence": {
                "powerBiDesktop": "NOT_RUN",
                "dax": "NOT_RUN",
                "rls": "NOT_RUN",
                "deployment": "NOT_RUN",
            },
        }
        row = store.create_generation_attempt(
            actor,
            case_id,
            contract.id,
            contract.interpretation_id,
            case.current_request_version_id,
            command_key,
            command_payload_digest,
            input_digest,
            evidence_digest,
            json.dumps(provenance, sort_keys=True, separators=(",", ":")),
            reviewed.id,
            retry_of_attempt_id=retry_of,
            supersedes_attempt_id=supersedes,
        )
        row.status = "RUNNING"
        row.started_at = datetime.now(UTC)
        store.add_audit(actor, "GENERATION_STARTED", "GENERATION_ATTEMPT", row.id)
        cast(Any, db).commit()
        fence = row.fence_token
        try:
            result = self.bridge.generate(payload)
            files = cast(dict[str, str], result["files"])
            content = _candidate_zip(files)
            filename = f"{result.get('projectName', 'APBRAReport')}.candidate.zip"
            current = store.generation_attempt(case_id, row.id, lock=True)
            if current is None or current.status != "RUNNING" or current.fence_token != fence:
                return attempt_json(store, current or row), True
            active_actor = store.active_actor(actor.membership_id, actor.identity_id, lock=True)
            if active_actor is None or active_actor.company_id != actor.company_id:
                raise GenerationFailed()
            current_payload, current_digest, current_evidence_digest, _, _ = (
                self._current_payload(
                    store, active_actor, case_id, contract_id, lock_access=True
                )
            )
            self._eligible_design(
                store, active_actor, case_id, contract_id, reviewed.id,
                current_payload, current_digest, current_evidence_digest,
                lock_access=True,
            )
            storage_key, digest, size = self.artifact_objects.write(
                actor.company_id, case_id, row.id, content
            )
            try:
                artifact = store.add_generated_artifact(
                    current, storage_key, filename, digest, size
                )
                current.validation_json = json.dumps(
                    {
                        **cast(dict[str, Any], result["validation"]),
                        "pipelineProvenance": result.get("provenance", {}),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                current.status = "SUCCEEDED"
                current.completed_at = datetime.now(UTC)
                store.add_audit(
                    active_actor,
                    "GENERATION_SUCCEEDED",
                    "GENERATION_ATTEMPT",
                    current.id,
                    json.dumps(
                        {"artifact_id": str(artifact.id), "digest": digest},
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
                cast(Any, db).commit()
            except Exception:
                cast(Any, db).rollback()
                self.artifact_objects.delete_uncommitted(storage_key)
                raise
            return attempt_json(store, current), True
        except Exception as exc:
            cast(Any, db).rollback()
            current = store.generation_attempt(case_id, row.id, lock=True)
            if current is not None and current.status == "RUNNING" and current.fence_token == fence:
                current.status = "FAILED"
                current.failure_code = (
                    exc.code if isinstance(exc, GenerationFailed) else "GENERATION_PIPELINE_FAILED"
                )
                current.failure_reason = "The canonical generation pipeline did not complete."
                current.completed_at = datetime.now(UTC)
                store.add_audit(actor, "GENERATION_FAILED", "GENERATION_ATTEMPT", current.id)
                cast(Any, db).commit()
                return attempt_json(store, current), True
            if current is None:
                raise
            return attempt_json(store, current), True

    def cancel(self, db: object, actor: Actor, case_id: UUID, attempt_id: UUID) -> dict[str, Any]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(store, actor, case_id, require_edit=True)
        row = store.generation_attempt(case_id, attempt_id, lock=True)
        if row is None:
            raise GenerationUnavailable()
        if row.status in {"PENDING", "RUNNING"}:
            row.status = "CANCELLED"
            row.cancelled_at = datetime.now(UTC)
            row.completed_at = row.cancelled_at
            store.add_audit(actor, "GENERATION_CANCELLED", "GENERATION_ATTEMPT", row.id)
        return attempt_json(store, row)

    def artifact(
        self, db: object, actor: Actor, case_id: UUID, attempt_id: UUID
    ) -> tuple[bytes, str, str]:
        store = cast(ApplicationPersistence, db)
        authorized_case_access(store, actor, case_id)
        row = store.generation_attempt(case_id, attempt_id)
        if row is None or row.status != "SUCCEEDED" or row.artifact_id is None:
            raise ArtifactUnavailable()
        artifact = store.generated_artifact(row.artifact_id)
        if (
            artifact is None
            or artifact.attempt_id != row.id
            or artifact.case_id != row.case_id
            or artifact.company_id != row.company_id
            or artifact.validation_status != "PASS"
        ):
            raise ArtifactUnavailable()
        try:
            content = self.artifact_objects.read(
                artifact.storage_key, artifact.content_digest, artifact.byte_size
            )
        except ArtifactError as exc:
            raise ArtifactUnavailable() from exc
        return content, artifact.filename, artifact.content_digest
