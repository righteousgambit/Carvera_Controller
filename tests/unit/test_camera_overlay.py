import time
from types import SimpleNamespace

from kivy.graphics.texture import Texture

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.desktop_camera_registration import CameraRegistrationPanel
from carveracontroller.machine.camera_registration import CameraIntrinsics, CameraPose, CameraRegistration
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.webcam_view import RegisteredCameraImage


def test_contained_image_overlay_respects_padding_and_source_pixels():
    view = RegisteredCameraImage(size=(400, 400), pos=(10, 20), texture=Texture.create(size=(400, 200)))
    view.set_overlay([((0, 0), (400, 200))], (400, 200))
    assert view.image_pixel_to_local((0, 0)) == (10, 320)
    assert view.image_pixel_to_local((400, 200)) == (410, 120)
    view.set_overlay([], (800, 400))
    assert view.image_pixel_to_local((0, 0)) is None


def test_camera_stock_outline_uses_fresh_machine_table_not_preview_cursor():
    recorded = []
    camera_view = SimpleNamespace(set_overlay=lambda segments, size: recorded.append((segments, size)))
    frame = SimpleNamespace(size=(400, 300), age=lambda: 0.1)
    pose = ObservedPose(time.monotonic(), "Idle", (0, -100, 0), (0, 0, 0), 1, 40)
    controller = SimpleNamespace(observed_pose=pose)
    viewer = SimpleNamespace(
        machine_setup=MachineSetup((0, 0, 0), (10, 10, 10), (0, 0, 0)), _machine_pose={"table": (0, 999, 0)}
    )
    workspace = SimpleNamespace(
        camera_texture=SimpleNamespace(views=[camera_view]),
        camera_client=SimpleNamespace(
            snapshot=lambda: (True, frame, None), calibration_snapshot=lambda: (True, frame, 0, "a" * 64)
        ),
        machine=SimpleNamespace(gcode_viewer=viewer, controller=controller),
    )
    panel = CameraRegistrationPanel(workspace)
    panel.registration = CameraRegistration(
        CameraIntrinsics(400, 300, 300, 300, 200, 150), CameraPose((0, 0, 0), (0, 0, 100))
    )
    panel.reference = SimpleNamespace(source_sha256="a" * 64, frame=frame)
    panel.reference_machine_y = -100
    panel.fit_identity = panel._input_identity()
    panel.overlay_enabled = True
    # UI construction may take longer than the freshness window under suite load.
    # Observe the test packet at use time; do not weaken stale-data rejection.
    controller.observed_pose = ObservedPose(time.monotonic(), "Idle", (0, -100, 0), (0, 0, 0), 1, 40)
    panel.update_overlay()
    original = recorded[-1][0]
    assert len(original) == 12
    viewer._machine_pose["table"] = (0, -999, 0)
    panel.update_overlay()
    assert recorded[-1][0] == original
    controller.observed_pose = ObservedPose(time.monotonic(), "Idle", (0, -105, 0), (0, 0, 0), 1, 40)
    panel.update_overlay()
    assert recorded[-1][0] != original
    controller.observed_pose = ObservedPose(time.monotonic() - 2, "Idle", (0, -105, 0), (0, 0, 0), 1, 40)
    panel.update_overlay()
    assert recorded[-1][0] == []


def test_inverse_image_mapping_rejects_letterbox_and_roundtrips_pixels():
    view = RegisteredCameraImage(size=(400, 400), pos=(10, 20), texture=Texture.create(size=(400, 200)))
    view.set_overlay([], (400, 200))
    assert view.local_to_image_pixel((30, 30)) is None
    for pixel in ((20, 30), (200, 100), (399, 199)):
        assert view.local_to_image_pixel(view.image_pixel_to_local(pixel)) == pixel


def test_zoom_anchor_inverse_and_drag_are_one_transform():
    import pytest

    view = RegisteredCameraImage(size=(400, 200), pos=(10, 20), texture=Texture.create(size=(400, 200)))
    view.set_overlay([], (400, 200))
    anchor = (310, 120)
    pixel = view.local_to_image_pixel(anchor)
    view.zoom_by(2, anchor)
    assert view.local_to_image_pixel(anchor) == pytest.approx(pixel)
    assert view.image_pixel_to_local(pixel) == pytest.approx(anchor)
    assert view.local_to_image_pixel((9, 120)) is None
    view.interactive = True
    touch = SimpleNamespace(pos=(210, 120), x=210, y=120, button="left", is_double_tap=False)
    touch.grab = lambda _view: None
    touch.ungrab = lambda _view: None
    assert view.on_touch_down(touch)
    touch.pos, touch.x = (230, 120), 230
    assert view.on_touch_move(touch)
    center = view.frame_center
    assert view.on_touch_move(touch)  # grabbed dispatch of same event
    assert view.frame_center == center
    assert view.on_touch_up(touch)
    view.reset_framing()
    assert view.capture_framing() == {"zoom": 1, "center_x": 0.5, "center_y": 0.5}
