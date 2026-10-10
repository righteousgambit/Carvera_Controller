"""Real workbench feed playback, all stock, timing gaps and lifecycle guards."""

import threading
import time
from fractions import Fraction as F

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource
from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames
from tests.integration.test_generated_playback import settled
from tests.integration.test_joint_clearance import wait
from tests.integration.test_program_joint_clearance import configured
from tests.unit.test_program_stock_evolution import stock_example


def ready(kivy_app, monkeypatch, *, repeat=False):
    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    source, offsets, report, _ = stock_example(ball=True, repeat=repeat, rotation=31, tilt=(20, -10))
    program = ProgramOperations.from_text(source.text)
    monkeypatch.setattr(ws.operation_panel, "program", program)
    parent = owner.clearance_panel.program_review
    parent.retained_inputs = (ProgramClearanceSource.capture(program), offsets)
    parent.show_result(report.body_review)
    parent.surfaces.show(report)
    playback = parent.surfaces.playback
    return ws, viewer, send, owner, playback


@pytest.mark.parametrize("width", [360, 800, 1440])
def test_partial_seek_full_material_pan_visibility_and_exact_return(kivy_app, monkeypatch, tmp_path, width):
    import carveracontroller.desktop_program_playback as module

    ws, viewer, send, owner, card = ready(kivy_app, monkeypatch, repeat=True)
    captured = []
    original_prepare = module.prepare_path_pose_view

    def record(*args, **kwargs):
        captured.append(kwargs["previous"])
        return original_prepare(*args, **kwargs)

    monkeypatch.setattr(module, "prepare_path_pose_view", record)
    parent = card.parent
    parent.remove_widget(card)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(card)
    popup = Popup(title="Loaded program playback", content=scroll, size_hint=(None, None), size=(width, 850))
    before = viewer.machine_setup, viewer.machine_profile, ws.operation_panel.program, tuple(ws.model_card.children)
    camera = tuple(ws.job_camera_splitter.children)
    try:
        card.toggle()
        popup.open()
        card.seek(F(3, 2))
        settled(card)
        stage = card.stage
        assert stage is not None and stage.canvas.scene.pose.sample == F(1, 2)
        assert len(stage.program_material.snapshots) == 2
        assert "Loaded program playback" in ws.model_caption.text and "L5" in card.status.text
        stage.canvas.yaw, stage.canvas.zoom, stage.canvas.pan = 0.8, 1.5, (20, 10)
        displayed = stage.canvas.displayed_scene
        card.seek_last()
        settled(card)
        assert captured[0] is None and captured[-1] is displayed
        assert card.stage is stage
        assert stage.program_material.snapshots == card.surfaces.result.stock_evolution.final_snapshots
        assert (stage.canvas.yaw, stage.canvas.zoom, stage.canvas.pan) == (0.8, 1.5, (20, 10))
        card.visibility.text = "Stock and target"
        pump_frames(8)
        assert set(stage.canvas.names) == set(stage.program_material.snapshots)
        card.state.text = "Initial CAD"
        settled(card)
        assert stage.program_material is None and all(b.kind == "cad" for b in stage.canvas.scene.bodies)
        card.visibility.text = "All bodies"
        pump_frames(8)
        stage.canvas.renderer.ask_update()
        stage.canvas.renderer.draw()
        pixels = stage.canvas.renderer.texture.pixels
        assert any(pixels[i] != pixels[0] for i in range(0, len(pixels), 4))
        scroll.scroll_to(card.back, animate=False)
        pump_frames(5)
        assert card.back.right <= card.right + 1 and card.play.right <= card.right + 1
        assert card.rapid.right <= card.right + 1 and card.continue_action.right <= card.right + 1
        popup.export_to_png(str(tmp_path / f"loaded-program-playback-{width}.png"))
        stage.canvas.export_to_png(str(tmp_path / f"loaded-program-machine-{width}.png"))
        card.back.dispatch("on_release")
        assert stage.closed and viewer.parent is ws.model_card
        assert before == (
            viewer.machine_setup,
            viewer.machine_profile,
            ws.operation_panel.program,
            tuple(ws.model_card.children),
        )
        assert camera == tuple(ws.job_camera_splitter.children)
        send.assert_not_called()
    finally:
        popup.dismiss()
        card.close()
        owner.dispose()


