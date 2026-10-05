"""Exact rendered-mesh selection and local placement deltas, without UI or I/O."""

import math
from dataclasses import dataclass


def vector(value):
    if len(value) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError("Scene vectors must contain three finite numbers")
    return tuple(value)


def subtract(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def ray(origin, direction):
    origin, direction = vector(origin), vector(direction)
    length = math.sqrt(dot(direction, direction))
    if length < 1e-10 or not math.isfinite(length):
        raise ValueError("Scene ray direction is degenerate")
    return origin, tuple(v / length for v in direction)


def triangle_distance(origin, direction, points):
    a, b, c = points
    edge1, edge2 = subtract(b, a), subtract(c, a)
    p = cross(direction, edge2)
    determinant = dot(edge1, p)
    if abs(determinant) < 1e-10:
        return None
    inverse = 1 / determinant
    distance_a = subtract(origin, a)
    u = dot(distance_a, p) * inverse
    if u < -1e-9 or u > 1 + 1e-9:
        return None
    q = cross(distance_a, edge1)
    v = dot(direction, q) * inverse
    if v < -1e-9 or u + v > 1 + 1e-9:
        return None
    distance = dot(edge2, q) * inverse
    return distance if distance >= 0 else None


def pick_geometry(origin, direction, components, max_distance=None):
    """Nearest two-sided indexed triangle; translated machine-frame meshes.

    components contains (name, Geometry, rendered movement). Metadata snapshots
    are immutable for the duration of the worker. A hole in a mesh remains a
    miss; bounding envelopes are not used as a substitute for a surface hit.
    """
    origin, direction = ray(origin, direction)
    if max_distance is not None and (
        type(max_distance) not in (int, float) or not math.isfinite(max_distance) or max_distance < 0
    ):
        raise ValueError("Pick distance must be finite and nonnegative")
    selected, nearest = None, math.inf
    for name, geometry, movement in components:
        local_origin = subtract(origin, vector(movement))
        vertices, indices = geometry.vertices, geometry.indices
        for index in range(0, len(indices), 3):
            points = [vertices[i * 10 : i * 10 + 3] for i in indices[index : index + 3]]
            distance = triangle_distance(local_origin, direction, points)
            if distance is not None and distance < nearest and (max_distance is None or distance <= max_distance):
                selected, nearest = name, distance
    return None if selected is None else (selected, nearest)


def plane_point(origin, direction, point, normal):
    origin, direction = ray(origin, direction)
    point, normal = vector(point), vector(normal)
    denominator = dot(direction, normal)
    if abs(denominator) < 1e-8:
        raise ValueError("Choose an angled view for this placement plane")
    distance = dot(subtract(point, origin), normal) / denominator
    if distance < 0:
        raise ValueError("Placement plane is behind the camera")
    return tuple(origin[i] + direction[i] * distance for i in range(3))


def placement_delta(start, end, axis, snap_mm=0):
    if axis not in ("XY", "Z"):
        raise ValueError("Choose XY or Z placement")
    if type(snap_mm) not in (int, float) or not math.isfinite(snap_mm) or snap_mm < 0:
        raise ValueError("Grid snap must be finite and nonnegative")
    delta = subtract(vector(end), vector(start))
    delta = tuple(value if (i == 2) == (axis == "Z") else 0 for i, value in enumerate(delta))
    return tuple(round(v / snap_mm) * snap_mm if snap_mm else v for v in delta)


def inverse_projection(model, projection):
    """Invert P*M using full homogeneous column-major renderer matrices.

    Kivy's affine matrix helpers are unsuitable for perspective unprojection.
    This bounded 4x4 elimination retains the perspective row explicitly.
    """
    if len(model) != 16 or len(projection) != 16:
        raise ValueError("Scene matrices require sixteen entries")
    if any(not math.isfinite(v) for v in (*model, *projection)):
        raise ValueError("Scene matrices must be finite")
    rows = [
        [sum(projection[k * 4 + r] * model[c * 4 + k] for k in range(4)) for c in range(4)]
        + [float(r == c) for c in range(4)]
        for r in range(4)
    ]
    for c in range(4):
        pivot = max(range(c, 4), key=lambda r: abs(rows[r][c]))
        if abs(rows[pivot][c]) < 1e-12:
            raise ValueError("Scene projection is not invertible")
        rows[c], rows[pivot] = rows[pivot], rows[c]
        divisor = rows[c][c]
        rows[c] = [v / divisor for v in rows[c]]
        for r in range(4):
            if r != c:
                amount = rows[r][c]
                rows[r] = [a - amount * b for a, b in zip(rows[r], rows[c])]
    return tuple(tuple(row[4:]) for row in rows)


def homogeneous_point(inverse, x, y, z):
    point = (x, y, z, 1)
    result = tuple(dot(row, point) for row in inverse)
    if any(not math.isfinite(v) for v in result) or abs(result[3]) < 1e-12:
        raise ValueError("Scene projection is at infinity")
    return tuple(v / result[3] for v in result[:3])


def rotation_step(start, end, pivot):
    """Signed incremental XY angle; callers accumulate steps across the wrap."""
    a, b = subtract(vector(start), vector(pivot)), subtract(vector(end), vector(pivot))
    lengths = (math.hypot(*a[:2]), math.hypot(*b[:2]))
    if any(not math.isfinite(v) or v < 1e-8 for v in lengths):
        raise ValueError("Drag the rotation ring away from its pivot")
    a, b = tuple(v / lengths[0] for v in a[:2]), tuple(v / lengths[1] for v in b[:2])
    return math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))


