"""Connection recovery stays operable without capturing unrelated desktop input."""

from unittest.mock import Mock

from tests.integration.conftest import pump_frames


def test_workbench_recovery_retains_editor_and_explicit_retry(kivy_app, monkeypatch):
    from kivy.core.window import Window

    root = kivy_app.root
    ws = root.desktop_workspace
    recovery = root.reconnection_popup
    original = ws.active_section
    retry, send = Mock(), Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    try:
        recovery.dismiss(animation=False)
        ws._open_profiles()
        library = ws.profile_library
        field = library.fields["name"]
        before = field.text
        recovery.show_manual_reconnect(retry)
        recovery.open()
        pump_frames(5)
        assert recovery.presentation_active and recovery.desktop_visible
        assert recovery.parent is None and recovery not in Window.children
        assert ws.connection_recovery.height > 0 and not ws.connection_recovery.disabled
        assert ws.connection_recovery.parent is ws.inspector
        assert ws.recovery_cancel.text == "Dismiss"
        field.focus = True
        assert field.focus and field.text == before
        ws.select("Scene")
        assert ws.active_section == "Scene" and recovery.presentation_active
        ws._open_profiles()
        assert library.fields["name"] is field and field.text == before
        ws.recovery_retry.dispatch("on_release")
        pump_frames(3)
        retry.assert_called_once_with()
        assert not recovery.presentation_active
        assert ws.connection_recovery.height == 0
        assert ws.connection_recovery.parent is None
        send.assert_not_called()
    finally:
        recovery.dismiss(animation=False)
        ws.select(original)


def test_workbench_countdown_and_cancel_use_existing_callbacks(kivy_app, monkeypatch):
    root = kivy_app.root
    ws = root.desktop_workspace
    recovery = root.reconnection_popup
    retry, cancel, send = Mock(), Mock(), Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    try:
        recovery.start_countdown(3, 10, retry, cancel)
        recovery.open()
        recovery.countdown_tick()
        ws.refresh_connection_recovery()
        assert "retry 1/3 in 9s" in ws.recovery_note.text
        assert ws.recovery_cancel.text == "Cancel retries"
        retry.assert_not_called()
        ws.recovery_cancel.dispatch("on_release")
        assert not recovery.presentation_active and not recovery._is_open
        cancel.assert_called_once_with()
        retry.assert_not_called()
        send.assert_not_called()
    finally:
        recovery.dismiss(animation=False)


def test_legacy_reconnection_prompt_still_uses_modal(kivy_app, monkeypatch):
    from kivy.core.window import Window

    recovery = kivy_app.root.reconnection_popup
    recovery.dismiss(animation=False)
    monkeypatch.setattr(recovery, "_workbench", lambda: None)
    try:
        recovery.show_manual_reconnect(Mock())
        recovery.open(animation=False)
        pump_frames(3)
        assert recovery.presentation_active and recovery._is_open
        assert not recovery.desktop_visible
        assert recovery in Window.children
    finally:
        recovery.dismiss(animation=False)
        pump_frames(3)


def test_unavailable_retry_reports_inline_without_opening_address_dialog(kivy_app, monkeypatch):
    from kivy.core.window import Window
    from kivy.uix.modalview import ModalView

    root = kivy_app.root
    retry = Mock(return_value=False)
    address, send = Mock(), Mock()
    monkeypatch.setattr(root, "reconnect_last_connection", retry)
    monkeypatch.setattr(root, "manually_input_ip", address)
    monkeypatch.setattr(root.controller, "executeCommand", send)
    root.attempt_reconnect()
    pump_frames(5)
    assert root.reconnection_popup.desktop_visible
    assert "Reconnect unavailable" in root.desktop_workspace.recovery_note.text
    assert not any(isinstance(item, ModalView) for item in Window.children)
    retry.assert_called_once_with(quiet=True, for_app_launch=False)
    address.assert_not_called()
    send.assert_not_called()


def test_exhausted_retry_from_worker_presents_only_on_ui_thread(kivy_app, monkeypatch):
    import threading

    from carveracontroller import main

    root = kivy_app.root
    recovery = root.reconnection_popup
    recovery.dismiss(animation=False)
    monkeypatch.setattr(kivy_app, "state", main.NOT_CONNECTED)
    monkeypatch.setattr(root.controller, "stream", None)
    main_ident = threading.get_ident()
    calls = []
    original = recovery.open

    def record_open(*args, **kwargs):
        calls.append(threading.get_ident())
        return original(*args, **kwargs)

    monkeypatch.setattr(recovery, "open", record_open)
    worker = threading.Thread(target=root.on_reconnect_failed)
    worker.start()
    worker.join(2)
    assert not worker.is_alive() and not calls
    pump_frames(5)
    assert calls == [main_ident]
    assert recovery.desktop_visible and not recovery._is_open
    assert "Retries exhausted" in root.desktop_workspace.recovery_note.text


def test_recovery_banner_reflows_without_collapsing_active_camera_page(kivy_app, monkeypatch, tmp_path):
    from kivy.core.window import Window
    from kivy.metrics import dp

    from tests.integration.conftest import set_window_viewport

    root = kivy_app.root
    ws = root.desktop_workspace
    recovery = root.reconnection_popup
    original_size, original_section = Window.size, ws.active_section
    send, retry = Mock(), Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    try:
        ws.select("Camera")
        recovery.show_manual_reconnect(retry)
        recovery.open()
        for width in (1040, 1920, 1040):
            set_window_viewport(width, 1200)
            ws.refresh_connection_recovery()
            pump_frames(8)
            banner = ws.connection_recovery
            compact = banner.width < dp(400)
            assert banner.orientation == ("vertical" if compact else "horizontal")
            assert ws.recovery_note.width >= dp(100)
            assert banner.height < dp(140)
            assert ws.inspector_pages.height > dp(50)
            assert ws.camera_registration_panel.sections.height > 0
            for button in (ws.recovery_retry, ws.recovery_cancel):
                left, bottom = button.to_window(*button.pos)
                x, y = banner.to_window(*banner.pos)
                assert x - 1 <= left and left + button.width <= x + banner.width + 1
                assert y - 1 <= bottom and bottom + button.height <= y + banner.height + 1
            for button in ws.machine_action_row.children:
                left, bottom = button.to_window(*button.pos)
                x, y = ws.machine_controls.to_window(*ws.machine_controls.pos)
                assert x - 1 <= left and left + button.width <= x + ws.machine_controls.width + 1
                assert y - 1 <= bottom and bottom + button.height <= y + ws.machine_controls.height + 1
                assert button.width >= dp(48)
            ws.inspector.export_to_png(str(tmp_path / f"recovery-camera-{width}.png"))
        retry.assert_not_called()
        send.assert_not_called()
        ws.recovery_cancel.dispatch("on_release")
        pump_frames(3)
        assert banner.parent is None and banner.height == 0
    finally:
        recovery.dismiss(animation=False)
        ws.select(original_section)
        Window.size = original_size
        pump_frames(5)
