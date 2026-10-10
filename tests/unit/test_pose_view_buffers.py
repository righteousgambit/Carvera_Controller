"""Retained complete buffers, finite camera bounds and display refusal semantics."""

import math
from dataclasses import replace
from unittest.mock import Mock

import pytest

from carveracontroller.machine.pose_view_buffers import pose_camera, prepare_pose_buffers
from carveracontroller.machine.tool_preview import PreviewPose
from tests.unit.test_contact_pose_view import prepared


def test_buffers_retain_original_order_faces_colors_and_16bit_batches(tmp_path):
    view = prepared(tmp_path)[2]
    body = replace(
        view.bodies[0], triangles=(view.bodies[0].triangles[0],) * 22000, highlighted_faces=(0,), envelope_only=False
    )
    view = replace(view, bodies=(body,), pair=(body.name, ""))
    buffers = prepare_pose_buffers(view, (body.name,))
    assert buffers.triangles == 22000 and len(buffers.batches) == 2
    assert all(len(i) <= 65535 and max(i) <= 65534 for _v, i in buffers.batches)
    first = buffers.batches[0][0]
    assert tuple(first[:3]) == body.triangles[0][0]
    assert tuple(first[6:9]) == (0.25, 1, 0.86)
    assert tuple(first[36 + 6 : 36 + 9]) == (0.25, 0.65, 0.64)
    faces = prepare_pose_buffers(view, (body.name,), surfaces_only=True)
    assert faces.triangles == 1 and len(faces.batches[0][1]) == 3


@pytest.mark.parametrize("yaw,tilt", [(0, 0), (0.6, -0.25), (2.2, 1.4), (-1.5, -1.4)])
def test_camera_contains_every_face_and_depth_at_varied_orbit_without_changing_buffers(tmp_path, yaw, tilt):
    view = prepared(tmp_path)[2]
    buffers = prepare_pose_buffers(view, tuple(b.name for b in view.bodies))
    batches = buffers.batches
    pose = PreviewPose(yaw, tilt, 1, 360, 180, 230, 170)
    camera = pose_camera(buffers, pose)
    cy, sy, ct, st = camera.rotation
    for vertices, _indices in batches:
        for i in range(0, len(vertices), 12):
            x, y, z = (vertices[i + j] - camera.center[j] for j in range(3))
            x, y = cy * x - sy * y, sy * x + cy * y
            sx = camera.offset[0] + x * camera.scale
            sz = camera.offset[1] + (st * y + ct * z) * camera.scale
            depth = (ct * y - st * z) * camera.depth_scale
            assert 86 - 1e-8 <= sx <= 374 + 1e-8 and 98 - 1e-8 <= sz <= 242 + 1e-8
            assert -0.90000001 <= depth <= 0.90000001
    assert buffers.batches is batches
    assert camera.offset == pytest.approx((230, 170))


@pytest.mark.parametrize("kind,color", [("remaining", (0.35, 0.72, 0.92)), ("target", (0.69, 0.49, 0.94))])
def test_material_colors_and_empty_remaining_state_are_preserved(tmp_path, kind, color):
    view = prepared(tmp_path)[2]
    body = replace(view.bodies[0], kind=kind, envelope_only=False, highlighted_faces=())
    buffers = prepare_pose_buffers(replace(view, bodies=(body,), pair=("", "")), (body.name,))
    assert tuple(buffers.batches[0][0][6:9]) == color
    if kind == "remaining":
        empty = prepare_pose_buffers(replace(view, bodies=(replace(body, triangles=()),)), (body.name,))
        assert not empty.batches and empty.triangles == 0
        assert math.isfinite(pose_camera(empty, PreviewPose(0, 0, 1, 400, 200, 200, 100)).scale)


@pytest.mark.parametrize("cause", ["names", "cancel", "range", "budget", "surfaces"])
def test_invalid_or_cancelled_buffers_do_not_return_partial_geometry(tmp_path, cause):
    view = prepared(tmp_path)[2]
    names = tuple(b.name for b in view.bodies)
    kwargs = {}
    if cause == "names":
        names = ("missing",)
    elif cause == "cancel":
        kwargs["cancelled"] = Mock(side_effect=[False, True])
    elif cause == "range":
        view = replace(view, bodies=(replace(view.bodies[0], triangles=(((math.inf, 0, 0), (0, 1, 0), (0, 0, 1)),)),))
        names = (view.bodies[0].name,)
    elif cause == "budget":
        view = replace(view, bodies=(replace(view.bodies[0], triangles=(view.bodies[0].triangles[0],) * 250385),))
        names = (view.bodies[0].name,)
    else:
        view = replace(view, bodies=tuple(replace(b, highlighted_faces=()) for b in view.bodies))
        kwargs["surfaces_only"] = True
    with pytest.raises(InterruptedError if cause == "cancel" else ValueError):
        prepare_pose_buffers(view, names, **kwargs)


@pytest.mark.parametrize("value", [0, math.inf, math.nan])
def test_invalid_camera_retains_no_nonfinite_uniforms(tmp_path, value):
    view = prepared(tmp_path)[2]
    buffers = prepare_pose_buffers(view, tuple(b.name for b in view.bodies))
    with pytest.raises(ValueError, match="finite and positive"):
        pose_camera(buffers, PreviewPose(0, 0, value, 400, 200, 200, 100))
