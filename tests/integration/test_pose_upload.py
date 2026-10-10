"""Complete mesh staging yields to real UI events and retains accepted frames."""

import time
from dataclasses import replace

import pytest

from carveracontroller.machine.pose_view_buffers import prepare_pose_buffers
from tests.integration.conftest import pump_frames
from tests.integration.test_contact_pose import projected
from tests.integration.test_pose_view_gpu import close, show
from tests.unit.test_contact_pose_view import prepared


def replacement(view):
    # Multiple complete GPU batches, independent of rigid-source reuse.
    triangle = ((-1.0, 10.0, -1.0), (1.0, 10.0, -1.0), (0.0, 10.0, 1.0))
    body = replace(
        view.bodies[0],
        name="replacement",
        kind="target",
        envelope_only=False,
        highlighted_faces=(),
        triangles=(triangle,) * 44_000,
    )
    return replace(view, bodies=(body,), pair=("", ""))


def staging(canvas):
    deadline = time.monotonic() + 20
    while canvas.upload_event is None and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert canvas.upload_event is not None and canvas.projecting


def test_complete_staging_yields_to_camera_input_without_partial_publication(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_contact_pose as module

    monkeypatch.setattr(module, "UPLOAD_SLICE_SECONDS", 0)
    view = prepared(tmp_path)[2]
    canvas, popup = show(view)
    try:
        accepted = canvas.buffers, dict(canvas.body_drawings), tuple(canvas.meshes)
        changed = replacement(view)
        canvas.scene, canvas.names = changed, ("replacement",)
        canvas.queue_redraw()
        staging(canvas)
        assert (canvas.buffers, canvas.body_drawings, tuple(canvas.meshes)) == accepted
        generation = canvas.generation
        canvas.yaw, canvas.pan, canvas.zoom = 0.17, (13, -9), 1.2
        canvas.queue_redraw()
        pump_frames(1)
        assert canvas.projecting and canvas.generation == generation
        assert canvas.buffers is accepted[0] and canvas.displayed_scene is view
        projected(canvas)
        assert canvas.displayed_scene is changed and canvas.upload_event is None
        expected = prepare_pose_buffers(changed, canvas.names)
        assert sum(len(m.indices) // 3 for m in canvas.meshes) == 44_000
        for mesh, (vertices, indices) in zip(canvas.meshes, expected.batches):
            assert list(mesh.vertices) == pytest.approx(vertices)
            assert list(mesh.indices) == indices
        assert canvas.renderer["preview_offset"] != (0, 0)
    finally:
        close(canvas, popup)


@pytest.mark.parametrize("cause", ["aba", "latest", "dispose"])
def test_obsolete_staging_never_replaces_the_accepted_frame(kivy_app, monkeypatch, tmp_path, cause):
    import carveracontroller.desktop_contact_pose as module

    monkeypatch.setattr(module, "UPLOAD_SLICE_SECONDS", 0)
    view = prepared(tmp_path)[2]
    canvas, popup = show(view)
    try:
        accepted, meshes = canvas.buffers, tuple(canvas.meshes)
        canvas.scene, canvas.names = replacement(view), ("replacement",)
        canvas.queue_redraw()
        staging(canvas)
        canvas.scene, canvas.names = view, tuple(b.name for b in view.bodies)
        if cause == "dispose":
            canvas.dispose()
        elif cause == "latest":
            canvas.scene = replace(view, member=view.member + 1)
            canvas.queue_redraw()
        else:
            canvas.queue_redraw()
        projected(canvas)
        assert canvas.upload_event is None
        assert tuple(canvas.meshes) == meshes
        if cause != "latest":
            assert canvas.buffers is accepted and canvas.displayed_scene is view
        else:
            assert canvas.displayed_scene is canvas.scene
        pump_frames(4)
        assert canvas.upload_event is None and not canvas.projecting
    finally:
        close(canvas, popup)


def test_failed_staged_mesh_retains_pixels_contexts_and_complete_accepted_geometry(kivy_app, monkeypatch, tmp_path):
    import carveracontroller.desktop_contact_pose as module

    view = prepared(tmp_path)[2]
    canvas, popup = show(view)
    real, constructed = module.Mesh, []

    def refuse(*args, **kwargs):
        constructed.append(True)
        if len(constructed) == 2:
            raise RuntimeError("GPU mesh allocation refused")
        return real(*args, **kwargs)

    monkeypatch.setattr(module, "Mesh", refuse)
    try:
        accepted = canvas.buffers, dict(canvas.body_drawings), tuple(canvas.meshes)
        canvas.renderer.draw()
        pixels = canvas.renderer.texture.pixels
        canvas.scene, canvas.names = replacement(view), ("replacement",)
        canvas.queue_redraw()
        projected(canvas)
        assert "allocation refused" in canvas.projection_error
        assert (canvas.buffers, canvas.body_drawings, tuple(canvas.meshes)) == accepted
        assert canvas.displayed_scene is view and canvas.upload_event is None
        assert canvas.renderer.texture.pixels == pixels
    finally:
        close(canvas, popup)


def test_failed_complete_publication_restores_uniforms_and_accepted_instructions(kivy_app, monkeypatch, tmp_path):
    view = prepared(tmp_path)[2]
    canvas, popup = show(view)
    real_update = canvas.update_camera
    try:
        accepted = canvas.buffers, dict(canvas.body_drawings), tuple(canvas.meshes)
        canvas.renderer.draw()
        pixels = canvas.renderer.texture.pixels
        translations = {
            name: context["preview_translation"] for name, (_body, context, _meshes) in canvas.body_drawings.items()
        }
        changed = replace(view, member=view.member + 1)

        def refuse(buffers):
            real_update(buffers)
            if buffers is not accepted[0]:
                raise RuntimeError("Complete camera publication refused")

        monkeypatch.setattr(canvas, "update_camera", refuse)
        canvas.scene = changed
        canvas.queue_redraw()
        projected(canvas)
        assert "publication refused" in canvas.projection_error
        assert (canvas.buffers, canvas.body_drawings, tuple(canvas.meshes)) == accepted
        assert canvas.displayed_scene is view and canvas.upload_event is None
        assert {
            name: context["preview_translation"] for name, (_body, context, _meshes) in canvas.body_drawings.items()
        } == translations
        canvas.renderer.draw()
        assert canvas.renderer.texture.pixels == pixels
    finally:
        close(canvas, popup)


def test_private_batch_warming_restores_actual_gl_depth_cull_and_stencil_state(kivy_app, tmp_path):
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

    view = prepared(tmp_path)[2]
    canvas, popup = show(view)
    flags = (GL_DEPTH_TEST, GL_CULL_FACE, GL_STENCIL_TEST)
    original = (
        tuple(bool(glIsEnabled(flag)) for flag in flags),
        glGetIntegerv(GL_DEPTH_FUNC)[0],
        bool(glGetBooleanv(GL_DEPTH_WRITEMASK)[0]),
    )
    steps = None
    try:
        changed = replacement(view)
        changed = replace(changed, bodies=(replace(changed.bodies[0], triangles=changed.bodies[0].triangles[:3]),))
        buffers = prepare_pose_buffers(changed, ("replacement",))
        steps = canvas.drawing_steps(buffers)
        next(steps)  # Context prepared; no mesh draw yet.
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glEnable(GL_STENCIL_TEST)
        glDepthFunc(GL_GREATER)
        glDepthMask(False)
        assert next(steps) == 1  # The actual private FBO warms this mesh.
        assert tuple(bool(glIsEnabled(flag)) for flag in flags) == (False, True, True)
        assert glGetIntegerv(GL_DEPTH_FUNC)[0] == GL_GREATER and not glGetBooleanv(GL_DEPTH_WRITEMASK)[0]
        assert canvas.displayed_scene is view
    finally:
        if steps is not None:
            steps.close()
        states, function, mask = original
        for flag, state in zip(flags, states):
            (glEnable if state else glDisable)(flag)
        glDepthFunc(function)
        glDepthMask(mask)
        close(canvas, popup)
