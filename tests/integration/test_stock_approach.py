"""Complete machine evidence, responsive witnesses and cancelled/stale workers."""

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
    cell = target.allowance
    cell.cell.text = "1, 1, 0"
    cell.tool.text = "T2"
    cell.calculate()
    wait(owner)
    return viewer, send, owner, target, cell.machine_approach


@pytest.mark.parametrize("width", [360, 800])
def test_review_results_witnesses_and_compact_layout(kivy_app, monkeypatch, tmp_path, width):
    viewer, send, owner, target, card = prepared(kivy_app, monkeypatch, tmp_path)
    popup = None
    # Independent complete overlapping / nested closed boxes exercise groups,
    # containment and missing geometry in the same real worker / plot inspector.
    from dataclasses import replace
    from types import MappingProxyType

    from carveracontroller.machine.surface_motion import SurfaceMesh
    from tests.unit.test_stock_solid import box

    parent = target.sections.surfaces.result
    meshes = {tool: dict(rows) for tool, rows in parent.meshes.items()}
    for name, lo, hi, surface in (
        ("Assembly A", (10, 10, 10), (12, 12, 12), True),
        ("Assembly B", (11, 11, 11), (13, 13, 13), True),
        ("Nested insert", (10.2, 10.2, 10.2), (10.4, 10.4, 10.4), True),
        ("Undeclared surface", (9, 9, 9), (14, 14, 14), False),
    ):
        parent.body_review.records[2]["collision_bodies"].append(
            {"name": name, "frame": "world", "joint_count": 0, "minimum_mm": lo, "maximum_mm": hi}
        )
        if surface:
            meshes[2][name] = SurfaceMesh.create(box(lo, hi))
    target.sections.surfaces.result = replace(parent, meshes=MappingProxyType(meshes))
    try:
        baseline = viewer.machine_setup, owner.record, target.sections.surfaces.result
        card.calculate()
        assert owner.running and card.calculate_button.disabled and card.cancel_button.disabled is False
        wait(owner)
        result = card.result
        assert result is not None and result.parent is baseline[2]
        assert {kind for kind, row in card.rows} == {"group", "solid", "rotating", "gap"}
        assert "declared bodies" in card.status.text
        assert card.progress_event is None and card.cancel_button.disabled
        assert not card.calculate_button.disabled
        assert "Selected initial stock replaced" in card.scope.text
        for option in card.choice.values:
            card.choice.text = option
            assert "Detached candidate insertion" in card.detail.text
            if card.plot.geometry:
                assert card.plot.height > 0 and len(card.plot.geometry[0]) == 3
        group_index = next((i for i, row in enumerate(card.rows) if row[0] == "group"), None)
        if group_index is not None:
            card.choice.text = card.choice.values[group_index]
            card.pair.text = "-1"
            assert "outside" in card.detail.text and not card.plot.geometry
            card.pair.text = "0"
            assert card.plot.geometry
        target.allowance.content.remove_widget(card)
        card.toggle()
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(card)
        popup = Popup(title="Machine approach", content=scroll, size_hint=(None, None), size=(width, 800))
        popup.open()
        pump_frames(8)
        for button in (card.calculate_button, card.cancel_button, card.previous, card.next):
            button.texture_update()
            assert button.texture_size[0] <= button.width
            assert button.right <= card.right + 1
        assert card.choice.right <= card.right + 1
        popup.export_to_png(str(tmp_path / f"machine-approach-{width}.png"))
        assert baseline == (viewer.machine_setup, owner.record, target.sections.surfaces.result)
        send.assert_not_called()
    finally:
        if popup:
            popup.dismiss()
        owner.dispose()


@pytest.mark.parametrize("mode", ["cancel", "refusal", "cell", "tool", "target", "aba"])
def test_stale_worker_withholds_detached_approach(kivy_app, monkeypatch, tmp_path, mode):
    import carveracontroller.desktop_stock_approach as desktop

    viewer, send, owner, target, card = prepared(kivy_app, monkeypatch, tmp_path)
    card.calculate()
    wait(owner)
    prior = card.result
    entered, release = threading.Event(), threading.Event()
    real = desktop.review_stock_approach

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        if mode == "refusal":
            raise ValueError("No partial machine review")
        return real(*args, **kwargs)

    monkeypatch.setattr(desktop, "review_stock_approach", blocked)
    try:
        card.calculate()
        assert entered.wait(3)
        if mode == "cancel":
            owner.cancel()
        elif mode == "cell":
            target.allowance.cell.text = "0, 0, 0"
        elif mode == "tool":
            target.allowance.tool.text = "T1"
        elif mode == "target":
            target.translation.text = "1, 0, 0"
        elif mode == "aba":
            target.allowance.cell.text = "0, 0, 0"
            target.allowance.cell.text = "1, 1, 0"
        release.set()
        wait(owner)
        assert card.result is prior if mode in ("cancel", "refusal") else card.result is None
        assert card.progress_event is None and not owner.running
        if mode not in ("cancel", "refusal"):
            assert "withheld" in card.status.text
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()
