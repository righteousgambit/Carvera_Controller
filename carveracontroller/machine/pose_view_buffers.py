"""Complete object-space display buffers and constant-size camera calculations."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from itertools import product

from carveracontroller.machine.contact_pose_view import ContactPoseView
from carveracontroller.machine.tool_preview import PreviewPose


@dataclass(frozen=True)
class PoseBuffers:
    batches: tuple[tuple[list[float], list[int]], ...]
    low: tuple[float, float, float]
    high: tuple[float, float, float]
    triangles: int


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
    cancelled: Callable[[], bool] = lambda: False,
) -> PoseBuffers:
    """Preserve every selected face; no camera transform, ordering or decimation."""
    if not names or len(set(names)) != len(names) or set(names) - {b.name for b in scene.bodies}:
        raise ValueError("Choose retained bodies for the contact-pose view")
    low, high = [math.inf] * 3, [-math.inf] * 3
    counts: dict[str, int] = {}
    limits = {"cad": 250_000 + 32 * 12, "remaining": 200_000, "target": 200_000}
    vertices: list[float] = []
    batches: list[tuple[list[float], list[int]]] = []
    total = 0
    for body in scene.bodies:
        if body.name not in names:
            continue
        highlighted = set(body.highlighted_faces)
        for index, triangle in enumerate(body.triangles):
            if index % 128 == 0 and cancelled():
                raise InterruptedError("Contact-pose buffers superseded")
            selected = index in highlighted
            if surfaces_only and not selected:
                continue
            counts[body.kind] = counts.get(body.kind, 0) + 1
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
            if any(not math.isfinite(v) or abs(v) > 1e30 for point in triangle for v in point):
                raise ValueError("Pose display coordinates exceed finite GPU range")
            a, b, c = triangle
            u, v = tuple(b[j] - a[j] for j in range(3)), tuple(c[j] - a[j] for j in range(3))
            normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            length = math.hypot(*normal)
            normal = (normal[0] / length, normal[1] / length, normal[2] / length) if length else (0.0, 0.0, 1.0)
            for point in triangle:
                for axis, value in enumerate(point):
                    low[axis], high[axis] = min(low[axis], value), max(high[axis], value)
                vertices.extend((*point, *normal, *color, 1.0, 0.0, 0.0))
            total += 1
            if len(vertices) == 65535 * 12:
                batches.append((vertices, list(range(65535))))
                vertices = []
    if cancelled():
        raise InterruptedError("Contact-pose buffers superseded")
    if vertices:
        batches.append((vertices, list(range(len(vertices) // 12))))
    if not batches:
        if not surfaces_only and all(
            b.kind == "remaining" and not b.triangles for b in scene.bodies if b.name in names
        ):
            return PoseBuffers((), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0)
        raise ValueError("This result has no original contact surfaces; use the complete pose or body pair")
    return PoseBuffers(tuple(batches), (low[0], low[1], low[2]), (high[0], high[1], high[2]), total)


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
