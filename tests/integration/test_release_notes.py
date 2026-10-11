from unittest.mock import Mock

import pytest
from kivy.clock import Clock

from carveracontroller.release_notes_view import ReleaseNotesView
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("width", [360, 650])
def test_hidden_notes_never_send_full_payload_to_textinput(width):
    view = ReleaseNotesView()
    view.size = (width, 500)
    payload = "[2.1.0]\n" + "Long release note é🙂\n" * 5000
    rendered = []
    view.body.bind(text=lambda _, text: rendered.append(text))
    view.text = payload
    assert view._pages is None and view.body.text == "" and not rendered
    ticks = []
    Clock.schedule_once(lambda _: ticks.append(True), 0)
    pump_frames(2)
    assert ticks
    view.active = True
    assert view.text == payload and len(view.body.text) <= 2048
    assert view._index == 0 and view.previous.disabled and not view.next.disabled
    view.next.dispatch("on_release")
    assert view._index == 1 and not view.previous.disabled
    view.move(100000)
    assert view.next.disabled
    assert "".join(view._pages) == payload
    view.active = False
    assert view.body.text == "" and not view.body.focus
    view.text = "[3.0.0]\nNew notes"
    assert view._pages is None and view.body.text == ""
    view.active = True
    assert view.body.text == view.text and view._index == 0
    assert all(len(text) <= 2048 for text in rendered)


def test_real_update_checks_detect_versions_without_rendering_hidden_notes(kivy_app, monkeypatch):
    root = kivy_app.root
    popup = root.upgrade_popup
    monkeypatch.setattr(root, "ctl_version", "2.1.0")
    monkeypatch.setattr(root, "ctl_upd_text", "[3.0.0]\n" + "Controller notes\n" * 1000)
    monkeypatch.setattr(root, "fw_version", "2.1.0")
    monkeypatch.setattr(root, "fw_upd_text", "[4.0.0]\n" + "Firmware notes\n" * 1000)
    root.check_ctl_version()
    root.check_fw_version()
    assert kivy_app.ctl_has_update and kivy_app.fw_has_update
    assert root.ctl_version_new == "3.0.0" and root.fw_version_new == "4.0.0"
    assert popup.ctl_upd_text.body.text == popup.fw_upd_text.body.text == ""
    monkeypatch.setattr(root.controller, "executeCommand", Mock())
    root.open_update_popup()
    assert popup.ctl_upd_text.active and popup.fw_upd_text.active
    assert 0 < len(popup.ctl_upd_text.body.text) <= 2048
    assert 0 < len(popup.fw_upd_text.body.text) <= 2048
    root.close_update_popup()
    pump_frames(3, sleep=0.1)
    assert not popup.ctl_upd_text.active and not popup.fw_upd_text.active
    assert popup.ctl_upd_text.body.text == popup.fw_upd_text.body.text == ""
    root.controller.executeCommand.assert_not_called()


def test_refresh_clears_old_notes_without_fetching_on_ui_thread(kivy_app, monkeypatch):
    from carveracontroller import main

    root = kivy_app.root
    request = Mock()
    monkeypatch.setattr(main, "UrlRequest", request)
    root.upgrade_popup.ctl_upd_text.text = "Old controller notes"
    root.upgrade_popup.fw_upd_text.text = "Old firmware notes"
    root.check_for_updates()
    assert request.call_count == 2
    assert not root.ctl_version_checked and not root.fw_version_checked
    assert root.upgrade_popup.ctl_upd_text.text == root.upgrade_popup.fw_upd_text.text == ""
