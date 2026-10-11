"""Recognise structured results in the machine's console output.

Probing cycles and tool calibrations report their findings as printed text
scrolling past in the log. The numbers are there; nothing catches them, so
they are read by eye and retyped.

This watches the stream and emits a result once a cycle has finished. It
buffers, because a report spans several lines and only the last one says it
is complete.

Kivy-free by contract.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from .probe_results import ProbeResult, parse_probe_result
from .tool_history import TloReport, parse_tlo_report

# Enough to hold the longest report with room to spare. Bounded so a session
# left connected for days does not accumulate the entire log in memory.
MAX_BUFFERED_LINES = 60

# Lines that mean a cycle has finished and the buffer can be parsed.
_PROBE_TERMINATORS = (
    "center point is:",
    "corner found.",
    "average angle from",
)
_TLO_TERMINATOR = "max delta:"
_PROBE_FAILURE = "error: probe fail"


class ResultKind(Enum):
    PROBE = "probe"
    TLO = "tlo"


@dataclass
class ConsoleWatcher:
    """Feed it console lines; it calls back when a result completes."""

    on_probe_result: Callable[[ProbeResult], None] | None = None
    on_tlo_report: Callable[[TloReport], None] | None = None

    _buffer: list[str] = field(default_factory=list, repr=False)

    def feed(self, line: str) -> ResultKind | None:
        """Consume one console line. Returns the kind of result completed."""
        self._buffer.append(line)
        if len(self._buffer) > MAX_BUFFERED_LINES:
            del self._buffer[:-MAX_BUFFERED_LINES]

        lowered = line.strip().lower()

        if lowered.startswith(_TLO_TERMINATOR):
            report = parse_tlo_report(self._buffer)
            self._buffer.clear()
            if report is not None and self.on_tlo_report is not None:
                self.on_tlo_report(report)
            return ResultKind.TLO if report is not None else None

        if lowered.startswith(_PROBE_FAILURE) or any(t in lowered for t in _PROBE_TERMINATORS):
            result = parse_probe_result(self._buffer)
            self._buffer.clear()
            if result is not None and self.on_probe_result is not None:
                self.on_probe_result(result)
            return ResultKind.PROBE if result is not None else None

        return None

    def reset(self) -> None:
        """Discard partial output, on disconnect or at the start of a cycle."""
        self._buffer.clear()

    @property
    def buffered(self) -> int:
        return len(self._buffer)
