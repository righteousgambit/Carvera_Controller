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


def test_rigid_canonical_buffers_keep_every_world_vertex_and_reuse_after_translation(tmp_path):
    from fractions import Fraction as F

    from carveracontroller.machine.contact_pose_view import prepare_path_pose_view

    report, row, _view = prepared(tmp_path)
    views = [prepare_path_pose_view(report, row.tool, row.segment_index, f) for f in (F(0), F(1, 2), F(1))]
    previous = None
    moved = False
    for view in views:
        buffers = prepare_pose_buffers(view, tuple(b.name for b in view.bodies), previous=previous)
        for body, geometry in zip(view.bodies, buffers.bodies):
            displayed = [
                tuple(v[i + j] + geometry.translation[j] for j in range(3))
                for v, _indices in geometry.batches
                for i in range(0, len(v), 12)
            ]
            assert len(displayed) == len(body.triangles) * 3
            for actual, world in zip(displayed, (p for triangle in body.triangles for p in triangle)):
                assert actual == pytest.approx(world, abs=1e-10)
            if previous is not None and body.display_reference is not None:
                prior = next(b for b in previous.bodies if b.name == body.name)
                assert geometry.batches is prior.batches and geometry.geometry is prior.geometry
                moved |= geometry.translation != prior.translation
        assert sum(b.triangles for b in buffers.bodies) == sum(len(b.triangles) for b in view.bodies)
        previous = buffers
    assert moved


def test_rigid_metadata_never_enters_archive_or_survives_body_edit(tmp_path):
    from dataclasses import asdict, fields

    view = prepared(tmp_path)[2]
    body = next(b for b in view.bodies if b.display_reference is not None)
    assert (
        set(asdict(body))
        == {f.name for f in fields(body)}
        == {"name", "triangles", "envelope_only", "highlighted_faces", "kind"}
    )
    assert replace(body).display_reference is None
    assert replace(body, triangles=body.triangles[:1]).display_reference is None
    archived = type(body)(**asdict(body))
    assert archived.display_reference is None and archived == body


@pytest.mark.parametrize("change", ["cad", "highlight", "pair", "filter", "edited", "visibility"])
def test_reuse_invalidates_changed_geometry_appearance_and_visibility(tmp_path, change):
    from carveracontroller.machine.contact_pose_view import RigidDisplayReference

    view = prepared(tmp_path)[2]
    names = tuple(b.name for b in view.bodies)
    first = prepare_pose_buffers(view, names)
    body = next(b for b in view.bodies if b.display_reference is not None)
    kwargs = {}
    if change == "cad":
        ref = body.display_reference
        # Same name, face count and coordinates, new actual source object.
        geometry = tuple(t for t in ref.triangles)
        assert geometry is not ref.triangles
        altered = replace(body, rigid_reference=RigidDisplayReference(geometry, ref.translation_mm))
    elif change == "highlight":
        altered = replace(body, highlighted_faces=(), rigid_reference=body.display_reference)
    elif change == "edited":
        altered = replace(body, triangles=(((99.0, 0.0, 0.0), (100.0, 0.0, 0.0), (99.0, 0.0, 1.0)),))
    else:
        altered = body
    updated = replace(view, bodies=tuple(altered if b.name == body.name else b for b in view.bodies))
    if change == "pair":
        updated = replace(updated, pair=("", ""))
    elif change == "filter":
        kwargs["surfaces_only"] = True
    elif change == "visibility":
        names = (body.name,)
    second = prepare_pose_buffers(updated, names, previous=first, **kwargs)
    accepted = next(b for b in first.bodies if b.name == body.name)
    current = next(b for b in second.bodies if b.name == body.name)
    if change == "visibility":
        assert len(second.bodies) == 1 and current.batches is accepted.batches
    else:
        assert current.batches is not accepted.batches
    assert second.triangles == sum(b.triangles for b in second.bodies)


def test_cancelled_reuse_preserves_accepted_buffers_and_respects_global_face_caps(tmp_path):
    view = prepared(tmp_path)[2]
    names = tuple(b.name for b in view.bodies)
    first = prepare_pose_buffers(view, names)
    before = tuple(id(b.batches) for b in first.bodies)
    with pytest.raises(InterruptedError):
        prepare_pose_buffers(view, names, previous=first, cancelled=Mock(side_effect=[False, True]))
    assert before == tuple(id(b.batches) for b in first.bodies)
    body = replace(view.bodies[0], triangles=(view.bodies[0].triangles[0],) * 125193)
    duplicated = replace(body, name="another")
    over = replace(view, bodies=(body, duplicated))
    with pytest.raises(ValueError, match="bound"):
        prepare_pose_buffers(over, (body.name, duplicated.name), previous=first)
