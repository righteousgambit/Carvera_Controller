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
    ws.select("Setup")
    pump_frames(3)
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
    assert "current definition" in panel.summary.text
    original_revision = panel.selected()["revision_id"]
    panel.edit_assembly()
    panel.stickout_input.text = "28 mm"
    panel.note_input.text = "Reseated and changed stickout"
    panel.popup.dismiss()
    assert panel.selected()["revision_id"] == original_revision
    panel.edit_assembly()
    panel.stickout_input.text = "28 mm"
    panel.popup_apply()  # revision reason is required
    assert panel.selected()["revision_id"] == original_revision
    panel.note_input.text = "Reseated and changed stickout"
    panel.popup_apply()
    assert panel.selected()["stickout_mm"] == 28
    assert "older definition" in panel.summary.text
    assert "older or unversioned definition; reconcile" in panel.summary.text
    assert store.assembly_reports(panel.selected_id) == [raw]
    panel.review_release()
    panel.popup.dismiss()
    assert store.assignment("machine-A", 2)
    panel.review_release()
    panel.popup_apply()  # removal reason required
    assert store.assignment("machine-A", 2)
    fields = [w for w in panel.popup.content.walk() if isinstance(w, Field)]
    fields[0].text = "Placed in labeled drawer"
    panel.popup_apply()
    assert store.assignment("machine-A", 2) is None
    assert "Declared locations: None" in panel.summary.text
    panel.show_history()
    assert "Reseated and changed stickout" in panel.history_text
    assert "Declaration removed from Test machine / T2" in panel.history_text
    assert "Placed in labeled drawer" in panel.history_text
    panel.popup_apply()
    reviewed = panel.selected()
    panel.edit_assembly()
    panel.name_input.text = "Unsaved stale name"
    panel.note_input.text = "My change"
    other = ToolCustodyStore(store.path)
    fresh = other.revise(
        reviewed["id"], reviewed["revision_id"], "Externally revised assembly", stickout_mm=29, note="Other editor"
    )
    before = store.path.read_bytes()
    panel.popup_apply()
    assert store.path.read_bytes() == before
    assert panel.selected()["revision_id"] == fresh["id"]
    assert panel.name_input.text == "Unsaved stale name"
    panel.popup.dismiss()
    panel.edit_assembly()
    assert panel.name_input.text == "Externally revised assembly"
    panel.popup.dismiss()
    pump_frames(15)
    height = panel.summary.height
    pump_frames(15)
    assert panel.summary.height == height
    send.assert_not_called()
    panel.selected_id = None
    ws.tool_comparison.selected = None


def test_assembly_link_opens_exact_design_and_preserves_library_draft(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.desktop_profiles import ProfileLibrary
    from carveracontroller.machine.desktop_profiles import ProfileStore
    from carveracontroller.machine.tool_custody import ToolCustodyStore

    ws = kivy_app.root.desktop_workspace
    profiles = ProfileStore(tmp_path / "profiles.json")
    first = profiles.save_tool({"id": "first", "name": "First", "number": 1, "diameter": 6.35, "shank_diameter": 6.35})
    second = profiles.save_tool(
        {"id": "second", "name": "Second", "number": 2, "diameter": 3.175, "shank_diameter": 6.35}
    )
    library = ProfileLibrary(ws, store=profiles)
    library.select_record("tools", first["id"])
    library.fields["name"].text = "Unsaved design draft"
    monkeypatch.setattr(ws, "profile_store", profiles)
    monkeypatch.setattr(ws, "profile_library", library, raising=False)
    opened = Mock()
    monkeypatch.setattr(ws, "_open_profiles", opened)
    store = ToolCustodyStore(tmp_path / "custody.json")
    monkeypatch.setattr(ws.machine, "_tool_custody", store)
    panel = ws.tool_comparison.custody
    assembly = store.create_assembly("Physical cutter", profile_id=second["id"])
    panel.selected_id = assembly["id"]
    panel.open_profile()
    opened.assert_called_once()
    assert library.selected_kind == "tools"
    assert library.selected_id == second["id"]
    library.select_record("tools", first["id"])
    assert library.fields["name"].text == "Unsaved design draft"
    assert next(p for p in profiles.data["tools"] if p["id"] == first["id"])["name"] == "First"
    store.revise(assembly["id"], assembly["id"], "Physical cutter", profile_id="missing", note="Lost reference")
    panel.open_profile()
    assert "missing" in panel.result.text
    assert opened.call_count == 1
    panel.selected_id = None
