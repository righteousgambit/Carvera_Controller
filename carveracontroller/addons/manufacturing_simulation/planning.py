"""Program-level engine orchestration without machine commands."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Callable

from .geometry import CollisionContact, CollisionScene, SweptTool, ToolGeometry, Vec3
from .stock import StockVolume


@dataclass(frozen=True)
class SimulationSegment:
    start: Vec3
    end: Vec3
    tool_id: str
    cutting: bool = True
    axis: Vec3 = field(default_factory=lambda: Vec3(0, 0, 1))
    line: int = 0
    source_start_ratio: float = 0.0
    source_end_ratio: float = 1.0


@dataclass(frozen=True)
class SimulationReport:
    segments_processed: int
    removed_volume_mm3: float
    remaining_volume_mm3: float
    candidates: tuple[tuple[int, str, str], ...]
    status: str
    resolution_mm: float
    cancelled: bool
    qualification: str = "software geometry only; physical registration and clearance unqualified"
    clearance_details: tuple[tuple[int, CollisionContact], ...] = ()


def simulate(
    segments: Iterable[SimulationSegment],
    tools: dict[str, ToolGeometry],
    stock: StockVolume,
    scene: CollisionScene,
    *,
    progress: Callable[[int, int, float], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    max_segments: int = 1_000_000,
) -> SimulationReport:
    """Run ordered stock evolution and continuous conservative collision checks.

    Caller owns this mutable stock instance. Unknown tools fail before modifying
    the segment; cancellation preserves previous completed segments. Bodies and
    rapid cutters are checked against occupied stock boxes before subtraction.
    Empty cells reflect center-classified removal, not physical qualification.
    """
    if not 1 <= max_segments <= 1_000_000:
        raise ValueError("Program simulation needs bounded segment budget")
    processed = 0
    hits = []
    details = []
    before = stock.remaining_volume_mm3
    was_cancelled = False
    for segment in segments:
        if cancelled and cancelled():
            was_cancelled = True
            break
        if processed >= max_segments:
            raise ValueError("Program exceeds simulation segment budget")
        if segment.tool_id not in tools:
            raise ValueError(f"Missing geometry for tool {segment.tool_id}")
        sweep = SweptTool(segment.start, segment.end, tools[segment.tool_id], segment.axis)
        try:
            collision = scene.check_sweep(sweep, cutting=segment.cutting, residual_stock=stock, cancelled=cancelled)
        except InterruptedError:
            was_cancelled = True
            break
        contacts = collision.contacts
        candidates = collision.candidates
        if len(hits) + len(candidates) > 100_000 or len(details) + len(contacts) > 100_000:
            raise ValueError("Collision report budget exceeded; reduce program or isolate operation")
        if segment.cutting:
            try:
                stock.subtract(sweep, cancelled=cancelled)
            except InterruptedError:
                was_cancelled = True
                break
        hits.extend((segment.line, component, obstacle) for component, obstacle in candidates)
        details.extend(
            (
                segment.line,
                replace(
                    contact,
                    source_ratio=(
                        segment.source_start_ratio
                        + (segment.source_end_ratio - segment.source_start_ratio) * contact.first_fraction
                        if contact.first_fraction is not None
                        else None
                    ),
                ),
            )
            for contact in contacts
        )
        processed += 1
        if progress:
            progress(processed, segment.line, stock.remaining_volume_mm3)
    if was_cancelled:
        status = "cancelled"
    elif hits:
        status = "potential_collision"
    elif not scene.registration_confirmed or not scene.geometry_complete:
        status = "unknown"
    else:
        status = "clear_conservative_bounds"
    return SimulationReport(
        processed,
        before - stock.remaining_volume_mm3,
        stock.remaining_volume_mm3,
        tuple(hits),
        status,
        stock.resolution_mm,
        was_cancelled,
        clearance_details=tuple(details),
    )
