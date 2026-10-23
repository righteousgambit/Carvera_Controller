"""Retained preview text, bound to one completed local selection generation."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from carveracontroller.machine.program_bytes import MAX_PROGRAM_BYTES


@dataclass(frozen=True)
class RetainedProgramSource:
    local_path: str
    source_hash: str
    lines: tuple[str, ...]
    generation: int

    def __post_init__(self) -> None:
        # Content validation belongs on the worker; rebinding a restored source
        # generation must not join/hash a large program on the UI thread.
        if not isinstance(self.local_path, str) or not self.local_path or "\x00" in self.local_path:
            raise ValueError("A retained program requires its selected local path")
        if not isinstance(self.source_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", self.source_hash):
            raise ValueError("A retained program requires an exact source identity")
        if not isinstance(self.lines, tuple) or type(self.generation) is not int or self.generation < 0:
            raise ValueError("Retained lines and a nonnegative selection generation are required")

    def matches(self, local: str, remote: str, digest: str | None, generation: int) -> bool:
        return not remote and local == self.local_path and digest == self.source_hash and generation == self.generation

    def rebound(self, generation: int) -> RetainedProgramSource:
        return replace(self, generation=generation)

    def text(self, *, cancelled: Callable[[], bool] = lambda: False) -> str:
        """Validate the exact retained text on the analysis worker, without I/O."""
        digest = hashlib.sha256()
        count = 0
        for line in self.lines:
            if cancelled():
                raise InterruptedError("Retained program analysis cancelled")
            if not isinstance(line, str):
                raise ValueError("Retained program lines must be text")
            for start in range(0, len(line), 4096):
                if cancelled():
                    raise InterruptedError("Retained program analysis cancelled")
                data = line[start : start + 4096].encode("utf-8")
                count += len(data)
                if count > MAX_PROGRAM_BYTES:
                    raise ValueError("Operation analysis limit is 64 MB")
                digest.update(data)
        if digest.hexdigest() != self.source_hash:
            raise ValueError("Retained program text differs from its displayed source identity")
        result = "".join(self.lines)
        if cancelled():
            raise InterruptedError("Retained program analysis cancelled")
        return result
