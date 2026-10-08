"""Resolved-program simulation inputs and bounded rest-stock display geometry."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from math import isfinite
from typing import TypedDict

from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot
from carveracontroller.addons.machine_simulation.model import Geometry, MachineSetup
from carveracontroller.addons.manufacturing_simulation import (
    AABB,
    CollisionObstacle,
    CollisionScene,
    SimulationSegment,
    StockVolume,
    SweptTool,
    ToolGeometry,
    Vec3,
)
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
from carveracontroller.machine.assembly_envelopes import assembly_envelopes
from carveracontroller.machine.program_operations import ProgramOperations


def simulation_segments(
    program: ProgramOperations,
    start_line: int | None = None,
    end_line: int | None = None,
    *,
    work_offsets: Mapping[str, Sequence[float]] | None = None,
    reference_offset: Sequence[float] = (0, 0, 0),
    cancelled: Callable[[], bool] | None = None,
) -> tuple[SimulationSegment, ...]:
    def check(index: int = 0) -> None:
        if index % 128 == 0 and cancelled is not None and cancelled():
            raise InterruptedError("Simulation motion preparation cancelled")

    selected = []
    for index, segment in enumerate(program.motion_segments):
        check(index)
        if (start_line is None or segment.line_number >= start_line) and (
            end_line is None or segment.line_number <= end_line
        ):
            selected.append(segment)
    if work_offsets is not None:
        from carveracontroller.machine.repeat_parts import WCS_NAMES, vector

        if not isinstance(work_offsets, Mapping) or any(key not in WCS_NAMES for key in work_offsets):
            raise ValueError("Declare named work offsets before transforming motion")
        work_offsets = {key: vector(value) for key, value in work_offsets.items()}
        reference_offset = vector(reference_offset)
        missing = {segment.wcs for segment in selected} - set(work_offsets)
        if missing:
            raise ValueError("Missing declared frame offsets: " + ", ".join(sorted(str(frame) for frame in missing)))
    if work_offsets is None and len({segment.wcs for segment in selected}) > 1:
        raise ValueError("Multiple work offsets require registered instance transforms")
    if not selected:
        raise ValueError("No resolved motion segments in this selection")
    from math import dist

    totals = {}
    for index, segment in enumerate(program.motion_segments):
        check(index)
        totals[segment.line_number] = totals.get(segment.line_number, 0) + dist(segment.start_mm, segment.end_mm)
    accumulated, result = {}, []
    for index, segment in enumerate(selected):
        check(index)
        number = segment.line_number
        length, before = dist(segment.start_mm, segment.end_mm), accumulated.get(number, 0)
        total = totals[number]
        if work_offsets is not None:
            frame = segment.wcs
            if frame is None:
                raise ValueError("Missing declared frame offsets: None")
            offset = tuple(work_offsets[frame][a] - reference_offset[a] for a in range(3))
        else:
            offset = (0, 0, 0)
        result.append(
            SimulationSegment(
                Vec3(*(v + offset[a] for a, v in enumerate(segment.start_mm))),
                Vec3(*(v + offset[a] for a, v in enumerate(segment.end_mm))),
                str(segment.tool_id),
                segment.cutting,
                line=number,
                source_start_ratio=before / total if total else 0,
                source_end_ratio=(before + length) / total if total else 1,
            )
        )
        accumulated[number] = before + length
    check()
    return tuple(result)


def simulation_tool_issues(
    definitions: Mapping[int, ToolDefinition], required_ids: Iterable[str]
) -> tuple[tuple[str, str], ...]:
    """Check declared cutting dimensions without disk I/O or installed-tool inference."""
    issues = []
    for identifier in sorted(required_ids, key=str):
        try:
            simulation_tools(definitions, {identifier}, validate_assets=False)
        except (ValueError, TypeError) as exc:
            issues.append((str(identifier), str(exc)))
    return tuple(issues)


def simulation_tools(
    definitions: Mapping[int, ToolDefinition], required_ids: Iterable[str], *, validate_assets: bool = True
) -> dict[str, ToolGeometry]:
    result = {}
    for identifier in required_ids:
        if identifier == "None":
            raise ValueError("Resolved motion has no declared tool; establish T before that motion")
        if int(identifier) not in definitions:
            raise ValueError(f"Load an explicit profile for T{identifier}")
        definition = definitions[int(identifier)]
        shape = definition.tool_type.value
        shapes = {
            "flat_end_mill": "flat",
            "ball_end_mill": "ball",
            "bull_nose_end_mill": "bull",
            "drill": "drill",
            "chamfer_mill": "chamfer",
            "engraving": "engraving",
            "tapered_mill": "tapered",
            "thread_mill": "threadmill",
        }
        if shape not in shapes:
            raise ValueError(f"T{identifier}: this tool needs an axial cutting-envelope model")
        if not definition.stickout or not definition.flute_length:
            raise ValueError(f"T{identifier}: enter exposed stickout and flute length in the tool profile")
        if not definition.shank_diameter:
            raise ValueError(f"T{identifier}: enter shank diameter in the tool profile")
        if definition.diameter is None or not isfinite(definition.diameter) or definition.diameter <= 0:
            raise ValueError(f"T{identifier}: enter a finite positive cutting diameter in the tool profile")
        if definition.flute_length > definition.stickout:
            raise ValueError(f"T{identifier}: cutting length exceeds declared exposed stickout")
        flute_length = definition.flute_length
        sections, notes = assembly_envelopes(definition, flute_length) if validate_assets else ((), ())
        result[identifier] = ToolGeometry(
            definition.diameter,
            flute_length,
            definition.shank_diameter,
            definition.stickout,
            shape=shapes[shape],
            corner_radius_mm=definition.corner_radius or 0,
            taper_angle_deg=definition.taper_angle_deg if definition.taper_angle_deg is not None else 45,
            tip_diameter_mm=definition.tip_diameter or 0,
            noncutting_sections=sections,
            clearance_notes=notes,
        )
    return result


class StockPathReview(TypedDict):
    cutting_segments: int
    possible_overlap_segments: int
    possible_overlap_lines: tuple[int, ...]
    stock_minimum_mm: tuple[float, float, float]
    stock_maximum_mm: tuple[float, float, float]


def stock_path_review(
    segments: Iterable[SimulationSegment],
    tools: Mapping[str, ToolGeometry],
    bounds: AABB,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> StockPathReview | None:
    """Review +Z cutter/stock overlap, without claiming removal or registration.

    Continuous cylindrical envelopes include cutting length, so a tip outside
    stock can still engage its side. Profile shape and voxel resolution may
    produce less removal than these conservative envelopes suggest.
    """
    cutting = [segment for segment in segments if segment.cutting]
    lines = set()
    overlaps = 0
    for segment in cutting:
        if cancelled():
            return None
        sweep = SweptTool(segment.start, segment.end, tools[segment.tool_id])
        section = sweep.sections()[0]
        if sweep.intersects_section(section, bounds):
            overlaps += 1
            lines.add(segment.line)
    return {
        "cutting_segments": len(cutting),
        "possible_overlap_segments": overlaps,
        "possible_overlap_lines": tuple(sorted(lines)),
        "stock_minimum_mm": bounds.minimum.tuple,
        "stock_maximum_mm": bounds.maximum.tuple,
    }


def scene_from_geometry(
    scene: Mapping[str, Geometry | GeometrySnapshot], setup: MachineSetup, stock_bounds: AABB
) -> CollisionScene:
    obstacles = []
    for group in ("fixture", "workholding"):
        geometry = scene.get(group)
        if geometry is None or not geometry.vertices:
            continue
        points = [setup.work_point(geometry.vertices[i : i + 3]) for i in range(0, len(geometry.vertices), 10)]
        low = [min(p[axis] for p in points) for axis in range(3)]
        high = [max(p[axis] for p in points) for axis in range(3)]
        for axis in range(3):
            if high[axis] - low[axis] < 0.001:
                high[axis] = low[axis] + 0.001
        obstacles.append(CollisionObstacle(group, AABB(Vec3(*low), Vec3(*high))))
    allowance = Vec3(1000, 1000, 1000)
    return CollisionScene(
        tuple(obstacles),
        stock=stock_bounds,
        allowed_cut_region=AABB(stock_bounds.minimum - allowance, stock_bounds.maximum + allowance),
        registration_confirmed=False,
        geometry_complete=False,
    )


def stock_geometry(
    stock: StockVolume, max_faces: int = 100000, *, cancelled: Callable[[], bool] | None = None
) -> Geometry:
    """Expose complete boundary faces in program mm; discard cancelled meshes."""
    if cancelled and cancelled():
        raise InterruptedError("Rest-stock visualization cancelled")
    geometry = Geometry()
    nx, ny, nz = stock.shape
    half = stock.cell_size.scaled(0.5)
    count = 0
    color = (0.67, 0.76, 0.82, 0.65)
    visited = 0
    for z in range(nz):
        for y in range(ny):
            for x in range(nx):
                if visited % 128 == 0 and cancelled and cancelled():
                    raise InterruptedError("Rest-stock visualization cancelled")
                visited += 1
                if not stock.occupied(x, y, z):
                    continue
                center = stock.grid_center(x, y, z)
                x0, y0, z0 = (center - half).tuple
                x1, y1, z1 = (center + half).tuple
                faces = (
                    ((-1, 0, 0), ((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0))),
                    ((1, 0, 0), ((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1))),
                    ((0, -1, 0), ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1))),
                    ((0, 1, 0), ((x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0))),
                    ((0, 0, -1), ((x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0))),
                    ((0, 0, 1), ((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))),
                )
                for normal, corners in faces:
                    if stock.occupied(x + normal[0], y + normal[1], z + normal[2]):
                        continue
                    count += 1
                    if count > max_faces:
                        raise ValueError("Rest-stock display exceeds face budget; use a coarser resolution")
                    program_corners = tuple(stock.program_point(Vec3(*point)).tuple for point in corners)
                    program_normal = stock.program_direction(Vec3(*normal)).tuple
                    geometry.triangle(program_corners[:3], program_normal, color)
                    geometry.triangle(
                        (program_corners[0], program_corners[2], program_corners[3]), program_normal, color
                    )
    if cancelled and cancelled():
        raise InterruptedError("Rest-stock visualization cancelled")
    return geometry
