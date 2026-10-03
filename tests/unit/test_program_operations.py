"""Operation evidence must not infer machine state or ATC occupancy."""

import math

import pytest

from carveracontroller.machine.program_operations import (
    ExecutionTimeline,
    ProgramOperations,
    TimelineEvent,
    summarize_operations,
)

HEADER = "G21 G90 G17 G91.1 G94 G54 G49\nM9\nT17\nM6\nS12000 M3\nG0 X0 Y0 Z0\n"


def test_fusion_operations_metadata_and_tool_selection_order():
    text = HEADER + "(T17 D=6.35 CR=0. - ZMIN=-2.)\n(2D Adaptive1)\nG1 X10 F100\n(Face2)\nM6 T42 S2\nG1 Y20 F200"
    program = ProgramOperations.from_text(text)
    assert [op.name for op in program.operations] == ["Program setup", "2D Adaptive1", "Face2"]
    assert program.operations[1].tool_ids == (17,)
    assert program.operations[2].tool_ids == (42,)
    assert program.checkpoints[-1].state.spindle_speed == 12000  # M6 S2 is collet index
    assert program.operations[1].bounds_mm == ((0, 0, 0), (10, 0, 0))
    assert program.operations[1].estimated_seconds == pytest.approx(6)
    assert program.operations[2].estimated_seconds == pytest.approx(6)
    assert summarize_operations(text.splitlines()) == program.operations


def test_makera_semicolon_operation_names_and_ids_bound_to_bytes():
    text = HEADER + "; Operation: Pocket left\nG1 X10 F100\n; Toolpath=Finish wall\nG1 X0"
    a = ProgramOperations.from_text(text)
    b = ProgramOperations.from_text(text)
    assert a.operations == b.operations
    assert a.operations[1].name == "Pocket left"
    assert a.operations[2].name == "Finish wall"
    assert a.operations[1].id != ProgramOperations.from_text(text + "\n").operations[1].id
    assert a.operations[1].end_line + 1 == a.operations[2].start_line


def test_twelve_tools_require_explicit_reload_banks_not_modulo_tool_ids():
    ids = [17, 42, 1, 19, 8, 31, 7, 33, 81, 20, 2, 95]
    text = "\n".join(f"(Operation: Cut {i})\nT{i} M6\nG1 X{i}" for i in ids)
    banks = ProgramOperations.from_text(text).plan_tool_banks()
    assert len(banks) == 2
    assert banks[0].slots == tuple(enumerate(ids[:6], 1))
    assert banks[1].slots == tuple(enumerate(ids[6:], 1))
    assert banks[1].reload_required and len(banks[1].instructions) == 3
    assert banks[0].end_line + 1 == banks[1].start_line
    # Revisit the first cutter after the second bank: an additional reload is required.
    third = ProgramOperations.from_text(text + "\nT17 M6").plan_tool_banks()
    assert len(third) == 3


def test_arc_extrema_time_and_helical_axis_bounds():
    text = HEADER + "(Operation: Helix)\nG1 X10 F600\nG3 X0 Y10 Z2 I-10 J0 F600"
    op = ProgramOperations.from_text(text).operations[-1]
    assert op.bounds_mm == ((0, 0, 0), (10, 10, 2))
    assert op.estimated_seconds == pytest.approx(1 + math.hypot(math.pi * 5, 2) / 10)


def test_full_circle_and_radius_major_arc():
    text = HEADER + "(Operation: Circle)\nG1 X10 F600\nG2 I-10 J0 F600"
    op = ProgramOperations.from_text(text).operations[-1]
    assert op.bounds_mm == ((-10, -10, 0), (10, 10, 0))
    assert op.estimated_seconds == pytest.approx(1 + 2 * math.pi)
    minor = ProgramOperations.from_text(HEADER + "(Operation: Arc)\nG2 X10 Y0 R10 F600").operations[-1]
    major = ProgramOperations.from_text(HEADER + "(Operation: Arc)\nG2 X10 Y0 R-10 F600").operations[-1]
    assert major.estimated_seconds > minor.estimated_seconds


