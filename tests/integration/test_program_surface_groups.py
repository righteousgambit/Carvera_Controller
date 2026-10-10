"""Grouped source/face inspection, detached v3 exchange and responsive workbench controls."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.program_surface_clearance import refine_program_surfaces
from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_program_joint_clearance import configured
from tests.unit.test_program_surface_groups import dense_example


@pytest.fixture(scope="module")
def example():
    return dense_example()


@pytest.mark.parametrize("width", [360, 800])
def test_grouped_contacts_members_source_and_portable_resave_preserve_active_setup(
    kivy_app, monkeypatch, tmp_path, example, width
):
    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    source, offsets, report = example
    parent = owner.clearance_panel.program_review
    card = parent.surfaces
    parent.content.remove_widget(card)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(card)
    popup = Popup(title="Exact contact groups", content=scroll, size_hint=(None, None), size=(width, 850))
    path = tmp_path / "grouped.cvsurfacereview"
    monkeypatch.setattr(ws, "choose_profile_file", lambda cb, **kw: cb(str(path)))
    monkeypatch.setattr(ws, "choose_asset_file", lambda cb, **kw: cb(str(path)))
    try:
        parent.retained_inputs = (source, offsets)
        card.toggle()
        popup.open()
        card.show(report)
        pump_frames(5)
        assert card.mode.text == "Exact interval groups"
        assert "original triangle pairs" in card.note.text
        assert card.selected in report.groups and card.members.parent is card.content
        assert card.plot.geometry and "All members remain retained" in card.detail.text
        assert card.selected.first in card.detail.text and card.selected.second in card.detail.text
        card.members.set_expanded(True)
        pump_frames(5)
        assert len(card.member_choice.values) == 64 and not card.member_next.disabled
        card.change_member_page(1)
        assert card.member_choice.text.startswith("65 ·") and len(card.member_choice.values) == 8
        assert not card.member_previous.disabled and card.member_next.disabled
        card.member_choice.text = card.member_choice.values[-1]
        assert "Inspecting pair 72" in card.detail.text
        card.change_member_page(-1)
        assert card.member_choice.text.startswith("1 ·")
        inspect = Mock()
        monkeypatch.setattr(ws.operation_panel, "inspect_line", inspect)
        monkeypatch.setattr(ws.operation_panel, "program", ProgramOperations.from_text(source.text))
        card.inspect_source()
        inspect.assert_called_once_with(card.selected.line, seek=True)
        current_setup, current_record = viewer.machine_setup, owner.record
        card.save_review()
        assert owner.running and card.mode.disabled
        wait(owner)
        assert path.exists(), card.exchange_status.text
        raw = path.read_bytes()
        parent.clear_result()
        card.load_review()
        wait(owner)
        assert card.result.contact_mode == "groups" and card.result.groups == report.groups
        assert viewer.machine_setup is current_setup and owner.record is current_record
        card.save_review()
        wait(owner)
        assert path.read_bytes() == raw
        pump_frames(5)
        card.members.set_expanded(True)
        pump_frames(4)
        scroll.scroll_to(card.member_choice, animate=False)
        pump_frames(4)
        assert card.member_choice.right <= card.members.right + 1 and card.whole.right <= card.right + 1
        popup.export_to_png(str(tmp_path / f"contact-groups-{width}.png"))
        scroll.scroll_to(card.plot, animate=False)
        pump_frames(4)
        popup.export_to_png(str(tmp_path / f"contact-pair-{width}.png"))
        send.assert_not_called()
    finally:
        popup.dismiss()
        owner.dispose()


def test_grouped_review_button_captures_mode_and_mode_change_invalidates_results(kivy_app, monkeypatch):
    import carveracontroller.desktop_program_clearance as desktop

    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    parent = owner.clearance_panel.program_review
    card = parent.surfaces
    original = desktop.review_program_surfaces
    seen = []

    def review(*args, **kwargs):
        seen.append(kwargs["grouped"])
        return original(*args, **kwargs)

    monkeypatch.setattr(desktop, "review_program_surfaces", review)
    try:
        assert card.mode.text == "Exact interval groups"
        card.whole.dispatch("on_release")
        assert owner.running and card.mode.disabled
        wait(owner)
        assert seen == [True] and card.result.contact_mode == "groups"
        assert not card.mode.disabled
        card.mode.text = "Individual triangle contacts"
        assert card.result is None and parent.result is None and card.members.parent is None
        card.whole.dispatch("on_release")
        wait(owner)
        assert seen == [True, False] and card.result.contact_mode == "triangles"
        send.assert_not_called()
    finally:
        owner.dispose()
