"""Declared branch review is asynchronous and cannot send machine commands."""

import json
import threading
from unittest.mock import Mock

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