def test_feed_play_stops_at_each_gap_then_reaches_exact_final_material(kivy_app, monkeypatch):
    ws, viewer, send, owner, card = ready(kivy_app, monkeypatch)
    try:
        card.rapid.text = "1000"
        card.advance.text = "10×"
        card.play.dispatch("on_release")
        settled(card)
        assert not card.playing and card.gap.line == 2 and "ATC" in card.status.text
        assert not card.continue_action.disabled
        card.continue_action.dispatch("on_release")
        settled(card)
        assert not card.playing and card.gap.line == 3
        card.continue_action.dispatch("on_release")
        deadline = time.monotonic() + 30
        while card.playing and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        settled(card)
        assert not card.playing and card.gap is None
        assert card.position == len(card.surfaces.result.body_review.segments)
        assert card.stage.program_material.snapshots == card.surfaces.result.stock_evolution.final_snapshots
        assert card.clock.elapsed_seconds == pytest.approx(0.72)
        assert "End of retained program" in card.status.text
        send.assert_not_called()
    finally:
        card.close()
        owner.dispose()


@pytest.mark.parametrize("cancel", [False, True])
def test_inflight_stale_or_cancelled_partial_seek_retains_accepted_frame(kivy_app, monkeypatch, cancel):
    import carveracontroller.desktop_program_playback as module

    ws, viewer, send, owner, card = ready(kivy_app, monkeypatch)
    card.seek(F(0))
    settled(card)
    scene = card.stage.canvas.scene
    original = module.prepare_program_material
    entered, release = threading.Event(), threading.Event()

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "prepare_program_material", delayed)
    try:
        card.seek(F(3, 2))
        assert entered.wait(2)
        if cancel:
            card.stop.dispatch("on_release")
        else:
            monkeypatch.setattr(
                ws.operation_panel, "program", ProgramOperations.from_text(ws.operation_panel.program.source_text)
            )
        release.set()
        settled(card)
        if cancel:
            assert card.stage.canvas.scene is scene and card.position == 0
        else:
            pump_frames(10, sleep=0.03)
            assert card.stage is None and viewer.parent is ws.model_card
        assert not owner.running and not card.playing
        send.assert_not_called()
    finally:
        release.set()
        card.close()
        owner.dispose()


def test_prepare_nominal_playback_without_surface_review_never_publishes_clearance(kivy_app, monkeypatch):
    ws, viewer, send, owner = configured(kivy_app, monkeypatch)
    source, offsets, report, captures = stock_example(ball=True)
    program = ProgramOperations.from_text(source.text)
    source = ProgramClearanceSource.capture(program)
    monkeypatch.setattr(ws.operation_panel, "program", program)
    parent = owner.clearance_panel.program_review
    card = parent.surfaces.playback
    monkeypatch.setattr(parent, "inputs", lambda selected: (source, captures, offsets, 1, len(source.lines)))
    parent.surfaces.stock_mode.text = "Initial CAD + ordered stock"
    parent.surfaces.stock_resolution.text = "0.5"
    try:
        card.prepare_action.dispatch("on_release")
        wait(owner)
        assert card.preparation is not None, card.status.text
        assert parent.result is None and parent.surfaces.result is None and parent.retained_inputs is None
        assert "not been reviewed" in card.status.text
        card.seek_last()
        settled(card)
        assert card.stage.program_material.snapshots == report.stock_evolution.final_snapshots
        assert "clearance not reviewed" in ws.model_caption.text
        assert not card.play.disabled
        send.assert_not_called()
    finally:
        card.close()
        owner.dispose()
