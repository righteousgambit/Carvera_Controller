"""Tests for resume-at-line work coordinate system recovery."""

from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller


def test_g53_does_not_replace_active_work_coordinate_system(tmp_path):
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
        "M3 S12000\n",
        "M9\n",
        "G0 X0 Y0 Z-3\n",
        "G53 G0 Z-2\n",
        "G1 X10 Y0 Z-3 F100\n",
        "G1 X20\n",
    ]
    source = tmp_path / "job.nc"
    source.write_text("".join(lines))
    controller._evidence_writes_enabled = False
    controller.set_program_source(source, lines)
    commands = controller.recovery_preview("job.nc", 9, lines=lines, clearance_machine_z_mm=-2)["commands"]
    assert "buffer G55" in commands
    assert "buffer G53" not in commands
    assert "buffer G53 G0 Z-2.000000" in commands
