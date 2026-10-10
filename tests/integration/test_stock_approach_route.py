"""Complete route controls, reported-pose binding and stale delivery rejection."""

import threading
import time
from dataclasses import replace

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.machine.observed_pose import ObservedPose
from tests.integration.conftest import pump_frames
from tests.integration.test_joint_clearance import wait
from tests.integration.test_stock_approach import prepared


@pytest.mark.parametrize("width", [360, 800])
def test_full_route_outcomes_and_start_controls(kivy_app, monkeypatch, tmp_path, width):
    viewer, send, owner, target, card = prepared(kivy_app, monkeypatch, tmp_path)
    popup = None
    try:
        baseline = viewer.machine_setup, owner.record, target.sections.surfaces.result
        card.use_move_end()
        assert card.route_mode.text == "Full approach route"
        card.start_coordinates.text = "-9, -5, -8"
        card.calculate()
        assert owner.running and card.route_mode.disabled and card.start_coordinates.disabled
        assert card.from_move.disabled and card.from_pose.disabled
        wait(owner)
        assert card.result is not None and card.result.leg_labels == ("Retract", "Traverse", "Insertion")
        assert len(card.result.scene.body_review.segments) == 3
        assert card.result.start_evidence.origin == "Declared machine XYZ"
        assert "Retract:" in card.status.text and "Traverse:" in card.status.text and "Insertion:" in card.status.text
        assert "target" in {kind for kind, row in card.rows}
        for index, (kind, row) in enumerate(card.rows):
            card.page = index // 64
            card.render_page()
            card.choice.text = card.choice.values[index % 64]
            if kind == "target":
                assert row.leg.label in card.detail.text and "program frame" in card.detail.text
                assert card.plot.geometry == (card.result.material.target_mesh.triangles[row.contact.triangle],)
            elif kind == "rotating":
                assert card.result.leg_labels[row.segment_index] in card.detail.text
        target.allowance.content.remove_widget(card)
        card.toggle()
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(card)
        popup = Popup(title="Approach route", content=scroll, size_hint=(None, None), size=(width, 850))
        popup.open()
        pump_frames(8)
        for button in (card.from_move, card.from_pose, card.calculate_button, card.cancel_button):
            button.texture_update()
            assert button.texture_size[0] <= button.width and button.right <= card.right + 1
        assert card.start_coordinates.right <= card.right + 1
        scroll.scroll_to(card.from_pose, animate=False)
        pump_frames(4)
        popup.export_to_png(str(tmp_path / f"approach-route-{width}.png"))
        assert baseline == (viewer.machine_setup, owner.record, target.sections.surfaces.result)
        send.assert_not_called()
    finally:
        if popup:
            popup.dismiss()
        owner.dispose()


@pytest.mark.parametrize("mode", ["stationary", "position", "length", "tool", "state", "reconnect", "aba"])
def test_captured_route_retains_packet_and_rechecks_delivery(kivy_app, monkeypatch, tmp_path, mode):
    import carveracontroller.desktop_stock_approach as desktop

    viewer, send, owner, target, card = prepared(kivy_app, monkeypatch, tmp_path)
    ws = owner.workspace
    controller = ws.machine.controller
    monkeypatch.setattr(type(ws), "connected", property(lambda self: True))
    monkeypatch.setattr(controller, "_connection_generation", 17)
    pose = ObservedPose(time.monotonic(), "Idle", (-9.0, -5.0, -8.0), (0.0, 0.0, 2.0), 2, 30.0, 0.0, 0, 0.0)
    monkeypatch.setattr(controller, "observed_pose", pose)
    card.capture_pose()
    assert card.captured_start.observed is pose and card.captured_generation == 17
    entered, release = threading.Event(), threading.Event()
    real = desktop.review_stock_approach

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        result = real(*args, **kwargs)
        # A later stationary packet stays valid; timestamp alone is not a pose change.
        current = replace(pose, timestamp=time.monotonic())
        if mode == "position":
            current = replace(current, machine_mm=(-9.5, -5.0, -8.0))
        elif mode == "length":
            current = replace(current, tool_length_mm=31.0)
        elif mode == "tool":
            current = replace(current, tool=1)
        elif mode == "state":
            current = replace(current, state="Run")
        controller.observed_pose = current
        return result

    monkeypatch.setattr(desktop, "review_stock_approach", blocked)
    try:
        card.calculate()
        assert entered.wait(3)
        if mode == "reconnect":
            controller._connection_generation += 1
        elif mode == "aba":
            previous = card.start_coordinates.text
            card.start_coordinates.text = "-9.5, -5, -8"
            card.start_coordinates.text = previous
        release.set()
        wait(owner)
        if mode == "stationary":
            assert card.result is not None and card.result.start_evidence.observed is pose
        else:
            assert card.result is None and "withheld" in card.status.text
        assert not owner.running and card.progress_event is None
        assert not card.start_coordinates.disabled and not card.from_pose.disabled
        send.assert_not_called()
    finally:
        release.set()
        owner.dispose()


def test_invalid_declared_or_stale_captured_start_starts_no_worker(kivy_app, monkeypatch, tmp_path):
    viewer, send, owner, target, card = prepared(kivy_app, monkeypatch, tmp_path)
    ws = owner.workspace
    monkeypatch.setattr(type(ws), "connected", property(lambda self: True))
    try:
        card.route_mode.text = "Full approach route"
        card.start_coordinates.text = "NaN, 0, 0"
        card.calculate()
        assert not owner.running and card.result is None and "finite" in card.status.text
        monkeypatch.setattr(
            ws.machine.controller,
            "observed_pose",
            ObservedPose(time.monotonic() - 2, "Idle", (-9, -5, -8), (0, 0, 2), 2, 30, 0, 0, 0),
        )
        card.capture_pose()
        assert card.captured_start is None and "fresh Idle" in card.status.text
        send.assert_not_called()
    finally:
        owner.dispose()
