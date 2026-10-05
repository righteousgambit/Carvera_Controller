"""Content-bound facing recipe review against declared assembly geometry."""

import hashlib
import json
from pathlib import Path

from carveracontroller.machine.assembly_preview import assembly_definition, design_fingerprint
from carveracontroller.machine.surface_planning import FacingParameters, HeightMap


def review_facing_recipe(path, assembly, design, expected_digest=None, *, prepared=False):
    with Path(path).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Facing recipe exceeds 2 MB")
    digest = hashlib.sha256(raw).hexdigest()
    if expected_digest is not None and digest != expected_digest:
        raise ValueError("Recipe file changed since linking; review and link the new content")
    record = json.loads(raw)
    if not isinstance(record, dict) or record.get("schema_version") != 1:
        raise ValueError("Unsupported facing recipe")
    parameters = FacingParameters.from_dict(record["parameters"])
    definition = assembly_definition(assembly, design)
    if definition.tool_type.value != "flat_end_mill":
        raise ValueError("Facing recipe requires a flat end mill")
    geometry = record.get("tool_geometry")
    if not isinstance(geometry, dict) or set(geometry) != {"diameter", "flute_length", "stickout"}:
        raise ValueError("Invalid cutter geometry snapshot")
    if any(type(value) not in (int, float) for value in geometry.values()):
        raise ValueError("Recipe cutter dimensions must be known numbers")
    if any(getattr(definition, key) != value for key, value in geometry.items()):
        raise ValueError("Recipe cutter dimensions differ from this physical assembly")
    if parameters.tool_diameter_mm != definition.diameter:
        raise ValueError("Facing diameter differs from the assembly")
    heights = HeightMap.from_dict(record["surface_map"]) if record.get("surface_map") else None
    if heights and (heights.wcs != parameters.wcs or heights.boundary != parameters.boundary):
        raise ValueError("Surface map boundary/work offset differs from the facing recipe")
    summary = {
        "path": str(Path(path).absolute()),
        "sha256": digest,
        "design_fingerprint": design_fingerprint(design),
        "material": parameters.material,
        "feed_mm_min": parameters.feed_mm_min,
        "spindle_rpm": parameters.spindle_rpm,
        "pass_depth_mm": parameters.pass_depth_mm,
        "stepover_mm": parameters.stepover_mm,
        "tool_id": parameters.tool_id,
        "wcs": parameters.wcs,
    }

    return (summary, parameters, geometry, heights) if prepared else summary
