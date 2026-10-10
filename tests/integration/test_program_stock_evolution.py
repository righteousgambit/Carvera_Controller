"""Ordered material controls, worker lifetime and detached source-linked inspection."""

import threading
from unittest.mock import Mock

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_program_joint_clearance import configured
from tests.unit.test_program_stock_evolution import stock_example


@pytest.mark.parametrize("width", [360, 800])
def test_ordered_worker_inspection_exchange_and_current_scene_preserved(kivy_app, monkeypatch, tmp_path, width):
    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    source, offsets, expected, captures = stock_example(ball=True)
    parent = owner.clearance_panel.program_review
    card = parent.surfaces
    parent.content.remove_widget(card)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(card)
    popup = Popup(title="Ordered material review", content=scroll, size_hint=(None, None), size=(width, 850))
    path = tmp_path / "ordered.cvsurfacereview"
    monkeypatch.setattr(ws, "choose_profile_file", lambda cb, **kw: cb(str(path)))
    monkeypatch.setattr(ws, "choose_asset_file", lambda cb, **kw: cb(str(path)))
    monkeypatch.setattr(parent, "inputs", lambda selected: (source, captures, offsets, 1, len(source.lines)))
    try:
        card.toggle()
        popup.open()
        card.stock_mode.text = "Initial CAD + ordered stock"
        card.stock_resolution.text = "0.5"
        parent.review(False, surfaces=True, grouped=True)
        assert owner.running
        assert card.stock_mode.disabled and card.stock_resolution.disabled
        wait(owner)
        assert card.result.stock_evolution.steps == expected.stock_evolution.steps
        assert not card.stock_mode.disabled and not card.stock_resolution.disabled
        assert "Ordered stock:" in card.note.text
        index = next(i for i, (kind, row) in enumerate(card.rows) if kind == "stock history" and row.line == 6)
        card.page = index // 64
        card.refresh()
        card.choice.text = card.choice.values[index % 64]
        pump_frames(5)
        assert "remaining 0.25 mm³" in card.detail.text and "cutter" in card.detail.text
        assert "declared work frame" in card.detail.text and "empty cells do not prove" in card.detail.text
        assert card.plot.geometry
        inspect = Mock()
        monkeypatch.setattr(ws.operation_panel, "inspect_line", inspect)
        monkeypatch.setattr(ws.operation_panel, "program", ProgramOperations.from_text(source.text))
        card.inspect_source()
        inspect.assert_called_once_with(6, seek=True)
        setup, record = viewer.machine_setup, owner.record
        card.save_review()
        wait(owner)
        raw = path.read_bytes()
        parent.clear_result()
        card.load_review()
        wait(owner)
        assert card.result.stock_evolution.steps == expected.stock_evolution.steps
        assert card.stock_mode.text == "Initial CAD + ordered stock" and card.stock_resolution.value() == 0.5
        assert viewer.machine_setup is setup and owner.record is record
        card.save_review()
        wait(owner)
        assert path.read_bytes() == raw
        card.page = index // 64
        card.refresh()
        card.choice.text = card.choice.values[index % 64]
        pump_frames(5)
        scroll.scroll_to(card.plot, animate=False)
        pump_frames(5)
        assert card.plot.right <= card.right + 1 and card.detail.right <= card.right + 1
        popup.export_to_png(str(tmp_path / f"ordered-stock-{width}.png"))
        send.assert_not_called()
    finally:
        popup.dismiss()
        owner.dispose()


@pytest.mark.parametrize("cancel", [False, True])
def test_replacement_refusal_or_cancel_preserves_prior_complete_review(kivy_app, monkeypatch, cancel):
    import carveracontroller.desktop_program_clearance as desktop

    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    source, offsets, prior, captures = stock_example()
    parent = owner.clearance_panel.program_review
    parent.retained_inputs = (source, offsets)
    parent.show_result(prior.body_review)
    parent.surfaces.show(prior)
    monkeypatch.setattr(parent, "inputs", lambda selected: (source, captures, offsets, 1, len(source.lines)))
    entered, release = threading.Event(), threading.Event()

    def refused(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        if cancel:
            assert kwargs["cancelled"]()
            raise InterruptedError("Cancelled new ordered report")
        raise ValueError("Ordered stock exhausted shared work budget; no partial report")

    monkeypatch.setattr(desktop, "review_program_surfaces", refused)
    try:
        parent.review(False, surfaces=True, grouped=True)
        assert entered.wait(2)
        assert parent.result is prior.body_review and parent.surfaces.result is prior
        assert parent.surfaces.save_action.disabled
        if cancel:
            owner.cancel()
        release.set()
        wait(owner)
        assert parent.result is prior.body_review and parent.surfaces.result is prior
        assert parent.retained_inputs == (source, offsets)
        assert not parent.surfaces.save_action.disabled
        assert ("cancelled" if cancel else "work budget") in parent.note.text
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()
