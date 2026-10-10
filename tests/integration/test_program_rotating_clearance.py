"""Responsive declared-cylinder witness inspection and detached review exchange."""

from unittest.mock import Mock

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_program_joint_clearance import configured
from tests.unit.test_program_rotating_clearance import rotating_example


@pytest.mark.parametrize("width", [360, 800])
def test_rotating_witness_source_exchange_and_current_scene_retention(kivy_app, monkeypatch, tmp_path, width):
    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    source, offsets, report = rotating_example(grouped=True)
    parent = owner.clearance_panel.program_review
    card = parent.surfaces
    parent.content.remove_widget(card)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(card)
    popup = Popup(title="Declared rotating assembly", content=scroll, size_hint=(None, None), size=(width, 850))
    path = tmp_path / "rotating.cvsurfacereview"
    monkeypatch.setattr(ws, "choose_profile_file", lambda cb, **kw: cb(str(path)))
    monkeypatch.setattr(ws, "choose_asset_file", lambda cb, **kw: cb(str(path)))
    try:
        parent.retained_inputs = (source, offsets)
        card.toggle()
        popup.open()
        card.show(report)
        pump_frames(5)
        assert "declared rotating sections" in card.note.text
        index = next(
            i
            for i, (kind, row) in enumerate(card.rows)
            if kind == "rotating possible_contact" and row.first == "T1 cutter" and row.second.startswith("fixed")
        )
        card.page = index // 64
        card.refresh()
        card.choice.text = card.choice.values[index % 64]
        pump_frames(5)
        assert "not entry/exit time" in card.detail.text and "Original obstacle face" in card.detail.text
        assert "Nominal world witness" in card.detail.text and card.plot.geometry and card.members.parent is None
        inspect = Mock()
        monkeypatch.setattr(ws.operation_panel, "inspect_line", inspect)
        monkeypatch.setattr(ws.operation_panel, "program", ProgramOperations.from_text(source.text))
        card.inspect_source()
        inspect.assert_called_once_with(4, seek=True)
        setup, record = viewer.machine_setup, owner.record
        card.save_review()
        assert owner.running
        wait(owner)
        assert path.exists(), card.exchange_status.text
        raw = path.read_bytes()
        parent.clear_result()
        card.load_review()
        wait(owner)
        assert card.result.rotating == report.rotating and card.result.rotating_envelopes == report.rotating_envelopes
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
        popup.export_to_png(str(tmp_path / f"rotating-witness-{width}.png"))
        send.assert_not_called()
    finally:
        popup.dismiss()
        owner.dispose()
