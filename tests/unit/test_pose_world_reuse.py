"""World evidence stays complete and exact when displayed rigid bodies are reused."""

import json
from dataclasses import asdict, replace
from fractions import Fraction as F

import pytest

from carveracontroller.machine.contact_pose_view import (
    RigidDisplayReference,
    prepare_contact_pose_view,
    prepare_path_pose_view,
)
from carveracontroller.machine.joint_clearance import bodies_from_record, body_transform
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.surface_motion import SurfaceMesh
from tests.unit.test_contact_pose_view import prepared


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)


def assert_exact_world(report, view):
    machine = machine_from_record(report.body_review.records[view.pose.tool])
    declared, _ = bodies_from_record(report.body_review.records[view.pose.tool], machine)
    bodies = {body.name: body for body in declared}
    placements = {body.name: body for body in view.pose.bodies}
    for body in view.bodies:
        mesh = report.meshes[view.pose.tool].get(body.name)
        if mesh is None:
            assert body.envelope_only and len(body.triangles) == 12
            continue
        origin = body_transform(machine, bodies[body.name], dict.fromkeys("XYZ", 0.0)).translation.tuple
        shift = tuple(placements[body.name].translation_mm[j] - F(origin[j]) for j in range(3))
        expected = tuple(
            tuple(tuple(float(F(p[j]) + shift[j]) for j in range(3)) for p in triangle) for triangle in mesh.triangles
        )
        assert encoded(body.triangles) == encoded(expected)
        assert len(body.triangles) == len(mesh.triangles)
        assert body.display_reference.placed_triangles is body.triangles


@pytest.mark.parametrize("sample", [F(0), F(1, 3), F(1)])
def test_zero_axes_signed_zero_subnormal_and_fractional_shift_keep_exact_world(tmp_path, sample):
    report, _row, _view = prepared(tmp_path)
    meshes = dict(report.meshes[2])
    for name, mesh in meshes.items():
        triangles = (((-0.0, 5e-324, 0.1), (0.3, -5e-324, -0.0), (0.0, -0.0, 1.0)),) + mesh.triangles
        meshes[name] = SurfaceMesh.create(triangles, index_method="median-v1")
    report = replace(report, meshes={2: meshes})
    view = prepare_path_pose_view(report, 2, 0, sample)
    assert_exact_world(report, view)
    again = prepare_path_pose_view(report, 2, 0, sample, previous=view)
    assert encoded(asdict(again)) == encoded(asdict(view))
    assert all(a.triangles is b.triangles for a, b in zip(again.bodies, view.bodies) if not a.envelope_only)


def test_only_same_exact_transform_and_canonical_identity_reuse_complete_world(tmp_path):
    report, _row, _view = prepared(tmp_path)
    first = prepare_path_pose_view(report, 2, 0, F(0))
    next_view = prepare_path_pose_view(report, 2, 0, F(1, 3), previous=first)
    assert_exact_world(report, next_view)
    pairs = {a.name: (a, b) for a, b in zip(first.bodies, next_view.bodies)}
    assert pairs["Wall"][0].triangles is pairs["Wall"][1].triangles
    assert pairs["Moving"][0].triangles is not pairs["Moving"][1].triangles
    backward = prepare_path_pose_view(report, 2, 0, F(0), previous=next_view)
    assert_exact_world(report, backward)
    assert pairs["Moving"][0].triangles == next(b for b in backward.bodies if b.name == "Moving").triangles
    assert pairs["Moving"][0].triangles is not next(b for b in backward.bodies if b.name == "Moving").triangles
    changed_meshes = dict(report.meshes[2])
    changed_meshes["Wall"] = SurfaceMesh.create(changed_meshes["Wall"].triangles, index_method="median-v1")
    changed_report = replace(report, meshes={2: changed_meshes})
    changed = prepare_path_pose_view(changed_report, 2, 0, F(0), previous=first)
    assert next(b for b in changed.bodies if b.name == "Wall").triangles is not pairs["Wall"][0].triangles
    assert_exact_world(changed_report, changed)


@pytest.mark.parametrize("edit", ["source", "world", "reference", "kind", "envelope"])
def test_rehashed_or_edited_previous_frame_cannot_supply_world_geometry(tmp_path, edit):
    report, _row, first = prepared(tmp_path)
    body = next(b for b in first.bodies if b.name == "Wall")
    original = body.triangles
    if edit == "source":
        previous = replace(first, source_sha256="another source")
    else:
        if edit == "world":
            body = replace(body, triangles=tuple(reversed(body.triangles)))
        elif edit == "reference":
            reference = body.display_reference
            body = replace(
                body,
                triangles=tuple(reversed(body.triangles)),
                rigid_reference=RigidDisplayReference(reference.triangles, reference.translation_mm),
            )
        elif edit == "kind":
            body = replace(body, kind="remaining", rigid_reference=body.display_reference)
        else:
            body = replace(body, envelope_only=True, rigid_reference=body.display_reference)
        previous = replace(first, bodies=tuple(body if b.name == "Wall" else b for b in first.bodies))
    actual = prepare_path_pose_view(report, 2, first.pose.segment_index, first.pose.sample, previous=previous)
    wall = next(b for b in actual.bodies if b.name == "Wall")
    assert wall.triangles is not original
    assert_exact_world(report, actual)


def test_group_member_highlights_and_archive_fields_remain_fresh(tmp_path):
    report, row, first = prepared(tmp_path)
    last = len(row.group.group.triangle_pairs) - 1
    other = prepare_contact_pose_view(report, row, last, previous=first)
    assert other.member == last and other.pair == first.pair
    assert (
        tuple(next(b for b in other.bodies if b.name == name).highlighted_faces[0] for name in other.pair)
        == row.group.group.triangle_pairs[last]
    )
    for a, b in zip(first.bodies, other.bodies):
        if not a.envelope_only:
            assert a.triangles is b.triangles
        assert set(asdict(b)) == {"name", "triangles", "envelope_only", "highlighted_faces", "kind"}
    assert "placed_triangles" not in encoded(asdict(other))
    before = encoded(asdict(other))
    with pytest.raises(InterruptedError):
        prepare_contact_pose_view(report, row, last, previous=other, cancelled=lambda: True)
    assert encoded(asdict(other)) == before
