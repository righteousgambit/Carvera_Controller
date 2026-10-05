import pytest

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.repeat_parts import RepeatPartPlan
from carveracontroller.machine.repeat_simulation import simulate_repeat_parts
from carveracontroller.machine.simulation_preview import simulation_segments

TEXT = "G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z2\nG1 Z-1 F100\nG1 X3\nG0 Z2\nG55\nG0 X0 Y0\nG1 Z-1\nG1 X3\n"


def plan():
    return RepeatPartPlan.grid(1, 2, (10, 0, 0), (0, 0, 0), (0, 0, -2), (4, 4, 2))


def definitions():
    return {1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, shank_diameter=2, flute_length=2, stickout=3)}


def test_declared_wcs_transition_preserves_machine_pose_and_resolves_rapid_between_parts():
    offsets = {"G54": (0, 0, 0), "G55": (10, 0, 0)}
    source = ProgramOperations.from_text(TEXT)
    mapped = ProgramOperations.from_text(TEXT, work_offsets=offsets)
    assert source.unresolved_motion_lines == (3, 8, 9)
    assert mapped.unresolved_motion_lines == (3,)
    transition = next(segment for segment in mapped.motion_segments if segment.line_number == 8)
    assert transition.start_mm == (-7, 0, 2)
    assert transition.end_mm == (0, 0, 2)
    segments = simulation_segments(mapped, work_offsets=offsets)
    rapid = next(segment for segment in segments if segment.line == 8)
    assert rapid.start.tuple == (3, 0, 2)
    assert rapid.end.tuple == (10, 0, 2)
    assert not rapid.cutting
    assert mapped.checkpoints[6].state.position_mm == (-7, 0, 2)
    relative = simulation_segments(mapped, work_offsets=offsets, reference_offset=(10, 0, 0))
    assert relative[-1].end.tuple == (3, 0, -1)
    assert mapped.file_hash == source.file_hash
    assert mapped.declared_work_offsets == offsets
    # The first operation contains an unknown initial approach, so its complete
    # bounds must remain unknown even when all subsequent WCS changes resolve.
    assert mapped.operations[-1].bounds_mm is None
    bounded = ProgramOperations.from_text(
        TEXT.replace("G1 Z-1 F100", "(Operation: Array cut)\nG1 Z-1 F100"), work_offsets=offsets
    )
    assert bounded.operations[-1].bounds_mm[1][0] == 13


def test_multi_stock_simulation_applies_actual_path_and_keeps_per_part_results():
    program = ProgramOperations.from_text(TEXT)
    result = simulate_repeat_parts(program, plan(), definitions(), {}, 1)
    assert result.program_hash == program.file_hash
    assert result.unresolved_lines == (3,)
    assert set(result.geometries) == {"G54", "G55"}
    assert result.reports[0].removed_volume_mm3 > 0
    assert result.reports[0].removed_volume_mm3 == result.reports[1].removed_volume_mm3
    assert result.reports[0].remaining_volume_mm3 == result.reports[1].remaining_volume_mm3
    for part, geometry in zip(result.plan.parts, result.geometries.values()):
        assert all(
            part.bounds[0][axis] <= value <= part.bounds[1][axis]
            for i in range(0, len(geometry.vertices), 10)
            for axis, value in enumerate(geometry.vertices[i : i + 3])
        )
    # A one-frame program must not be duplicated to the second stock.
    single = ProgramOperations.from_text(TEXT.split("G55")[0])
    only_first = simulate_repeat_parts(single, plan(), definitions(), {}, 1)
    assert only_first.reports[0].removed_volume_mm3 > 0
    assert only_first.reports[1].removed_volume_mm3 == 0
    # Motion in G54 can still physically cut the G55 stock; frame labels do not filter engagement.
    across = ProgramOperations.from_text("G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y1 Z-1\nG1 X13 F100")
    crossed = simulate_repeat_parts(across, plan(), definitions(), {}, 1)
    assert all(report.removed_volume_mm3 > 0 for report in crossed.reports)


@pytest.mark.parametrize("offsets", [{"G53": (0, 0, 0)}, {"G54": (True, 0, 0)}, {"G54": (float("nan"), 0, 0)}, {}])
def test_invalid_frame_tables_rejected(offsets):
    with pytest.raises(ValueError):
        ProgramOperations.from_text(TEXT, work_offsets=offsets)


def test_missing_frames_unsupported_modal_and_cancellation_fail_before_publication():
    with pytest.raises(ValueError, match="Missing declared"):
        simulate_repeat_parts(ProgramOperations.from_text(TEXT.replace("G55", "G59")), plan(), definitions(), {}, 1)
    with pytest.raises(ValueError, match="unsupported modal"):
        simulate_repeat_parts(ProgramOperations.from_text(TEXT + "G92 X0\nG1 X2\n"), plan(), definitions(), {}, 1)
    with pytest.raises(InterruptedError, match="cancelled"):
        simulate_repeat_parts(ProgramOperations.from_text(TEXT), plan(), definitions(), {}, 1, cancelled=lambda: True)
    with pytest.raises(ValueError, match="Missing declared"):
        simulation_segments(ProgramOperations.from_text(TEXT), work_offsets={"G54": (0, 0, 0)})


def test_shared_voxel_budget_prevents_six_individual_maximum_allocations():
    large = RepeatPartPlan.grid(1, 2, (120, 0, 0), (0, 0, 0), (0, 0, 0), (110, 110, 110))
    with pytest.raises(ValueError, match="shared two-million"):
        simulate_repeat_parts(ProgramOperations.from_text(TEXT), large, definitions(), {}, 1)