def snap_angle(angle, step=0):
    if type(angle) not in (int, float) or not math.isfinite(angle):
        raise ValueError("Rotation must be finite")
    if type(step) not in (int, float) or not math.isfinite(step) or not 0 <= step <= 180:
        raise ValueError("Angle snap must be between zero and 180 degrees")
    return round(angle / step) * step if step else angle


def canonical_angle(angle):
    return (snap_angle(angle) + 180) % 360 - 180


def near_polyline(point, points, tolerance):
    """Screen-space ring hit, including perspective-flattened segments."""
    if len(points) % 2 or len(point) != 2 or tolerance < 0:
        raise ValueError("Invalid screen-space hit region")
    for i in range(0, len(points) - 2, 2):
        a, b = points[i : i + 2], points[i + 2 : i + 4]
        delta = subtract(b, a)
        size = dot(delta, delta)
        t = max(0, min(1, dot(subtract(point, a), delta) / size)) if size else 0
        if sum((point[j] - a[j] - t * delta[j]) ** 2 for j in (0, 1)) <= tolerance**2:
            return True
    return False


@dataclass(frozen=True)
class RenderedMesh:
    vertices: tuple
    indices: tuple


def render_tool_snapshot(snapshot):
    """Exact pointer-shader vertices mapped from render space to machine mm.

    Shader rotation uses xyz directly, without a homogeneous divide. Color,
    normals and texture coordinates do not alter the surface intersection.
    """
    vertices, indices, rotation = snapshot["vertices"], snapshot["indices"], snapshot["rotation"]
    scale = snapshot["scale"]
    offset, center, work = (vector(snapshot[key]) for key in ("offset", "center", "work_offset"))
    if type(scale) not in (int, float) or not math.isfinite(scale) or scale <= 0:
        raise ValueError("Render scale must be positive")
    if len(vertices) % 12 or len(indices) % 3 or len(rotation) != 16:
        raise ValueError("Invalid rendered cutter mesh")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in rotation):
        raise ValueError("Render rotation must be finite")
    count = len(vertices) // 12
    if any(type(i) is not int or not 0 <= i < count for i in indices):
        raise ValueError("Invalid rendered cutter index")
    result = []
    for start in range(0, len(vertices), 12):
        point = vector(vertices[start : start + 3])
        rotated = tuple(sum(rotation[c * 4 + r] * point[c] for c in range(3)) + rotation[12 + r] for r in range(3))
        machine = vector(tuple((rotated[i] + offset[i] + center[i]) / scale + work[i] for i in range(3)))
        result.extend((*machine, 0, 0, 1, 1, 1, 1, 1))
    return RenderedMesh(tuple(result), tuple(indices))
