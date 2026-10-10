"""Frozen controller job files and independently checked transfer receipts.

The command dialect is not a firmware identity. A verified remote file and a
compiled launch plan establish file provenance only, never execution admission.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .arguments import MAX_FILE
from .client import Response
from .operations import compile_operation


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def context_digest(context: object) -> str:
    return digest(json.dumps(context, sort_keys=True, allow_nan=False, separators=(",", ":")).encode())


@dataclass(frozen=True)
class FrozenProgram:
    source: str
    data: bytes
    context_sha256: str
    session_id: str
    connection_id: str
    sha256: str = field(init=False)
    remote_path: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes) or not 0 < len(self.data) <= MAX_FILE or b"\0" in self.data:
            raise ValueError("Choose a nonempty program without NUL bytes, at most 8 MiB")
        self.data.decode("utf-8")
        if not all(isinstance(value, str) and value for value in (self.source, self.session_id, self.connection_id)):
            raise ValueError("The file needs its source and exact backend connection identities")
        object.__setattr__(self, "sha256", digest(self.data))
        object.__setattr__(self, "remote_path", f"/sd/gcodes/job-{self.sha256}.nc")


class JobFile:
    def __init__(self, source: str, data: bytes, context_sha256: str, session_id: str, connection_id: str) -> None:
        self.program = FrozenProgram(source, data, context_sha256, session_id, connection_id)
        self.phase = "staged"
        self.receipts: list[dict[str, Any]] = []
        self.launch_plan: dict[str, Any] | None = None
        self.identity_record: dict[str, Any] | None = None
        self.run_record: dict[str, Any] | None = None

    @property
    def source(self) -> str:
        return self.program.source

    @property
    def data(self) -> bytes:
        return self.program.data

    @property
    def sha256(self) -> str:
        return self.program.sha256

    @property
    def remote_path(self) -> str:
        return self.program.remote_path

    @property
    def context_sha256(self) -> str:
        return self.program.context_sha256

    @property
    def session_id(self) -> str:
        return self.program.session_id

    @property
    def connection_id(self) -> str:
        return self.program.connection_id

    def record(self) -> dict[str, Any]:
        return {
            "schema_version": "carvera.job_file.v1",
            "source": self.source,
            "bytes": len(self.data),
            "sha256": self.sha256,
            "context_sha256": self.context_sha256,
            "backend_session_id": self.session_id,
            "connection_id": self.connection_id,
            "remote_path": self.remote_path,
            "phase": self.phase,
            "receipts": self.receipts,
            "launch_plan": self.launch_plan,
            "reported_identity": self.identity_record,
            "job_run": self.run_record,
            "execution_admitted": False,
            "motion_completed": False,
        }

    def matches(self, session: str, connection: str, context: object) -> bool:
        return (session, connection, context_digest(context)) == (
            self.session_id,
            self.connection_id,
            self.context_sha256,
        )

    def begin(self, action: str) -> dict[str, Any]:
        expected = {"upload": "staged", "download": "uploaded", "compile": "verified"}
        if expected.get(action) != self.phase:
            raise ValueError("This file operation is unavailable; unresolved operations are never retried")
        self.phase = action + "_pending"
        if action == "compile":
            return {"operation": "job.start", "parameters": {"path": self.remote_path}}
        params: dict[str, Any] = {"path": self.remote_path, "timeout": 120}
        if action == "upload":
            params["data_base64"] = base64.b64encode(self.data).decode("ascii")
        return params

    def accept(self, action: str, response: Response) -> None:
        if self.phase != action + "_pending":
            raise ValueError("Unexpected job file response")
        envelope = response.envelope
        receipt = {
            "action": action,
            "request_id": envelope.get("id"),
            "request_sha256": response.request_sha256,
            "response_sha256": response.response_sha256,
            "received_at_s": response.received_at_s,
            "elapsed_ms": response.elapsed_ms,
            "outcome": "unverified_response",
        }
        self.receipts.append(receipt)
        self.phase = "unresolved"
        result = envelope.get("result")
        if envelope.get("ok") is not True or not isinstance(result, dict):
            receipt["error"] = envelope.get("error")
            raise ValueError("The backend refused the operation or its outcome is unresolved")
        if action == "compile":
            expected = compile_operation("job.start", {"path": self.remote_path})
            if context_digest(result) != context_digest(expected):
                raise ValueError("The backend launch plan differs from the exact reviewed file")
            self.launch_plan = result
            self.phase = "reviewed"
            receipt["outcome"] = "plan_compiled_only"
            return
        if (
            result.get("outcome") != "transfer_acknowledged"
            or result.get("direction") != action
            or result.get("path") != self.remote_path
            or type(result.get("size")) is not int
            or result["size"] != len(self.data)
            or result.get("sha256") != self.sha256
            or result.get("md5") != hashlib.md5(self.data).hexdigest()
            or result.get("readback_verified") is not False
            or result.get("completion") != f"Info: {action} success: {self.remote_path}."
        ):
            raise ValueError("The transfer receipt does not identify the exact frozen file")
        if action == "download":
            encoded = result.get("data_base64")
            if not isinstance(encoded, str) or len(encoded) > (MAX_FILE * 4 // 3 + 4):
                raise ValueError("Invalid readback bytes")
            try:
                data = base64.b64decode(encoded, validate=True)
            except ValueError:
                raise ValueError("Invalid readback bytes") from None
            if data != self.data:
                raise ValueError("Controller readback differs from the frozen program")
            self.phase = "verified"
            receipt["outcome"] = "exact_bytes_readback_verified"
        else:
            self.phase = "uploaded"
            receipt["outcome"] = "transfer_acknowledged_readback_pending"

    def fail(self, action: str, error: Exception) -> None:
        self.phase = "unresolved"
        self.receipts.append(
            {
                "action": action,
                "outcome": "not_submitted"
                if getattr(error, "submission", None) == "not_submitted"
                else "backend_response_unknown",
                "request_id": getattr(error, "request_id", None),
                "error_type": type(error).__name__,
            }
        )
