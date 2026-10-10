"""Direct plot selection, complete contact pages and stale/cancelled workers."""

import threading
from unittest.mock import Mock

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_stock_target import target_card


@pytest.mark.parametrize("plane,expected", [("XY", (1, 2, 1)), ("XZ", (1, 1, 2)), ("YZ", (1, 1, 2))])
def test_cell_picker_inspection_and_approach(kivy_app, monkeypatch, tmp_path, plane, expected):
    ws, viewer, send, owner, review, sections, target = target_card(kivy_app, monkeypatch, tmp_path)
    cell = target.allowance
    try:
        baseline = viewer.machine_setup, owner.record
        target.calculate()
        wait(owner)
        sections.plane.text = plane
        sections.layer.text = "1"
        target.view_section()
        wait(owner)
        plot = target.plot
        plot.width = 420
        plot.draw()
        x, y, width, height = plot.frame
        assert plot.grid_shape == (4, 4, 4)
        assert not plot.select_at(x - 1, y)
        assert plot.select_at(x + width * 0.3, y + height * 0.6)
        assert cell.cell.text == ", ".join(str(v) for v in expected) and cell.expanded
        cell.calculate()
        assert owner.running and cell.inspect.disabled and cell.cell.disabled
        wait(owner)
        first = cell.result
        assert plot.selected is not None
        assert first.cell == expected and first.approach is None
        assert "Signed center distance" in cell.status.text
        assert not cell.cell.disabled and not cell.inspect.disabled
        cell.tool.text = "T2"
        assert plot.selected is None
        cell.calculate()
        wait(owner)
        assert cell.result.approach is not None and cell.rows
        assert "No holder geometry" in cell.details.text
        assert baseline == (viewer.machine_setup, owner.record)
        target.calculate()
        wait(owner)
        assert cell.result is None
        sections.plane.text = "XY" if plane != "XY" else "XZ"
        assert cell.result is None and plot.selected is None
        send.assert_not_called()
    finally:
        owner.dispose()


@pytest.mark.parametrize("mode", ["cancel", "refusal", "cell", "tool", "state", "target", "aba"])
def test_worker_delivery_preserves_prior_or_withholds_stale(kivy_app, monkeypatch, tmp_path, mode):
    import carveracontroller.desktop_stock_allowance as desktop

    ws, viewer, send, owner, review, sections, target = target_card(kivy_app, monkeypatch, tmp_path)
    target.calculate()
    wait(owner)
    cell = target.allowance
    cell.calculate()
    wait(owner)
    prior = cell.result
    real = desktop.inspect_target_cell
    entered, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        if mode == "refusal":
            raise ValueError("Complete budget exhausted; no partial witness")
        return real(*args, **kwargs)

    monkeypatch.setattr(desktop, "inspect_target_cell", blocked)
    try:
        cell.calculate()
        assert entered.wait(3)
        if mode == "cancel":
            owner.cancel()
        elif mode == "cell":
            cell.cell.text = "1, 1, 1"
        elif mode == "tool":
            cell.tool.text = "T2"
        elif mode == "state":
            target.variant.text = "Initial stock"
        elif mode == "target":
            target.translation.text = "1, 0, 0"
        elif mode == "aba":
            cell.cell.text = "1, 1, 1"
            cell.cell.text = "0, 0, 0"
        release.set()
        wait(owner)
        assert cell.result is prior if mode in ("cancel", "refusal") else cell.result is None
        assert not cell.cell.disabled and not owner.running
        if mode not in ("cancel", "refusal"):
            assert "withheld" in cell.status.text
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()


@pytest.mark.parametrize("width", [360, 800])
def test_allowance_layout_all_contact_pages_and_bad_indices(kivy_app, monkeypatch, tmp_path, width):
    ws, viewer, send, owner, review, sections, target = target_card(kivy_app, monkeypatch, tmp_path)
    popup = None
    try:
        target.calculate()
        wait(owner)
        card = target.allowance
        card.cell.text = "0, -1, 0"
        card.calculate()
        assert not owner.running and "nonnegative" in card.status.text
        card.cell.text = "99, 0, 0"
        card.calculate()
        wait(owner)
        assert card.result is None and "inside" in card.status.text
        card.cell.text = "1, 1, 0"
        card.tool.text = "T2"
        card.calculate()
        wait(owner)
        assert card.result.approach
        card.rows = tuple(f"retained contact {i}" for i in range(130))
        card.page = 0
        card.render_page()
        assert len(card.contacts.values) == 64 and card.previous.disabled
        card.change_page(1)
        assert card.contacts.values[0].startswith("65.") and not card.next.disabled
        card.change_page(1)
        assert len(card.contacts.values) == 2 and card.next.disabled
        card.change_page(-9)
        assert card.page == 0
        target.content.remove_widget(card)
        card.toggle()
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(card)
        popup = Popup(title="Cell allowance", content=scroll, size_hint=(None, None), size=(width, 800))
        popup.open()
        pump_frames(8)
        assert card.cell.right <= card.right + 1 and card.clearance.right <= card.right + 1
        popup.export_to_png(str(tmp_path / f"cell-allowance-{width}.png"))
        send.assert_not_called()
    finally:
        if popup:
            popup.dismiss()
        owner.dispose()
