"""Detached local-program evidence; never establishes machine-file identity."""

from __future__ import annotations

import hashlib
import re
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from carveracontroller.machine.program_bytes import MAX_PROGRAM_BYTES, preview_digest

_OPERATION = re.compile(
    r"(?:operation(?:\s+name)?\s*[:=]|\(\s*(?:(?:2D|3D)\s+)?(?:adaptive|pocket|contour|drill|face|bore|trace|engrave)[^\r\n)]*)([^\r\n]*)",
    re.I,
)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class PreparedProgramManifest:
    local_path: str
    sha256: str
    parsed_lines_sha256: str
    operations: tuple[tuple[int, str, str], ...]
    operation_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.local_path, str) or not self.local_path or "\x00" in self.local_path:
            raise ValueError("A local program path is required")
        if not _DIGEST.fullmatch(self.sha256) or not _DIGEST.fullmatch(self.parsed_lines_sha256):
            raise ValueError("Program manifest requires exact SHA-256 identities")
        if (
            type(self.operation_count) is not int
            or self.operation_count < len(self.operations)
            or len(self.operations) > 4096
        ):
            raise ValueError("Invalid retained operation count")
        for number, name, label in self.operations:
            if type(number) is not int or number < 1 or len(name) > 160 or len(label) > 160:
                raise ValueError("Invalid retained operation")

    def to_record(self) -> dict[str, Any]:
        return {
            "local_path": self.local_path,
            "sha256": self.sha256,
            "parsed_lines_sha256": self.parsed_lines_sha256,
            "identity_source": "retained reviewed program bytes",
            "machine_file_identity": "unverified",
            "operations": [{"line": n, "name": name, "label": label} for n, name, label in self.operations],
            "operation_count": self.operation_count,
            "operations_dropped": max(0, self.operation_count - len(self.operations)),
            "operations_retained": "latest",
            "requested_machine_path": None,
            "request": None,
        }


def prepare_program_manifest(
    local_path: str, raw: bytes, lines: Sequence[str], *, cancelled: Callable[[], bool] = lambda: False
) -> PreparedProgramManifest:
    if not isinstance(raw, bytes) or len(raw) > MAX_PROGRAM_BYTES:
        raise ValueError("Expected retained program bytes within the 64 MB budget")
    raw_hash = hashlib.sha256()
    for start in range(0, len(raw), 65536):
        if cancelled():
            raise InterruptedError("Program manifest preparation cancelled")
        raw_hash.update(raw[start : start + 65536])
    parsed = hashlib.sha256()
    operations: deque[tuple[int, str, str]] = deque(maxlen=4096)
    count = 0
    for number, line in enumerate(lines, 1):
        if cancelled():
            raise InterruptedError("Program manifest preparation cancelled")
        parsed.update(line.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))
        match = _OPERATION.search(line)
        if match:
            count += 1
            label = match.group(0).strip("(); ")
            operations.append((number, label.split(":", 1)[-1].strip()[:160], label[:160]))
    if cancelled():
        raise InterruptedError("Program manifest preparation cancelled")
    if preview_digest(raw) != parsed.hexdigest():
        raise ValueError("Retained program bytes do not match the prepared source lines")
    if cancelled():
        raise InterruptedError("Program manifest preparation cancelled")
    return PreparedProgramManifest(local_path, raw_hash.hexdigest(), parsed.hexdigest(), tuple(operations), count)
