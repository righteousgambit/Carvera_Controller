"""Real workbench changes invalidate evidence; inspector navigation never moves CNC."""

import time
from unittest.mock import Mock

import pytest
from kivy.metrics import dp

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames, set_window_viewport


def record_current(readiness, group):
    machine, snapshots, present = readiness.snapshot()
    assert machine and present[group]
    now = time.time()
    readiness.store.record(machine, group, snapshots[group], "inspection-log-42", "Physical check", now - 1, now + 3600)
    readiness.refresh()


def test_workholding_edit_invalidates_stock_and_offset_receipts(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "readiness-machine", "host": "fixture"})
    viewer.configure_machine(work_offset_mm=(-180, -120, -110), stock_size_mm=(100, 60, 30), stock_origin_mm=(0, 0, 0))
    readiness = ws.readiness
    for group in ("workholding", "stock", "offsets"):
        record_current(readiness, group)
    viewer.configure_workholding((10, 20, 0), 90, 20)
    readiness.refresh()
    states = {item.key: item.state for item in readiness.items}
    assert all(states[group] == "stale" for group in ("workholding", "stock", "offsets"))
    readiness.open()
    pump_frames(2)
    assert ws.inspector_pages.current == "Readiness"
    assert len(readiness.evidence_cards) == 4
    assert readiness.evidence_header.parent is readiness.rows
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    readiness._navigate("Scene")
    assert ws.active_section == "Scene"
    send.assert_not_called()


def test_tool_replacement_invalidates_measurement_and_serializes_enum(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "tool-evidence-machine"})
    monkeypatch.setattr(ws.operation_panel, "program", ProgramOperations.from_text("G21 G90 G94\nT1 M6\nG1 X10 F100\n"))
    viewer = ws.machine.gcode_viewer
    viewer.load_tool_profiles({1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6, length=50)})
    record_current(ws.readiness, "tools")
    assert next(item for item in ws.readiness.items if item.key == "tools").state == "measured"
    viewer.load_tool_profiles({1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6, length=48)})
    ws.readiness.refresh()
    assert next(item for item in ws.readiness.items if item.key == "tools").state == "stale"


def test_missing_program_tool_cannot_be_present_even_with_a_loaded_cutter(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "missing-program-tool"})
    monkeypatch.setattr(
        ws.operation_panel, "program", ProgramOperations.from_text("G21 G90 G94\nT1 M6\nG1 X10 F100\nT2 M6\nG1 X20\n")
    )
    ws.machine.gcode_viewer.load_tool_profiles({1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6, length=50)})
    _, snapshot, present = ws.readiness.snapshot()
    assert snapshot["tools"]["required_tools"] == [1, 2]
    assert not present["tools"]


