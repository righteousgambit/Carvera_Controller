"""Actual GPU occlusion, retained camera buffers and coalesced preparation."""

import threading
from dataclasses import replace

import pytest
from kivy.graphics.opengl import (
    GL_CULL_FACE,
    GL_DEPTH_FUNC,
    GL_DEPTH_TEST,
    GL_DEPTH_WRITEMASK,
    GL_GREATER,
    GL_STENCIL_TEST,
    glDepthFunc,
    glDepthMask,
    glDisable,
    glEnable,
    glGetBooleanv,
    glGetIntegerv,
    glIsEnabled,
)
from kivy.uix.popup import Popup
from PIL import Image

from carveracontroller.desktop_contact_pose import ContactPoseCanvas
from carveracontroller.machine.pose_view_buffers import pose_camera
from tests.integration.conftest import pump_frames
from tests.integration.test_contact_pose import projected
from tests.unit.test_contact_pose_view import prepared


def show(view):
    canvas = ContactPoseCanvas(view, lambda _text: None)
    popup = Popup(title="Complete GPU pose", content=canvas, size_hint=(None, None), size=(800, 600))
    popup.open()
    projected(canvas)
    return canvas, popup


def close(canvas, popup):
    canvas.dispose()
    popup.dismiss()
    pump_frames(3)
    if canvas.worker is not None:
        canvas.worker.join(5)
        assert not canvas.worker.is_alive()