def test_inverse_time_requires_feed_on_each_motion():
    text = HEADER + "(Operation: Inverse)\nG93 G1 X10 F2\nG1 X20 F4"
    assert ProgramOperations.from_text(text).operations[-1].estimated_seconds == 45
    assert ProgramOperations.from_text(text + "\nG1 X30").operations[-1].estimated_seconds is None


def test_unknown_arc_center_cannot_produce_false_geometry():
    text = HEADER.replace("G91.1", "") + "(Operation: Arc)\nG2 X10 Y0 I5 J0 F600"
    op = ProgramOperations.from_text(text).operations[-1]
    assert op.bounds_mm is None and op.estimated_seconds is None
    assert any("center mode" in warning for warning in op.warnings)


def test_inches_incremental_and_g53_is_nonmodal():
    text = (
        "G20 G90 G17 G94 G54\nG0 X0 Y0 Z0\n(Operation: Cut)\nG1 X1 F1\nG53 G0 Z0\nG1 X2\nG90 G0 X2 Y0 Z0\nG91 G1 X1 F1"
    )
    program = ProgramOperations.from_text(text)
    assert program.checkpoints[3].state.position_mm == (25.4, 0, 0)
    assert program.checkpoints[4].state.position_mm == (None, None, None)
    assert program.checkpoints[-1].state.position_mm == pytest.approx((76.2, 0, 0))
    assert program.checkpoints[-1].state.wcs == "G54"
    assert program.operations[-1].estimated_seconds is None


def test_macros_and_rotary_motion_remain_explicitly_unknown():
    macro = ProgramOperations.from_text(HEADER + "(Operation: Macro)\nG1 X[#1+5] F100\nG1 X20")
    op = macro.operations[-1]
    assert op.bounds_mm is None and op.estimated_seconds is None
    assert any("expressions" in warning for warning in op.warnings)
    rotary = ProgramOperations.from_text(HEADER + "(Operation: Rotary)\nG1 A90 F100").operations[-1]
    assert rotary.bounds_mm is None and rotary.estimated_seconds is None


def test_recovery_draft_requires_known_state_and_explicit_physical_evidence():
    text = HEADER + "(Operation: Cut)\nG1 X10 F100\nG1 X20"
    program = ProgramOperations.from_text(text)
    blocked = program.recovery_plan(len(program.lines))
    assert not blocked.ready and not blocked.commands
    ready = program.recovery_plan(
        len(program.lines), safe_machine_z=-5, verified_machine_position=(-200, -150, -20), clearance_verified=True
    )
    assert ready.ready
    assert "G53 G0 Z-5" in ready.commands
    assert not any(command.startswith(("M3", "M4", "M6")) for command in ready.commands)
    assert ready.state.position_mm == (10, 0, 0)
    macro = ProgramOperations.from_text(text.replace("G1 X10 F100", "G1 X[#1] F100"))
    assert not macro.recovery_plan(
        len(macro.lines), safe_machine_z=-5, verified_machine_position=(0, 0, 0), clearance_verified=True
    ).ready


def test_unhandled_modal_command_blocks_recovery():
    text = HEADER + "G41 D1\nG1 X10 F100\nG1 X20"
    program = ProgramOperations.from_text(text)
    plan = program.recovery_plan(
        len(program.lines), safe_machine_z=-5, verified_machine_position=(0, 0, 0), clearance_verified=True
    )
    assert not plan.ready
    assert any("G41" in warning for warning in plan.warnings)


def test_timeline_distinguishes_queue_and_execution_and_records_gaps():
    timeline = ExecutionTimeline(capacity=4)
    timeline.append(TimelineEvent(100, "telemetry", executed_line=1, queued_line=80))
    timeline.append(TimelineEvent(101, "telemetry", queued_line=100))
    assert timeline.executed_line == 1 and timeline.queued_line == 100
    timeline.append(TimelineEvent(105, "telemetry", executed_line=2))
    assert [event.kind for event in timeline.events] == ["telemetry", "telemetry", "gap", "telemetry"]
    with pytest.raises(ValueError):
        timeline.append(TimelineEvent(104, "telemetry"))
    with pytest.raises(ValueError):
        timeline.append(TimelineEvent(float("nan"), "telemetry"))
    with pytest.raises(ValueError):
        ProgramOperations.from_text("G1 X1").plan_tool_banks(0)


