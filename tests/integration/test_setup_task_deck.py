"""Setup task routes retain local drafts and use guarded existing controls."""

from unittest.mock import Mock

import pytest

from carveracontroller.desktop_commands import workspace_commands
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("width", [360, 650])
def test_setup_task_layout_draft_routes_and_tool_focus(kivy_app, monkeypatch, tmp_path, width):
    from kivy.metrics import dp
    from kivy.uix.popup import Popup

    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    deck = ws.setup_tasks
    ws.select("Setup")
    page = deck.parent
    page.remove_widget(deck)
    popup = Popup(content=deck, size_hint=(None, None), size=(dp(width + 28), dp(700)))
    popup.open(animation=False)
    surface = ws.surface_planning_panel
    before, expanded = surface.source.text, surface.expanded
    try:
        pump_frames(8)
        commands = {c.id: c for c in workspace_commands(ws)}
        for task in deck.names:
            assert commands["setup.task." + task.casefold()].invoke()
            pump_frames(5)
            assert ws.active_section == "Setup" and deck.active == task
            assert deck.host.children == [deck.sections[task]]
            assert deck.choice.text == task
        deck.show("Surface")
        if not surface.expanded:
            surface.toggle()
        pump_frames(8)
        surface.source.text = "Unsaved instrument draft"
        surface.source.focus = True
        deck.show("Holes")
        pump_frames(5)
        assert not surface.source.focus
        assert surface.parent is deck.sections["Surface"]
        deck.show("Surface")
        pump_frames(5)
        assert surface.source.text == "Unsaved instrument draft"
        assert surface.expanded
        ws.tool_comparison.focus()
        pump_frames(10)
        assert deck.active == "Tools"
        assert deck.navigation.height == dp(34)
        assert deck.scroll.height > dp(500)
        assert deck.navigation.children[0] in (deck.choice, deck.tabs)
        if width == 650:
            assert deck.tabs.parent is deck.navigation
        send.assert_not_called()
        deck.export_to_png(str(tmp_path / f"setup-tools-{width}.png"))
        deck.show("Datum")
        pump_frames(6)
        deck.export_to_png(str(tmp_path / f"setup-datum-{width}.png"))
    finally:
        surface.source.text = before
        if surface.expanded != expanded:
            surface.toggle()
        popup.dismiss(animation=False)
        if deck.parent is not None:
            deck.parent.remove_widget(deck)
        page.add_widget(deck)
        deck.show("Tools")
        pump_frames(5)
