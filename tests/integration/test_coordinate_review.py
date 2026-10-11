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


def test_reported_comparison_selection_and_stale_refresh_clear_estimate(kivy_app, monkeypatch, tmp_path):
    from types import SimpleNamespace

    from carveracontroller.machine.observed_pose import ObservedPose

    ws = kivy_app.root.desktop_workspace
    # This tests packet freshness, not the speed of constructing a real popup.
    # A loaded CI renderer can age a wall-clock fixture before the first review.
    now = [1000.0]
    monkeypatch.setattr("carveracontroller.desktop_coordinate_review.time", SimpleNamespace(monotonic=lambda: now[0]))
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(
        ws.machine.controller,
        "observed_pose",
        ObservedPose(now[0], "Idle", (100, 200, 300), (10, 20, 30), 1, 50, rotation_deg=90, wcs_index=2),
    )
    popup = open_coordinate_review(ws)
    try:
        tree = popup.coordinate_tree
        assert tree.select("Reported review-point estimate")
        assert "Conditional algebraic comparison" in popup.coordinate_detail.text
        assert "WCS index 2" in popup.coordinate_detail.text
        assert "no command" in popup.coordinate_detail.text
        assert tree.nodes["Reported review-point estimate"].depth == 2
        assert tree.select("Reported versus preview difference")
        assert "not its cause" in popup.coordinate_detail.text
        pump_frames(8)
        popup.export_to_png(str(tmp_path / "reported-coordinate-comparison.png"))
        now[0] += 2
        popup.refresh_coordinates()
        assert "Reported review-point estimate" not in tree.nodes
        assert "Reported versus preview difference" not in tree.nodes
        assert tree.selected_name == "Program/WCS point"
        assert "stale" in tree.nodes["Reported machine/work relation"].text
        send.assert_not_called()
    finally:
        popup.dismiss()
        pump_frames(20)
    assert popup.parent is None


def test_search_selects_exact_coordinate_dependency_and_rechecks_setup(kivy_app, monkeypatch):
    import carveracontroller.desktop_coordinate_review as review_module
    from carveracontroller.desktop_commands import coordinate_commands, search_commands

    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    opened = []
    original = review_module.open_coordinate_review

    def open_selected(workspace, name):
        popup = original(workspace, name)
        opened.append(popup)
        return popup

    monkeypatch.setattr(review_module, "open_coordinate_review", open_selected)
    entries = coordinate_commands(ws)
    command = search_commands(entries, "coordinate fixture frame")[0]
    try:
        assert command.invoke()
        popup = opened[0]
        pump_frames(6)
        assert popup.coordinate_tree.selected_name == "Fixture frame"
        assert "Unknown measured registration" in popup.coordinate_detail.text
        assert popup.coordinate_tree.select("Configured bed point")
        popup.refresh_coordinates()
        assert popup.coordinate_tree.selected_name == "Configured bed point"
        with monkeypatch.context() as stale_setup:
            stale_setup.setattr(ws.machine.gcode_viewer, "machine_setup", object())
            assert not command.invoke() and len(opened) == 1
        send.assert_not_called()
    finally:
        for popup in opened:
            popup.dismiss(animation=False)
        pump_frames(4)
