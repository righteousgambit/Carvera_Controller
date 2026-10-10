"""Complete object-space display buffers and constant-size camera calculations."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from itertools import product

from carveracontroller.machine.contact_pose_view import ContactPoseView
from carveracontroller.machine.surface_motion import Triangle
from carveracontroller.machine.tool_preview import PreviewPose


@dataclass(frozen=True)
class PoseBodyBuffers:
    name: str
    geometry: tuple[Triangle, ...]
    appearance: tuple[object, ...]
    translation: tuple[float, float, float]
    batches: tuple[tuple[list[float], list[int]], ...]
    low: tuple[float, float, float]
    high: tuple[float, float, float]
    triangles: int


@dataclass(frozen=True)
class PoseBuffers:
    batches: tuple[tuple[list[float], list[int]], ...]
    low: tuple[float, float, float]
    high: tuple[float, float, float]
    triangles: int
    bodies: tuple[PoseBodyBuffers, ...] = ()


@dataclass(frozen=True)
class PoseCamera:
    center: tuple[float, float, float]
    rotation: tuple[float, float, float, float]
    scale: float
    offset: tuple[float, float]
    depth_scale: float


def prepare_pose_buffers(
    scene: ContactPoseView,
    names: tuple[str, ...],
    *,
    surfaces_only: bool = False,
    previous: PoseBuffers | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> PoseBuffers:
    """Complete per-body geometry, with transactional reuse of immutable sources.

    Only the immediately accepted body set is retained, not a frame history.
    Every face cap applies before reuse. World-space evidence remains intact;
    trusted ephemeral CAD references supply translation-only display instances.
    Edited/deserialized bodies fall back to their complete world geometry.
    """
    if not names or len(set(names)) != len(names) or set(names) - {b.name for b in scene.bodies}:
        raise ValueError("Choose retained bodies for the contact-pose view")
    if len({b.name for b in scene.bodies}) != len(scene.bodies):
        raise ValueError("Retained body names must be unique")
    low, high = [math.inf] * 3, [-math.inf] * 3
    counts: dict[str, int] = {}
    limits = {"cad": 250_000 + 32 * 12, "remaining": 200_000, "target": 200_000}
    prior = {b.name: b for b in previous.bodies} if previous is not None else {}
    bodies = []
    for body in scene.bodies:
        if cancelled():
            raise InterruptedError("Contact-pose buffers superseded")
        if body.name not in names:
            continue
        reference = body.display_reference
        geometry = reference.triangles if reference is not None else body.triangles
        translation = tuple(float(v) for v in reference.translation_mm) if reference is not None else (0.0, 0.0, 0.0)
        if reference is not None and (body.kind != "cad" or body.envelope_only or len(geometry) != len(body.triangles)):
            raise ValueError("Rigid display reference differs from complete retained CAD")
        if any(not math.isfinite(v) or abs(v) > 1e30 for v in translation):
            raise ValueError("Pose display translation exceeds finite GPU range")
        highlighted = set(body.highlighted_faces)
        count = sum(0 <= i < len(geometry) for i in highlighted) if surfaces_only else len(geometry)
        counts[body.kind] = counts.get(body.kind, 0) + count
        if body.kind not in limits or counts[body.kind] > limits[body.kind]:
            raise ValueError("Complete contact-pose display exceeds retained scene bound")
        appearance = (
            body.kind,
            body.envelope_only,
            body.highlighted_faces,
            body.name == scene.pair[0],
            body.name == scene.pair[1],
            surfaces_only,
        )
        accepted = prior.get(body.name)
        if accepted is not None and accepted.geometry is geometry and accepted.appearance == appearance:
            prepared = replace(accepted, translation=(translation[0], translation[1], translation[2]))
        else:
            vertices: list[float] = []
            batches: list[tuple[list[float], list[int]]] = []
            body_low, body_high = [math.inf] * 3, [-math.inf] * 3
            total = 0
            for index, triangle in enumerate(geometry):
                if index % 128 == 0 and cancelled():
                    raise InterruptedError("Contact-pose buffers superseded")
                selected = index in highlighted
                if surfaces_only and not selected:
                    continue
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
                if any(not math.isfinite(v) or abs(v) > 1e30 for point in triangle for v in point):
                    raise ValueError("Pose display coordinates exceed finite GPU range")
                points = [(float(p[0]), float(p[1]), float(p[2])) for p in triangle]
                triangle = (points[0], points[1], points[2])
                a, b, c = triangle
                u, v = tuple(b[j] - a[j] for j in range(3)), tuple(c[j] - a[j] for j in range(3))
                normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
                length = math.hypot(*normal)
                normal = (normal[0] / length, normal[1] / length, normal[2] / length) if length else (0.0, 0.0, 1.0)
                for point in triangle:
                    for axis, value in enumerate(point):
                        body_low[axis], body_high[axis] = min(body_low[axis], value), max(body_high[axis], value)
                    vertices.extend((*point, *normal, *color, 1.0, 0.0, 0.0))
                total += 1
                if len(vertices) == 65535 * 12:
                    batches.append((vertices, list(range(65535))))
                    vertices = []
            if vertices:
                batches.append((vertices, list(range(len(vertices) // 12))))
            if not batches:
                body_low, body_high = [0.0] * 3, [0.0] * 3
            prepared = PoseBodyBuffers(
                body.name,
                geometry,
                appearance,
                (translation[0], translation[1], translation[2]),
                tuple(batches),
                (body_low[0], body_low[1], body_low[2]),
                (body_high[0], body_high[1], body_high[2]),
                total,
            )
        if prepared.triangles:
            for axis in range(3):
                lo, hi = prepared.low[axis] + translation[axis], prepared.high[axis] + translation[axis]
                if not math.isfinite(lo) or not math.isfinite(hi) or max(abs(lo), abs(hi)) > 1e30:
                    raise ValueError("Pose display coordinates exceed finite GPU range")
                low[axis], high[axis] = min(low[axis], lo), max(high[axis], hi)
        bodies.append(prepared)
    if cancelled():
        raise InterruptedError("Contact-pose buffers superseded")
    batches_out = tuple(batch for body in bodies for batch in body.batches)
    if not batches_out:
        if not surfaces_only and all(
            b.kind == "remaining" and not b.triangles for b in scene.bodies if b.name in names
        ):
            return PoseBuffers((), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0, tuple(bodies))
        raise ValueError("This result has no original contact surfaces; use the complete pose or body pair")
    return PoseBuffers(
        batches_out,
        (low[0], low[1], low[2]),
        (high[0], high[1], high[2]),
        sum(b.triangles for b in bodies),
        tuple(bodies),
    )


def pose_camera(buffers: PoseBuffers, pose: PreviewPose) -> PoseCamera:
    """Fit the eight rotated bounds corners; cost does not depend on face count.

    The box may leave more padding than the exact vertex extent. It contains
    every original face at every orbit; no geometry or visibility is sampled.
    Depth coordinates reserve a margin inside the clipping planes.
    """
    if any(not math.isfinite(v) for v in pose.__dict__.values()) or min(pose.width, pose.height, pose.zoom) <= 0:
        raise ValueError("Contact-pose viewport must be finite and positive")
    center = (
        (buffers.low[0] + buffers.high[0]) / 2,
        (buffers.low[1] + buffers.high[1]) / 2,
        (buffers.low[2] + buffers.high[2]) / 2,
    )
    cy, sy, ct, st = math.cos(pose.yaw), math.sin(pose.yaw), math.cos(pose.tilt), math.sin(pose.tilt)
    points = []
    for corner in product(*zip(buffers.low, buffers.high)):
        x, y, z = (corner[j] - center[j] for j in range(3))
        x, y = cy * x - sy * y, sy * x + cy * y
        points.append((x, st * y + ct * z, ct * y - st * z))
    low_x, high_x = min(p[0] for p in points), max(p[0] for p in points)
    low_z, high_z = min(p[1] for p in points), max(p[1] for p in points)
    scale = min(pose.width / max(high_x - low_x, 0.01), pose.height / max(high_z - low_z, 0.01)) * 0.8 * pose.zoom
    offset = (pose.center_x - (low_x + high_x) / 2 * scale, pose.center_y - (low_z + high_z) / 2 * scale)
    return PoseCamera(center, (cy, sy, ct, st), scale, offset, 0.9 / max(max(abs(p[2]) for p in points), 0.01))
