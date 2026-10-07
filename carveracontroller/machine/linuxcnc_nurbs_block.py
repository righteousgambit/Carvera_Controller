"""Version-bound G5.2/G5.3 data-block interpretation for local study.

The enclosing program supplies pre-block modal context. No commands are emitted;
unknown expressions, modal changes and unrelated side effects are refused.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from .nurbs_geometry import NurbsCurve, linuxcnc_g52_curve, linuxcnc_g52_effective_order
from .spline_geometry import Point

INTERPRETER_REVISION = "46a388fd15a477b4bf2ce090919b0273074e7fc1"
_WORD = re.compile(r"([A-Za-z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
_COMMENT = re.compile(r"\([^()]*\)")


@dataclass(frozen=True)
class NurbsDataBlock:
    curve: NurbsCurve
    start_line: int
    end_line: int
    control_source_lines: tuple[int | None, ...]
    source_sha256: str
    interpreter_revision: str
    final_feed_per_minute_mm: float | None


def parse_linuxcnc_nurbs_block(
    text: str,
    *,
    start_mm: Point,
    plane: str,
    unit_scale: float,
    distance: str,
    start_line: int = 1,
    feed_per_minute_mm: float | None = None,
) -> NurbsDataBlock:
    """Interpret complete pinned-version data, retaining source/control identity.

    In G91 each control is relative to the pre-block current position: the
    interpreter updates current coordinates only at G5.3, not at each control.
    Every subsequent control requires explicit positive P in this version.
    Opening without axes uses P for the implicit current-position control;
    opening with axes uses P for the new control and implicit first weight1.
    """
    if plane not in ("G17", "G18", "G19") or distance not in ("G90", "G91") or unit_scale not in (1, 25.4):
        raise ValueError("NURBS requires explicit supported plane, units and distance mode")
    if type(unit_scale) not in (int, float) or type(start_line) is not int or start_line < 1:
        raise ValueError("NURBS context requires valid unit scale and positive source line")
    # Validate pre-block coordinates through the same preserved-curve boundary.
    linuxcnc_g52_curve((start_mm, start_mm, start_mm), (1, 1, 1))
    if feed_per_minute_mm is not None and (not math.isfinite(feed_per_minute_mm) or feed_per_minute_mm <= 0):
        raise ValueError("NURBS declared feed must be positive and finite")
    axes = {"G17": ("X", "Y"), "G18": ("X", "Z"), "G19": ("Y", "Z")}[plane]
    controls: list[Point] = [start_mm]
    weights = [1.0]
    sources: list[int | None] = [None]
    order, opened, closed = 3, False, False
    first_line, last_line = 0, 0
    for offset, raw in enumerate(text.splitlines()):
        number = start_line + offset
        code = _COMMENT.sub("", raw).split(";", 1)[0].strip()
        if not code:
            continue
        if closed:
            raise ValueError(f"Line{number}: source follows closing G5.3")
        tokens = [(m[1].upper(), float(m[2])) for m in _WORD.finditer(code)]
        if _WORD.sub("", code).strip() or any(not math.isfinite(v) for _, v in tokens):
            raise ValueError(f"Line{number}: NURBS syntax requires finite numeric words")
        keys = [k for k, _ in tokens]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Line{number}: duplicate NURBS words")
        words = dict(tokens)
        if "N" in words and (not words["N"].is_integer() or words["N"] < 0):
            raise ValueError(f"Line{number}: source line number must be a nonnegative integer")
        if words.get("G") == 5.3:
            if not opened or set(words) - {"G", "N"}:
                raise ValueError(f"Line{number}: invalid NURBS closure")
            closed, last_line = True, number
            continue
        if not opened:
            if words.get("G") != 5.2:
                raise ValueError(f"Line{number}: data block must open with G5.2")
            first_line, opened = number, True
        elif "G" in words and words["G"] != 5.2:
            raise ValueError(f"Line{number}: unrelated motion inside NURBS data block")
        if set(words) - {"G", "N", "P", "L", "F", *axes}:
            raise ValueError(f"Line{number}: unsupported modal or axis word inside NURBS data block")
        if "L" in words:
            l = words["L"]
            if l < 0 or not l.is_integer():
                raise ValueError(f"Line{number}: NURBS L must be a nonnegative integer")
            order = linuxcnc_g52_effective_order(int(l), previous_order=order)
        if "F" in words:
            if words["F"] <= 0:
                raise ValueError(f"Line{number}: NURBS feed must be positive")
            feed_per_minute_mm = words["F"] * unit_scale
            if not math.isfinite(feed_per_minute_mm):
                raise ValueError(f"Line{number}: converted NURBS feed overflows")
        present = [a in words for a in axes]
        if any(present) and not all(present):
            raise ValueError(f"Line{number}: both plane axes are required per control")
        if not any(present):
            if len(controls) != 1 or number != first_line:
                raise ValueError(f"Line{number}: control without plane axes")
            weights[0] = words.get("P", 1.0)
            if weights[0] <= 0:
                raise ValueError(f"Line{number}: first control weight must be positive")
            continue
        if words.get("P", -1) <= 0:
            raise ValueError(f"Line{number}: pinned interpreter requires positive explicit P for each control")
        xyz = list(start_mm)
        for axis in axes:
            index = "XYZ".index(axis)
            xyz[index] = words[axis] * unit_scale + (start_mm[index] if distance == "G91" else 0)
        controls.append((xyz[0], xyz[1], xyz[2]))
        weights.append(words["P"])
        sources.append(number)
        if len(controls) > 4096:
            raise ValueError("NURBS data block exceeds4096 controls")
    if not closed:
        raise ValueError("NURBS data block has no closing G5.3")
    return NurbsDataBlock(
        linuxcnc_g52_curve(controls, weights, order=order),
        first_line,
        last_line,
        tuple(sources),
        hashlib.sha256(text.encode()).hexdigest(),
        INTERPRETER_REVISION,
        feed_per_minute_mm,
    )
