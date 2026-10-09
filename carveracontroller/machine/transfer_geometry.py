"""Continuous nominal clearance for an explicitly coaxial spindle handoff.

Z increases from the source toward the receiver. Opposing chuck faces bound
annular bodies and blind cylindrical bores. No jaws, phase, compliance, cutting
tools, CAD surfaces or machine adapter are inferred from these declarations.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Callable


@dataclass(frozen=True)
class Chuck:
    body_length_mm: float
    outer_diameter_mm: float
    bore_diameter_mm: float
    bore_depth_mm: float


@dataclass(frozen=True)
class TransferGeometry:
    step: str
    axis: str
    stock_start_z_mm: float
    stock_end_z_mm: float
    stock_diameter_mm: float
    source_face_z_mm: float
    receiver_start_z_mm: float
    receiver_end_z_mm: float
    source: Chuck
    receiver: Chuck
    clearance_mm: float = 0


@dataclass(frozen=True)
class Contact:
    code: str
    surface_a: str
    surface_b: str
    fraction: float
    receiver_face_z_mm: float


@dataclass(frozen=True)
class TransferStudy:
    geometry: TransferGeometry
    contacts: tuple[Contact, ...]
    source_engagement_mm: float
    receiver_engagement_mm: float
    required_engagement_mm: float
    source_required_engagement_mm: float
    minimum_clearance_mm: float

    @property
    def accepted(self) -> bool:
        return (
            not self.contacts
            and self.source_engagement_mm >= self.source_required_engagement_mm
            and self.receiver_engagement_mm >= self.required_engagement_mm
        )


def _record(value: object, keys: set[str], title: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{title} requires exactly: {', '.join(sorted(keys))}")
    return value


def _number(value: object, title: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{title} must be numeric millimetres")
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise ValueError(f"{title} exceeds bounds")
    if not math.isfinite(result) or abs(result) > 10000 or positive and result <= 0:
        raise ValueError(f"{title} must be finite within 10000 mm" + (" and positive" if positive else ""))
    return result


def _chuck(value: object, title: str) -> Chuck:
    row = _record(value, set(Chuck.__dataclass_fields__), title)
    chuck = Chuck(**{key: _number(row[key], f"{title} {key}", positive=True) for key in Chuck.__dataclass_fields__})
    if chuck.bore_diameter_mm >= chuck.outer_diameter_mm or chuck.bore_depth_mm >= chuck.body_length_mm:
        raise ValueError(f"{title}: blind bore must fit strictly inside chuck body")
    return chuck


def geometry_from_record(value: object) -> TransferGeometry:
    row = _record(value, set(TransferGeometry.__dataclass_fields__), "Coaxial transfer geometry")
    step = row["step"]
    if not isinstance(step, str) or not step or len(step) > 64:
        raise ValueError("Transfer geometry needs a bounded step ID")
    axis = row["axis"]
    if not isinstance(axis, str) or not axis or len(axis) > 64:
        raise ValueError("Transfer geometry needs a declared approach axis ID")
    numbers = {
        key: _number(row[key], key)
        for key in TransferGeometry.__dataclass_fields__
        if key not in ("step", "axis", "source", "receiver")
    }
    geometry = TransferGeometry(
        step,
        axis,
        source=_chuck(row["source"], "Source chuck"),
        receiver=_chuck(row["receiver"], "Receiver chuck"),
        **numbers,
    )
    if (
        geometry.stock_diameter_mm <= 0
        or geometry.stock_end_z_mm <= geometry.stock_start_z_mm
        or geometry.clearance_mm < 0
    ):
        raise ValueError("Stock requires positive diameter/length and nonnegative clearance")
    if geometry.receiver_start_z_mm < geometry.receiver_end_z_mm:
        raise ValueError("Coaxial approach must move toward decreasing Z")
    return geometry


def geometry_record(geometry: TransferGeometry) -> dict[str, object]:
    return asdict(geometry)


def receiver_face(geometry: TransferGeometry, fraction: float) -> float:
    if not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError("Approach fraction must lie between zero and one")
    return geometry.receiver_start_z_mm + fraction * (geometry.receiver_end_z_mm - geometry.receiver_start_z_mm)


def engagement(start: float, end: float, bore_start: float, bore_end: float) -> float:
    return max(0.0, min(end, bore_end) - max(start, bore_start))


def study_transfer(
    geometry: TransferGeometry,
    required_mm: float,
    cancelled: Callable[[], bool] | None = None,
    *,
    source_required_mm: float | None = None,
) -> TransferStudy:
    """Analytic first contact across the whole linear approach, without sampling."""
    if cancelled is not None and cancelled():
        raise ValueError("Transfer geometry review cancelled")
    g = geometry_from_record(geometry_record(geometry))
    required = _number(required_mm, "Required engagement", positive=True)
    source_required = (
        required
        if source_required_mm is None
        else _number(source_required_mm, "Required source engagement", positive=True)
    )
    source, receiver = g.source, g.receiver
    radius = g.stock_diameter_mm / 2
    contacts = []

    def contact(code: str, a: str, b: str, low: float, high: float) -> None:
        if g.receiver_end_z_mm > high or g.receiver_start_z_mm < low:
            return
        travel = g.receiver_start_z_mm - g.receiver_end_z_mm
        fraction = max(0.0, (g.receiver_start_z_mm - high) / travel) if travel else 0.0
        contacts.append(Contact(code, a, b, fraction, receiver_face(g, fraction)))

    def initial(code: str, a: str, b: str) -> None:
        contacts.append(Contact(code, a, b, 0.0, g.receiver_start_z_mm))

    # Each axisymmetric solid is (radial lower/upper, axial lower/upper).
    # Annular walls plus full-radius blind ends exactly represent the declared
    # chuck solids, including one chuck nesting inside the other's open bore.
    stock = (0.0, radius, g.stock_start_z_mm, g.stock_end_z_mm)
    source_solids = (
        (
            "source bore wall",
            (
                source.bore_diameter_mm / 2,
                source.outer_diameter_mm / 2,
                g.source_face_z_mm - source.body_length_mm,
                g.source_face_z_mm,
            ),
        ),
        (
            "source blind bore bottom",
            (
                0.0,
                source.outer_diameter_mm / 2,
                g.source_face_z_mm - source.body_length_mm,
                g.source_face_z_mm - source.bore_depth_mm,
            ),
        ),
    )
    receiver_solids = (
        (
            "receiver bore entrance",
            (receiver.bore_diameter_mm / 2, receiver.outer_diameter_mm / 2, 0.0, receiver.body_length_mm),
        ),
        (
            "receiver blind bore bottom",
            (0.0, receiver.outer_diameter_mm / 2, receiver.bore_depth_mm, receiver.body_length_mm),
        ),
    )

    def radial_overlap(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
        return max(a[0], b[0]) <= min(a[1], b[1]) + g.clearance_mm

    for index, (name, solid) in enumerate(source_solids):
        if radial_overlap(stock, solid) and max(stock[2], solid[2]) <= min(stock[3], solid[3]) + g.clearance_mm:
            initial("source_bore" if index == 0 else "source_bottom", "stock cylinder", name)
    for index, (name, moving) in enumerate(receiver_solids):
        if radial_overlap(stock, moving):
            contact(
                "receiver_bore" if index == 0 else "receiver_bottom",
                "stock cylinder",
                name,
                stock[2] - moving[3] - g.clearance_mm,
                stock[3] - moving[2] + g.clearance_mm,
            )
        for source_name, static in source_solids:
            if radial_overlap(static, moving):
                contact(
                    "chuck_bodies",
                    source_name,
                    name,
                    static[2] - moving[3] - g.clearance_mm,
                    static[3] - moving[2] + g.clearance_mm,
                )
    source_wall = source.bore_diameter_mm / 2 - radius
    source_bottom = g.stock_start_z_mm - (g.source_face_z_mm - source.bore_depth_mm)
    receiver_wall = receiver.bore_diameter_mm / 2 - radius
    contacts.sort(key=lambda entry: (entry.fraction, entry.code))
    source_engagement = engagement(
        g.stock_start_z_mm, g.stock_end_z_mm, g.source_face_z_mm - source.bore_depth_mm, g.source_face_z_mm
    )
    receiving_engagement = engagement(
        g.stock_start_z_mm, g.stock_end_z_mm, g.receiver_end_z_mm, g.receiver_end_z_mm + receiver.bore_depth_mm
    )
    clearances = [
        source_wall,
        source_bottom,
        receiver_wall,
        g.receiver_end_z_mm + receiver.bore_depth_mm - g.stock_end_z_mm,
    ]
    if radial_overlap(source_solids[0][1], receiver_solids[0][1]):
        clearances.append(g.receiver_end_z_mm - g.source_face_z_mm)
    return TransferStudy(
        g, tuple(contacts), source_engagement, receiving_engagement, required, source_required, min(clearances)
    )


def example_geometry(step: str = "grip", axis: str = "Z-shared") -> TransferGeometry:
    """Nominal coaxial dimensions for the explicit demonstration only."""
    return TransferGeometry(step, axis, -15, 50, 20, 0, 80, 44, Chuck(50, 80, 24, 20), Chuck(50, 80, 24, 12), 0.5)
