from pathlib import Path
from unittest.mock import Mock

import pytest

from carveracontroller.main import MAX_CONFIG_DOWNLOAD_ATTEMPTS


@pytest.mark.parametrize("framed", [False, True])
def test_download_takes_rx_ownership_before_request(kivy_app, monkeypatch, tmp_path, framed):
    from carveracontroller import main as main_module

    root = kivy_app.root
    events = []
    stream = Mock()
    stream.download.side_effect = lambda *_: events.append("receive") or -1
    monkeypatch.setattr(root.controller, "stream", stream)
    monkeypatch.setattr(root.controller, "comms", Mock(uses_framed_transfer=framed))
    monkeypatch.setattr(root.controller, "pauseStream", lambda wait: events.append("park"))
    monkeypatch.setattr(root.controller, "downloadCommand", lambda path: events.append("request"))
    monkeypatch.setattr(root.controller, "resumeStream", lambda: events.append("resume"))
    monkeypatch.setattr(root, "downloading_config", False)
    monkeypatch.setattr(main_module.Clock, "schedule_once", lambda *_: None)
    root.doDownload("/sd/config.txt", str(tmp_path / "config.txt"), show_progress=False)
    assert events == ["park", "request", "receive", "resume"]


def test_configuration_cancel_remains_in_transfer_until_completion_and_suppresses_retries(kivy_app, monkeypatch):
    root = kivy_app.root
    stream = Mock()
    monkeypatch.setattr(root.controller, "stream", stream)
    monkeypatch.setattr(root, "_config_download_failures", 0)
    monkeypatch.setattr(root, "_config_download_cancel_requested", False, raising=False)
    monkeypatch.setattr(root, "config_loading", True)
    monkeypatch.setattr(root, "downloading_config", True)
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    root.progressStart("Load config...", root.cancelConfigurationDownload)
    try:
        assert not root.progress_popup.btn_cancel.disabled
        root.progress_popup.cancel()
        root.progress_popup.cancel()
        root.progressUpdate(50, "Downloading", False)
        stream.cancel_process.assert_called_once_with()
        assert root._config_download_failures == MAX_CONFIG_DOWNLOAD_ATTEMPTS
        assert root.config_loading and root.downloading_config
        assert root.progress_popup.btn_cancel.disabled
        assert "Canceling configuration" in root.progress_popup.progress_text
        send.assert_not_called()
    finally:
        root.progressFinish()


def test_canceled_configuration_never_applies_a_late_success(kivy_app, monkeypatch, tmp_path):
    from carveracontroller import main as main_module

    root = kivy_app.root
    stream = Mock()
    monkeypatch.setattr(root.controller, "stream", stream)
    monkeypatch.setattr(root.controller, "comms", Mock(uses_framed_transfer=True))
    for name in ("pauseStream", "resumeStream", "downloadCommand"):
        monkeypatch.setattr(root.controller, name, Mock())
    monkeypatch.setattr(root, "_config_download_cancel_requested", False, raising=False)
    monkeypatch.setattr(root, "_config_download_failures", 0)
    monkeypatch.setattr(root, "downloading_config", True)
    scheduled = []
    monkeypatch.setattr(main_module.Clock, "schedule_once", lambda callback, delay=0: scheduled.append(callback))

    def late_success(path, *_args):
        Path(path).write_text("late configuration bytes")
        root.cancelConfigurationDownload()
        return 24

    stream.download.side_effect = late_success
    target = tmp_path / "config.txt"
    root.doDownload("/sd/config.txt", str(target))
    assert not target.exists() and not Path(str(target) + ".tmp").exists()
    assert root._config_download_failures == MAX_CONFIG_DOWNLOAD_ATTEMPTS
    completions = [callback for callback in scheduled if getattr(callback, "func", None) == root.finishLoadConfig]
    assert len(completions) == 1 and completions[0].args == (False,)
    assert not any(getattr(callback, "func", None) == root.show_message_popup for callback in scheduled)
    root.controller.resumeStream.assert_called_once_with()


