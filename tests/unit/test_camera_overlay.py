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
        camera_client=SimpleNamespace(snapshot=lambda: (True, frame, None)),
        machine=SimpleNamespace(gcode_viewer=viewer, controller=controller),
    )
    panel = CameraRegistrationPanel(workspace)
    panel.registration = CameraRegistration(
        CameraIntrinsics(400, 300, 300, 300, 200, 150), CameraPose((0, 0, 0), (0, 0, 100))
    )
    panel.reference_machine_y = -100
    panel.overlay_enabled = True
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
