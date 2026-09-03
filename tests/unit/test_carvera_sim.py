"""Tests for the in-memory Carvera simulator.

The simulator exists so controller features can be developed without
hardware, which is only true if the status reports it emits are accepted by
the real parser. These tests assert that round trip rather than the
simulator's own view of itself.
"""

import pytest
from carvera_sim.machine import MAX_PWM, SimulatedMachine

from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller


@pytest.fixture
def parsed():
    """Parse a simulator status line with the production status parser."""

    def _parse(machine):
        controller = Controller(CNC(), lambda _line: None, False)
        controller.parseBracketAngle(machine.status_line())
        return CNC.vars

    return _parse


def test_status_line_is_accepted_by_the_real_parser(parsed):
    machine = SimulatedMachine()
    v = parsed(machine)

    assert v["state"] == "Idle"
    assert v["wx"] == pytest.approx(0.0)
    assert v["mx"] == pytest.approx(-180.0)
    assert v["tool"] == 1


def test_spindle_temperature_and_external_output_survive_the_s_field(parsed):
    """`S:` needs nine fields before the parser reads temp and ext-out."""
    machine = SimulatedMachine()
    machine.spindle_temp = 41.5
    machine.ext_out = 1

    v = parsed(machine)

    assert v["spindletemp"] == pytest.approx(41.5, abs=0.1)
    assert v["extoutmode"] == 1


def test_pwm_field_is_parsed(parsed):
    machine = SimulatedMachine()
    machine.execute("M3 S12000")
    machine.settle(5.0)

    v = parsed(machine)

    assert 0.0 < v["spindlepwm"] <= MAX_PWM


def test_spindle_holds_commanded_rpm_while_effort_has_headroom():
    """Load raises PWM effort long before it moves RPM.

    This is the whole reason PWM is the load signal and droop is not.
    """
    machine = SimulatedMachine()
    machine.execute("M3 S14000")
    machine.settle(8.0)
    unloaded_pwm = machine.pwm

    machine.load = 0.5
    machine.settle(8.0)

    assert machine.pwm > unloaded_pwm + 0.2, "effort should rise under load"
    assert machine.rpm_droop < 0.01, "speed should not have moved yet"
    assert not machine.is_saturated


def test_rpm_collapses_once_effort_saturates():
    machine = SimulatedMachine()
    machine.execute("M3 S14000")
    machine.load = 0.9
    machine.settle(10.0)

    assert machine.is_saturated
    assert machine.pwm == pytest.approx(MAX_PWM)
    assert machine.rpm_droop > 0.2, "speed must fall once there is no headroom"


def test_spindle_stops_on_m5():
    machine = SimulatedMachine()
    machine.execute("M3 S10000")
    machine.settle(4.0)
    assert machine.current_rpm > 0

    machine.execute("M5")
    machine.settle(4.0)

    assert machine.current_rpm == pytest.approx(0.0)
    assert machine.pwm == pytest.approx(0.0)
    assert machine.state == "Idle"


def test_tool_change_updates_tool_and_offset(parsed):
    machine = SimulatedMachine()
    machine.execute("M6 T3")

    v = parsed(machine)

    assert v["tool"] == 3
    assert v["tlo"] == pytest.approx(34.5)


def test_g0_moves_relative_to_the_work_offset(parsed):
    machine = SimulatedMachine()
    machine.execute("G0 X10 Y-5 Z-2")

    v = parsed(machine)

    assert v["wx"] == pytest.approx(10.0)
    assert v["wy"] == pytest.approx(-5.0)
    assert v["wz"] == pytest.approx(-2.0)
    assert v["mx"] == pytest.approx(-170.0)


def test_m491_1_halts_when_tool_length_has_changed():
    machine = SimulatedMachine()
    machine.probe_vars["tool_break_delta"] = 1.2

    out = machine.execute("M491.1 H0.1")

    assert "ERROR" in out
    assert machine.state == "Alarm"


def test_m491_1_passes_within_tolerance():
    machine = SimulatedMachine()
    machine.probe_vars["tool_break_delta"] = 0.02

    out = machine.execute("M491.1 H0.1")

    assert "ERROR" not in out
    assert machine.state == "Idle"


def test_injected_halt_is_reported_in_the_status_line(parsed):
    machine = SimulatedMachine()
    machine.inject_halt(3, "simulated probe crash")

    v = parsed(machine)

    assert v["state"] == "Alarm"


def test_load_classification_tracks_the_simulated_spindle():
    """Walk the simulator through load and check the UI would say the right thing.

    Ties the machine-layer classifier to the physics model: effort must be
    flagged before speed moves, which is the entire argument for the gauge.
    """
    from carveracontroller.machine.spindle import SpindleLoadState, evaluate_spindle_load

    machine = SimulatedMachine()
    machine.execute("M3 S14000")

    seen = {}
    for load in (0.0, 0.3, 0.55, 0.9):
        machine.load = load
        machine.settle(8.0)
        result = evaluate_spindle_load(machine.current_rpm, machine.target_rpm, machine.pwm, machine.spindle_override)
        seen[load] = result

    assert seen[0.0].state is SpindleLoadState.NORMAL
    assert seen[0.3].state is SpindleLoadState.NORMAL

    # Working hard, but the machine is still holding commanded speed exactly.
    assert seen[0.55].state is SpindleLoadState.HIGH
    assert seen[0.55].droop < 0.01

    # Out of headroom, and now speed has actually fallen.
    assert seen[0.9].state is SpindleLoadState.SATURATED
    assert seen[0.9].droop > 0.2

    efforts = [seen[k].effort for k in (0.0, 0.3, 0.55, 0.9)]
    assert efforts == sorted(efforts), "effort must rise monotonically with load"
