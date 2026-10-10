"""Source-bound nominal playback time with explicit non-motion timing gaps."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction as F
from math import isfinite

from carveracontroller.machine.program_joint_clearance import ProgramBodyClearance, ProgramClearanceSource
from carveracontroller.machine.program_operations import _COMMENT, _WORD, ProgramOperations
from carveracontroller.machine.simulation_preview import simulation_segments


@dataclass(frozen=True)
class PlaybackSpan:
    line: int
    move: int | None
    position: F
    seconds: float | None
    reason: str


@dataclass(frozen=True)
class PlaybackClock:
    span: int = 0
    fraction: F = F(0)
    elapsed_seconds: float = 0


@dataclass(frozen=True)
class PlaybackAdvance:
    clock: PlaybackClock
    position: F
    gap: PlaybackSpan | None
    done: bool


@dataclass(frozen=True)
class ProgramPlaybackTiming:
    source: ProgramClearanceSource
    body: ProgramBodyClearance
    spans: tuple[PlaybackSpan, ...]
    move_spans: tuple[int, ...]
    rapid_mm_min: float | None
    known_prefix_seconds: tuple[float, ...]
    gap_count: int

    @property
    def known_seconds(self) -> float:
        return self.known_prefix_seconds[-1]

    def seek(self, move: int, sample: F) -> PlaybackClock:
        """Manual seek acknowledges preceding gaps; it does not estimate their time."""
        if (
            type(move) is not int
            or not 0 <= move < len(self.move_spans)
            or type(sample) is not F
            or not 0 <= sample <= 1
        ):
            raise ValueError("Choose a retained motion and exact fraction")
        index = self.move_spans[move]
        duration = self.spans[index].seconds
        elapsed = self.known_prefix_seconds[index]
        return PlaybackClock(index, sample, elapsed + (duration or 0) * float(sample))

    def advance(self, clock: PlaybackClock, seconds: float) -> PlaybackAdvance:
        if (
            type(seconds) not in (float, int)
            or not isfinite(seconds)
            or not 0 <= seconds <= 3600
            or type(clock.span) is not int
            or not 0 <= clock.span <= len(self.spans)
            or type(clock.fraction) is not F
            or not 0 <= clock.fraction <= 1
            or not isfinite(clock.elapsed_seconds)
            or clock.elapsed_seconds < 0
        ):
            raise ValueError("Playback clock requires bounded finite nominal time")
        index, sample, elapsed = clock.span, clock.fraction, clock.elapsed_seconds
        position = F(len(self.body.segments)) if index == len(self.spans) else self.spans[index].position
        while index < len(self.spans):
            span = self.spans[index]
            position = span.position + (sample if span.move is not None else 0)
            if span.seconds is None:
                return PlaybackAdvance(PlaybackClock(index, sample, elapsed), position, span, False)
            remaining = span.seconds * float(1 - sample)
            if remaining > seconds:
                sample += F(str(seconds / span.seconds)).limit_denominator(10**12)
                sample = min(F(1), sample)
                return PlaybackAdvance(
                    PlaybackClock(index, sample, elapsed + seconds),
                    span.position + (sample if span.move is not None else 0),
                    None,
                    False,
                )
            elapsed += remaining
            seconds -= remaining
            position = span.position + (1 if span.move is not None else 0)
            index, sample = index + 1, F(0)
            if seconds == 0 and index < len(self.spans):
                return PlaybackAdvance(PlaybackClock(index, sample, elapsed), position, None, False)
        return PlaybackAdvance(PlaybackClock(index, sample, elapsed), position, None, True)


def prepare_program_timing(
    source: ProgramClearanceSource,
    body: ProgramBodyClearance,
    offsets: Mapping[str, Sequence[float]],
    *,
    rapid_mm_min: float | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> ProgramPlaybackTiming:
    """No acceleration/override inference; G93 is one duration per source block."""
    if (
        source.file_hash != body.program_hash
        or not body.segments
        or len(body.segments) > 100_000
        or len(source.lines) > 1_000_000
        or not 1 <= body.start_line <= body.end_line <= len(source.lines)
    ):
        raise ValueError("Playback needs a complete bounded retained source program review")
    detached = ProgramOperations(
        source.lines, (), source.checkpoints, source.file_hash, source.motion, source.unresolved, dialect=source.dialect
    )
    expected = simulation_segments(detached, body.start_line, body.end_line, work_offsets=offsets, cancelled=cancelled)
    if body.curve_coverage:
        rows: dict[int, list[int]] = {}
        for i, segment in enumerate(expected):
            rows.setdefault(segment.line, []).append(i)
        changed = list(expected)
        for curve in source.curve_enclosures:
            indices = rows.get(curve.line_number, ())
            if not indices:
                continue
            if len(curve.parameters) != len(indices) + 1:
                raise ValueError("Playback curve parameters differ from complete retained motion")
            for k, i in enumerate(indices):
                changed[i] = replace(
                    expected[i], source_start_ratio=curve.parameters[k], source_end_ratio=curve.parameters[k + 1]
                )
        expected = tuple(changed)
    if expected != body.segments:
        raise ValueError("Playback source, datums or retained motion differ")
    if rapid_mm_min is None and source.parse_settings is not None:
        rapid_mm_min = source.parse_settings.rapid_mm_min
    if rapid_mm_min is not None and (
        type(rapid_mm_min) not in (int, float) or not isfinite(rapid_mm_min) or not 0 < rapid_mm_min <= 1_000_000
    ):
        raise ValueError("Declare a finite rapid estimate from 0 to 1000000 mm/min")
    states = {row.line_number: row.state for row in source.checkpoints}
    by_line: dict[int, list[int]] = {}
    for index, segment in enumerate(body.segments):
        by_line.setdefault(segment.line, []).append(index)
    spans: list[PlaybackSpan] = []
    move_spans = [0] * len(body.segments)
    next_move = 0
    gaps = set(body.uncovered_lines) | set(source.unresolved) | set(body.tool_change_lines)
    for line in range(body.start_line, body.end_line + 1):
        if line % 128 == 0 and cancelled():
            raise InterruptedError("Playback timing cancelled; no partial map")
        code = _COMMENT.sub(" ", source.lines[line - 1]).split(";", 1)[0]
        tokens = [(m[1].upper(), float(m[2])) for m in _WORD.finditer(code)]
        words = dict(tokens)
        gs = {v for k, v in tokens if k == "G"}
        ms = {v for k, v in tokens if k == "M"}
        if line in gaps or ms.intersection((0, 1, 6)) or ms - {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 30}:
            reason = "Tool change / ATC travel unqualified" if 6 in ms else "Unresolved motion or controller wait"
            spans.append(PlaybackSpan(line, None, F(next_move), None, reason))
        if 4 in gs:
            unit = source.parse_settings.dwell_p_seconds if source.parse_settings is not None else None
            duration = words.get("P", -1) * unit if unit is not None else None
            if duration is not None and (not isfinite(duration) or duration < 0):
                duration = None
            spans.append(
                PlaybackSpan(
                    line,
                    None,
                    F(next_move),
                    duration,
                    "Dwell" if duration is not None else "Dwell units/duration unknown",
                )
            )
        indices = by_line.get(line, ())
        length = sum((body.segments[i].end - body.segments[i].start).length for i in indices)
        state = states.get(line)
        for index in indices:
            segment = body.segments[index]
            distance = (segment.end - segment.start).length
            duration = None
            reason = "Feed mode or feed rate unknown"
            if not segment.cutting:
                if rapid_mm_min is not None:
                    duration = 60 * distance / rapid_mm_min
                reason = "Declared rapid estimate" if duration is not None else "Rapid rate undeclared"
            elif state is not None and state.feed_mode == "G93":
                feed = words.get("F")
                if feed is not None and isfinite(feed) and feed > 0:
                    duration = 60 / feed * (distance / length if length else 1 / len(indices))
                reason = (
                    "G93 block time distributed over chords"
                    if duration is not None
                    else "G93 needs F on this source block"
                )
            elif state is not None and state.feed_mode == "G94" and state.units in ("G20", "G21"):
                feed = state.feed
                if feed is not None and isfinite(feed) and feed > 0:
                    duration = (60 * distance / feed) / (25.4 if state.units == "G20" else 1)
                reason = "Nominal polyline feed time" if duration is not None else reason
            elif state is not None and state.feed_mode == "G95":
                reason = "G95 requires qualified spindle timing"
            if duration is not None and not isfinite(duration):
                duration, reason = None, "Nominal motion duration exceeds finite timing range"
            move_spans[index] = len(spans)
            spans.append(PlaybackSpan(line, index, F(index), duration, reason))
            next_move = index + 1
    if cancelled():
        raise InterruptedError("Playback timing cancelled; no partial map")
    prefix = [0.0]
    for span in spans:
        prefix.append(prefix[-1] + (span.seconds or 0))
    return ProgramPlaybackTiming(
        source,
        body,
        tuple(spans),
        tuple(move_spans),
        rapid_mm_min,
        tuple(prefix),
        sum(s.seconds is None for s in spans),
    )