def test_dwell_p_units_require_explicit_machine_convention():
    text = HEADER + "(Operation: Dwell)\nG4 P1000"
    assert ProgramOperations.from_text(text).operations[-1].estimated_seconds is None
    assert ProgramOperations.from_text(text, dwell_p_seconds=0.001).operations[-1].estimated_seconds == 1
    assert ProgramOperations.from_text(text.replace("P1000", "S2")).operations[-1].estimated_seconds == 2


def test_wcs_changes_do_not_combine_unregistered_coordinate_frames():
    text = HEADER + "(Operation: Two fixtures)\nG1 X10 F100\nG55\nG0 X0 Y0 Z0\nG1 X10"
    op = ProgramOperations.from_text(text).operations[-1]
    assert op.bounds_mm is None
    assert any("offset mapping" in warning for warning in op.warnings)


def test_g18_and_g19_arcs_use_correct_plane_normal():
    g18 = ProgramOperations.from_text(HEADER + "(Operation: ZX)\nG18 G1 Z10 F600\nG3 X10 Z0 K-10 I0").operations[-1]
    assert g18.bounds_mm == ((0, 0, 0), (10, 0, 10))
    assert g18.estimated_seconds == pytest.approx(1 + math.pi / 2)
    g19 = ProgramOperations.from_text(HEADER + "(Operation: YZ)\nG19 G1 Y10 F600\nG3 Y0 Z10 J-10 K0").operations[-1]
    assert g19.bounds_mm == ((0, 0, 0), (0, 10, 10))


def test_recovery_rejects_downward_retract_and_macro_target():
    text = HEADER + "G1 X10 F100\nG1 X20"
    program = ProgramOperations.from_text(text)
    plan = program.recovery_plan(
        len(program.lines), safe_machine_z=-30, verified_machine_position=(0, 0, -20), clearance_verified=True
    )
    assert not plan.ready and any("descend" in w for w in plan.warnings)
    macro = ProgramOperations.from_text(text.replace("G1 X20", "G1 X[#1]"))
    plan = macro.recovery_plan(
        len(macro.lines), safe_machine_z=-5, verified_machine_position=(0, 0, -20), clearance_verified=True
    )
    assert not plan.ready and any("expressions" in w for w in plan.warnings)


def test_tool_preselection_does_not_report_unused_old_tool_in_new_operation():
    text = HEADER + "(Operation: New cutter)\nT42\nM6\nG1 X10 F100"
    assert ProgramOperations.from_text(text).operations[-1].tool_ids == (42,)


def test_unannotated_program_splits_operations_at_actual_tool_change():
    text = HEADER + "G1 X10 F100\nT42\nM6\nG1 X20\nT17 M6\nG1 X30"
    program = ProgramOperations.from_text(text)
    assert [op.name for op in program.operations] == ["Program setup", "Tool 42", "Tool 17"]
    assert [op.tool_ids for op in program.operations] == [(17,), (42,), (17,)]
    assert program.operations[0].end_line + 1 == program.operations[1].start_line


def test_multi_turn_arc_is_not_reported_as_single_turn():
    op = ProgramOperations.from_text(HEADER + "(Operation: Three turns)\nG2 I10 J0 P3 F600").operations[-1]
    assert op.estimated_seconds is None and op.bounds_mm is None
    assert any("Multi-turn" in warning for warning in op.warnings)


def test_rejected_timeline_event_does_not_insert_gap():
    timeline = ExecutionTimeline()
    timeline.append(TimelineEvent(1, "telemetry", executed_line=1))
    with pytest.raises(ValueError):
        timeline.append(TimelineEvent(10, "telemetry", executed_line=0))
    assert len(timeline.events) == 1
