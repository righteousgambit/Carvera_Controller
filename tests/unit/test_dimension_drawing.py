from dataclasses import replace

import pytest

from carveracontroller.addons.tool_visualization.dimension_drawing import assembly_dimensions
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition


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
