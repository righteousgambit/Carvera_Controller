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


@pytest.mark.parametrize("pointer", [False, True])
def test_review_keeps_visible_load_action_at_its_reading_position(kivy_app, pointer, tmp_path):
    from kivy.metrics import dp
    from kivy.uix.popup import Popup

    ws = kivy_app.root.desktop_workspace
    ws.select("Settings")
    deck = ws.machine_tasks
    page = deck.parent
    page.remove_widget(deck)
    popup = Popup(content=deck, size_hint=(None, None), size=(dp(650), dp(650)))
    popup.open(animation=False)
    deck.show("Channels")
    panel = ws.mill_turn_panel
    panel.source.text = ""
    try:
        pump_frames(12)
        scroll = deck.scroll
        scroll.scroll_y = 1
        pump_frames(5)
        assert deck.host.height < scroll.height  # Small draft becomes a scrolling report.
        before = panel.example_action.to_window(panel.example_action.x, panel.example_action.top)[1]
        generation = panel.generation
        if pointer:
            from kivy.tests.common import UnitTestTouch

            touch = UnitTestTouch(*panel.example_action.to_window(*panel.example_action.center))
            touch.touch_down()
            touch.touch_up()
            pump_frames(20, sleep=0.01)
        else:
            panel.load_example()
        assert panel.generation > generation
        assert wait_review(panel)
        after = panel.example_action.to_window(panel.example_action.x, panel.example_action.top)[1]
        assert after == pytest.approx(before, abs=2), (before, after, scroll.scroll_y)
        deck.export_to_png(str(tmp_path / f"channel-review-anchor-{pointer}.png"))
        panel.edit.set_expanded(True)
        pump_frames(10)
        scroll.scroll_to(panel.apply_action, animate=False)
        pump_frames(5)
        before = panel.apply_action.to_window(panel.apply_action.x, panel.apply_action.top)[1]
        panel.duration.text = "3"
        if pointer:
            touch = UnitTestTouch(*panel.apply_action.to_window(*panel.apply_action.center))
            touch.touch_down()
            touch.touch_up()
            pump_frames(20, sleep=0.01)
        else:
            panel.apply_step()
        assert wait_review(panel).duration_s == 25.5
        after = panel.apply_action.to_window(panel.apply_action.x, panel.apply_action.top)[1]
        assert after == pytest.approx(before, abs=2), (before, after, scroll.scroll_y)
        panel.edit.set_expanded(False)
    finally:
        popup.dismiss(animation=False)
        if deck.parent is not None:
            deck.parent.remove_widget(deck)
        page.add_widget(deck)


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
    copied = Mock()
    monkeypatch.setattr("carveracontroller.desktop_mill_turn.Clipboard.copy", copied)
    panel.copy_review()
    from carveracontroller.machine.mill_turn_plan import load_plan

    assert load_plan(copied.call_args[0][0]) == review.plan
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


def wait_transfer(transfer):
    deadline = time.monotonic() + 5
    while transfer.active and time.monotonic() < deadline:
        pump_frames(2, sleep=0.005)
    assert not transfer.active
    pump_frames(4)


def test_file_roundtrip_receipts_and_native_picker_contract(kivy_app, monkeypatch, tmp_path):
    from pathlib import Path

    import carveracontroller.desktop_mill_turn as module

    panel = kivy_app.root.desktop_workspace.mill_turn_panel
    send = Mock()
    monkeypatch.setattr(panel.workspace.machine.controller, "executeCommand", send)
    panel.load_example()
    assert wait_review(panel)
    text = panel.source.text
    target = tmp_path / "reviewed.channel-plan.json"
    transfer = panel.transfer_plan_file(target, save=True)
    wait_transfer(transfer)
    assert target.read_text() == text and panel.file_receipt["path"] == str(target)
    assert "Saved exact reviewed" in panel.file_status.text
    transfer.dismiss()
    panel.source.text = "rejected local draft"
    assert panel.review is None and panel.save_action.disabled
    transfer = panel.transfer_plan_file(target)
    wait_transfer(transfer)
    assert panel.source.text == text and panel.review.duration_s == 24.5
    assert "Loaded declared plan" in panel.file_status.text
    transfer.dismiss()
    browser = SimpleNamespace(popup=Mock(), open=Mock(), filename=SimpleNamespace(text=""), dismiss=Mock())
    created = Mock(return_value=browser)
    monkeypatch.setattr(module, "ArtifactBrowser", created)
    panel.choose_plan_file(save=True)
    assert (
        created.call_args.kwargs["save"] is True
        and created.call_args.kwargs["title"] == "Save reviewed channel declarations"
    )
    assert browser.filename.text.endswith(".channel-plan.json")
    assert Path(browser.filename.text).name == browser.filename.text
    browser.open.assert_called_once()
    assert panel.load_action.disabled and panel.save_action.disabled
    # Callback rejects a changed draft instead of saving stale declarations.
    chosen = created.call_args.args[1]
    panel.source.text += " "
    with pytest.raises(ValueError, match="Draft changed"):
        chosen(str(tmp_path / "stale.json"))
    panel.file_browser = None
    panel.refresh_file_controls()
    send.assert_not_called()


