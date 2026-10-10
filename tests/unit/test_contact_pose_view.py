"""Complete pose placement, original faces, absent geometry and GPU-safe projection."""

from dataclasses import replace
from fractions import Fraction as F
from unittest.mock import Mock

import pytest

from carveracontroller.machine.contact_pose_view import prepare_contact_pose_view, project_contact_pose_view
from carveracontroller.machine.program_cad_first_contact import locate_cad_first_contacts
from carveracontroller.machine.program_surface_clearance import contact_triangles
from carveracontroller.machine.tool_preview import PreviewPose
from tests.unit.test_program_cad_first_contact import scene


def prepared(tmp_path, kind="entry"):
    report = scene(tmp_path, kind=kind)
    row = locate_cad_first_contacts(report).pairs[0]
    return report, row, prepare_contact_pose_view(report, row)


def test_full_original_faces_placements_and_explicit_envelopes(tmp_path):
    report, row, view = prepared(tmp_path)
    assert view.pose == row.pose and view.source_sha256 == report.body_review.program_hash
    assert {b.name for b in view.bodies} == {b.name for b in row.pose.bodies}
    original = contact_triangles(report, row.surface)
    for name, triangle in zip(view.pair, original):
        body = next(b for b in view.bodies if b.name == name)
        assert not body.envelope_only and len(body.triangles) == len(report.meshes[row.tool][name].triangles)
        selected = body.triangles[body.highlighted_faces[0]]
        for point, expected in zip(selected, triangle):
            assert point == pytest.approx(expected, abs=1e-12)
    for body in view.bodies:
        if body.name not in report.meshes[row.tool]:
            assert body.envelope_only and len(body.triangles) == 12 and not body.highlighted_faces
    assert "absent manufactured geometry still unknown" in view.qualification
    last = len(row.group.group.triangle_pairs) - 1
    other = prepare_contact_pose_view(report, row, last)
    assert other.member == last
    assert (
        tuple(next(b for b in other.bodies if b.name == name).highlighted_faces[0] for name in view.pair)
        == row.group.group.triangle_pairs[last]
    )


@pytest.mark.parametrize("kind", ["contained", "open"])
def test_containment_and_unknown_occupancy_do_not_invent_surface_faces(tmp_path, kind):
    _report, row, view = prepared(tmp_path, kind)
    if kind == "contained":
        assert not any(b.highlighted_faces for b in view.bodies)
        with pytest.raises(ValueError, match="no original contact surfaces"):
            project_contact_pose_view(view, PreviewPose(0, 0, 1, 400, 200, 200, 100), view.pair, surfaces_only=True)
    else:
        assert not row.earliest_proven and view.pose == row.pose


def test_complete_projection_retains_triangles_at_varied_orientations_and_viewport_bounds(tmp_path):
    _report, _row, view = prepared(tmp_path)
    names = tuple(b.name for b in view.bodies)
    for yaw, tilt in ((0, 0), (0.6, -0.25), (2.2, 1.4)):
        pose = PreviewPose(yaw, tilt, 1, 360, 180, 230, 170)
        batches = project_contact_pose_view(view, pose, names)
        assert sum(len(i) // 3 for _v, i in batches) == sum(len(b.triangles) for b in view.bodies)
        points = [(v[j], v[j + 1]) for v, _i in batches for j in range(0, len(v), 12)]
        assert all(50 + 36 - 1e-8 <= x <= 410 - 36 + 1e-8 and 80 + 18 - 1e-8 <= y <= 260 - 18 + 1e-8 for x, y in points)
        assert (min(x for x, y in points) + max(x for x, y in points)) / 2 == pytest.approx(230)
    faces = project_contact_pose_view(view, pose, view.pair, surfaces_only=True)
    assert sum(len(i) // 3 for _v, i in faces) == 2


def test_more_than_16bit_vertices_use_complete_ordered_gpu_batches(tmp_path):
    _report, _row, view = prepared(tmp_path)
    body = view.bodies[0]
    large = replace(body, triangles=(body.triangles[0],) * 22000)
    view = replace(view, bodies=(large,))
    batches = project_contact_pose_view(view, PreviewPose(0.6, -0.2, 1, 640, 360, 320, 180), (large.name,))
    assert len(batches) == 2 and sum(len(i) // 3 for _v, i in batches) == 22000
    assert all(len(i) <= 65535 and max(i) <= 65534 and i == list(range(len(v) // 12)) for v, i in batches)


def test_invalid_or_superseded_complete_view_withholds_output(tmp_path):
    report, row, view = prepared(tmp_path)
    with pytest.raises(ValueError, match="differs"):
        prepare_contact_pose_view(report, replace(row, pose=replace(row.pose, sample=F(1))))
    with pytest.raises(ValueError, match="original"):
        prepare_contact_pose_view(report, row, 999999)
    with pytest.raises(InterruptedError):
        prepare_contact_pose_view(report, row, cancelled=lambda: True)
    for names in ((), ("missing",), (view.pair[0], view.pair[0])):
        with pytest.raises(ValueError, match="retained bodies"):
            project_contact_pose_view(view, PreviewPose(0, 0, 1, 400, 200, 200, 100), names)
    cancelled = Mock(side_effect=[False, True])
    with pytest.raises(InterruptedError):
        project_contact_pose_view(view, PreviewPose(0, 0, 1, 400, 200, 200, 100), view.pair, cancelled=cancelled)
    with pytest.raises(ValueError, match="positive"):
        project_contact_pose_view(view, PreviewPose(0, 0, 0, 400, 200, 200, 100), view.pair)
