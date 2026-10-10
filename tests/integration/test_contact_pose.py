"""Detached full assembly in the actual left pane, preserving active state and camera."""

import threading
import time

import pytest
from kivy.core.window import Window
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_stock_generated_machine import prepared


def ready(kivy_app, monkeypatch, tmp_path):
    result = prepared(kivy_app, monkeypatch, tmp_path)
    owner, card = result[3], result[-1]
    card.calculate()
    wait(owner)
    card.locate_cad()
    wait(owner)
    index = next(i for i, (_, row) in enumerate(card.rows) if row.group is not None)
    card.page = index // 64
    card.render_page()
    card.choice.text = card.choice.values[index % 64]
    return result


def projected(canvas):
    deadline = time.monotonic() + 20
    pump_frames(3)
    while (canvas.projecting or canvas.pending is not None) and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not canvas.projecting and canvas.pending is None


def test_left_pane_complete_pose_visibility_and_return_restore_exact_viewer(kivy_app, monkeypatch, tmp_path):
    ws, viewer, send, owner, sections, target, generated, card = ready(kivy_app, monkeypatch, tmp_path)
    stage = None
    try:
        camera = tuple(ws.job_camera_splitter.children)
        before = (
            viewer.machine_setup,
            viewer.machine_profile,
            viewer.pose_mode,
            ws.operation_panel.program,
            viewer.parent,
            tuple(ws.model_card.children),
        )
        card.pose_button.dispatch("on_release")
        assert owner.running and card.pose_button.disabled
        wait(owner)
        stage = card.pose_stage
        assert stage is not None and ws.contact_pose_stage is stage
        assert stage.canvas.parent is ws.model_card and viewer.parent is None
        assert camera == tuple(ws.job_camera_splitter.children)
        assert "Nominal contact pose" in ws.model_caption.text and not card.pose_return.disabled
        assert "envelope only" in card.pose_scope.text or "Envelope only" in card.pose_scope.text
        projected(stage.canvas)
        assert stage.canvas.meshes
        ws._update_model_caption("Refreshed ordinary program caption")
        assert ws.model_caption.text == stage.caption
        count = lambda: sum(len(m.indices) // 3 for m in stage.canvas.meshes)
        assert count() == sum(len(b.triangles) for b in stage.canvas.scene.bodies)
        card.pose_bodies.text = "Original contact surfaces"
        projected(stage.canvas)
        assert count() == 2
        card.pose_bodies.text = "Contacting bodies"
        projected(stage.canvas)
        assert count() == sum(len(b.triangles) for b in stage.canvas.scene.bodies if b.name in stage.canvas.scene.pair)
        card.pose_bodies.text = card.pose_bodies.values[3]
        projected(stage.canvas)
        assert count() == len(stage.canvas.scene.bodies[0].triangles)
        stage.canvas.zoom_by(2)
        card.pose_fit.dispatch("on_release")
        projected(stage.canvas)
        assert stage.canvas.zoom == 1 and stage.canvas.pan == (0, 0)
        latest_caption = ws._program_model_caption
        card.pose_return.dispatch("on_release")
        assert card.pose_stage is None and stage.closed and stage.canvas.closed.is_set()
        assert ws.model_caption.text == latest_caption
        assert before == (
            viewer.machine_setup,
            viewer.machine_profile,
            viewer.pose_mode,
            ws.operation_panel.program,
            viewer.parent,
            tuple(ws.model_card.children),
        )
        assert tuple(ws.job_camera_splitter.children) == camera
        send.assert_not_called()
    finally:
        card.close_pose()
        owner.dispose()
        if stage is not None:
            projected(stage.canvas)


@pytest.mark.parametrize("mode", ["cancel", "refusal", "parent", "target"])
def test_complete_pose_prepare_cancel_refusal_and_stale_never_replace_left_view(kivy_app, monkeypatch, tmp_path, mode):
    from dataclasses import replace

    import carveracontroller.desktop_stock_generated_machine as desktop

    ws, viewer, send, owner, sections, target, generated, card = ready(kivy_app, monkeypatch, tmp_path)
    entered, release = threading.Event(), threading.Event()
    real = desktop.prepare_contact_pose_view
    before = tuple(ws.model_card.children)

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        if mode == "refusal":
            raise ValueError("Complete pose triangle budget exhausted")
        return real(*args, **kwargs)

    monkeypatch.setattr(desktop, "prepare_contact_pose_view", blocked)
    try:
        card.view_pose()
        assert entered.wait(3)
        if mode == "cancel":
            card.cancel_button.dispatch("on_release")
        elif mode == "parent":
            sections.surfaces.result = replace(sections.surfaces.result)
        elif mode == "target":
            target.translation.text = "1, 0, 0"
            target.translation.text = "0, 0, 0"
        release.set()
        wait(owner)
        assert card.pose_stage is None and tuple(ws.model_card.children) == before
        assert (
            "cancel" in card.pose_status.text.lower()
            or "withheld" in card.pose_status.text
            or "budget" in card.pose_status.text
        )
        send.assert_not_called()
    finally:
        release.set()
        card.close_pose()
        owner.dispose()


@pytest.mark.parametrize("cause", ["member", "clear", "dispose", "escape"])
def test_pose_close_on_evidence_change_or_disposal(kivy_app, monkeypatch, tmp_path, cause):
    ws, viewer, send, owner, sections, target, generated, card = ready(kivy_app, monkeypatch, tmp_path)
    stage = None
    try:
        card.view_pose()
        wait(owner)
        stage = card.pose_stage
        projected(stage.canvas)
        if cause == "member":
            card.pair.text = str(len(card.selected_pose_row.group.group.triangle_pairs) - 1)
        elif cause == "clear":
            card.clear()
        elif cause == "escape":
            assert ws._workspace_keydown(Window, 27, 0, "", [])
        else:
            owner.dispose()
            pump_frames(3, sleep=0.12)
        assert stage.closed and stage.canvas.closed.is_set() and viewer.parent is ws.model_card
        send.assert_not_called()
    finally:
        card.close_pose()
        owner.dispose()
        if stage is not None:
            projected(stage.canvas)


@pytest.mark.parametrize("width", [360, 800])
def test_contact_pose_workbench_controls_and_left_canvas_render_at_compact_width(
    kivy_app, monkeypatch, tmp_path, width
):
    ws, viewer, send, owner, sections, target, generated, card = ready(kivy_app, monkeypatch, tmp_path)
    old_size = Window.size
    popup = stage = None
    try:
        Window.size = (1280, 820)
        pump_frames(4)
        card.view_pose()
        wait(owner)
        stage = card.pose_stage
        projected(stage.canvas)
        card.pose_bodies.text = "Contacting bodies"
        projected(stage.canvas)
        ws.export_to_png(str(tmp_path / f"contact-pose-workspace-{width}.png"))
        card.parent.remove_widget(card)
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(card)
        popup = Popup(title="Retained contact pose", content=scroll, size_hint=(None, None), size=(width, 850))
        popup.open()
        card.toggle()
        pump_frames(4)
        for action in (card.pose_button, card.pose_return, card.pose_fit):
            assert card.x <= action.x < action.right <= card.right + 1
        scroll.scroll_y = 0.42
        pump_frames(4)
        popup.export_to_png(str(tmp_path / f"contact-pose-controls-{width}.png"))
        assert stage.canvas.width > 100 and stage.canvas.height > 100
        send.assert_not_called()
    finally:
        card.close_pose()
        owner.dispose()
        if popup:
            popup.dismiss()
        if stage:
            projected(stage.canvas)
        Window.size = old_size
