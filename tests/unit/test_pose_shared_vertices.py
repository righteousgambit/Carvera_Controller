"""Shared CAD corners preserve every face and exact placed-world serialization."""

from dataclasses import replace
from fractions import Fraction as F

import pytest

from carveracontroller.machine.contact_pose_view import prepare_path_pose_view
from carveracontroller.machine.surface_motion import SurfaceMesh
from tests.unit.test_contact_pose_view import prepared
from tests.unit.test_pose_world_reuse import assert_exact_world, encoded


def shared_report(tmp_path):
    report, _row, _view = prepared(tmp_path)
    meshes = dict(report.meshes[2])
    corners = ((-0.0, 5e-324, 0.1), (0.3, -5e-324, -0.0), (0.0, -0.0, 1.0), (0.3, 0.5, 1.0))
    faces = ((corners[0], corners[1], corners[2]), (corners[2], corners[1], corners[3])) * 2048
    meshes["Moving"] = SurfaceMesh.create(faces, index_method="median-v1")
    return replace(report, meshes={2: meshes})


@pytest.mark.parametrize("sample", [F(0), F(1, 3), F(1)])
def test_large_shared_corner_mesh_keeps_every_ordered_face_and_exact_coordinate(tmp_path, sample):
    report = shared_report(tmp_path)
    original = encoded(report.meshes[2]["Moving"].triangles)
    view = prepare_path_pose_view(report, 2, 0, sample)
    assert_exact_world(report, view)
    moving = next(b for b in view.bodies if b.name == "Moving")
    assert len(moving.triangles) == 4096
    assert moving.triangles[0][2] == moving.triangles[1][0]
    assert encoded(report.meshes[2]["Moving"].triangles) == original
    backward = prepare_path_pose_view(report, 2, 0, F(0), previous=view)
    assert_exact_world(report, backward)
    assert encoded(report.meshes[2]["Moving"].triangles) == original


def test_cancellation_inside_shared_mesh_retains_previous_complete_world(tmp_path):
    report = shared_report(tmp_path)
    previous = prepare_path_pose_view(report, 2, 0, F(0))
    before = encoded(previous)
    checks = 0

    def cancelled():
        nonlocal checks
        checks += 1
        return checks == 24

    with pytest.raises(InterruptedError):
        prepare_path_pose_view(report, 2, 0, F(1, 3), previous=previous, cancelled=cancelled)
    assert checks == 24
    assert encoded(previous) == before