@pytest.mark.parametrize("reverse", [False, True])
def test_depth_buffer_occludes_far_face_independently_of_submission_order_and_export(kivy_app, tmp_path, reverse):
    view = prepared(tmp_path)[2]
    triangle = lambda y: ((-1.0, y, -1.0), (1.0, y, -1.0), (0.0, y, 1.0))
    front = replace(
        view.bodies[0],
        name="near blue",
        kind="remaining",
        envelope_only=False,
        highlighted_faces=(),
        triangles=(triangle(10.0),),
    )
    far = replace(front, name="far purple", kind="target", triangles=(triangle(0.0),))
    view = replace(view, bodies=(far, front) if reverse else (front, far), pair=("", ""))
    canvas, popup = show(view)
    try:
        canvas.yaw = canvas.tilt = 0
        canvas.queue_redraw()
        projected(canvas)
        w, h = map(int, canvas.renderer.size)
        pixels = canvas.renderer.texture.pixels
        pixel = pixels[((h // 2) * w + w // 2) * 4 : ((h // 2) * w + w // 2) * 4 + 4]
        assert tuple(pixel) == pytest.approx((89, 184, 235, 255), abs=2)
        canvas.export_to_png(str(tmp_path / f"gpu-depth-{reverse}.png"))
        # Export draws into another FBO; the private depth buffer is still retained.
        with Image.open(tmp_path / f"gpu-depth-{reverse}.png") as exported:
            assert exported.convert("RGB").getpixel((exported.width // 2, exported.height // 2)) == pytest.approx(
                (89, 184, 235), abs=2
            )
        assert sum(len(m.indices) // 3 for m in canvas.meshes) == 2
    finally:
        close(canvas, popup)


def test_orbit_pan_zoom_and_resize_retain_buffers_meshes_and_worker(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_contact_pose as module

    view = prepared(tmp_path)[2]
    real = module.prepare_pose_buffers
    calls = []

    def record(*args, **kwargs):
        calls.append(args[0])
        return real(*args, **kwargs)

    monkeypatch.setattr(module, "prepare_pose_buffers", record)
    canvas, popup = show(view)
    try:
        buffers, meshes, worker = canvas.buffers, tuple(canvas.meshes), canvas.worker
        before = canvas.renderer.texture.pixels
        for index in range(30):
            canvas.yaw = 0.02 * index
            canvas.tilt = -0.01 * index
            canvas.pan = (index, -index)
            canvas.zoom = 1 + index * 0.01
            canvas.queue_redraw()
            pump_frames(1)
        popup.size = (700, 500)
        projected(canvas)
        assert canvas.buffers is buffers and tuple(canvas.meshes) == meshes and canvas.worker is worker
        assert len(calls) == 1 and canvas.camera_updates >= 30
        assert canvas.renderer.texture.pixels != before
        camera = pose_camera(buffers, canvas.camera_pose())
        assert canvas.renderer["preview_offset"] == pytest.approx(camera.offset)
        assert canvas.renderer["preview_scale"] == pytest.approx(camera.scale)
        canvas.export_to_png(str(tmp_path / "gpu-retained-orbit.png"))
    finally:
        close(canvas, popup)


def test_camera_input_during_preparation_is_not_a_geometry_restart(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_contact_pose as module

    view = prepared(tmp_path)[2]
    entered, release = threading.Event(), threading.Event()
    calls = []
    real = module.prepare_pose_buffers

    def block(*args, **kwargs):
        calls.append(args[0])
        entered.set()
        assert release.wait(8)
        return real(*args, **kwargs)

    monkeypatch.setattr(module, "prepare_pose_buffers", block)
    canvas = ContactPoseCanvas(view, lambda _text: None)
    popup = Popup(content=canvas, size_hint=(None, None), size=(800, 600))
    popup.open()
    pump_frames(3)
    try:
        assert entered.wait(3)
        generation = canvas.generation
        for index in range(10):
            canvas.yaw = index * 0.2
            canvas.queue_redraw()
            pump_frames(1)
        assert canvas.generation == generation
        release.set()
        projected(canvas)
        assert len(calls) == 1 and canvas.displayed_scene is view
        assert canvas.renderer["preview_rotation"] == pytest.approx(
            pose_camera(canvas.buffers, canvas.camera_pose()).rotation
        )
    finally:
        release.set()
        close(canvas, popup)


def test_scene_aba_cancels_obsolete_geometry_and_keeps_accepted_frame(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_contact_pose as module

    view = prepared(tmp_path)[2]
    canvas, popup = show(view)
    prior = canvas.buffers
    meshes = tuple(canvas.meshes)
    entered, release = threading.Event(), threading.Event()
    real = module.prepare_pose_buffers

    def block(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        return real(*args, **kwargs)

    monkeypatch.setattr(module, "prepare_pose_buffers", block)
    try:
        canvas.scene = replace(view, member=view.member + 1)
        canvas.queue_redraw()
        pump_frames(3)
        assert entered.wait(3)
        canvas.scene = view
        canvas.queue_redraw()
        pump_frames(2)
        release.set()
        projected(canvas)
        assert canvas.displayed_scene is view and canvas.buffers is prior and tuple(canvas.meshes) == meshes
        assert canvas.pending is None
    finally:
        release.set()
        close(canvas, popup)


def test_depth_callback_restores_gl_state_after_real_fbo_draw(kivy_app, tmp_path):
    view = prepared(tmp_path)[2]
    canvas, popup = show(view)
    flags = (GL_DEPTH_TEST, GL_CULL_FACE, GL_STENCIL_TEST)
    original = (
        tuple(bool(glIsEnabled(f)) for f in flags),
        glGetIntegerv(GL_DEPTH_FUNC)[0],
        bool(glGetBooleanv(GL_DEPTH_WRITEMASK)[0]),
    )
    try:
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glEnable(GL_STENCIL_TEST)
        glDepthFunc(GL_GREATER)
        glDepthMask(False)
        canvas.renderer.draw()
        assert tuple(bool(glIsEnabled(f)) for f in flags) == (False, True, True)
        assert glGetIntegerv(GL_DEPTH_FUNC)[0] == GL_GREATER and not glGetBooleanv(GL_DEPTH_WRITEMASK)[0]
    finally:
        states, func, mask = original
        for flag, state in zip(flags, states):
            (glEnable if state else glDisable)(flag)
        glDepthFunc(func)
        glDepthMask(mask)
        close(canvas, popup)