def test_next_action_rechecks_navigation_without_motion(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    choose, send = Mock(), Mock()
    monkeypatch.setattr(ws, "_choose_program", choose)
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    kivy_app.selected_local_filename = ""
    kivy_app.selected_remote_filename = ""
    ws.readiness.refresh()
    assert ws.readiness.next_button.text == "Choose program"
    ws.select("Job")
    ws.readiness.refresh()
    assert ws.readiness.next_button.parent is None
    ws.select("Scene")
    ws.readiness.refresh()
    assert ws.readiness.next_button.parent is ws.readiness.strip
    ws.readiness.next_action()
    assert ws.readiness.next_button.parent is None
    choose.assert_called_once()
    send.assert_not_called()


@pytest.mark.parametrize("group", ["stock", "workholding", "tools", "offsets"])
@pytest.mark.parametrize("state", ["entered", "expired", "changed"])
def test_next_action_reveals_exact_check_and_preserves_other_receipts(kivy_app, monkeypatch, tmp_path, group, state):
    from copy import deepcopy

    from carveracontroller.machine.setup_readiness import SetupEvidenceStore

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    readiness = ws.readiness
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "next-evidence-machine"})
    monkeypatch.setattr(readiness, "store", SetupEvidenceStore(tmp_path / "evidence.json"))
    # This test supplies an analyzed program; a nonexistent file must not start
    # a competing analysis that replaces its required tool IDs between frames.
    ws.operation_panel.generation += 1
    monkeypatch.setattr(ws.operation_panel, "load", Mock())
    monkeypatch.setattr(kivy_app, "selected_local_filename", "prepared-job.cnc")
    monkeypatch.setattr(ws.operation_panel, "program", ProgramOperations.from_text("G21 G90 G94\nT1 M6\nG1 X10 F100\n"))
    viewer.configure_machine(stock_size_mm=(100, 60, 30), alignment_confirmed=True)
    viewer.load_tool_profiles({1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6, length=50)})
    for other in ("stock", "workholding", "tools", "offsets"):
        if other != group:
            record_current(readiness, other)
    machine, snapshots, _present = readiness.snapshot()
    now = time.time()
    if state != "entered":
        captured = snapshots[group] if state == "expired" else {"previous_setup": snapshots[group]}
        readiness.store.record(
            machine,
            group,
            captured,
            "previous-check",
            "Physical check",
            now - 3600,
            now - 1 if state == "expired" else now + 3600,
        )
    before = readiness.store.path.read_bytes()
    records = deepcopy(readiness.store.records)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    ws.select("Scene")
    readiness.next_button.dispatch("on_release")
    pump_frames(10)
    assert ws.inspector_pages.current == "Readiness"
    card, view = readiness.evidence_cards[group], readiness.evidence_scroll
    top = card.to_window(card.x, card.top)[1]
    view_bottom = view.to_window(view.x, view.y)[1]
    view_top = view.to_window(view.x, view.top)[1]
    assert view_bottom < top <= view_top + 1
    assert top - view_bottom >= min(card.height, view.height) - dp(20)
    states = {item.key: item.state for item in readiness.items}
    assert states[group] == ("entered" if state == "entered" else "stale")
    assert all(value == "measured" for key, value in states.items() if key != group), states
    assert readiness.store.records == records
    assert readiness.store.path.read_bytes() == before
    send.assert_not_called()
    ws.select("Job")


def test_next_action_opens_connection_task_when_only_telemetry_is_missing(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.machine.setup_readiness import SetupEvidenceStore

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    readiness = ws.readiness
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "connection-evidence-machine"})
    monkeypatch.setattr(readiness, "store", SetupEvidenceStore(tmp_path / "evidence.json"))
    ws.operation_panel.generation += 1
    monkeypatch.setattr(ws.operation_panel, "load", Mock())
    monkeypatch.setattr(ws.operation_panel, "program", None)
    monkeypatch.setattr(kivy_app, "selected_local_filename", "prepared-job.cnc")
    monkeypatch.setattr(kivy_app, "state", "Disconnected")
    viewer.configure_machine(stock_size_mm=(100, 60, 30), alignment_confirmed=True)
    viewer.load_tool_profiles({1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6, length=50)})
    for group in ("stock", "workholding", "tools", "offsets"):
        record_current(readiness, group)
    before = readiness.store.path.read_bytes()
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    ws._connection_menu()
    # Leave the connection inspector on a different task before invoking next.
    ws.machine_tasks.show("Preferences")
    readiness.next_button.dispatch("on_release")
    pump_frames(10)
    assert ws.active_section == "Settings"
    assert ws.machine_tasks.active == "Connect"
    assert readiness.next_button.text == "Inspect connection"
    assert readiness.store.path.read_bytes() == before
    send.assert_not_called()
    ws.select("Job")


def test_evidence_form_and_physical_invalidation(kivy_app, monkeypatch):
    from carveracontroller.desktop_components import Action, Field

    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "physical-change-machine"})
    readiness = ws.readiness
    record_current(readiness, "workholding")
    readiness.open()
    readiness.invalidate_dialog("workholding")
    pump_frames(2)
    dialog = readiness.record_popup
    field = next(widget for widget in dialog.walk() if isinstance(widget, Field))
    field.text = "Reclamped vise on the same holes"
    next(
        widget for widget in dialog.walk() if isinstance(widget, Action) and widget.text == "Invalidate receipt"
    ).dispatch("on_release")
    assert readiness.store.latest("physical-change-machine", "workholding")["source"] == field.text
    item = next(item for item in readiness.items if item.key == "workholding")
    assert item.state == "stale" and "Reclamped" in item.detail
    assert len([r for r in readiness.store.records if r["machine_id"] == "physical-change-machine"]) == 2
    ws.select("Job")