def test_invalid_import_preserves_review_and_existing_export(kivy_app, tmp_path):
    panel = kivy_app.root.desktop_workspace.mill_turn_panel
    panel.load_example()
    review = wait_review(panel)
    text, selected = panel.source.text, panel.selected_id
    path = tmp_path / "invalid.json"
    path.write_bytes(b"not a plan")
    transfer = panel.transfer_plan_file(path)
    wait_transfer(transfer)
    assert panel.review is review and panel.source.text == text and panel.selected_id == selected
    assert "not accepted" in transfer.status.text
    transfer.dismiss()
    transfer = panel.transfer_plan_file(path, save=True)
    wait_transfer(transfer)
    assert path.read_bytes() == b"not a plan"
    assert panel.review is review and not list(tmp_path.glob(".carvera-channel-*"))
    transfer.dismiss()


def test_cancel_blocked_reader_retains_single_owner_and_current_plan(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_channel_transfer as module

    panel = kivy_app.root.desktop_workspace.mill_turn_panel
    panel.load_example()
    review = wait_review(panel)
    path = tmp_path / "plan.json"
    path.write_text(panel.source.text)
    entered, release = threading.Event(), threading.Event()
    original = module.read_plan_file

    def blocked(*args, **kwargs):
        entered.set()
        release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "read_plan_file", blocked)
    transfer = panel.transfer_plan_file(path)
    assert entered.wait(1)
    pump_frames(4)
    transfer.dismiss()
    assert panel.file_transfer is transfer and transfer.active
    assert panel.load_action.disabled
    with pytest.raises(ValueError, match="Wait for current"):
        panel.transfer_plan_file(path)
    panel.source.text += " "
    release.set()
    wait_transfer(transfer)
    assert panel.file_transfer is None and panel.review is None and panel.source.text.endswith(" ")
    assert not panel.load_action.disabled
    panel.load_example()
    assert wait_review(panel) == review


