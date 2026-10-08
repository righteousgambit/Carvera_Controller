"""Calibrated camera projection and bounded fitting, without machine motion.

World coordinates are millimetres. Pose maps world to camera coordinates; camera
X points right, Y down, Z forward. Calibration residuals describe image agreement,
not machine clearance, metrology accuracy, or physical qualification.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

Vec3 = tuple[float, float, float]
Pixel = tuple[float, float]


def _finite(values: Sequence[float]) -> None:
    if not all(math.isfinite(x) for x in values):
        raise ValueError("Camera data must be finite")


def _vec3(values: Sequence[float]) -> Vec3:
    if len(values) != 3:
        raise ValueError("Three coordinates required")
    return (float(values[0]), float(values[1]), float(values[2]))


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _cross(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a: Sequence[float]) -> Vec3:
    n = math.sqrt(_dot(a, a))
    if n < 1e-10:
        raise ValueError("Degenerate calibration geometry")
    return tuple(x / n for x in a)  # type: ignore[return-value]


def _rotation(v: Sequence[float]) -> list[list[float]]:
    theta = math.sqrt(_dot(v, v))
    a = math.sin(theta) / theta if theta > 1e-8 else 1 - theta * theta / 6
    b = (1 - math.cos(theta)) / (theta * theta) if theta > 1e-8 else 0.5 - theta * theta / 24
    x, y, z = v
    k = [[0, -z, y], [z, 0, -x], [-y, x, 0]]
    return [
        [float(i == j) + a * k[i][j] + b * sum(k[i][s] * k[s][j] for s in range(3)) for j in range(3)] for i in range(3)
    ]


def _rotvec(r: Sequence[Sequence[float]]) -> Vec3:
    theta = math.acos(max(-1.0, min(1.0, (sum(r[i][i] for i in range(3)) - 1) / 2)))
    if theta < 1e-7:
        return ((r[2][1] - r[1][2]) / 2, (r[0][2] - r[2][0]) / 2, (r[1][0] - r[0][1]) / 2)
    if abs(math.sin(theta)) < 1e-6:
        # Diagonal formula handles a half turn without division by sin(theta).
        axis = [math.sqrt(max(0.0, (r[i][i] + 1) / 2)) for i in range(3)]
        largest = max(range(3), key=lambda i: axis[i])
        for i in range(3):
            if i != largest and r[largest][i] < 0:
                axis[i] = -axis[i]
        return tuple(theta * x for x in _unit(axis))  # type: ignore[return-value]
    f = theta / (2 * math.sin(theta))
    return (f * (r[2][1] - r[1][2]), f * (r[0][2] - r[2][0]), f * (r[1][0] - r[0][1]))


def _solve(a: Sequence[Sequence[float]], b: Sequence[float]) -> list[float]:
    n = len(b)
    m = [list(row) + [v] for row, v in zip(a, b)]
    for j in range(n):
        p = max(range(j, n), key=lambda i: abs(m[i][j]))
        if abs(m[p][j]) < 1e-14:
            raise ValueError("Underdetermined calibration geometry")
        m[p], m[j] = m[j], m[p]
        scale = m[j][j]
        m[j] = [v / scale for v in m[j]]
        for i in range(n):
            if i != j:
                f = m[i][j]
                m[i] = [x - f * y for x, y in zip(m[i], m[j])]
    return [row[-1] for row in m]


def _least(rows: Sequence[Sequence[float]], target: Sequence[float]) -> list[float]:
    n = len(rows[0])
    return _solve(
        [[sum(r[i] * r[j] for r in rows) for j in range(n)] for i in range(n)],
        [sum(r[i] * v for r, v in zip(rows, target)) for i in range(n)],
    )


@dataclass(frozen=True)
class CameraIntrinsics:
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    distortion: tuple[float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        _finite((self.fx, self.fy, self.cx, self.cy, *self.distortion))
        if (
            not 1 <= self.width <= 32768
            or not 1 <= self.height <= 32768
            or self.fx <= 0
            or self.fy <= 0
            or len(self.distortion) != 5
        ):
            raise ValueError("Invalid camera intrinsics")

    def distort(self, x: float, y: float) -> Pixel:
        k1, k2, p1, p2, k3 = self.distortion
        r2 = x * x + y * y
        radial = 1 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
        return (
            x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x),
            y * radial + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y,
        )

    def undistort(self, pixel: Pixel) -> Pixel:
        """Return normalized ray coordinates using Newton inversion."""
        _finite(pixel)
        tx, ty = (pixel[0] - self.cx) / self.fx, (pixel[1] - self.cy) / self.fy
        x, y = tx, ty
        for _ in range(30):
            dx, dy = self.distort(x, y)
            ex, ey = dx - tx, dy - ty
            if math.hypot(ex, ey) < 1e-11:
                return x, y
            h = 1e-6
            ax, ay = self.distort(x + h, y)
            bx, by = self.distort(x, y + h)
            a, c = (ax - dx) / h, (ay - dy) / h
            b, d = (bx - dx) / h, (by - dy) / h
            det = a * d - b * c
            if abs(det) < 1e-12:
                break
            x -= (d * ex - b * ey) / det
            y -= (-c * ex + a * ey) / det
            if abs(x) > 20 or abs(y) > 20:
                break
        raise ValueError("Distortion inversion did not converge")

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "fx": self.fx,
            "fy": self.fy,
            "cx": self.cx,
            "cy": self.cy,
            "distortion": list(self.distortion),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CameraIntrinsics:
        return cls(
            int(data["width"]),
            int(data["height"]),
            float(data["fx"]),
            float(data["fy"]),
            float(data["cx"]),
            float(data["cy"]),
            cast(tuple[float, float, float, float, float], tuple(float(v) for v in data.get("distortion", [0] * 5))),
        )


@dataclass(frozen=True)
class CameraPose:
    rotation_vector: Vec3
    translation: Vec3

    def __post_init__(self) -> None:
        if len(self.rotation_vector) != 3 or len(self.translation) != 3:
            raise ValueError("Pose needs three rotation and translation coordinates")
        _finite((*self.rotation_vector, *self.translation))

    def transform(self, point: Vec3) -> Vec3:
        if len(point) != 3:
            raise ValueError("World point requires three coordinates")
        _finite(point)
        return tuple(_dot(row, point) + t for row, t in zip(_rotation(self.rotation_vector), self.translation))  # type: ignore[return-value]

    def to_dict(self) -> dict[str, Any]:
        return {"rotation_vector": list(self.rotation_vector), "translation": list(self.translation)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CameraPose:
        return cls(_vec3(data["rotation_vector"]), _vec3(data["translation"]))


@dataclass(frozen=True)
class RegistrationObservation:
    world_mm: Vec3
    pixel: Pixel

    def __post_init__(self) -> None:
        if len(self.world_mm) != 3 or len(self.pixel) != 2:
            raise ValueError("Observation needs a 3D point and a 2D pixel")
        _finite((*self.world_mm, *self.pixel))

    def to_dict(self) -> dict[str, Any]:
        return {"world_mm": list(self.world_mm), "pixel": list(self.pixel)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegistrationObservation:
        pixel = data["pixel"]
        if len(pixel) != 2:
            raise ValueError("Pixel requires two coordinates")
        return cls(_vec3(data["world_mm"]), (float(pixel[0]), float(pixel[1])))


@dataclass(frozen=True)
class CameraRegistration:
    intrinsics: CameraIntrinsics
    pose: CameraPose

    def project(self, world_mm: Vec3) -> Pixel:
        x, y, z = self.pose.transform(world_mm)
        if z <= 1e-6:
            raise ValueError("Point lies behind or on the camera plane")
        x, y = self.intrinsics.distort(x / z, y / z)
        return self.intrinsics.fx * x + self.intrinsics.cx, self.intrinsics.fy * y + self.intrinsics.cy

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "intrinsics": self.intrinsics.to_dict(), "pose": self.pose.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CameraRegistration:
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported registration schema")
        p = data["pose"]
        return cls(
            CameraIntrinsics.from_dict(data["intrinsics"]),
            CameraPose(tuple(p["rotation_vector"]), tuple(p["translation"])),
        )


@dataclass(frozen=True)
class CalibrationResult:
    registration: CameraRegistration
    residuals_px: tuple[float, ...]
    rms_px: float
    max_px: float
    outlier_indices: tuple[int, ...]
    warnings: tuple[str, ...]
    iterations: int
    geometry_condition: float = 1.0


def _initial_pose(
    intrinsics: CameraIntrinsics, observations: Sequence[RegistrationObservation]
) -> tuple[CameraPose, bool]:
    origin = observations[0].world_mm
    delta = [tuple(p.world_mm[i] - origin[i] for i in range(3)) for p in observations]
    u = _unit(max(delta, key=lambda x: _dot(x, x)))
    cross = max((_cross(u, d) for d in delta), key=lambda x: _dot(x, x))
    spread = math.sqrt(max(_dot(d, d) for d in delta))
    if math.sqrt(_dot(cross, cross)) / spread < 1e-4:
        raise ValueError("Degenerate calibration geometry: nearly collinear points")
    n = _unit(cross)
    v = _cross(n, u)
    planar = max(abs(_dot(d, n)) for d in delta) < 1e-5
    rays = [intrinsics.undistort(p.pixel) for p in observations]
    rows = []
    target = []
    if planar:
        for d, (x, y) in zip(delta, rays):
            a, b = _dot(d, u), _dot(d, v)
            rows.extend(([a, b, 1, 0, 0, 0, -x * a, -x * b], [0, 0, 0, a, b, 1, -y * a, -y * b]))
            target.extend((x, y))
        h = _least(rows, target) + [1.0]
        c1 = [h[0], h[3], h[6]]
        c2 = [h[1], h[4], h[7]]
        scale = 2 / (math.sqrt(_dot(c1, c1)) + math.sqrt(_dot(c2, c2)))
        if h[8] * scale < 0:
            scale = -scale
        r1 = _unit([x * scale for x in c1])
        r2 = _unit([x * scale - _dot([q * scale for q in c2], r1) * r1[i] for i, x in enumerate(c2)])
        r3 = _cross(r1, r2)
        basis = [u, v, n]
        cols = [r1, r2, r3]
        r = [[sum(cols[k][i] * basis[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        t = [h[i] * scale - _dot(r[j], origin) for j, i in enumerate((2, 5, 8))]
    else:
        if len(observations) < 6:
            raise ValueError("Nonplanar pose initialization needs at least six points")
        for p, (x, y) in zip(observations, rays):
            a, b, c = p.world_mm
            rows.extend(
                ([a, b, c, 1, 0, 0, 0, 0, -x * a, -x * b, -x * c], [0, 0, 0, 0, a, b, c, 1, -y * a, -y * b, -y * c])
            )
            target.extend((x, y))
        h = _least(rows, target) + [1.0]
        rr = [h[0:3], h[4:7], h[8:11]]
        scale = sum(math.sqrt(_dot(row, row)) for row in rr) / 3
        if _dot(_cross(rr[0], rr[1]), rr[2]) < 0:
            scale = -scale
        r1 = _unit([x / scale for x in rr[0]])
        r2 = _unit([rr[1][i] / scale - _dot([x / scale for x in rr[1]], r1) * r1[i] for i in range(3)])
        r = [list(r1), list(r2), list(_cross(r1, r2))]
        t = [h[i] / scale for i in (3, 7, 11)]
    return CameraPose(_rotvec(r), tuple(t)), planar  # type: ignore[arg-type]


def _refine(
    parameters: list[float], residual_fn: Callable[[list[float]], list[float]], max_iterations: int
) -> tuple[list[float], int]:
    damping = 1e-3
    residual = residual_fn(parameters)
    for iteration in range(max_iterations):
        jac = []
        for j, p in enumerate(parameters):
            h = 1e-5 * max(1.0, abs(p))
            shifted = parameters.copy()
            shifted[j] += h
            try:
                after = residual_fn(shifted)
            except (ValueError, OverflowError):
                raise ValueError("Calibration Jacobian outside valid projection domain") from None
            jac.append([(a - b) / h for a, b in zip(after, residual)])
        # Huber weights limit a misidentified fixture hole's influence.
        weights = [min(1.0, 3 / max(1e-12, abs(v))) for v in residual]
        n = len(parameters)
        normal = [[sum(w * a * b for w, a, b in zip(weights, jac[i], jac[j])) for j in range(n)] for i in range(n)]
        for i in range(n):
            normal[i][i] += damping * max(1.0, normal[i][i])
        rhs = [-sum(w * a * b for w, a, b in zip(weights, jac[i], residual)) for i in range(n)]
        step = _solve(normal, rhs)
        proposed = [p + d for p, d in zip(parameters, step)]
        try:
            candidate = residual_fn(proposed)
        except (ValueError, OverflowError):
            damping *= 10
            continue

        def loss(rs: Sequence[float]) -> float:
            return sum(v * v if abs(v) <= 3 else 6 * abs(v) - 9 for v in rs)

        if loss(candidate) < loss(residual):
            parameters, residual = proposed, candidate
            damping = max(1e-9, damping / 3)
            if max(abs(x) for x in step) < 1e-8:
                return parameters, iteration + 1
        else:
            damping *= 10
            if damping > 1e12:
                return parameters, iteration + 1
    return parameters, max_iterations


def fit_camera_pose(
    intrinsics: CameraIntrinsics,
    observations: Sequence[RegistrationObservation],
    initial_pose: CameraPose | None = None,
    *,
    max_iterations: int = 80,
) -> CalibrationResult:
    """Fit camera extrinsics; intrinsics must come from independent calibration.

    Four noncollinear planar points suffice with an intrinsic prior. Nonplanar
    initialization needs six points. A poor intrinsic prior remains systematic
    error even when the fitting residual is small.
    """
    if not 4 <= len(observations) <= 500 or not 1 <= max_iterations <= 200:
        raise ValueError("Pose fitting needs 4 to 500 observations and 1 to 200 iterations")
    initialized, planar = _initial_pose(intrinsics, observations)
    pose = initial_pose or initialized

    def residual(parameters: list[float]) -> list[float]:
        reg = CameraRegistration(intrinsics, CameraPose(_vec3(parameters[:3]), _vec3(parameters[3:])))
        return [q - p for o in observations for q, p in zip(reg.project(o.world_mm), o.pixel)]

    parameters, iterations = _refine([*pose.rotation_vector, *pose.translation], residual, max_iterations)
    reg = CameraRegistration(intrinsics, CameraPose(_vec3(parameters[:3]), _vec3(parameters[3:])))
    errors = tuple(math.dist(reg.project(o.world_mm), o.pixel) for o in observations)
    rms = math.sqrt(sum(x * x for x in errors) / len(errors))
    warnings = ["Image fit is not physical or metrology qualification"]
    if planar:
        warnings.append("Planar calibration relies on independently valid lens intrinsics")
    world_span = max(math.dist(a.world_mm, b.world_mm) for a in observations for b in observations)
    pixel_span = max(math.dist(a.pixel, b.pixel) for a in observations for b in observations)
    geometry_condition = pixel_span / max(intrinsics.width, intrinsics.height)
    if geometry_condition < 0.1:
        warnings.append("Small image coverage makes camera pose and raised-stock projection weakly constrained")
    if world_span < 1:
        warnings.append("Calibration world baseline is below one millimetre")
    if rms > 2:
        warnings.append("High reprojection residual: check lens calibration and hole correspondences")
    return CalibrationResult(
        reg,
        errors,
        rms,
        max(errors),
        tuple(i for i, e in enumerate(errors) if e > 3),
        tuple(warnings),
        iterations,
        geometry_condition,
    )


def calibrate_camera(
    intrinsics_prior: CameraIntrinsics,
    boards: Sequence[Sequence[RegistrationObservation]],
    *,
    fit_distortion: bool = True,
    max_iterations: int = 100,
) -> tuple[CameraIntrinsics, tuple[CalibrationResult, ...]]:
    """Joint intrinsic and per-board pose refinement from varied board views.

    Requires three distinct tilted views and at least eight points per view.
    Board world coordinates may be reused because each view has its own pose.
    The returned residuals are calibration evidence, not dimensional accuracy.
    """
    if not 3 <= len(boards) <= 12 or any(not 8 <= len(b) <= 100 for b in boards) or not 1 <= max_iterations <= 200:
        raise ValueError("Intrinsic calibration needs 3 to 12 views of 8 to 100 points")
    fits = [fit_camera_pose(intrinsics_prior, b) for b in boards]
    normals = [_rotation(f.registration.pose.rotation_vector)[2] for f in fits]
    if max(math.dist(a, b) for a in normals for b in normals) < 0.15:
        raise ValueError("Calibration views need distinctly different board tilts")
    n_intrinsic = 9 if fit_distortion else 4
    params = [math.log(intrinsics_prior.fx), math.log(intrinsics_prior.fy), intrinsics_prior.cx, intrinsics_prior.cy]
    if fit_distortion:
        params.extend(intrinsics_prior.distortion)
    for f in fits:
        params.extend((*f.registration.pose.rotation_vector, *f.registration.pose.translation))

    def camera(p: list[float]) -> CameraIntrinsics:
        fx, fy = math.exp(p[0]), math.exp(p[1])
        if (
            not 0.1 * intrinsics_prior.width < fx < 10 * intrinsics_prior.width
            or not 0.1 * intrinsics_prior.height < fy < 10 * intrinsics_prior.height
            or not -intrinsics_prior.width < p[2] < 2 * intrinsics_prior.width
            or not -intrinsics_prior.height < p[3] < 2 * intrinsics_prior.height
        ):
            raise ValueError("Intrinsic calibration escaped plausible bounds")
        d = tuple(p[4:9]) if fit_distortion else intrinsics_prior.distortion
        if max(abs(x) for x in d) > 5:
            raise ValueError("Distortion calibration escaped plausible bounds")
        return CameraIntrinsics(intrinsics_prior.width, intrinsics_prior.height, fx, fy, p[2], p[3], d)  # type: ignore[arg-type]

    def residual(p: list[float]) -> list[float]:
        intrinsic = camera(p)
        result = []
        for i, board in enumerate(boards):
            start = n_intrinsic + 6 * i
            reg = CameraRegistration(
                intrinsic, CameraPose(_vec3(p[start : start + 3]), _vec3(p[start + 3 : start + 6]))
            )
            result.extend(q - r for o in board for q, r in zip(reg.project(o.world_mm), o.pixel))
        return result

    params, _ = _refine(params, residual, max_iterations)
    intrinsic = camera(params)
    return intrinsic, tuple(
        fit_camera_pose(
            intrinsic,
            b,
            CameraPose(
                _vec3(params[n_intrinsic + 6 * i : n_intrinsic + 6 * i + 3]),
                _vec3(params[n_intrinsic + 6 * i + 3 : n_intrinsic + 6 * i + 6]),
            ),
        )
        for i, b in enumerate(boards)
    )
