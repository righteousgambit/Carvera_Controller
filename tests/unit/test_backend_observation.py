from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from carveracontroller.headless.desktop_observation import describe_backend
from carveracontroller.headless.telemetry import parse_diagnostics, parse_status


def observed_state():
    return {
        "ready": True,
        "running": True,
        "last_machine_snapshot_age_s": 0.5,
        "last_machine_snapshot": {
            "connected": True,
            "connection_id": "connection-1",
            "unknown_outcome": False,
            "transfer_active": False,
            "status_age_ms": 100,
            "diagnostics_age_ms": 1200,
            "status": parse_status(
                "<Idle|MPos:1,2,3,45,90|WPos:4,5,6,45,90|C:0,4,0,1|S:11950,12000,100|F:600,0,80|T:2>"
            ),
            "diagnostics": parse_diagnostics("{S:1|P:0,1|E:0,0,0,0,0,1|I:0}"),
        },
    }


def test_detached_backend_observation_retains_actual_rotary_spindle_and_input_meanings():
    state = observed_state()
    original = deepcopy(state)
    view = describe_backend(state)
    assert view.connected is True and view.connection_id == "connection-1"
    assert view.unknown_outcome is False and view.transfer_active is False
    assert "reported" in view.summary and "connected" in view.summary
    assert "X 1 mm / Y 2 mm / Z 3 mm" in view.telemetry
    assert "A 45° / B 90°" in view.telemetry
    assert "actual 11950 RPM / target 12000 RPM" in view.telemetry
    assert "Feed · 600 mm/min / override 80%" in view.telemetry
    assert "Reported tool: 2" in view.telemetry
    assert "receipt age 0.6s" in view.telemetry and "receipt age 1.7s" in view.telemetry
    assert "Cover input: reported 1" in view.telemetry and "Stop input: reported 0" in view.telemetry
    assert "Probe input: reported 0" in view.telemetry and "Setter input: reported 1" in view.telemetry
    assert state == original
    with pytest.raises(FrozenInstanceError):
        view.connected = False


def test_snapshot_age_makes_child_reports_stale_without_resetting_receipt_time():
    state = observed_state()
    state["last_machine_snapshot_age_s"] = 3
    view = describe_backend(state)
    assert "Position / spindle: stale · host receipt age 3.1s" in view.telemetry
    assert "Machine inputs: stale · host receipt age 4.2s" in view.telemetry


@pytest.mark.parametrize(
    "key,value", [("ready", False), ("running", False), ("connected", False), ("connection_id", None)]
)
def test_disconnected_retired_or_identityless_reports_are_retained_not_current(key, value):
    state = observed_state()
    (state if key in ("ready", "running") else state["last_machine_snapshot"])[key] = value
    view = describe_backend(state)
    assert "retained report · current receipt unavailable" in view.telemetry
    assert "recent" not in view.telemetry
    if key in ("ready", "running"):
        assert "Backend unavailable" in view.telemetry


@pytest.mark.parametrize("value", [None, -1, True, "0", float("nan"), float("inf"), 10**400])
@pytest.mark.parametrize("field", ["last_machine_snapshot_age_s", "status_age_ms"])
def test_missing_or_invalid_clock_evidence_never_becomes_a_recent_report(field, value):
    state = observed_state()
    (state if field == "last_machine_snapshot_age_s" else state["last_machine_snapshot"])[field] = value
    assert "Position / spindle: receipt age unknown" in describe_backend(state).telemetry


def test_partial_packets_do_not_borrow_prior_spindle_coordinates_or_diagnostics():
    state = observed_state()
    first = describe_backend(state)
    assert "11950" in first.telemetry
    state["last_machine_snapshot"]["status"] = parse_status("<Hold|MPos:7,8,9|C:0,4,0,1>")
    state["last_machine_snapshot"]["diagnostics"] = parse_diagnostics("{P:1}")
    second = describe_backend(state)
    assert "Reported state: Hold" in second.telemetry and "X 7 mm / Y 8 mm / Z 9 mm" in second.telemetry
    assert "actual unknown / target unknown" in second.telemetry
    assert "Work · X unknown / Y unknown / Z unknown" in second.telemetry
    assert "Spindle enabled: unknown" in second.telemetry and "Probe input: reported 1" in second.telemetry
    assert "Cover input: unknown" in second.telemetry
    assert "11950" not in second.telemetry


def test_unknown_units_and_flags_remain_unknown_without_execution_readiness():
    state = observed_state()
    state["last_machine_snapshot"]["status"] = parse_status("<Idle|MPos:1,2,3>")
    for field in ("connected", "unknown_outcome", "transfer_active"):
        del state["last_machine_snapshot"][field]
    view = describe_backend(state)
    assert view.connected is view.unknown_outcome is view.transfer_active is None
    assert "Reported connection: unknown" in view.summary
    assert "Unresolved command outcome: unknown" in view.summary
    assert "Transfer: unknown" in view.summary
    assert "Machine · X unknown / Y unknown / Z unknown" in view.telemetry
    assert "current receipt unavailable" in view.telemetry
    absent = describe_backend({})
    assert absent.connected is absent.unknown_outcome is absent.transfer_active is None
    assert "No machine snapshot" in absent.summary


def test_inch_linear_reports_stay_converted_mm_and_rotary_reports_remain_degrees():
    state = observed_state()
    state["last_machine_snapshot"]["status"] = parse_status("<Idle|MPos:1,2,3,45|C:0,4,1,1|F:10>")
    view = describe_backend(state)
    assert "X 25.4 mm / Y 50.8 mm / Z 76.2 mm" in view.telemetry
    assert "A 45° / B unknown" in view.telemetry
    assert "Feed · 254 mm/min" in view.telemetry
