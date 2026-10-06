import threading
from unittest.mock import Mock

from .conftest import pump_frames


def test_wifi_open_does_not_block_frames_or_write_ui_from_worker(kivy_app, monkeypatch):
    root = kivy_app.root
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    main_ident = threading.get_ident()
    ui_threads = []

    def open_transport(*_args):
        assert threading.get_ident() != main_ident
        entered.set()
        assert release.wait(5)
        returned.set()
        return True

    opened = Mock(side_effect=open_transport)
    monkeypatch.setattr(root.controller, "open", opened)
    monkeypatch.setattr(root, "_wifi_connect_in_progress", False, raising=False)
    monkeypatch.setattr(root, "_usb_connect_in_progress", False, raising=False)
    for name in ("store_machine_address", "_remember_connection_method", "updateStatus"):
        monkeypatch.setattr(root, name, Mock(side_effect=lambda *_: ui_threads.append(threading.get_ident())))
    try:
        root.openWIFI("192.0.2.10:2222")
        assert entered.wait(2)
        assert root._wifi_connect_in_progress
        root.openWIFI("192.0.2.11:2222")
        root.openUSB("must-not-open")
        pump_frames(3)
        assert not ui_threads
        opened.assert_called_once()
    finally:
        release.set()
        assert returned.wait(2)
        pump_frames(10)
    assert not root._wifi_connect_in_progress
    assert ui_threads and set(ui_threads) == {main_ident}
    root.store_machine_address.assert_called_once_with("192.0.2.10")
    root._remember_connection_method.assert_called_once_with("wifi")


def test_failed_wifi_open_clears_busy_state_without_persisting_target(kivy_app, monkeypatch):
    root = kivy_app.root
    monkeypatch.setattr(root.controller, "open", Mock(side_effect=OSError("offline")))
    for name in ("store_machine_address", "_remember_connection_method", "updateStatus"):
        monkeypatch.setattr(root, name, Mock())
    monkeypatch.setattr(root, "_wifi_connect_in_progress", True, raising=False)
    worker = threading.Thread(target=root._open_wifi_worker, args=("192.0.2.10",))
    worker.start()
    worker.join(2)
    assert not worker.is_alive()
    assert root._wifi_connect_in_progress
    pump_frames(10)
    assert not root._wifi_connect_in_progress
    root.store_machine_address.assert_not_called()
    root._remember_connection_method.assert_not_called()
    root.updateStatus.assert_called_once_with()


def test_timer_reconnect_only_touches_popup_on_event_loop(kivy_app, monkeypatch):
    root = kivy_app.root
    main_ident = threading.get_ident()
    calls = []
    popup = Mock(_is_open=True)
    popup.dismiss.side_effect = lambda: calls.append(("dismiss", threading.get_ident()))
    monkeypatch.setattr(root, "reconnection_popup", popup)
    reconnect = Mock(side_effect=lambda **_: calls.append(("reconnect", threading.get_ident())))
    monkeypatch.setattr(root, "reconnect_last_connection", reconnect)
    worker = threading.Thread(target=root.attempt_reconnect)
    worker.start()
    worker.join(2)
    assert not worker.is_alive() and not calls
    pump_frames(3)
    assert calls == [("dismiss", main_ident), ("reconnect", main_ident)]
    reconnect.assert_called_once_with(quiet=False, for_app_launch=False)


def test_workbench_preserves_failure_and_disables_duplicate_attempt(kivy_app, monkeypatch, tmp_path):
    import time

    from carveracontroller.machine.connection_attempt import ConnectionAttempt

    root = kivy_app.root
    ws = root.desktop_workspace
    monkeypatch.setattr(kivy_app, "state", "Disconnected")
    entered, release = threading.Event(), threading.Event()
    send = Mock()

    def unreachable(*_args):
        entered.set()
        assert release.wait(5)
        raise OSError(65, "No route to host")

    opened = Mock(side_effect=unreachable)
    monkeypatch.setattr(root.controller, "open", opened)
    monkeypatch.setattr(root.controller, "executeCommand", send)
    monkeypatch.setattr(root.controller, "stream", None)
    monkeypatch.setattr(root.controller, "_connecting", False)
    monkeypatch.setattr(root, "_wifi_connect_in_progress", False, raising=False)
    monkeypatch.setattr(root, "_usb_connect_in_progress", False, raising=False)
    monkeypatch.setattr(root, "_connection_attempt", None, raising=False)
    monkeypatch.setattr(ws, "selected_machine_profile", {"host": "192.0.2.10", "port": 2222})
    for name in ("store_machine_address", "_remember_connection_method", "updateStatus"):
        monkeypatch.setattr(root, name, Mock())
    try:
        ws._connect_profile()
        assert entered.wait(2)
        pump_frames(3)
        ws.refresh(0)
        assert ws.state_label.text == "Connecting…"
        assert "192.0.2.10:2222" in ws.connection_label.text
        assert "Connecting via Wi-Fi" in ws.connection_health_note.text
        assert ws.profile_connect_button.disabled
        ws._connect_profile()
        opened.assert_called_once()
    finally:
        release.set()
        for _ in range(30):
            pump_frames(1, sleep=0.01)
            if not root._wifi_connect_in_progress:
                break
    ws.refresh(0)
    assert ws.state_label.text == "Connection failed"
    assert "Local Network permission" in ws.connection_health_note.text
    assert ws.profile_connect_button.text == "Retry profile"
    assert not ws.profile_connect_button.disabled
    assert root._connection_attempt.finished_at is not None
    pump_frames(3)
    ws.refresh(0)
    assert "No route to host" in ws.connection_health_note.text
    ws._connection_menu()
    pump_frames(25)
    assert ws.connection_health_note.height >= ws.connection_health_note.texture_size[1]
    ws.export_to_png(str(tmp_path / "connection-failed-workbench.png"))
    root.store_machine_address.assert_not_called()
    root._remember_connection_method.assert_not_called()
    send.assert_not_called()
    # An attempt record is not a live machine-state receipt.
    root._connection_attempt = ConnectionAttempt("Wi-Fi", "192.0.2.10:2222", time.monotonic()).finish(
        time.monotonic(), True
    )
    ws.refresh(0)
    assert ws.state_label.text == "Disconnected"
    assert "No active connection" in ws.connection_health_note.text
