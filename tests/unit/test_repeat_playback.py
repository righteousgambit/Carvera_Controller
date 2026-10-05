import pytest

from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.repeat_parts import RepeatPartPlan
from carveracontroller.machine.repeat_playback import prepare_repeat_playback


def test_path_has_actual_machine_coordinates_and_rebases_without_duplicating():
    text = "G21 G90 G94 G17 G54\nT1 M6\nG0 X0 Y0 Z2\nG1 Z-1 F100\nG1 X3\nG0 Z2\nG55\nG0 X0 Y0\nG1 Z-1\nG1 X3"
    program = ProgramOperations.from_text(text)
    plan = RepeatPartPlan.grid(1, 2, (10, 0, 0), (0, 0, 0), (0, 0, -2), (4, 4, 2))
    result = prepare_repeat_playback(program, plan)
    assert result.source_hash == program.file_hash
    assert result.unresolved_lines == (3,)
    assert result.machine_rows[0][:3] == (0, 0, 2)
    assert result.machine_rows[-1][:3] == (13, 0, -1)
    assert result.rows_for_offset((10, 0, 0))[-1][:3] == [3, 0, -1]
    rapid = [row for row in result.machine_rows if row[5] == 8]
    assert rapid[0][:3] == (3, 0, 2)
    assert rapid[-1][:3] == (10, 0, 2)
    assert all(row[4] == 0 for row in rapid)
    assert all(row[6] == 1 for row in result.machine_rows)
    assert result.machine_rows[-1][7] == 100
    with pytest.raises(InterruptedError, match="cancelled"):
        prepare_repeat_playback(program, plan, cancelled=lambda: True)


def test_unknown_or_rotary_or_inverse_time_path_cannot_be_fabricated():
    plan = RepeatPartPlan.grid(1, 2, (10, 0, 0), (0, 0, 0), (0, 0, -2), (4, 4, 2))
    prefix = "G21 G90 G94 G17 G54\nT1 M6\nG0 X0 Y0 Z2\nG1 X3 F100\n"
    for suffix in ("G92 X0\nG1 X4", "G1 A20", "G93\nG1 X4 F2"):
        with pytest.raises(ValueError):
            prepare_repeat_playback(ProgramOperations.from_text(prefix + suffix), plan)
