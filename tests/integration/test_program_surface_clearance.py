"""Responsive source-linked surface controls, shared workers and no actuation."""

import threading
from dataclasses import replace
from unittest.mock import Mock

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.machine.program_surface_clearance import refine_program_surfaces
from carveracontroller.machine.surface_motion import SurfaceMesh
from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_program_joint_clearance import configured
from tests.unit.test_program_joint_clearance import program, review


def triangle_report(p):
    base = review(p)
    names = [b["name"] for b in base.records[1]["collision_bodies"]]
    moving = next(n for n in names if n.startswith("carriage"))
    fixed = next(n for n in names if n.startswith("fixed"))
    candidate = replace(base.contacts[0], contact=replace(base.contacts[0].contact, first=moving, second=fixed))
    base = replace(base, contacts=(candidate,))
    return refine_program_surfaces(
        base,
        {
            1: {
                moving: SurfaceMesh.create((((180, 0, 0), (182, 1, 0), (181, 0, 2)),)),
                fixed: SurfaceMesh.create((((9, 0, 0), (11, 1, 0), (10, 0, 2)),)),
            }
        },
    )


@pytest.mark.parametrize("width", [360, 800])
def test_surface_review_layout_triangles_gaps_source_and_body_archive_scope(kivy_app, monkeypatch, tmp_path, width):
    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    parent = owner.clearance_panel.program_review
    card = parent.surfaces
    parent.content.remove_widget(card)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(card)
    popup = Popup(title="Continuous CAD surfaces", content=scroll, size_hint=(None, None), size=(width, 850))
    try:
        card.toggle()
        popup.open()
        pump_frames(5)
        parent.review(False, surfaces=True)
        assert owner.running and card.whole.disabled and card.operation.disabled and parent.whole.disabled
        wait(owner)
        assert parent.result is not None, parent.note.text
        assert card.result is not None and card.result.gaps
        assert "Closed-solid containment" in card.note.text
        assert "Save body review" in parent.save_action.text
        inspect = Mock()
        monkeypatch.setattr(ws.operation_panel, "inspect_line", inspect)
        card.inspect_source()
        inspect.assert_called_once_with(card.selected.line, seek=True)
        # Display a controlled, analytically verified real triangle contact.
        report = triangle_report(ws.operation_panel.program)
        card.show(report)
        assert card.plot.geometry and len(card.plot.geometry[0]) == 3
        assert "Retained faces" in card.detail.text and "midpoint" in card.detail.text
        card.show(replace(report, contacts=report.contacts * 130))
        assert len(card.choice.values) == 64 and not card.next.disabled
        card.change_page(1)
        assert card.choice.text.startswith("65 ·") and not card.previous.disabled
        pump_frames(6)
        scroll.scroll_to(card.plot, animate=False)
        pump_frames(4)
        assert card.whole.right <= card.right + 1
        assert card.plot.width > 200
        popup.export_to_png(str(tmp_path / f"program-surfaces-{width}.png"))
        card.scope.toggle()
        pump_frames(4)
        assert "local" in card.scope_note.text.lower()
        inspect.reset_mock()
        monkeypatch.setattr(ws.operation_panel, "program", program("G1 X12"))
        card.inspect_source()
        inspect.assert_not_called()
        assert "withheld" in card.note.text
        parent.clear_result()
        assert card.result is None and not card.plot.geometry and card.source.disabled
        assert not card.whole.disabled and not card.operation.disabled
        send.assert_not_called()
    finally:
        popup.dismiss()
        owner.dispose()
        pump_frames(3)


@pytest.mark.parametrize("cancel", [False, True])
def test_stale_or_cancelled_surface_worker_withholds_results_and_restores_controls(kivy_app, monkeypatch, cancel):
    import carveracontroller.desktop_program_clearance as desktop

    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    card = owner.clearance_panel.program_review
    original = desktop.review_program_surfaces
    entered, release = threading.Event(), threading.Event()

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        return original(*args, **kwargs)

    monkeypatch.setattr(desktop, "review_program_surfaces", delayed)
    try:
        card.review(False, surfaces=True)
        assert entered.wait(2)
        if cancel:
            owner.cancel()
        else:
            viewer.jaw_offset_mm += 1
        release.set()
        wait(owner)
        assert card.result is None and card.surfaces.result is None
        assert ("cancelled" if cancel else "changed during review") in card.note.text
        assert not card.whole.disabled and not card.surfaces.whole.disabled
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()


