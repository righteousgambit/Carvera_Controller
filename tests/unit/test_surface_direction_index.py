"""Complete directional indices, independent all-face evidence and legacy replay."""

import hashlib
import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from carveracontroller.machine.program_surface_archive import load_surface_review, save_surface_review
from carveracontroller.machine.surface_directions import DIRECTIONS
from carveracontroller.machine.surface_motion import SurfaceBudget, SurfaceMesh, mesh_contacts
from tests.unit.test_program_surface_archive import resign
from tests.unit.test_surface_motion_exact import full_axis_reference

A = ((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 2.0, 0.0))
B = ((2.0, 2.0, 0.0), (2.0, 0.5, 0.0), (0.5, 2.0, 0.0))


@pytest.mark.parametrize("error", [0.0, 1e-6, 0.01])
def test_direction_index_retains_every_continuous_exact_pair_against_full_axis_oracle(error):
    first = tuple(tuple((p[0] + i * 3.0, p[1], p[2]) for p in A) for i in range(8)) + (((1.0, 1.0, 0.0),) * 3,) * 2
    second = tuple(tuple((p[0] + i * 3.0, p[1], p[2]) for p in B) for i in range(8)) + first[::-1]
    shift, delta = (-2.0, 0.0, 1.0), (4.0, 0.0, -2.0)
    expected = {
        (i, j, *hit)
        for i, a in enumerate(first)
        for j, b in enumerate(second)
        if (hit := full_axis_reference(a, b, shift, delta, error)) is not None
    }
    for method in ("median-v1", "surface-area-v2", "surface-directions-v3"):
        result = mesh_contacts(
            *(SurfaceMesh.create(rows, index_method=method) for rows in (first, second)),
            shift,
            delta,
            position_error_mm=error,
        )
        assert {(c.first_triangle, c.second_triangle, c.lower, c.upper) for c in result} == expected


def test_complete_hierarchy_projection_encloses_all_original_points_without_rounding():
    rows = (A, B, ((0.0, 0.0, 0.0),) * 3, A)
    mesh = SurfaceMesh.create(rows)
    assert mesh.index_method == "surface-directions-v3" and mesh.triangles == rows

    def visit(node):
        ids = tuple(i for child in node.children for i in visit(child)) if node.children else node.ids
        assert len(node.projections) == len(DIRECTIONS)
        for axis, (low, high) in zip(DIRECTIONS, node.projections):
            values = [sum(F(x) * n for x, n in zip(p, axis)) for i in ids for p in rows[i]]
            assert min(values) == low and max(values) == high
        if not node.children:
            assert len(ids) == 1
        return ids

    assert sorted(visit(mesh.root)) == list(range(len(rows)))


def test_direction_bounds_cull_empty_boxes_before_triangle_work_and_keep_node_guard():
    old = tuple(SurfaceMesh.create(rows, index_method="surface-area-v2") for rows in ((A,) * 3, (B,) * 3))
    with pytest.raises(ValueError, match="pairs budget"):
        mesh_contacts(*old, (0, 0, 0), (0, 0, 0), budget=SurfaceBudget(max_pairs=1))
    work = SurfaceBudget(max_pairs=1)
    assert (
        mesh_contacts(SurfaceMesh.create((A,) * 3), SurfaceMesh.create((B,) * 3), (0, 0, 0), (0, 0, 0), budget=work)
        == ()
    )
    assert work.nodes == 1 and work.pairs == 0
    mesh = SurfaceMesh.create((A,) * 3)
    with pytest.raises(ValueError, match="nodes budget"):
        mesh_contacts(mesh, mesh, (0, 0, 0), (0, 0, 0), budget=SurfaceBudget(max_nodes=1))
    with pytest.raises(InterruptedError):
        SurfaceMesh.create((A,), cancelled=lambda: True)


@pytest.mark.parametrize(
    "version,digest",
    [
        (2, "d5c45b1fb64785311c872b6ed20498a2a90e229b417303c29d0ff50f2a7c3f2b"),
        (3, "5763faea5e343003bb7a94a8ab7d141878605f3aaed1cb13c6aa0cfde41b02d2"),
    ],
)
def test_original_40c4fec_writer_fixtures_preserve_v2_v3_evidence_and_work(tmp_path, version, digest):
    from carveracontroller.machine.program_surface_archive import DIRECTION_GROUP_METHOD, DIRECTION_METHOD

    path = Path(__file__).resolve().parents[1] / "fixtures" / f"program-surface-40c4fec-v{version}.cvsurfacereview"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest
    loaded = load_surface_review(path)
    assert loaded.report.nodes == 142 and loaded.report.triangle_pairs == 248
    assert loaded.report.solid_counts == (112, 0, 0, 4)
    assert {m.index_method for rows in loaded.report.meshes.values() for m in rows.values()} == {"surface-area-v2"}
    assert loaded.report.group_counts == ((0, 0) if version == 2 else (12, 236))
    output = tmp_path / "resave.cvsurfacereview"
    save_surface_review(output, loaded.source, loaded.work_offsets, loaded.report)
    assert output.read_bytes() == raw
    data = json.loads(raw)
    data["method"] = DIRECTION_GROUP_METHOD if version == 3 else DIRECTION_METHOD
    output.write_bytes(resign(data))
    with pytest.raises(ValueError, match="differs"):
        load_surface_review(output)


@pytest.mark.parametrize("method", [None, False, 4, [], {}, "unrecognized"])
def test_unknown_or_unhashable_review_method_is_bounded_value_error(tmp_path, method):
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "program-surface-40c4fec-v3.cvsurfacereview"
    data = json.loads(fixture.read_bytes())
    data["method"] = method
    path = tmp_path / "invalid.cvsurfacereview"
    path.write_bytes(resign(data))
    with pytest.raises(ValueError):
        load_surface_review(path)


@pytest.mark.parametrize("error", [0.0, 0.9, 1.0])
def test_exact_diagonal_bounds_remove_only_proved_empty_degenerate_box_space(error):
    line = ((-1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (1.0, 1.0, 0.0))
    point = ((1.0, -1.0, 0.0),) * 3
    old = mesh_contacts(
        *(SurfaceMesh.create((x,), index_method="surface-area-v2") for x in (line, point)),
        (0, 0, 0),
        (0, 0, 0),
        position_error_mm=error,
    )
    result = mesh_contacts(
        *(SurfaceMesh.create((x,)) for x in (line, point)), (0, 0, 0), (0, 0, 0), position_error_mm=error
    )
    # Original conservative degenerate SAT sees overlapping coordinate boxes.
    # The line has x-y=0; the point has x-y=2. An L∞ error box below1 cannot
    # bridge them; error1 touches exactly at the origin and must remain closed.
    assert len(old) == 1
    assert len(result) == int(error == 1.0)
    if result:
        assert result[0].lower == 0 and result[0].upper == 1
