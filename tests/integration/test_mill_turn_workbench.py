"""Rendered local planning navigation, retention, stale work and launch failures."""

import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.integration.conftest import pump_frames


def wait_review(panel):
    deadline = time.monotonic() + 5
    while panel.active and time.monotonic() < deadline:
        pump_frames(2, sleep=0.005)
    assert not panel.active
    pump_frames(6)
    return panel.review


def test_channel_planner_navigation_transfer_edit_and_no_commands(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.desktop_commands import workspace_commands

    ws = kivy_app.root.desktop_workspace
    panel = ws.mill_turn_panel
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    command = next(c for c in workspace_commands(ws) if c.id == "machine.task.channels")
    assert command.invoke()
    panel.load_example()
    review = wait_review(panel)
    assert review and not review.issues
    pump_frames(5)
    x, y, width, height, _ = next(region for region in panel.timeline.hit_regions if region[-1] == "cutoff")
    touch = SimpleNamespace(
        pos=(x + width / 2, y + height / 2), x=x + width / 2, y=y + height / 2, is_mouse_scrolling=False
    )
    assert panel.timeline.on_touch_down(touch)
    assert panel.selected_id == "cutoff"
    assert "datum UNSET" in panel.details.text and "remnant main" in panel.details.text
    panel.edit.set_expanded(True)
    panel.duration.text = "3"
    panel.apply_step()
    changed = wait_review(panel)
    assert changed.duration_s == 25.5
    assert panel.selected_id == "cutoff"
    panel.select_step("back-mill", changed)
    assert "sub-back" in panel.details.text
    ws.machine_tasks.show("Health")
    ws.machine_tasks.show("Channels")
    pump_frames(6)
    assert panel.review is changed and panel.selected_id == "back-mill"
    assert panel.timeline.hit_regions
    # A recycled row referring to an older analysis cannot change selection.
    panel.select_step("cutoff", review)
    assert panel.selected_id == "back-mill"
    ws.machine_tasks.export_to_png(str(tmp_path / "channel-planner.png"))
    send.assert_not_called()


@pytest.mark.parametrize("width", [360, 650, 1100])
def test_channel_panel_reflows_without_horizontal_overflow(kivy_app, width, tmp_path):
    from kivy.metrics import dp
    from kivy.uix.popup import Popup

    ws = kivy_app.root.desktop_workspace
    panel = ws.mill_turn_panel
    parent = panel.parent
    parent.remove_widget(panel)
    popup = Popup(content=panel, size_hint=(None, None), size=(dp(width + 28), dp(1600)))
    popup.open(animation=False)
    try:
        panel.load_example()
        assert wait_review(panel)
        panel.select_step("cutoff", panel.review)
        pump_frames(8)
        assert panel.timeline.width <= panel.width
        for control in (panel.example_action, panel.review_action, panel.copy_action, panel.steps, panel.details):
            assert control.x >= panel.x and control.right <= panel.right + dp(1)
        assert panel.details.height >= panel.details.texture_size[1]
        panel.export_to_png(str(tmp_path / f"channel-panel-{width}.png"))
    finally:
        popup.dismiss(animation=False)
        panel.parent.remove_widget(panel)
        parent.add_widget(panel)


def test_bounded_latest_request_cancel_closed_and_retry(monkeypatch):
    import carveracontroller.desktop_mill_turn as module
    from carveracontroller.machine.mill_turn_plan import example_record

    panel = module.MillTurnPanel(Mock())
    entered, release = threading.Event(), threading.Event()
    original = module.review_plan
    calls = []

    def slow(plan, cancelled):
        calls.append(plan.name)
        entered.set()
        release.wait(3)
        return original(plan, cancelled)

    monkeypatch.setattr(module, "review_plan", slow)
    panel.load_example()
    assert entered.wait(1)
    for index in range(12):
        record = example_record()
        record["name"] = f"Draft {index}"
        panel.source.text = json.dumps(record)
        panel.request_review()
    assert panel.active and panel.pending[1] == panel.source.text
    release.set()
    review = wait_review(panel)
    assert calls == ["DEMO dual-spindle transfer", "Draft 11"]
    assert review.plan.name == "Draft 11"
    panel.source.text = "invalid draft"
    assert panel.review is None and panel.copy_action.disabled
    panel.request_review()
    assert wait_review(panel) is None and "not admitted" in panel.status.text
    panel.dispose()
    panel._finish((panel.generation, panel.source.text), review, None)
    assert panel.review is None and not panel.steps.data


def test_worker_start_failure_is_retryable(monkeypatch):
    import carveracontroller.desktop_mill_turn as module

    panel = module.MillTurnPanel(Mock())
    original = module.threading.Thread

    class BrokenThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("injected launch failure")

    monkeypatch.setattr(module.threading, "Thread", BrokenThread)
    panel.load_example()
    assert not panel.active and "could not start" in panel.status.text
    monkeypatch.setattr(module.threading, "Thread", original)
    panel.request_review()
    assert wait_review(panel)
    panel.dispose()
