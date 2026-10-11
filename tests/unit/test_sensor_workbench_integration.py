"""Sensor evidence coexists with published workbench contracts and journals."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller
from carveracontroller.machine.adaptive_monitor import AdaptiveMonitor, Sample
from carveracontroller.machine.run_recording import RecordingReplay, RunRecording
from carveracontroller.machine.sensor_run_recording import RunEvidence


@pytest.fixture
def controller(tmp_path, monkeypatch):
    monkeypatch.setenv("KIVY_HOME", str(tmp_path))
    controller = Controller(CNC(), None)
    controller.stream = Mock()
    controller._evidence_arrival_override = 1
    yield controller
    controller.stream.send.assert_not_called()
    controller.stream = None
    controller.stop_telemetry_logging(timeout=2)
    assert controller.shutdown_evidence()


def test_both_recorders_consume_the_same_packet_without_changing_format(controller):
    controller.parseBracketAngle("<Idle|MPos:1,2,3|WPos:0,0,0|S:12000,12000,100,1,35|F:0,600,100|C:0,4,0,1|P:8,40,2>")
    assert isinstance(controller.run_recording, RunRecording)
    assert isinstance(controller.run_evidence, RunEvidence)
    event = controller.run_recording.snapshot()["events"][-1]
    assert event["monotonic_at"] == controller.run_evidence.latest["arrival_monotonic_s"] == 1
    assert event["data"]["fields"]["P"] == [8, 40, 2]
    replay = RecordingReplay(controller.run_recording.export_bytes())
    assert replay.at(1)["sample"]["data"]["fields"]["MPos"] == [1, 2, 3]
    assert controller._adaptive_log.drain()["written"] == 1
    assert controller._evidence_writer.flush(2)
    assert controller.sensor_log_path != controller.adaptive_log_path
    assert controller.sensor_log_path.parent.name == "sensor-evidence"
    assert controller.adaptive_log_path.parent.name == "adaptive"
    assert '"kind":"status"' in controller.sensor_log_path.read_text()
    assert '"persistence"' in controller.adaptive_log_path.read_text()


def test_missing_units_preserves_packet_liveness_and_workbench_evidence(controller):
    controller.parseBracketAngle("<Idle|MPos:1,2,3|WPos:0,0,0>")
    assert controller.observed_pose is None
    assert controller._receive_health.snapshot(1)["valid_status_age_s"] == 0
    assert controller.run_recording.snapshot()["events"][-1]["data"]["fields"]["MPos"] == [1, 2, 3]
    assert controller.sensor_context_snapshot()["machine_position"] is None


@pytest.mark.parametrize("route", ["command", "recovery_disposal", "connection"])
def test_backend_owner_blocks_sensor_transport_routes_before_writes_or_measurement_callbacks(controller, route):
    controller.command_owner_guard = lambda: False
    controller.measurement_command_callback = Mock()
    if route == "command":
        result = controller.executeCommand("M491")
    elif route == "recovery_disposal":
        controller._recovery_disposal_nonce = 7
        result = controller._request_recovery_buffer_disposal()
    else:
        result = controller.open(1, "test-only")
    assert result is False
    controller.stream.send.assert_not_called()
    controller.measurement_command_callback.assert_not_called()


def qualified_monitor():
    monitor = AdaptiveMonitor()
    monitor.configure_recipe(
        {
            "cutter": "mill-1",
            "material": "6061",
            "operation": "roughing",
            "rpm": 12000,
            "flutes": 2,
            "programmed_feed_mm_min": 600,
            "chipload_min_mm": 0.0175,
            "chipload_max_mm": 0.02375,
        }
    )
    monitor.capture_baseline()
    initial = Sample(
        0, "Idle", 12000, 12000, 0.3, 0, 95, (0, 0, 0), {"operation": "roughing", "commanded_feed_mm_min": 600}
    )
    for index in range(27):
        monitor.observe(replace(initial, timestamp=index * 0.2))
    return monitor, initial


@pytest.mark.parametrize("case", ["missing_recipe", "wrong_operation", "wrong_feed", "below_floor"])
def test_legacy_decision_display_cannot_offer_a_recipe_rejected_proposal(case):
    monitor, initial = qualified_monitor()
    changes = {"timestamp": 5.4, "state": "Run", "feed": 600, "pwm": 0.96}
    if case == "missing_recipe":
        monitor.recipe = None
    elif case == "wrong_operation":
        changes["context"] = dict(initial.context, operation="finishing")
    elif case == "wrong_feed":
        changes["context"] = dict(initial.context, commanded_feed_mm_min=601)
    else:
        changes["override"] = 60
    result = monitor.observe(replace(initial, **changes))
    assert result["proposal_eligible"] is False
    assert result["proposal_blocker"]
    assert result["decision"]["status"] == "blocked"
    assert result["decision"]["proposal_percent"] is None
    assert result["decision"]["response"]["status"] == "unavailable"


def test_decision_floor_and_ceiling_match_recipe_instead_of_generic_limits():
    monitor, initial = qualified_monitor()
    monitor.proposed = 75
    state = monitor.observe(replace(initial, timestamp=5.4, state="Run", feed=600, pwm=0.96))
    assert state["feed_floor_percent"] == pytest.approx(70)
    assert state["feed_ceiling_percent"] == pytest.approx(95)
    assert state["decision"]["proposal_percent"] == pytest.approx(70)
    assert state["decision"]["limiting_factor"].startswith("70% recipe chip-load floor")
    monitor.proposed = 95
    state = monitor.observe(replace(initial, timestamp=5.6, state="Run", feed=600))
    assert state["decision"]["status"] == "ceiling"
    assert state["decision"]["limiting_factor"].startswith("95% recipe feed ceiling")


def test_incomplete_current_packet_immediately_withholds_previous_decision(controller):
    monitor, initial = qualified_monitor()
    controller.adaptive_monitor = monitor
    eligible = monitor.observe(replace(initial, timestamp=5.4, state="Run", feed=600))
    assert eligible["decision"]["proposal_percent"] is not None
    retained = monitor.last
    history = tuple(monitor.history)
    controller._evidence_arrival_override = 5.6
    controller._observe_adaptive({"MPos": [1, 2, 3]})
    current = monitor.snapshot(5.6)
    assert current["telemetry_quality"]["state"] == "incomplete"
    assert current["proposal_eligible"] is False
    assert current["decision"]["proposal_percent"] is None
    assert current["decision"]["response"]["status"] == "unavailable"
    assert monitor.last is retained and tuple(monitor.history) == history
