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
            raise SemanticValidationFailed()
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
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SemanticValidationFailed() from exc
        if result.returncode != 0 or len(result.stdout) > MAX_BRIDGE_BYTES:
            raise SemanticValidationFailed()
        try:
            response = json.loads(result.stdout)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SemanticValidationFailed() from exc
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise SemanticValidationFailed()
        value = response.get("value")
        if not isinstance(value, dict):
            raise SemanticValidationFailed()
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
            raise SemanticValidationFailed()
        if not isinstance(summary, dict):
            raise SemanticValidationFailed()
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
            raise SemanticValidationFailed()
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
            raise SemanticValidationFailed()
        if (
            contract.get("artifact_kind") != "ConfirmedRequirementContract"
            or contract.get("schema_version") != 2
        ):
            raise SemanticValidationFailed()
        return ConfirmationResult(confirmed_session, contract)
