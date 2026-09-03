"""Static checks on a G-code program against machine limits.

Catches, before the spindle turns, the mistakes this machine punishes: feeds
its axes cannot reach, spindle speeds outside the range it can hold, cutting
moves with the spindle stopped, and use of features known to be broken in
firmware.

Deliberately conservative. A false positive that stops someone running a good
program is worse than a missed warning, so every check here is grounded in a
documented machine limit or a known firmware defect rather than in a guess
about what makes a good toolpath.

Kivy-free by contract.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

# Carvera C1. Feeds in mm/min, from config_c1.json.
DEFAULT_MAX_FEED_XY = 3000.0
DEFAULT_MAX_FEED_Z = 2000.0
DEFAULT_MIN_RPM = 1000.0
DEFAULT_MAX_RPM = 15000.0

_WORD = re.compile(r"([A-Za-z])\s*(-?\d*\.?\d+)")
_CUTTING_MOVES = frozenset({1, 2, 3})


class Severity(Enum):
    ERROR = "error"
    """The machine cannot do this, or will be damaged trying."""

    WARNING = "warning"
    """Legal but likely wrong, or relies on something known to misbehave."""

    INFO = "info"


@dataclass(frozen=True)
class ProgramIssue:
    line_number: int
    """First line on which this issue occurs."""

    severity: Severity
    code: str
    message: str
    text: str = ""
    occurrences: int = 1
    """How many times it occurs. A modal bad feed can repeat thousands of
    times; reporting each one buries everything else."""


@dataclass(frozen=True)
class MachineLimits:
    max_feed_xy: float = DEFAULT_MAX_FEED_XY
    max_feed_z: float = DEFAULT_MAX_FEED_Z
    min_rpm: float = DEFAULT_MIN_RPM
    max_rpm: float = DEFAULT_MAX_RPM
    atc_tool_slots: int = 6


@dataclass
class _State:
    motion: int | None = None
    plane: int | None = None
    units_set: bool = False
    distance_set: bool = False
    spindle_on: bool = False
    spindle_rpm: float = 0.0
    feed: float = 0.0
    inch_mode: bool = False
    laser_mode: bool = False
    issues: list[ProgramIssue] = field(default_factory=list)


def _words(line: str) -> list[tuple[str, float]]:
    """Strip comments, then split into (letter, value) pairs."""
    text = re.sub(r"\(.*?\)", " ", line)
    text = text.split(";")[0]
    return [(m.group(1).upper(), float(m.group(2))) for m in _WORD.finditer(text)]


def check_program(lines: Iterable[str], limits: MachineLimits | None = None) -> list[ProgramIssue]:
    """Check ``lines`` of G-code, returning issues in program order."""
    limits = limits or MachineLimits()
    state = _State()

    for index, raw in enumerate(lines, start=1):
        words = _words(raw)
        if not words:
            continue
        text = raw.strip()

        gcodes = [int(v) for letter, v in words if letter == "G"]
        mcodes = [v for letter, v in words if letter == "M"]
        axis = {letter: v for letter, v in words if letter in ("X", "Y", "Z", "A")}

        for g in gcodes:
            if g in (0, 1, 2, 3):
                state.motion = g
            elif g in (17, 18, 19):
                state.plane = g
            elif g == 20:
                state.inch_mode = True
                state.units_set = True
                _add(
                    state,
                    index,
                    Severity.ERROR,
                    "inch-mode",
                    "G20 inch mode is broken in firmware and should not be used: M-codes "
                    "internally emit G-code that inherits the unit mode. Post in metric.",
                    text,
                )
            elif g == 21:
                state.units_set = True
            elif g in (90, 91):
                state.distance_set = True

        for m in mcodes:
            if m == 321.0:
                # Laser mode. From here S is beam power, not spindle RPM, and
                # cutting moves legitimately run with the spindle stopped.
                state.laser_mode = True
            elif m in (3.0, 4.0):
                state.spindle_on = True
            elif m == 5.0:
                state.spindle_on = False

        # S is only a spindle speed when it is not a parameter to some other
        # M-code. M851 S100, M6 T1 S5 (collet index) and the override M-codes
        # all carry an S that has nothing to do with spindle RPM.
        s_is_spindle_speed = _spindle_word_is_speed(mcodes, gcodes)
        for letter, value in words:
            if letter == "S" and s_is_spindle_speed:
                state.spindle_rpm = value
            elif letter == "F":
                state.feed = value

        if s_is_spindle_speed and not state.laser_mode:
            _check_spindle_speed(state, index, words, limits, text)
        _check_tool(state, index, words, limits, text)

        if state.motion is None or not axis:
            continue

        _check_feed(state, index, axis, limits, text)

        if state.motion in _CUTTING_MOVES:
            _check_cutting_move(state, index, axis, text)

    _check_header(state)
    return _deduplicate(state.issues)


def _deduplicate(issues: list[ProgramIssue]) -> list[ProgramIssue]:
    """Collapse repeats of the same check into one issue carrying a count.

    A modal feed error repeats on every subsequent move; one real program in
    the wild produced 134,000 identical findings. Reporting the first
    occurrence and a count is what makes the output usable.
    """
    first: dict[str, ProgramIssue] = {}
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue.code] = counts.get(issue.code, 0) + 1
        if issue.code not in first:
            first[issue.code] = issue
    collapsed = [
        ProgramIssue(
            line_number=i.line_number,
            severity=i.severity,
            code=i.code,
            message=i.message,
            text=i.text,
            occurrences=counts[code],
        )
        for code, i in first.items()
    ]
    return sorted(collapsed, key=lambda i: (i.line_number, i.code))


# G-codes that take S as their own parameter. G4 S<n> is a dwell in seconds.
_G_CODES_CONSUMING_S = frozenset({4})


def _spindle_word_is_speed(mcodes: list[float], gcodes: list[int]) -> bool:
    """Whether an S word on this line means spindle RPM.

    False when some other code on the line claims S for itself: `G4 S1` is a
    one-second dwell, `M851 S100` is that M-code's parameter, and `M6 T1 S5`
    selects a collet. Only M3/M4, or a bare S with nothing else to claim it,
    set spindle speed.
    """
    if any(g in _G_CODES_CONSUMING_S for g in gcodes):
        return False
    if not mcodes:
        return True
    return any(m in (3.0, 4.0) for m in mcodes)


def _add(state: _State, line: int, severity: Severity, code: str, message: str, text: str = "") -> None:
    state.issues.append(ProgramIssue(line, severity, code, message, text))


def _check_spindle_speed(
    state: _State, index: int, words: list[tuple[str, float]], limits: MachineLimits, text: str
) -> None:
    for letter, value in words:
        if letter != "S" or value <= 0:
            continue
        if value > limits.max_rpm:
            _add(
                state,
                index,
                Severity.ERROR,
                "rpm-too-high",
                f"S{value:.0f} exceeds the {limits.max_rpm:.0f} RPM maximum. "
                "The spindle will not reach the commanded speed.",
                text,
            )
        elif value < limits.min_rpm:
            _add(
                state,
                index,
                Severity.WARNING,
                "rpm-too-low",
                f"S{value:.0f} is below the {limits.min_rpm:.0f} RPM minimum. "
                "The spindle cannot hold speed reliably this low.",
                text,
            )


def _check_tool(state: _State, index: int, words: list[tuple[str, float]], limits: MachineLimits, text: str) -> None:
    has_m6 = any(letter == "M" and value == 6.0 for letter, value in words)
    if not has_m6:
        return
    for letter, value in words:
        if letter == "T" and not (1 <= value <= limits.atc_tool_slots):
            _add(
                state,
                index,
                Severity.WARNING,
                "tool-outside-atc",
                f"T{value:.0f} is outside the {limits.atc_tool_slots}-slot ATC range. "
                "This needs a custom tool slot defined, or it will be a manual change.",
                text,
            )


def _check_feed(state: _State, index: int, axis: dict[str, float], limits: MachineLimits, text: str) -> None:
    if state.motion == 0 or state.feed <= 0:
        return
    feed = state.feed * (25.4 if state.inch_mode else 1.0)

    z_only = "Z" in axis and not any(a in axis for a in ("X", "Y"))
    limit = limits.max_feed_z if z_only else limits.max_feed_xy
    name = "Z" if z_only else "XY"

    if feed > limit:
        _add(
            state,
            index,
            Severity.ERROR,
            "feed-too-high",
            f"F{feed:.0f} exceeds the {name} axis maximum of {limit:.0f} mm/min. "
            "The machine will clamp the feed, so the program will not run as posted.",
            text,
        )


def _check_cutting_move(state: _State, index: int, axis: dict[str, float], text: str) -> None:
    if not state.spindle_on and not state.laser_mode:
        _add(
            state,
            index,
            Severity.ERROR,
            "cutting-without-spindle",
            "Cutting move with the spindle stopped. Add M3 with an S word before cutting.",
            text,
        )
    if state.motion in (2, 3) and state.plane is None:
        _add(
            state,
            index,
            Severity.WARNING,
            "arc-without-plane",
            "Arc move before any plane selection. Set G17, G18 or G19 explicitly.",
            text,
        )


def _check_header(state: _State) -> None:
    if not state.units_set:
        _add(
            state,
            0,
            Severity.WARNING,
            "units-not-set",
            "Program never sets units. Add G21 so it does not inherit millimetres or inches from whatever ran last.",
        )
    if not state.distance_set:
        _add(
            state,
            0,
            Severity.WARNING,
            "distance-mode-not-set",
            "Program never sets G90 or G91. Add G90 so it does not inherit the distance mode.",
        )
