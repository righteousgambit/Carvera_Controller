"""Scene component relationships and geometry bounds; no UI or transport."""

from __future__ import annotations

from carveracontroller.addons.machine_simulation.geometry_snapshot import Bounds, GeometrySnapshot, indexed_bounds

from .scene_interaction import IndexedMesh

COMPONENT_TITLES = {
    "outer": "Outer machine",
    "table": "Machine bed",
    "fixture": "Fixture plate",
    "workholding": "Vise",
    "stock": "Stock",
    "spindle": "Spindle",
    "cutter": "Cutter / mill",
    "atc": "ATC / slots",
}
RELATIONSHIPS = (
    ("outer", "table", "contains"),
    ("outer", "spindle", "contains"),
    ("table", "fixture", "supports"),
    ("table", "atc", "carries"),
    ("fixture", "workholding", "mounts"),
    ("workholding", "stock", "holds (declared)"),
    ("spindle", "cutter", "holds (preview)"),
    ("atc", "cutter", "stores (unreconciled)"),
    ("cutter", "stock", "machines (planned)"),
)
GEOMETRY_GROUPS: dict[str, tuple[str, ...]] = {key: (key,) for key in COMPONENT_TITLES if key != "cutter"}
GEOMETRY_GROUPS["outer"] = ("fixed", "carriage")
EVIDENCE_GROUPS = {
    "outer": ("workholding", "offsets"),
    "table": ("workholding", "offsets"),
    "fixture": ("workholding",),
    "workholding": ("workholding", "stock"),
    "stock": ("stock", "offsets"),
    "spindle": ("tools", "offsets"),
    "cutter": ("tools", "offsets"),
    "atc": ("tools",),
}


def related_components(key: str) -> tuple[tuple[str, str], ...]:
    if key not in COMPONENT_TITLES:
        raise ValueError("Unknown scene component")
    return tuple(
        (other, f"{COMPONENT_TITLES[a]} {relation} {COMPONENT_TITLES[b]}")
        for a, b, relation in RELATIONSHIPS
        if key in (a, b)
        for other in (b if key == a else a,)
    )


def geometry_bounds(geometry: IndexedMesh) -> Bounds | None:
    """Bounds of rendered indexed vertices, in the geometry's own frame."""
    if isinstance(geometry, GeometrySnapshot):
        return geometry.bounds
    return indexed_bounds(geometry.vertices, geometry.indices)
