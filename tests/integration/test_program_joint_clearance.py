"""Rendered source-linked program review, bounded choices and stale-input guards."""

import threading
from dataclasses import replace
from unittest.mock import Mock

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_kinematic_review import KinematicReviewPanel
from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_scene_joint_clearance import configure
from tests.unit.test_program_joint_clearance import program


def configured(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    viewer, send = configure(ws, monkeypatch)
    p = program("G1 X11")
    monkeypatch.setattr(ws.operation_panel, "program", p)
    monkeypatch.setattr(ws.operation_panel, "selected_operation", p.operations[-1])
    return ws, viewer, send, KinematicReviewPanel(ws)


@pytest.mark.parametrize("width", [360, 800])
def test_program_review_contacts_source_navigation_and_paging(kivy_app, monkeypatch, tmp_path, width):
    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    card = owner.clearance_panel.program_review
    owner.clearance_panel.content.remove_widget(card)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(card)
    popup = Popup(title="Program machine clearance", content=scroll, size_hint=(None, None), size=(width, 850))
    try:
        card.toggle()
        popup.open()
        pump_frames(8)
        card.review(False)
        assert owner.running and card.whole.disabled and card.operation.disabled
        wait(owner)
        assert card.result is not None, card.note.text
        assert len(card.result.segments) == 2
        assert card.result.uncovered_lines == (3,)
        assert "Coverage gap lines" in card.note.text
        assert card.plot.geometry and card.selected is not None
        assert "source path fraction" in card.details.text
        inspect = Mock()
        monkeypatch.setattr(ws.operation_panel, "inspect_line", inspect)
        card.inspect_source()
        inspect.assert_called_once_with(card.selected.line, seek=True)
        retained = card.result
        # Large retained results never create thousands of dropdown widgets.
        card.show_result(replace(retained, contacts=retained.contacts * 100))
        assert len(card.contact.values) == 64 and not card.next.disabled
        card.change_page(1)
        assert card.page == 1 and not card.previous.disabled
        assert card.selected == card.result.contacts[64]
        assert card.contact.text.startswith("65 ·")
        pump_frames(8)
        scroll.scroll_to(card.plot, animate=False)
        pump_frames(4)
        assert card.frame.right <= card.right + 1
        assert card.plot.width > 200
        popup.export_to_png(str(tmp_path / f"program-clearance-{width}.png"))
        monkeypatch.setattr(ws.operation_panel, "program", program("G1 X12"))
        inspect.reset_mock()
        card.inspect_source()
        inspect.assert_not_called()
        assert "differs" in card.note.text
        assert not card.whole.disabled and not card.operation.disabled
        send.assert_not_called()
    finally:
        popup.dismiss()
        owner.dispose()


def test_scene_change_during_program_review_withholds_result(kivy_app, monkeypatch):
    import carveracontroller.desktop_program_clearance as desktop

    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    card = owner.clearance_panel.program_review
    original = desktop.review_program_clearance
    entered, release = threading.Event(), threading.Event()

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        return original(*args, **kwargs)

    monkeypatch.setattr(desktop, "review_program_clearance", delayed)
    card.review(False)
    assert entered.wait(2)
    viewer.jaw_offset_mm += 1
    release.set()
    wait(owner)
    assert card.result is None and "changed during review" in card.note.text
    assert not card.whole.disabled and not card.operation.disabled
    send.assert_not_called()
    owner.dispose()


def test_selected_operation_scope_and_datum_change_invalidate_program_result(kivy_app, monkeypatch):
    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    card = owner.clearance_panel.program_review
    operation = replace(ws.operation_panel.program.operations[-1], start_line=4, end_line=4)
    monkeypatch.setattr(ws.operation_panel, "selected_operation", operation)
    card.review(True)
    wait(owner)
    assert card.result is not None, card.note.text
    assert len(card.result.segments) == 1 and card.result.start_line == card.result.end_line == 4
    card.frame.text = "G55"
    assert card.result is None and card.source_action.disabled
    card.review(False)
    wait(owner)
    assert card.result is None and "Missing declared frame" in card.note.text
    send.assert_not_called()
    owner.dispose()


def test_cancelled_program_review_restores_controls_without_publication(kivy_app, monkeypatch):
    import carveracontroller.desktop_program_clearance as desktop

    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    card = owner.clearance_panel.program_review
    entered, release = threading.Event(), threading.Event()

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        assert kwargs["cancelled"]()
        raise InterruptedError("cancelled")

    monkeypatch.setattr(desktop, "review_program_clearance", delayed)
    card.review(False)
    assert entered.wait(2)
    owner.cancel()
    release.set()
    wait(owner)
    assert card.result is None and "cancelled" in card.note.text
    assert not card.whole.disabled and not card.operation.disabled
    send.assert_not_called()
    owner.dispose()


@pytest.mark.parametrize("width", [360, 800])
def test_curve_enclosure_report_and_parameter_navigation(kivy_app, monkeypatch, tmp_path, width):
    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    p = program(arc=True)
    monkeypatch.setattr(ws.operation_panel, "program", p)
    card = owner.clearance_panel.program_review
    owner.clearance_panel.content.remove_widget(card)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(card)
    popup = Popup(title="Bounded curve machine clearance", content=scroll, size_hint=(None, None), size=(width, 850))
    try:
        card.toggle()
        popup.open()
        pump_frames(6)
        card.review(False)
        wait(owner)
        assert card.result and card.result.curve_enclosures, card.note.text
        assert card.result.curved_lines == ()
        assert "Bounded curves: 1 · curve gaps: 0" in card.note.text
        assert "L4 G2 ≤" in card.scope_note.text
        assert "physical clearance unqualified" in card.note.text
        assert "same-attachment" in card.scope_note.text
        assert len(card.note.text) < 600
        assert "source curve parameter" in card.details.text
        inspect = Mock()
        monkeypatch.setattr(ws.operation_panel, "inspect_line", inspect)
        card.inspect_source()
        inspect.assert_called_once_with(4, seek=True)
        pump_frames(6)
        scroll.scroll_to(card.note, animate=False)
        pump_frames(4)
        assert card.note.right <= card.right + 1
        popup.export_to_png(str(tmp_path / f"curve-clearance-{width}.png"))
        send.assert_not_called()
    finally:
        popup.dismiss()
        owner.dispose()


def test_same_text_reanalysis_during_curve_review_withholds_stale_certificate(kivy_app, monkeypatch):
    import carveracontroller.desktop_program_clearance as desktop
    from carveracontroller.machine.program_operations import ProgramOperations

    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    p = program(arc=True)
    monkeypatch.setattr(ws.operation_panel, "program", p)
    card = owner.clearance_panel.program_review
    original = desktop.review_program_clearance
    entered, release = threading.Event(), threading.Event()

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        return original(*args, **kwargs)

    monkeypatch.setattr(desktop, "review_program_clearance", delayed)
    card.review(False)
    assert entered.wait(2)
    replacement = ProgramOperations.from_text(p.source_text, arc_tolerance_mm=0.005)
    assert replacement.file_hash == p.file_hash
    monkeypatch.setattr(ws.operation_panel, "program", replacement)
    release.set()
    wait(owner)
    assert card.result is None and "changed during review" in card.note.text
    assert card.save_action.disabled
    send.assert_not_called()
    owner.dispose()


def test_curve_scope_disclosure_keeps_result_and_source_navigation(kivy_app, monkeypatch, tmp_path):
    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    p = program(arc=True)
    monkeypatch.setattr(ws.operation_panel, "program", p)
    card = owner.clearance_panel.program_review
    owner.clearance_panel.content.remove_widget(card)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(card)
    popup = Popup(title="Curve coverage & limits", content=scroll, size_hint=(None, None), size=(360, 850))
    try:
        card.toggle()
        popup.open()
        pump_frames(4)
        card.review(False)
        wait(owner)
        retained, selected = card.result, card.selected
        assert retained and selected and not card.scope.expanded
        compact_height = card.height
        card.scope.header.dispatch("on_release")
        pump_frames(6)
        assert card.scope.expanded and card.height > compact_height
        assert "G2 ≤" in card.scope_note.text and "physical clearance remain unqualified" in card.scope_note.text
        assert card.scope_note.right <= card.right + 1
        scroll.scroll_to(card.scope_note, animate=False)
        pump_frames(4)
        popup.export_to_png(str(tmp_path / "curve-scope-360.png"))
        card.scope.header.dispatch("on_release")
        pump_frames(6)
        assert not card.scope.expanded and card.height == pytest.approx(compact_height)
        assert card.result is retained and card.selected is selected and not card.source_action.disabled
        inspect = Mock()
        monkeypatch.setattr(ws.operation_panel, "inspect_line", inspect)
        card.inspect_source()
        inspect.assert_called_once_with(4, seek=True)
        send.assert_not_called()
    finally:
        popup.dismiss()
        owner.dispose()
