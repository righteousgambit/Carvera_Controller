"""Operation tree, tool-bank planning and conservative recovery evidence.

This module never issues machine commands. Line numbers are one-based and
inclusive; unknown initial modal state is deliberately not filled from defaults.
Time is nominal commanded time, without acceleration, tool changes or dwell
controller overhead. Bounds belong to program coordinates, not machine space.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any, Optional, cast

_WORD = re.compile(r"([A-Za-z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))")
_COMMENT = re.compile(r"\(([^()]*)\)")
_OP = re.compile(r"^(?:operation|op(?:eration)?\s*name|toolpath|strategy)\s*[:=]\s*(.+)$", re.I)
_CAM = re.compile(
    r"^(?:\d+d\s+)?(?:adaptive|face|facing|contour|pocket|drill|bore|thread|chamfer|"
    r"parallel|scallop|trace|engrave|flat|horizontal|ramp|rest|finish|rough|slot|spiral|morph)",
    re.I,
)
Point = tuple[float, float, float]
Bounds = tuple[Point, Point]
Position = tuple[Optional[float], Optional[float], Optional[float]]


@dataclass(frozen=True)
class ModalState:
    units: str | None = None
    distance: str | None = None
    plane: str | None = None
    feed_mode: str | None = None
    arc_distance: str | None = None
    wcs: str | None = None
    motion: int | None = None
    feed: float | None = None
    spindle_speed: float | None = None
    spindle: str | None = None
    coolant: str | None = None
    tool: int | None = None
    pending_tool: int | None = None
    position_mm: tuple[float | None, float | None, float | None] = (None, None, None)
    tool_length_command: str | None = None
    recovery_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class MotionSegment:
    """Canonical linear segment in its named work coordinate frame.

    Rotary motion is intentionally unresolved until kinematics are supplied.
    Arc segments respect the caller's maximum chord error in millimetres.
    """

    line_number: int
    start_mm: Point
    end_mm: Point
    tool_id: int | None
    rapid: bool
    cutting: bool
    rotary: tuple[float, ...] | None = None
    wcs: str | None = None


@dataclass(frozen=True)
class Checkpoint:
    line_number: int
    state: ModalState


@dataclass(frozen=True)
class Operation:
    id: str
    name: str
    start_line: int
    end_line: int
    tool_ids: tuple[int, ...]
    bounds_mm: Bounds | None
    estimated_seconds: float | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolBank:
    index: int
    start_line: int
    end_line: int
    slots: tuple[tuple[int, int], ...]
    reload_required: bool
    instructions: tuple[str, ...]


@dataclass(frozen=True)
class RecoveryPlan:
    line_number: int
    ready: bool
    commands: tuple[str, ...]
    warnings: tuple[str, ...]
    state: ModalState


@dataclass(frozen=True)
class TimelineEvent:
    timestamp: float
    kind: str
    executed_line: int | None = None
    queued_line: int | None = None
    message: str = ""


class ExecutionTimeline:
    """Bounded events; queued reports never advance executed progress."""

    def __init__(self, capacity: int = 10000, gap_seconds: float = 2.0):
        if capacity < 2 or gap_seconds <= 0:
            raise ValueError("Timeline capacity must be >= 2 and gap must be positive")
        self.events: deque[TimelineEvent] = deque(maxlen=capacity)
        self.gap_seconds = gap_seconds
        self.executed_line: int | None = None
        self.queued_line: int | None = None
        self._last_timestamp: float | None = None

    def append(self, event: TimelineEvent) -> None:
        if not math.isfinite(event.timestamp):
            raise ValueError("Timestamp must be finite")
        for value in (event.executed_line, event.queued_line):
            if value is not None and value < 1:
                raise ValueError("Line numbers are one-based")
        if self._last_timestamp is not None:
            if event.timestamp < self._last_timestamp:
                raise ValueError("Timeline timestamps must be monotonic")
            if event.timestamp - self._last_timestamp > self.gap_seconds:
                self.events.append(TimelineEvent(event.timestamp, "gap", message="Telemetry gap; motion is unknown"))
        if event.executed_line is not None:
            self.executed_line = event.executed_line
        if event.queued_line is not None:
            self.queued_line = event.queued_line
        self.events.append(event)
        self._last_timestamp = event.timestamp


def _operation_name(raw: str) -> str | None:
    comments = _COMMENT.findall(raw)
    if ";" in raw:
        comments.append(raw.split(";", 1)[1].strip())
    for comment in comments:
        comment = comment.strip()
        match = _OP.match(comment)
        if match:
            return match.group(1).strip()
        # Fusion posts standalone operation labels, separate from tool metadata.
        if _CAM.match(comment) and not re.search(r"\b(?:D|CR|ZMIN|T)\s*[=\d]", comment, re.I):
            return comment
    return None


def _arc_points(
    start: Point,
    end: Point,
    words: dict[str, float],
    state: ModalState,
    cw: bool,
    tolerance_mm: float,
    max_segments: int,
) -> tuple[list[Point], float, list[Point]]:
    if "P" in words:
        raise ValueError("Multi-turn P arcs require a machine-specific interpreter")
    if state.plane not in ("G17", "G18", "G19"):
        raise ValueError("Arc plane is unknown")
    # G18 uses ZX so positive rotation follows the right-hand plane normal.
    u, v, axial, ij = {"G17": (0, 1, 2, "IJ"), "G18": (2, 0, 1, "KI"), "G19": (1, 2, 0, "JK")}[state.plane]
    scale = 25.4 if state.units == "G20" else 1.0
    x, y = start[u], start[v]
    ex, ey = end[u], end[v]
    if "R" in words:
        rword = words["R"] * scale
        radius = abs(rword)
        chord = math.hypot(ex - x, ey - y)
        if chord == 0 or chord > 2 * radius + 1e-7:
            raise ValueError("Invalid R arc radius or full-circle R arc")
        height = math.sqrt(max(0.0, radius * radius - chord * chord / 4))
        sign = (-1 if cw else 1) * (-1 if rword < 0 else 1)
        cx = (x + ex) / 2 - sign * (ey - y) * height / chord
        cy = (y + ey) / 2 + sign * (ex - x) * height / chord
    else:
        if state.arc_distance is None:
            raise ValueError("Arc center mode is unknown; set G91.1 or G90.1")
        if not any(key in words for key in ij):
            raise ValueError("Arc has no center or radius")
        if state.arc_distance == "G90.1":
            if not all(key in words for key in ij):
                raise ValueError("Absolute arc center is incomplete")
            cx, cy = (words[key] * scale for key in ij)
        else:
            cx, cy = x + words.get(ij[0], 0) * scale, y + words.get(ij[1], 0) * scale
        radius = math.hypot(x - cx, y - cy)
        if radius <= 0 or abs(math.hypot(ex - cx, ey - cy) - radius) > max(0.01, radius * 1e-4):
            raise ValueError("Arc endpoint does not match its center radius")
    if not all(math.isfinite(value) for value in (cx, cy, radius)):
        raise ValueError("Arc center or radius exceeds finite geometry range")
    a = math.atan2(y - cy, x - cx)
    b = math.atan2(ey - cy, ex - cx)
    sweep = ((a - b) if cw else (b - a)) % (2 * math.pi)
    if math.hypot(ex - x, ey - y) < 1e-8:
        sweep = 2 * math.pi
    points = [start, end]
    for angle in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
        delta = ((a - angle) if cw else (angle - a)) % (2 * math.pi)
        if delta <= sweep + 1e-8:
            point = list(start)
            point[u], point[v] = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
            point[axial] = start[axial] + (end[axial] - start[axial]) * delta / sweep if sweep else start[axial]
            points.append((point[0], point[1], point[2]))
    # Stable sagitta formula: theta = 4 asin(sqrt(error / (2 radius))).
    max_angle = min(math.pi / 2, 4 * math.asin(math.sqrt(min(tolerance_mm / (2 * radius), 0.5))))
    count = math.ceil(sweep / max_angle) if max_angle > 0 else max_segments + 1
    if count > max_segments:
        raise ValueError(f"Arc subdivision exceeds {max_segments} segments at requested chord tolerance")
    sampled = [start]
    for index in range(1, max(1, count)):
        fraction = index / count
        angle = a + (-1 if cw else 1) * sweep * fraction
        point = list(start)
        point[u], point[v] = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
        point[axial] = start[axial] + (end[axial] - start[axial]) * fraction
        sampled.append((point[0], point[1], point[2]))
    sampled.append(end)
    return points, math.hypot(radius * sweep, end[axial] - start[axial]), sampled


class ProgramOperations:
    def __init__(
        self,
        lines: tuple[str, ...],
        operations: tuple[Operation, ...],
        checkpoints: tuple[Checkpoint, ...],
        file_hash: str,
        motion_segments: tuple[MotionSegment, ...] = (),
        unresolved_motion_lines: tuple[int, ...] = (),
    ):
        self.lines = lines
        self.operations = operations
        self.checkpoints = checkpoints
        self.file_hash = file_hash
        self.motion_segments = motion_segments
        self.unresolved_motion_lines = unresolved_motion_lines

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        rapid_mm_min: float | None = None,
        dwell_p_seconds: float | None = None,
        arc_tolerance_mm: float = 0.1,
        max_arc_segments: int = 10000,
    ) -> ProgramOperations:
        if rapid_mm_min is not None and (not math.isfinite(rapid_mm_min) or rapid_mm_min <= 0):
            raise ValueError("Rapid estimate must be a positive finite speed")
        if dwell_p_seconds is not None and (not math.isfinite(dwell_p_seconds) or dwell_p_seconds <= 0):
            raise ValueError("Dwell P unit must be a positive finite seconds multiplier")
        if not math.isfinite(arc_tolerance_mm) or arc_tolerance_mm <= 0:
            raise ValueError("Arc chord tolerance must be positive and finite")
        if max_arc_segments < 1:
            raise ValueError("Maximum arc segments must be positive")
        lines = tuple(text.splitlines())
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        state = ModalState()
        checkpoints: list[Checkpoint] = []
        result: list[Operation] = []
        segments: list[MotionSegment] = []
        unresolved: list[int] = []
        start_line, name = 1, "Program setup"
        tools: list[int] = []
        points: list[Point] = []
        warnings: list[str] = []
        seconds, timing_known, geometry_known = 0.0, True, True
        had_motion = False

        def finish(end: int) -> None:
            if end < start_line:
                return
            bounds: Bounds | None = None
            if points and geometry_known:
                bounds = (
                    cast(Point, tuple(min(p[a] for p in points) for a in range(3))),
                    cast(Point, tuple(max(p[a] for p in points) for a in range(3))),
                )
            oid = hashlib.sha256(f"{digest}:{start_line}:{end}".encode()).hexdigest()[:20]
            result.append(
                Operation(
                    oid,
                    name,
                    start_line,
                    end,
                    tuple(tools),
                    bounds,
                    seconds if timing_known else None,
                    tuple(dict.fromkeys(warnings)),
                )
            )

        for number, raw in enumerate(lines, 1):
            label = _operation_name(raw)
            if label:
                finish(number - 1)
                start_line, name = number, label
                tools, points, warnings = [], [], []
                seconds, timing_known, geometry_known = 0.0, True, True
                had_motion = False
            code = _COMMENT.sub(" ", raw).split(";", 1)[0].strip()
            if not code or code == "%":
                checkpoints.append(Checkpoint(number, state))
                continue
            if re.search(r"[#\[\]]|\b(?:IF|WHILE|CALL|SUB|GOTO)\b", code, re.I):
                unresolved.append(number)
                warning = f"Line {number}: expressions or control flow require controller interpretation"
                warnings.append(warning)
                state = replace(
                    state, recovery_errors=(*state.recovery_errors, warning), position_mm=(None, None, None)
                )
                timing_known = geometry_known = False
                checkpoints.append(Checkpoint(number, state))
                continue
            tokens = [(m[1].upper(), float(m[2])) for m in _WORD.finditer(code)]
            leftover = _WORD.sub("", code).strip()
            if leftover:
                warning = f"Line {number}: unparsed syntax {leftover!r}"
                warnings.append(warning)
                state = replace(state, recovery_errors=(*state.recovery_errors, warning))
                timing_known = geometry_known = False
            if any(not math.isfinite(value) for _, value in tokens):
                unresolved.append(number)
                warning = f"Line {number}: nonfinite numeric word"
                warnings.append(warning)
                state = replace(
                    state, recovery_errors=(*state.recovery_errors, warning), position_mm=(None, None, None)
                )
                timing_known = geometry_known = False
                checkpoints.append(Checkpoint(number, state))
                continue
            words = dict(tokens)
            gs = [value for key, value in tokens if key == "G"]
            ms = [value for key, value in tokens if key == "M"]
            selected = words.get("T", state.pending_tool)
            if 6 in ms and had_motion and selected != state.tool:
                finish(number - 1)
                start_line, name = number, f"Tool {selected:g}" if selected is not None else "Tool change"
                tools, points, warnings = [], [], []
                seconds, timing_known, geometry_known = 0.0, True, True
                had_motion = False
            changes: dict[str, Any] = {}
            for g in gs:
                command = f"G{g:g}"
                if g in (20, 21):
                    changes["units"] = command
                elif g in (90, 91):
                    changes["distance"] = command
                elif g in (90.1, 91.1):
                    changes["arc_distance"] = command
                elif g in (17, 18, 19):
                    changes["plane"] = command
                elif g in (93, 94, 95):
                    changes["feed_mode"] = command
                elif g in (54, 55, 56, 57, 58, 59):
                    if state.wcs is not None and state.wcs != command:
                        changes["position_mm"] = (None, None, None)
                        geometry_known = False
                        warnings.append(f"Line {number}: WCS changed; combined bounds require measured offset mapping")
                    changes["wcs"] = command
                elif g in (0, 1, 2, 3):
                    changes["motion"] = int(g)
                elif g == 80:
                    changes["motion"] = None
                elif g == 49:
                    changes["tool_length_command"] = "G49"
                elif g == 43 and "H" in words:
                    changes["tool_length_command"] = f"G43 H{words['H']:g}"
                elif g not in (4, 53, 40):
                    warning = f"Line {number}: unsupported modal command {command}"
                    warnings.append(warning)
                    changes["recovery_errors"] = (*state.recovery_errors, warning)
                    timing_known = geometry_known = False
            if changes.get("feed_mode") in ("G94", "G95") and changes["feed_mode"] != state.feed_mode:
                # Inverse minutes, distance/minute and distance/revolution are
                # different quantities. Mode transitions require a new feed.
                changes["feed"] = None
            if "F" in words:
                changes["feed"] = words["F"]
            if "S" in words and 4 not in gs and (not ms or any(m in (3, 4) for m in ms)):
                changes["spindle_speed"] = words["S"]
            if "T" in words:
                if words["T"].is_integer() and words["T"] >= 0:
                    changes["pending_tool"] = int(words["T"])
                else:
                    changes["recovery_errors"] = (*state.recovery_errors, f"Line {number}: invalid tool number")
            if 6 in ms:
                changes["tool"] = changes.get("pending_tool", state.pending_tool)
            for m in ms:
                if m in (3, 4, 5):
                    changes["spindle"] = f"M{m:g}"
                elif m == 9:
                    changes["coolant"] = "M9"
                elif m in (7, 8):
                    active = changes.get("coolant", state.coolant)
                    command = f"M{m:g}"
                    changes["coolant"] = " ".join(sorted(set((active or "").split()) - {"M9"} | {command}))
                elif m not in (0, 1, 2, 6, 30):
                    warning = f"Line {number}: unsupported command M{m:g}"
                    warnings.append(warning)
                    changes["recovery_errors"] = (*state.recovery_errors, warning)
            state = replace(state, **changes)
            if state.tool is not None and state.tool not in tools and (6 in ms or any(a in words for a in "XYZABCUVW")):
                tools.append(state.tool)
            if 4 in gs:
                if "P" in words and words["P"] >= 0 and dwell_p_seconds is not None:
                    seconds += words["P"] * dwell_p_seconds
                elif "S" in words and words["S"] >= 0:
                    seconds += words["S"]
                else:
                    timing_known = False
                    warnings.append(f"Line {number}: dwell duration/unit is not established")
            elif any(a in words for a in "XYZABCUVW") or (state.motion in (2, 3) and any(a in words for a in "IJKR")):
                had_motion = True
                if 53 in gs:
                    unresolved.append(number)
                    # Machine-coordinate motion is nonmodal, and cannot establish WCS coordinates.
                    state = replace(state, position_mm=(None, None, None))
                    timing_known = False
                    warnings.append(f"Line {number}: G53 motion excluded from program-coordinate bounds")
                elif any(a in words for a in "ABCUVW") or state.units is None or state.distance is None:
                    unresolved.append(number)
                    timing_known = geometry_known = False
                    warning = f"Line {number}: rotary/auxiliary motion or unknown units/distance; geometry unavailable"
                    warnings.append(warning)
                    state = replace(state, position_mm=(None, None, None))
                    if any(a in words for a in "ABCUVW"):
                        state = replace(state, recovery_errors=(*state.recovery_errors, warning))
                else:
                    scale = 25.4 if state.units == "G20" else 1.0
                    old = state.position_mm
                    new = cast(
                        Position,
                        tuple(
                            (
                                words[a] * scale
                                if state.distance == "G90"
                                else None
                                if old[i] is None
                                else old[i] + words[a] * scale
                            )
                            if a in words
                            else old[i]
                            for i, a in enumerate("XYZ")
                        ),
                    )
                    if all(v is not None for v in old) and all(v is not None for v in new):
                        p, q = cast(Point, old), cast(Point, new)
                        try:
                            if not all(math.isfinite(v) for v in (*p, *q)):
                                raise ValueError("Motion endpoint exceeds finite geometry range")
                            if state.motion not in (0, 1, 2, 3) or state.recovery_errors:
                                raise ValueError("Motion is unresolved after unknown modal state")
                            path, length, sampled = (
                                _arc_points(p, q, words, state, state.motion == 2, arc_tolerance_mm, max_arc_segments)
                                if state.motion in (2, 3)
                                else ([p, q], math.dist(p, q), [p, q])
                            )
                            if state.wcs is None:
                                unresolved.append(number)
                                warnings.append(f"Line {number}: work coordinate frame is unknown")
                            segments.extend(
                                MotionSegment(
                                    number,
                                    a,
                                    b,
                                    state.tool,
                                    state.motion == 0,
                                    state.motion in (1, 2, 3),
                                    wcs=state.wcs,
                                )
                                for a, b in zip(sampled, sampled[1:])
                            )
                            points.extend(path)
                            if state.motion == 0 and rapid_mm_min:
                                seconds += 60 * length / rapid_mm_min
                            elif state.motion in (1, 2, 3) and state.feed and state.feed > 0:
                                if state.feed_mode == "G94":
                                    seconds += 60 * length / (state.feed * scale)
                                elif state.feed_mode == "G93" and "F" in words:
                                    seconds += 60 / state.feed
                                else:
                                    timing_known = False
                            else:
                                timing_known = False
                        except ValueError as exc:
                            unresolved.append(number)
                            warning = f"Line {number}: {exc}"
                            warnings.append(warning)
                            state = replace(state, recovery_errors=(*state.recovery_errors, warning))
                            timing_known = geometry_known = False
                    else:
                        unresolved.append(number)
                        timing_known = geometry_known = False
                        warnings.append(f"Line {number}: motion starts from an unknown position")
                        if all(v is not None for v in new):
                            points.append(cast(Point, new))
                    state = replace(state, position_mm=new if state.motion in (0, 1, 2, 3) else (None, None, None))
            checkpoints.append(Checkpoint(number, state))
        finish(len(lines))
        return cls(lines, tuple(result), tuple(checkpoints), digest, tuple(segments), tuple(dict.fromkeys(unresolved)))

    def plan_tool_banks(self, slot_count: int = 6) -> tuple[ToolBank, ...]:
        """Partition ordered tool usage into banks; never map T numbers modulo slots.

        These are setup plans, not rewritten programs. Manual reload checkpoints
        must be inserted and qualified before physical execution.
        """
        if slot_count < 1:
            raise ValueError("Slot count must be positive")
        if not self.lines:
            return ()
        banks: list[ToolBank] = []
        start, bank_tools = 1, []
        previous: int | None = None
        for checkpoint in self.checkpoints:
            tool = checkpoint.state.tool
            if tool is None or tool == previous:
                continue
            previous = tool
            if tool not in bank_tools:
                if len(bank_tools) == slot_count:
                    banks.append(self._bank(len(banks) + 1, start, checkpoint.line_number - 1, bank_tools))
                    start, bank_tools = checkpoint.line_number, []
                bank_tools.append(tool)
        banks.append(self._bank(len(banks) + 1, start, len(self.lines), bank_tools))
        return tuple(banks)

    @staticmethod
    def _bank(index: int, start: int, end: int, tools: list[int]) -> ToolBank:
        instructions = (
            (
                "Retract to verified safe position and stop spindle before changing bank",
                "Reload assigned slots and verify physical tool identities",
                "Measure replacement tools and validate offsets before continuing",
            )
            if index > 1
            else ()
        )
        return ToolBank(index, start, end, tuple(enumerate(tools, 1)), index > 1, instructions)

    def recovery_plan(
        self,
        line_number: int,
        *,
        safe_machine_z: float | None = None,
        verified_machine_position: Point | None = None,
        clearance_verified: bool = False,
    ) -> RecoveryPlan:
        """Draft modal restoration only. Never includes automatic tool changes or approach moves.

        Position and clearance evidence is supplied by the caller from physical
        qualification, not inferred from this parser. A ready plan still needs
        operator review and a separately verified approach to the resume point.
        """
        if not 1 <= line_number <= len(self.lines):
            raise ValueError("Resume line is outside program")
        state = self.checkpoints[line_number - 2].state if line_number > 1 else ModalState()
        warnings = list(state.recovery_errors)
        required = (
            "units",
            "distance",
            "plane",
            "feed_mode",
            "wcs",
            "tool",
            "spindle",
            "coolant",
            "tool_length_command",
        )
        warnings.extend(f"Unknown {key.replace('_', ' ')}" for key in required if getattr(state, key) is None)
        if state.feed_mode != "G94":
            warnings.append("Recovery supports only G94 units-per-minute feed")
        if state.feed is None or state.feed <= 0:
            warnings.append("Feed is not established")
        if state.spindle in ("M3", "M4") and (state.spindle_speed is None or state.spindle_speed <= 0):
            warnings.append("Spindle speed is not established")
        if not all(v is not None for v in state.position_mm):
            warnings.append("Resume program position is unknown")
        if not clearance_verified:
            warnings.append("Retract and re-entry clearance must be physically verified")
        if safe_machine_z is None or not math.isfinite(safe_machine_z):
            warnings.append("Safe machine Z is not established")
        if verified_machine_position is None or not all(math.isfinite(v) for v in verified_machine_position):
            warnings.append("Current machine position is not verified")
        if (
            safe_machine_z is not None
            and verified_machine_position is not None
            and safe_machine_z < verified_machine_position[2]
        ):
            warnings.append("Safe Z would descend from the current machine position")
        target_errors = self.checkpoints[line_number - 1].state.recovery_errors
        warnings.extend(error for error in target_errors if error not in state.recovery_errors)
        if warnings:
            return RecoveryPlan(line_number, False, (), tuple(dict.fromkeys(warnings)), state)
        # Restoration drafts intentionally omit M3/M4, M6 and approach motion.
        commands = (
            "M5",
            "M9",
            "G90",
            f"G53 G0 Z{safe_machine_z:g}",
            f"{state.units} {state.plane} {state.feed_mode} {state.wcs}",
            state.tool_length_command or "G49",
            f"F{state.feed:g}",
            state.distance or "G90",
        )
        return RecoveryPlan(
            line_number,
            True,
            commands,
            ("Confirm installed tool and offsets; re-entry and spindle start require a separate reviewed plan",),
            state,
        )


def summarize_operations(lines: Iterable[str]) -> tuple[Operation, ...]:
    return ProgramOperations.from_text("\n".join(lines)).operations
