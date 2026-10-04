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
