"""Generated path/replay UI, all records, stale guards and responsive rendering."""

import threading

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_stock_allowance_summary import prepared


def card_example(kivy_app, monkeypatch, tmp_path):
    ws, viewer, send, owner, sections, target, _ = prepared(kivy_app, monkeypatch, tmp_path)
    return ws, viewer, send, owner, sections, target, target.generated_finish


@pytest.mark.parametrize("plane", ["XY", "XZ", "YZ"])
def test_complete_generated_path_planes_stock_and_navigation_preserve_live_context(
    kivy_app, monkeypatch, tmp_path, plane
):
    ws, viewer, send, owner, sections, target, card = card_example(kivy_app, monkeypatch, tmp_path)
    try:
        before = viewer.machine_setup, owner.record, sections.surfaces.result, ws.operation_panel.program
        assert tuple(card.tool.values) == ("T2",)
        card.calculate()
        assert owner.running and card.generate.disabled and not card.cancel_button.disabled
        wait(owner)
        plan = card.result
        assert plan is not None and len(plan.states) == 2 and plan.moves
        assert card.progress_event is None and "Complete:" in card.status.text
        assert card.plot.plan is plan and card.page == 0
        card.plane.text = plane
        assert card.result is plan and card.plot.plane == plane
        card.state.text = "Initial stock"
        card.view_stock()
        wait(owner)
        assert card.stock_plot.sections[0].plane == plane and card.stock_plot.grid_shape == (4, 4, 4)
        assert "Missing target" in card.metrics.text and "Axial allowance" in card.detail.text
        while not card.next.disabled:
            card.next.dispatch("on_release")
        assert card.moves.values[-1].startswith(f"{len(plan.moves)}.")
        assert before == (viewer.machine_setup, owner.record, sections.surfaces.result, ws.operation_panel.program)
        target.calculate()
        wait(owner)
        assert card.result is None and card.plot.plan is None and not card.stock_plot.sections
        send.assert_not_called()
    finally:
        owner.dispose()


@pytest.mark.parametrize("mode", ["cancel", "refusal", "target", "aba", "parameter"])
def test_generator_cancel_refusal_and_stale_delivery(kivy_app, monkeypatch, tmp_path, mode):
    import carveracontroller.desktop_stock_generated_finish as desktop

    ws, viewer, send, owner, sections, target, card = card_example(kivy_app, monkeypatch, tmp_path)
    card.calculate()
    wait(owner)
    prior = card.result
    entered, release = threading.Event(), threading.Event()
    real = desktop.generate_stock_finish

    def blocked(*args, **kwargs):
        kwargs["progress"]("Replay Initial stock", 3, 20)
        entered.set()
        assert release.wait(8)
        if mode == "refusal":
            raise ValueError("Complete move budget exhausted")
        return real(*args, **kwargs)

    monkeypatch.setattr(desktop, "generate_stock_finish", blocked)
    try:
        card.calculate()
        assert entered.wait(3)
        card.tick()
        assert "3/20 work items" in card.status.text
        if mode == "cancel":
            card.cancel_button.dispatch("on_release")
            card.tick()
            assert "Cancel requested" in card.status.text
        elif mode in ("target", "aba"):
            target.translation.text = "1, 0, 0"
            if mode == "aba":
                target.translation.text = "0, 0, 0"
        elif mode == "parameter":
            card.stepdown.text = "0.5"
            card.stepdown.text = "0.25"
        release.set()
        wait(owner)
        assert card.result is prior if mode in ("cancel", "refusal") else card.result is None
        if mode in ("target", "aba", "parameter"):
            assert "withheld" in card.status.text
        assert card.progress_event is None and not owner.running
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()


