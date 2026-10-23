"""Detached legacy program metadata and streamed path preparation, without Kivy."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import islice
from types import MappingProxyType
from typing import Any

from carveracontroller.CNC import CNC, LASER_TOOL_NUMBER, OCODE_PATTERN, PROBE_3D_TOOL_NUMBER, ZPROBE_TOOL_NUMBER
from carveracontroller.machine.job_program_validation import MAX_PREVIEW_POINTS, PreviewParserInputs

LEGACY_CHUNK_LINES = 10_000
MARGIN_KEYS = ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")
RowConsumer = Callable[[list[list[float]], bool], None]


@dataclass(frozen=True)
class PreparedLegacyProgram:
    lines: tuple[str, ...]
    source_hash: str
    inputs: PreviewParserInputs
    vertex_count: int
    upcoming_tool: int
    used_tools: tuple[int, ...]
    tool_change_markers: tuple[tuple[int, str], ...]
    has_4axis: bool
    file_has_ocodes: bool
    parser_state: Mapping[str, Any]
    margins: Mapping[str, float]


def bridge_program_colors(rows: Sequence[list[float]]) -> list[list[float]]:
    """Retain the legacy per-chunk feed/rapid bridging, including row attributes."""
    result = []
    last_color = -1.0
    for row in rows:
        color = row[4]
        if color >= 0 and last_color >= 0 and color != last_color:
            bridge = row.copy()
            bridge[4] = last_color
            result.append(bridge)
        result.append(row)
        last_color = color
    return result


def prepare_legacy_program(
    lines: Sequence[str],
    inputs: PreviewParserInputs,
    *,
    consume: RowConsumer,
    chunk_lines: int = LEGACY_CHUNK_LINES,
    point_budget: int = MAX_PREVIEW_POINTS,
    cancelled: Callable[[], bool] = lambda: False,
) -> PreparedLegacyProgram:
    if type(chunk_lines) is not int or chunk_lines < 1:
        raise ValueError("Preview chunk size must be a positive integer")
    retained = tuple(lines)
    parser = CNC(
        variables={"clearance_z": inputs.clearance_z, "wcoz": inputs.wcoz},
        point_budget=point_budget,
        cancelled=cancelled,
    )
    parser.inch, parser.accuracy = inputs.inch, inputs.accuracy
    count, upcoming = 0, 0
    used: list[int] = []
    markers: list[tuple[int, str]] = []
    has_ocodes = False
    digest = hashlib.sha256()
    for number, line in enumerate(retained, 1):
        if cancelled():
            raise InterruptedError("Preview preparation cancelled")
        if not isinstance(line, str):
            raise ValueError("Preview program lines must be text")
        digest.update(line.encode("utf-8"))
        has_ocodes = has_ocodes or bool(OCODE_PATTERN.search(line))
        previous_tool, start = parser.tool, len(parser.coordinates)
        try:
            parser.parseLine(line, number)
        except InterruptedError:
            raise
        except (ValueError, TypeError, ArithmeticError) as exc:
            raise ValueError(f"Program preview failed at line {number}: {exc}") from exc
        for row in islice(parser.coordinates, start, None):
            if any(not math.isfinite(value) for value in row):
                raise ValueError(f"Program preview has nonfinite coordinates at line {number}")
        count += len(parser.coordinates) - start
        if upcoming == 0:
            upcoming = parser.tool
        if (parser.tool_cmd or parser.tool != previous_tool) and parser.tool not in used:
            used.append(parser.tool)
        label = None
        if parser.mval == 321 or parser.tool == LASER_TOOL_NUMBER:
            label = "L"
        elif parser.tool == ZPROBE_TOOL_NUMBER and (parser.tool != previous_tool or parser.tool_cmd):
            label = "P"
        elif parser.tool == PROBE_3D_TOOL_NUMBER and (parser.tool != previous_tool or parser.tool_cmd):
            label = "3DP"
        elif parser.tool >= 1 and parser.tool != previous_tool:
            label = f"T{parser.tool}"
        if label is not None and not (markers and markers[-1][1] == label):
            markers.append((number, label))
        if number % chunk_lines == 0 or number == len(retained):
            if cancelled():
                raise InterruptedError("Preview preparation cancelled")
            consume(parser.coordinates, number == len(retained))
            parser.coordinates = []
    if not retained:
        consume([], True)
    if cancelled():
        raise InterruptedError("Preview preparation cancelled")
    excluded = {"vars", "coordinates", "inch", "accuracy"}
    state = {
        key: value for key, value in vars(parser).items() if key not in excluded and not key.startswith("_preview_")
    }
    return PreparedLegacyProgram(
        retained,
        digest.hexdigest(),
        inputs,
        count,
        upcoming,
        tuple(used),
        tuple(markers),
        parser.has_4axis,
        has_ocodes,
        MappingProxyType(state),
        MappingProxyType({key: float(parser.vars[key]) for key in MARGIN_KEYS}),
    )
