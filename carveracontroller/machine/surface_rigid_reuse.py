"""Operation-local exact reuse for identical complete C1 translation queries."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from typing import TYPE_CHECKING

from carveracontroller.addons.manufacturing_simulation import SimulationSegment

if TYPE_CHECKING:
    from carveracontroller.machine.program_surface_clearance import (
        ProgramRotatingResult,
        ProgramSolidInterval,
        ProgramSurfaceContact,
        ProgramSurfaceContactGroup,
        SurfaceGap,
    )

Key = tuple[int, str, str, tuple[float, float, float], tuple[float, float, float], float]
Rows = tuple[
    tuple["ProgramSurfaceContact", ...],
    tuple["ProgramSurfaceContactGroup", ...],
    tuple["ProgramSolidInterval", ...],
    tuple["ProgramRotatingResult", ...],
    tuple["SurfaceGap", ...],
]


class RigidPairReuse:
    """Only one operation, one immutable mesh set and identical complete chords.

    The caller keys exact relative start, delta and allowance before lookup. Geometry primitives remain
    shared; every segment gets its own complete source-parameter wrapper. Counts
    describe unique geometry work/storage rather than duplicated memberships.
    """

    def __init__(self) -> None:
        self.rows: dict[Key, Rows] = {}
        self.hits = 0

    def get(self, key: Key, index: int, segment: SimulationSegment) -> Rows | None:
        rows = self.rows.get(key)
        if rows is None:
            return None
        self.hits += 1
        lo = Fraction(segment.source_start_ratio)
        span = Fraction(segment.source_end_ratio) - lo
        return (
            tuple(
                replace(
                    r,
                    segment_index=index,
                    line=segment.line,
                    source_lower_ratio=lo + span * r.contact.lower,
                    source_upper_ratio=lo + span * r.contact.upper,
                )
                for r in rows[0]
            ),
            tuple(
                replace(
                    r,
                    segment_index=index,
                    line=segment.line,
                    source_lower_ratio=lo + span * r.group.lower,
                    source_upper_ratio=lo + span * r.group.upper,
                )
                for r in rows[1]
            ),
            tuple(
                replace(
                    r,
                    segment_index=index,
                    line=segment.line,
                    source_lower_ratio=lo + span * r.interval.lower,
                    source_upper_ratio=lo + span * r.interval.upper,
                )
                for r in rows[2]
            ),
            tuple(
                replace(r, segment_index=index, line=segment.line, source_sample_ratio=lo + span * r.result.sample)
                for r in rows[3]
            ),
            tuple(replace(r, segment_index=index, line=segment.line) for r in rows[4]),
        )
