"""Per-tool measurement history.

Advanced TLO calibration already probes a tool several times, prints every
measurement and a max delta, and then throws all of it away. That delta is
flute-to-flute height variation -- a free readout of grind quality, seating
and damage for every tool you own -- and it is worth keeping.

Single-digit microns is a good tool. A delta that grows over successive
calibrations is a tool going dull, damaged, or not seating in the collet.

Kivy-free by contract; storage is plain JSON so it can be inspected and
diffed outside the app.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

HISTORY_FORMAT_VERSION = 1

# Flute-to-flute variation, in mm. A well-ground endmill sits in single-digit
# microns; tens of microns means something is wrong with the tool or its seat.
GOOD_DELTA_MM = 0.010
SUSPECT_DELTA_MM = 0.030

_MEASUREMENT = re.compile(r"TLO value from measurement\s+(-?\d+)\s*:\s*(-?\d+\.?\d*)")
_MAX_DELTA = re.compile(r"Max delta\s*:\s*(-?\d+\.?\d*)")
_USING = re.compile(r"Using TLO value from measurement\s+(-?\d+)\s*:\s*(-?\d+\.?\d*)")


class ToolCondition(Enum):
    UNKNOWN = "unknown"
    GOOD = "good"
    WATCH = "watch"
    SUSPECT = "suspect"


@dataclass(frozen=True)
class TloReport:
    """One Advanced TLO calibration, as parsed from the machine's output."""

    measurements: tuple[float, ...]
    max_delta: float
    applied: float | None = None
    timestamp: float = 0.0

    @property
    def condition(self) -> ToolCondition:
        if not self.measurements:
            return ToolCondition.UNKNOWN
        if self.max_delta >= SUSPECT_DELTA_MM:
            return ToolCondition.SUSPECT
        if self.max_delta >= GOOD_DELTA_MM:
            return ToolCondition.WATCH
        return ToolCondition.GOOD

    def to_dict(self) -> dict[str, Any]:
        return {
            "measurements": list(self.measurements),
            "max_delta": self.max_delta,
            "applied": self.applied,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> TloReport:
        return TloReport(
            measurements=tuple(float(v) for v in data.get("measurements", ())),
            max_delta=float(data.get("max_delta", 0.0)),
            applied=None if data.get("applied") is None else float(data["applied"]),
            timestamp=float(data.get("timestamp", 0.0)),
        )


def parse_tlo_report(lines: Iterable[str], timestamp: float | None = None) -> TloReport | None:
    """Parse an Advanced TLO calibration report from machine output.

    Returns None when the text contains no measurements, which is the normal
    case for a single-shot calibration -- the repeat block is only printed
    when repeat count is greater than one.
    """
    measurements: list[float] = []
    max_delta: float | None = None
    applied: float | None = None

    for line in lines:
        found = _MEASUREMENT.search(line)
        if found and not _USING.search(line):
            measurements.append(float(found.group(2)))
            continue
        using = _USING.search(line)
        if using:
            applied = float(using.group(2))
            continue
        delta = _MAX_DELTA.search(line)
        if delta:
            max_delta = float(delta.group(1))

    if not measurements:
        return None
    if max_delta is None:
        max_delta = max(measurements) - min(measurements)

    return TloReport(
        measurements=tuple(measurements),
        max_delta=max_delta,
        applied=applied,
        timestamp=time.time() if timestamp is None else timestamp,
    )


@dataclass
class ToolRecord:
    tool_number: int
    reports: list[TloReport] = field(default_factory=list)
    cutting_seconds: float = 0.0
    life_limit_seconds: float | None = None
    label: str = ""

    @property
    def latest(self) -> TloReport | None:
        return self.reports[-1] if self.reports else None

    @property
    def condition(self) -> ToolCondition:
        latest = self.latest
        return latest.condition if latest else ToolCondition.UNKNOWN

    @property
    def delta_trend(self) -> float | None:
        """Change in max delta since the first recorded calibration.

        Positive means the tool is getting worse. None until there are two
        calibrations to compare.
        """
        if len(self.reports) < 2:
            return None
        return self.reports[-1].max_delta - self.reports[0].max_delta

    @property
    def life_used(self) -> float | None:
        """Fraction of the configured life consumed, or None if no limit."""
        if not self.life_limit_seconds:
            return None
        return self.cutting_seconds / self.life_limit_seconds

    @property
    def life_exhausted(self) -> bool:
        used = self.life_used
        return used is not None and used >= 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_number": self.tool_number,
            "reports": [r.to_dict() for r in self.reports],
            "cutting_seconds": self.cutting_seconds,
            "life_limit_seconds": self.life_limit_seconds,
            "label": self.label,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ToolRecord:
        return ToolRecord(
            tool_number=int(data["tool_number"]),
            reports=[TloReport.from_dict(r) for r in data.get("reports", [])],
            cutting_seconds=float(data.get("cutting_seconds", 0.0)),
            life_limit_seconds=(None if data.get("life_limit_seconds") is None else float(data["life_limit_seconds"])),
            label=str(data.get("label", "")),
        )


class ToolHistory:
    """Every tool's measurement and usage history."""

    def __init__(self, records: Sequence[ToolRecord] | None = None) -> None:
        self._records: dict[int, ToolRecord] = {r.tool_number: r for r in (records or ())}

    def record(self, tool_number: int) -> ToolRecord:
        """The record for a tool, created on first reference."""
        if tool_number not in self._records:
            self._records[tool_number] = ToolRecord(tool_number)
        return self._records[tool_number]

    def tools(self) -> list[ToolRecord]:
        return [self._records[n] for n in sorted(self._records)]

    def add_report(self, tool_number: int, report: TloReport) -> ToolRecord:
        record = self.record(tool_number)
        record.reports.append(report)
        return record

    def add_cutting_time(self, tool_number: int, seconds: float) -> ToolRecord:
        record = self.record(tool_number)
        record.cutting_seconds += max(0.0, seconds)
        return record

    def needing_attention(self) -> list[ToolRecord]:
        """Tools that are out of life or measuring badly."""
        return [
            r for r in self.tools() if r.life_exhausted or r.condition in (ToolCondition.WATCH, ToolCondition.SUSPECT)
        ]

    def to_json(self) -> str:
        return json.dumps(
            {"version": HISTORY_FORMAT_VERSION, "tools": [r.to_dict() for r in self.tools()]},
            indent=2,
        )

    @staticmethod
    def from_json(text: str) -> ToolHistory:
        """Load history, tolerating an empty or unreadable file.

        A corrupt history must not stop the app starting: losing the record is
        an inconvenience, refusing to run is not.
        """
        if not text.strip():
            return ToolHistory()
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                return ToolHistory()
            entries = data.get("tools", [])
            if not isinstance(entries, list):
                return ToolHistory()
            return ToolHistory([ToolRecord.from_dict(r) for r in entries])
        except (ValueError, KeyError, TypeError, AttributeError):
            return ToolHistory()
