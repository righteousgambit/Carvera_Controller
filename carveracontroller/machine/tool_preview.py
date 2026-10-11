"""Worker-side projection of full cutter geometry, without widgets or hardware."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PreviewPose:
    yaw: float
    tilt: float
    zoom: float
    width: float
    height: float
    center_x: float
    center_y: float


def mesh_center(vertices: Sequence[float], cancelled: Callable[[], bool]) -> tuple[float, float, float]:
    low, high = [math.inf] * 3, [-math.inf] * 3
    if not vertices or len(vertices) % 12:
        raise ValueError("Tool preview mesh is empty or incomplete")
    for i in range(0, len(vertices), 12):
        if i % (12 * 128) == 0 and cancelled():
            raise InterruptedError("Tool preview closed")
        for axis in range(3):
            low[axis] = min(low[axis], vertices[i + axis])
            high[axis] = max(high[axis], vertices[i + axis])
    if cancelled():
        raise InterruptedError("Tool preview closed")
    return ((low[0] + high[0]) / 2, (low[1] + high[1]) / 2, (low[2] + high[2]) / 2)


def project_mesh(
    vertices: Sequence[float],
    indices: Sequence[int],
    center: Sequence[float],
    pose: PreviewPose,
    cancelled: Callable[[], bool],
) -> tuple[list[float], list[int]]:
    """Retain every triangle and old lighting/order; interrupt obsolete views."""
    cy, sy = math.cos(pose.yaw), math.sin(pose.yaw)
    ct, st = math.cos(pose.tilt), math.sin(pose.tilt)
    transformed = []
    low_x = low_z = math.inf
    high_x = high_z = -math.inf
    for i in range(0, len(vertices), 12):
        if i % (12 * 128) == 0 and cancelled():
            raise InterruptedError("Tool preview superseded")
        x, y, z = (vertices[i + j] - center[j] for j in range(3))
        x, y = cy * x - sy * y, sy * x + cy * y
        y, z = ct * y - st * z, st * y + ct * z
        nx, ny, nz = vertices[i + 3 : i + 6]
        nx, ny = cy * nx - sy * ny, sy * nx + cy * ny
        ny, nz = ct * ny - st * nz, st * ny + ct * nz
        shade = 0.35 + 0.65 * abs(ny)
        transformed.append((x, z, y, nx, ny, nz, *(c * shade for c in vertices[i + 6 : i + 9]), 1, 0, 0))
        low_x, high_x = min(low_x, x), max(high_x, x)
        low_z, high_z = min(low_z, z), max(high_z, z)
    if cancelled():
        raise InterruptedError("Tool preview superseded")
    if not transformed or not indices or len(indices) % 3:
        raise ValueError("Tool preview mesh is empty or incomplete")
    factor = min(pose.width / max(high_x - low_x, 0.01), pose.height / max(high_z - low_z, 0.01)) * 0.8 * pose.zoom
    triangles = []
    for i in range(0, len(indices), 3):
        if i % (3 * 128) == 0 and cancelled():
            raise InterruptedError("Tool preview superseded")
        triangle = indices[i : i + 3]
        triangles.append((sum(transformed[index][2] for index in triangle), triangle))
    triangles.sort(key=lambda pair: pair[0])
    projected = []
    for i, (_depth, triangle) in enumerate(triangles):
        if i % 128 == 0 and cancelled():
            raise InterruptedError("Tool preview superseded")
        for index in triangle:
            value = transformed[index]
            projected.extend((pose.center_x + value[0] * factor, pose.center_y + value[1] * factor, 0, *value[3:]))
    if cancelled():
        raise InterruptedError("Tool preview superseded")
    return projected, list(range(len(projected) // 12))
