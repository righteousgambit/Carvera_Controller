"""Program-level engine orchestration without machine commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .geometry import CollisionScene, SweptTool, ToolGeometry, Vec3
from .stock import StockVolume


@dataclass(frozen=True)
class SimulationSegment:
    start: Vec3
    end: Vec3
    tool_id: str
    cutting: bool = True
    axis: Vec3 = field(default_factory=lambda: Vec3(0, 0, 1))
    line: int = 0


@dataclass(frozen=True)
class SimulationReport:
    segments_processed: int
    removed_volume_mm3: float
    remaining_volume_mm3: float
    candidates: tuple
    status: str
    resolution_mm: float
    cancelled: bool
    qualification: str = "software geometry only; physical registration and clearance unqualified"


def simulate(
    segments,
    tools: dict[str, ToolGeometry],
    stock: StockVolume,
    scene: CollisionScene,
    *,
    progress: Callable | None = None,
    cancelled: Callable | None = None,
    max_segments=1_000_000,
):
    """Run ordered stock evolution and continuous conservative collision checks.

    Caller owns this mutable stock instance. Unknown tools fail before modifying
    the segment; cancellation preserves previous completed segments. This checks
    original stock bounds conservatively for non-cutting bodies, so cleared
    pockets may yield false-positive shank/holder candidates.
    """
    if not 1 <= max_segments <= 1_000_000:
        raise ValueError("Program simulation needs bounded segment budget")
    processed = 0
    hits = []
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
        collision = scene.check_sweep(sweep, cutting=segment.cutting)
        if len(hits) + len(collision.candidates) > 100_000:
            raise ValueError("Collision report budget exceeded; reduce program or isolate operation")
        hits.extend((segment.line, component, obstacle) for component, obstacle in collision.candidates)
        if segment.cutting:
            stock.subtract(sweep)
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
    )
