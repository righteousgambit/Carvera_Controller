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
        popup.export_to_png(str(tmp_path / "declared-frame-chain-narrow.png"))
        close.trigger_action(0)
        pump_frames(20)
        assert popup.parent is None
    finally:
        if popup is not None:
            popup.dismiss()
        set_window_viewport(*previous)
