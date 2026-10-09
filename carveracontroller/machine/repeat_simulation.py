"""Declared-frame multi-stock subtraction; no controller transport or offsets."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import prod
from typing import Any

from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot
from carveracontroller.addons.machine_simulation.model import Geometry, MachineSetup
from carveracontroller.addons.machine_simulation.stock_model import initial_stock
from carveracontroller.addons.manufacturing_simulation import simulate
from carveracontroller.addons.manufacturing_simulation.planning import SimulationReport, SimulationSegment
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.repeat_parts import RepeatPartPlan
from carveracontroller.machine.simulation_preview import (
    scene_from_geometry,
    simulation_segments,
    simulation_tools,
    stock_geometry,
)


@dataclass(frozen=True)
class RepeatSimulation:
    plan: RepeatPartPlan
    program_hash: str
    segments: tuple[SimulationSegment, ...]
    reports: tuple[SimulationReport, ...]
    geometries: Mapping[str, GeometrySnapshot]
    unresolved_lines: tuple[int, ...]
    snapshots: tuple[dict[str, Any], ...] = ()


def simulate_repeat_parts(
    program: ProgramOperations,
    plan: RepeatPartPlan,
    definitions: Mapping[int, ToolDefinition],
    geometry: Mapping[str, Geometry | GeometrySnapshot],
    resolution_mm: float,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> RepeatSimulation:
    """Apply actual transformed motions to every stock, including cross-part engagement.

    Translation-only G54–G59 declarations. Unknown initial machine position remains
    unresolved; unsupported modal/rotary commands reject publication. Outputs use
    machine millimetres. Every part sees the entire ordered path, so a cutter can
    engage a different part than the selected WCS. Global voxel/face budgets apply.
    """
    if not isinstance(plan, RepeatPartPlan):
        raise ValueError("Build a declared repeat-part plan first")
    offsets = {part.wcs: part.work_offset_mm for part in plan.parts}
    interpreted = ProgramOperations.from_text("\n".join(program.lines), work_offsets=offsets, cancelled=cancelled)
    if any(checkpoint.state.recovery_errors for checkpoint in interpreted.checkpoints):
        raise ValueError("Array simulation cannot resolve unsupported modal or rotary commands")
    used_frames = {checkpoint.state.wcs for checkpoint in interpreted.checkpoints if checkpoint.state.wcs}
    missing = used_frames - set(offsets)
    if missing:
        raise ValueError("Missing declared frame offsets: " + ", ".join(sorted(missing)))
    segments = simulation_segments(interpreted, work_offsets=offsets, cancelled=cancelled)
    tools = simulation_tools(definitions, {segment.tool_id for segment in segments})
    plan = plan.prepared(cancelled=cancelled)
    stocks = []
    total_voxels = 0
    for part in plan.parts:
        if cancelled():
            raise InterruptedError("Array calculation cancelled; previous scene retained")
        stock = initial_stock(plan.setup(part, machine_space=True), resolution_mm, cancelled=cancelled)
        total_voxels += prod(stock.shape)
        if total_voxels > 2_000_000:
            raise ValueError("Array exceeds the shared two-million voxel budget; use a coarser resolution")
        stocks.append(stock)
    reports, meshes, snapshots = [], {}, []
    remaining_faces = 100_000
    for part, stock in zip(plan.parts, stocks):
        if cancelled():
            raise InterruptedError("Array calculation cancelled; previous scene retained")
        scene = scene_from_geometry(geometry, MachineSetup(work_offset_mm=(0, 0, 0)), stock.bounds, cancelled=cancelled)
        report = simulate(segments, tools, stock, scene, cancelled=cancelled)
        if report.cancelled:
            raise InterruptedError("Array calculation cancelled; previous scene retained")
        mesh = stock_geometry(stock, max_faces=remaining_faces, cancelled=cancelled)
        remaining_faces -= len(mesh.indices) // 6
        if remaining_faces < 0:
            raise ValueError("Array exceeds the shared rest-stock face budget")
        reports.append(report)
        snapshots.append(stock.snapshot(cancelled=cancelled))
        meshes[part.wcs] = GeometrySnapshot(mesh.vertices, mesh.indices, cancelled=cancelled)
    return RepeatSimulation(
        plan, program.file_hash, segments, tuple(reports), meshes, interpreted.unresolved_motion_lines, tuple(snapshots)
    )
