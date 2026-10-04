import time
from unittest.mock import Mock

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.tool_history import TloReport, ToolHistory
from tests.integration.conftest import pump_frames


def test_tool_comparison_filters_links_and_expires_without_commands(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    history = ToolHistory()
    history.add_report(2, TloReport((50.47, 50.48), 0.01, 50.48, 123))
    monkeypatch.setattr(ws.machine, "tool_history", history)
    monkeypatch.setattr(
        viewer, "library_tool_table_mm", {2: ToolDefinition(2, diameter=6.35, description="Quarter-inch ball")}
    )
    monkeypatch.setattr(viewer, "tool_table", {2: ToolDefinition(2, diameter=0.25)})
    monkeypatch.setattr(viewer, "tool_unit_scale", 25.4)
    monkeypatch.setattr(
        ws.machine.controller,
        "observed_pose",
        ObservedPose(time.monotonic(), "Idle", (0, 0, 0), (0, 0, 0), 2, 50.48),
        raising=False,
    )
    monkeypatch.setattr(type(ws), "connected", property(lambda self: True))
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel = ws.tool_comparison
    panel.refresh(force=True)
    panel.choose(2)
    pump_frames(3)
    assert "50.48 mm" in panel.detail.text
    assert "50.47 mm" in panel.detail.text
    assert "session-local" in panel.detail.text
    pump_frames(15)
    settled_height = panel.detail.height
    pump_frames(15)
    assert panel.detail.height == settled_height
    panel.search.text = "absent tool"
    assert len(panel.list.children) == 1
    assert panel.list.children[0].text.startswith("No matching")
    panel.search.text = "ball"
    assert len(panel.list.children) == 1
    panel.search.text = ""
    monkeypatch.setattr(
        ws.machine.controller,
        "observed_pose",
        ObservedPose(time.monotonic() - 10, "Idle", (0, 0, 0), (0, 0, 0), 2, 50.48),
    )
    panel.refresh()
    assert "Current reported TLO: Unknown" in panel.detail.text
    assert "Last calibration applied TLO: 50.48 mm" in panel.detail.text
    send.assert_not_called()
    panel.selected = None


def test_persistent_assembly_drafts_cancellation_and_attribution(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.machine.tool_custody import ToolCustodyStore

    ws = kivy_app.root.desktop_workspace
    store = ToolCustodyStore(tmp_path / "custody.json")
    monkeypatch.setattr(ws.machine, "_tool_custody", store, raising=False)
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "machine-A", "name": "Test machine"})
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel = ws.tool_comparison.custody
    panel.selected_id = None
    ws.tool_comparison.selected = 2
    panel.new_assembly()
    panel.name_input.text = "Physical ball #1"
    panel.holder_input.text = "Collet A"
    panel.stickout_input.text = "1/4 in"
    panel.popup.dismiss()
    assert store.events == []
    panel.new_assembly()
    panel.name_input.text = "Physical ball #1"
    panel.stickout_input.text = "1/4 in"
    panel.popup_apply()
    assert panel.selected()["stickout_mm"] == 6.35
    panel.review_assignment()
    panel.popup.dismiss()
    assert store.assignment("machine-A", 2) is None
    panel.review_assignment()
    panel.popup_apply()
    assert store.assignment("machine-A", 2)["assembly_id"] == panel.selected_id
    raw = store.capture(2, TloReport((50.47, 50.48), 0.01, 50.48, 123), "fixture-test-source")
    panel.refresh(force=True)
    assert "1 unassigned" in panel.summary.text
    panel.review_link()
    panel.popup_apply()  # required attribution note must reject blank
    assert not store.assembly_reports(panel.selected_id)
    from carveracontroller.desktop_components import Field

    fields = [w for w in panel.popup.content.walk() if isinstance(w, Field)]
    fields[0].text = "Inventory tag checked in setup record"
    panel.popup_apply()
    assert store.assembly_reports(panel.selected_id) == [raw]
    assert "50.47" in panel.summary.text
    pump_frames(15)
    height = panel.summary.height
    pump_frames(15)
    assert panel.summary.height == height
    send.assert_not_called()
    panel.selected_id = None
    ws.tool_comparison.selected = None
