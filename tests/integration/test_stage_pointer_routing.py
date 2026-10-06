"""Exercise stage gestures through the production Window mouse provider."""

from unittest.mock import Mock

import pytest
from kivy.base import EventLoop
from kivy.core.window import Window
from kivy.graphics.texture import Texture
from kivy.input.providers.mouse import MouseMotionEventProvider
from kivy.metrics import dp

from tests.integration.conftest import pump_frames


def system_position(position):
    x, y = position
    return x * Window.system_size[0] / Window.width, (Window.height - y) * Window.system_size[1] / Window.height


def test_window_divider_drag_and_camera_wheel_are_isolated(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    ws.select("Camera")
    pump_frames(10)
    provider = MouseMotionEventProvider("stage-pointer", "multitouch_on_demand")
    camera = ws.camera_stage_view
    old_texture = camera.texture
    framing = camera.capture_framing()
    share = ws.workspace_media_share if hasattr(ws, "workspace_media_share") else 0.5
    monkeypatch.setattr(ws, "_refresh_camera", lambda: None)
    camera.texture = Texture.create(size=(640, 360))
    camera.reset_framing()
    viewer = ws.machine.gcode_viewer
    pose = (viewer.m_xRot, viewer.m_yRot, viewer.m_xPan, viewer.m_yPan, viewer.m_zoom)
    try:
        provider.start()
        divider = ws.pane_divider
        assert divider.height >= ws.inspector.height - 2
        start = divider.to_window(*divider.center)
        end = (start[0] - ws.body.width * 0.1, start[1])
        Window.dispatch("on_mouse_down", *system_position(start), "left", [])
        provider.update(EventLoop.post_dispatch_input)
        Window.dispatch("on_mouse_move", *system_position(end), [])
        provider.update(EventLoop.post_dispatch_input)
        Window.dispatch("on_mouse_up", *system_position(end), "left", [])
        provider.update(EventLoop.post_dispatch_input)
        pump_frames(8)
        assert divider.focus, "Release must retain the selected divider keyboard focus"
        assert ws.workspace_media_share == pytest.approx(0.4, abs=0.01)
        assert (viewer.m_xRot, viewer.m_yRot, viewer.m_xPan, viewer.m_yPan, viewer.m_zoom) == pose
        before_share = ws.workspace_media_share
        divider._keyboard.dispatch("on_key_down", (275, "right"), "", ["shift"])
        pump_frames(3)
        assert ws.workspace_media_share == pytest.approx(before_share + 0.05)
        assert divider.line.points[1] == pytest.approx(divider.y + dp(16))
        assert divider.line.points[3] == pytest.approx(divider.y + divider.height - dp(16))
        position = system_position(camera.to_window(*camera.center))
        Window.dispatch("on_mouse_down", *position, "left", [])
        provider.update(EventLoop.post_dispatch_input)
        Window.dispatch("on_mouse_up", *position, "left", [])
        provider.update(EventLoop.post_dispatch_input)
        pump_frames(3)
        assert camera.focus and not divider.focus
        camera._keyboard.dispatch("on_key_down", (61, "="), "=", [])
        assert camera.zoom == 1.25
        camera._keyboard.dispatch("on_key_down", (48, "0"), "0", [])
        assert camera.zoom == 1
        for button, expected in (("scrollup", 1.25), ("scrolldown", 1)):
            Window.dispatch("on_mouse_down", *position, button, [])
            provider.update(EventLoop.post_dispatch_input)
            Window.dispatch("on_mouse_up", *position, button, [])
            provider.update(EventLoop.post_dispatch_input)
            pump_frames(4)
            assert camera.zoom == pytest.approx(expected)
            assert (viewer.m_xRot, viewer.m_yRot, viewer.m_xPan, viewer.m_yPan, viewer.m_zoom) == pose
        ws.export_to_png(str(tmp_path / "stage-pointer-routing.png"))
        send.assert_not_called()
    finally:
        provider.stop()
        from carveracontroller.desktop_pane_divider import set_media_share

        set_media_share(ws, share)
        divider.focus = False
        camera.focus = False
        camera.texture = old_texture
        camera.restore_framing(framing)


def test_camera_keyboard_framing_preserves_machine_and_modifier_shortcuts(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    ws.select("Camera")
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    camera = ws.camera_stage_view
    before = camera.capture_framing()
    reference = ws.camera_registration_panel.reference_view
    assert camera.is_focusable and not reference.is_focusable
    try:
        camera.reset_framing()
        assert camera.keyboard_on_key_down(Window, (61, "="), "=", [])
        assert camera.zoom == 1.25
        assert camera.keyboard_on_key_down(Window, (45, "-"), "-", [])
        assert camera.zoom == 1
        camera.zoom_by(4)
        assert camera.keyboard_on_key_down(Window, (48, "0"), "0", [])
        assert camera.capture_framing() == {"zoom": 1, "center_x": 0.5, "center_y": 0.5}
        camera.keyboard_on_key_down(Window, (61, "="), "=", ["ctrl"])
        assert camera.zoom == 1
        send.assert_not_called()
    finally:
        camera.restore_framing(before)
