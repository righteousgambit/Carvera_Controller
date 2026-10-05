"""Declared-frame multi-stock subtraction; no controller transport or offsets."""

from dataclasses import dataclass
from math import prod

from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot
from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3, simulate
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
    segments: tuple
    reports: tuple
    geometries: dict
    unresolved_lines: tuple


def simulate_repeat_parts(program, plan, definitions, geometry, resolution_mm, *, cancelled=lambda: False):
    """Apply actual transformed motions to every stock, including cross-part engagement.

    Translation-only G54–G59 declarations. Unknown initial machine position remains
    unresolved; unsupported modal/rotary commands reject publication. Outputs use
    machine millimetres. Every part sees the entire ordered path, so a cutter can
    engage a different part than the selected WCS. Global voxel/face budgets apply.
    """
    if not isinstance(plan, RepeatPartPlan):
        raise ValueError("Build a declared repeat-part plan first")
    offsets = {part.wcs: part.work_offset_mm for part in plan.parts}
    interpreted = ProgramOperations.from_text("\n".join(program.lines), work_offsets=offsets)
    if any(checkpoint.state.recovery_errors for checkpoint in interpreted.checkpoints):
        raise ValueError("Array simulation cannot resolve unsupported modal or rotary commands")
    used_frames = {checkpoint.state.wcs for checkpoint in interpreted.checkpoints if checkpoint.state.wcs}
    missing = used_frames - set(offsets)
    if missing:
        raise ValueError("Missing declared frame offsets: " + ", ".join(sorted(missing)))
    segments = simulation_segments(interpreted, work_offsets=offsets)
    tools = simulation_tools(definitions, {segment.tool_id for segment in segments})
    stocks = []
    total_voxels = 0
    for part in plan.parts:
        if cancelled():
            raise InterruptedError("Array calculation cancelled; previous scene retained")
        bounds = AABB(Vec3(*part.bounds[0]), Vec3(*part.bounds[1]))
        stock = StockVolume(bounds, resolution_mm, max_voxels=2_000_000)
        total_voxels += prod(stock.shape)
        if total_voxels > 2_000_000:
            raise ValueError("Array exceeds the shared two-million voxel budget; use a coarser resolution")
        stocks.append(stock)
    reports, meshes = [], {}
    remaining_faces = 100_000
    for part, stock in zip(plan.parts, stocks):
        if cancelled():
            raise InterruptedError("Array calculation cancelled; previous scene retained")
        scene = scene_from_geometry(geometry, MachineSetup(work_offset_mm=(0, 0, 0)), stock.bounds)
        report = simulate(segments, tools, stock, scene, cancelled=cancelled)
        if report.cancelled:
            raise InterruptedError("Array calculation cancelled; previous scene retained")
        mesh = stock_geometry(stock, max_faces=remaining_faces)
        remaining_faces -= len(mesh.indices) // 6
        if remaining_faces < 0:
            raise ValueError("Array exceeds the shared rest-stock face budget")
        reports.append(report)
        meshes[part.wcs] = GeometrySnapshot(mesh.vertices, mesh.indices)
    return RepeatSimulation(
        plan, program.file_hash, segments, tuple(reports), meshes, interpreted.unresolved_motion_lines
    )
