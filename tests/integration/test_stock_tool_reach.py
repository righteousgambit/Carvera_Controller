"""Full tool-access comparison, retained paging, navigation and worker guards."""

import threading
import time

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_stock_allowance_summary import prepared


def wait_reach(panel):
    # Full exact target/stock studies can outlast small-fixture waits on a
    # shared host. This guards completion, not measured UI responsiveness.
    deadline = time.monotonic() + 60
    while panel.running and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not panel.running, panel.status.text


def reach_card(kivy_app, monkeypatch, tmp_path):
    ws, viewer, send, owner, sections, target, _ = prepared(kivy_app, monkeypatch, tmp_path)
    return ws, viewer, send, owner, sections, target, target.tool_reach


@pytest.mark.parametrize("plane", ["XY", "XZ", "YZ"])
def test_complete_states_tools_navigation_preserves_setup(kivy_app, monkeypatch, tmp_path, plane):
    ws, viewer, send, owner, sections, target, card = reach_card(kivy_app, monkeypatch, tmp_path)
    try:
        before = viewer.machine_setup, owner.record, sections.surfaces.result, ws.operation_panel.program
        card.calculate()
        assert owner.running and card.review.disabled and not card.cancel_button.disabled
        wait_reach(owner)
        study = card.result
        assert study is not None and study.tools == (1, 2) and len(study.states) == 2
        assert study.logical_outcomes == sum(len(rows) for tools in study.states.values() for rows in tools.values())
        assert card.progress_event is None and "Complete:" in card.status.text
        assert study.states["Initial stock"][1] and "target-face" in card.details.text
        card.tool.text = "T2"
        card.state.text = "Initial stock"
        selected = card.selected_row()
        sections.plane.text = plane
        assert card.result is study
        card.show_cell()
        wait(owner)
        assert target.variant.text == "Initial stock" and target.allowance.tool.text == "T2"
        assert target.allowance.cell.text == ", ".join(str(v) for v in selected.query.cell)
        assert target.plot.sections[0].plane == plane and target.plot.selected is not None
        assert card.result is study and before == (
            viewer.machine_setup,
            owner.record,
            sections.surfaces.result,
            ws.operation_panel.program,
        )
        target.calculate()
        wait(owner)
        assert card.result is None
        send.assert_not_called()
    finally:
        owner.dispose()


@pytest.mark.parametrize("mode", ["cancel", "refusal", "target", "aba", "tools"])
def test_cancellation_refusal_and_stale_inputs_preserve_accepted_evidence(kivy_app, monkeypatch, tmp_path, mode):
    import carveracontroller.desktop_stock_tool_reach as desktop

    ws, viewer, send, owner, sections, target, card = reach_card(kivy_app, monkeypatch, tmp_path)
    card.calculate()
    wait_reach(owner)
    prior = card.result
    entered, release = threading.Event(), threading.Event()
    real = desktop.review_tool_reach

    def blocked(*args, **kwargs):
        kwargs["progress"]("Review Initial stock / T1", 3, 20)
        entered.set()
        assert release.wait(8)
        if mode == "refusal":
            raise ValueError("Complete shared outcome budget exhausted")
        return real(*args, **kwargs)

    monkeypatch.setattr(desktop, "review_tool_reach", blocked)
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
        elif mode == "tools":
            card.candidates.text = "T1"
            card.candidates.text = ""
        release.set()
        wait_reach(owner)
        assert card.result is prior if mode in ("cancel", "refusal") else card.result is None
        if mode in ("target", "aba", "tools"):
            assert "withheld" in card.status.text
        assert card.progress_event is None and not owner.running
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()


@pytest.mark.parametrize("width", [360, 800])
def test_access_layout_retains_complete_page_and_fits_actions(kivy_app, monkeypatch, tmp_path, width):
    ws, viewer, send, owner, sections, target, card = reach_card(kivy_app, monkeypatch, tmp_path)
    popup = None
    try:
        card.calculate()
        wait_reach(owner)
        assert card.result is not None
        target.content.remove_widget(card)
        card.toggle()
        card.witness_card.toggle()
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(card)
        popup = Popup(title="Candidate-tool access", content=scroll, size_hint=(None, None), size=(width, 850))
        popup.open()
        pump_frames(8)
        for button in (
            card.review,
            card.cancel_button,
            card.previous,
            card.next,
            card.show,
            card.contact_previous,
            card.contact_next,
        ):
            button.texture_update()
            assert button.texture_size[0] <= button.width - 10 and button.right <= card.right + 1
        popup.export_to_png(str(tmp_path / f"tool-access-{width}.png"))
        send.assert_not_called()
    finally:
        if popup:
            popup.dismiss()
        owner.dispose()


def test_every_target_face_witness_is_accessible_beyond_first_page(kivy_app, monkeypatch, tmp_path):
    from tests.unit.test_stock_solid import box, mesh

    ws, viewer, send, owner, sections, target, card = reach_card(kivy_app, monkeypatch, tmp_path)
    try:
        triangles = box((-0.5, -0.5, 0.5), (0.5, 0.5, 1.5))
        for _ in range(2):
            refined = []
            for a, b, c in triangles:
                middle = tuple((a[i] + b[i] + c[i]) / 3 for i in range(3))
                refined.extend(((a, b, middle), (b, c, middle), (c, a, middle)))
            triangles = refined
        assert len(triangles) == 108
        source = mesh(tmp_path, triangles)
        target.path.text = source.source_path
        target.calculate(reload=True)
        wait(owner)
        card.candidates.text = "T2"
        card.calculate()
        wait_reach(owner)
        card.state.text = "Initial stock"
        row = card.selected_row()
        assert len(row.query.target_contacts) == 108 and len(card.contact.values) == 64
        assert "original target triangle" in card.witness.text
        card.change_contact_page(1)
        assert len(card.contact.values) == 44 and card.contact.text.startswith("65.")
        assert card.contact_previous.disabled is False and card.contact_next.disabled is True
        witness = row.query.target_contacts[64]
        assert f"triangle {witness.triangle}" in card.witness.text and str(witness.witness.sample) in card.witness.text
        card.change_contact_page(-1)
        assert card.contact.text.startswith("1.")
        send.assert_not_called()
    finally:
        owner.dispose()
