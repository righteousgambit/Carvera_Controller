from unittest.mock import Mock

from carveracontroller.desktop_coordinate_review import open_coordinate_review
from tests.integration.conftest import pump_frames


def test_readonly_coordinate_snapshot_units_invalid_draft_and_focus(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    viewer = ws.machine.gcode_viewer
    before = viewer.machine_setup
    popup = open_coordinate_review(ws)
    try:
        pump_frames(8)
        assert popup.coordinate_rows.children
        popup.coordinate_fields[0].text = "1/4 in"
        popup.refresh_coordinates()
        assert any("X 6.3500" in row.text for row in popup.coordinate_rows.children)
        popup.coordinate_fields[0].input.focus = True
        popup.coordinate_fields[0].text = "bad input"
        popup.refresh_coordinates()
        assert not popup.coordinate_rows.children
        assert viewer.machine_setup is before
        send.assert_not_called()
    finally:
        popup.dismiss()
        pump_frames(3)
    assert not popup.coordinate_fields[0].input.focus


def test_coordinate_review_narrow_layout_and_snapshot_identity(kivy_app, tmp_path):
    from kivy.core.window import Window

    from tests.integration.conftest import set_window_viewport

    previous = tuple(Window.size)
    popup = None
    try:
        set_window_viewport(500, 800)
        popup = open_coordinate_review(kivy_app.root.desktop_workspace)
        pump_frames(12)
        assert popup.width <= Window.width
        assert all(field.width >= 140 for field in popup.coordinate_fields)
        assert any("Fixture frame" in row.text and "Unknown" in row.text for row in popup.coordinate_rows.children)
        popup.export_to_png(str(tmp_path / "coordinate-review-narrow.png"))
    finally:
        if popup is not None:
            popup.dismiss()
        set_window_viewport(*previous)
