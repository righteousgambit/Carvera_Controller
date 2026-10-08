"""Declared tooth-stack visualization shares pitch/count/datum with planning."""

import pytest

from carveracontroller.addons.tool_visualization.mesh_builder import _thread_mill_profile


def test_multiform_draws_exact_complete_tooth_cells_and_tip_datum():
    points = _thread_mill_profile(3, 8, thread_pitch=1.27, thread_teeth=6, thread_tip_offset=0.25)
    crests = [z for z, radius in points if radius == 1.5]
    assert crests == pytest.approx([0.25 + (i + 0.5) * 1.27 for i in range(6)])
    assert points[0][0] == 0 and points[-1][0] == 8
    assert all(a[0] < b[0] for a, b in zip(points, points[1:]))
    assert len([radius for _, radius in _thread_mill_profile(3, 8, thread_pitch=1.27) if radius == 1.5]) == 1


def test_multiform_visualization_rejects_truncated_stack():
    with pytest.raises(ValueError, match="exceeds"):
        _thread_mill_profile(3, 5, thread_pitch=1.27, thread_teeth=6, thread_tip_offset=0.25)


def test_changing_only_tooth_metadata_invalidates_thumbnail_cache():
    from dataclasses import replace

    from carveracontroller.addons.tool_visualization.icon_geometry import geometry_cache_key
    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType

    original = ToolDefinition(
        3, ToolType.THREAD_MILL, diameter=3, flute_length=8, thread_pitch=1.27, thread_teeth=6, thread_tip_offset=0.25
    )
    assert geometry_cache_key(original) != geometry_cache_key(replace(original, thread_teeth=5))
    assert geometry_cache_key(original) != geometry_cache_key(replace(original, thread_tip_offset=0.3))
