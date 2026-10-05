"""Resolved-program simulation inputs and bounded rest-stock display geometry."""

from carveracontroller.addons.machine_simulation.model import Geometry
from carveracontroller.addons.manufacturing_simulation import (
    AABB,
    CollisionObstacle,
    CollisionScene,
    SimulationSegment,
    SweptTool,
    ToolGeometry,
    Vec3,
)
from carveracontroller.machine.assembly_envelopes import assembly_envelopes


def simulation_segments(program, start_line=None, end_line=None):
    selected = [
        segment
        for segment in program.motion_segments
        if (start_line is None or segment.line_number >= start_line)
        and (end_line is None or segment.line_number <= end_line)
    ]
    if len({segment.wcs for segment in selected}) > 1:
        raise ValueError("Multiple work offsets require registered instance transforms")
    if not selected:
        raise ValueError("No resolved motion segments in this selection")
    from math import dist

    totals = {}
    for segment in program.motion_segments:
        totals[segment.line_number] = totals.get(segment.line_number, 0) + dist(segment.start_mm, segment.end_mm)
    accumulated, result = {}, []
    for segment in selected:
        number = segment.line_number
        length, before = dist(segment.start_mm, segment.end_mm), accumulated.get(number, 0)
        total = totals[number]
        result.append(
            SimulationSegment(
                Vec3(*segment.start_mm),
                Vec3(*segment.end_mm),
                str(segment.tool_id),
                segment.cutting,
                line=number,
                source_start_ratio=before / total if total else 0,
                source_end_ratio=(before + length) / total if total else 1,
            )
        )
        accumulated[number] = before + length
    return tuple(result)


def simulation_tool_issues(definitions, required_ids):
    """Check declared cutting dimensions without disk I/O or installed-tool inference."""
    issues = []
    for identifier in sorted(required_ids, key=str):
        try:
            simulation_tools(definitions, {identifier}, validate_assets=False)
        except (ValueError, TypeError) as exc:
            issues.append((str(identifier), str(exc)))
    return tuple(issues)


def simulation_tools(definitions, required_ids, *, validate_assets=True):
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
        flute_length = min(definition.flute_length, definition.stickout)
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


def stock_path_review(segments, tools, bounds, *, cancelled=lambda: False):
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


def scene_from_geometry(scene, setup, stock_bounds):
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


def stock_geometry(stock, max_faces=100000):
    """Expose only boundary faces, omitting interior cell walls. Program mm."""
    geometry = Geometry()
    nx, ny, nz = stock.shape
    half = stock.cell_size.scaled(0.5)
    count = 0
    color = (0.67, 0.76, 0.82, 0.65)
    for z in range(nz):
        for y in range(ny):
            for x in range(nx):
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
                    corners = tuple(stock.program_point(Vec3(*point)).tuple for point in corners)
                    normal = stock.program_direction(Vec3(*normal)).tuple
                    geometry.triangle(corners[:3], normal, color)
                    geometry.triangle((corners[0], corners[2], corners[3]), normal, color)
    return geometry
