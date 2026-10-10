"""Complete generated material at the exact retained nominal contact time."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from fractions import Fraction as F
from math import prod
from typing import Any, cast

from carveracontroller.addons.manufacturing_simulation import StockVolume, SweptTool, Vec3
from carveracontroller.machine.contact_pose_view import ContactPoseView, PoseViewBody
from carveracontroller.machine.joint_clearance import bodies_from_record, body_transform
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_cad_first_contact import contact_pose
from carveracontroller.machine.program_stock_evolution import StockEvolution
from carveracontroller.machine.simulation_preview import stock_geometry
from carveracontroller.machine.stock_generated_clearance import GeneratedMachineClearance, _context
from carveracontroller.machine.stock_generated_finish import _state_stock
from carveracontroller.machine.surface_motion import Triangle


@dataclass(frozen=True)
class ContactMaterial:
    view: ContactPoseView
    state: str
    stock: str
    before_mm3: float
    remaining_mm3: float
    removed_mm3: float
    cell_work: int
    resolution_mm: float
    replayed_moves: int = 0
    qualification: str = (
        "Blue: complete remaining grid boundary after every preceding generated move and the selected move's "
        "partial cutting sweep. Purple: original declared target faces. Cells represent center-classified material, "
        "not measured surfaces or certified clearance. Rapid moves retain material. Nominal work-chain placement, "
        "stock orientation and WCS offset are retained; effective compensation, manufactured flutes, live registration, "
        "backend execution and physical machining remain unqualified."
    )


class MaterialCursor:
    """One complete prefix snapshot, committed only after a whole view validates.

    Single-worker ownership is required. Partial sweeps never enter the prefix;
    backwards seeks start from the selected independent initial state. Memory
    is bounded by one stock grid, not a mask for every move in the job.
    """

    def __init__(self, source: GeneratedMachineClearance, state: str) -> None:
        self.source, self.state = source, state
        self.next_move = 0
        self.checkpoint: dict[str, Any] | None = None
        self.before_mm3: float | None = None


def prepare_contact_material(
    result: GeneratedMachineClearance,
    view: ContactPoseView,
    state: str,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    max_cell_work: int = 50_000_000,
    max_boundary_faces: int = 100_000,
    cursor: MaterialCursor | None = None,
) -> ContactMaterial:
    """Replay to the exact contact parameter; no final-stock substitution or decimation."""
    plan, parent, pose = result.plan, result.parent, view.pose
    if type(max_cell_work) is not int or not 1 <= max_cell_work <= 50_000_000:
        raise ValueError("Contact material exceeds shared complete cell-work budget")
    if type(max_boundary_faces) is not int or not 1 <= max_boundary_faces <= 100_000:
        raise ValueError("Contact material exceeds complete boundary-face budget")
    if state not in plan.states or state not in plan.analysis.fits:
        raise ValueError("Choose a retained independent stock state")
    if cursor is not None and (cursor.source is not result or cursor.state != state):
        raise ValueError("Material playback cursor belongs to a different path or stock state")
    if (
        view.source_sha256 != result.proposal_sha256
        or result.scene.body_review.program_hash != result.proposal_sha256
        or pose.tool != plan.tool
        or pose != contact_pose(result.scene, pose.tool, pose.segment_index, pose.sample, cancelled=cancelled)
        or _context(plan, parent, cancelled) != result.proposal_sha256
        or any(body.kind != "cad" for body in view.bodies)
    ):
        raise ValueError("Contact material differs from retained generated path, pose or parent")
    evolution = parent.stock_evolution
    if not isinstance(evolution, StockEvolution):
        raise ValueError("Contact material needs retained initial stock and tools")
    target = plan.analysis.target
    if result.replaced_initial_stock != target.stock or any(
        a is not b for a, b in zip(target.bindings, (parent.body_review, evolution, parent.rotating_envelopes))
    ):
        raise ValueError("Contact material belongs to a different retained stock review")

    def verify_scene() -> None:
        record: dict[str, Any] = dict(parent.body_review.records[plan.tool])
        record["collision_bodies"] = [r for r in record["collision_bodies"] if r["name"] != target.stock]
        record["collision_exclusions"] = [p for p in record["collision_exclusions"] if target.stock not in p]
        if result.scene.body_review.records[plan.tool] != record or len(result.scene.body_review.segments) != len(
            plan.moves
        ):
            raise ValueError("Contact material machine declarations differ from retained parent")
        segment = result.scene.body_review.segments[pose.segment_index]
        move = plan.moves[pose.segment_index]
        if (
            segment.start.tuple != (Vec3(*move.start) + Vec3(*plan.stock_offset_mm)).tuple
            or segment.end.tuple != (Vec3(*move.end) + Vec3(*plan.stock_offset_mm)).tuple
            or segment.tool_id != str(plan.tool)
            or segment.cutting != move.cutting
            or tuple(b.name for b in view.bodies) != tuple(b.name for b in pose.bodies)
        ):
            raise ValueError("Contact material move or complete assembly differs from retained generated path")

    verify_scene()
    grid = StockVolume.from_snapshot(target.target, cancelled=cancelled)
    geometry = evolution.inputs.tools[plan.tool]
    work = prod(grid.shape) * (
        2 + (pose.segment_index + 1) * (len(SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), geometry).sections()) + 1)
    )
    if work > max_cell_work:
        raise ValueError("Contact material exhausted shared complete cell-work budget; no sampled prefix")
    reuse = (
        cursor is not None
        and cursor.checkpoint is not None
        and (
            cursor.next_move <= pose.segment_index or (pose.sample == 1 and cursor.next_move == pose.segment_index + 1)
        )
    )
    if reuse:
        assert cursor is not None and cursor.checkpoint is not None and cursor.before_mm3 is not None
        stock = StockVolume.from_snapshot(cursor.checkpoint, cancelled=cancelled)
        before, start = cursor.before_mm3, cursor.next_move
    else:
        stock, _missing = _state_stock(plan.analysis, state, grid, cancelled)
        before, start = stock.remaining_volume_mm3, 0
    checkpoint = None
    next_move = pose.segment_index + (pose.sample == 1)
    for index in range(start, pose.segment_index + 1):
        move = plan.moves[index]
        if cancelled():
            raise InterruptedError("Contact material replay cancelled; no partial view")
        if cursor is not None and index == pose.segment_index and pose.sample != 1:
            checkpoint = stock.snapshot(cancelled=cancelled)
        if move.cutting:
            end = move.end
            if index == pose.segment_index:
                end = cast(
                    tuple[float, float, float],
                    tuple(float(F(a) + pose.sample * (F(b) - F(a))) for a, b in zip(move.start, move.end)),
                )
            stock.subtract(SweptTool(Vec3(*move.start), Vec3(*end), geometry), cancelled=cancelled)
    if cursor is not None and checkpoint is None:
        checkpoint = stock.snapshot(cancelled=cancelled)
    # Geometry is in the stock's rotated program frame. Apply its WCS datum
    # before its original work-chain transform, including negative table Y.
    machine = machine_from_record(parent.body_review.records[plan.tool])
    declared, _ = bodies_from_record(parent.body_review.records[plan.tool], machine)
    body = next((b for b in declared if b.name == target.stock), None)
    if body is None or body.frame != "work":
        raise ValueError("Selected stock has no retained work-chain attachment")
    transform = body_transform(machine, body, dict(zip(("X", "Y", "Z"), map(float, pose.joints_mm))))
    offset = Vec3(*plan.stock_offset_mm)

    def place(point: tuple[float, float, float]) -> tuple[float, float, float]:
        return transform.apply(Vec3(*point) + offset).tuple

    boundary = stock_geometry(stock, max_boundary_faces, cancelled=cancelled)
    triangles: list[Triangle] = []
    for index in range(0, len(boundary.indices), 3):
        if index % 384 == 0 and cancelled():
            raise InterruptedError("Contact material boundary placement cancelled")
        points = [
            place((boundary.vertices[j * 10], boundary.vertices[j * 10 + 1], boundary.vertices[j * 10 + 2]))
            for j in boundary.indices[index : index + 3]
        ]
        triangles.append((points[0], points[1], points[2]))
    original: list[Triangle] = []
    if len(target.solid.mesh.triangles_mm) > 200_000:
        raise ValueError("Complete target exceeds retained input face budget")
    shift = Vec3(*target.translation_mm)
    for index, triangle in enumerate(target.solid.mesh.triangles_mm):
        if index % 128 == 0 and cancelled():
            raise InterruptedError("Contact target placement cancelled")
        points = [place(grid.program_point(Vec3(*p) + shift).tuple) for p in triangle]
        original.append((points[0], points[1], points[2]))
    names = {b.name for b in view.bodies}
    remaining_name, target_name = f"Remaining stock · {target.stock}", f"Part target · {target.stock}"
    if names.intersection((remaining_name, target_name)) or remaining_name == target_name:
        raise ValueError("Contact material names collide with retained machine bodies")
    bodies = view.bodies + (
        PoseViewBody(remaining_name, tuple(triangles), False, (), "remaining"),
        PoseViewBody(target_name, tuple(original), False, (), "target"),
    )
    if _context(plan, parent, cancelled) != result.proposal_sha256 or cancelled():
        raise ValueError("Generated path or parent changed during complete material preparation")
    verify_scene()
    if cursor is not None:
        cursor.checkpoint, cursor.next_move, cursor.before_mm3 = checkpoint, next_move, before
    return ContactMaterial(
        replace(view, bodies=bodies),
        state,
        target.stock,
        before,
        stock.remaining_volume_mm3,
        before - stock.remaining_volume_mm3,
        work,
        stock.resolution_mm,
        max(0, pose.segment_index + 1 - start),
    )
