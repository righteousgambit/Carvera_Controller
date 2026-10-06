"""Header connection navigation reveals its controls without issuing commands."""

from unittest.mock import Mock

import pytest
from kivy.uix.scrollview import ScrollView

from tests.integration.conftest import pump_frames


def test_connection_action_reveals_controls_and_respects_later_task(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    before = ws.active_section
    card = ws.connection_card
    scroll = card.parent
    while not isinstance(scroll, ScrollView):
        scroll = scroll.parent
    old_scroll = scroll.scroll_y
    try:
        scroll.scroll_y = 1
        ws._connection_menu()
        pump_frames(25)
        assert ws.active_section == "Settings"
        connect = ws.profile_connect_button
        assert connect in list(card.walk())
        scroll_top = scroll.to_window(scroll.x, scroll.top)[1]
        scroll_bottom = scroll.to_window(scroll.x, scroll.y)[1]
        assert connect.to_window(connect.x, connect.top)[1] <= scroll_top
        assert connect.to_window(connect.x, connect.y)[1] >= scroll_bottom
        scroll.scroll_y = 1
        ws._connection_menu()
        ws.select("Job")
        pump_frames(10)
        assert ws.active_section == "Job"
        assert scroll.scroll_y == 1
        send.assert_not_called()
    finally:
        scroll.scroll_y = old_scroll
        ws.select(before)
        pump_frames(3)


def test_connection_timing_details_are_available_without_crowding_health(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    assert ws.navigation_timing_note.parent is None
    try:
        ws.navigation_timing_toggle.dispatch("on_release")
        pump_frames(3)
        assert ws.navigation_timing_note.parent is ws.navigation_timing_toggle.parent
        assert ws.navigation_timing_toggle.text.startswith("−")
        assert "callback" in ws.navigation_timing_note.text
        ws.navigation_timing_toggle.dispatch("on_release")
        pump_frames(3)
        assert ws.navigation_timing_note.parent is None
        assert ws.navigation_timing_toggle.text.startswith("+")
        send.assert_not_called()
    finally:
        if ws.navigation_timing_note.parent is not None:
            ws.navigation_timing_toggle.dispatch("on_release")


def test_incomplete_local_machine_profile_keeps_connect_disabled(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    connect = Mock()
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "draft"})
    monkeypatch.setattr(ws.machine, "openWIFI", connect)
    ws.refresh(0)
    assert ws.profile_connect_button.disabled
    ws._connect_profile()
    connect.assert_not_called()


@pytest.mark.parametrize("width", [530, 360])
def test_header_connection_pointer_click_reveals_machine_controls(kivy_app, monkeypatch, width):
    from kivy.metrics import dp
    from kivy.tests.common import UnitTestTouch

    ws = kivy_app.root.desktop_workspace
    original = ws.inspector.size_hint_x, ws.inspector.width
    before = ws.active_section
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    try:
        ws.inspector.size_hint_x = None
        ws.inspector.width = dp(width)
        ws.select("Scene")
        pump_frames(10)
        x, y = ws.connect_button.to_window(*ws.connect_button.center)
        touch = UnitTestTouch(x, y)
        touch.touch_down()
        pump_frames(2)
        touch.touch_up()
        pump_frames(25)
        assert ws.active_section == "Settings"
        assert not ws.connect_button.disabled
        send.assert_not_called()
    finally:
        ws.inspector.size_hint_x, ws.inspector.width = original
        ws.select(before)
        pump_frames(5)