@pytest.mark.parametrize("width", [360, 800])
def test_generated_path_layout_fits_and_contains_all_actions(kivy_app, monkeypatch, tmp_path, width):
    ws, viewer, send, owner, sections, target, card = card_example(kivy_app, monkeypatch, tmp_path)
    popup = None
    try:
        card.calculate()
        wait(owner)
        assert card.result is not None
        target.content.remove_widget(card)
        card.toggle()
        card.after_card.toggle()
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(card)
        popup = Popup(title="Finishing preview", content=scroll, size_hint=(None, None), size=(width, 850))
        popup.open()
        pump_frames(8)
        for button in (
            card.generate,
            card.cancel_button,
            card.previous,
            card.next,
            card.section,
            card.contact_previous,
            card.contact_next,
        ):
            button.texture_update()
            assert button.texture_size[0] <= button.width - 10 and button.right <= card.right + 1
        assert card.plot.height >= 150
        scroll.scroll_to(card.plot, animate=False)
        pump_frames(5)
        popup.export_to_png(str(tmp_path / f"generated-finish-{width}.png"))
        send.assert_not_called()
    finally:
        if popup:
            popup.dismiss()
        owner.dispose()


def test_all_four_states_and_preexisting_missing_material_stay_distinct(kivy_app, monkeypatch, tmp_path):
    ws, viewer, send, owner, sections, target, card = card_example(kivy_app, monkeypatch, tmp_path)
    try:
        sections.finishing.tool.text = "T2"
        sections.finishing.end_line.text = "6"
        sections.finishing.calculate()
        wait(owner)
        target.calculate()
        wait(owner)
        analysis = target.result
        card.calculate()
        wait(owner)
        assert len(card.result.states) == len(analysis.fits) == 4
        for label, state in card.result.states.items():
            assert state.before is analysis.fits[label]
            assert state.after.missing_mm3 == state.before.missing_mm3
        assert card.result.states["T2 continuation"].after.missing_mm3 == 1
        send.assert_not_called()
    finally:
        owner.dispose()


def test_complete_target_contacts_page_and_navigate_exact_generated_move(kivy_app, monkeypatch, tmp_path):
    from tests.unit.test_stock_generated_finish import holder_example

    ws, viewer, send, owner, sections, target, card = card_example(kivy_app, monkeypatch, tmp_path)
    try:
        target.result = holder_example(tmp_path)
        card.set_busy(False)
        card.tool.text = "T1"
        card.stepover.text = "0.2"
        card.calculate()
        wait(owner)
        assert card.result is not None and len(card.result.target_contacts) > 64
        card.state.text = "Initial stock"
        records = card.records()
        card.change_contact_page(1)
        assert card.contacts.values[0].startswith("65.")
        selected = records[64][1]
        assert card.plot.selected == selected.move
        assert card.moves.text.startswith(f"{selected.move + 1}.")
        assert "original face" in card.witness.text
        while not card.contact_next.disabled:
            card.change_contact_page(1)
        assert card.contacts.values[-1].startswith(f"{len(records)}.")
        send.assert_not_called()
    finally:
        owner.dispose()


def test_maximum_path_plot_selection_reuses_geometry_and_keeps_complete_lines(kivy_app, monkeypatch, tmp_path):
    import json
    import time
    from dataclasses import replace

    from kivy.graphics import Mesh

    ws, viewer, send, owner, sections, target, card = card_example(kivy_app, monkeypatch, tmp_path)
    try:
        card.calculate()
        wait(owner)
        plan = card.result
        # Rendering-capacity control only: repeated source moves are synthetic,
        # not a new simulated material or toolpath qualification claim.
        moves = (plan.moves * (20000 // len(plan.moves) + 1))[:20000]
        card.plot.plan = replace(plan, moves=moves)
        card.plot.size = (800, 260)
        card.plot.draw()
        original = tuple(card.plot.canvas.children)
        meshes = [c for c in original if isinstance(c, Mesh)]
        assert len(meshes) == 2 and sum(len(m.indices) for m in meshes) == 40000
        start = time.perf_counter()
        for index in range(100):
            card.plot.selected = index * 199
            card.plot.draw()
        elapsed = time.perf_counter() - start
        assert tuple(card.plot.canvas.children) == original
        assert len(card.plot.highlight.points) == 4
        (tmp_path / "plot-selection-timing.json").write_text(
            json.dumps(
                {
                    "moves": 20000,
                    "selections": 100,
                    "elapsed_seconds": elapsed,
                    "qualification": "source rendering-capacity control; synthetic repeated move sequence, no installed latency claim",
                }
            )
            + "\n"
        )
        card.plot.plane = "XZ"
        card.plot.draw()
        assert tuple(card.plot.canvas.children) != original
        send.assert_not_called()
    finally:
        owner.dispose()
