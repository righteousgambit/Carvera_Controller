"""Declared branch review is asynchronous and cannot send machine commands."""

import json
import threading
from unittest.mock import Mock

import pytest

from tests.integration.conftest import pump_frames


def wait_review(panel):
    for _ in range(80):
        pump_frames(2)
        if not panel.running:
            return
    assert not panel.running


def test_branch_selection_quantity_expression_and_no_commands(kivy_app, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    panel = workspace.kinematic_review_panel
    send = Mock()
    monkeypatch.setattr(workspace.machine.controller, "executeCommand", send)
    panel.target_fields[0].text = "0.5 in"
    panel.solve()
    wait_review(panel)
    assert len(panel.reviews) == 2
    assert panel.reviews[0].result.converged
    assert "limit margin" in panel.detail.text
    panel.select_branch(1)
    assert panel.selected_branch == 1
    assert panel.branch_buttons[1].base_color != panel.branch_buttons[0].base_color
    panel.target_fields[0].text = "5 mm"
    assert not panel.reviews
    assert "Inputs changed" in panel.status.text
    send.assert_not_called()


def test_stale_worker_result_discarded(kivy_app):
    panel = kivy_app.root.desktop_workspace.kinematic_review_panel
    release = threading.Event()
    delivered = Mock()

    def work(_cancelled):
        release.wait(2)
        return "stale"

    panel._start(work, delivered)
    panel.seeds.text += "\n"
    release.set()
    wait_review(panel)
    delivered.assert_not_called()
    assert "discarded" in panel.status.text
    assert not panel.solve_action.disabled


def test_profile_import_provenance_and_rejection_preserves_record(kivy_app, monkeypatch, tmp_path):
    workspace = kivy_app.root.desktop_workspace
    panel = workspace.kinematic_review_panel
    path = tmp_path / "declared.json"
    path.write_text(json.dumps(dict(panel.record, name="Declared mill")))
    monkeypatch.setattr(workspace, "choose_asset_file", lambda cb, **_kw: cb(str(path)))
    panel.import_profile()
    wait_review(panel)
    assert panel.record["name"] == "Declared mill"
    assert panel.topology.text == "Imported geometry"
    assert "file SHA" in panel.profile_note.text
    prior = panel.record
    path.write_text(json.dumps(dict(prior, controller_tcp_supported=True)))
    panel.import_profile()
    wait_review(panel)
    assert panel.record is prior
    assert "cannot establish" in panel.status.text


def test_invalid_unused_metadata_rejected_in_worker(kivy_app, monkeypatch, tmp_path):
    workspace = kivy_app.root.desktop_workspace
    panel = workspace.kinematic_review_panel
    prior = panel.record
    path = tmp_path / "malformed.json"
    path.write_text(json.dumps(dict(prior, metadata=float("nan"))))
    monkeypatch.setattr(workspace, "choose_asset_file", lambda cb, **_kw: cb(str(path)))
    panel.import_profile()
    wait_review(panel)
    assert panel.record is prior
    assert "Unknown" in panel.status.text
    assert not panel.import_action.disabled


def test_closed_panel_does_not_publish_pending_result(kivy_app):
    # Use an independent instance so the session workspace remains available.
    from carveracontroller.desktop_kinematic_review import KinematicReviewPanel

    panel = KinematicReviewPanel(kivy_app.root.desktop_workspace)
    release = threading.Event()
    done = Mock()
    panel._start(lambda _cancelled: release.wait(2), done)
    panel.dispose()
    release.set()
    wait_review(panel)
    done.assert_not_called()
    assert panel.closed


def test_review_controls_reflow_and_bound_input(kivy_app):
    from kivy.core.window import Window
    from kivy.metrics import dp

    from carveracontroller.desktop_components import AdaptiveGrid
    from carveracontroller.desktop_kinematic_review import KinematicReviewPanel

    panel = KinematicReviewPanel(kivy_app.root.desktop_workspace)
    panel.size_hint_x = None
    Window.add_widget(panel)
    try:
        panel.toggle()
        for width, target_columns in ((360, 2), (650, 3)):
            panel.width = dp(width)
            pump_frames(6)
            grid = next(
                child for child in panel.content.children if isinstance(child, AdaptiveGrid) and child.max_cols == 3
            )
            assert grid.cols == target_columns
            for cell in grid.children:
                assert cell.width >= grid.min_width
        panel.seeds.text = "0 " * 5000
        panel.solve()
        assert "bounded review size" in panel.status.text
        assert not panel.running
    finally:
        panel.dispose()
        Window.remove_widget(panel)


def test_shared_scroll_reveal_stops_at_self_parent_window(kivy_app):
    from kivy.core.window import Window
    from kivy.uix.widget import Widget

    from carveracontroller.desktop_scroll_navigation import queue_reveal

    target = Widget()
    Window.add_widget(target)
    try:
        event = queue_reveal(target, active=lambda: True)
        pump_frames(3)
        assert not event.is_triggered
    finally:
        Window.remove_widget(target)


def test_example_seeds_explore_distinct_endpoints_without_empty_result_gap(kivy_app):
    from carveracontroller.desktop_kinematic_review import KinematicReviewPanel

    panel = KinematicReviewPanel(kivy_app.root.desktop_workspace)
    assert panel.results.height == 0
    assert "→" not in panel.profile_note.text
    for topology in ("Head / head", "Head / table", "Table / table"):
        if panel.topology.text != topology:
            panel.topology.text = topology
        panel.solve()
        wait_review(panel)
        assert len(panel.reviews) == 2
        assert all(row.result.converged for row in panel.reviews)
        first, second = (row.result.positions for row in panel.reviews)
        assert abs(first["B"] - second["B"]) > 50
        assert abs(first["C"] - second["C"]) > 170
        assert "may coincide" in panel.status.text
    panel.dispose()


def test_joint_route_selects_interior_singularity_reflows_and_never_sends(kivy_app, monkeypatch):
    from types import SimpleNamespace

    from kivy.core.window import Window
    from kivy.metrics import dp

    from carveracontroller.desktop_kinematic_review import KinematicReviewPanel

    workspace = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(workspace.machine.controller, "executeCommand", send)
    panel = KinematicReviewPanel(workspace)
    panel.size_hint_x = None
    panel.width = dp(360)
    Window.add_widget(panel)
    try:
        panel.toggle()
        panel.path_card.toggle()
        panel.seeds.text = "0 0 0 0 -30\n0 0 0 0 30"
        panel.review_path()
        wait_review(panel)
        assert panel.path_review is not None
        assert 15 in panel.path_review.singular_indices
        assert panel.path_index == 15
        assert "4/5" in panel.path_detail.text
        assert "dependent local directions" in panel.path_note.text
        assert panel.path_navigation.parent is panel.path_card.content
        pump_frames(6)
        assert panel.path_plot.width > dp(250)
        assert panel.path_detail.height >= panel.path_detail.texture_size[1]
        assert panel.path_note.height >= panel.path_note.texture_size[1]
        panel.path_card.export_to_png("/private/tmp/carvera-joint-route-review-narrow-20261005.png")
        panel.step_path("last")
        assert panel.path_index == 30 and "5/5" in panel.path_detail.text
        panel.step_path(1)
        assert panel.path_index == 30
        plot = panel.path_plot
        touch = SimpleNamespace(pos=(plot.center_x, plot.center_y), x=plot.center_x, is_mouse_scrolling=False)
        assert plot.on_touch_down(touch)
        assert panel.path_index == 15
        panel.step_path(None)
        assert panel.path_index == 0
        panel.path_rotary_step.text = "1"
        assert panel.path_review is None and panel.path_plot.height == 0
        assert panel.path_navigation.parent is None
        assert "Inputs changed" in panel.path_note.text
        panel.review_path()
        wait_review(panel)
        assert len(panel.path_review.samples) == 61
        panel.path_rotary_step.text = "0"
        panel.review_path()
        wait_review(panel)
        assert panel.path_review is None
        assert "Minimum" in panel.path_note.text
        assert not panel.path_action.disabled
        send.assert_not_called()
    finally:
        panel.dispose()
        Window.remove_widget(panel)


def test_copy_solved_branches_to_explicit_route_and_cancel_pending_review(kivy_app, monkeypatch):
    from carveracontroller import desktop_kinematic_review as desktop

    panel = desktop.KinematicReviewPanel(kivy_app.root.desktop_workspace)
    panel.solve()
    wait_review(panel)
    assert not panel.path_solution_action.disabled
    solved = [r.result.positions for r in panel.reviews]
    panel.solutions_to_waypoints()
    assert not panel.reviews and panel.path_card.expanded
    assert "still requires review" in panel.path_note.text
    names = ["X", "Y", "Z", "C", "B"]
    for line, state in zip(panel.seeds.text.splitlines(), solved):
        assert all(abs(float(value) - state[name]) < 1e-8 for name, value in zip(names, line.split()))
    release = threading.Event()
    original = desktop.review_joint_path

    def delayed(*args, **kwargs):
        release.wait(2)
        return original(*args, **kwargs)

    monkeypatch.setattr(desktop, "review_joint_path", delayed)
    panel.review_path()
    panel.seeds.text += "\n"
    release.set()
    wait_review(panel)
    assert panel.path_review is None
    assert "discarded" in panel.path_note.text
    assert not panel.path_action.disabled
    panel.dispose()


def test_indexed_work_points_reflow_and_explicit_route_handoff(kivy_app, monkeypatch):
    from kivy.core.window import Window
    from kivy.metrics import dp

    from carveracontroller.desktop_kinematic_review import KinematicReviewPanel

    workspace = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(workspace.machine.controller, "executeCommand", send)
    panel = KinematicReviewPanel(workspace)
    indexed = panel.indexed_panel
    panel.size_hint_x = None
    panel.width = dp(360)
    Window.add_widget(panel)
    try:
        panel.toggle()
        indexed.toggle()
        indexed.rotary_fields["B"].text = "30 deg"
        indexed.rotary_fields["C"].text = "180 deg"
        indexed.map_points()
        wait_review(panel)
        assert indexed.review is not None
        assert indexed.review.fixed_rotary == {"B": 30, "C": 180}
        assert not indexed.copy_action.disabled
        assert "Tool axis in work" in indexed.note.text
        assert "limit margin" in indexed.details.text
        assert indexed.selected_point == 0
        indexed.select_point(1)
        assert indexed.selected_point == 1 and "Work point 2" in indexed.details.text
        assert indexed.point_buttons[0].base_color != indexed.point_buttons[1].base_color
        pump_frames(6)
        assert indexed.rotary_grid.cols == 2
        assert indexed.points.parent.height >= indexed.points.height + dp(24)
        assert indexed.branch_action.y >= indexed.points.parent.top
        assert indexed.points.y >= indexed.points.parent.y
        assert indexed.points.top <= indexed.points.parent.top
        assert all(button.height == indexed.point_choices.row_height for button in indexed.point_buttons)
        assert indexed.note.height >= indexed.note.texture_size[1]
        assert indexed.details.height >= indexed.details.texture_size[1]
        indexed.export_to_png("/private/tmp/carvera-indexed-setup-narrow-20261005.png")
        assert panel.seeds.text.startswith("0 0 0")  # Review does not silently rewrite a joint route.
        indexed.copy_waypoints()
        assert indexed.review is None and indexed.copy_action.disabled
        assert panel.path_card.expanded and "no indexing approach" in panel.path_note.text
        panel.review_path()
        wait_review(panel)
        assert panel.path_review is not None
        assert panel.path_review.joint_travel["B"] == panel.path_review.joint_travel["C"] == 0
        assert panel.path_review.largest_tip_chord_error_mm < 1e-8
        send.assert_not_called()
    finally:
        panel.dispose()
        Window.remove_widget(panel)


def test_indexed_selected_branch_copy_rejection_and_stale_result(kivy_app):
    from carveracontroller.desktop_kinematic_review import KinematicReviewPanel

    panel = KinematicReviewPanel(kivy_app.root.desktop_workspace)
    try:
        panel.solve()
        wait_review(panel)
        panel.select_branch(1)
        positions = dict(panel.reviews[1].result.positions)
        indexed = panel.indexed_panel
        assert not indexed.branch_action.disabled
        indexed.use_branch()
        assert not panel.reviews
        assert all(field.value() == pytest.approx(positions[name]) for name, field in indexed.rotary_fields.items())
        indexed.points.text = "10 15 25\n1000 0 0"
        indexed.map_points()
        wait_review(panel)
        assert indexed.review is None and indexed.copy_action.disabled
        assert "Work point 2 exceeds" in indexed.note.text
        release = threading.Event()
        delivered = Mock()
        panel._start(lambda _cancelled: release.wait(2), delivered, error_target=indexed.note)
        indexed.rotary_fields["B"].text = "40"
        release.set()
        wait_review(panel)
        delivered.assert_not_called()
        assert "discarded" in indexed.note.text
        assert not indexed.review_action.disabled
    finally:
        panel.dispose()
