from unittest.mock import Mock

import pytest

from carveracontroller.machine.webcam import CameraFrame, WebcamClient
from tests.integration.conftest import pump_frames, set_window_viewport


@pytest.mark.parametrize("viewport", [(1040, 800), (1040, 1200), (1920, 1080)])
def test_camera_workbench_delivery_health_wraps_and_updates_without_machine_commands(
    kivy_app, monkeypatch, tmp_path, viewport
):
    from kivy.core.window import Window
    from kivy.metrics import dp

    ws = kivy_app.root.desktop_workspace
    original_size = Window.size
    original_section = ws.active_section
    original_camera_section = ws.camera_registration_panel.sections.current
    ticks = iter((10, 11.5, 20, 22))
    client = WebcamClient(
        start=False,
        clock=lambda: next(ticks),
        fetch=lambda _url, seq: CameraFrame((4, 3), bytes((20, 80, 120)) * 12, None, 11.5, seq, b"", 1.4, 0.1),
    )
    monkeypatch.setattr(ws, "camera_client", client)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    try:
        set_window_viewport(*viewport)
        ws.select("Camera")
        ws.camera_registration_panel.select_section("Source")
        client.poll_once()
        ws._refresh_camera()
        pump_frames(8)
        note = ws.camera_delivery_note
        assert "1 accepted · 0 failed · 1 requests" in note.text
        assert "Transfer 1.400s · decode 0.100s" in note.text
        assert "capture time unavailable" in ws.camera_status_labels[-1].text

        def fail(_url, _seq):
            raise TimeoutError("private request details")

        client.fetch = fail
        client.poll_once()
        ws._refresh_camera()
        pump_frames(5)
        assert "1 accepted · 1 failed · 2 requests" in note.text
        assert "Last attempt 2.000s" in note.text and "timing unavailable" in note.text
        assert "private" not in note.text
        assert note.text_size[0] == pytest.approx(note.width)
        assert note.texture_size[1] <= note.height
        scroll = ws.camera_registration_panel.sections.get_screen("Source").children[0]
        scroll.scroll_to(note, animate=False)
        pump_frames(5)
        note_bottom = note.to_window(*note.pos)[1]
        scroll_bottom = scroll.to_window(*scroll.pos)[1]
        assert scroll.height > 0, {
            "children": [
                (type(c).__name__, c.height, c.size_hint_y, getattr(c, "text", "")) for c in ws.inspector.children
            ],
            "window": Window.size,
            "workspace": ws.size,
            "inspector": ws.inspector.size,
            "pages": ws.inspector_pages.size,
            "panel": ws.camera_registration_panel.size,
            "navigation": ws.camera_registration_panel.section_navigation.size,
            "sections": ws.camera_registration_panel.sections.size,
        }
        assert note_bottom < scroll_bottom + scroll.height and note_bottom + note.height > scroll_bottom
        if viewport[1] >= 1080:
            assert note_bottom >= scroll_bottom - 2
            assert note_bottom + note.height <= scroll_bottom + scroll.height + 2
        else:
            assert ws.camera_registration_panel.note.parent is not ws.camera_registration_panel
        panel = ws.camera_registration_panel
        expected_navigation = panel.section_choice if panel.section_navigation.width < dp(340) else panel.section_tabs
        assert expected_navigation.parent is panel.section_navigation
        assert len(panel.section_navigation.children) == 1
        ws.camera_registration_panel.note.text = "Current calibration message"
        assert all(
            item.text == "Current calibration message" for item in ws.camera_registration_panel.section_notes.values()
        )
        ws.camera_registration_panel.export_to_png(str(tmp_path / f"camera-delivery-{viewport[0]}.png"))
        send.assert_not_called()
    finally:
        ws.camera_registration_panel.select_section(original_camera_section)
        ws.select(original_section)
        Window.size = original_size
        pump_frames(5)
