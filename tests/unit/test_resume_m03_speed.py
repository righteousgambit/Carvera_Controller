"""Tests for resume-at-line spindle-speed recovery."""

import pytest

from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller


@pytest.mark.parametrize(
    ("lines", "start_line", "expected"),
    (
        (["M03 S12000\n", "G1 X1\n"], 2, 12000.0),
        (["S8000M03\n", "G1 X1\n"], 2, 8000.0),
        (["M03 S6000\n", "M03\n", "G1 X1\n"], 3, 6000.0),
        (["M3 S7000\n", "M030 S9999\n", "G1 X1\n"], 3, 7000.0),
        (["M03 S5000\n", "G1 X1 (M03 S9999)\n", "G1 X2\n"], 3, 5000.0),
    ),
)
def test_recovers_speed_from_zero_padded_m03(lines, start_line, expected):
    controller = Controller(CNC(), None)

    assert controller._find_m3_spindle_speed(lines, start_line) == expected


def test_resume_preview_includes_m03_speed(tmp_path):
    controller = Controller(CNC(), None)
    controller._recovery_context = lambda: {
        "work_position": [0, 0, -10],
        "machine_position": [0, 0, -10],
        "wcs": 1,
        "tool": 2,
        "modes": [0, 4, 0, 1],
    }
    lines = [
        "G21 G90 G17 G94\n",
        "G55\n",
        "T2 M6\n",
        "M03 S12000\n",
        "M9\n",
        "G0 X0 Y0 Z-3\n",
        "G1 X1 F100\n",
        "G1 X2\n",
    ]
    source = tmp_path / "job.nc"
    source.write_text("".join(lines))
    controller._evidence_writes_enabled = False
    controller.set_program_source(source, lines)
    commands = controller.recovery_preview("job.nc", 8, lines=lines, clearance_machine_z_mm=-2)["commands"]
    assert "buffer M3 S12000.000000" in commands
    assert "buffer M3" not in commands
