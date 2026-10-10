"""Full workbench playback, coalesced seeks, state switching and exact return."""

import threading
import time
from fractions import Fraction as F

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from tests.integration.conftest import pump_frames
from tests.integration.test_contact_pose import projected
from tests.integration.test_joint_clearance import wait
from tests.integration.test_stock_generated_machine import prepared


def ready(kivy_app, monkeypatch, tmp_path):
    result = prepared(kivy_app, monkeypatch, tmp_path)
    owner, controller = result[3], result[-1]
    controller.calculate()
    wait(owner)
    return (*result, controller.playback)


def settled(playback):
    deadline = time.monotonic() + 30
    while (playback.inflight or playback.pending is not None or playback.owner.running) and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not playback.inflight and playback.pending is None and not playback.owner.running
    if playback.stage is not None:
        projected(playback.stage.canvas)


def test_arbitrary_partial_seek_visibility_orbit_state_switch_and_return(kivy_app, monkeypatch, tmp_path):
    ws, viewer, send, owner, sections, target, generated, card, playback = ready(kivy_app, monkeypatch, tmp_path)
    before = viewer.machine_setup, viewer.machine_profile, ws.operation_panel.program, tuple(ws.model_card.children)
    camera = tuple(ws.job_camera_splitter.children)
    stage = None
    try:
        playback.seek(F(3, 2))
        settled(playback)
        stage = playback.stage
        assert stage is not None and stage.canvas.scene.pair == ("", "")
        assert stage.canvas.scene.pose.sample == F(1, 2) and stage.canvas.scene.pose.segment_index == 1
        assert "Generated playback" in ws.model_caption.text
        playback.visibility.text = "Stock and target"
        projected(stage.canvas)
        assert sum(len(m.indices) // 3 for m in stage.canvas.meshes) == sum(
            len(b.triangles) for b in stage.canvas.scene.bodies if b.kind != "cad"
        )
        stage.canvas.zoom = 1.5
        stage.canvas.yaw = 0.9
        stage.canvas.pan = (20, 10)
        playback.seek_last()
        settled(playback)
        assert playback.stage is stage
        assert stage.material.remaining_mm3 == generated.result.states[playback.state.text].after.material_mm3
        assert (stage.canvas.zoom, stage.canvas.yaw, stage.canvas.pan) == (1.5, 0.9, (20, 10))
        playback.seek(F(0))
        settled(playback)
        assert stage.material.remaining_mm3 == stage.material.before_mm3
        for state in playback.state.values:
            playback.state.text = state
            settled(playback)
            assert stage.material.state == state
        playback.back.dispatch("on_release")
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
        playback.close()
        owner.dispose()
        if stage is not None:
            projected(stage.canvas)


def test_completion_paced_play_visits_every_move_and_stops_at_final_material(kivy_app, monkeypatch, tmp_path):
    ws, viewer, send, owner, sections, target, generated, card, playback = ready(kivy_app, monkeypatch, tmp_path)
    seen = []
    real = playback.launch

    def record(request):
        seen.append((request[1], request[2]))
        return real(request)

    monkeypatch.setattr(playback, "launch", record)
    try:
        playback.play.dispatch("on_release")
        deadline = time.monotonic() + 45
        while playback.playing and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        settled(playback)
        assert not playback.playing
        count = len(generated.result.moves)
        assert seen == [(i, F(0)) for i in range(count)] + [(count - 1, F(1))]
        assert playback.position == count
        assert playback.stage.material.remaining_mm3 == generated.result.states[playback.state.text].after.material_mm3
        assert "End of generated path" in playback.status.text
        send.assert_not_called()
    finally:
        playback.close()
        owner.dispose()


@pytest.mark.parametrize("case", ["seek", "state_aba", "cancel", "parent", "close", "refusal"])
def test_running_frame_coalesces_or_refuses_and_keeps_previous_display(kivy_app, monkeypatch, tmp_path, case):
    from dataclasses import replace

    import carveracontroller.desktop_generated_playback as module

    ws, viewer, send, owner, sections, target, generated, card, playback = ready(kivy_app, monkeypatch, tmp_path)
    playback.seek(F(0))
    settled(playback)
    stage = playback.stage
    prior = stage.material
    entered, release = threading.Event(), threading.Event()
    real = module.prepare_contact_material
    blocked = False

    def block(*args, **kwargs):
        nonlocal blocked
        if not blocked:
            blocked = True
            entered.set()
            assert release.wait(8)
            if case == "refusal":
                raise ValueError("Complete boundary-face budget exhausted")
        return real(*args, **kwargs)

    monkeypatch.setattr(module, "prepare_contact_material", block)
    try:
        playback.seek_last()
        assert entered.wait(3)
        assert stage.material is prior
        if case == "seek":
            playback.seek(F(1, 4))
            playback.seek(F(3, 4))
        elif case == "state_aba":
            original = playback.state.text
            playback.state.text = playback.state.values[1]
            playback.state.text = original
        elif case == "cancel":
            playback.pause()
        elif case == "parent":
            sections.surfaces.result = replace(sections.surfaces.result)
        elif case == "close":
            playback.close()
        release.set()
        if case == "close":
            wait(owner)
        else:
            settled(playback)
        if case == "seek":
            assert playback.position == F(3, 4) and stage.material is not prior
        elif case == "state_aba":
            assert stage.material.state == original and playback.position == len(generated.result.moves)
        elif case in ("parent", "close"):
            pump_frames(3, sleep=0.12)
            assert stage.closed and viewer.parent is ws.model_card
        else:
            assert stage.material is prior and playback.position == 0 and not playback.playing
        send.assert_not_called()
    finally:
        release.set()
        playback.close()
        owner.dispose()


