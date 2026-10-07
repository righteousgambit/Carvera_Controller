from unittest.mock import Mock

from carveracontroller.desktop_components import Action
from tests.integration.conftest import pump_frames


def test_entered_chain_selection_snapshot_and_actual_dismissal(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    panel = ws.kinematic_review_panel
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    original_length = panel.length_field.text
    popup = panel.inspect_frames()
    assert popup is not None
    try:
        tree = popup.frame_tree
        assert tree.select("Tool joint 5 · B")
        assert "Local:" in popup.frame_detail.text
        assert "Cumulative = parent" in popup.frame_detail.text
        assert "not measured" in popup.frame_detail.text
        assert "30 deg" in tree.nodes["Tool joint 5 · B"].text
        assert tree.select("Tool axis in workpiece")
        assert "dimensionless direction" in popup.frame_detail.text
        assert "No resolved point" not in tree.nodes["Tool axis in workpiece"].text
        assert tree.select("Tool tip in workpiece")
        assert "applied once" in popup.frame_detail.text
        captured = tree.captured
        detail = popup.frame_detail.text
        panel.length_field.text = "12 mm"
        assert tree.captured == captured and popup.frame_detail.text == detail
        pump_frames(8)
        popup.export_to_png(str(tmp_path / "declared-frame-chain.png"))
        close = next(widget for widget in popup.walk() if isinstance(widget, Action) and widget.text == "Close")
        close.trigger_action(0)
        pump_frames(20)
        assert popup.parent is None
        send.assert_not_called()
    finally:
        popup.dismiss()
        panel.length_field.text = original_length


def test_invalid_entered_chain_and_busy_panel_cannot_open_review(kivy_app):
    panel = kivy_app.root.desktop_workspace.kinematic_review_panel
    original_seeds = panel.seeds.text
    try:
        panel.seeds.text = ""
        assert panel.inspect_frames() is None
        assert "Enter a joint row" in panel.status.text
        panel.running = True
        assert panel.inspect_frames() is None
    finally:
        panel.running = False
        panel.seeds.text = original_seeds


def test_selected_calculated_branch_frame_snapshot(kivy_app, monkeypatch):
    from tests.integration.test_desktop_kinematic_review import wait_review

    ws = kivy_app.root.desktop_workspace
    panel = ws.kinematic_review_panel
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    original = panel.target_fields[0].text
    popup = None
    try:
        panel.target_fields[0].text = "0.5 in"
        panel.solve()
        assert panel.frame_action.disabled
        wait_review(panel)
        assert not panel.frame_action.disabled
        assert len(panel.reviews) == 2
        panel.select_branch(1)
        popup = panel.inspect_frames()
        assert popup is not None
        path = popup.frame_tree.nodes["Tool joint 1 · X"].path
        expected = panel.reviews[1].result.positions["X"]
        assert f"linear {expected:g} mm" in path.review.relation
        send.assert_not_called()
    finally:
        if popup is not None:
            popup.dismiss()
        panel.target_fields[0].text = original
        pump_frames(20)


def test_narrow_nine_joint_chain_keeps_rows_and_close_accessible(kivy_app, tmp_path):
    from kivy.core.window import Window

    from carveracontroller.desktop_kinematic_frames import open_kinematic_frames
    from tests.integration.conftest import set_window_viewport

    previous = tuple(Window.size)
    popup = None
    try:
        set_window_viewport(500, 800)
        record = {
            "schema": 1,
            "tool_chain": [
                {"name": f"J{i}", "kind": "linear", "axis": [1, 0, 0], "minimum": -10, "maximum": 10} for i in range(9)
            ],
        }
        popup = open_kinematic_frames(record, {f"J{i}": 1 for i in range(9)}, 5, "Synthetic nine-joint declaration")
        pump_frames(12)
        tree = popup.frame_tree
        deepest = tree.nodes["Tool joint 9 · J8"]
        assert deepest.width - deepest.padding[0] - deepest.padding[2] >= 100
        assert tree.select("Tool joint 9 · J8", navigate=True)
        pump_frames(8)
        detail_top = popup.frame_scroll.parent.to_widget(
            *popup.frame_detail.to_window(popup.frame_detail.x, popup.frame_detail.top)
        )[1]
        assert popup.frame_scroll.y <= detail_top <= popup.frame_scroll.top
        close = next(widget for widget in popup.walk() if isinstance(widget, Action) and widget.text == "Close")
        assert close.y >= popup.y and close.top <= popup.top
        assert "9.0, 0.0, 0.0" in popup.frame_detail.text
        popup.spatial_action.trigger_action(0)
        pump_frames(12)
        assert popup.frame_scroll.height >= 40
        assert popup.frame_diagram.height > 0
        diagram_bottom = popup.frame_scroll.parent.to_widget(
            *popup.frame_diagram.to_window(popup.frame_diagram.x, popup.frame_diagram.y)
        )[1]
        diagram_top = popup.frame_scroll.parent.to_widget(
            *popup.frame_diagram.to_window(popup.frame_diagram.x, popup.frame_diagram.top)
        )[1]
        popup.export_to_png(str(tmp_path / "spatial-narrow-before-assert.png"))
        assert diagram_bottom >= close.top
        assert diagram_top <= popup.top
        popup.export_to_png(str(tmp_path / "declared-frame-chain-narrow.png"))
        close.trigger_action(0)
        pump_frames(20)
        assert popup.parent is None
    finally:
        if popup is not None:
            popup.dismiss()
        set_window_viewport(*previous)


def test_linked_spatial_selection_reference_projection_and_origin_picking(kivy_app, monkeypatch, tmp_path):
    from kivy.input.motionevent import MotionEvent

    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    popup = ws.kinematic_review_panel.inspect_frames()
    try:
        popup.spatial_action.trigger_action(0)
        pump_frames(8)
        diagram = popup.frame_diagram
        tree = popup.frame_tree
        assert popup.spatial_box.height > 0
        fitted = list(diagram.projected.values()) + [end for _, end in diagram.axis_segments]
        assert abs((min(p[0] for p in fitted) + max(p[0] for p in fitted)) / 2 - (diagram.x + diagram.width / 2)) < 0.01
        assert (
            abs((min(p[1] for p in fitted) + max(p[1] for p in fitted)) / 2 - (diagram.y + diagram.height / 2)) < 0.01
        )
        tree.select("Tool joint 5 · B")
        pump_frames(5)
        assert diagram.selected_name == tree.selected_name
        assert len(diagram.axis_segments) == 3
        assert diagram.axis_segments[2][1] != diagram.axis_segments[2][0]
        tree.select("Tool axis in workpiece")
        assert "Direction glyph at spindle reference" in popup.spatial_caption.text
        popup.frame_reference.text = "Workpiece"
        popup.frame_view.text = "Front"
        pump_frames(8)
        assert "Workpiece reference" in popup.spatial_caption.text
        assert diagram.projection((2, 3, 4)) == (2, 4)
        assert diagram.selected_name == "Tool axis in workpiece"
        assert all(
            diagram.x <= x <= diagram.right and diagram.y <= y <= diagram.top for x, y in diagram.projected.values()
        )
        tree.select("Tool tip in world")
        pump_frames(3)

        class Touch(MotionEvent):
            def depack(self, args):
                self.sx, self.sy = args
                self.profile = ["pos"]
                super().depack(args)

        point = diagram.projected["Tool tip in world"]
        touch = Touch("test", 1, (0, 0))
        touch.x, touch.y = point
        touch.pos = point
        assert diagram.on_touch_down(touch)
        assert tree.selected_name == diagram.selected_name
        assert tree.selected_name != "Tool tip in world"  # coincident reference cycles identities
        popup.export_to_png(str(tmp_path / "spatial-frame-linked.png"))
        popup.spatial_action.trigger_action(0)
        assert popup.spatial_box.height == 0 and not popup.spatial_box.children
        assert tree.selected_name == diagram.selected_name
        send.assert_not_called()
    finally:
        popup.dismiss()


def test_spatial_resize_centers_from_current_geometry(kivy_app):
    from carveracontroller.desktop_frame_diagram import FrameDiagram
    from carveracontroller.machine.kinematic_frames import declared_spatial_frames

    record = {
        "schema": 1,
        "tool_chain": [{"name": "X", "kind": "linear", "axis": [1, 0, 0], "minimum": -50, "maximum": 50}],
    }
    diagram = FrameDiagram(declared_spatial_frames(record, {"X": 20}, 5))

    def assert_centered():
        points = list(diagram.projected.values()) + [end for _, end in diagram.axis_segments]
        for axis, expected in enumerate((diagram.x + diagram.width / 2, diagram.y + diagram.height / 2)):
            assert abs((min(p[axis] for p in points) + max(p[axis] for p in points)) / 2 - expected) < 0.01

    # Inspect each geometry change without requiring a selected-frame click.
    diagram.width = 950
    assert_centered()
    diagram.x = 240
    assert_centered()
    diagram.height = 180
    assert_centered()
    diagram.y = 350
    assert_centered()

    pump_frames(4)
    assert_centered()


def test_spatial_keyboard_inspects_exact_frames_and_releases_hidden_or_covered_focus(kivy_app, monkeypatch):
    from kivy.uix.popup import Popup

    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    popup = ws.kinematic_review_panel.inspect_frames()
    covering = Popup()
    try:
        popup.spatial_action.trigger_action(0)
        pump_frames(8)
        diagram, tree = popup.frame_diagram, popup.frame_tree
        names = [frame.name for frame in diagram.frames]
        diagram.focus = True
        keyboard = diagram._keyboard
        for key, index in (("home", 0), ("right", 1), ("down", 2), ("end", -1), ("home", 0), ("left", 0)):
            keyboard.dispatch("on_key_down", (0, key), "", [])
            assert diagram.selected_name == tree.selected_name == names[index]
            assert names[index] in popup.spatial_caption.text
        keyboard.dispatch("on_key_down", (0, "right"), "", ["super"])
        assert tree.selected_name == names[0]
        popup.frame_reference.text = "Workpiece"
        popup.frame_view.text = "Front"
        keyboard.dispatch("on_key_down", (0, "end"), "", [])
        assert tree.selected_name == names[-1]
        assert "Workpiece reference" in popup.spatial_caption.text
        covering.open(animation=False)
        pump_frames(3)
        keyboard.dispatch("on_key_down", (0, "home"), "", [])
        assert tree.selected_name == names[-1] and not diagram.focus
        covering.dismiss(animation=False)
        diagram.focus = True
        popup.spatial_action.trigger_action(0)
        assert not diagram.focus
        popup.spatial_action.trigger_action(0)
        diagram.focus = True
        popup.dismiss(animation=False)
        assert not diagram.focus
        send.assert_not_called()
    finally:
        covering.dismiss(animation=False)
        popup.dismiss(animation=False)