def test_readiness_render_at_desktop_and_compact_sizes(kivy_app, monkeypatch):
    import os
    from pathlib import Path

    from kivy.core.window import Window

    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "render-machine"})
    old_size = Window.size
    try:
        for width, height in ((1440, 900), (1000, 700)):
            set_window_viewport(width, height)
            ws.readiness.open()
            pump_frames(5)
            assert ws.readiness.rows.height > 0
            for card in ws.readiness.rows.children:
                assert card.width <= ws.inspector.width
            proof = os.environ.get("CARVERA_READINESS_PROOF_DIR")
            if proof:
                Path(proof).mkdir(parents=True, exist_ok=True)
                Window.screenshot(name=str(Path(proof) / f"readiness-{width}.png"))
            ws.select("Job")
    finally:
        set_window_viewport(*old_size)


def test_measurement_form_requires_receipt_and_saves_current_geometry(kivy_app, monkeypatch):
    from carveracontroller.desktop_components import Action, Field

    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "measurement-form-machine"})
    readiness = ws.readiness
    readiness.open()
    readiness.record_dialog("workholding")
    pump_frames(2)
    dialog = readiness.record_popup
    save = next(w for w in dialog.walk() if isinstance(w, Action) and w.text == "Save measurement receipt")
    save.dispatch("on_release")
    assert readiness.store.latest("measurement-form-machine", "workholding") is None
    fields = [w for w in dialog.walk() if isinstance(w, Field)]
    next(w for w in fields if w.hint_text.startswith("Micrometer")).text = "Dial indicator alignment"
    next(w for w in fields if w.hint_text.startswith("Measurement log")).text = "Inspection record 123"
    save.dispatch("on_release")
    receipt = readiness.store.latest("measurement-form-machine", "workholding")
    assert receipt and receipt["source"] == "Inspection record 123"
    assert next(item for item in readiness.items if item.key == "workholding").state == "measured"
    ws.select("Job")


def test_evidence_overview_distinguishes_declarations_rechecks_and_configuration(kivy_app, monkeypatch, tmp_path):
    from kivy.core.window import Window
    from PIL import Image

    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "mixed-evidence-machine"})
    monkeypatch.setattr(ws.operation_panel, "program", None)
    viewer = ws.machine.gcode_viewer
    viewer.configure_machine(stock_size_mm=(100, 60, 30), alignment_confirmed=False)
    viewer.load_tool_profiles({1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6, length=50)})
    readiness = ws.readiness
    machine, snapshots, present = readiness.snapshot()
    assert present["stock"] and present["tools"] and present["workholding"] and not present["offsets"]
    now = time.time()
    readiness.store.record(
        machine, "stock", snapshots["stock"], "Expired inspection", "Micrometer", now - 3600, now - 1
    )
    readiness.store.record(
        machine, "workholding", snapshots["workholding"], "Mounting inspection", "Indicator", now - 1, now + 3600
    )
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    old_size = Window.size
    try:
        for width in (1000, 1440):
            set_window_viewport(width, 900)
            readiness.open()
            pump_frames(5)
            assert readiness.state_summary.parent is readiness.evidence_header
            assert readiness.evidence_header.parent is readiness.rows
            assert (
                readiness.state_summary.text
                == "1 current operator receipts · 1 declared only · 1 need recheck · 1 need configuration"
            )
            for key, title in (
                ("workholding", "Current operator receipt"),
                ("stock", "Recheck needed"),
                ("tools", "Declared only"),
                ("offsets", "Configuration needed"),
            ):
                card = readiness.evidence_cards[key]
                heading = next(child for child in card.children if title in getattr(child, "text", ""))
                assert heading.texture_size[1] <= heading.height
                assert heading.text_size[0] <= card.width
            rendered = readiness.page.export_as_image().texture
            Image.frombytes("RGBA", rendered.size, rendered.pixels).save(tmp_path / f"readiness-overview-{width}.png")
            ws.select("Job")
        card = readiness.evidence_cards["workholding"]
        card.size_hint_x = None
        card.width = 280
        pump_frames(5)
        heading = next(child for child in card.children if "Current operator receipt" in getattr(child, "text", ""))
        assert heading.texture_size[1] <= heading.height and heading.height > 30
        from carveracontroller.desktop_components import Action

        for action in card.walk():
            if isinstance(action, Action):
                assert action.texture_size[0] <= action.width
                assert action.texture_size[1] <= action.height
        rendered = card.export_as_image().texture
        Image.frombytes("RGBA", rendered.size, rendered.pixels).save(tmp_path / "readiness-card-280.png")
        card.size_hint_x = 1
    finally:
        set_window_viewport(*old_size)
        ws.select("Job")
    send.assert_not_called()


