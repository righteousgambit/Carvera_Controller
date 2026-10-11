"""Conservative, pure reconstruction of the state before a recovery line.

This is deliberately a supported-subset parser, not a substitute for the
firmware interpreter. An unsupported or ambiguous prefix refuses automatic
re-entry. No device, viewer cache, default coordinate origin or assumed
physical position is consulted here.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

_WORD = re.compile(r"([A-Za-z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))")
_WCS = (54.0, 55.0, 56.0, 57.0, 58.0, 59.0, 59.1, 59.2, 59.3)


class RecoveryPlanError(ValueError):
    """The supplied program cannot establish a supported re-entry state."""


@dataclass(frozen=True)
class RecoveryState:
    start_line: int
    units: str
    distance: str
    wcs_index: int
    tool: int | None
    selected_tool: int | None
    spindle: str
    spindle_rpm: float | None
    air_on: bool
    motion: str
    plane: str
    feed_mm_min: float | None
    position_mm: tuple[float, float, float]

    def __post_init__(self) -> None:
        if type(self.start_line) is not int or self.start_line < 1:
            raise RecoveryPlanError("positive recovery boundary line required")
        if self.units not in ("G20", "G21") or self.distance not in ("G90", "G91"):
            raise RecoveryPlanError("explicit unit and distance modes required")
        if self.motion not in ("G0", "G1", "G2", "G3") or self.plane not in ("G17", "G18", "G19"):
            raise RecoveryPlanError("supported motion and plane required")
        if type(self.wcs_index) is not int or not 0 <= self.wcs_index < len(_WCS):
            raise RecoveryPlanError("valid WCS identity required")
        for tool_value in (self.tool, self.selected_tool):
            if tool_value is not None and (type(tool_value) is not int or not 1 <= tool_value <= 999999):
                raise RecoveryPlanError("valid tool identity required")
        if self.spindle not in ("M3", "M5") or type(self.air_on) is not bool:
            raise RecoveryPlanError("explicit spindle and air states required")
        for value in (self.feed_mm_min, self.spindle_rpm):
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value <= 0):
                raise RecoveryPlanError("finite positive feed and spindle RPM required")
        if self.spindle == "M3" and self.spindle_rpm is None:
            raise RecoveryPlanError("running spindle requires explicit RPM")
        if len(self.position_mm) != 3 or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in self.position_mm
        ):
            raise RecoveryPlanError("finite work XYZ boundary required")


def parse_words(line: str, line_number: int) -> list[tuple[str, float]]:
    """Strip balanced comments and parse every remaining byte as G-code."""
    # Current firmware hoists G90/G91 before comment removal and truncates
    # at the first parenthesis. Refuse source whose ordinary interpretation
    # could disagree with those firmware rules.
    comment_indexes = [index for marker in ("(", ";") if (index := line.find(marker)) >= 0]
    first_comment = min(comment_indexes) if comment_indexes else -1
    if first_comment >= 0:
        comment_tail = line[first_comment:]
        if re.search(r"G9[01]", comment_tail):
            raise RecoveryPlanError(f"line {line_number}: firmware-ambiguous distance mode inside comment")
    out: list[str] = []
    depth = 0
    for index, char in enumerate(line):
        if char == ";" and depth == 0:
            break
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise RecoveryPlanError(f"line {line_number}: unmatched comment")
        elif depth == 0:
            if first_comment >= 0 and index > first_comment:
                if not char.isspace():
                    raise RecoveryPlanError(f"line {line_number}: executable text after inline comment is unsupported")
            else:
                out.append(char)
    if depth:
        raise RecoveryPlanError(f"line {line_number}: unmatched comment")
    text = "".join(out).strip()
    if not text or text == "%":
        return []
    words: list[tuple[str, float]] = []
    cursor = 0
    while cursor < len(text):
        if text[cursor].isspace():
            cursor += 1
            continue
        match = _WORD.match(text, cursor)
        if match is None:
            raise RecoveryPlanError(f"line {line_number}: unsupported expression or syntax")
        if match.group(1).islower():
            raise RecoveryPlanError(f"line {line_number}: lowercase command semantics unsupported")
        value = float(match.group(2))
        if not math.isfinite(value):
            raise RecoveryPlanError(f"line {line_number}: nonfinite word")
        words.append((match.group(1).upper(), value))
        cursor = match.end()
    return words


def reconstruct_recovery(lines: Sequence[str], start_line: int) -> RecoveryState:
    """Reconstruct the prefix, excluding the line which will execute next."""
    if type(start_line) is not int or not 1 <= start_line <= len(lines):
        raise RecoveryPlanError("selected recovery line is outside the program")
    units: str | None = None
    distance: str | None = None
    wcs: int | None = None
    motion: str | None = None
    # Plane survives jobs and is absent from live telemetry. Startup defaults
    # cannot establish the mode in which this particular prefix executed.
    plane: str | None = None
    feed_mode_known = False
    feed: float | None = None
    rpm: float | None = None
    spindle: str | None = None
    air: bool | None = None
    tool: int | None = None
    selected_tool: int | None = None
    position: list[float | None] = [None, None, None]
    for number, line in enumerate(lines[: start_line - 1], 1):
        words = parse_words(line, number)
        standalone_feed = bool(words and words[0][0] == "F")
        if standalone_feed and any(letter in ("G", "M", "T", "S") for letter, _ in words):
            raise RecoveryPlanError(f"line {number}: leading feed combined with explicit commands is unsupported")
        if (
            any(letter == "F" for letter, _ in words)
            and words
            and words[0][0] == "N"
            and not any(letter in ("G", "M") for letter, _ in words)
        ):
            raise RecoveryPlanError(f"line {number}: line-numbered implicit feed dispatch is ambiguous")
        motion_indexes = [
            index for index, (letter, value) in enumerate(words) if letter == "G" and value in (0, 1, 2, 3)
        ]
        if motion_indexes and any(
            letter == "G" and value not in (0, 1, 2, 3) for letter, value in words[motion_indexes[0] + 1 :]
        ):
            raise RecoveryPlanError(f"line {number}: modal control after motion is unsupported")
        if (
            any(letter == "F" for letter, _ in words)
            and not motion_indexes
            and any(letter in ("G", "M", "T", "S") for letter, _ in words)
        ):
            raise RecoveryPlanError(f"line {number}: feed mixed with non-motion command is unsupported")
        groups: dict[str, float] = {}
        values: dict[str, float] = {}
        for letter, value in words:
            group = letter
            if letter == "G":
                if value in (0, 1, 2, 3):
                    group = "motion"
                elif value == 53:
                    group = "machine_space"
                elif value in (20, 21):
                    group = "units"
                elif value in (90, 91):
                    group = "distance"
                elif value in _WCS:
                    group = "wcs"
                elif value in (17, 18, 19):
                    group = "plane"
                elif value in (40, 94):
                    group = f"neutral-G{value:g}"
                else:
                    raise RecoveryPlanError(f"line {number}: unsupported G{value:g} in recovery prefix")
            elif letter == "M":
                if value in (3, 5):
                    group = "spindle"
                elif value in (7, 9):
                    group = "air"
                elif value == 6:
                    group = "tool_change"
                else:
                    raise RecoveryPlanError(f"line {number}: unsupported M{value:g} in recovery prefix")
            elif letter not in ("X", "Y", "Z", "I", "J", "K", "F", "S", "T", "N"):
                raise RecoveryPlanError(f"line {number}: unsupported {letter} word in recovery prefix")
            if group in groups:
                raise RecoveryPlanError(f"line {number}: ambiguous repeated {group} word")
            groups[group] = value
            if letter not in ("G", "M"):
                values[letter] = value
        if standalone_feed:
            # GcodeDispatch rewrites an F-leading implicit line as G1, even
            # when the previous motion was G0. This also changes modal motion.
            groups["motion"] = 1.0
        if "units" in groups:
            units = "G20" if groups["units"] == 20 else "G21"
        if "distance" in groups:
            distance = "G90" if groups["distance"] == 90 else "G91"
        if "wcs" in groups:
            updated_wcs = _WCS.index(groups["wcs"])
            if wcs != updated_wcs:
                position = [None, None, None]
            wcs = updated_wcs
        if "plane" in groups:
            plane = f"G{groups['plane']:g}"
        if "neutral-G94" in groups:
            # Inverse-time G93 can survive an earlier job or MDI. The live
            # status fields do not establish feed interpretation.
            feed_mode_known = True
        if "motion" in groups:
            motion = f"G{groups['motion']:g}"
        if "T" in values:
            if values["T"] < 1 or not values["T"].is_integer():
                raise RecoveryPlanError(f"line {number}: invalid tool identity")
            selected_tool = int(values["T"])
        if "tool_change" in groups:
            if selected_tool is None:
                raise RecoveryPlanError(f"line {number}: M6 has no established selected tool")
            tool = selected_tool
            # ATC motion does not establish the work-coordinate endpoint.
            position = [None, None, None]
        scale = 25.4 if units == "G20" else 1.0
        if "F" in values:
            if units is None or values["F"] <= 0:
                raise RecoveryPlanError(f"line {number}: positive feed with explicit units required")
            if motion != "G0":
                if not feed_mode_known:
                    raise RecoveryPlanError(f"line {number}: cutting feed has no explicit G94 mode")
                feed = values["F"] * scale
        if "S" in values:
            if values["S"] <= 0:
                raise RecoveryPlanError(f"line {number}: positive spindle RPM required")
            rpm = values["S"]
        if "spindle" in groups:
            spindle = "M3" if groups["spindle"] == 3 else "M5"
        if "air" in groups:
            air = groups["air"] == 7
        machine_move = "machine_space" in groups
        if machine_move and ("motion" not in groups or motion not in ("G0", "G1")):
            raise RecoveryPlanError(f"line {number}: G53 requires explicit G0 or G1 motion")
        if machine_move and any(axis in values for axis in ("I", "J", "K")):
            raise RecoveryPlanError(f"line {number}: arc center is unsupported for G53")
        previous_position = position[:]
        axes = any(axis in values for axis in ("X", "Y", "Z"))
        if (
            motion in ("G1", "G2", "G3")
            and (axes or any(axis in values for axis in ("I", "J", "K")))
            and not feed_mode_known
        ):
            raise RecoveryPlanError(f"line {number}: cutting motion has no explicit G94 mode")
        if axes:
            if units is None or distance is None or (wcs is None and not machine_move) or motion is None:
                raise RecoveryPlanError(f"line {number}: motion has unknown units, distance, WCS or motion mode")
            if "tool_change" in groups:
                raise RecoveryPlanError(f"line {number}: motion combined with tool change is unsupported")
            for index, axis in enumerate(("X", "Y", "Z")):
                if axis not in values:
                    continue
                if machine_move:
                    # Firmware uses an absolute unit-scaled MCS target even
                    # under G91. Without a reviewed transform its WCS value is
                    # unknown, not the same numeric value in another frame.
                    position[index] = None
                    continue
                coordinate = values[axis] * scale
                if distance == "G91":
                    previous = position[index]
                    if previous is None:
                        raise RecoveryPlanError(f"line {number}: relative {axis} has no absolute anchor")
                    coordinate += previous
                position[index] = coordinate
            if machine_move and any(axis in values for axis in ("X", "Y")):
                # Unverified XY rotation couples the two work-coordinate axes.
                position[0] = position[1] = None
        center_words = any(axis in values for axis in ("I", "J", "K"))
        if center_words and motion not in ("G2", "G3"):
            raise RecoveryPlanError(f"line {number}: arc-center words outside arc motion")
        if motion in ("G2", "G3") and (axes or center_words):
            if plane is None:
                raise RecoveryPlanError(f"line {number}: arc has no explicitly established plane")
            if not center_words:
                raise RecoveryPlanError(
                    f"line {number}: firmware arcs require relative IJK center offsets; R is unsupported"
                )
            if any(value is None for value in previous_position) or units is None:
                raise RecoveryPlanError(f"line {number}: arc has no established start position or units")
            plane_axes, permitted = {
                "G17": ((0, 1), ("I", "J")),
                "G18": ((0, 2), ("I", "K")),
                "G19": ((1, 2), ("J", "K")),
            }[plane]
            if any(axis in values for axis in ("I", "J", "K") if axis not in permitted):
                raise RecoveryPlanError(f"line {number}: center word outside the selected arc plane")
            a, b = plane_axes
            start_a, start_b = previous_position[a], previous_position[b]
            end_a, end_b = position[a], position[b]
            assert start_a is not None and start_b is not None and end_a is not None and end_b is not None
            offset_a, offset_b = (values.get(axis, 0) * scale for axis in permitted)
            radius = math.hypot(offset_a, offset_b)
            end_radius = math.hypot(end_a - start_a - offset_a, end_b - start_b - offset_b)
            if radius <= 0 or abs(radius - end_radius) > max(0.01, radius * 0.001):
                raise RecoveryPlanError(f"line {number}: inconsistent or zero arc radius")
    if units is None or distance is None or wcs is None or motion is None:
        raise RecoveryPlanError("prefix does not establish units, distance, WCS and motion mode")
    if plane is None:
        raise RecoveryPlanError("prefix does not establish an explicit G17/G18/G19 plane")
    if not feed_mode_known:
        raise RecoveryPlanError("prefix does not establish explicit G94 feed mode")
    if spindle is None or air is None:
        raise RecoveryPlanError("prefix does not establish spindle and air state (M3/M5 and M7/M9)")
    if spindle == "M3" and rpm is None:
        raise RecoveryPlanError("running spindle has no established RPM")
    if any(value is None or not math.isfinite(value) for value in position):
        raise RecoveryPlanError("prefix does not establish all three absolute work coordinates")
    x, y, z = position
    assert x is not None and y is not None and z is not None
    return RecoveryState(
        start_line, units, distance, wcs, tool, selected_tool, spindle, rpm, air, motion, plane, feed, (x, y, z)
    )


def build_reentry(
    state: RecoveryState,
    *,
    current_work_mm: Sequence[float],
    current_machine_z_mm: float,
    clearance_machine_z_mm: float,
    verified_wcs_index: int,
    verified_tool: int,
    tolerance_mm: float = 0.001,
) -> tuple[str, ...]:
    """Build a verified-subset approach without repeating a tool change.

    The caller must independently validate the operator verification and its
    scope immediately before sending these commands. Clearance is a declared
    collision-free machine Z, not a computed guarantee about clamps or stock.
    """
    if len(current_work_mm) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in current_work_mm):
        raise RecoveryPlanError("finite current work XYZ required")
    for value in (current_machine_z_mm, clearance_machine_z_mm, tolerance_mm):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise RecoveryPlanError("finite machine Z, clearance and tolerance required")
    if tolerance_mm < 0:
        raise RecoveryPlanError("nonnegative comparison tolerance required")
    if (
        type(verified_wcs_index) is not int
        or not 0 <= verified_wcs_index < len(_WCS)
        or type(verified_tool) is not int
        or not 1 <= verified_tool <= 999999
    ):
        raise RecoveryPlanError("valid verified tool and WCS identities required")
    if state.tool is None:
        raise RecoveryPlanError(
            "program prefix has no established active tool; do not assume the installed probe is a cutter"
        )
    if state.wcs_index != verified_wcs_index or state.tool != verified_tool:
        raise RecoveryPlanError("prepare and verify the program WCS and tool before re-entry")
    changed = [abs(a - b) > tolerance_mm for a, b in zip(state.position_mm, current_work_mm)]
    commands: list[str] = []
    spindle_command = (
        f"M3 S{state.spindle_rpm:.6f}" if state.spindle == "M3" and state.spindle_rpm is not None else "M5"
    )
    air_command = "M7" if state.air_on else "M9"
    if any(changed):
        target_machine_z = current_machine_z_mm + state.position_mm[2] - current_work_mm[2]
        if clearance_machine_z_mm < max(current_machine_z_mm, target_machine_z) - tolerance_mm:
            raise RecoveryPlanError("verified clearance would lower below the current or target machine Z")
        if state.feed_mm_min is None:
            raise RecoveryPlanError("re-entry descent requires an established feed")
        commands.append("G21 G90 G94")
        if abs(clearance_machine_z_mm - current_machine_z_mm) > tolerance_mm:
            commands.append(f"G53 G0 Z{clearance_machine_z_mm:.6f}")
        commands.extend((spindle_command, air_command))
        if changed[0] or changed[1]:
            commands.append(f"G0 X{state.position_mm[0]:.6f} Y{state.position_mm[1]:.6f}")
        commands.extend((f"G1 F{state.feed_mm_min:.6f}", f"G1 Z{state.position_mm[2]:.6f}"))
    # Restore explicit modal state even when no approach motion was necessary.
    commands.extend((state.units, state.distance, f"{state.plane} G40 G94", f"G{_WCS[state.wcs_index]:g}"))
    if state.feed_mm_min is not None:
        scale = 25.4 if state.units == "G20" else 1.0
        commands.append(f"G1 F{state.feed_mm_min / scale:.6f}")
    if not any(changed):
        commands.extend((spindle_command, air_command))
    if state.motion in ("G2", "G3") and state.feed_mm_min is None:
        raise RecoveryPlanError("arc motion has no established cutting feed")
    commands.append(state.motion)
    return tuple(commands)
