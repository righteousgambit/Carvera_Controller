"""Cached layer interaction and detached finishing comparison worker ergonomics."""

import threading
from dataclasses import replace
from unittest.mock import Mock

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_program_joint_clearance import configured
from tests.unit.test_stock_finishing import finishing_example


def prepared(kivy_app, monkeypatch):
    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    review = finishing_example()
    surfaces = owner.clearance_panel.program_review.surfaces
    surfaces.show(review)
    sections = surfaces.stock_sections
    index = next(i for i, (kind, r) in enumerate(surfaces.rows) if kind == "stock history" and r.segment_index == 0)
    surfaces.page = index // 64
    surfaces.refresh()
    surfaces.choice.text = surfaces.choice.values[index % 64]
    surfaces.select()
    return ws, viewer, send, owner, review, sections


@pytest.mark.parametrize("width", [360, 800])
def test_layer_cache_finish_worker_contacts_and_scene_preserved(kivy_app, monkeypatch, tmp_path, width):
    import carveracontroller.desktop_stock_sections as desktop

    ws, viewer, send, owner, review, sections = prepared(kivy_app, monkeypatch)
    called = Mock(wraps=desktop.reconstruct_stock_move)
    monkeypatch.setattr(desktop, "reconstruct_stock_move", called)
    popup = None
    try:
        sections.layer.text = "0"
        sections.calculate()
        wait(owner)
        state = sections.state
        assert called.call_count == 1 and state is not None
        assert not sections.upper_layer.disabled
        sections.upper_layer.trigger_action(0)
        wait(owner)
        assert sections.plot.section.layer == 1 and called.call_count == 1
        sections.plane.text = "XZ"
        sections.calculate()
        wait(owner)
        assert sections.plot.section.plane == "XZ" and sections.state is state and called.call_count == 1
        card = sections.finishing
        assert tuple(card.tool.values) == ("T1", "T2") and not card.compare.disabled
        card.tool.text = "T2"
        card.end_line.text = "6"
        setup, record = viewer.machine_setup, owner.record
        card.calculate()
        assert owner.running and card.tool.disabled and card.end_line.disabled and card.compare.disabled
        wait(owner)
        assert card.result.planned.remaining_mm3 == 0.25 and card.result.candidate.remaining_mm3 == 0
        assert "0.25 mm³ extra removal" in card.status.text
        assert sections.state is state and viewer.machine_setup is setup and owner.record is record
        assert called.call_count == 1 and not card.tool.disabled
        navigate = Mock()
        monkeypatch.setattr(ws.operation_panel, "inspect_line", navigate)
        monkeypatch.setattr(ws.operation_panel, "program", Mock(file_hash=review.body_review.program_hash))
        card.inspect_source()
        navigate.assert_called_once_with(6, seek=True)
        monkeypatch.setattr(ws.operation_panel, "program", ProgramOperations.from_text("G21"))
        card.inspect_source()
        assert navigate.call_count == 1 and "differs" in card.status.text
        sections.content.remove_widget(card)
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(card)
        popup = Popup(title="Compare finishing tools", content=scroll, size_hint=(None, None), size=(width, 900))
        card.toggle()
        popup.open()
        # Restore summary without recomputing source or changing the stock state.
        card.calculate()
        wait(owner)
        pump_frames(8)
        scroll.scroll_to(card.status, animate=False)
        pump_frames(5)
        assert card.status.right <= card.right + 1 and card.contacts.right <= card.right + 1
        popup.export_to_png(str(tmp_path / f"stock-finish-{width}.png"))
        send.assert_not_called()
    finally:
        if popup:
            popup.dismiss()
        owner.dispose()


@pytest.mark.parametrize("mode", ["cancel", "budget", "selection", "options", "result"])
def test_finish_replacement_preserves_prior_or_withholds_stale(kivy_app, monkeypatch, mode):
    import carveracontroller.desktop_stock_finish as desktop

    ws, viewer, send, owner, review, sections = prepared(kivy_app, monkeypatch)
    card = sections.finishing
    card.tool.text = "T2"
    card.end_line.text = "6"
    card.calculate()
    wait(owner)
    prior = card.result
    assert prior is not None
    entered, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        if mode == "budget":
            raise ValueError("Finishing comparison exhausted shared cell-work budget")
        return prior

    monkeypatch.setattr(desktop, "compare_stock_continuation", blocked)
    try:
        card.calculate()
        assert entered.wait(2)
        if mode == "cancel":
            owner.cancel()
        elif mode == "selection":
            sections.set_target(review.stock_evolution.steps[1])
        elif mode == "options":
            card.tool.text = "T1"
        elif mode == "result":
            sections.surfaces.show(replace(review))
        release.set()
        wait(owner)
        assert card.result is (prior if mode in ("cancel", "budget") else None)
        assert not card.tool.disabled and not card.end_line.disabled
        assert (
            "cancelled" if mode == "cancel" else "work budget" if mode == "budget" else "withheld"
        ) in card.status.text
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()
