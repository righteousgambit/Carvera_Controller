from unittest.mock import Mock

import pytest

from carveracontroller.machine.capability_map import capability_rows


def rows(**changes):
    observations = {"model": "C1", "firmware": "2.1.0c", "has_atc": True, "status_at": 10, "generation": 2}
    observations.update(changes)
    return {r["key"]: r for r in capability_rows(observations, connected=True, now=10.2)}


def test_available_protocol_is_distinct_from_physical_prerequisites_and_simulation():
    result = rows()
    assert result["probe"]["state"] == "Protocol available"
    assert "calibrated probe" in result["probe"]["prerequisite"]
    assert result["tcp"]["state"] == "Simulation only"
    assert result["rigid_tapping"]["state"] == "Unsupported by adapter"
    assert "thread-milling" in result["rigid_tapping"]["alternative"]
    assert result["atc"]["generation"] == 2
    assert rows(has_atc=False)["atc"]["state"] == "Not detected"
    assert rows(has_atc=None)["atc"]["state"] == "Needs verification"


@pytest.mark.parametrize("now,connected", [(11, True), (9, True), (10.1, False)])
def test_stale_reversed_or_disconnected_identity_never_enables_protocol(now, connected):
    result = capability_rows({"model": "C1", "firmware": "2.1.0c", "status_at": 10}, connected=connected, now=now)
    assert all(r["state"] != "Protocol available" for r in result)


def test_unknown_or_missing_identity_never_uses_saved_configuration():
    assert rows(firmware="9.0.0c")["spindle"]["state"] == "Needs verification"
    assert rows(model="")["spindle"]["state"] == "Needs verification"


def test_transport_identity_capture_and_failed_reconnect_clear_prior_session():
    from carveracontroller.CNC import CNC
    from carveracontroller.Controller import CONN_WIFI, Controller

    controller = Controller(CNC(), lambda _: None)
    controller.parseLine("version = 2.1.0c")
    controller.parseLine("model = C1, 0, 4, 0")
    controller.parseBracketAngle("<Idle|MPos:0,0,0|WPos:0,0,0|C:0,4,0,1|S:0,12000,100|F:0,600,100>")
    assert controller._capability_observations["firmware"] == "2.1.0c"
    assert controller._capability_observations["has_atc"] is True
    assert controller._capability_observations["status_at"] == controller.observed_pose.timestamp
    controller.wifi_stream = Mock()
    controller.wifi_stream.open.return_value = False
    assert controller.open(CONN_WIFI, "test.invalid") is False
    assert controller._capability_observations == {"generation": 1}
