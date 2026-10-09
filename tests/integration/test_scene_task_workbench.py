"""Retained Scene tasks, linked selections and navigation without machine writes."""

from contextlib import contextmanager

import pytest
from kivy.metrics import dp
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget

from carveracontroller.desktop_scene import capture_scene_setup
from tests.integration import test_setup_editor
from tests.integration.conftest import pump_frames


@pytest.fixture
def scene_workspace(kivy_app, tmp_path, monkeypatch):
    yield from test_setup_editor.setup_workspace.__wrapped__(kivy_app, tmp_path, monkeypatch)


@contextmanager
def compact_scene(deck):
    parent, index = deck.parent, deck.parent.children.index(deck)
    parent.remove_widget(deck)
    popup = Popup(title="Compact Scene workbench", content=deck, size_hint=(None, None), size=(dp(340), dp(540)))
    popup.open()
    try:
        pump_frames(8)
        yield
    finally:
        popup.dismiss()
        deck.parent.remove_widget(deck)
        parent.add_widget(deck, index=index)
        pump_frames(5)


def test_scene_tasks_mount_one_body_retain_fields_and_release_menu_focus(scene_workspace, tmp_path):
    ws, send = scene_workspace
    ws.object_inspector.select("stock", record=False, reveal=False)
    ws.select("Scene")
    deck, interaction = ws.scene_tasks, ws.scene_interaction
    before = capture_scene_setup(ws)
    original = interaction.snap.text
    try:
        deck.show("Placement")
        pump_frames(8)
        interaction.snap.text = "1/8 in"
        interaction.snap.input.focus = True
        assert interaction.snap.input.focus
        deck.show("Inspect")
        pump_frames(8)
        assert not interaction.snap.input.focus
        assert interaction.snap.text == "1/8 in"
        assert len(deck.host.children) == 1
        assert deck.host.children[0] is deck.sections["Inspect"]
        assert deck.sections["Placement"].parent is None
        ws.object_inspector.choice.focus = True
        ws.object_inspector.choice.is_open = True
        deck.show("Components")
        pump_frames(8)
        assert not ws.object_inspector.choice.is_open
        assert ws.object_inspector.selected == "stock"
        assert interaction.snap.text == "1/8 in"
        deck.export_to_png(str(tmp_path / "scene-components-wide.png"))
        with compact_scene(deck):
            assert deck.choice.parent is deck.navigation
            for task in deck.names:
                deck.choice.text = task
                pump_frames(8)
                assert deck.active == task
                assert len(deck.host.children) == 1
                assert not deck.scroll.do_scroll_x
                assert all(c.width > 0 for c in deck.sections[task].children)
                deck.export_to_png(str(tmp_path / f"scene-{task.lower()}-compact.png"))
        deck.show("Placement")
        assert interaction.snap.text == "1/8 in"
        assert capture_scene_setup(ws) == before
        assert not ws.scene_setup_store.path.exists()
        send.assert_not_called()
    finally:
        interaction.snap.text = original
        ws.navigation.reset()


def test_scene_history_restores_task_component_and_reading_position(scene_workspace):
    ws, send = scene_workspace
    ws.select("Scene")
    deck = ws.scene_tasks
    deck.show("View")
    filler = Widget(size_hint_y=None, height=dp(1800))
    deck.sections["View"].add_widget(filler)
    try:
        pump_frames(8)
        ws.navigation.reset()
        ws.navigation.enter("Scene")
        deck.scroll.scroll_y = 0.23
        deck.show("Components")
        pump_frames(8)
        previous_count = len(ws.navigation.history.items)
        ws.object_inspector.select("fixture")
        pump_frames(8)
        assert deck.active == "Inspect" and ws.object_inspector.selected == "fixture"
        # A linked component action produces one arrival, not an intermediate task entry.
        assert len(ws.navigation.history.items) == previous_count + 1
        assert ws.navigation.navigate(-1)
        pump_frames(8)
        assert deck.active == "Components" and ws.object_inspector.selected == "stock"
        assert ws.navigation.navigate(-1)
        pump_frames(8)
        assert deck.active == "View"
        assert deck.scroll.scroll_y == pytest.approx(0.23, abs=0.005)
        assert ws.navigation.navigate(1)
        assert ws.navigation.navigate(-1)
        deck.show("Placement")
        pump_frames(8)
        assert deck.active == "Placement"
        send.assert_not_called()
    finally:
        deck.sections["View"].remove_widget(filler)
        ws.navigation.reset()


@pytest.mark.parametrize(
    "field,value", [("task", "Missing"), ("scroll", True), ("scroll", float("nan")), ("scroll", 2)]
)
def test_invalid_scene_history_rejects_before_selection_or_view_changes(scene_workspace, monkeypatch, field, value):
    from unittest.mock import Mock

    ws, send = scene_workspace
    ws.select("Scene")
    ws.scene_tasks.show("Components")
    pump_frames(8)
    ws.navigation.reset()
    ws.navigation.enter("Scene")
    ws.scene_tasks.show("View")
    pump_frames(8)
    ws.navigation.history.items[0][field] = value
    before = ws.active_section, ws.scene_tasks.active, ws.object_inspector.selected, ws.navigation.history.index
    restore = Mock()
    monkeypatch.setattr(ws.machine.gcode_viewer, "set_inspected_component", restore)
    assert not ws.navigation.navigate(-1)
    assert (
        ws.active_section,
        ws.scene_tasks.active,
        ws.object_inspector.selected,
        ws.navigation.history.index,
    ) == before
    assert "Navigation unavailable" in ws.navigation_label.text
    restore.assert_not_called()
    send.assert_not_called()
    ws.navigation.reset()
