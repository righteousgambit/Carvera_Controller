"""CAD conversion controls stay responsive and reject late/dismissed publication."""

import sys
import threading
import time
from unittest.mock import Mock

import pytest
from kivy.config import Config

from carveracontroller.desktop_cad_import import open_cad_import
from carveracontroller.desktop_components import Action, Field
from tests.integration.conftest import pump_frames


def action(popup, text):
    return next(widget for widget in popup.walk() if isinstance(widget, Action) and widget.text == text)


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert predicate()


def dialog(tmp_path, monkeypatch):
    source = tmp_path / "tool.obj"
    source.write_text("v 0 0 0\nv 1 0 1\nv 0 1 1\nf 1 2 3\n")
    monkeypatch.setattr(Config, "write", Mock())
    Config.set("carvera", "tool_cad_python", sys.executable)
    applied = Mock()
    return open_cad_import(source, applied), applied


@pytest.mark.parametrize("dismiss", [False, True])
def test_cancel_and_dismiss_leave_ui_live_and_no_asset_applied(kivy_app, tmp_path, monkeypatch, dismiss):
    import carveracontroller.addons.tool_visualization.conversion_process as module

    entered, release, ended = threading.Event(), threading.Event(), threading.Event()
    observed = []

    def work(command, output, cancelled):
        observed.append((threading.current_thread(), command, output))
        entered.set()
        assert release.wait(5)
        assert cancelled()
        ended.set()
        # Deliberately successful late completion: delivery must still reject it.

    monkeypatch.setattr(module, "convert_process", work)
    send = Mock()
    monkeypatch.setattr(kivy_app.root.desktop_workspace.machine.controller, "executeCommand", send)
    popup, applied = dialog(tmp_path, monkeypatch)
    try:
        convert, cancel = action(popup, "Convert & inspect"), action(popup, "Cancel")
        convert.dispatch("on_release")
        wait_for(entered.is_set)
        assert convert.disabled and not cancel.disabled
        assert all(widget.disabled for widget in popup.walk() if isinstance(widget, Field))
        assert observed[0][0] is not threading.current_thread()
        if dismiss:
            popup.dismiss()
        else:
            cancel.dispatch("on_release")
            assert cancel.disabled
        pump_frames(3)
        release.set()
        wait_for(ended.is_set)
        pump_frames(5)
        if not dismiss:
            wait_for(lambda: not convert.disabled)
            assert not cancel.disabled and popup.parent
            assert any("no tool asset applied" in getattr(widget, "text", "") for widget in popup.walk())
            assert all(not widget.disabled for widget in popup.walk() if isinstance(widget, Field))
        applied.assert_not_called()
        send.assert_not_called()
    finally:
        release.set()
        popup.dismiss()


@pytest.mark.parametrize("stage", ["construct", "start"])
@pytest.mark.parametrize("failure", [RuntimeError, OSError])
def test_launch_failure_recovers_dialog(kivy_app, tmp_path, monkeypatch, stage, failure):
    import carveracontroller.desktop_cad_import as module

    popup, applied = dialog(tmp_path, monkeypatch)

    class FailedThread:
        def __init__(self, **_kwargs):
            if stage == "construct":
                raise failure("private environment diagnostic")

        def start(self):
            raise failure("private environment diagnostic")

    monkeypatch.setattr(module.threading, "Thread", FailedThread)
    try:
        convert, cancel = action(popup, "Convert & inspect"), action(popup, "Cancel")
        convert.dispatch("on_release")
        assert not convert.disabled and not cancel.disabled
        assert any("worker could not start" in getattr(widget, "text", "") for widget in popup.walk())
        assert not any("private environment" in getattr(widget, "text", "") for widget in popup.walk())
        applied.assert_not_called()
    finally:
        popup.dismiss()


def test_completed_validation_publishes_once(kivy_app, tmp_path, monkeypatch):
    import carveracontroller.addons.tool_visualization.conversion_process as module

    calls = []
    monkeypatch.setattr(module, "convert_process", lambda command, output, cancelled: calls.append(str(output)))
    popup, applied = dialog(tmp_path, monkeypatch)
    try:
        action(popup, "Convert & inspect").dispatch("on_release")
        wait_for(lambda: applied.call_count == 1)
        assert applied.call_args.args == (calls[0],)
        assert not popup.parent
    finally:
        popup.dismiss()


def test_frozen_module_uses_shipped_source_for_external_interpreter(kivy_app, tmp_path, monkeypatch):
    import carveracontroller.addons.tool_visualization.conversion_process as module
    from carveracontroller.addons.tool_visualization import converter

    source = tmp_path / "converter.py"
    source.write_text("# bundled Python source")
    monkeypatch.setattr(converter, "__file__", str(source.with_suffix(".pyc")))
    calls = []
    monkeypatch.setattr(module, "convert_process", lambda command, output, cancelled: calls.append(command))
    popup, applied = dialog(tmp_path, monkeypatch)
    try:
        action(popup, "Convert & inspect").dispatch("on_release")
        wait_for(lambda: applied.call_count == 1)
        assert calls[0][1] == str(source)
    finally:
        popup.dismiss()


def test_preference_write_failure_launches_nothing_and_recovers(kivy_app, tmp_path, monkeypatch):
    import carveracontroller.addons.tool_visualization.conversion_process as module

    popup, applied = dialog(tmp_path, monkeypatch)
    worker = Mock()
    monkeypatch.setattr(module, "convert_process", worker)
    monkeypatch.setattr(Config, "write", Mock(side_effect=OSError("private preference path")))
    try:
        convert, cancel = action(popup, "Convert & inspect"), action(popup, "Cancel")
        convert.dispatch("on_release")
        assert not convert.disabled and not cancel.disabled
        assert any("no conversion started" in getattr(widget, "text", "") for widget in popup.walk())
        assert all(not widget.disabled for widget in popup.walk() if isinstance(widget, Field))
        worker.assert_not_called()
        applied.assert_not_called()
    finally:
        popup.dismiss()
