"""Worker-side path buffers and cutter meshes for one retained local program."""

from dataclasses import dataclass

from carveracontroller.addons.tool_visualization import ToolDefinition, extract_tool_table
from carveracontroller.addons.tool_visualization.profile_loading import prepare_tool_profiles
from carveracontroller.CNC import detect_document_unit, unit_scale_to_mm
from carveracontroller.GcodeViewer import MeshManager
from carveracontroller.machine.program_manifest import PreparedProgramManifest, prepare_program_manifest
from carveracontroller.machine.program_render_preparation import (
    PreparedLegacyProgram,
    bridge_program_colors,
    prepare_legacy_program,
)


@dataclass(frozen=True)
class PreparedProgramPreview:
    program: PreparedLegacyProgram
    manager: MeshManager
    tool_table: dict[int, ToolDefinition]
    document_unit: str
    tool_unit_scale: float
    tool_profiles: tuple
    manifest: PreparedProgramManifest


def prepare_program_preview(lines, inputs, definitions, *, local_path, raw, cancelled=lambda: False):
    """Never creates a widget, GL instruction or controller operation."""
    manager = MeshManager(cancelled=cancelled)
    program = prepare_legacy_program(
        lines,
        inputs,
        consume=lambda rows, end: manager.add_data_arrs(bridge_program_colors(rows), end),
        cancelled=cancelled,
    )
    if cancelled():
        raise InterruptedError("Program preparation cancelled")
    unit = detect_document_unit(program.lines, cancelled=cancelled)
    cam_tools = extract_tool_table(program.lines)
    unit_scale = unit_scale_to_mm(unit)
    profiles = prepare_tool_profiles(definitions, {}, cam_tools, manager.position_scale, unit_scale)
    if cancelled():
        raise InterruptedError("Program preparation cancelled")
    manifest = prepare_program_manifest(local_path, raw, program.lines, cancelled=cancelled)
    if manifest.parsed_lines_sha256 != program.source_hash:
        raise ValueError("Prepared program and manifest source identities differ")
    manager._cancelled = None  # A published buffer must not retain an obsolete request callback.
    return PreparedProgramPreview(program, manager, cam_tools, unit, unit_scale, profiles, manifest)
