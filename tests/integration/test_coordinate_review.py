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
        popup.coordinate_point_fold.set_expanded(True)
        pump_frames(8)
        assert popup.coordinate_rows.children
        popup.coordinate_fields[0].text = "1/4 in"
        assert not popup.coordinate_tree.nodes
        assert "changed" in popup.coordinate_detail.text
        popup.refresh_coordinates()
        assert any("X 6.3500" in row.text for row in popup.coordinate_tree.nodes.values())
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
        assert popup.coordinate_scroll.height > 0
        popup.coordinate_point_fold.set_expanded(True)
        pump_frames(8)
        assert all(field.width >= 140 for field in popup.coordinate_fields)
        popup.coordinate_point_fold.set_expanded(False)
        pump_frames(8)
        assert any(
            "Fixture frame" in row.text and "Unknown" in row.text for row in popup.coordinate_tree.nodes.values()
        )
        popup.coordinate_scroll.scroll_to(popup.coordinate_tree.nodes["Configured bed point"], animate=False)
        pump_frames(8)
        for node in popup.coordinate_tree.nodes.values():
            assert node.text_size[0] == node.width
            assert node.width - node.padding[0] - node.padding[2] >= 120
        popup.export_to_png(str(tmp_path / "coordinate-review-narrow.png"))
        node = popup.coordinate_tree.nodes["Fixture frame"]
        node.trigger_action(0)
        pump_frames(8)
        popup.export_to_png(str(tmp_path / "coordinate-detail-narrow.png"))
    finally:
        if popup is not None:
            popup.dismiss()
        set_window_viewport(*previous)


def test_selectable_paths_keep_source_and_dependency_kinds(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    popup = open_coordinate_review(ws)
    try:
        pump_frames(8)
        tree = popup.coordinate_tree
        assert tree.select("Configured bed point")
        assert "Configured transformation" in popup.coordinate_detail.text
        assert "Program +" in popup.coordinate_detail.text
        assert tree.nodes["Configured bed point"].depth == 1
        assert tree.nodes["Stock local point"].depth == 1
        tree.nodes["Fixture frame"].trigger_action(0)
        pump_frames(3)
        assert tree.selected_name == "Fixture frame"
        assert "no parent asserted" in popup.coordinate_detail.text
        assert "Unknown measured registration" in popup.coordinate_detail.text
        assert tree.nodes["Fixture frame"].path.group == "Unregistered fixture"
        popup.refresh_coordinates()
        assert tree.selected_name == "Fixture frame"
        assert not tree.select("missing")
        pump_frames(8)
        popup.export_to_png(str(tmp_path / "coordinate-tree-wide.png"))
        popup.coordinate_fields[1].text = "bad"
        assert not tree.nodes and not tree.paths and tree.captured is None
        popup.refresh_coordinates()
        assert not tree.nodes and "Cannot review" in popup.coordinate_detail.text
        send.assert_not_called()
    finally:
        popup.dismiss()


def test_close_action_removes_popup_and_releases_focus(kivy_app):
    from carveracontroller.desktop_components import Action

    popup = open_coordinate_review(kivy_app.root.desktop_workspace)
    popup.coordinate_point_fold.set_expanded(True)
    pump_frames(12)
    popup.coordinate_fields[0].input.focus = True
    close = next(widget for widget in popup.walk() if isinstance(widget, Action) and widget.text == "Close")
    close.trigger_action(0)
    pump_frames(20)
    assert popup.parent is None
    assert not popup.coordinate_fields[0].input.focus
