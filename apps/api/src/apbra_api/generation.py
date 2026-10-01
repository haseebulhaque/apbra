from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import logging
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
    DesignProposalUnavailable,
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
from .model_provider import (
    ModelProvider,
    ProviderCallError,
    ProviderExecutionObservation,
    ProviderRequest,
    report_design_schema,
)

MAX_BRIDGE_BYTES = 20_000_000
MAX_BRIDGE_EXECUTABLE_BYTES = 5_000_000
MAX_CANDIDATE_FILES = 500
MAX_CANDIDATE_TEXT = 5_000_000
logger = logging.getLogger(__name__)


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

    def _call(self, payload: dict[str, Any], *, validate_candidate: bool) -> dict[str, Any]:
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
        if writer_error:
            raise GenerationFailed()
        try:
            response = json.loads(output)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise GenerationFailed() from exc
        if isinstance(response, dict) and response.get("ok") is False:
            error = response.get("error")
            if isinstance(error, dict):
                code = error.get("code")
                message = error.get("message")
                if isinstance(code, str) and code and isinstance(message, str) and message:
                    raise GenerationBridgeFailure(code[:100], message[:500])
            raise GenerationFailed()
        if return_code != 0:
            raise GenerationFailed()
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise GenerationFailed()
        value = response.get("value")
        if not isinstance(value, dict):
            raise GenerationFailed()
        if not validate_candidate:
            knowledge = value.get("knowledge")
            if (
                not isinstance(knowledge, list)
                or not knowledge
                or len(knowledge) > 100
                or any(
                    not isinstance(item, dict)
                    or not isinstance(item.get("citation"), str)
                    or not item["citation"]
                    or not isinstance(item.get("text"), str)
                    or not item["text"]
                    or len(item["text"].encode()) > 100_000
                    for item in knowledge
                )
            ):
                raise GenerationFailed()
            return value
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

    def governed_knowledge(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        value = self._call({**payload, "operation": "knowledge"}, validate_candidate=False)
        return cast(list[dict[str, str]], value["knowledge"])

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call({**payload, "operation": "generate"}, validate_candidate=True)


class GenerationBridgeFailure(GenerationFailed):
    """Trusted bounded bridge diagnostic that is never returned to the browser."""

    def __init__(self, diagnostic_code: str, diagnostic_message: str) -> None:
        super().__init__(diagnostic_code)
        self.diagnostic_code = diagnostic_code
        self.diagnostic_message = diagnostic_message


SAFE_BRIDGE_DIAGNOSTIC_DETAILS = {
    "REPORT_DESIGN_NORMALIZATION_FAILED",
    "REPORT_DESIGN_SEMANTICS_FAILED",
}


def _safe_bridge_diagnostic_detail(exc: GenerationBridgeFailure) -> str | None:
    return exc.diagnostic_message if exc.diagnostic_code in SAFE_BRIDGE_DIAGNOSTIC_DETAILS else None


def _provider_validation_failure(exc: Exception) -> Exception | None:
    if isinstance(exc, ProviderCallError) and exc.code == "MODEL_CANDIDATE_REJECTED":
        return exc.__cause__ if isinstance(exc.__cause__, Exception) else None
    return exc if isinstance(exc, GenerationFailed) else None


def _safe_failed_validation(exc: Exception) -> dict[str, str] | None:
    validation_failure = _provider_validation_failure(exc)
    if validation_failure is None:
        return None
    if isinstance(validation_failure, GenerationBridgeFailure):
        category = validation_failure.diagnostic_code
        detail = _safe_bridge_diagnostic_detail(validation_failure)
    elif isinstance(validation_failure, GenerationFailed):
        category = validation_failure.code
        detail = None
    else:
        category = "CANDIDATE_VALIDATION_FAILED"
        detail = None
    evidence = {
        "status": "FAILED",
        "stage": "REPORT_DESIGN_DETERMINISTIC_VALIDATION",
        "category": category,
        "detail_status": "RECORDED" if detail is not None else "WITHHELD",
    }
    if detail is not None:
        evidence["structural_detail"] = detail[:500]
    return evidence


def _apply_provider_observation(attempt: Any, observation: ProviderExecutionObservation) -> None:
    attempt.provider_profile_id = observation.profile_id
    attempt.model_or_deployment = observation.model_or_deployment
    attempt.prompt_version = observation.prompt_version
    attempt.configuration_id = observation.configuration_id
    attempt.capability_profile_json = json.dumps(
        observation.capability_profile, sort_keys=True, separators=(",", ":")
    )
    attempt.usage_json = json.dumps(
        {
            **observation.usage,
            "latency_ms": observation.latency_ms,
            "call_count": observation.call_count,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    attempt.candidate_digest = observation.candidate_digest


def _automatic_design_retry_instruction(
    exc: Exception, *, max_visuals_per_page: int
) -> str:
    if (
        isinstance(exc, GenerationBridgeFailure)
        and exc.diagnostic_code == "REPORT_DESIGN_NORMALIZATION_FAILED"
        and "LAYOUT_CAPACITY_EXCEEDED" in exc.diagnostic_message
    ):
        return (
            "The prior ReportDesign passed structured parsing but failed compiler geometry "
            "only. Return the exact same complete ReportDesign, changing only the order of "
            "objects within each affected page's visuals array. Preserve every object, value, "
            "ID, page membership, measure, field, title, citation, warning, and all other array "
            "orders exactly; do not add, remove, move between pages, or otherwise change any "
            f"visual. Stay within the validated {max_visuals_per_page}-visual page limit and "
            "use only physical slots reported as in bounds by deterministic geometry. "
            f"Deterministic geometry finding: {exc.diagnostic_message}"
        )
    if (
        isinstance(exc, GenerationBridgeFailure)
        and exc.diagnostic_code == "REPORT_DESIGN_SEMANTICS_FAILED"
    ):
        return (
            "The prior ReportDesign failed deterministic confirmed-requirement coverage. "
            "Return one complete corrected ReportDesign. Use every zero-based index in the "
            "deterministic finding to locate the exact entry in coverageChecklist and the "
            "corresponding supplied ConfirmedRequirementContract array. Preserve every already-"
            "covered obligation, dimension, business question, measure, field, page, citation, "
            "and supported visual; do not trade one covered requirement for another. Correct "
            "the uncovered entries without inventing business meaning or unsupported capability. "
            f"Deterministic coverage finding: {exc.diagnostic_message}"
        )
    if isinstance(exc, GenerationBridgeFailure):
        detail = _safe_bridge_diagnostic_detail(exc)
        finding = f"{exc.diagnostic_code}: {detail}" if detail is not None else exc.diagnostic_code
    else:
        finding = type(exc).__name__
    return (
        "The prior ReportDesign was rejected by deterministic validation. Return one complete "
        "corrected ReportDesign and preserve the supplied ConfirmedRequirementContract exactly. "
        "Correct the failed invariants without inventing business meaning, measures, fields, "
        "pages, citations, or unsupported capability, and without following a prescribed "
        "business design recipe. The corrected value will be fully revalidated. "
        f"Deterministic finding: {finding}"
    )


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


def design_attempt_json(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "confirmed_contract_id": str(row.confirmed_contract_id),
        "status": row.status,
        "provider_profile_id": row.provider_profile_id,
        "model_or_deployment": row.model_or_deployment,
        "prompt_version": row.prompt_version,
        "configuration_id": row.configuration_id,
        "capability_profile": json.loads(row.capability_profile_json),
        "usage": json.loads(row.usage_json),
        "failure": (
            {"code": row.safe_failure_code, "message": "The design proposal was not eligible."}
            if row.safe_failure_code
            else None
        ),
        "validation": json.loads(row.validation_json) if row.validation_json else None,
        "created_at": row.created_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


class GenerationService:
    def __init__(
        self,
        bridge: GenerationBridge | None,
        evidence_objects: LocalEvidenceStore,
        artifact_objects: LocalArtifactStore,
        *,
        reference_objects: LocalEvidenceStore | None = None,
        model_provider: ModelProvider | None = None,
        generation_policy: dict[str, Any] | None = None,
    ) -> None:
        self.bridge = bridge
        self.evidence_objects = evidence_objects
        self.artifact_objects = artifact_objects
        self.reference_objects = reference_objects
        self.model_provider = model_provider
        self.generation_policy = generation_policy

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
        references: list[dict[str, Any]] = []
        for row in store.reference_materials(case_id):
            if row.request_version_id != case.current_request_version_id:
                continue
            if self.reference_objects is None:
                raise GenerationUnavailable()
            try:
                self.reference_objects.read(row.storage_key, row.content_digest)
            except EvidenceError as exc:
                raise GenerationUnavailable() from exc
            references.append(
                {
                    "id": str(row.id),
                    "requestVersionId": str(row.request_version_id),
                    "filename": row.filename,
                    "mediaType": row.media_type,
                    "contentDigest": row.content_digest,
                    "interpretationState": row.interpretation_state,
                    "capabilityProfileId": row.capability_profile_id,
                }
            )
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
                "referenceMaterial": references,
            },
        }
        if self.generation_policy is not None:
            payload["generationPolicy"] = self.generation_policy
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
        ):
            raise ReviewedDesignRequired()
        if row.origin == "EXPERT_REVIEWED":
            if (
                row.reviewer_membership_id is None
                or row.reviewer_identity_id is None
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
            except ProtectedResourceNotFound as exc:
                raise ReviewedDesignRequired() from exc
        elif row.origin == "AUTO_ELIGIBLE":
            try:
                eligibility = json.loads(row.eligibility_validation_json or "")
            except json.JSONDecodeError as exc:
                raise ReviewedDesignRequired() from exc
            if (
                row.design_attempt_id is None
                or not isinstance(eligibility, dict)
                or eligibility.get("status") != "PASS"
            ):
                raise ReviewedDesignRequired()
        else:
            raise ReviewedDesignRequired()
        try:
            design = json.loads(row.design_json)
        except json.JSONDecodeError as exc:
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

    def propose_automatic_design(
        self,
        db: object,
        actor: Actor,
        case_id: UUID,
        *,
        contract_id: UUID,
        command_key: str,
    ) -> tuple[dict[str, Any], bool]:
        store = cast(ApplicationPersistence, db)
        bridge = self.bridge
        model_provider = self.model_provider
        generation_policy = self.generation_policy
        if bridge is None or model_provider is None or generation_policy is None:
            raise DesignProposalUnavailable()
        payload, semantic_digest, evidence_digest, case, contract = self._current_payload(
            store, actor, case_id, contract_id, lock_access=True
        )
        references = cast(list[dict[str, Any]], payload["binding"]["referenceMaterial"])
        reference_digest = canonical_digest(references)
        requirement_digest = canonical_digest(
            {"contract": payload["contract"], "binding": payload["binding"]}
        )
        command_digest = canonical_digest(
            {
                "contractId": str(contract_id),
                "semanticInputDigest": semantic_digest,
                "profileId": model_provider.profile.profile_id,
                "configurationId": model_provider.profile.configuration_id,
            }
        )
        existing = store.design_attempt_by_command(actor, case_id, command_key)
        if existing is not None:
            if not hmac.compare_digest(existing.command_payload_digest, command_digest):
                raise IdempotencyConflict()
            design = next(
                (
                    self._reviewed_design_json(row)
                    for row in store.reviewed_designs(case_id, contract_id)
                    if row.design_attempt_id == existing.id
                ),
                None,
            )
            return {"attempt": design_attempt_json(existing), "reviewed_design": design}, False
        attempt = store.create_design_attempt(
            actor,
            case_id,
            contract.id,
            contract.interpretation_id,
            case.current_request_version_id,
            case.semantic_context_version,
            command_key,
            command_digest,
            requirement_digest,
            evidence_digest,
            reference_digest,
        )
        attempt.provider_profile_id = model_provider.profile.profile_id
        attempt.model_or_deployment = model_provider.profile.model_or_deployment
        attempt.prompt_version = model_provider.profile.prompt_version
        attempt.configuration_id = model_provider.profile.configuration_id
        attempt.capability_profile_json = json.dumps(
            model_provider.profile.capabilities.model_dump(),
            sort_keys=True,
            separators=(",", ":"),
        )
        store.add_audit(actor, "AUTOMATIC_DESIGN_STARTED", "AUTOMATIC_DESIGN_ATTEMPT", attempt.id)
        cast(Any, db).commit()
        provider_observation: ProviderExecutionObservation | None = None
        terminal_validation: dict[str, Any] | None = None
        try:
            governed_knowledge = bridge.governed_knowledge(payload)
            generation_capabilities = cast(
                dict[str, Any], generation_policy["generation"]
            )
            governance = cast(dict[str, Any], generation_policy["governance"])
            supported_trend_grains = cast(
                list[str], generation_capabilities["supportedTrendGrains"]
            )
            max_visuals_per_page = cast(int, governance["maxVisualsPerPage"])
            contract_payload = cast(dict[str, Any], payload["contract"])
            obligations = cast(list[dict[str, Any]], contract_payload.get("obligations", []))
            obligation_indexes = {
                item.get("id"): index
                for index, item in enumerate(obligations)
                if isinstance(item.get("id"), str)
            }
            coverage_checklist = {
                "obligations": [
                    {
                        "index": index,
                        "kind": item.get("kind"),
                        "required": item.get("required"),
                        "minimumRepresentations": item.get("minimumRepresentations"),
                        "measureCount": len(item.get("measureNames", [])),
                        "fieldCount": len(item.get("fields", [])),
                        "pageCount": len(item.get("pageNames", [])),
                    }
                    for index, item in enumerate(obligations)
                ],
                "dimensions": [
                    {"index": index}
                    for index, _item in enumerate(contract_payload.get("dimensions", []))
                ],
                "businessQuestions": [
                    {
                        "index": index,
                        "obligationIndexes": [
                            obligation_indexes.get(item)
                            for item in question.get("coverageRequirementIds", [])
                            if obligation_indexes.get(item) is not None
                        ],
                    }
                    for index, question in enumerate(
                        cast(list[dict[str, Any]], contract_payload.get("businessQuestions", []))
                    )
                ],
            }
            validated_result: dict[str, Any] | None = None

            def validate_candidate(candidate: dict[str, Any]) -> None:
                nonlocal validated_result
                validation_payload = {**payload, "reportDesign": candidate}
                input_digest = canonical_digest(validation_payload)
                validation_payload["execution"] = {
                    "inputDigest": input_digest,
                    "pipelineExecutableDigest": bridge.pipeline_digest,
                }
                try:
                    result = bridge.generate(validation_payload)
                except GenerationBridgeFailure as exc:
                    detail = _safe_bridge_diagnostic_detail(exc)
                    if detail is None:
                        logger.warning(
                            "Automatic design candidate rejected by deterministic validation: "
                            "code=%s detail=withheld",
                            exc.diagnostic_code,
                        )
                    else:
                        logger.warning(
                            "Automatic design candidate rejected by deterministic validation: "
                            "code=%s detail=%s",
                            exc.diagnostic_code,
                            detail,
                        )
                    raise
                validation = result.get("validation")
                provenance = result.get("provenance")
                normalized = (
                    provenance.get("reportDesign") if isinstance(provenance, dict) else None
                )
                if (
                    not isinstance(validation, dict)
                    or validation.get("status") != "PASS"
                    or not isinstance(normalized, dict)
                ):
                    raise GenerationFailed()
                validated_result = result

            provider_result = model_provider.structured(
                ProviderRequest(
                    task="REPORT_DESIGN",
                    system_prompt=(
                        "Propose a generic Power BI ReportDesign for the exact confirmed business "
                        "requirements and qualified schema. Preserve every measure, "
                        "operand, dimension, filter, time grain and business question. "
                        "Copy the exact complete canonical measure objects from the "
                        "confirmed contract into ReportDesign.measures; do not change "
                        "any measure value. Use only evidenced Table.Column fields and "
                        "supported typed operations. Every visual must use an exact "
                        "confirmed page, field and measure ID. Emit every confirmed "
                        "required page exactly once without renaming it. Each required "
                        "KPI measure must appear in a visual on an allowed page. Each "
                        "BREAKDOWN or TREND must cover all of its exact measure IDs and "
                        "fields on an allowed page; one supported visual may combine its "
                        "measures. Trend visuals must use "
                        "the exact confirmed date field and time grain, while all other "
                        "visuals use timeGrain NONE. A card uses exactly one measure. A "
                        "bar, column or line uses at least one measure and a non-empty "
                        "categoryField. A table uses at least one field or measure. A "
                        "slicer uses exactly one fields entry, an empty categoryField, "
                        "and no measures. Represent every required obligation at least "
                        "its configured minimum, within the configured page and visual "
                        f"limits. The validated runtime permits at most "
                        f"{max_visuals_per_page} visuals per page. The active compiler has "
                        "four general visual slots followed by two card-only slots; stay "
                        "within both the configured limit and those physical slot types. "
                        "Use the smallest "
                        "nonredundant design that fully covers "
                        "the contract. Treat coverageChecklist as an exhaustive zero-based "
                        "cross-reference: cover every required obligation entry, bind every "
                        "dimension entry in at least one visual, and satisfy every business-"
                        "question mapping without trading away another entry. Prefer exact "
                        "ReportDesign.filters entries for "
                        "FILTER obligations because they satisfy filter coverage without a "
                        "duplicate slicer. Never create a slicer for a field already listed "
                        "in ReportDesign.filters; do not repeat the same filter or analysis on "
                        "every page. Do not assert access, confirmation, validation, "
                        "approval or eligibility. Do not emit executable DAX, M or SQL. "
                        "Reference-material metadata marked NOT_INTERPRETED conveys no "
                        "visual semantics. Apply only supplied exact governed citation "
                        "IDs and apply at least one; do not invent citations. Return "
                        "only the requested structured "
                        "candidate."
                    ),
                    context={
                        "confirmedRequirements": payload["contract"],
                        "dataStructure": payload["dataStructure"],
                        "referenceMaterial": references,
                        "governedKnowledge": governed_knowledge,
                        "generationPolicy": generation_policy,
                        "coverageChecklist": coverage_checklist,
                    },
                    output_schema=report_design_schema(
                        max_visuals_per_page=max_visuals_per_page,
                        supported_trend_grains=supported_trend_grains,
                    ),
                    validator=validate_candidate,
                    retry_instruction=lambda exc: _automatic_design_retry_instruction(
                        exc, max_visuals_per_page=max_visuals_per_page
                    ),
                )
            )
            provider_observation = provider_result.observation
            _apply_provider_observation(attempt, provider_observation)
            if validated_result is None:
                raise GenerationFailed()
            result = validated_result
            validation = cast(dict[str, Any], result["validation"])
            terminal_validation = validation
            normalized = cast(dict[str, Any], result["provenance"])["reportDesign"]
            active_actor = store.active_actor(actor.membership_id, actor.identity_id, lock=True)
            if active_actor is None or active_actor.company_id != actor.company_id:
                raise GenerationFailed()
            current_payload, current_digest, current_evidence, current_case, _ = (
                self._current_payload(
                    store, active_actor, case_id, contract_id, lock_access=True
                )
            )
            if (
                not hmac.compare_digest(current_digest, semantic_digest)
                or not hmac.compare_digest(current_evidence, evidence_digest)
                or current_case.semantic_context_version != attempt.semantic_context_version
            ):
                raise StaleVersion()
            normalized_json = json.dumps(
                normalized, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            pages = normalized.get("pages")
            report_title = normalized.get("projectName")
            description = normalized.get("overview")
            if (
                not isinstance(pages, list)
                or not isinstance(report_title, str)
                or not report_title.strip()
                or not isinstance(description, str)
                or not description.strip()
            ):
                raise GenerationFailed()
            visual_count = sum(
                len(page.get("visuals", []))
                for page in pages
                if isinstance(page, dict) and isinstance(page.get("visuals"), list)
            )
            summary = {
                "page_count": len(pages),
                "visual_count": visual_count,
                "description": description,
            }
            binding_json = json.dumps(
                current_payload["binding"], sort_keys=True, separators=(",", ":")
            )
            validation_json = json.dumps(
                validation, sort_keys=True, separators=(",", ":")
            )
            reviewed = store.add_reviewed_design(
                active_actor,
                case_id,
                contract.id,
                contract.interpretation_id,
                current_case.current_request_version_id,
                current_case.semantic_context_version,
                binding_json,
                hashlib.sha256(binding_json.encode()).hexdigest(),
                current_digest,
                current_evidence,
                normalized_json,
                hashlib.sha256(normalized_json.encode()).hexdigest(),
                json.dumps(summary, sort_keys=True, separators=(",", ":")),
                origin="AUTO_ELIGIBLE",
                design_attempt_id=attempt.id,
                eligibility_validation_json=validation_json,
            )
            store.update_case_report_title(current_case, report_title.strip()[:160])
            attempt.status = "ELIGIBLE"
            attempt.validation_json = validation_json
            attempt.completed_at = datetime.now(UTC)
            store.add_audit(
                active_actor,
                "AUTOMATIC_DESIGN_ELIGIBLE",
                "AUTOMATIC_DESIGN_ATTEMPT",
                attempt.id,
            )
            cast(Any, db).commit()
            return {
                "attempt": design_attempt_json(attempt),
                "reviewed_design": self._reviewed_design_json(reviewed),
            }, True
        except Exception as exc:
            failure_observation = (
                exc.observation
                if isinstance(exc, ProviderCallError) and exc.observation is not None
                else provider_observation
            )
            failure_validation = _safe_failed_validation(exc) or terminal_validation
            validation_failure = _provider_validation_failure(exc)
            cast(Any, db).rollback()
            failed_attempt = store.design_attempt_by_command(actor, case_id, command_key)
            if failed_attempt is None:
                raise
            if isinstance(validation_failure, GenerationBridgeFailure):
                detail = _safe_bridge_diagnostic_detail(validation_failure)
                if detail is None:
                    logger.warning(
                        "Automatic design deterministic validation failed: code=%s detail=withheld",
                        validation_failure.diagnostic_code,
                    )
                else:
                    logger.warning(
                        "Automatic design deterministic validation failed: code=%s detail=%s",
                        validation_failure.diagnostic_code,
                        detail,
                    )
            elif isinstance(exc, ProviderCallError):
                logger.warning("Automatic design provider failed: code=%s", exc.code)
            else:
                logger.warning("Automatic design failed: type=%s", type(exc).__name__)
            failure_code = (
                exc.code
                if isinstance(exc, (ProviderCallError, GenerationFailed))
                else "AUTOMATIC_DESIGN_VALIDATION_FAILED"
            )
            if failure_observation is not None:
                _apply_provider_observation(failed_attempt, failure_observation)
            if failure_validation is not None:
                failed_attempt.validation_json = json.dumps(
                    failure_validation, sort_keys=True, separators=(",", ":")
                )
            failed_attempt.status = "FAILED"
            failed_attempt.safe_failure_code = failure_code
            failed_attempt.completed_at = datetime.now(UTC)
            store.add_audit(
                actor,
                "AUTOMATIC_DESIGN_FAILED",
                "AUTOMATIC_DESIGN_ATTEMPT",
                failed_attempt.id,
            )
            cast(Any, db).commit()
            raise DesignProposalUnavailable() from exc

    def automatic_design_history(
        self, db: object, actor: Actor, case_id: UUID, contract_id: UUID
    ) -> list[dict[str, Any]]:
        store = cast(ApplicationPersistence, db)
        self._current_payload(store, actor, case_id, contract_id, require_edit=False)
        return [design_attempt_json(row) for row in store.design_attempts(case_id, contract_id)]

    @staticmethod
    def _reviewed_design_json(row: ReviewedReportDesignRecord) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "confirmed_contract_id": str(row.confirmed_contract_id),
            "summary": json.loads(row.summary_json),
            "origin": row.origin,
            "provenance_label": (
                "Automatically eligible"
                if row.origin == "AUTO_ELIGIBLE"
                else "Expert reviewed"
            ),
            "reviewed_at": row.reviewed_at.isoformat(),
        }

    def list_reviewed_designs(
        self, db: object, actor: Actor, case_id: UUID, contract_id: UUID
    ) -> dict[str, Any]:
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
        try:
            authorized_case_access(store, actor, case_id, require_edit=True)
            can_build = True
        except ProtectedResourceNotFound:
            can_build = False
        return {
            "items": result,
            "can_build": can_build,
            "can_submit": can_build and actor.role == Role.EXPERT,
        }

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