def test_evidence_navigation_reveals_hidden_cards_without_writes_or_commands(kivy_app, monkeypatch, tmp_path):
    from copy import deepcopy

    from kivy.core.window import Window
    from PIL import Image

    from carveracontroller.desktop_components import DesktopScrollView

    ws = kivy_app.root.desktop_workspace
    readiness = ws.readiness
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    records = deepcopy(readiness.store.records)
    old_size = Window.size
    try:
        for width in (1000, 1440):
            set_window_viewport(width, 900)
            readiness.open()
            pump_frames(6)
            assert isinstance(readiness.evidence_scroll, DesktopScrollView)
            assert readiness.evidence_scroll.height >= 60
            assert readiness.evidence_scroll.scroll_type == ["content", "bars"]
            for key in ("offsets", "tools", "workholding", "stock"):
                if readiness.section_choice.parent is readiness.section_navigation_host:
                    readiness.section_choice._dropdown.select(readiness.section_titles[key])
                else:
                    readiness.section_actions[key].dispatch("on_release")
                pump_frames(8)
                card = readiness.evidence_cards[key]
                view = readiness.evidence_scroll
                bottom = card.to_window(card.x, card.y)[1]
                top = card.to_window(card.x, card.top)[1]
                view_bottom = view.to_window(view.x, view.y)[1]
                view_top = view.to_window(view.x, view.top)[1]
                assert top > view_bottom and bottom < view_top
                assert top <= view_top + 1
                assert top - view_bottom >= min(card.height, view.height) - dp(20)
                if key == "offsets":
                    rendered = readiness.page.export_as_image().texture
                    Image.frombytes("RGBA", rendered.size, rendered.pixels).save(
                        tmp_path / f"evidence-offset-{width}.png"
                    )
            if readiness.section_choice.parent is readiness.section_navigation_host:
                # A real dropdown selection must reveal even the unchanged value.
                readiness.evidence_scroll.scroll_y = 0
                pump_frames(3)
                readiness.section_choice._dropdown.select(readiness.section_choice.text)
                pump_frames(8)
                card = readiness.evidence_cards["stock"]
                top = card.to_window(card.x, card.top)[1]
                view_top = readiness.evidence_scroll.to_window(0, readiness.evidence_scroll.top)[1]
                assert abs(top - (view_top - dp(12))) <= 2
            # Pending navigation must not scroll a hidden page after changing tabs.
            readiness.section_actions["offsets"].dispatch("on_release")
            position = readiness.evidence_scroll.scroll_y
            ws.select("Job")
            pump_frames(5)
            assert readiness.evidence_scroll.scroll_y == position
        assert readiness.store.records == records
    finally:
        set_window_viewport(*old_size)
        ws.select("Job")
    send.assert_not_called()


def test_measured_mounting_form_roundtrip_sheet_and_stock_invalidation(kivy_app, monkeypatch, tmp_path):
    from dataclasses import asdict

    from carveracontroller.desktop_components import Action, Field, QuantityField
    from carveracontroller.machine.job_packages import JobPackage
    from carveracontroller.machine.setup_readiness import SetupEvidenceStore
    from carveracontroller.machine.setup_sheet import render_setup_sheet, setup_sheet

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "mounting-form-machine"})
    monkeypatch.setattr(ws.readiness, "store", SetupEvidenceStore(tmp_path / "evidence.json"))
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    viewer.configure_machine(stock_size_mm=(100, 60, 30))
    readiness = ws.readiness
    readiness.record_dialog("workholding")
    pump_frames(3)
    dialog = readiness.record_popup
    fields = [w for w in dialog.walk() if isinstance(w, Field)]
    next(w for w in fields if w.hint_text.startswith("Micrometer")).text = "Indicator and caliper"
    next(w for w in fields if w.hint_text.startswith("Measurement log")).text = "Mounting log 42"
    holes = next(w for w in fields if w.hint_text.startswith("Your plate labels"))
    holes.text = "A1, a1"
    next(w for w in fields if w.hint_text.startswith("Contact locations")).text = "Fixed jaw shoulder and movable jaw"
    protrusion = next(w for w in dialog.walk() if isinstance(w, QuantityField))
    protrusion.text = "1/4 in"
    save = next(w for w in dialog.walk() if isinstance(w, Action) and w.text == "Save measurement receipt")
    save.dispatch("on_release")
    assert not readiness.store.path.exists()  # Invalid labels preserve the draft.
    assert dialog.parent is not None and protrusion.text == "1/4 in"
    holes.text = "A1, B3"
    save.dispatch("on_release")
    receipt = SetupEvidenceStore(readiness.store.path).latest("mounting-form-machine", "workholding")
    assert receipt["mounting"] == {
        "hole_labels": ["A1", "B3"],
        "jaw_contact_notes": "Fixed jaw shoulder and movable jaw",
        "stock_protrusion_mm": 6.35,
    }
    card = readiness.evidence_cards["workholding"]
    assert any("A1, B3" in getattr(w, "text", "") for w in card.walk())
    sheet = setup_sheet(
        JobPackage(name="fixture", program=b"G21\n"),
        [asdict(item) for item in readiness.items],
        "2026-10-06T15:00:00+00:00",
    )
    rendered = render_setup_sheet(sheet)
    assert "Fixed jaw shoulder" in rendered and "stock_protrusion_mm" in rendered
    viewer.configure_machine(stock_size_mm=(101, 60, 30))
    readiness.refresh()
    assert next(item for item in readiness.items if item.key == "workholding").state == "stale"
    assert readiness.store.latest("mounting-form-machine", "workholding") == receipt
    send.assert_not_called()
    ws.select("Job")


