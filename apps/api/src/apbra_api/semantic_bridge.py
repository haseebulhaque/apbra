from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .domain import SemanticValidationFailed

MAX_BRIDGE_BYTES = 1_000_000


# Exact fixed canonical messages only. Never retain dynamic identifiers, candidate
# values, combined errors or arbitrary subprocess messages in failure diagnostics.
_MESSAGE_REASONS = {
    "Question IDs must be non-empty and unique within a round.": "QUESTION_IDS_INVALID",
    "AI returned more questions than the configured per-round limit.": "QUESTION_LIMIT_EXCEEDED",
    "AI returned a malformed clarification question.": "QUESTION_INVALID",
    "Analysis knowledge provenance is malformed.": "KNOWLEDGE_PROVENANCE_INVALID",
    "Clarification requires questions and unresolved material ambiguity.":
        "CLARIFICATION_INCOMPLETE",
    "The configured clarification-round limit prevents another question.":
        "CLARIFICATION_BUDGET_EXCEEDED",
    "Ready for confirmation requires a supported interpretation with no unresolved "
    "ambiguity in the deliverable scope.": "CONFIRMATION_SCOPE_UNRESOLVED",
    "OUT_OF_SCOPE requires an out-of-scope interpretation.": "OUT_OF_SCOPE_INCONSISTENT",
    "Analysis history is malformed.": "ANALYSIS_HISTORY_INVALID",
    "Session envelope or configured limits are invalid.": "SESSION_ENVELOPE_INVALID",
    "Session material input context binding is missing.": "SESSION_CONTEXT_MISSING",
    "Session readiness is not bound to the exact visible interpretation and input context.":
        "SESSION_READINESS_UNBOUND",
    "Clarification rounds and analyses are inconsistent.": "CLARIFICATION_HISTORY_INCONSISTENT",
    "Session is not a complete confirmed transcript.": "CONFIRMED_TRANSCRIPT_INCOMPLETE",
}
_MESSAGE_REASONS = {
    "CLARIFICATION_STATE_INVALID: " + message: reason
    for message, reason in _MESSAGE_REASONS.items()
}
_SAFE_REASONS = frozenset(_MESSAGE_REASONS.values()) | frozenset({
    "SEMANTIC_RULE_UNCLASSIFIED", "BRIDGE_INPUT_TOO_LARGE", "BRIDGE_OUTPUT_TOO_LARGE",
    "BRIDGE_TIMEOUT", "BRIDGE_PROCESS_FAILED", "BRIDGE_RESPONSE_INVALID", "BRIDGE_VALUE_INVALID",
    "ANALYSIS_STATE_UNSUPPORTED",
})


def safe_semantic_reason(value: object) -> str:
    return value if type(value) is str and value in _SAFE_REASONS else "SEMANTIC_RULE_UNCLASSIFIED"


class SemanticBridgeFailure(SemanticValidationFailed):
    """Same public failure; only a curated constant is available to internal audit."""

    def __init__(self, reason_code: object) -> None:
        super().__init__()
        self.reason_code = safe_semantic_reason(reason_code)


@dataclass(frozen=True)
class ReadinessResult:
    readiness_binding: str
    context_binding: str
    confirmation_summary: dict[str, Any]


@dataclass(frozen=True)
class ConfirmationResult:
    session: dict[str, Any]
    contract: dict[str, Any]


@dataclass(frozen=True)
class SimulationResult:
    session: dict[str, Any]


