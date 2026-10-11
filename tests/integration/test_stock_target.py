"""Part target picker, worker, grid visualization and stale/cancelled delivery."""

import threading
from unittest.mock import Mock

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_stock_finishing import prepared
from tests.unit.test_stock_solid import box, mesh


def target_card(kivy_app, monkeypatch, tmp_path):
    ws, viewer, send, owner, review, sections = prepared(kivy_app, monkeypatch)
    source = mesh(tmp_path, box((-0.5, -0.5, 0.5), (0.5, 0.5, 1.5)))
    card = sections.part_target
    card.path.text = source.source_path
    card.units.text = "mm"
    return ws, viewer, send, owner, review, sections, card


@pytest.mark.parametrize("width", [360, 800])
def test_target_worker_picker_fit_and_view_preserve_setup(kivy_app, monkeypatch, tmp_path, width):
    ws, viewer, send, owner, review, sections, card = target_card(kivy_app, monkeypatch, tmp_path)
    popup = None
    try:
        picker = Mock()
        monkeypatch.setattr(ws, "choose_asset_file", picker)
        card.pick.trigger_action(0)
        assert picker.call_args.kwargs["suffixes"] == (".stl",)
        picker.call_args.args[0](card.path.text)
        baseline = viewer.machine_setup, owner.record
        card.calculate()
        assert owner.running and card.path.disabled and card.units.disabled and card.compare.disabled
        wait(owner)
        target, first = card.target, card.result
        assert first is not None and first.target_grid_mm3 == 1
        assert first.fits["After selected move"].excess_mm3 == 7
        assert not card.path.disabled and "7" in card.status.text and card.reload.disabled is False
        assert baseline == (viewer.machine_setup, owner.record)
        cached = sections.state
        sections.finishing.tool.text = "T2"
        sections.finishing.end_line.text = "6"
        sections.finishing.calculate()
        wait(owner)
        assert card.result is None and card.target is target
        assert "cleared" in card.status.text
        card.calculate()
        wait(owner)
        assert card.target is target and sections.state is cached
        assert card.result.fits["T2 continuation"].missing_mm3 == 1
        assert card.result.fits["Planned continuation"].missing_mm3 == 1
        card.variant.text = "T2 continuation"
        sections.layer.text = "1"
        card.view_section()
        wait(owner)
        assert card.plot.sections and card.plot.sections[2].remaining
        assert card.plot.sections[1].remaining == ()
        sections.plane.text = "XZ"
        assert card.plot.sections == () and card.result is not None
        card.view_section()
        wait(owner)
        assert card.plot.sections[0].plane == "XZ"
        sections.content.remove_widget(card)
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(card)
        popup = Popup(title="Part target comparison", content=scroll, size_hint=(None, None), size=(width, 950))
        card.toggle()
        popup.open()
        pump_frames(8)
        scroll.scroll_to(card.plot, animate=False)
        pump_frames(5)
        assert card.plot.right <= card.right + 1 and card.path.right <= card.right + 1
        popup.export_to_png(str(tmp_path / f"part-target-{width}.png"))
        send.assert_not_called()
    finally:
        if popup:
            popup.dismiss()
        owner.dispose()


@pytest.mark.parametrize(
    "mode", ["cancel", "refusal", "path", "units", "placement", "selection", "comparison", "review"]
)
def test_target_replacement_and_changed_selection_controls(kivy_app, monkeypatch, tmp_path, mode):
    import carveracontroller.desktop_stock_target as desktop

    ws, viewer, send, owner, review, sections, card = target_card(kivy_app, monkeypatch, tmp_path)
    card.calculate()
    wait(owner)
    prior = card.result
    assert prior is not None
    entered, release = threading.Event(), threading.Event()
    real = desktop.analyze_stock_target

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        if mode == "refusal":
            raise ValueError("Target comparison exhausted complete shared budget")
        return real(*args, **kwargs)

    monkeypatch.setattr(desktop, "analyze_stock_target", blocked)
    try:
        card.calculate()
        assert entered.wait(3)
        if mode == "cancel":
            owner.cancel()
        elif mode == "path":
            card.path.text = "changed.stl"
        elif mode == "units":
            card.units.text = "inch"
        elif mode == "placement":
            card.translation.text = "1, 0, 0"
        elif mode == "selection":
            sections.set_target(
                next(r for kind, r in sections.surfaces.rows if kind == "stock history" and r.segment_index == 1)
            )
        elif mode == "comparison":
            sections.finishing.invalidate()
        elif mode == "review":
            sections.surfaces.clear()
        release.set()
        wait(owner)
        if mode in ("cancel", "refusal"):
            assert card.result is prior
        else:
            assert card.result is None
            if mode == "selection":
                sections.set_target(None)
                assert card.target is None and "No retained" in card.scope.text
        assert not card.path.disabled and not owner.running
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()


def test_target_units_required_bad_inputs_and_explicit_reload(kivy_app, monkeypatch, tmp_path):
    ws, viewer, send, owner, review, sections, card = target_card(kivy_app, monkeypatch, tmp_path)
    try:
        card.units.text = "Choose source units"
        card.calculate()
        assert not owner.running and "explicitly" in card.status.text
        card.units.text = "mm"
        card.translation.text = "0, 0"
        card.calculate()
        assert not owner.running and "needs" in card.status.text
        card.translation.text = "0, 0, 0"
        card.calculate()
        wait(owner)
        prior = card.target
        assert prior is not None
        # Reusing the detached target remains bound to its retained bytes.
        changed = mesh(tmp_path, box((-0.75, -0.75, 0.25), (0.75, 0.75, 1.75)))
        card.calculate()
        wait(owner)
        assert card.target is prior and card.result.target_grid_mm3 == 1
        card.calculate(reload=True)
        wait(owner)
        assert card.target.source_sha256 == changed.source_sha256 != prior.source_sha256
        assert card.result.target_grid_mm3 == 8
        card.translation.text = "nan, 0, 0"
        card.calculate()
        wait(owner)
        assert card.result is None and card.target is None
        assert "finite" in card.status.text
        send.assert_not_called()
    finally:
        owner.dispose()


def test_changed_then_restored_section_selection_withholds_stale_plot(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_stock_target as desktop

    ws, viewer, send, owner, review, sections, card = target_card(kivy_app, monkeypatch, tmp_path)
    card.calculate()
    wait(owner)
    sections.layer.text = "1"
    card.view_section()
    wait(owner)
    assert card.plot.sections
    real = desktop.target_sections
    entered, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        return real(*args, **kwargs)

    monkeypatch.setattr(desktop, "target_sections", blocked)
    try:
        card.view_section()
        assert entered.wait(3)
        card.variant.text = "Initial stock"
        card.variant.text = "After selected move"
        release.set()
        wait(owner)
        assert card.plot.sections == () and "withheld" in card.status.text
        assert card.result is not None
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()
