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
