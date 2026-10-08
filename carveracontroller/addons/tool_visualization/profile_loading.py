"""Prepare local cutter assets without renderer or controller mutation."""

import math
from collections.abc import Mapping
from dataclasses import replace as replace_dataclass

from carveracontroller.addons.tool_visualization.mesh_builder import build_tool_meshes
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType


def prepare_tool_profiles(definitions, existing, cam_tools, scale, cam_unit_scale, replace=True):
    if not isinstance(definitions, Mapping) or len(definitions) > 1000:
        raise ValueError("Expected up to 1000 numbered ToolDefinition profiles")
    incoming = {}
    for number, definition in definitions.items():
        if type(number) is not int or not 1 <= number <= 9999:
            raise ValueError("Preview tool numbers must be integers from 1 to 9999")
        if not isinstance(definition, ToolDefinition) or not isinstance(definition.tool_type, ToolType):
            raise ValueError("Expected a ToolDefinition with a supported tool shape")
        for key in (
            "diameter",
            "shank_diameter",
            "tip_diameter",
            "corner_radius",
            "length",
            "flute_length",
            "shoulder_length",
            "stickout",
            "thread_depth",
            "thread_pitch",
            "taper_angle_deg",
        ):
            value = getattr(definition, key)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value < 0
                or value > 1000
                or not math.isfinite(value)
            ):
                raise ValueError(f"Invalid millimeter tool dimension: {key}")
        for key in ("diameter", "shank_diameter", "length", "flute_length", "shoulder_length", "thread_pitch"):
            if getattr(definition, key) is not None and getattr(definition, key) <= 0:
                raise ValueError(f"Tool {key} must be positive when specified")
        from carveracontroller.addons.cad_identity import asset_digest

        incoming[number] = replace_dataclass(
            definition,
            number=number,
            geometry_sha256=asset_digest(definition.geometry_path),
            holder_geometry_sha256=asset_digest(definition.holder_geometry_path),
        )
    updated = {} if replace else dict(existing)
    updated.update(incoming)
    if len(updated) > 1000:
        raise ValueError("Preview library may contain at most 1000 tools")
    meshes, fallback = build_tool_meshes(cam_tools, scale=scale * cam_unit_scale)
    library_meshes, _ = build_tool_meshes(updated, scale=scale)
    meshes.update(library_meshes)
    return updated, incoming, meshes, fallback, replace
