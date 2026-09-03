"""Parse probing cycle results out of the machine's console output.

The probing cycles report their findings as printed text, which the operator
currently has to read out of the MDI log and retype. Parsing it turns a
transcript into numbers that can be shown, checked against a nominal, or
appended to a measurement log.

Format strings are taken from ZProbe.cpp. They are matched loosely enough to
survive whitespace changes but not so loosely that an unrelated line is read
as a measurement -- including one genuine upstream typo, "Betweeen" with
three E's, which appears only in the boss cycle.

Kivy-free by contract.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

_NUM = r"(-?\d+\.?\d*)"

# M461 uses "Distance Point 2 X surfaces"/"Distance between 2 Y surfaces";
# M462 uses "Distance Betweeen 2 X/Y surfaces". Both are accepted.
_X_DIAMETER = re.compile(rf"Distance (?:Point|between|Betweeen)\s+2\s+X\s+surfaces.*?:\s*{_NUM}", re.I)
_Y_DIAMETER = re.compile(rf"Distance (?:Point|between|Betweeen)\s+2\s+Y\s+surfaces.*?:\s*{_NUM}", re.I)
_CENTRE = re.compile(rf"Center Point is:\s*{_NUM}\s*,\s*{_NUM}", re.I)
_CORNER = re.compile(rf"Corner found.*?#154 as MCS\s*{_NUM}\s*,.*?#155 as MCS\s*{_NUM}", re.I)
_ANGLE = re.compile(rf"Average angle from\s+(\w+)\s+Axis is:\s*{_NUM}\s*degrees", re.I)
_BORE_FOUND = re.compile(r"Center of bore or rectangular pocket found", re.I)
_BOSS_FOUND = re.compile(r"Center of Boss or Rectangular Block found", re.I)
_PROBE_ERROR = re.compile(r"ERROR:\s*(Probe\s+fail[^\n]*)", re.I)


class ProbeResultKind(Enum):
    BORE = "bore"
    BOSS = "boss"
    CORNER = "corner"
    ANGLE = "angle"
    FAILURE = "failure"


@dataclass(frozen=True)
class ProbeResult:
    kind: ProbeResultKind
    x_diameter: float | None = None
    y_diameter: float | None = None
    centre_x: float | None = None
    centre_y: float | None = None
    corner_x: float | None = None
    corner_y: float | None = None
    angle_degrees: float | None = None
    angle_reference: str = ""
    error: str = ""

    @property
    def ovality(self) -> float | None:
        """Difference between the X and Y diameters of a round feature.

        The wear signature worth trending: a bore that starts round and goes
        oval is reporting its own wear, in microns, without any extra
        instrumentation. Only meaningful when both diameters were probed.
        """
        if self.x_diameter is None or self.y_diameter is None:
            return None
        return abs(self.x_diameter - self.y_diameter)

    @property
    def mean_diameter(self) -> float | None:
        present = [d for d in (self.x_diameter, self.y_diameter) if d is not None]
        if not present:
            return None
        return sum(present) / len(present)


def parse_probe_result(lines: Iterable[str]) -> ProbeResult | None:
    """Parse one cycle's output. Returns None when nothing was recognised."""
    text = list(lines)
    joined = "\n".join(text)

    failure = _PROBE_ERROR.search(joined)
    if failure:
        return ProbeResult(ProbeResultKind.FAILURE, error=failure.group(1).strip())

    angle = _ANGLE.search(joined)
    if angle:
        return ProbeResult(
            ProbeResultKind.ANGLE,
            angle_degrees=float(angle.group(2)),
            angle_reference=angle.group(1).upper(),
        )

    corner = _CORNER.search(joined)
    if corner:
        return ProbeResult(
            ProbeResultKind.CORNER,
            corner_x=float(corner.group(1)),
            corner_y=float(corner.group(2)),
        )

    x_dia = _X_DIAMETER.search(joined)
    y_dia = _Y_DIAMETER.search(joined)
    centre = _CENTRE.search(joined)
    if not (x_dia or y_dia or centre):
        return None

    if _BOSS_FOUND.search(joined):
        kind = ProbeResultKind.BOSS
    elif _BORE_FOUND.search(joined):
        kind = ProbeResultKind.BORE
    else:
        # Diameters without the summary line: assume a bore, which is the
        # cycle that reports "Distance Point 2 X surfaces".
        kind = ProbeResultKind.BORE

    return ProbeResult(
        kind,
        x_diameter=float(x_dia.group(1)) if x_dia else None,
        y_diameter=float(y_dia.group(1)) if y_dia else None,
        centre_x=float(centre.group(1)) if centre else None,
        centre_y=float(centre.group(2)) if centre else None,
    )


def format_probe_result(result: ProbeResult) -> str:
    """Render a result for display, one measurement per line."""
    if result.kind is ProbeResultKind.FAILURE:
        return result.error or "Probe failed."

    rows: list[tuple[str, str]] = []
    if result.kind is ProbeResultKind.ANGLE:
        rows.append((f"Angle from {result.angle_reference}", f"{result.angle_degrees:.3f} deg"))
    if result.kind is ProbeResultKind.CORNER:
        rows.append(("Corner X", f"{result.corner_x:.3f} mm"))
        rows.append(("Corner Y", f"{result.corner_y:.3f} mm"))
    if result.x_diameter is not None:
        rows.append(("X diameter", f"{result.x_diameter:.3f} mm"))
    if result.y_diameter is not None:
        rows.append(("Y diameter", f"{result.y_diameter:.3f} mm"))
    ovality = result.ovality
    if ovality is not None:
        rows.append(("Ovality", f"{ovality * 1000:.0f} um"))
    if result.centre_x is not None:
        rows.append(("Centre", f"X{result.centre_x:.3f} Y{result.centre_y:.3f}"))

    width = max((len(label) for label, _ in rows), default=0)
    return "\n".join(f"{label.ljust(width)}  {value}" for label, value in rows)
