import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_camera_registration import CameraRegistrationPanel
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.webcam import WebcamClient
from tests.integration.conftest import pump_frames
from tests.unit.test_camera_calibration_file import reference


def panel():
    client = WebcamClient(start=False)
    captured = reference()
    client.frame = captured.frame
    controller = SimpleNamespace(observed_pose=None, _connection_generation=1, executeCommand=Mock())
    workspace = SimpleNamespace(
        camera_client=client,
        camera_texture=SimpleNamespace(views=[]),
        machine=SimpleNamespace(controller=controller),
        choose_profile_file=Mock(),
    )
    view = CameraRegistrationPanel(workspace)
    controller.observed_pose = ObservedPose(time.monotonic(), "Idle", (0, -100, 0), (0, 0, 0), 1, 40)
    return view, client, controller


def test_capture_freezes_exact_frame_and_pose_without_changing_live_view():
    view, client, controller = panel()
    view.capture_reference()
    assert view.reference.frame is client.frame
    assert view.reference.machine_mm == (0, -100, 0)
    assert view.reference_texture.texture is not None
    assert "exposure synchronization unqualified" in view.reference_note.text
    frozen = view.reference.frame
    client.frame = None
    assert view.reference.frame is frozen
    assert view.registration is None
    controller.executeCommand.assert_not_called()


@pytest.mark.parametrize("change", ["points", "camera", "connection"])
def test_fit_rejects_late_result_when_inputs_or_owner_change(monkeypatch, change):
    view, client, controller = panel()
    view.capture_reference()
    view.focal.text = "20 20 12 9"
    view.points.text = "0 0 0 12 9"
    workers = []
    monkeypatch.setattr(
        "carveracontroller.desktop_camera_registration.threading.Thread",
        lambda target, **kwargs: SimpleNamespace(start=lambda: workers.append(target)),
    )
    fake = SimpleNamespace(registration=object(), rms_px=0, max_px=0, outlier_indices=[], warnings=[])
    monkeypatch.setattr("carveracontroller.desktop_camera_registration.fit_camera_pose", lambda *_: fake)
    view.fit()
    assert view.running and len(workers) == 1
    if change == "points":
        view.points.text += "\n1 1 0 13 10"
    elif change == "camera":
        client.configure("http://localhost:18091/changed.jpg")
    else:
        controller._connection_generation += 1
    workers[0]()
    pump_frames(2)
    assert not view.running and view.registration is None
    assert "Fit discarded" in view.note.text
    controller.executeCommand.assert_not_called()


def test_fit_requires_reference_and_save_requires_unchanged_inputs():
    view, _, controller = panel()
    view.fit()
    assert "Capture a reference" in view.note.text
    view.registration = object()
    view.save()
    assert "Refit before saving" in view.note.text
    view.workspace.choose_profile_file.assert_not_called()
    controller.executeCommand.assert_not_called()


def test_point_pick_uses_frozen_pixels_and_requires_known_coordinates():
    view, _, controller = panel()
    view.capture_reference()
    view.reference_view.size = (240, 180)
    view.reference_view.pos = (0, 0)
    touch = SimpleNamespace(pos=(120, 90))
    view.toggle_point_pick()
    assert view._pick_reference(view.reference_view, touch)
    assert not view.points.text and "three finite" in view.note.text
    view.world_point.text = "10 20 0"
    assert view._pick_reference(view.reference_view, touch)
    assert [float(v) for v in view.points.text.split()] == [10, 20, 0, 12, 9]
    assert not view.picking_reference
    assert len(view.reference_view.overlay_segments) == 2
    controller.executeCommand.assert_not_called()


def test_async_load_rejects_changed_profile_and_preserves_current_registration(monkeypatch):
    view, _, _ = panel()
    view.workspace.selected_machine_profile = {"id": "first"}
    workers = []
    monkeypatch.setattr(
        "carveracontroller.desktop_camera_registration.threading.Thread",
        lambda target, **kwargs: SimpleNamespace(start=lambda: workers.append(target)),
    )
    previous = object()
    view.registration = previous
    applied = Mock()
    view._background(lambda: "loaded", applied)
    view.workspace.selected_machine_profile = {"id": "other"}
    workers[0]()
    pump_frames(2)
    applied.assert_not_called()
    assert view.registration is previous and not view.running


def test_capture_refuses_historical_camera_without_replacing_reference():
    view, _, controller = panel()
    view.capture_reference()
    captured = view.reference
    view.workspace.run_recording_panel = SimpleNamespace(camera_replay_enabled=True)
    view.capture_reference()
    assert view.reference is captured
    assert "Show live camera" in view.note.text
    controller.executeCommand.assert_not_called()


def test_repeated_frame_sequence_replaces_reference_texture():
    view, client, _ = panel()
    view.capture_reference()
    original_texture = view.reference_texture.texture
    view.reference = reference()  # Imported sources can reuse a sequence number.
    view._show_reference()
    assert view.reference_texture.texture is not original_texture
    assert view.reference_view.texture is view.reference_texture.texture
