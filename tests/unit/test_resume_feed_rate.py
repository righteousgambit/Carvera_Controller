"""Tests for resume-at-line feed-rate recovery."""

import pytest

from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller


@pytest.mark.parametrize(
    ("lines", "expected"),
    (
        (["G1 X0 F100\n", "F275\n", "G0 X1\n", "G1 X2\n"], 275.0),
        (["G1 X0 F100\n", "X10Y10G1F425\n", "G28\n", "G1 X2\n"], 425.0),
        (["G1 X0 F100\n", "G1 X1 ; F900\n", "G0 X2\n", "G1 X3\n"], 100.0),
        (["G1 X0 F100\n", "G1 X1 (F900)\n", "G0 X2\n", "G1 X3\n"], 100.0),
    ),
)
def test_recovers_feed_from_standalone_and_tightly_packed_words(lines, expected):
    controller = Controller(CNC(), None)

    assert controller._find_last_feed_rate(lines, 4) == expected


def test_restores_feed_before_recovery_z_move(tmp_path):
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
        "G0 X0 Y2 Z-3\n",
        "G1 F100\n",
        "F275\n",
        "G1 X1\n",
        "G1 X2\n",
    ]
    source = tmp_path / "job.nc"
    source.write_text("".join(lines))
    controller._evidence_writes_enabled = False
    controller.set_program_source(source, lines)
    commands = controller.recovery_preview("job.nc", 10, lines=lines, clearance_machine_z_mm=-2)["commands"]
    feed_index = commands.index("buffer G1 F275.000000")
    z_index = commands.index("buffer G1 Z-3.000000")
    assert feed_index < z_index
