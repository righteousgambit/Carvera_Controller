"""Capture the current workspace without hardware writes or stale publication."""

import threading
from unittest.mock import Mock

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_kinematic_review import KinematicReviewPanel
from carveracontroller.machine.kinematic_review import machine_from_record
from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.unit.test_scene_joint_clearance import scene_viewer


def configure(ws, monkeypatch):
    viewer = ws.machine.gcode_viewer
    source = scene_viewer()
    for name in (
        "machine_profile",
        "machine_component_profiles",
        "machine_setup",
        "workholding_offset_mm",
        "workholding_rotation_deg",
        "jaw_offset_mm",
        "library_tool_table_mm",
        "repeat_stock_plan",
    ):
        monkeypatch.setattr(viewer, name, getattr(source, name))
    monkeypatch.setattr(viewer, "_preview_program_point", (0, 0, 0))
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    return viewer, send


@pytest.mark.parametrize("width", [360, 800])
def test_capture_review_save_and_source_match_are_explicit_and_responsive(kivy_app, monkeypatch, tmp_path, width):
    ws = kivy_app.root.desktop_workspace
    viewer, send = configure(ws, monkeypatch)
    owner = KinematicReviewPanel(ws)
    card = owner.clearance_panel
    controls = card.scene_capture
    owner.content.remove_widget(card)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(card)
    popup = Popup(title="Workspace geometry capture", content=scroll, size_hint=(None, None), size=(width, 850))
    try:
        card.toggle()
        controls.toggle()
        popup.open()
        pump_frames(8)
        controls.capture()
        wait(owner)
        assert owner.record.get("scene_source") and len(owner.record["collision_bodies"]) == 10, controls.note.text
        assert owner.length_field.text == "0"
        assert [float(field.text) for field in owner.target_fields] == [-180, -120, -110]
        owner.solve()
        wait(owner)
        assert len(owner.reviews) == 2 and all(branch.result.converged for branch in owner.reviews)
        assert owner.seeds.text == "-180 -110 -120\n-180 -110 -120"
        assert machine_from_record(owner.record).forward({"X": -180, "Z": -110, "Y": -120}).tooltip_world.x == -180
        assert "No holder envelope" in controls.note.text
        controls.check_source()
        assert "inputs match" in controls.note.text
        viewer.jaw_offset_mm += 1
        controls.check_source()
        assert "differs" in controls.note.text
        viewer.jaw_offset_mm -= 1
        card.review()
        wait(owner)
        assert card.result is not None, card.note.text
        saved = tmp_path / "scene-review.cvclearance"
        monkeypatch.setattr(ws, "choose_profile_file", lambda cb, **kw: cb(str(saved)))
        card.save_review()
        wait(owner)
        assert saved.exists() and "Saved clearance review" in card.note.text
        pump_frames(8)
        scroll.scroll_to(controls.header, padding=8, animate=False)
        pump_frames(5)
        assert controls.tool.width >= 120
        assert controls.tool.parent.right <= controls.right + 1
        popup.export_to_png(str(tmp_path / f"scene-clearance-{width}.png"))
        send.assert_not_called()
    finally:
        popup.dismiss()
        owner.dispose()
        pump_frames(3)


def test_changed_scene_and_body_drafts_refuse_capture_publication(kivy_app, monkeypatch):
    import carveracontroller.desktop_scene_clearance as desktop

    ws = kivy_app.root.desktop_workspace
    viewer, send = configure(ws, monkeypatch)
    owner = KinematicReviewPanel(ws)
    card = owner.clearance_panel
    controls = card.scene_capture
    card.minimum.text = "2,2,2"
    controls.capture()
    assert not owner.running and "retained body drafts" in controls.note.text
    card.discard_body()
    previous = owner.record
    entered, release = threading.Event(), threading.Event()
    original = desktop.build_scene_clearance

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(desktop, "build_scene_clearance", delayed)
    controls.capture()
    assert entered.wait(2)
    viewer.jaw_offset_mm += 1
    release.set()
    wait(owner)
    assert owner.record is previous and "changed during capture" in controls.note.text
    assert not card.review_action.disabled
    send.assert_not_called()
    owner.dispose()


def test_long_disclosure_headings_wrap_and_recover_after_resize(kivy_app):
    from kivy.metrics import dp

    from carveracontroller.desktop_planning import PlanningCard

    card = PlanningCard(
        "Continuous machine-body clearance with declared geometry and source identity", size_hint_x=None, width=dp(240)
    )
    popup = Popup(title="Responsive disclosure", content=card, size_hint=(None, None), size=(dp(280), dp(500)))
    try:
        popup.open()
        pump_frames(12)
        narrow = card.header.height
        assert narrow > dp(34)
        assert card.header.texture_size[0] <= card.header.width - dp(20)
        assert card.header.texture_size[1] + dp(12) <= card.header.height + 1
        card.toggle()
        pump_frames(8)
        assert card.expanded and card.content in card.children
        card.width = dp(700)
        popup.width = dp(740)
        pump_frames(12)
        assert card.header.height < narrow
        card.toggle()
        pump_frames(8)
        assert not card.expanded and card.content not in card.children
    finally:
        popup.dismiss()
