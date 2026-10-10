"""All-stock partial loaded-program replay with one validated complete prefix."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from fractions import Fraction as F
from math import ceil, isfinite, prod
from types import MappingProxyType
from typing import Any

from carveracontroller.addons.manufacturing_simulation import StockVolume, SweptTool, Vec3
from carveracontroller.machine.contact_pose_view import ContactPoseView, PoseViewBody
from carveracontroller.machine.joint_clearance import bodies_from_record, body_transform
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_cad_first_contact import contact_pose
from carveracontroller.machine.program_stock_evolution import (
    MAX_CELL_WORK,
    MAX_CELLS,
    StockEvolutionInput,
    review_stock_evolution,
)
from carveracontroller.machine.program_surface_clearance import ProgramSurfaceClearance
from carveracontroller.machine.repeat_parts import vector
from carveracontroller.machine.simulation_preview import stock_geometry
from carveracontroller.machine.surface_motion import Triangle


class ProgramMaterialCursor:
    """Single-worker ownership. A partial sweep never becomes a prefix checkpoint."""

    def __init__(self, report: ProgramSurfaceClearance) -> None:
        self.source = report
        self.next_move = 0
        self.checkpoint: Mapping[str, Mapping[str, Any]] | None = None


@dataclass(frozen=True)
class ProgramPlaybackMaterial:
    view: ContactPoseView
    snapshots: Mapping[str, Mapping[str, Any]]
    remaining_mm3: Mapping[str, float]
    cell_work: int
    replayed_moves: int
    qualification: str = (
        "Complete remaining cell boundaries, including all preceding moves and this partial sweep. "
        "Rapid moves and uncertified curve chords retain material. Cells are center-classified estimates; "
        "empty cells do not prove clearance. Original CAD/contact evidence remains retained separately."
    )


def prepare_program_material(
    report: ProgramSurfaceClearance,
    view: ContactPoseView,
    *,
    cursor: ProgramMaterialCursor | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    max_cell_work: int = MAX_CELL_WORK,
    max_boundary_faces: int = 100_000,
) -> ProgramPlaybackMaterial:
    evolution, body, pose = report.stock_evolution, report.body_review, view.pose
    if evolution is None or body.start_line != 1:
        raise ValueError("Remaining-stock playback needs complete ordered history from source line 1")
    if type(max_cell_work) is not int or not 1 <= max_cell_work <= MAX_CELL_WORK:
        raise ValueError("Playback exceeds shared complete cell-work budget")
    if type(max_boundary_faces) is not int or not 1 <= max_boundary_faces <= 100_000:
        raise ValueError("Playback exceeds complete boundary-face budget")
    if (
        view.source_sha256 != body.program_hash
        or view.pair != ("", "")
        or pose != contact_pose(report, pose.tool, pose.segment_index, pose.sample, cancelled=cancelled)
        or any(b.kind != "cad" for b in view.bodies)
        or tuple(b.name for b in view.bodies) != tuple(b.name for b in pose.bodies)
        or (cursor is not None and cursor.source is not report)
    ):
        raise ValueError("Playback material differs from retained source, complete assembly or nominal pose")
    count = len(evolution.inputs.stocks)
    if not count or len(evolution.steps) != count * len(body.segments):
        raise ValueError("Playback requires complete ordered move/stock history")
    # Admission always accounts for the complete prefix, even with a warm cursor.
    cells = 0
    for _, snapshot in evolution.inputs.stocks.values():
        low, high = vector(snapshot["minimum"]), vector(snapshot["maximum"])
        resolution = snapshot["resolution_mm"]
        if (
            type(resolution) not in (float, int)
            or not isfinite(resolution)
            or not 0.05 <= resolution <= 100
            or any(a >= b for a, b in zip(low, high))
        ):
            raise ValueError("Playback stock requires bounded finite dimensions and resolution")
        cells += prod(max(1, ceil((b - a) / resolution)) for a, b in zip(low, high))
        if cells > MAX_CELLS:
            raise ValueError("Playback exceeds shared two-million-cell budget before grid allocation")
    required = 0
    for index, segment in enumerate(body.segments[: pose.segment_index + 1]):
        if index % 128 == 0 and cancelled():
            raise InterruptedError("Playback material cancelled; no partial frame")
        geometry = evolution.inputs.tools[int(segment.tool_id)]
        required += cells * (len(SweptTool(segment.start, segment.end, geometry, segment.axis).sections()) + 1)
    if required > max_cell_work:
        raise ValueError("Playback exhausted shared complete cell-work budget; no sampled prefix")
    reuse = cursor is not None and cursor.checkpoint is not None and cursor.next_move <= pose.segment_index
    start = cursor.next_move if reuse and cursor is not None else 0
    snapshots = cursor.checkpoint if reuse and cursor is not None else None
    inputs = (
        StockEvolutionInput(
            MappingProxyType(
                {name: (offset, snapshots[name]) for name, (offset, _) in evolution.inputs.stocks.items()}
            ),
            evolution.inputs.tools,
        )
        if snapshots is not None
        else evolution.inputs
    )
    prefix = review_stock_evolution(
        replace(body, segments=body.segments[start : pose.segment_index]),
        inputs,
        report.rotating_envelopes,
        cancelled=cancelled,
        max_cell_work=max_cell_work,
    )
    normalized = tuple(replace(step, segment_index=step.segment_index + start) for step in prefix.steps)
    if normalized != evolution.steps[start * count : pose.segment_index * count]:
        raise ValueError("Playback reconstructed prefix differs from retained ordered history")
    checkpoint = prefix.final_snapshots
    segment = body.segments[pose.segment_index]
    end = Vec3(*(float(F(a) + pose.sample * (F(b) - F(a))) for a, b in zip(segment.start.tuple, segment.end.tuple)))
    partial = (
        segment
        if pose.sample == 1
        else replace(
            segment,
            end=end,
            source_end_ratio=segment.source_start_ratio
            + float(pose.sample) * (segment.source_end_ratio - segment.source_start_ratio),
        )
    )
    partial_inputs = StockEvolutionInput(
        MappingProxyType({name: (offset, checkpoint[name]) for name, (offset, _) in evolution.inputs.stocks.items()}),
        evolution.inputs.tools,
    )
    current = review_stock_evolution(
        replace(body, segments=(partial,)),
        partial_inputs,
        report.rotating_envelopes,
        cancelled=cancelled,
        max_cell_work=max_cell_work - prefix.cell_work,
    )
    if pose.sample == 1:
        normalized = tuple(replace(step, segment_index=pose.segment_index) for step in current.steps)
        if normalized != evolution.steps[pose.segment_index * count : (pose.segment_index + 1) * count]:
            raise ValueError("Playback complete move differs from retained ordered history")
        if pose.segment_index == len(body.segments) - 1 and current.final_snapshots != evolution.final_snapshots:
            raise ValueError("Playback final material differs from retained complete cells")
        checkpoint = current.final_snapshots
    machine = machine_from_record(body.records[pose.tool])
    declarations, _ = bodies_from_record(body.records[pose.tool], machine)
    declared = {b.name: b for b in declarations}
    bodies = [b for b in view.bodies if b.name not in evolution.inputs.stocks]
    volumes: dict[str, float] = {}
    faces = 0
    for name, snapshot in current.final_snapshots.items():
        stock = StockVolume.from_snapshot(snapshot, cancelled=cancelled)
        volumes[name] = stock.remaining_volume_mm3
        transform = body_transform(machine, declared[name], dict(zip(("X", "Y", "Z"), map(float, pose.joints_mm))))
        offset = Vec3(*evolution.inputs.stocks[name][0])
        boundary = stock_geometry(stock, max_boundary_faces - faces, cancelled=cancelled)
        faces += len(boundary.indices) // 6
        triangles: list[Triangle] = []
        for index in range(0, len(boundary.indices), 3):
            if index % 384 == 0 and cancelled():
                raise InterruptedError("Playback stock placement cancelled; no partial frame")
            points = [
                transform.apply(Vec3(*boundary.vertices[j * 10 : j * 10 + 3]) + offset).tuple
                for j in boundary.indices[index : index + 3]
            ]
            triangles.append((points[0], points[1], points[2]))
        bodies.append(PoseViewBody(name, tuple(triangles), False, (), "remaining"))
    if cancelled():
        raise InterruptedError("Playback material cancelled; no partial frame")
    if cursor is not None:
        cursor.checkpoint, cursor.next_move = checkpoint, pose.segment_index + (pose.sample == 1)
    return ProgramPlaybackMaterial(
        replace(view, bodies=tuple(bodies)),
        current.final_snapshots,
        MappingProxyType(volumes),
        prefix.cell_work + current.cell_work,
        pose.segment_index - start + 1,
    )
