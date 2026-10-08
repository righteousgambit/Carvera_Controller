"""Measurements taken on the machine, with nominals and history.

Two things want the same data. A first-article report asks whether one part
matches its drawing. Wear analysis asks how one feature on one part changes
across duty cycles. Both are a feature name, a nominal, a measured value and
a timestamp, so they share a model rather than diverging into two.

Honest about what this machine is: excellent for relative change on one part
measured the same way each time, unqualified for absolute certification
against a drawing. The report says so rather than implying otherwise.

Kivy-free by contract.
"""

from __future__ import annotations

import csv
import io
import json
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

LOG_FORMAT_VERSION = 1


class ToleranceState(Enum):
    UNKNOWN = "unknown"
    """No nominal or no tolerance given, so conformance is not a question."""

    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class Measurement:
    feature: str
    measured: float
    nominal: float | None = None
    tolerance: float | None = None
    units: str = "mm"
    timestamp: float = 0.0
    note: str = ""

    @property
    def deviation(self) -> float | None:
        if self.nominal is None:
            return None
        return self.measured - self.nominal

    @property
    def state(self) -> ToleranceState:
        deviation = self.deviation
        if deviation is None or self.tolerance is None:
            return ToleranceState.UNKNOWN
        return ToleranceState.PASS if abs(deviation) <= self.tolerance else ToleranceState.FAIL

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "measured": self.measured,
            "nominal": self.nominal,
            "tolerance": self.tolerance,
            "units": self.units,
            "timestamp": self.timestamp,
            "note": self.note,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Measurement:
        return Measurement(
            feature=str(data["feature"]),
            measured=float(data["measured"]),
            nominal=None if data.get("nominal") is None else float(data["nominal"]),
            tolerance=None if data.get("tolerance") is None else float(data["tolerance"]),
            units=str(data.get("units", "mm")),
            timestamp=float(data.get("timestamp", 0.0)),
            note=str(data.get("note", "")),
        )


@dataclass
class MeasurementSession:
    """One inspection run: a part, measured at a point in time."""

    part_id: str = ""
    label: str = ""
    cycles: float | None = None
    """Duty cycles the part had accumulated, for wear work. None if unknown."""

    measurements: list[Measurement] = field(default_factory=list)
    started: float = field(default_factory=lambda: time.time())

    def add(
        self,
        feature: str,
        measured: float,
        nominal: float | None = None,
        tolerance: float | None = None,
        note: str = "",
    ) -> Measurement:
        entry = Measurement(
            feature=feature,
            measured=measured,
            nominal=nominal,
            tolerance=tolerance,
            timestamp=time.time(),
            note=note,
        )
        self.measurements.append(entry)
        return entry

    @property
    def failures(self) -> list[Measurement]:
        return [m for m in self.measurements if m.state is ToleranceState.FAIL]

    @property
    def conforms(self) -> bool:
        """True when nothing measured fell outside a stated tolerance."""
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": LOG_FORMAT_VERSION,
            "part_id": self.part_id,
            "label": self.label,
            "cycles": self.cycles,
            "started": self.started,
            "measurements": [m.to_dict() for m in self.measurements],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> MeasurementSession:
        return MeasurementSession(
            part_id=str(data.get("part_id", "")),
            label=str(data.get("label", "")),
            cycles=None if data.get("cycles") is None else float(data["cycles"]),
            measurements=[Measurement.from_dict(m) for m in data.get("measurements", [])],
            started=float(data.get("started", 0.0)),
        )


def to_csv(sessions: Sequence[MeasurementSession]) -> str:
    """Flatten sessions to CSV, one row per measurement.

    Long format rather than a column per feature, so a new feature appearing
    partway through a study does not invalidate everything measured before it.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "part_id",
            "label",
            "cycles",
            "timestamp",
            "feature",
            "measured",
            "nominal",
            "deviation",
            "units",
            "state",
            "note",
        ]
    )
    for session in sessions:
        for m in session.measurements:
            deviation = m.deviation
            writer.writerow(
                [
                    session.part_id,
                    session.label,
                    "" if session.cycles is None else session.cycles,
                    f"{m.timestamp:.3f}",
                    m.feature,
                    f"{m.measured:.4f}",
                    "" if m.nominal is None else f"{m.nominal:.4f}",
                    "" if deviation is None else f"{deviation:.4f}",
                    m.units,
                    m.state.value,
                    m.note,
                ]
            )
    return buffer.getvalue()


def to_json(sessions: Sequence[MeasurementSession]) -> str:
    return json.dumps({"sessions": [s.to_dict() for s in sessions]}, indent=2)


def sessions_from_json(text: str) -> list[MeasurementSession]:
    """Load sessions, tolerating anything unreadable rather than raising."""
    if not text.strip():
        return []
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return []
        entries = data.get("sessions", [])
        if not isinstance(entries, list):
            return []
        return [MeasurementSession.from_dict(s) for s in entries]
    except (ValueError, KeyError, TypeError, AttributeError):
        return []


def feature_history(sessions: Iterable[MeasurementSession], feature: str) -> list[tuple[float | None, Measurement]]:
    """Every measurement of one feature, ordered for trending.

    Ordered by duty cycles where known, otherwise by time, so a wear study
    reads in the order it happened rather than the order it was filed.
    """
    found = [(session.cycles, m) for session in sessions for m in session.measurements if m.feature == feature]
    return sorted(found, key=lambda pair: (pair[0] is None, pair[0] or 0.0, pair[1].timestamp))


def wear_trend(sessions: Iterable[MeasurementSession], feature: str) -> float | None:
    """Change in a feature between its first and last measurement.

    None when there is nothing to compare, which is not the same as no wear.
    """
    history = feature_history(sessions, feature)
    if len(history) < 2:
        return None
    return history[-1][1].measured - history[0][1].measured


def format_report(session: MeasurementSession) -> str:
    """Render a first-article style report."""
    header = [f"Inspection report: {session.part_id or 'unidentified part'}"]
    if session.label:
        header.append(session.label)
    if session.cycles is not None:
        header.append(f"Duty cycles: {session.cycles:g}")
    header.append("")

    rows = [("Feature", "Nominal", "Measured", "Deviation", "Result")]
    for m in session.measurements:
        deviation = m.deviation
        rows.append(
            (
                m.feature,
                "-" if m.nominal is None else f"{m.nominal:.4f}",
                f"{m.measured:.4f}",
                "-" if deviation is None else f"{deviation * 1000:+.0f} um",
                m.state.value,
            )
        )

    widths = [max(len(row[i]) for row in rows) for i in range(5)]
    body = ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip() for row in rows]
    body.insert(1, "  ".join("-" * w for w in widths))

    footer = [""]
    if session.failures:
        footer.append(f"{len(session.failures)} feature(s) outside tolerance.")
    elif any(m.state is ToleranceState.PASS for m in session.measurements):
        footer.append("All toleranced features within tolerance.")
    footer.append(
        "Measured on a Carvera with a touch probe. Reliable for relative change on one part "
        "measured the same way each time; not a substitute for certified metrology."
    )
    return "\n".join(header + body + footer)