def test_desktop_configuration_status_preserves_editor_and_cancel_owner(kivy_app, monkeypatch):
    from tests.integration.conftest import pump_frames

    root = kivy_app.root
    ws = root.desktop_workspace
    status = ws.configuration_status
    ws.select("Camera")
    selected = ws.active_section
    stream = Mock()
    monkeypatch.setattr(root.controller, "stream", stream)
    monkeypatch.setattr(root, "downloading_config", True)
    monkeypatch.setattr(root, "config_loading", True)
    monkeypatch.setattr(root, "_config_download_cancel_requested", False, raising=False)
    root.progressStart("Load config...", root.cancelConfigurationDownload)
    try:
        pump_frames(4)
        assert root.progress_popup.parent is None
        assert status.strip.parent is ws.inspector
        root.progressUpdate(42, "Receiving config", False)
        assert "42%" in status.note.text
        assert ws.active_section == selected
        status.invoke()
        status.invoke()
        root.progressUpdate(80, "Late update", False)
        stream.cancel_process.assert_called_once_with()
        assert "Canceling" in status.note.text
        assert status.action.disabled
        status.complete(False, canceled=True)
        assert "canceled" in status.note.text
        status.complete(True)
        assert status.strip.parent is None
    finally:
        root.progressFinish()
        status.complete(True)


def test_configuration_error_inline_retry_guard_and_legacy_fallback(kivy_app, monkeypatch):
    root = kivy_app.root
    ws = root.desktop_workspace
    status = ws.configuration_status
    popup = Mock()
    monkeypatch.setattr(root, "show_message_popup", popup)
    root.configurationDownloadError("MD5 mismatch; configuration unavailable")
    assert "MD5 mismatch" in status.note.text
    assert status.strip.parent is ws.inspector
    popup.assert_not_called()
    request = Mock()
    monkeypatch.setattr(root, "download_config_file", request)
    monkeypatch.setattr(kivy_app, "state", "Idle")
    monkeypatch.setattr(root, "config_loading", False)
    monkeypatch.setattr(root, "downloading", True)
    status.invoke()
    request.assert_not_called()
    monkeypatch.setattr(root, "downloading", False)
    monkeypatch.setattr(root, "uploading", False)
    status.invoke()
    request.assert_called_once_with()
    status.complete(True)
    monkeypatch.setattr(root, "desktop_workspace", None)
    root.configurationDownloadError("legacy failure")
    popup.assert_called_once_with("legacy failure", False)


@pytest.mark.parametrize("md5_failed", [False, True])
def test_failed_config_transfer_routes_detailed_error_without_modal(kivy_app, monkeypatch, tmp_path, md5_failed):
    from carveracontroller import main as main_module

    root = kivy_app.root
    status = root.desktop_workspace.configuration_status
    stream = Mock()
    stream.download.return_value = None
    stream.modem.download_md5_failed = md5_failed
    monkeypatch.setattr(root.controller, "stream", stream)
    monkeypatch.setattr(root.controller, "comms", Mock(uses_framed_transfer=True))
    for name in ("pauseStream", "resumeStream", "downloadCommand"):
        monkeypatch.setattr(root.controller, name, Mock())
    monkeypatch.setattr(root, "downloading_config", True)
    monkeypatch.setattr(root, "_config_download_cancel_requested", False, raising=False)
    scheduled = []
    monkeypatch.setattr(main_module.Clock, "schedule_once", lambda callback, delay=0: scheduled.append(callback))
    popup = Mock()
    monkeypatch.setattr(root, "show_message_popup", popup)
    monkeypatch.setattr(
        root, "finishLoadConfig", lambda *_, **kwargs: (status.complete(False), status.error(kwargs["error_message"]))
    )
    try:
        root.doDownload("/sd/config.txt", str(tmp_path / "config.txt"))
        for callback in scheduled:
            callback(0)
        assert status.strip.parent is root.desktop_workspace.inspector
        assert "MD5" in status.note.text if md5_failed else "Download config file error" in status.note.text
        assert not status.active
        assert root.progress_popup.parent is None
        popup.assert_not_called()
    finally:
        root.progressFinish()
        status.complete(True)


def test_inline_config_error_wraps_in_narrow_workbench(kivy_app, tmp_path):
    from kivy.core.window import Window

    from tests.integration.conftest import pump_frames, set_window_viewport

    ws = kivy_app.root.desktop_workspace
    status = ws.configuration_status
    previous = tuple(Window.size)
    try:
        set_window_viewport(600, 850)
        status.error(
            "Configuration unavailable: received bytes failed MD5 verification. Retry when the machine is idle."
        )
        pump_frames(12)
        assert status.strip.parent is ws.inspector
        assert status.note.texture_size[1] <= status.strip.height < 500
        status.strip.export_to_png(str(tmp_path / "configuration-status-narrow.png"))
        assert (
            status.action.to_window(status.action.right, status.action.y)[0]
            <= status.strip.to_window(status.strip.right, status.strip.y)[0] + 1
        )
        assert status.note.width > 80
        assert kivy_app.root.progress_popup.parent is None
        status.strip.export_to_png(str(tmp_path / "configuration-status-narrow.png"))
    finally:
        status.complete(True)
        set_window_viewport(*previous)
