import time
from unittest.mock import Mock

import pytest

from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller
from carveracontroller.machine.homing_evidence import HomingEvidence


@pytest.mark.parametrize("response", ["X:1 Y:1 Z:1", "X:1 Y:1 Z:1 A:0", "X:1 Y:1 Z:1 A:1"])
def test_cartesian_homing_ignores_optional_rotary_axis(response):
    evidence = HomingEvidence()
    evidence.request(1, 10)
    assert evidence.observe(response, 1, 10.1)
    assert evidence.homed(1, 10.1) is True


def test_pending_query_keeps_original_deadline():
    evidence = HomingEvidence()
    assert evidence.request(1, 10)
    assert not evidence.request(1, 12)
    assert not evidence.observe("X:1 Y:1 Z:1", 1, 13.1)
    assert evidence.homed(1) is None


def test_homing_requires_current_requested_receipt_and_rejects_late_or_retired_reply():
    evidence = HomingEvidence()
    assert evidence.homed(1) is None
    assert not evidence.observe("X:1 Y:1 Z:1 A:0", 1, 10)
    evidence.request(1, 10)
    assert not evidence.observe("X:1 Y:1 Z:1 A:0", 2, 10.1)
    assert evidence.observe("X:1 Y:0 Z:1 A:0", 1, 10.2)
    assert evidence.homed(1) is False
    assert evidence.homed(1, 14) is None
    assert evidence.homed(2) is None
    evidence.request(2, 11)
    assert evidence.homed(2) is None
    assert not evidence.observe("X:1 Y:1 Z:1 A:0", 2, 15)
    assert evidence.homed(2) is None


@pytest.mark.parametrize("response", ["X:1 Y:1 Z:2", "X:1 Y:1", "X:1 Y:1 Z:1 junk", "X:1 Y:1 Z:1 A:0 B:1"])
def test_malformed_homing_does_not_establish_position(response):
    evidence = HomingEvidence()
    evidence.request(1, 10)
    assert not evidence.observe(response, 1, 10.1)
    assert evidence.homed(1) is None


def test_fresh_boot_zero_packet_cannot_enable_jogging_until_xyz_homed_receipt():
    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    controller.executeCommand = Mock()
    controller.parseLine("<Idle|MPos:0,0,0|WPos:0,0,0|C:1,5,0,1|T:1,50.48>")
    assert controller.observed_pose is not None
    assert controller.cartesian_homed is None
    controller.jog("X1")
    controller.executeCommand.assert_not_called()
    controller.homing_evidence.request(controller._connection_generation, time.monotonic())
    controller.parseLine("X:0 Y:0 Z:0 A:0")
    assert controller.cartesian_homed is False
    controller.jog("X1")
    controller.executeCommand.assert_not_called()
    controller.homing_evidence.request(controller._connection_generation, time.monotonic())
    controller.parseLine("X:1 Y:1 Z:1 A:0")
    assert controller.cartesian_homed is True
    controller.jog("X1")
    controller.executeCommand.assert_called_once()
    controller._connection_generation += 1
    assert controller.cartesian_homed is None


@pytest.mark.parametrize(
    "command", ["reset\n", "$H", "M112", "M999", "G28.3", "G28.2", "G28.5X0", "G28X0", "G90G28.5X0"]
)
def test_reset_and_homing_commands_revoke_old_homing_receipt(command):
    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    controller.parseLine("<Idle|MPos:0,0,0|WPos:0,0,0|C:1,5,0,1|T:1,50.48>")
    now = time.monotonic()
    controller.homing_evidence.request(controller._connection_generation, now)
    controller.homing_evidence.observe("X:1 Y:1 Z:1", controller._connection_generation, now)
    assert controller.cartesian_homed is True
    controller.executeCommand(command)
    assert controller.cartesian_homed is None


def test_current_run_and_pause_retain_same_boot_homing_but_stale_or_alarm_withdraws_it(monkeypatch):
    from carveracontroller import Controller as module

    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    clock = [10.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    controller.homing_evidence.request(controller._connection_generation, 10)
    controller.parseLine("X:1 Y:1 Z:1 A:0")
    for state in ("Run", "Pause"):
        clock[0] += 10
        controller.parseLine(f"<{state}|MPos:1,2,3|WPos:1,2,3|C:1,5,0,1|T:1,50.48>")
        assert controller.cartesian_homed is True
    clock[0] += 1
    assert controller.cartesian_homed is None
    controller.parseLine("<Alarm|MPos:1,2,3|WPos:1,2,3|C:1,5,0,1|T:1,50.48>")
    assert controller.cartesian_homed is None


@pytest.mark.parametrize(
    "before,after", [("1,1,1,1,100,0,11,2,1", "1,2,1,2,200,0,11,2,1"), ("1,0,0,1,100,0,11,2,1", "1,0,0,2,50,0,11,2,1")]
)
def test_sensor_boot_change_or_clock_reset_revokes_homing_with_fresh_pose(before, after):
    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()

    def packet(source):
        return f"<Idle|MPos:1,2,3|WPos:1,2,3|C:1,5,0,1|T:1,50.48|SE:{source}>"

    controller.parseLine(packet(before))
    controller.homing_evidence.request(controller._connection_generation, time.monotonic())
    controller.parseLine("X:1 Y:1 Z:1 A:0")
    assert controller.cartesian_homed is True
    controller.parseLine(packet(after))
    assert controller.observed_pose.fresh(time.monotonic())
    assert controller.cartesian_homed is None
