"""All-state allowance delivery, worst-cell navigation and worker lifecycle."""

import threading

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_stock_target import target_card


def prepared(kivy_app, monkeypatch, tmp_path):
    ws, viewer, send, owner, review, sections, target = target_card(kivy_app, monkeypatch, tmp_path)
    target.calculate()
    wait(owner)
    return ws, viewer, send, owner, sections, target, target.allowance_summary


@pytest.mark.parametrize("plane", ["XY", "XZ", "YZ"])
def test_all_states_and_worst_cell_navigation_preserve_setup(kivy_app, monkeypatch, tmp_path, plane):
    ws, viewer, send, owner, sections, target, card = prepared(kivy_app, monkeypatch, tmp_path)
    try:
        baseline = viewer.machine_setup, owner.record
        sections.finishing.tool.text = "T2"
        sections.finishing.end_line.text = "6"
        sections.finishing.calculate()
        wait(owner)
        target.calculate()
        wait(owner)
        card.calculate()
        assert owner.running and card.calculate_button.disabled
        wait(owner)
        assert card.result.cell_work == 256 and len(card.state.values) == 4
        assert card.progress_event is None and card.progress.snapshot()["status"] == "stopped"
        prior = card.result
        sections.plane.text = plane
        assert card.result is prior
        card.state.text = "T2 continuation"
        assert not card.missing.disabled
        peak = card.result.states[card.state.text].missing_peak
        card.show_peak("missing")
        wait(owner)
        assert target.variant.text == "T2 continuation"
        assert target.allowance.cell.text == ", ".join(str(v) for v in peak.cell)
        assert target.plot.sections[0].plane == plane and target.plot.selected is not None
        assert card.result is prior
        target.allowance.calculate()
        wait(owner)
        assert target.allowance.result.signed_distance_mm == peak.signed_center_distance_mm
        assert baseline == (viewer.machine_setup, owner.record)
        target.calculate()
        wait(owner)
        assert card.result is None
        send.assert_not_called()
    finally:
        owner.dispose()


@pytest.mark.parametrize("mode", ["cancel", "refusal", "target", "aba"])
def test_summary_retention_and_stale_delivery(kivy_app, monkeypatch, tmp_path, mode):
    import carveracontroller.desktop_stock_allowance_summary as desktop

    ws, viewer, send, owner, sections, target, card = prepared(kivy_app, monkeypatch, tmp_path)
    card.calculate()
    wait(owner)
    prior = card.result
    entered, release = threading.Event(), threading.Event()
    real = desktop.summarize_target_allowance

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        if mode == "refusal":
            raise ValueError("Complete shared distance budget exhausted")
        return real(*args, **kwargs)

    monkeypatch.setattr(desktop, "summarize_target_allowance", blocked)
    try:
        card.calculate()
        assert entered.wait(3)
        if mode == "cancel":
            owner.cancel()
        elif mode in ("target", "aba"):
            target.translation.text = "1, 0, 0"
            if mode == "aba":
                target.translation.text = "0, 0, 0"
        release.set()
        wait(owner)
        assert card.result is prior if mode in ("cancel", "refusal") else card.result is None
        assert card.progress_event is None and not owner.running
        if mode in ("target", "aba"):
            assert "withheld" in card.status.text
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()


@pytest.mark.parametrize("width", [360, 800])
def test_summary_compact_layout_and_continuing_progress(kivy_app, monkeypatch, tmp_path, width):
    ws, viewer, send, owner, sections, target, card = prepared(kivy_app, monkeypatch, tmp_path)
    popup = None
    try:
        card.calculate()
        wait(owner)
        assert "Complete:" in card.status.text and "Largest excess:" in card.metrics.text
        assert card.missing.disabled and not card.excess.disabled
        target.content.remove_widget(card)
        card.toggle()
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(card)
        popup = Popup(title="Whole-stock allowance", content=scroll, size_hint=(None, None), size=(width, 850))
        popup.open()
        pump_frames(8)
        assert card.excess.right <= card.right + 1 and card.missing.right <= card.right + 1
        for action in (card.calculate_button, card.excess, card.missing):
            assert action.texture_size[0] <= action.width - 12
        popup.export_to_png(str(tmp_path / f"allowance-summary-{width}.png"))
        send.assert_not_called()
    finally:
        if popup:
            popup.dismiss()
        owner.dispose()


def test_live_progress_reports_state_cells_and_cancellation_age(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_stock_allowance_summary as desktop

    ws, viewer, send, owner, sections, target, card = prepared(kivy_app, monkeypatch, tmp_path)
    entered, release = threading.Event(), threading.Event()
    real = desktop.summarize_target_allowance

    def blocked(*args, **kwargs):
        kwargs["progress"](32, 256, 3)
        entered.set()
        assert release.wait(8)
        return real(*args, **kwargs)

    monkeypatch.setattr(desktop, "summarize_target_allowance", blocked)
    try:
        card.calculate()
        assert entered.wait(3)
        card.tick_progress()
        assert "32/256 state-cell visits" in card.status.text and "3 center queries" in card.status.text
        owner.cancel()
        card.tick_progress()
        assert "Cancel requested" in card.status.text
        release.set()
        wait(owner)
        assert card.result is None and card.progress_event is None
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()
