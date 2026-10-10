"""Rendered portable triangle/solid replay, stale picker and cancelled worker controls."""

import json
import threading
from unittest.mock import Mock

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_program_joint_clearance import configured
from tests.unit.test_program_joint_clearance import program


@pytest.mark.parametrize("width", [360, 800])
def test_save_open_recompute_resave_preserve_active_scene_and_responsive_controls(
    kivy_app, monkeypatch, tmp_path, width
):
    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    parent = owner.clearance_panel.program_review
    card = parent.surfaces
    parent.content.remove_widget(card)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(card)
    popup = Popup(title="Portable surface review", content=scroll, size_hint=(None, None), size=(width, 850))
    path = tmp_path / "retained.cvsurfacereview"
    monkeypatch.setattr(ws, "choose_profile_file", lambda cb, **kw: cb(str(path)))
    monkeypatch.setattr(ws, "choose_asset_file", lambda cb, **kw: cb(str(path)))
    try:
        card.toggle()
        popup.open()
        pump_frames(5)
        assert card.save_action.disabled
        parent.review(False, surfaces=True)
        wait(owner)
        assert card.result and not card.save_action.disabled, parent.note.text
        original = card.result
        card.save_review()
        assert owner.running and card.save_action.disabled and card.load_action.disabled
        wait(owner)
        assert path.exists() and "Saved and recomputed" in card.exchange_status.text, card.exchange_status.text
        raw = path.read_bytes()
        current = program("G1 X12")
        monkeypatch.setattr(ws.operation_panel, "program", current)
        monkeypatch.setattr(viewer, "machine_profile", None)
        monkeypatch.setattr(viewer, "library_tool_table_mm", {})
        setup, record = viewer.machine_setup, owner.record
        parent.clear_result()
        card.load_review()
        wait(owner)
        assert card.result and card.result.body_review.program_hash == original.body_review.program_hash, (
            card.exchange_status.text
        )
        assert "Opened and recomputed detached surface review" in card.exchange_status.text
        assert viewer.machine_profile is None and viewer.library_tool_table_mm == {}
        assert viewer.machine_setup is setup and owner.record is record and ws.operation_panel.program is current
        assert (
            card.result.contacts == original.contacts
            and card.result.occupancy == original.occupancy
            and card.result.gaps == original.gaps
        )
        inspect = Mock()
        monkeypatch.setattr(ws.operation_panel, "inspect_line", inspect)
        card.inspect_source()
        inspect.assert_not_called()
        assert "withheld" in card.note.text
        monkeypatch.setattr(ws.operation_panel, "program", program("G1 X11"))
        card.inspect_source()
        inspect.assert_called_once_with(card.selected.line, seek=True)
        assert "withheld" not in card.note.text and "possible triangle contacts" in card.note.text
        card.save_review()
        wait(owner)
        assert "Saved and recomputed" in card.exchange_status.text and path.read_bytes() == raw
        pump_frames(6)
        scroll.scroll_to(card.save_action, animate=False)
        pump_frames(4)
        assert card.save_action.right <= card.right + 1 and card.load_action.right <= card.right + 1
        assert card.save_action.width >= 145 and not card.save_action.disabled and not card.load_action.disabled
        popup.export_to_png(str(tmp_path / f"surface-replay-{width}.png"))
        send.assert_not_called()
    finally:
        popup.dismiss()
        owner.dispose()


def test_delayed_picker_cannot_save_or_load_after_generation_change(kivy_app, monkeypatch, tmp_path):
    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    parent = owner.clearance_panel.program_review
    card = parent.surfaces
    callbacks = []
    monkeypatch.setattr(ws, "choose_profile_file", lambda cb, **kw: callbacks.append(cb))
    monkeypatch.setattr(ws, "choose_asset_file", lambda cb, **kw: callbacks.append(cb))
    parent.review(False, surfaces=True)
    wait(owner)
    card.save_review()
    owner._invalidate()
    path = tmp_path / "never-created"
    callbacks.pop()(str(path))
    assert "changed while choosing" in card.exchange_status.text and not path.exists()
    card.load_review()
    owner._invalidate()
    callbacks.pop()(str(path))
    assert "changed while choosing" in card.exchange_status.text and not owner.running
    send.assert_not_called()
    owner.dispose()


def test_invalid_or_cancelled_load_preserves_previous_surface_review(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.machine.program_surface_archive as archive

    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    parent = owner.clearance_panel.program_review
    card = parent.surfaces
    parent.review(False, surfaces=True)
    wait(owner)
    previous = card.result
    path = tmp_path / "invalid.cvsurfacereview"
    path.write_text(json.dumps({"schema": True}))
    monkeypatch.setattr(ws, "choose_asset_file", lambda cb, **kw: cb(str(path)))
    card.load_review()
    wait(owner)
    assert card.result is previous and "schema" in card.exchange_status.text
    entered, release = threading.Event(), threading.Event()

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        assert kwargs["cancelled"]()
        raise InterruptedError("cancelled")

    monkeypatch.setattr(archive, "load_surface_review", delayed)
    card.load_review()
    assert entered.wait(2)
    owner.cancel()
    release.set()
    wait(owner)
    assert card.result is previous and "cancelled" in card.exchange_status.text
    assert not card.save_action.disabled and not card.load_action.disabled
    send.assert_not_called()
    owner.dispose()
