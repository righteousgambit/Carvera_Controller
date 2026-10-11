from dataclasses import replace

import pytest

from carveracontroller.addons.tool_visualization.dimension_drawing import assembly_dimensions, drawing_definition_mm
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType


def test_declared_insertion_and_unknown_dimensions():
    tool = ToolDefinition(1, diameter=6.35, shank_diameter=6.35, length=75, flute_length=12, stickout=30)
    dimensions = assembly_dimensions(tool)
    assert [item.value for item in dimensions] == [75, 12, 30, 45]
    assert (dimensions[-1].start, dimensions[-1].end) == (30, 75)
    assert tool.stickout == 30
    unknown = assembly_dimensions(replace(tool, stickout=None))
    assert unknown[-1].value is None
    assert unknown[-1].caption == "Inserted cutter: unknown"
    assert assembly_dimensions(replace(tool, length=None))[-1].value is None


@pytest.mark.parametrize(
    "changes", [{"stickout": 80}, {"stickout": 5}, {"length": 10}, {"length": float("nan")}, {"diameter": -1}]
)
def test_incompatible_geometry_has_no_invented_drawing(changes):
    with pytest.raises(ValueError):
        assembly_dimensions(
            replace(ToolDefinition(1, diameter=6.35, length=75, flute_length=12, stickout=30), **changes)
        )


def test_inch_drawing_converts_linear_dimensions_only_and_preserves_unknowns():
    tool = ToolDefinition(
        7,
        ToolType.THREAD_MILL,
        diameter=0.25,
        length=3,
        flute_length=1,
        shank_diameter=0.25,
        corner_radius=0.015,
        thread_pitch=0.05,
        thread_depth=0.04,
        thread_tip_offset=0.1,
        taper_angle_deg=30,
        thread_teeth=3,
    )
    drawing = drawing_definition_mm(tool, 25.4)
    assert drawing.diameter == 6.35 and drawing.length == pytest.approx(76.2)
    assert drawing.thread_pitch == pytest.approx(1.27)
    assert drawing.thread_depth == pytest.approx(1.016)
    assert drawing.thread_tip_offset == pytest.approx(2.54)
    assert drawing.corner_radius == pytest.approx(0.381)
    assert drawing.flute_length == 25.4 and drawing.shank_diameter == 6.35
    assert drawing.stickout is None and drawing.tip_diameter is None
    assert drawing.taper_angle_deg == 30 and drawing.thread_teeth == 3
    assert tool.length == 3 and tool.flute_length == 1


@pytest.mark.parametrize("scale", [True, 0, -1, float("nan"), float("inf")])
def test_invalid_drawing_units_rejected(scale):
    with pytest.raises(ValueError):
        drawing_definition_mm(ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6, length=50), scale)


@pytest.mark.parametrize("change", [{"tool_type": ToolType.UNKNOWN}, {"diameter": None}, {"length": None}])
def test_incomplete_shape_is_not_drawn_as_an_inferred_cutter(change):
    with pytest.raises(ValueError):
        drawing_definition_mm(replace(ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6, length=50), **change), 1)


@pytest.mark.parametrize("value", [True, -1, float("inf"), float("nan"), 1e308])
def test_bad_optional_shape_dimensions_cannot_publish_an_invalid_drawing(value):
    with pytest.raises(ValueError):
        drawing_definition_mm(
            ToolDefinition(1, ToolType.BULL_NOSE_END_MILL, diameter=6, length=50, corner_radius=value), 25.4
        )