def test_export_changed_draft_rejected_before_commit(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_channel_transfer as module

    panel = kivy_app.root.desktop_workspace.mill_turn_panel
    panel.load_example()
    assert wait_review(panel)
    target = tmp_path / "new.json"
    entered, release = threading.Event(), threading.Event()
    original = module.prepare_plan_file

    def blocked(*args, **kwargs):
        prepared = original(*args, **kwargs)
        entered.set()
        release.wait(3)
        return prepared

    monkeypatch.setattr(module, "prepare_plan_file", blocked)
    transfer = panel.transfer_plan_file(target, save=True)
    assert entered.wait(1)
    panel.duration.text = "4"
    panel.apply_step()
    assert wait_review(panel)
    release.set()
    wait_transfer(transfer)
    assert not target.exists() and not list(tmp_path.glob(".carvera-channel-*"))
    assert panel.review is not None
    transfer.dismiss()


def test_transfer_worker_launch_failure_close_and_retry(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_channel_transfer as module

    panel = kivy_app.root.desktop_workspace.mill_turn_panel
    panel.load_example()
    assert wait_review(panel)
    target = tmp_path / "new.json"
    original = module.threading.Thread

    class Broken:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("injected startup failure")

    monkeypatch.setattr(module.threading, "Thread", Broken)
    transfer = panel.transfer_plan_file(target, save=True)
    assert not transfer.active and panel.file_transfer is None
    assert "could not start" in transfer.status.text
    transfer.dismiss()
    monkeypatch.setattr(module.threading, "Thread", original)
    transfer = panel.transfer_plan_file(target, save=True)
    wait_transfer(transfer)
    assert target.is_file()
    transfer.dismiss()


def test_import_delivery_rejects_changed_or_closed_owner(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_channel_transfer as module
    from carveracontroller.desktop_mill_turn import MillTurnPanel

    for closed in (False, True):
        panel = MillTurnPanel(kivy_app.root.desktop_workspace)
        panel.load_example()
        assert wait_review(panel)
        retained = panel.source.text
        path = tmp_path / f"queued-{closed}.json"
        path.write_text(retained)
        queued, delivered = [], threading.Event()

        def schedule(callback, _timeout=0, queued=queued, delivered=delivered):
            queued.append(callback)
            delivered.set()

        monkeypatch.setattr(module, "Clock", SimpleNamespace(schedule_once=schedule))
        transfer = panel.transfer_plan_file(path)
        assert delivered.wait(1)
        pump_frames(4)
        if closed:
            panel.dispose()
        else:
            panel.source.text = retained + " "
        queued.pop()(0)
        assert panel.source.text == retained + ("" if closed else " ")
        assert panel.review is None
        assert panel.file_transfer is None
        if not closed:
            assert "Draft changed while loading" in transfer.status.text
        transfer.dismiss()
        panel.dispose()


def test_publishing_cannot_be_dismissed_and_frames_remain_available(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_channel_transfer as module

    panel = kivy_app.root.desktop_workspace.mill_turn_panel
    panel.load_example()
    assert wait_review(panel)
    target = tmp_path / "publishing.json"
    entered, release = threading.Event(), threading.Event()
    original = module.commit_plan_file

    def blocked(prepared):
        entered.set()
        release.wait(3)
        return original(prepared)

    monkeypatch.setattr(module, "commit_plan_file", blocked)
    transfer = panel.transfer_plan_file(target, save=True)
    deadline = time.monotonic() + 2
    while not entered.is_set() and time.monotonic() < deadline:
        pump_frames(2, sleep=0.005)
    assert entered.is_set() and transfer.publishing and transfer.cancel.disabled
    pump_frames(8)
    transfer.dismiss()
    assert not transfer.closed and panel.file_transfer is transfer
    release.set()
    wait_transfer(transfer)
    assert target.is_file() and not transfer.cancel.disabled
    assert not list(tmp_path.glob(".carvera-channel-*"))
    transfer.dismiss()


def test_actual_artifact_browser_save_load_and_render(kivy_app, monkeypatch, tmp_path):
    from pathlib import Path

    from carveracontroller.desktop_file_picker import ArtifactBrowser

    ws = kivy_app.root.desktop_workspace
    panel = ws.mill_turn_panel
    panel.load_example()
    assert wait_review(panel)
    text = panel.source.text
    transfers = []
    original = panel.transfer_plan_file

    def capture(*args, **kwargs):
        transfer = original(*args, **kwargs)
        transfers.append(transfer)
        return transfer

    monkeypatch.setattr(panel, "transfer_plan_file", capture)
    ws.artifact_locations = {tuple(sorted((".channel-plan.json", ".json"))): str(tmp_path)}
    panel.choose_plan_file(save=True)
    browser = panel.file_browser
    assert isinstance(browser, ArtifactBrowser)
    deadline = time.monotonic() + 5
    while not browser.ready and time.monotonic() < deadline:
        pump_frames(2, sleep=0.005)
    assert browser.ready
    browser.filename.text = "file-roundtrip.channel-plan.json"
    browser.popup.export_to_png(str(tmp_path / "channel-plan-save-picker.png"))
    browser.choose()
    deadline = time.monotonic() + 5
    while not transfers and time.monotonic() < deadline:
        pump_frames(2, sleep=0.005)
    assert transfers
    transfer = transfers.pop()
    wait_transfer(transfer)
    target = Path(panel.file_receipt["path"])
    assert target.read_text() == text
    transfer.export_to_png(str(tmp_path / "channel-plan-save-receipt.png"))
    transfer.dismiss()
    panel.source.text = "local rejected draft"
    panel.choose_plan_file()
    browser = panel.file_browser
    deadline = time.monotonic() + 5
    while not browser.ready and time.monotonic() < deadline:
        pump_frames(2, sleep=0.005)
    assert browser.ready
    browser.filename.text = str(target)
    browser.choose()
    deadline = time.monotonic() + 5
    while not transfers and time.monotonic() < deadline:
        pump_frames(2, sleep=0.005)
    assert transfers
    transfer = transfers.pop()
    wait_transfer(transfer)
    assert panel.source.text == text and panel.review.duration_s == 24.5
    assert panel.file_browser is None
    transfer.dismiss()
