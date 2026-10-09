"""Read-only coordinate explanation; configured CAD frames are not measurements."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import cos, isfinite, radians, sin

from carveracontroller.addons.manufacturing_simulation.orientation import StockOrientation
from carveracontroller.machine.observed_pose import ObservedPose

Vec3 = tuple[float, float, float]


def vector(values: Sequence[float]) -> Vec3:
    if len(values) != 3 or not all(isfinite(v) for v in values):
        raise ValueError("Coordinates require three finite millimetre values")
    return float(values[0]), float(values[1]), float(values[2])


def subtract(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def rotate(point: Vec3, angle: float) -> Vec3:
    if not isfinite(angle):
        raise ValueError("Frame rotation must be finite")
    c, s = cos(radians(angle)), sin(radians(angle))
    return c * point[0] - s * point[1], s * point[0] + c * point[1], point[2]


@dataclass(frozen=True)
class FrameReview:
    name: str
    point_mm: Vec3 | None
    source: str
    relation: str
    display_value: str | None = None


def review_coordinates(
    point: Sequence[float],
    work_offset: Sequence[float],
    stock_origin: Sequence[float],
    stock_size: Sequence[float] | None,
    stock_rotation: float,
    vise_pivot: Sequence[float] | None,
    vise_offset: Sequence[float],
    vise_rotation: float,
    jaw_offset: float,
    cad_translation: Sequence[float],
    pose: ObservedPose | None,
    now: float,
    stock_tilt: tuple[float, float] = (0, 0),
) -> tuple[FrameReview, ...]:
    point, offset, origin = vector(point), vector(work_offset), vector(stock_origin)
    bed = tuple(a + b for a, b in zip(point, offset))
    rows = [
        FrameReview("Program/WCS point", point, "Entered review point", "No controller write"),
        FrameReview("Configured bed point", vector(bed), "Configured preview offset", f"Program + {offset} mm"),
        FrameReview(
            "Fixture frame",
            None,
            "Unknown measured registration",
            "CAD geometry alone does not locate a physical fixture datum",
        ),
    ]
    if stock_size is None:
        rows.append(
            FrameReview(
                "Stock local point", None, "Stock dimensions unknown", "Center of rotation cannot be established"
            )
        )
    else:
        size = vector(stock_size)
        if min(size) <= 0:
            raise ValueError("Stock dimensions must be positive")
        pivot = tuple(a + b / 2 for a, b in zip(origin, size))
        orientation = StockOrientation.from_z_tilt(stock_rotation, stock_tilt)
        relative = orientation.apply(subtract(point, vector(pivot)), inverse=True)
        local = tuple(relative[i] + size[i] / 2 for i in range(3))
        rows.append(
            FrameReview(
                "Stock local point",
                vector(local),
                "Configured stock geometry",
                f"Inverse X/Y/Z {orientation.degrees}° (Rz·Ry·Rx) about stock center; zero is the unrotated lower corner",
            )
        )
    if vise_pivot is None:
        rows.append(FrameReview("Vise / jaw point", None, "Vise CAD pivot unknown", "No invented datum"))
    else:
        pivot, translation, placement = vector(vise_pivot), vector(cad_translation), vector(vise_offset)
        bed_origin = tuple(pivot[i] + translation[i] + placement[i] for i in range(3))
        local = rotate(subtract(vector(bed), vector(bed_origin)), -vise_rotation)
        if not isfinite(jaw_offset):
            raise ValueError("Jaw displacement must be finite")
        rows += [
            FrameReview(
                "Vise pivot-relative point",
                local,
                "Configured CAD placement",
                f"Bed origin {bed_origin}; inverse {vise_rotation:g}°",
            ),
            FrameReview(
                "Movable-jaw relative point",
                subtract(local, (0, jaw_offset, 0)),
                "Configured jaw displacement",
                f"Vise local − (0, {jaw_offset:g}, 0); actual contact unknown",
            ),
        ]
    if pose is None or not pose.fresh(now):
        rows.append(
            FrameReview(
                "Reported machine/work relation",
                None,
                "Missing or stale telemetry",
                "Refresh for one fresh packet; configured preview remains separate",
            )
        )
    else:
        rotated_point = rotate(point, pose.rotation_deg)
        effective_offset = pose.reported_offset_mm
        estimated = vector(tuple(rotated_point[i] + effective_offset[i] for i in range(3)))
        rows += [
            FrameReview(
                "Reported machine point",
                pose.machine_mm,
                "Fresh controller packet",
                f"Reported work point {pose.work_mm}; WCS index {pose.wcs_index}",
            ),
            FrameReview(
                "Reported effective offset",
                pose.reported_offset_mm,
                "Derived from that same packet",
                f"MPos − Rz({pose.rotation_deg:g}°)·WPos; does not isolate individual compensation owners",
            ),
            FrameReview(
                "Reported review-point estimate",
                estimated,
                "Algebraic comparison using one fresh packet",
                f"Entered point {point}; Rz({pose.rotation_deg:g}°)·point + effective offset {effective_offset}. "
                f"Assumes the entered point belongs to reported WCS index {pose.wcs_index}; "
                f"holds rotary A={pose.rotary_deg:g}° and compensation state fixed. "
                "Does not resolve rotary/tool compensation owners or qualify a machine target; no command is sent.",
            ),
            FrameReview(
                "Reported versus preview difference",
                subtract(estimated, vector(bed)),
                "Difference between algebraic estimate and configured preview",
                "Reported review-point estimate − configured bed point for the same entered point. "
                "A difference identifies disagreement, not its cause or a correction to apply.",
            ),
            FrameReview(
                "Reported tool length",
                None,
                "Controller-reported value; unmeasured here",
                f"T{pose.tool}: {pose.tool_length_mm} mm; kept separate, not added again to reported MPos",
            ),
        ]
    return tuple(rows)


@dataclass(frozen=True)
class FramePath:
    """A displayed dependency, not a measured machine transform hierarchy."""

    review: FrameReview
    parent: str | None
    group: str
    relationship: str


def coordinate_paths(rows: Sequence[FrameReview]) -> tuple[FramePath, ...]:
    """Keep configured calculations, missing registrations and packet fields apart."""
    names = {row.name for row in rows}
    if len(names) != len(rows):
        raise ValueError("Coordinate review names must be unique")
    parents = {
        "Configured bed point": ("Program/WCS point", "Configured transformation"),
        "Stock local point": ("Program/WCS point", "Configured transformation"),
        "Vise pivot-relative point": ("Configured bed point", "Configured transformation"),
        "Vise / jaw point": ("Configured bed point", "Unresolved transformation"),
        "Movable-jaw relative point": ("Vise pivot-relative point", "Configured transformation"),
        "Reported effective offset": ("Reported machine point", "Same-packet derivation"),
        "Reported review-point estimate": ("Reported effective offset", "Conditional algebraic comparison"),
        "Reported versus preview difference": ("Reported review-point estimate", "Preview disagreement"),
        "Reported tool length": ("Reported machine point", "Packet metadata · not added to position"),
    }
    result = []
    for row in rows:
        parent, relationship = parents.get(row.name, (None, "Independent reference"))
        if parent is not None and parent not in names:
            raise ValueError(f"Missing coordinate dependency: {parent}")
        group = (
            "Controller packet snapshot"
            if row.name.startswith("Reported")
            else "Unregistered fixture"
            if row.name == "Fixture frame"
            else "Configured preview calculations"
        )
        if row.point_mm is None and relationship == "Configured transformation":
            relationship = "Unresolved transformation"
        result.append(FramePath(row, parent, group, relationship))
    return tuple(result)
