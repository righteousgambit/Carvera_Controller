"""Complete nominal loaded-program imagery, independent of collision acceptance."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from math import isfinite
from types import MappingProxyType

from carveracontroller.machine.joint_clearance import bodies_from_record
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_joint_clearance import ProgramBodyClearance, ProgramClearanceSource
from carveracontroller.machine.program_operations import _COMMENT, _WORD, ProgramOperations
from carveracontroller.machine.program_stock_evolution import capture_stock_inputs, review_stock_evolution
from carveracontroller.machine.program_surface_clearance import (
    ProgramSurfaceClearance,
    scene_rotating_envelopes,
    scene_surfaces,
)
from carveracontroller.machine.scene_joint_clearance import SceneClearanceCapture, build_scene_clearance
from carveracontroller.machine.simulation_preview import simulation_segments

QUALIFICATION = (
    "Nominal playback preparation only; collision/clearance has not been reviewed. Every retained CAD triangle, "
    "declared missing-CAD envelope, resolved motion and ordered stock input is retained. Unknown source motion, "
    "ATC travel, timing gaps and uncertified curve removal remain unknown. No collision result, safe execution, "
    "manufactured tool shape, live registration or physical machining is qualified by this preparation."
)


@dataclass(frozen=True)
class ProgramPlaybackPreparation:
    source: ProgramClearanceSource
    offsets: Mapping[str, tuple[float, float, float]]
    scene: ProgramSurfaceClearance


def prepare_program_playback(
    source: ProgramClearanceSource,
    captures: Mapping[int, SceneClearanceCapture],
    offsets: Mapping[str, Sequence[float]],
    *,
    stock_resolution_mm: float | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> ProgramPlaybackPreparation:
    """Produce display inputs without inventing collision-contact evidence."""
    from carveracontroller.machine.repeat_parts import vector

    if cancelled():
        raise InterruptedError("Nominal playback cancelled; no partial preparation")
    if not source.lines or len(source.lines) > 1_000_000 or len(source.motion) > 1_000_000:
        raise ValueError("Nominal playback requires bounded parsed source motion")
    datums = {name: vector(point) for name, point in offsets.items()}
    if any(frame in datums and datums[frame] != point for frame, point in source.declared_offsets):
        raise ValueError("Playback datums differ from parser-declared work offsets")
    detached = ProgramOperations(
        source.lines, (), source.checkpoints, source.file_hash, source.motion, source.unresolved, dialect=source.dialect
    )
    segments = simulation_segments(detached, work_offsets=datums, cancelled=cancelled)
    if not segments or len(segments) > 100_000 or any(m.rotary is not None for m in source.motion):
        raise ValueError(
            "Nominal C1 playback requires 1..100000 resolved XYZ moves; rotary mapping remains unavailable"
        )
    required = {int(s.tool_id) for s in segments if s.tool_id != "None"}
    if any(s.tool_id == "None" for s in segments) or not required <= captures.keys() or len(required) > 32:
        raise ValueError("Capture explicit profiles for every playback tool (at most 32)")
    baseline = captures[min(required)]
    for tool in required:
        current = captures[tool]
        if (
            current.profile is not baseline.profile
            or current.setup != baseline.setup
            or current.placement != baseline.placement
            or current.repeat_plan != baseline.repeat_plan
            or {g: p.geometry_sha256 for g, p in current.components.items()}
            != {g: p.geometry_sha256 for g, p in baseline.components.items()}
        ):
            raise ValueError("Playback tools must share the same captured machine, fixture and stock")
    records = {tool: build_scene_clearance(captures[tool], cancelled=cancelled) for tool in sorted(required)}
    if any(record["scene_source"]["tool_number"] != tool for tool, record in records.items()):
        raise ValueError("Playback tool identity differs from captured geometry")
    meshes = {tool: scene_surfaces(captures[tool], records[tool], cancelled=cancelled) for tool in sorted(required)}
    envelopes = {tool: scene_rotating_envelopes(captures[tool]) for tool in sorted(required)}
    # Match the source-bound enclosure parameterization used by exact reviews.
    by_line: dict[int, list[int]] = {}
    motion_by_line = {}
    for motion in source.motion:
        motion_by_line.setdefault(motion.line_number, []).append(motion)
    for index, segment in enumerate(segments):
        by_line.setdefault(segment.line, []).append(index)
    adjusted = list(segments)
    for curve in source.curve_enclosures:
        indices = by_line.get(curve.line_number, ())
        motions = motion_by_line.get(curve.line_number, ())
        if (
            not indices
            or len(curve.parameters) != len(indices) + 1
            or len(curve.points_mm) != len(indices) + 1
            or len(motions) != len(indices)
            or curve.parameters[0] != 0
            or curve.parameters[-1] != 1
            or any(not isfinite(u) or not 0 <= u <= 1 for u in curve.parameters)
            or any(a >= b for a, b in zip(curve.parameters, curve.parameters[1:]))
            or not isfinite(curve.maximum_error_bound_mm)
            or not 0 <= curve.maximum_error_bound_mm <= 1000
            or any(
                m.start_mm != curve.points_mm[k] or m.end_mm != curve.points_mm[k + 1] for k, m in enumerate(motions)
            )
        ):
            raise ValueError("Playback curve enclosure differs from complete parser motion")
        for k, i in enumerate(indices):
            adjusted[i] = replace(
                segments[i], source_start_ratio=curve.parameters[k], source_end_ratio=curve.parameters[k + 1]
            )
    segments = tuple(adjusted)
    machines = {}
    for tool, record in records.items():
        machine = machine_from_record(record)
        links = machine.tool_chain + machine.work_chain
        if (
            tuple(j.name for j in links) != ("X", "Z", "Y")
            or any(j.kind != "linear" for j in links)
            or tuple(j.axis.tuple for j in links) != ((1, 0, 0), (0, 0, 1), (0, -1, 0))
            or len(machine.tool_chain) != 2
        ):
            raise ValueError("Nominal playback requires the captured C1 XYZ spindle/table mapping")
        bodies_from_record(record, machine)
        machines[tool] = machine
    for index, segment in enumerate(segments):
        if index % 128 == 0 and cancelled():
            raise InterruptedError("Nominal playback cancelled; no partial preparation")
        machine = machines[int(segment.tool_id)]
        if any(
            machine.forward(dict(zip(("X", "Y", "Z"), point.tuple))).limit_violations
            for point in (segment.start, segment.end)
        ):
            raise ValueError(f"Nominal playback source line {segment.line} exceeds declared C1 travel")
    changes = []
    gaps = set(source.unresolved)
    prior_errors: tuple[str, ...] = ()
    segment_lines = set(by_line)
    curved_lines = {c.line_number for c in source.curve_enclosures}
    for cp in source.checkpoints:
        if cp.state.recovery_errors != prior_errors or (
            cp.line_number in segment_lines and cp.state.cutter_compensation not in (None, "G40")
        ):
            gaps.add(cp.line_number)
        if cp.line_number in segment_lines and cp.state.motion in (2, 3, 5, 5.1):
            curved_lines.add(cp.line_number)
        prior_errors = cp.state.recovery_errors
    curved_lines.update(block.line_number for block in source.spline_blocks if block.line_number in segment_lines)
    for line, text in enumerate(source.lines, 1):
        if line % 128 == 0 and cancelled():
            raise InterruptedError("Nominal playback cancelled; no partial preparation")
        code = _COMMENT.sub(" ", text).split(";", 1)[0]
        if any(m[1].upper() == "M" and float(m[2]) == 6 for m in _WORD.finditer(code)):
            changes.append(line)
    curves = tuple((c.line_number, c.command, c.maximum_error_bound_mm) for c in source.curve_enclosures)
    body = ProgramBodyClearance(
        source.file_hash,
        1,
        len(source.lines),
        segments,
        MappingProxyType(records),
        tuple((tool, str(record["scene_source"]["scene_digest"])) for tool, record in records.items()),
        (),
        tuple(sorted(gaps)),
        tuple(sorted(curved_lines)),
        tuple(changes),
        0,
        0,
        0.05,
        "nominal_playback_clearance_not_reviewed",
        curve_enclosures=curves,
        curve_coverage=True,
        qualification=QUALIFICATION,
    )
    history = None
    if stock_resolution_mm is not None:
        inputs = capture_stock_inputs(
            {tool: captures[tool] for tool in required}, stock_resolution_mm, cancelled=cancelled
        )
        history = review_stock_evolution(body, inputs, envelopes, cancelled=cancelled)
    scene = ProgramSurfaceClearance(
        body,
        MappingProxyType(meshes),
        (),
        (),
        0,
        0,
        0,
        sum(len(m.triangles) for tool_meshes in meshes.values() for m in tool_meshes.values()),
        rotating_envelopes=MappingProxyType(envelopes),
        stock_evolution=history,
        qualification=QUALIFICATION,
    )
    if cancelled():
        raise InterruptedError("Nominal playback cancelled; no partial preparation")
    return ProgramPlaybackPreparation(source, MappingProxyType(datums), scene)