@pytest.mark.parametrize("group", ["stock", "workholding", "tools", "offsets"])
def test_configuration_cards_open_exact_local_workflow_and_preserve_evidence(kivy_app, monkeypatch, tmp_path, group):
    from copy import deepcopy

    from carveracontroller.desktop_components import Action
    from carveracontroller.machine.setup_readiness import SetupEvidenceStore

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "configuration-route-machine"})
    store = SetupEvidenceStore(tmp_path / "route-evidence.json")
    monkeypatch.setattr(ws.readiness, "store", store)
    monkeypatch.setattr(
        ws.operation_panel, "program", ProgramOperations.from_text("G21 G90\nT1 M6\nG0 Z5\nT2 M6\nG0 Z5\nM30")
    )
    monkeypatch.setattr(viewer, "library_tool_table_mm", {1: ToolDefinition(1, diameter=6.35)})
    viewer.configure_machine(stock_size_mm=(100, 60, 30), stock_origin_mm=(0, 0, 0))
    record_current(ws.readiness, "stock")
    record_current(ws.readiness, "workholding")
    before_bytes = store.path.read_bytes()
    before_setup = deepcopy(ws.readiness.snapshot())
    send = Mock(side_effect=AssertionError("Evidence navigation cannot execute CNC commands"))
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    ws.readiness.open()
    pump_frames(3)
    card = ws.readiness.evidence_cards[group]
    action = next(
        child
        for child in card.walk()
        if isinstance(child, Action) and child.text == ws.readiness.configuration_label(group)
    )
    action.dispatch("on_release")
    pump_frames(5)
    if group in ("stock", "workholding"):
        assert ws.setup_editor.kind == group
        assert ws.setup_editor.popup._is_open
        ws.setup_editor.cancel()
    else:
        assert ws.active_section == "Setup"
        assert ws.setup_tasks.active == ("Tools" if group == "tools" else "Datum")
        if group == "tools":
            assert ws.tool_comparison.selected == 2
            assert "no loaded geometry" in ws.tool_comparison.detail.text
    assert store.path.read_bytes() == before_bytes
    assert ws.readiness.snapshot() == before_setup
    send.assert_not_called()
    ws.select("Job")
    pump_frames(3)


def test_configuration_action_rechecks_missing_machine_and_opens_profile_kind(kivy_app, monkeypatch):
    from types import SimpleNamespace

    ws = kivy_app.root.desktop_workspace
    opened, kind, send = Mock(), Mock(), Mock()
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "old-profile"})
    assert ws.readiness.configuration_label("stock") == "Edit stock geometry…"
    monkeypatch.setattr(ws, "selected_machine_profile", None)
    monkeypatch.setattr(ws, "_open_profiles", opened)
    monkeypatch.setattr(ws, "profile_library", SimpleNamespace(select_kind=kind), raising=False)
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    assert ws.readiness.configuration_label("stock") == "Choose machine profile"
    ws.readiness.configure("stock")
    opened.assert_called_once()
    kind.assert_called_once_with("machines")
    send.assert_not_called()
