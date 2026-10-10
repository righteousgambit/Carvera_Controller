"""Full generated-machine worker, contact navigation, stale delivery and layout."""

import threading

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_stock_generated_finish import card_example


def prepared(kivy_app, monkeypatch, tmp_path):
    result = card_example(kivy_app, monkeypatch, tmp_path)
    from dataclasses import replace

    from carveracontroller.machine.surface_motion import SurfaceMesh
    from tests.unit.test_stock_solid import box

    surfaces = result[4].surfaces
    parent = surfaces.result
    rows = {n: dict(m) for n, m in parent.meshes.items()}
    for name, lo, hi in (("Rigid A", (10, 10, 10), (12, 12, 12)), ("Rigid B", (11, 11, 11), (13, 13, 13))):
        parent.body_review.records[2]["collision_bodies"].append(
            {"name": name, "frame": "world", "joint_count": 0, "minimum_mm": lo, "maximum_mm": hi}
        )
        rows[2][name] = SurfaceMesh.create(box(lo, hi))
    surfaces.result = replace(parent, meshes=rows)
    result[-1].calculate()
    wait(result[3])
    return (*result, result[-1].machine_review)


def test_whole_path_geometry_navigation_preserves_program_profiles_and_material(kivy_app, monkeypatch, tmp_path):
    ws, viewer, send, owner, sections, target, generated, card = prepared(kivy_app, monkeypatch, tmp_path)
    try:
        before = (
            viewer.machine_setup,
            owner.record,
            sections.surfaces.result,
            ws.operation_panel.program,
            generated.result,
        )
        card.calculate()
        assert owner.running and card.review.disabled and not card.cancel_button.disabled
        wait(owner)
        result = card.result
        assert result is not None and result.plan is generated.result
        assert len(result.scene.body_review.segments) == len(generated.result.moves)
        assert card.progress_event is None and "Complete:" in card.status.text
        assert any(kind == "group" for kind, _ in card.rows)
        while not card.next.disabled:
            card.next.dispatch("on_release")
        card.choice.text = card.choice.values[-1]
        kind, row = card.rows[-1]
        assert generated.plot.selected == row.segment_index
        assert generated.detail.text.startswith(f"Move {row.segment_index + 1}:")
        card.page = 0
        card.render_page()
        index, group = next((i, r) for i, (k, r) in enumerate(card.rows) if k == "group")
        card.page = index // 64
        card.render_page()
        card.choice.text = card.choice.values[index % 64]
        assert card.plot.geometry and "Exact contact interval" in card.detail.text
        card.pair.text = "999999"
        assert not card.plot.geometry and "outside" in card.detail.text
        assert before == (
            viewer.machine_setup,
            owner.record,
            sections.surfaces.result,
            ws.operation_panel.program,
            generated.result,
        )
        generated.stepover.text = "0.25"
        assert card.result is None and generated.result is None and not card.rows
        send.assert_not_called()
    finally:
        owner.dispose()


@pytest.mark.parametrize("mode", ["cancel", "refusal", "target", "parameter", "parent"])
def test_full_machine_cancel_refusal_and_stale_delivery(kivy_app, monkeypatch, tmp_path, mode):
    from dataclasses import replace

    import carveracontroller.desktop_stock_generated_machine as desktop

    ws, viewer, send, owner, sections, target, generated, card = prepared(kivy_app, monkeypatch, tmp_path)
    card.calculate()
    wait(owner)
    prior = card.result
    assert prior is not None
    entered, release = threading.Event(), threading.Event()
    real = desktop.review_generated_finish

    def blocked(*args, **kwargs):
        kwargs["progress"]("Complete moving-machine CAD/solids", 3, 20)
        entered.set()
        assert release.wait(8)
        if mode == "refusal":
            raise ValueError("Complete shared result budget exhausted")
        return real(*args, **kwargs)

    monkeypatch.setattr(desktop, "review_generated_finish", blocked)
    try:
        card.calculate()
        assert entered.wait(3)
        card.tick()
        assert "3/20 work items" in card.status.text
        if mode == "cancel":
            card.cancel_button.dispatch("on_release")
        elif mode == "target":
            target.translation.text = "1, 0, 0"
            target.translation.text = "0, 0, 0"
        elif mode == "parameter":
            generated.stepover.text = "0.25"
            generated.stepover.text = "0.5"
        elif mode == "parent":
            sections.surfaces.result = replace(sections.surfaces.result)
        release.set()
        wait(owner)
        if mode in ("cancel", "refusal", "parent"):
            assert card.result is prior
        else:
            assert card.result is None
        if mode in ("target", "parameter", "parent"):
            assert "withheld" in card.status.text
        assert card.progress_event is None and not owner.running
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()


@pytest.mark.parametrize("width", [360, 800])
def test_generated_machine_layout_all_actions_and_witness(kivy_app, monkeypatch, tmp_path, width):
    ws, viewer, send, owner, sections, target, generated, card = prepared(kivy_app, monkeypatch, tmp_path)
    popup = None
    try:
        card.calculate()
        wait(owner)
        assert card.result is not None
        generated.content.remove_widget(card)
        card.toggle()
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(card)
        popup = Popup(title="Machine clearance", content=scroll, size_hint=(None, None), size=(width, 850))
        popup.open()
        pump_frames(8)
        for button in (card.review, card.cancel_button, card.previous, card.next):
            button.texture_update()
            assert button.texture_size[0] <= button.width - 10 and button.right <= card.right + 1
        assert card.plot.geometry
        scroll.scroll_to(card.plot, animate=False)
        pump_frames(5)
        popup.export_to_png(str(tmp_path / f"generated-machine-{width}.png"))
        send.assert_not_called()
    finally:
        if popup:
            popup.dismiss()
        owner.dispose()
