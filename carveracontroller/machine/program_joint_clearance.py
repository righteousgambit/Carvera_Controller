"""Source-linked C1 body review of every resolved program polyline segment.

This is a declared-geometry review, never executable-program qualification.
Unresolved blocks, curve interiors and automatic tool-change travel remain gaps.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from carveracontroller.addons.manufacturing_simulation import SimulationSegment
from carveracontroller.machine.joint_clearance import JointContact, bodies_from_record, review_joint_clearance
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_operations import (
    Checkpoint,
    MotionSegment,
    ProgramOperations,
    ProgramParseSettings,
    SplineBlock,
)
from carveracontroller.machine.scene_joint_clearance import SceneClearanceCapture, build_scene_clearance
from carveracontroller.machine.simulation_preview import simulation_segments


@dataclass(frozen=True)
class ProgramClearanceSource:
    lines: tuple[str, ...]
    motion: tuple[MotionSegment, ...]
    checkpoints: tuple[Checkpoint, ...]
    unresolved: tuple[int, ...]
    file_hash: str
    dialect: str
    declared_offsets: tuple[tuple[str, tuple[float, float, float]], ...]
    text: str | None = None
    parse_settings: ProgramParseSettings | None = None
    spline_blocks: tuple[SplineBlock, ...] = ()

    @classmethod
    def capture(cls, program: ProgramOperations) -> ProgramClearanceSource:
        # Parser-owned tuples and their frozen rows are safe to retain without
        # scanning a large program on the UI thread. No mutable parser object.
        return cls(
            program.lines,
            program.motion_segments,
            program.checkpoints,
            program.unresolved_motion_lines,
            program.file_hash,
            program.dialect,
            tuple(sorted((program.declared_work_offsets or {}).items())),
            program.source_text,
            program.parse_settings,
            program.spline_blocks,
        )


@dataclass(frozen=True)
class ProgramBodyContact:
    segment_index: int
    line: int
    tool: int
    source_lower_ratio: float
    source_upper_ratio: float
    contact: JointContact


@dataclass(frozen=True)
class ProgramBodyClearance:
    program_hash: str
    start_line: int
    end_line: int
    segments: tuple[SimulationSegment, ...]
    records: Mapping[int, dict[str, object]]
    scene_digests: tuple[tuple[int, str], ...]
    contacts: tuple[ProgramBodyContact, ...]
    uncovered_lines: tuple[int, ...]
    curved_lines: tuple[int, ...]
    tool_change_lines: tuple[int, ...]
    tested_pairs: int
    intervals: int
    tolerance_mm: float
    status: str
    qualification: str = (
        "Every resolved XYZ polyline segment in the selected source range; "
        "curve interiors, unresolved blocks and automatic tool-change travel are not covered. "
        "Conservative initial-stock boxes include intended cutting contact and unremoved material. "
        "Nominal CAD registration, missing geometry, backend execution and physical clearance remain unqualified."
    )


def review_program_clearance(
    source: ProgramClearanceSource,
    captures: Mapping[int, SceneClearanceCapture],
    work_offsets: Mapping[str, Sequence[float]],
    *,
    start_line: int = 1,
    end_line: int | None = None,
    tolerance_mm: float = 0.05,
    max_intervals: int = 2_000_000,
    max_segments: int = 100_000,
    max_contacts: int = 10_000,
    cancelled: Callable[[], bool] = lambda: False,
) -> ProgramBodyClearance:
    if cancelled():
        raise InterruptedError("Program machine clearance cancelled")
    # Build only required tools; every capture was detached on the UI thread.
    end = len(source.lines) if end_line is None else end_line
    required = set()
    for index, motion in enumerate(source.motion):
        if index % 128 == 0 and cancelled():
            raise InterruptedError("Program machine clearance cancelled")
        if start_line <= motion.line_number <= end:
            if type(motion.tool_id) is not int:
                raise ValueError("Resolved motion has no explicit tool profile")
            required.add(motion.tool_id)
    if not required or not required <= captures.keys() or len(required) > 32:
        raise ValueError("Capture explicit geometry for every program tool (at most 32)")
    baseline = captures[min(required)]
    for tool in required:
        current = captures[tool]
        if (
            current.setup != baseline.setup
            or current.placement != baseline.placement
            or current.repeat_plan != baseline.repeat_plan
            or {g: p.geometry_sha256 for g, p in current.components.items()}
            != {g: p.geometry_sha256 for g, p in baseline.components.items()}
        ):
            raise ValueError("All program tools must share one captured machine, workholding and stock setup")
    records = {tool: build_scene_clearance(captures[tool], cancelled=cancelled) for tool in sorted(required)}
    return review_program_body_records(
        source,
        records,
        work_offsets,
        start_line=start_line,
        end_line=end_line,
        tolerance_mm=tolerance_mm,
        max_intervals=max_intervals,
        max_segments=max_segments,
        max_contacts=max_contacts,
        cancelled=cancelled,
    )


def review_program_body_records(
    source: ProgramClearanceSource,
    declarations: Mapping[int, dict[str, object]],
    work_offsets: Mapping[str, Sequence[float]],
    *,
    start_line: int = 1,
    end_line: int | None = None,
    tolerance_mm: float = 0.05,
    max_intervals: int = 2_000_000,
    max_segments: int = 100_000,
    max_contacts: int = 10_000,
    cancelled: Callable[[], bool] = lambda: False,
) -> ProgramBodyClearance:
    """Recompute declared body records without opening CAD assets or hardware.

    Geometry/source references describe the retained declaration; they do not
    authenticate a manufacturer's original CAD or prove current registration.
    """
    from types import MappingProxyType

    end = len(source.lines) if end_line is None else end_line
    if type(start_line) is not int or type(end) is not int or not 1 <= start_line <= end <= len(source.lines):
        raise ValueError("Choose an inclusive source range inside the loaded program")
    if (
        type(max_intervals) is not int
        or not 1 <= max_intervals <= 2_000_000
        or type(max_segments) is not int
        or not 1 <= max_segments <= 100_000
        or type(max_contacts) is not int
        or not 1 <= max_contacts <= 10_000
    ):
        raise ValueError("Program clearance budgets exceed the bounded review contract")

    def check() -> None:
        if cancelled():
            raise InterruptedError("Program machine clearance cancelled; no partial report published")

    check()
    for frame, offset in source.declared_offsets:
        if frame in work_offsets and tuple(work_offsets[frame]) != offset:
            raise ValueError(
                "Program geometry used different declared WCS offsets; inspect it with current datums again"
            )
    if len(source.motion) > 1_000_000:
        raise ValueError("Program has more than one million parsed segments; select a smaller source file")
    detached = ProgramOperations(
        source.lines, (), source.checkpoints, source.file_hash, source.motion, source.unresolved, dialect=source.dialect
    )
    segments = simulation_segments(detached, start_line, end, work_offsets=work_offsets, cancelled=cancelled)
    if len(segments) > max_segments:
        raise ValueError("Selected program exceeds the segment budget; no segments were decimated")
    required = {int(segment.tool_id) for segment in segments if segment.tool_id != "None"}
    if any(segment.tool_id == "None" for segment in segments):
        raise ValueError("Resolved motion has no explicit tool profile")
    if not required <= declarations.keys() or len(required) > 32:
        raise ValueError("Declare geometry for every program tool (at most 32)")
    records = {}
    scene_digests = []
    machines = {}
    body_sets = {}
    for tool in sorted(required):
        check()
        record = declarations[tool]
        machine = machine_from_record(record)
        origin = record.get("scene_source")
        if not isinstance(origin, dict) or type(origin.get("tool_number")) is not int or origin["tool_number"] != tool:
            raise ValueError("Program tool identity does not match its declared scene source")
        links = machine.tool_chain + machine.work_chain
        if (
            tuple(j.name for j in links) != ("X", "Z", "Y")
            or any(j.kind != "linear" for j in links)
            or tuple(j.axis.tuple for j in links) != ((1, 0, 0), (0, 0, 1), (0, -1, 0))
            or len(machine.tool_chain) != 2
        ):
            raise ValueError("Declared C1 program review needs its X/Z spindle and negative-Y table mapping")
        scene_digests.append((tool, str(origin["scene_digest"])))
        bodies, excluded = bodies_from_record(record, machine)
        records[tool], machines[tool], body_sets[tool] = record, machine, (bodies, excluded)
    # Validate ALL endpoints before checking any pair. Never silently skip a
    # rotary or out-of-travel segment and then report the remainder as clear.
    selected_motion = (m for m in source.motion if start_line <= m.line_number <= end)
    for index, (motion, segment) in enumerate(zip(selected_motion, segments)):
        if index % 128 == 0:
            check()
        if motion.rotary is not None:
            raise ValueError(f"Line {motion.line_number}: C1 XYZ review cannot map rotary motion")
        machine = machines[int(segment.tool_id)]
        for point in (segment.start, segment.end):
            if machine.forward(dict(zip(("X", "Y", "Z"), point.tuple))).limit_violations:
                raise ValueError(f"Line {segment.line}: resolved motion exceeds nominal C1 travel")
    contacts = []
    tested, intervals = 0, 0
    for index, segment in enumerate(segments):
        check()
        tool = int(segment.tool_id)
        remaining = max_intervals - intervals
        if remaining <= 0:
            raise ValueError("Program machine clearance exhausted its shared interval budget; no partial report")
        bodies, excluded = body_sets[tool]
        result = review_joint_clearance(
            machines[tool],
            [dict(zip(("X", "Y", "Z"), point.tuple)) for point in (segment.start, segment.end)],
            bodies,
            excluded,
            tolerance_mm=tolerance_mm,
            max_intervals=min(50_000, remaining),
            cancelled=cancelled,
        )
        tested += result.tested_pairs
        intervals += result.intervals
        for contact in result.contacts:
            if len(contacts) >= max_contacts:
                raise ValueError("Program machine clearance exceeds contact budget; narrow the source range")
            span = segment.source_end_ratio - segment.source_start_ratio
            contacts.append(
                ProgramBodyContact(
                    index,
                    segment.line,
                    tool,
                    segment.source_start_ratio + span * contact.lower_fraction,
                    segment.source_start_ratio + span * contact.upper_fraction,
                    contact,
                )
            )
    check()
    uncovered = tuple(n for n in source.unresolved if start_line <= n <= end)
    segment_lines = {s.line for s in segments}
    curved = tuple(
        sorted(
            {
                cp.line_number
                for cp in source.checkpoints
                if start_line <= cp.line_number <= end
                and cp.state.motion in (2, 3, 5, 5.1)
                and cp.line_number in segment_lines
            }
            | {block.line_number for block in source.spline_blocks if block.line_number in segment_lines}
        )
    )
    # Unsupported modal/backend commands and compensation are not represented
    # by the nominal tool-tip polylines, even when endpoints can be parsed.
    unsupported = []
    prior_errors: tuple[str, ...] = ()
    for cp in source.checkpoints:
        if start_line <= cp.line_number <= end and (
            cp.state.recovery_errors != prior_errors
            or (cp.line_number in segment_lines and cp.state.cutter_compensation not in (None, "G40"))
        ):
            unsupported.append(cp.line_number)
        prior_errors = cp.state.recovery_errors
    uncovered = tuple(sorted(set(uncovered) | set(unsupported)))
    changes = []
    previous = None
    for cp in source.checkpoints:
        code = re.sub(r"\([^()]*\)", " ", source.lines[cp.line_number - 1]).split(";", 1)[0]
        tool_change = any(float(word) == 6 for word in re.findall(r"[Mm]\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", code))
        if (tool_change or cp.state.tool != previous) and start_line <= cp.line_number <= end:
            changes.append(cp.line_number)
        previous = cp.state.tool
    # A polyline-only clear result is always described by that limited scope.
    status = (
        "potential_contact"
        if contacts
        else ("incomplete_coverage" if uncovered or curved or changes else "clear_resolved_polylines")
    )
    return ProgramBodyClearance(
        source.file_hash,
        start_line,
        end,
        segments,
        MappingProxyType(records),
        tuple(scene_digests),
        tuple(contacts),
        uncovered,
        curved,
        tuple(changes),
        tested,
        intervals,
        tolerance_mm,
        status,
    )
