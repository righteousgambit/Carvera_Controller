"""Read-only tooling comparison; nominal lengths and TLO are different quantities."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.tool_history import ToolHistory


def finite(value: object) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


@dataclass(frozen=True)
class ToolComparison:
    number: int
    name: str
    library_diameter_mm: float | None
    cam_diameter_mm: float | None
    stickout_mm: float | None
    historical_tlo_mm: float | None
    historical_time: float | None
    observed_tlo_mm: float | None
    reported_active: bool
    report_state: str
    diameter_conflict: bool
    measurement_count: int


def compare_tools(
    library: Mapping[int, ToolDefinition],
    cam: Mapping[int, ToolDefinition],
    history: ToolHistory,
    pose: ObservedPose | None,
    *,
    connected: bool,
    now: float,
    cam_scale: float = 1.0,
) -> tuple[ToolComparison, ...]:
    """Return detached rows without creating history entries or changing tools.

    Calibration history is keyed by tool number, not identified physical cutter.
    It must never be treated as proof the current cutter has that measurement.
    """
    records = {record.tool_number: record for record in history.tools()}
    numbers = set(library) | set(cam) | set(records)
    if pose is not None and pose.tool is not None:
        numbers.add(pose.tool)
    fresh = connected and pose is not None and pose.fresh(now)
    scale = finite(cam_scale)
    rows = []
    for number in sorted(n for n in numbers if isinstance(n, int) and not isinstance(n, bool) and n > 0):
        nominal, programmed, record = library.get(number), cam.get(number), records.get(number)
        report = record.latest if record else None
        diameter = finite(getattr(nominal, "diameter", None))
        cam_diameter = finite(getattr(programmed, "diameter", None))
        cam_diameter = cam_diameter * scale if cam_diameter is not None and scale is not None and scale > 0 else None
        reported = fresh and pose is not None and pose.tool == number
        rows.append(
            ToolComparison(
                number=number,
                name=getattr(nominal, "description", "")
                or getattr(programmed, "description", "")
                or (record.label if record else "")
                or "Unnamed tool",
                library_diameter_mm=diameter,
                cam_diameter_mm=cam_diameter,
                stickout_mm=finite(getattr(nominal, "stickout", None)),
                historical_tlo_mm=finite(report.applied) if report else None,
                historical_time=finite(report.timestamp) if report else None,
                observed_tlo_mm=finite(pose.tool_length_mm) if reported and pose is not None else None,
                reported_active=reported,
                report_state="fresh" if fresh else "disconnected" if not connected else "stale or unavailable",
                diameter_conflict=diameter is not None
                and cam_diameter is not None
                and not math.isclose(diameter, cam_diameter, abs_tol=0.001, rel_tol=0),
                measurement_count=len(record.reports) if record else 0,
            )
        )
    return tuple(rows)
