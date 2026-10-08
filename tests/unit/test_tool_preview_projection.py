"""Exact full-mesh framing, shading and cooperative obsolete-view cancellation."""

import pytest

from carveracontroller.machine.tool_preview import PreviewPose, mesh_center, project_mesh


def mesh():
    return [value for p in ((-1, 0, 0), (1, 0, 0), (0, 1, 2)) for value in (*p, 0, 1, 0, 0.8, 0.6, 0.2, 1, 0, 0)]


def test_projection_preserves_all_triangle_vertices_normals_color_and_fit():
    source = mesh()
    center = mesh_center(source, lambda: False)
    assert center == (0, 0.5, 1)
    result, indices = project_mesh(source, [0, 1, 2], center, PreviewPose(0, 0, 1, 200, 100, 100, 100), lambda: False)
    assert indices == [0, 1, 2]
    assert [result[i : i + 3] for i in (0, 12, 24)] == [[60, 60, 0], [140, 60, 0], [100, 140, 0]]
    assert all(result[i + 3 : i + 12] == [0, 1, 0, 0.8, 0.6, 0.2, 1, 0, 0] for i in (0, 12, 24))
    assert source == mesh()


@pytest.mark.parametrize("checkpoint", [1, 3, 6, 9])
def test_projection_interrupts_large_mesh_without_publishing_partial_vertices(checkpoint):
    source = mesh() * 1024
    calls = []

    def cancelled():
        calls.append(True)
        return len(calls) >= checkpoint

    with pytest.raises(InterruptedError):
        project_mesh(
            source, list(range(len(source) // 12)), (0, 0, 1), PreviewPose(0.6, -0.2, 1, 600, 500, 300, 250), cancelled
        )
    assert len(calls) == checkpoint
    assert source == mesh() * 1024


def test_mesh_center_cancel_and_empty_diagnostics():
    with pytest.raises(InterruptedError):
        mesh_center(mesh(), lambda: True)
    with pytest.raises(ValueError, match="empty or incomplete"):
        mesh_center([], lambda: False)
