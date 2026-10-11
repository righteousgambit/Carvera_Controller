"""Tooling source identity, explicit disconnects and firmware-unit boundaries."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_tool_observation import observe_tool
from carveracontroller.machine.backend_live_report import BackendLiveReport
from carveracontroller.machine.desktop_control_owner import ControlBinding, DesktopControlOwner
from carveracontroller.machine.observed_pose import ObservedPose


class ForbiddenGui:
    def __getattribute__(self, name):
        raise AssertionError(f"Selected backend accessed GUI field {name}")


def backend_workspace():
    owner = DesktopControlOwner()
    owner.binding = ControlBinding("session", "connection")
    # Even an upstream pose containing a numeric TLO must not qualify raw
    # firmware offset units for a backend millimetre comparison.
    pose = ObservedPose(1000, "Idle", (0, 0, 0), (0, 0, 0), 1, 28)
    report = BackendLiveReport({"tool": 1, "tool_offset_reported": 28}, pose, 0.1, "session", "connection", "")
    client = SimpleNamespace(session_id="session", host="127.0.0.1", port=2222, submit=Mock())
    ws = SimpleNamespace(
        control_owner=owner,
        backend_report=lambda: report,
        backend_panel=SimpleNamespace(client=client, closed=False, stopping=False),
        machine=SimpleNamespace(controller=ForbiddenGui()),
    )
    return ws, report


def test_backend_endpoint_and_offset_do_not_read_gui_or_infer_calibration_mm():
    ws, report = backend_workspace()
    observation = observe_tool(ws, 1000.1)
    assert observation.current and observation.connection_current is True
    assert observation.endpoint == "127.0.0.1:2222"
    assert observation.tool == 1 and observation.raw_offset == 28
    assert observation.pose.tool_length_mm is None
    row = {"controller_tool": 1, "controller_applicable": [{"report": {"applied": 28}}]}
    status = observation.compare_offset(row, 1000.1)
    assert status["state"] == "unknown" and status["reported_mm"] is None
    assert "raw offset 28" in status["detail"] and "no mm comparison" in status["detail"]
    assert report.pose.tool_length_mm == 28
    ws.backend_panel.client.submit.assert_not_called()


@pytest.mark.parametrize(
    "retire", ["missing", "stale", "connection", "client", "closed", "stopping", "during_read", "owner"]
)
def test_unavailable_backend_cannot_substitute_a_gui_report(retire):
    ws, report = backend_workspace()
    if retire == "missing":
        ws.backend_report = lambda: None
    elif retire == "stale":
        ws.backend_report = lambda: BackendLiveReport(reason="Backend status stale")
    elif retire == "connection":
        ws.control_owner.binding = ControlBinding("session", "other")
    elif retire == "client":
        ws.backend_panel.client.session_id = "other"
    elif retire in ("closed", "stopping"):
        setattr(ws.backend_panel, retire, True)
    else:

        def read():
            if retire == "owner":
                ws.control_owner = DesktopControlOwner()
            else:
                ws.control_owner.binding = ControlBinding("new", "new")
            return report

        ws.backend_report = read
    observation = observe_tool(ws, 1000.1)
    assert observation.backend_selected and not observation.current
    assert observation.pose is None and observation.raw_offset is None and observation.endpoint == ""
    ws.backend_panel.client.submit.assert_not_called()


@pytest.mark.parametrize("connected", [True, False, None])
def test_gui_packet_and_connection_availability_remain_distinct(connected):
    controller = SimpleNamespace(
        observed_pose=ObservedPose(1000, "Idle", (0, 0, 0), (0, 0, 0), 1, 28),
        connection_address="legacy",
        executeCommand=Mock(),
    )
    ws = SimpleNamespace(machine=SimpleNamespace(controller=controller))
    if connected is not None:
        ws.connected = connected
    observation = observe_tool(ws, 1000.1)
    assert observation.connection_current is connected
    assert observation.current is (connected is not False)
    assert observation.pose is None if connected is False else observation.pose.tool_length_mm == 28
    if connected is None:
        assert "availability unknown" in observation.reason
    controller.executeCommand.assert_not_called()
