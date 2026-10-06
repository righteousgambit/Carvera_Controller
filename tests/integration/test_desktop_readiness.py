"""Real workbench changes invalidate evidence; inspector navigation never moves CNC."""

import time
from unittest.mock import Mock

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from tests.integration.conftest import pump_frames


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
    assert len(readiness.rows.children) == 5
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    readiness._navigate("Scene")
    assert ws.active_section == "Scene"
    send.assert_not_called()


def test_tool_replacement_invalidates_measurement_and_serializes_enum(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "tool-evidence-machine"})
    viewer = ws.machine.gcode_viewer
    viewer.load_tool_profiles({1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6, length=50)})
    record_current(ws.readiness, "tools")
    assert next(item for item in ws.readiness.items if item.key == "tools").state == "measured"
    viewer.load_tool_profiles({1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6, length=48)})
    ws.readiness.refresh()
    assert next(item for item in ws.readiness.items if item.key == "tools").state == "stale"


def test_next_action_rechecks_navigation_without_motion(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    choose, send = Mock(), Mock()
    monkeypatch.setattr(ws, "_choose_program", choose)
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    kivy_app.selected_local_filename = ""
    kivy_app.selected_remote_filename = ""
    ws.readiness.refresh()
    assert ws.readiness.next_button.text == "Choose program"
    ws.readiness.next_action()
    choose.assert_called_once()
    send.assert_not_called()


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
            Window.size = (width, height)
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
        Window.size = old_size


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
            Window.size = (width, 900)
            readiness.open()
            pump_frames(5)
            assert readiness.state_summary.parent is readiness.page
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
        Window.size = old_size
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
            Window.size = (width, 900)
            readiness.open()
            pump_frames(6)
            assert isinstance(readiness.evidence_scroll, DesktopScrollView)
            assert readiness.evidence_scroll.scroll_type == ["content", "bars"]
            for key in ("offsets", "tools", "workholding", "stock"):
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
                assert top - view_bottom >= min(card.height, view.height) - 20
                if key == "offsets":
                    rendered = readiness.page.export_as_image().texture
                    Image.frombytes("RGBA", rendered.size, rendered.pixels).save(
                        tmp_path / f"evidence-offset-{width}.png"
                    )
            # Pending navigation must not scroll a hidden page after changing tabs.
            readiness.section_actions["offsets"].dispatch("on_release")
            position = readiness.evidence_scroll.scroll_y
            ws.select("Job")
            pump_frames(5)
            assert readiness.evidence_scroll.scroll_y == position
        assert readiness.store.records == records
    finally:
        Window.size = old_size
        ws.select("Job")
    send.assert_not_called()