def test_selected_surface_scope_saves_body_review_and_reopen_clears_local_triangles(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.machine.program_clearance_archive import load_program_review, report_record

    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    parent = owner.clearance_panel.program_review
    monkeypatch.setattr(
        ws.operation_panel,
        "selected_operation",
        replace(ws.operation_panel.selected_operation, start_line=4, end_line=4),
    )
    try:
        parent.review(True, surfaces=True)
        wait(owner)
        assert parent.result.start_line == parent.result.end_line == 4
        assert parent.surfaces.result is not None
        retained = parent.result
        path = tmp_path / "body-only.cvprogramclearance"
        monkeypatch.setattr(ws, "choose_profile_file", lambda cb, **kw: cb(str(path)))
        parent.save_review()
        wait(owner)
        assert path.exists() and parent.surfaces.result is not None
        archive = load_program_review(path)
        assert report_record(archive.report) == report_record(retained)
        monkeypatch.setattr(ws, "choose_asset_file", lambda cb, **kw: cb(str(path)))
        parent.load_review()
        wait(owner)
        assert report_record(parent.result) == report_record(retained) and parent.surfaces.result is None
        assert parent.surfaces.source.disabled and not parent.surfaces.plot.geometry
        send.assert_not_called()
    finally:
        owner.dispose()


@pytest.mark.parametrize("width", [360, 800])
def test_closed_solid_choices_witness_cavity_source_paging_and_clear(kivy_app, monkeypatch, tmp_path, width):
    from tests.unit.test_program_surface_clearance import solid_report

    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    parent = owner.clearance_panel.program_review
    card = parent.surfaces
    parent.content.remove_widget(card)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(card)
    popup = Popup(title="CAD surfaces & solids", content=scroll, size_hint=(None, None), size=(width, 850))
    try:
        card.toggle()
        popup.open()
        report = solid_report(ws.operation_panel.program)
        card.show(report)
        pump_frames(6)
        assert "1 contained" in card.note.text and "0 separated" in card.note.text
        assert "contained" in card.choice.text and "Closed-solid contained" in card.detail.text
        assert "face 0" in card.detail.text and "X-1 Y-1 Z-1" in card.detail.text
        assert not card.plot.geometry and card.plot.height == 0
        assert "0.25, 0.75]" in card.detail.text
        inspect = Mock()
        monkeypatch.setattr(ws.operation_panel, "inspect_line", inspect)
        card.inspect_source()
        inspect.assert_called_once_with(4, seek=True)
        scroll.scroll_to(card.detail, animate=False)
        pump_frames(4)
        assert card.detail.right <= card.right + 1 and card.whole.right <= card.right + 1
        popup.export_to_png(str(tmp_path / f"program-solids-contained-{width}.png"))
        separated = solid_report(ws.operation_panel.program, hollow=True)
        card.show(separated)
        pump_frames(4)
        assert "1 separated" in card.note.text and "including declared cavities" in card.detail.text
        assert "Contained shell" not in card.detail.text
        popup.export_to_png(str(tmp_path / f"program-solids-cavity-{width}.png"))
        card.show(replace(report, occupancy=report.occupancy * 130))
        assert len(card.choice.values) == 64 and not card.next.disabled
        card.change_page(2)
        assert len(card.choice.values) == 2 and card.next.disabled
        assert card.choice.text.startswith("129 ·")
        card.show(solid_report(ws.operation_panel.program, open_mesh=True))
        assert "solid unavailable" in card.detail.text and not card.plot.geometry
        card.clear()
        assert card.selected is None and card.source.disabled and not card.rows
        assert card.detail.text == "" and not card.plot.geometry
        send.assert_not_called()
    finally:
        popup.dismiss()
        owner.dispose()
        pump_frames(3)
