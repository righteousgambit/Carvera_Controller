"""Task navigation preserves advanced state without sending controller commands."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_commands import workspace_commands
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("width", [360, 650, 1100])
def test_machine_tasks_retain_state_focus_scroll_and_connection_route(kivy_app, monkeypatch, width):
    from kivy.metrics import dp
    from kivy.uix.popup import Popup
    from kivy.uix.widget import Widget

    ws = kivy_app.root.desktop_workspace
    deck = ws.machine_tasks
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    ws.select("Settings")
    page = deck.parent
    page.remove_widget(deck)
    popup = Popup(content=deck, size_hint=(None, None), size=(dp(width + 28), dp(700)))
    popup.open(animation=False)
    filler = Widget(size_hint_y=None, height=dp(1800))
    deck.sections["Connect"].add_widget(filler)
    original = ws.kinematic_review_panel
    try:
        pump_frames(8)
        deck.show("Connect")
        pump_frames(5)
        deck.scroll.scroll_y = 0.31
        deck.show("Captures")
        pump_frames(5)
        ws.commissioning_panel.note.text = "Retained imported review context"
        deck.show("Kinematics")
        pump_frames(5)
        assert ws.kinematic_review_panel is original
        assert deck.host.children == [deck.sections["Kinematics"]]
        deck.show("Connect")
        pump_frames(5)
        assert deck.scroll.scroll_y == pytest.approx(0.31, abs=0.003)
        deck.show("Captures")
        pump_frames(5)
        assert ws.commissioning_panel.note.text == "Retained imported review context"
        ws.commissioning_panel.import_button.focus = True
        deck.show("Health")
        pump_frames(5)
        assert not ws.commissioning_panel.import_button.focus
        assert ws.commissioning_panel.parent is deck.sections["Captures"]
        commands = {c.id: c for c in workspace_commands(ws)}
        for task in deck.names:
            assert commands["machine.task." + task.casefold()].invoke()
            pump_frames(3)
            assert deck.active == task and ws.active_section == "Settings"
            assert deck.choice.text == task
            assert deck.summary.text == deck.descriptions[task]
        ws._connection_menu()
        pump_frames(5)
        assert deck.active == "Connect"
        assert deck.navigation.height == dp(34)
        assert deck.scroll.height > dp(500)
        if width == 360:
            assert deck.choice.parent is deck.navigation
        if width == 1100:
            assert deck.tabs.parent is deck.navigation
        # Connection reveal intentionally goes to the top; select a new reading position.
        deck.scroll.scroll_y = 0.31
        # A deliberately rapid sequence must not restore a superseded task's scroll.
        deck.show("Connect")
        deck.show("Health")
        deck.show("Connect")
        pump_frames(6)
        assert deck.active == "Connect" and deck.scroll.scroll_y == pytest.approx(0.31, abs=0.003)
        send.assert_not_called()
        deck.sections["Connect"].remove_widget(filler)
        deck.scroll.scroll_y = 1
        pump_frames(5)
        out = Path("/private/tmp/carvera-machine-task-evidence-20261006")
        out.mkdir(exist_ok=True)
        deck.export_to_png(str(out / f"machine-connect-{width}.png"))
        deck.show("Health")
        pump_frames(5)
        deck.export_to_png(str(out / f"machine-health-{width}.png"))
    finally:
        if filler.parent is not None:
            filler.parent.remove_widget(filler)
        popup.dismiss(animation=False)
        if deck.parent is not None:
            deck.parent.remove_widget(deck)
        page.add_widget(deck)
        deck.show("Connect")
        pump_frames(3)
