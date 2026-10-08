"""Canonical translation-only repeat playback, independent of controller transport."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import dist

from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.repeat_parts import RepeatPartPlan, vector
from carveracontroller.machine.simulation_preview import simulation_segments

PlaybackRow = tuple[float, float, float, int, int, int, int, float]


@dataclass(frozen=True)
class RepeatPlayback:
    source_hash: str
    plan: RepeatPartPlan
    machine_rows: tuple[PlaybackRow, ...]
    unresolved_lines: tuple[int, ...]

    def rows_for_offset(self, offset: Sequence[float]) -> list[list[float]]:
        reference = vector(offset)
        return [[*(row[axis] - reference[axis] for axis in range(3)), *row[3:]] for row in self.machine_rows]


def prepare_repeat_playback(
    program: ProgramOperations, plan: RepeatPartPlan, *, cancelled: Callable[[], bool] = lambda: False
) -> RepeatPlayback:
    if cancelled():
        raise InterruptedError("Playback preparation cancelled")
    if not isinstance(plan, RepeatPartPlan):
        raise ValueError("Build a declared repeat-part plan first")
    offsets = {part.wcs: part.work_offset_mm for part in plan.parts}
    mapped = ProgramOperations.from_text("\n".join(program.lines), work_offsets=offsets)
    if any(checkpoint.state.recovery_errors for checkpoint in mapped.checkpoints):
        raise ValueError("Playback cannot resolve unsupported modal or rotary commands")
    segments = simulation_segments(mapped, work_offsets=offsets)
    if len(segments) > 1_000_000:
        raise ValueError("Repeat playback exceeds the one-million segment preview budget")
    rows: list[PlaybackRow] = []
    previous = None
    for segment in segments:
        if cancelled():
            raise InterruptedError("Playback preparation cancelled")
        start, end = segment.start.tuple, segment.end.tuple
        if previous is not None and dist(previous, start) > 1e-7:
            raise ValueError("Unresolved motion creates a path gap; playback cannot invent a connecting move")
        state = mapped.checkpoints[segment.line - 1].state
        if state.feed_mode != "G94":
            raise ValueError("Repeat playback requires feed-per-minute G94")
        tool = int(segment.tool_id) if segment.tool_id != "None" else 0
        feed = (state.feed or 0) * (25.4 if state.units == "G20" else 1)
        attributes = (0, 1 if segment.cutting else 0, segment.line, tool, feed)
        # A duplicate start changes tool/feed/move type without fabricated travel.
        if not rows or rows[-1][3:] != attributes:
            rows.append((*start, *attributes))
        if dist(start, end) > 0:
            rows.append((*end, *attributes))
        previous = end
    if len(rows) < 2:
        raise ValueError("No nonzero resolved motion for repeat playback")
    return RepeatPlayback(program.file_hash, plan, tuple(rows), mapped.unresolved_motion_lines)
