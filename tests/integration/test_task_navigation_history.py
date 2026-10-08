"""Back/forward restores task-specific context without executing machine actions."""

from unittest.mock import Mock

import pytest

from tests.integration.conftest import pump_frames


def test_setup_machine_and_monitor_tasks_form_distinct_history(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    ws.select("Setup")
    ws.setup_tasks.show("Tools")
    pump_frames(5)
    ws.navigation.reset()
    ws.navigation.enter("Setup")
    ws.setup_tasks.show("Holes")
    pump_frames(5)
    ws.select("Settings")
    ws.machine_tasks.show("Captures")
    pump_frames(5)
    ws.select("Monitor")
    ws.monitor_section_buttons["Diagnostics"].dispatch("on_release")
    pump_frames(5)
    history = ws.navigation.history
    targets = [(p["value"], p.get("task")) for p in history.items]
    assert targets[0:2] == [("Setup", "Tools"), ("Setup", "Holes")]
    assert ("Settings", "Captures") in targets
    assert targets[-1] == ("Monitor", "Diagnostics")
    expected = list(reversed(targets[:-1]))
    count = len(history.items)
    for page, task in expected:
        assert ws.navigation.navigate(-1)
        pump_frames(6)
        assert ws.active_section == page
        assert ws.navigation.task_context(page)[0] == task
        assert len(history.items) == count
    for page, task in targets[1:]:
        assert ws.navigation.navigate(1)
        pump_frames(6)
        assert ws.active_section == page and ws.navigation.task_context(page)[0] == task
        assert len(history.items) == count
    send.assert_not_called()
    ws.navigation.reset()


def test_history_restores_own_reading_position_and_stale_restore_cannot_steal_task(kivy_app, monkeypatch):
    from kivy.metrics import dp
    from kivy.uix.widget import Widget

    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    ws.select("Settings")
    deck = ws.machine_tasks
    deck.show("Connect")
    filler = Widget(size_hint_y=None, height=dp(1800))
    deck.sections["Connect"].add_widget(filler)
    try:
        pump_frames(8)
        ws.navigation.reset()
        ws.navigation.enter("Settings")
        deck.scroll.scroll_y = 0.24
        deck.show("Health")
        pump_frames(8)
        assert ws.navigation.navigate(-1)
        pump_frames(8)
        assert deck.active == "Connect"
        assert deck.scroll.scroll_y == pytest.approx(0.24, abs=0.005)
        assert ws.navigation.navigate(1)
        assert ws.navigation.navigate(-1)
        deck.show("Captures")
        pump_frames(8)
        assert deck.active == "Captures"
        send.assert_not_called()
    finally:
        deck.sections["Connect"].remove_widget(filler)
        ws.navigation.reset()


@pytest.mark.parametrize(
    "field,value", [("task", "Missing task"), ("scroll", True), ("scroll", float("nan")), ("scroll", 2)]
)
def test_invalid_task_history_rejects_before_page_or_view_changes(kivy_app, monkeypatch, field, value):
    ws = kivy_app.root.desktop_workspace
    ws.select("Setup")
    ws.setup_tasks.show("Tools")
    pump_frames(5)
    ws.navigation.reset()
    ws.navigation.enter("Setup")
    ws.setup_tasks.show("Holes")
    ws.navigation.history.items[0][field] = value
    before = ws.active_section, ws.setup_tasks.active, ws.navigation.history.index
    restore = Mock()
    monkeypatch.setattr(ws.machine.gcode_viewer, "set_pos_by_distance", restore)
    assert not ws.navigation.navigate(-1)
    assert (ws.active_section, ws.setup_tasks.active, ws.navigation.history.index) == before
    assert "Navigation unavailable" in ws.navigation_label.text
    restore.assert_not_called()
    ws.navigation.reset()


def test_missing_preview_geometry_is_not_captured_or_sought(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    ws.select("Setup")
    ws.setup_tasks.show("Tools")
    monkeypatch.setattr(viewer, "lengths", [])
    monkeypatch.setattr(viewer, "display_count", 5.0)
    ws.navigation.reset()
    ws.navigation.enter("Setup")
    assert ws.navigation.history.items[0]["distance"] is None
    ws.setup_tasks.show("Holes")
    # Retained old records must reject absent geometry before attempting a seek.
    ws.navigation.history.items[0]["distance"] = 5.0
    seek = Mock()
    monkeypatch.setattr(viewer, "set_pos_by_distance", seek)
    before = ws.active_section, ws.setup_tasks.active, ws.navigation.history.index
    assert not ws.navigation.navigate(-1)
    assert (ws.active_section, ws.setup_tasks.active, ws.navigation.history.index) == before
    assert "geometry is unavailable" in ws.navigation_label.text
    seek.assert_not_called()
    ws.navigation.reset()
