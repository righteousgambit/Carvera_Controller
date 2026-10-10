"""Complete retained nominal CAD pose geometry for a detached inspection view."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import InitVar, dataclass
from fractions import Fraction as F
from typing import ClassVar

from carveracontroller.machine.joint_clearance import bodies_from_record, body_transform, corners
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_cad_first_contact import CadFirstContact, ContactPose, contact_pose
from carveracontroller.machine.program_surface_clearance import ProgramSurfaceClearance, group_member_contact
from carveracontroller.machine.surface_motion import Point, Triangle
from carveracontroller.machine.tool_preview import PreviewPose, mesh_center, project_mesh


@dataclass(frozen=True)
class RigidDisplayReference:
    """Ephemeral canonical CAD plus its exact translation, never archive evidence."""

    triangles: tuple[Triangle, ...]
    translation_mm: tuple[F, F, F]
    placed_triangles: tuple[Triangle, ...] | None = None


@dataclass(frozen=True)
class PoseViewBody:
    name: str
    triangles: tuple[Triangle, ...]
    envelope_only: bool
    highlighted_faces: tuple[int, ...]
    kind: str = "cad"
    rigid_reference: InitVar[RigidDisplayReference | None] = None
    display_reference: ClassVar[RigidDisplayReference | None] = None

    def __post_init__(self, rigid_reference: RigidDisplayReference | None) -> None:
        # InitVar keeps the archive schema unchanged. dataclasses.replace drops
        # this reference by default, so edited world geometry cannot reuse it.
        object.__setattr__(self, "display_reference", rigid_reference)


@dataclass(frozen=True)
class ContactPoseView:
    source_sha256: str
    pose: ContactPose
    pair: tuple[str, str]
    bodies: tuple[PoseViewBody, ...]
    member: int
    qualification: str = (
        "Detached nominal contact pose. Prepared CAD retains every original triangle; amber bodies are declared "
        "envelopes only, with absent manufactured geometry still unknown. Face colors identify original evidence, "
        "not physical contact. Display coordinates are approximate. Loaded program, active setup, live pose and "
        "controller execution remain separate."
    )


def _axis_placement(shift: F) -> Callable[[float], float]:
    """Exact placement once per distinct coordinate, scoped to this body/frame."""
    if not shift:
        # Fraction's zero result is positive, including a source negative zero.
        return lambda value: value or 0.0
    values: dict[float, float] = {}

    def place(value: float) -> float:
        result = values.get(value)
        if result is None:
            result = float(F(value) + shift)
            values[value] = result
        return result

    return place


def _point_placement(shift: tuple[F, F, F]) -> Callable[[Point], Point]:
    """Bind exact coordinate functions and shared corners to one body/frame."""
    place_x, place_y, place_z = (_axis_placement(value) for value in shift)
    placed_points: dict[Point, Point] = {}

    def place(point: Point) -> Point:
        placed = placed_points.get(point)
        if placed is None:
            placed = (place_x(point[0]), place_y(point[1]), place_z(point[2]))
            placed_points[point] = placed
        return placed

    return place


def prepare_contact_pose_view(
    report: ProgramSurfaceClearance,
    row: CadFirstContact,
    member: int = 0,
    *,
    previous: ContactPoseView | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> ContactPoseView:
    """Place all retained CAD and explicit missing-CAD envelopes, without rereading assets."""
    if row.pose is None or row.segment_index is None or row.lower is None:
        raise ValueError("Select a retained CAD contact pose first")
    pose = contact_pose(report, row.tool, row.segment_index, row.lower, cancelled=cancelled)
    if pose != row.pose or report.body_review.program_hash == "":
        raise ValueError("Contact pose differs from its retained source joints or body placements")
    if type(member) is not int or member < 0 or (row.group is None and member != 0):
        raise ValueError("Select an original contact-group member")
    contact = group_member_contact(row.group, member) if row.group is not None else row.surface
    highlights = (
        {row.first: contact.contact.first_triangle, row.second: contact.contact.second_triangle}
        if contact is not None
        else {}
    )
    return _prepare_pose_view(report, pose, (row.first, row.second), highlights, member, cancelled, previous)


def prepare_path_pose_view(
    report: ProgramSurfaceClearance,
    tool: int,
    move: int,
    sample: F,
    *,
    previous: ContactPoseView | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> ContactPoseView:
    """Complete assembly at any retained move; no invented contact record or highlight."""
    if type(move) is not int or not report.body_review.program_hash:
        raise ValueError("Playback requires a retained move and source identity")
    pose = contact_pose(report, tool, move, sample, cancelled=cancelled)
    return _prepare_pose_view(report, pose, ("", ""), {}, 0, cancelled, previous)


def _prepare_pose_view(
    report: ProgramSurfaceClearance,
    pose: ContactPose,
    pair: tuple[str, str],
    highlights: dict[str, int],
    member: int,
    cancelled: Callable[[], bool],
    previous: ContactPoseView | None,
) -> ContactPoseView:
    machine = machine_from_record(report.body_review.records[pose.tool])
    declared, _ = bodies_from_record(report.body_review.records[pose.tool], machine)
    by_name = {b.name: b for b in declared}
    meshes = report.meshes[pose.tool]
    if set(meshes) - set(by_name) or any(name and name not in by_name for name in pair):
        raise ValueError("Retained CAD or contact names differ from the complete declared assembly")
    if sum(len(mesh.triangles) for mesh in meshes.values()) > 250_000:
        raise ValueError("Complete contact-pose CAD exceeds the shared 250000-triangle bound; no faces omitted")
    bodies = []
    prior_bodies = (
        {body.name: body for body in previous.bodies}
        if previous is not None and previous.source_sha256 == report.body_review.program_hash
        else {}
    )
    zero = dict.fromkeys(("X", "Y", "Z"), 0.0)
    for placement in pose.bodies:
        if cancelled():
            raise InterruptedError("Complete contact-pose view cancelled")
        body = by_name[placement.name]
        mesh = meshes.get(body.name)
        transformed: list[Triangle] = []
        world: tuple[Triangle, ...]
        if mesh is not None:
            origin = body_transform(machine, body, zero).translation.tuple
            shift = tuple(placement.translation_mm[j] - F(origin[j]) for j in range(3))
            prior = prior_bodies.get(body.name)
            ref = prior.display_reference if prior is not None else None
            if (
                prior is not None
                and prior.kind == "cad"
                and not prior.envelope_only
                and ref is not None
                and ref.triangles is mesh.triangles
                and ref.translation_mm == shift
                and ref.placed_triangles is prior.triangles
                and len(prior.triangles) == len(mesh.triangles)
            ):
                world = prior.triangles
            else:
                place = _point_placement((shift[0], shift[1], shift[2]))
                for index, triangle in enumerate(mesh.triangles):
                    if index % 128 == 0 and cancelled():
                        raise InterruptedError("Complete contact-pose view cancelled")
                    # Equal corners share an immutable placed tuple in this body
                    # and frame. Every original triangle and order stays intact.
                    transformed.append((place(triangle[0]), place(triangle[1]), place(triangle[2])))
                world = tuple(transformed)
        else:
            # Exactly 12 illustrative box faces. They never supply surface-contact evidence.
            envelope_points = tuple(
                tuple(
                    float(placement.translation_mm[j])
                    + sum(placement.rotation[j * 3 + k] * point.tuple[k] for k in range(3))
                    for j in range(3)
                )
                for point in corners(body.bounds)
            )
            for axis in range(3):
                other = [j for j in range(3) if j != axis]
                for side in (0, 1):
                    base = side << (2 - axis)
                    a, b = 1 << (2 - other[0]), 1 << (2 - other[1])
                    for indices in ((base, base | a, base | a | b), (base, base | a | b, base | b)):
                        transformed.append(tuple(envelope_points[i] for i in indices))  # type: ignore[arg-type]
            world = tuple(transformed)
        selected = (highlights[body.name],) if body.name in highlights else ()
        if selected and (mesh is None or not 0 <= selected[0] < len(world)):
            raise ValueError("Highlighted original face is absent from retained CAD")
        reference = (
            RigidDisplayReference(mesh.triangles, (shift[0], shift[1], shift[2]), world) if mesh is not None else None
        )
        bodies.append(PoseViewBody(body.name, world, mesh is None, selected, rigid_reference=reference))
    if cancelled():
        raise InterruptedError("Complete contact-pose view cancelled")
    view = ContactPoseView(report.body_review.program_hash, pose, pair, tuple(bodies), member)
    if pair == ("", ""):
        from dataclasses import replace

        view = replace(
            view,
            qualification="Detached generated-path playback at the exact selected move parameter. Every original CAD face and explicit missing-CAD envelope is retained. No contact witness is inferred from this pose; live execution, compensation, measured registration and physical qualification remain separate.",
        )
    return view


def project_contact_pose_view(
    scene: ContactPoseView,
    pose: PreviewPose,
    names: tuple[str, ...],
    *,
    surfaces_only: bool = False,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[tuple[list[float], list[int]], ...]:
    """Worker-side, depth-sorted full geometry. GPU batches stay below 16-bit indices."""
    if not names or len(set(names)) != len(names) or set(names) - {b.name for b in scene.bodies}:
        raise ValueError("Choose retained bodies for the contact-pose view")
    if any(not math.isfinite(v) for v in pose.__dict__.values()) or min(pose.width, pose.height, pose.zoom) <= 0:
        raise ValueError("Contact-pose viewport must be finite and positive")
    vertices: list[float] = []
    counts: dict[str, int] = {}
    for body in scene.bodies:
        if body.name not in names:
            continue
        for index, triangle in enumerate(body.triangles):
            if index % 128 == 0 and cancelled():
                raise InterruptedError("Contact-pose projection superseded")
            selected = index in body.highlighted_faces
            if surfaces_only and not selected:
                continue
            counts[body.kind] = counts.get(body.kind, 0) + 1
            limits = {"cad": 250_000 + 32 * 12, "remaining": 200_000, "target": 200_000}
            if body.kind not in limits or counts[body.kind] > limits[body.kind]:
                raise ValueError("Complete contact-pose display exceeds retained scene bound")
            color = (
                (0.25, 1.0, 0.86)
                if selected and body.name == scene.pair[0]
                else (1.0, 0.35, 0.42)
                if selected
                else (0.95, 0.65, 0.25)
                if body.envelope_only
                else (0.35, 0.72, 0.92)
                if body.kind == "remaining"
                else (0.69, 0.49, 0.94)
                if body.kind == "target"
                else (0.25, 0.65, 0.64)
                if body.name == scene.pair[0]
                else (0.75, 0.4, 0.46)
                if body.name == scene.pair[1]
                else (0.47, 0.55, 0.63)
            )
            a, b, c = triangle
            u, v = tuple(b[j] - a[j] for j in range(3)), tuple(c[j] - a[j] for j in range(3))
            normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            length = math.sqrt(sum(n * n for n in normal))
            normal = (normal[0] / length, normal[1] / length, normal[2] / length) if length else (0.0, 0.0, 1.0)
            for point in triangle:
                vertices.extend((*point, *normal, *color, 1.0, 0.0, 0.0))
    if not vertices:
        if not surfaces_only and all(
            b.kind == "remaining" and not b.triangles for b in scene.bodies if b.name in names
        ):
            return ()
        raise ValueError("This result has no original contact surfaces; use the complete pose or body pair")
    projected, _indices = project_mesh(
        vertices, range(len(vertices) // 12), mesh_center(vertices, cancelled), pose, cancelled
    )
    # Fit the rotated extent, rather than assuming its midpoint stays at the
    # unrotated bounds center. Panning remains a deliberate viewport offset.
    coordinates = tuple(zip(projected[0::12], projected[1::12]))
    offset_x = (min(p[0] for p in coordinates) + max(p[0] for p in coordinates)) / 2 - pose.center_x
    offset_y = (min(p[1] for p in coordinates) + max(p[1] for p in coordinates)) / 2 - pose.center_y
    batches = []
    for offset in range(0, len(projected), 65535 * 12):
        if cancelled():
            raise InterruptedError("Contact-pose projection superseded")
        batch = projected[offset : offset + 65535 * 12]
        for index in range(0, len(batch), 12):
            batch[index] -= offset_x
            batch[index + 1] -= offset_y
        batches.append((batch, list(range(len(batch) // 12))))
    return tuple(batches)