class SemanticBridge:
    """Bounded adapter to the canonical TypeScript semantic engine."""

    def __init__(
        self,
        executable: Path,
        *,
        node_executable: Path = Path("/usr/local/bin/node"),
        timeout_seconds: int = 10,
    ) -> None:
        self.executable = executable.resolve()
        self.node_executable = node_executable.resolve()
        self.timeout_seconds = timeout_seconds
        if not self.executable.is_file() or self.executable.is_symlink():
            raise ValueError("The semantic bridge must be a fixed regular file.")
        if not self.node_executable.is_file() or self.node_executable.is_symlink():
            raise ValueError("The semantic bridge runtime must be a fixed regular file.")

    def _call(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        if len(encoded) > MAX_BRIDGE_BYTES:
            raise SemanticBridgeFailure("BRIDGE_INPUT_TOO_LARGE")
        environment = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "NODE_ENV": "production",
        }
        try:
            # Both executables are fixed, resolved regular files; user input is stdin JSON only.
            result = subprocess.run(  # noqa: S603
                [str(self.node_executable), str(self.executable)],
                input=encoded,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=self.timeout_seconds,
                env=environment,
            )
        except subprocess.TimeoutExpired:
            raise SemanticBridgeFailure("BRIDGE_TIMEOUT") from None
        except OSError:
            raise SemanticBridgeFailure("BRIDGE_PROCESS_FAILED") from None
        if len(result.stdout) > MAX_BRIDGE_BYTES:
            raise SemanticBridgeFailure("BRIDGE_OUTPUT_TOO_LARGE")
        try:
            response = json.loads(result.stdout)
        except (json.JSONDecodeError, UnicodeDecodeError):
            reason = "BRIDGE_PROCESS_FAILED" if result.returncode else "BRIDGE_RESPONSE_INVALID"
            raise SemanticBridgeFailure(reason) from None
        if not isinstance(response, dict):
            raise SemanticBridgeFailure("BRIDGE_RESPONSE_INVALID")
        if response.get("ok") is False:
            error = response.get("error")
            reason = "SEMANTIC_RULE_UNCLASSIFIED"
            if isinstance(error, dict) and error.get("code") == "SEMANTIC_VALIDATION_FAILED":
                message = error.get("message")
                if type(message) is str:
                    reason = _MESSAGE_REASONS.get(message, reason)
            raise SemanticBridgeFailure(reason)
        # An error exit must never become success even if stdout claims ok:true.
        if result.returncode != 0:
            raise SemanticBridgeFailure("BRIDGE_PROCESS_FAILED")
        if response.get("ok") is not True:
            raise SemanticBridgeFailure("BRIDGE_RESPONSE_INVALID")
        value = response.get("value")
        if not isinstance(value, dict):
            raise SemanticBridgeFailure("BRIDGE_VALUE_INVALID")
        return value

    def readiness(self, session: dict[str, Any], data_structure: dict[str, Any]) -> ReadinessResult:
        value = self._call(
            {"operation": "readiness", "session": session, "dataStructure": data_structure}
        )
        binding = value.get("readinessBinding")
        context = value.get("contextBinding")
        summary = value.get("confirmationSummary")
        if (
            not isinstance(binding, str)
            or not binding
            or not isinstance(context, str)
            or not context
        ):
            raise SemanticBridgeFailure("BRIDGE_VALUE_INVALID")
        if not isinstance(summary, dict):
            raise SemanticBridgeFailure("BRIDGE_VALUE_INVALID")
        return ReadinessResult(binding, context, summary)

    def simulate(
        self,
        *,
        session_id: str,
        original_request: str,
        context_binding: str,
        analysed_at: datetime,
        data_structure: dict[str, Any],
    ) -> SimulationResult:
        value = self._call(
            {
                "operation": "simulate",
                "sessionId": session_id,
                "originalRequest": original_request,
                "contextBinding": context_binding,
                "analysedAt": analysed_at.isoformat(),
                "dataStructure": data_structure,
            }
        )
        session = value.get("session")
        if not isinstance(session, dict):
            raise SemanticBridgeFailure("BRIDGE_VALUE_INVALID")
        return SimulationResult(session)

    def analysis(
        self,
        *,
        session_id: str,
        original_request: str,
        context_binding: str,
        analysed_at: datetime,
        data_structure: dict[str, Any],
        analysis: dict[str, Any],
        limits: dict[str, int],
    ) -> SimulationResult:
        value = self._call(
            {
                "operation": "analysis",
                "sessionId": session_id,
                "originalRequest": original_request,
                "contextBinding": context_binding,
                "analysedAt": analysed_at.isoformat(),
                "dataStructure": data_structure,
                "analysis": analysis,
                "limits": limits,
            }
        )
        session = value.get("session")
        if not isinstance(session, dict):
            raise SemanticBridgeFailure("BRIDGE_VALUE_INVALID")
        return SimulationResult(session)

    def confirm(
        self,
        session: dict[str, Any],
        data_structure: dict[str, Any],
        *,
        confirmed_at: datetime,
        readiness_binding: str,
        context_binding: str,
    ) -> ConfirmationResult:
        value = self._call(
            {
                "operation": "confirm",
                "session": session,
                "dataStructure": data_structure,
                "confirmedAt": confirmed_at.isoformat(),
                "readinessBinding": readiness_binding,
                "contextBinding": context_binding,
            }
        )
        confirmed_session = value.get("session")
        contract = value.get("contract")
        if not isinstance(confirmed_session, dict) or not isinstance(contract, dict):
            raise SemanticBridgeFailure("BRIDGE_VALUE_INVALID")
        if (
            contract.get("artifact_kind") != "ConfirmedRequirementContract"
            or contract.get("schema_version") != 2
        ):
            raise SemanticBridgeFailure("BRIDGE_VALUE_INVALID")
        return ConfirmationResult(confirmed_session, contract)
