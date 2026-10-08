"""Content-bound facing and hole recipe review against declared assembly geometry."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast, overload

from carveracontroller.machine.assembly_preview import assembly_definition, design_fingerprint
from carveracontroller.machine.surface_planning import FacingParameters, HeightMap

if TYPE_CHECKING:
    from carveracontroller.machine.hole_planning import HoleWorkflow


class RecipeSummary(TypedDict):
    path: str
    sha256: str
    design_fingerprint: str
    feed_mm_min: float
    spindle_rpm: float
    tool_id: str
    wcs: str


class HoleRecipeSummary(RecipeSummary):
    stage: str
    thread: str
    hole_count: int
    tip_angle_deg: float


class FacingRecipeSummary(RecipeSummary):
    material: str
    pass_depth_mm: float
    stepover_mm: float


HOLE_STAGE_SHAPES = {
    "spot": {"drill", "chamfer_mill", "engraving"},
    "drill": {"drill"},
    "bore": {"flat_end_mill"},
    "chamfer": {"chamfer_mill", "engraving"},
    "threadmill": {"thread_mill"},
}


@overload
def review_hole_recipe(
    path: str | Path,
    assembly: Mapping[str, Any],
    design: Mapping[str, Any],
    stage: str,
    expected_digest: str | None = None,
    *,
    prepared: Literal[True],
) -> tuple[HoleRecipeSummary, HoleWorkflow]: ...


@overload
def review_hole_recipe(
    path: str | Path,
    assembly: Mapping[str, Any],
    design: Mapping[str, Any],
    stage: str,
    expected_digest: str | None = None,
    *,
    prepared: Literal[False] = False,
) -> HoleRecipeSummary: ...


@overload
def review_hole_recipe(
    path: str | Path,
    assembly: Mapping[str, Any],
    design: Mapping[str, Any],
    stage: str,
    expected_digest: str | None = None,
    *,
    prepared: bool,
) -> HoleRecipeSummary | tuple[HoleRecipeSummary, HoleWorkflow]: ...


def review_hole_recipe(
    path: str | Path,
    assembly: Mapping[str, Any],
    design: Mapping[str, Any],
    stage: str,
    expected_digest: str | None = None,
    *,
    prepared: bool = False,
) -> HoleRecipeSummary | tuple[HoleRecipeSummary, HoleWorkflow]:
    """Bind one explicit stage to an assembly; other tools remain separate inputs."""
    from carveracontroller.machine.hole_planning import THREAD_SPECS, HoleWorkflow

    with Path(path).open("rb") as stream:
        raw = stream.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise ValueError("Hole recipe exceeds 512 KB")
    digest = hashlib.sha256(raw).hexdigest()
    if expected_digest is not None and digest != expected_digest:
        raise ValueError("Recipe file changed since linking; review and link the new content")
    record = json.loads(raw)
    if not isinstance(record, dict) or record.get("schema") != "carvera-hole-recipe" or record.get("version") != 1:
        raise ValueError("Unsupported hole recipe schema")
    workflow = HoleWorkflow.from_dict(record["workflow"])
    workflow.plan()
    if workflow.thread_spec not in THREAD_SPECS.values():
        raise ValueError("Recipe thread is not in the supported thread library")
    definition = assembly_definition(assembly, design)
    if stage not in HOLE_STAGE_SHAPES or stage not in workflow.tools:
        raise ValueError("Select a stage present in this hole recipe")
    tool = workflow.tools[stage]
    if definition.tool_type.value not in HOLE_STAGE_SHAPES[stage]:
        raise ValueError("Assembly cutter shape does not support the selected recipe stage")
    diameter, flute_length, stickout = definition.diameter, definition.flute_length, definition.stickout
    if diameter is None or flute_length is None or stickout is None:
        raise ValueError("Physical assembly dimensions must be declared")
    if (
        tool.diameter_mm != definition.diameter
        or tool.cutting_length_mm != min(flute_length, stickout)
        or tool.reach_mm != definition.stickout
        or tool.thread_pitch_mm != definition.thread_pitch
        or tool.thread_teeth != definition.thread_teeth
        or tool.thread_tip_offset_mm != (definition.thread_tip_offset or 0)
    ):
        raise ValueError("Recipe cutter dimensions differ from this physical assembly")
    if stage in {"spot", "chamfer"} and definition.tool_type.value != "drill" and definition.tip_diameter != 0:
        raise ValueError("Spot/chamfer stage requires an explicitly zero tip diameter")
    summary: HoleRecipeSummary = {
        "path": str(Path(path).absolute()),
        "sha256": digest,
        "design_fingerprint": design_fingerprint(design),
        "stage": stage,
        "thread": next(key for key, spec in THREAD_SPECS.items() if spec == workflow.thread_spec),
        "hole_count": len(workflow.holes),
        "feed_mm_min": workflow.feed_mm_min,
        "spindle_rpm": workflow.rpm,
        "tool_id": str(tool.number),
        "wcs": workflow.wcs,
        "tip_angle_deg": tool.tip_angle_deg,
    }
    return (summary, workflow) if prepared else summary


def recipe_description(recipe: Mapping[str, Any]) -> str:
    """Readable process details without inventing material or physical outcomes."""
    process = f"{recipe['spindle_rpm']:g} RPM · {recipe['feed_mm_min']:g} mm/min"
    if "stage" in recipe:
        hole = cast(HoleRecipeSummary, recipe)
        return f"{hole['thread']} · {hole['hole_count']} holes · {hole['stage']}\n{process}\nIncluded tip angle {hole['tip_angle_deg']:g}° · recipe input"
    return f"{recipe['material']} · {process}\nDepth {recipe['pass_depth_mm']:g} mm · stepover {recipe['stepover_mm']:g} mm"


@overload
def review_facing_recipe(
    path: str | Path,
    assembly: Mapping[str, Any],
    design: Mapping[str, Any],
    expected_digest: str | None = None,
    *,
    prepared: Literal[True],
) -> tuple[FacingRecipeSummary, FacingParameters, dict[str, float], HeightMap | None]: ...


@overload
def review_facing_recipe(
    path: str | Path,
    assembly: Mapping[str, Any],
    design: Mapping[str, Any],
    expected_digest: str | None = None,
    *,
    prepared: Literal[False] = False,
) -> FacingRecipeSummary: ...


@overload
def review_facing_recipe(
    path: str | Path,
    assembly: Mapping[str, Any],
    design: Mapping[str, Any],
    expected_digest: str | None = None,
    *,
    prepared: bool,
) -> FacingRecipeSummary | tuple[FacingRecipeSummary, FacingParameters, dict[str, float], HeightMap | None]: ...


def review_facing_recipe(
    path: str | Path,
    assembly: Mapping[str, Any],
    design: Mapping[str, Any],
    expected_digest: str | None = None,
    *,
    prepared: bool = False,
) -> FacingRecipeSummary | tuple[FacingRecipeSummary, FacingParameters, dict[str, float], HeightMap | None]:
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
    summary: FacingRecipeSummary = {
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

    return (summary, parameters, cast(dict[str, float], geometry), heights) if prepared else summary