@pytest.mark.parametrize("width", [360, 800])
def test_playback_compact_workbench_layout_and_real_render(kivy_app, monkeypatch, tmp_path, width):
    result = ready(kivy_app, monkeypatch, tmp_path)
    owner, playback = result[3], result[-1]
    playback.toggle()
    parent = playback.parent
    parent.remove_widget(playback)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(playback)
    popup = Popup(title="Generated material playback", content=scroll, size_hint=(None, None), size=(width, 840))
    try:
        popup.open()
        pump_frames(5)
        for action in (
            playback.view,
            playback.play,
            playback.stop,
            playback.first,
            playback.previous,
            playback.next,
            playback.last,
            playback.fit,
            playback.back,
        ):
            assert action.x >= playback.x and action.right <= playback.right + 1
            assert action.texture_size[0] <= action.width - 8
        popup.export_to_png(str(tmp_path / f"playback-controls-{width}.png"))
        playback.seek_last()
        settled(playback)
        popup.dismiss()
        pump_frames(3)
        result[0].export_to_png(str(tmp_path / f"playback-workspace-{width}.png"))
    finally:
        popup.dismiss()
        playback.close()
        owner.dispose()
        scroll.remove_widget(playback)
        parent.add_widget(playback)


def test_projection_failure_pauses_instead_of_advancing_an_undisplayed_frame(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_contact_pose as module

    result = ready(kivy_app, monkeypatch, tmp_path)
    owner, playback = result[3], result[-1]

    def refuse(*args, **kwargs):
        raise ValueError("Complete GPU projection unavailable")

    monkeypatch.setattr(module, "prepare_pose_buffers", refuse)
    try:
        playback.toggle_play()
        deadline = time.monotonic() + 15
        while playback.playing and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        settled(playback)
        assert not playback.playing and playback.position == 0
        assert playback.stage.canvas.displayed_scene is None
        assert "Playback paused" in playback.status.text
        result[2].assert_not_called()
    finally:
        playback.close()
        owner.dispose()


def test_quarter_move_playback_keeps_exact_samples_and_finishes(kivy_app, monkeypatch, tmp_path):
    result = ready(kivy_app, monkeypatch, tmp_path)
    owner, playback = result[3], result[-1]
    seen = []
    real = playback.launch

    def record(request):
        seen.append((request[1], request[2]))
        return real(request)

    monkeypatch.setattr(playback, "launch", record)
    try:
        count = len(result[-2].result.plan.moves)
        playback.advance.text = "Quarter move"
        playback.seek(F(count - 2))
        settled(playback)
        playback.toggle_play()
        deadline = time.monotonic() + 30
        while playback.playing and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        settled(playback)
        assert playback.position == count and not playback.playing
        assert (count - 2, F(1, 4)) in seen and (count - 1, F(3, 4)) in seen
    finally:
        playback.close()
        owner.dispose()


@pytest.mark.parametrize("fraction", ["1/0", "2", "1" * 129])
def test_invalid_fraction_preserves_completed_frame(kivy_app, monkeypatch, tmp_path, fraction):
    result = ready(kivy_app, monkeypatch, tmp_path)
    owner, playback = result[3], result[-1]
    try:
        playback.seek(F(0))
        settled(playback)
        prior = playback.stage.material
        playback.fraction.text = fraction
        playback.request()
        assert not owner.running and not playback.playing
        assert playback.stage.material is prior
        result[2].assert_not_called()
    finally:
        playback.close()
        owner.dispose()


def test_pause_during_preparation_resumes_from_displayed_position(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_generated_playback as module

    result = ready(kivy_app, monkeypatch, tmp_path)
    owner, playback = result[3], result[-1]
    playback.seek(F(1, 2))
    settled(playback)
    entered, release = threading.Event(), threading.Event()
    real = module.prepare_contact_material
    blocked = False
    samples = []

    def block(source, scene, state, **kwargs):
        nonlocal blocked
        samples.append((scene.pose.segment_index, scene.pose.sample))
        if not blocked:
            blocked = True
            entered.set()
            assert release.wait(8)
        return real(source, scene, state, **kwargs)

    monkeypatch.setattr(module, "prepare_contact_material", block)
    try:
        playback.seek_last()
        assert entered.wait(3)
        playback.pause()
        release.set()
        settled(playback)
        assert playback.move.text == "1" and playback.fraction.text == "1/2"
        assert playback.timeline.value == 0.5
        playback.toggle_play()
        deadline = time.monotonic() + 15
        while len(samples) < 2 and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert samples[1] == (0, F(1, 2))
        playback.pause()
        settled(playback)
        result[2].assert_not_called()
    finally:
        release.set()
        playback.close()
        owner.dispose()
